"""Leave Request orchestration — the read-only preview (2.5) and the atomic submission (2.6).

Implements: FR-08 (the day count and its reasoned/named breakdown, plus the projected balance,
BEFORE a request is submitted — the preview; AND the submission that reserves the days and freezes
the count on the row), FR-09 (managerless auto-approval), AD-2 (this is the sole caller-facing
entry to `domain.calendar`'s count + breakdown — the client computes nothing), AD-3 (the preview
is ADVISORY and side-effect-free — a READ session, NO lock, NO write; the submission is ONE write
transaction that decides admission from the balance row read `FOR UPDATE`), AD-8 (one `audit_entry`
per submission, same transaction), AD-18 (`leave_days` is frozen on the request row at admission).
DR-3/AD-5 (STORED balance quantities travel up; derived figures are formed at the `api/`
projection, never here). SM-6.

The file name is plural (`leave_requests`) to match `api/v1/leave_requests.py` and the codebase's
`leave_types`/`balances` idiom; it is the spine's `services/leave_request`.

--- Preview vs. submission: the deliberate split ---

The preview is TOTAL and permissive (2.5 AC5): `count_leave_days`/`excluded_dates` never raise on
their inputs, so a start-after-end range previews as `0` days and an overspend shows a negative
`available_after` — never a refusal. Range VALIDITY and its refusals — `INVALID_DATE_RANGE`,
`PAST_DATE_RANGE`, `SPANS_TWO_LEAVE_YEARS`, `ZERO_LEAVE_DAYS` — and `INSUFFICIENT_BALANCE` are the
SUBMISSION path's (2.6): the first three are pure date-property checks (`domain/
leave_request_rules`) made before the lock; the last two are decided under the balance lock (via
`services/balances.reserve`/`consume_direct`). `preview_leave_request` still imports no balance
mutator and raises no refusal; `submit_leave_request` owns all of them.
"""

import datetime
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Row
from sqlalchemy.orm import Session

from app.domain import calendar
from app.domain import leave_request_rules as rules
from app.domain import vocabulary
from app.domain.calendar import ExcludedDate
from app.domain.errors import DomainError
from app.repositories import audit_entry as audit_entry_repo
from app.repositories import holiday as holiday_repo
from app.repositories import leave_balance as leave_balance_repo
from app.repositories import leave_request as leave_request_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import authorization as authz
from app.services import balances
from app.services import rollover

# The four Leave Request status values, re-exported for the `api/` status filter (Story 2.7). The
# route cannot import `domain/` (contract 2) or type the literal (`test_vocabulary_literals.py`), so
# it reads the allowed filter values through this `api → services` edge — the same indirection
# `authz` uses for the role constants — and builds its query-param enum from them at runtime.
LEAVE_STATUS_VALUES: tuple[str, ...] = (
    vocabulary.STATUS_PENDING,
    vocabulary.STATUS_APPROVED,
    vocabulary.STATUS_REJECTED,
    vocabulary.STATUS_CANCELLED,
)


@dataclass(frozen=True)
class PreviewView:
    """The preview as the service hands it up — the day count, the breakdown, the three quantities.

    `available_before`/`available_after` are NOT here: they are derived (`accrued − consumed −
    reserved`, then minus `leave_days`) at the `api/` projection, mirroring `BalanceView` (DR-3,
    AD-5, AC8). `accrued` travels so the projection can derive `available_before`; `excluded_dates`
    is the `domain.ExcludedDate` type (a service may import `domain/`). `leave_days` is the domain
    count.
    """

    leave_days: int
    excluded_dates: list[ExcludedDate]
    accrued: int
    reserved: int
    consumed: int


@dataclass(frozen=True)
class SubmitView:
    """The stored Leave Request as the submission command hands it up (Story 2.6, AC3/AC8).

    A frozen snapshot of the persisted row's projectable fields — read AFTER the insert, inside
    the transaction, so `id` and `status` are the committed values and `leave_days` is the FROZEN
    `count_leave_days` figure (AD-18; no read path recomputes it). The `api/` route projects this
    by hand (it may import neither the ORM nor this dataclass — contract 2), the `balances.py`/
    preview precedent.
    """

    id: uuid.UUID
    leave_type_id: uuid.UUID
    start_date: datetime.date
    end_date: datetime.date
    leave_days: int
    status: str


@dataclass(frozen=True)
class LeaveRequestView:
    """A Leave Request as the read/transition path hands it up (Story 2.7, AC1/AC5/AC9).

    Carries the request's own fields plus the applicant's `employee_id`/`employee_name` (so a
    Manager's queue shows WHOSE request it is, AC9) and the Leave Type `code`/`name` (AC5's "with
    its Leave Type", so the queue and by-id read are human-readable without a second round-trip —
    Open Decision #2). `leave_days` is the STORED figure the row carries (AD-18) — no read or
    transition recomputes it. A transition returns this with `status` set to the NEW state; a read
    returns it with the row's current `status`. The `api/` route projects it by hand (it imports
    neither the ORM nor this dataclass — contract 2, the `SubmitView` precedent).
    """

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_type_name: str
    start_date: datetime.date
    end_date: datetime.date
    leave_days: int
    status: str


# One message per refusal, stated once at module level — the `services/balances._insufficient_
# balance` / `services/leave_types` idiom. `details` names the numbers/boundary a refusal must
# state (NFR-17), so a client can act on it rather than re-guess the request.
_INVALID_DATE_RANGE_MESSAGE = "The end date cannot be before the start date."
_PAST_DATE_RANGE_MESSAGE = "The requested range is entirely in the past."
_SPANS_TWO_LEAVE_YEARS_MESSAGE = (
    "A leave request cannot span two leave years; split it at the year boundary."
)
_ZERO_LEAVE_DAYS_MESSAGE = (
    "The requested range contains no working days, so it would cost no leave."
)
_TRANSITION_NOT_ALLOWED_MESSAGE = (
    "The request is no longer in a state that allows this action."
)


def _invalid_date_range() -> DomainError:
    """Build the `400 INVALID_DATE_RANGE` refusal — an inverted range (`end < start`)."""
    return DomainError(
        code=vocabulary.INVALID_DATE_RANGE,
        message=_INVALID_DATE_RANGE_MESSAGE,
        details={},
    )


def _past_date_range() -> DomainError:
    """Build the `400 PAST_DATE_RANGE` refusal — the range lies wholly in the past."""
    return DomainError(
        code=vocabulary.PAST_DATE_RANGE,
        message=_PAST_DATE_RANGE_MESSAGE,
        details={},
    )


def _spans_two_leave_years(boundary: datetime.date) -> DomainError:
    """Build the `400 SPANS_TWO_LEAVE_YEARS` refusal, naming the crossed boundary (NFR-17)."""
    return DomainError(
        code=vocabulary.SPANS_TWO_LEAVE_YEARS,
        message=_SPANS_TWO_LEAVE_YEARS_MESSAGE,
        details={"boundary": boundary.isoformat()},
    )


def _zero_leave_days() -> DomainError:
    """Build the `400 ZERO_LEAVE_DAYS` refusal — no Working Day in the range."""
    return DomainError(
        code=vocabulary.ZERO_LEAVE_DAYS,
        message=_ZERO_LEAVE_DAYS_MESSAGE,
        details={},
    )


def _transition_not_allowed() -> DomainError:
    """Build the `409 TRANSITION_NOT_ALLOWED` refusal — the guarded UPDATE matched zero rows (AC2).

    A state conflict names no numbers, so `details` is empty — the request simply is not in the
    state the transition required (a lost race, or a settled request). Mirrors the `_invalid_date_
    range` idiom: one `_MESSAGE` const, one factory.
    """
    return DomainError(
        code=vocabulary.TRANSITION_NOT_ALLOWED,
        message=_TRANSITION_NOT_ALLOWED_MESSAGE,
        details={},
    )


def _scope_for_role(role: str) -> Scope:
    """Resolve an actor's role to the read scope it grants (Story 2.7, AC4/AC5).

    The three-way extension of `balance_reads.py`'s two-way idiom: an Admin reads every request
    (`ALL`), a Manager their Direct Reports' (`REPORTS`), and everyone else their own (`SELF`). A
    pure function of the role string alone — no I/O — so it is unit-testable DB-free with a bare
    role value (Task 9). The scope becomes a SQL predicate downstream (AD-10); it is never a
    post-filter.
    """
    if role == authz.ROLE_ADMIN:
        return Scope.ALL
    if role == authz.ROLE_MANAGER:
        return Scope.REPORTS
    return Scope.SELF


def _row_to_view(row: Row, *, status: str | None = None) -> LeaveRequestView:  # type: ignore[type-arg]
    """Map a repository `_READ_COLUMNS` row to a `LeaveRequestView`.

    `status` overrides the row's stored status when set — a transition returns the view with the
    NEW state (the row still holds the OLD `from` state at read time), while a read passes `status=
    None` and keeps the row's current value. `leave_days` is read straight from the stored column
    (AD-18); nothing here recomputes it.
    """
    return LeaveRequestView(
        id=row.id,
        employee_id=row.employee_id,
        employee_name=row.full_name,
        leave_type_id=row.leave_type_id,
        leave_type_code=row.code,
        leave_type_name=row.name,
        start_date=row.start_date,
        end_date=row.end_date,
        leave_days=row.leave_days,
        status=row.status if status is None else status,
    )


def _current_leave_year() -> int:
    """The current Leave Year — `date.today().year` (DR-8). The clock lives in the shell (AD-1)."""
    return datetime.date.today().year


def _today() -> datetime.date:
    """Today, from the shell clock (AD-1) — the `PAST_DATE_RANGE` comparison's reference date."""
    return datetime.date.today()


def _now() -> datetime.datetime:
    """The current instant (UTC), from the shell clock (AD-1) — an audit row's `occurred_at`."""
    return datetime.datetime.now(datetime.timezone.utc)


def preview_leave_request(
    actor: Employee,
    *,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
) -> PreviewView:
    """Preview what a request would cost the caller — read-only, side-effect-free (FR-08, AD-3).

    Scope `SELF`, intrinsic to the token subject (like `GET /balances`): the caller previews
    their OWN current-year balance. In order:

      1. Open one READ session — no `commit()`, nothing is written (AD-3).
      2. Read the caller's `(accrued, reserved, consumed)` for this Leave Type, scoped to `SELF`.
         A `None` — an unknown `leave_type_id`, or no materialized balance — is a byte-identical
         `404 RESOURCE_NOT_FOUND` via `authz.not_found()` (AC10).
      3. Read the Company Holidays in `[start, end]` and build the `date → name` map.
      4. Reach `domain.calendar` for BOTH the count and the reasoned/named breakdown — the single
         day-count authority (AD-2). The client renders these; it computes nothing.

    Returns a `PreviewView`; the `api/` layer derives `available_before`/`available_after` from
    its three stored quantities (DR-3). No lock, no write, no reservation, no `INSUFFICIENT_BALANCE`
    (AC9, AC11).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        row = leave_balance_repo.get_balance(
            session,
            actor,
            employee_id=actor.id,
            leave_type_id=leave_type_id,
            leave_year=_current_leave_year(),
            scope=Scope.SELF,
        )
        if row is None:
            authz.not_found()

        holidays = holiday_repo.holidays_in_range(session, start, end)
        holiday_map = {holiday.holiday_date: holiday.name for holiday in holidays}

        leave_days = calendar.count_leave_days(start, end, holiday_map.keys())
        excluded = calendar.excluded_dates(start, end, holiday_map)

        return PreviewView(
            leave_days=leave_days,
            excluded_dates=excluded,
            accrued=row.accrued,
            reserved=row.reserved,
            consumed=row.consumed,
        )


def submit_leave_request(
    actor: Employee,
    *,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
) -> SubmitView:
    """Submit a Leave Request atomically — the first WRITE in the lifecycle (FR-08, AC3–AC5).

    Scope `self`, intrinsic to the token subject: an Employee submits their OWN request. The
    whole command is ONE write transaction (AD-3), opened and committed here — a rolled-back
    submit leaves no `leave_request` row AND no `audit_entry` row (AD-8). The sequence, in order:

      1. **Pure range validity, before the lock** (precedence fixed and tested):
         `INVALID_DATE_RANGE` (`end < start`) → `PAST_DATE_RANGE` (`end < today`) →
         `SPANS_TWO_LEAVE_YEARS` (`start.year != end.year`, naming the boundary). The predicates
         live in `domain/leave_request_rules` (pure, DB-free-testable); this service raises the
         typed `DomainError` (AD-5 — the service is the gate). `today` comes from the shell (AD-1).
      2. `leave_year = start.year` (a single-year range by step 1's guard). Read the Company
         Holidays in `[start, end]` and build the `{date: name}` map (the preview's shape).
      3. `leave_days = count_leave_days(...)` — the SOLE day-count authority (AD-2). `0` →
         `ZERO_LEAVE_DAYS`. The count is FROZEN on the row from here (AD-18).
      4. Branch on the applicant's `manager_id`:
           - **Has a manager** → `balances.reserve(...)` (locks the row `FOR UPDATE`, raises
             `INSUFFICIENT_BALANCE` from the LOCKED row before any write — AD-3/AD-5), then insert
             the request as `PENDING` and one `audit_entry` (`EMPLOYEE`/`SUBMITTED`, `NULL →
             PENDING`).
           - **`manager_id is None`** → `balances.consume_direct(...)` (FR-09 auto-approval; never
             touches `reserved`, the Available check still fires — AC5), then insert the request as
             `APPROVED` and one `audit_entry` (`SYSTEM`/`AUTO_APPROVED_NO_MANAGER`, `actor_id
             NULL`, `NULL → APPROVED`).
      5. `commit()`. Return the stored row as a frozen `SubmitView` for the route to project.

    Lock order (AD-3): the balance row is locked (inside `reserve`/`consume_direct`) BEFORE the
    request row is inserted — a single balance row here, so the ordering is trivial but observed.
    """
    # Step 1 — pure range validity, in fixed precedence, before any lock (AD-5). The predicates
    # are pure; the typed refusal is the service's.
    if rules.is_inverted_range(start, end):
        raise _invalid_date_range()
    if rules.is_wholly_past(end, _today()):
        raise _past_date_range()
    if rules.spans_two_leave_years(start, end):
        raise _spans_two_leave_years(rules.leave_year_end_boundary(start))

    leave_year = start.year  # single-year by the guard above

    with Session(get_engine(), expire_on_commit=False) as session:
        # Step 1b — the balance row MUST exist before we try to lock+mutate it. An unknown
        # `leave_type_id`, or a `leave_year` (= start.year) with no materialized row, is a CLIENT
        # error, not a programming error: `balances._lock` would raise `LookupError` → a raw 500.
        # Mirror `preview_leave_request` — a non-locking `SELF`-scoped read, `None` → a byte-
        # identical `404 RESOURCE_NOT_FOUND` via `authz.not_found()` (code review 2026-07-13).
        if (
            leave_balance_repo.get_balance(
                session,
                actor,
                employee_id=actor.id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                scope=Scope.SELF,
            )
            is None
        ):
            authz.not_found()

        # Step 2 — Company Holidays in range → the {date: name} map (the preview's shape).
        holidays = holiday_repo.holidays_in_range(session, start, end)
        holiday_map = {holiday.holiday_date: holiday.name for holiday in holidays}

        # Step 3 — the ONE day-count authority (AD-2), frozen on the row from here (AD-18).
        leave_days = calendar.count_leave_days(start, end, holiday_map.keys())
        if leave_days == 0:
            raise _zero_leave_days()

        # Step 4 — branch on the applicant's manager. `reserve`/`consume_direct` lock the balance
        # row and decide `INSUFFICIENT_BALANCE` under that lock (AD-3), BEFORE the request insert.
        if actor.manager_id is None:
            # Managerless → auto-approve directly (FR-09): consume without ever reserving. The
            # Available check still fires inside `consume_direct` (AC5).
            balances.consume_direct(
                session,
                employee_id=actor.id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                days=leave_days,
            )
            status = vocabulary.STATUS_APPROVED
            actor_type = vocabulary.ACTOR_SYSTEM
            actor_id: uuid.UUID | None = None
            reason = vocabulary.REASON_AUTO_APPROVED_NO_MANAGER
        else:
            balances.reserve(
                session,
                employee_id=actor.id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                days=leave_days,
            )
            status = vocabulary.STATUS_PENDING
            actor_type = vocabulary.ACTOR_EMPLOYEE
            actor_id = actor.id
            reason = vocabulary.REASON_SUBMITTED

        request = leave_request_repo.insert_leave_request(
            session,
            employee_id=actor.id,
            leave_type_id=leave_type_id,
            start_date=start,
            end_date=end,
            leave_days=leave_days,
            status=status,
        )

        # Exactly one audit row, in THIS transaction (AD-8). `from_state=None` — a creation has no
        # prior state. `occurred_at` from the shell clock (AD-1).
        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_LEAVE_REQUEST,
            subject_id=request.id,
            from_state=None,
            to_state=status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            occurred_at=_now(),
        )

        # Snapshot the projectable fields BEFORE commit (attributes stay readable —
        # `expire_on_commit=False`), so the route projects committed values (AD-18: `leave_days`
        # is the frozen figure, never recomputed).
        view = SubmitView(
            id=request.id,
            leave_type_id=leave_type_id,
            start_date=start,
            end_date=end,
            leave_days=leave_days,
            status=status,
        )
        session.commit()
        return view


# The AD-17 balance mutator a transition applies: `consume_reserved` (approve) or `release_reserved`
# (reject/cancel). Both share the keyword signature `(session, *, employee_id, leave_type_id,
# leave_year, days)`; typed loosely because the two are the only values ever passed.
_BalanceMutator = Callable[..., None]


def _decide(
    actor: Employee,
    request_id: uuid.UUID,
    *,
    from_status: str,
    to_status: str,
    scope: Scope,
    reason: str,
    mutate: _BalanceMutator,
    actor_type: str,
    actor_id: uuid.UUID | None,
    recompute_carry_forward: bool = False,
) -> LeaveRequestView:
    """The one transaction every transition (approve/reject/cancel) shares (AC1–AC3, AC7, AC8).

    In strict order — the lock order the 2.7 Dev Notes justify (guarded UPDATE first, balance
    second), the INVERSE of submission's balance-first order, so a lost race is a clean 409 before
    any balance is touched:

      1. Locate the request UNDER `scope` (`get_leave_request`, a plain non-locking SELECT). `None`
         ⇒ `authz.not_found()` — a nonexistent id AND an out-of-scope one (a non-report Manager, a
         non-owner Employee) are a byte-identical 404 (AD-10, AC7). Authority is bound HERE, at
         decision time, from `actor.id` (DR-12, AC8): a reassigned applicant is decided by their
         NEW Manager, and the scope predicate is `Employee.manager_id == :actor_id` evaluated now.
      2. The AD-4 guarded transition (`transition_status`): `UPDATE … WHERE status = :from`. Zero
         rows ⇒ `raise _transition_not_allowed()` (409) and the transaction rolls back — nothing
         else has been written (AC2). This runs BEFORE the balance mutation on purpose: a lost race
         is caught here, so `mutate` never runs against a reservation a competing transition already
         released (which would raise `ValueError` → a raw 500 instead of the clean 409).
      3. `mutate` the balance under its own row lock (`consume_reserved` on approve, `release_
         reserved` on reject/cancel) — `leave_year = start_date.year` (a request never spans two
         Leave Years, Story 2.6's guard). One AD-17 mutator; the transition never touches
         `leave_days` or dates.
      4. **The DR-7a carry-forward top-up, but ONLY when `recompute_carry_forward` is set** (Story
         2.10, AC6). See the note below — this is a conditional on purpose.
      5. Exactly ONE `audit_entry`, in THIS transaction (AD-8): `from_state=from_status`,
         `to_state=to_status`, naming the actor and the moment (`_now()`, the shell clock, AD-1).
         The top-up in step 4 writes NO audit row: a balance re-derivation is not a state transition,
         and SM-4's one-to-one count must stay literally true (AD-8).
      6. `commit()`. Return the located row projected to a view with the NEW `status`.

    --- Why the top-up is CONDITIONAL and not simply always-on (AC6) ---

    Of the three transitions this function serves, exactly two RAISE `available(Y)`: reject and
    cancel, both via `release_reserved`. Approve does NOT — `consume_reserved` shifts Reserved →
    Consumed and leaves Available unchanged by construction, so the derived carry-forward is already
    correct. AC6 says it outright: "approval leaves `available(Y)` unchanged, so carry-forward is
    never clawed back."

    An unconditional recompute wired in here would therefore fire on approve too. It would be a
    no-op TODAY, by arithmetic — and that is exactly the problem: it would make the no-clawback
    guarantee an accident of the numbers rather than a decision the code states. `reject_leave_
    request` and `cancel_leave_request` pass `True`; `approve_leave_request` does not, and the
    default is `False` so a future caller must opt in deliberately.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        row = leave_request_repo.get_leave_request(session, actor, request_id, scope)
        if row is None:
            authz.not_found()

        moved = leave_request_repo.transition_status(
            session,
            request_id=request_id,
            from_status=from_status,
            to_status=to_status,
        )
        if moved == 0:
            raise _transition_not_allowed()

        mutate(
            session,
            employee_id=row.employee_id,
            leave_type_id=row.leave_type_id,
            leave_year=row.start_date.year,
            days=row.leave_days,
        )

        if recompute_carry_forward:
            # DR-7a (Story 2.10, AC6): `release_reserved` just RAISED `available(Y)`, so the derived
            # `carried_forward(Y+1)` — and every materialized year above it — must be re-derived and
            # topped up. Same transaction as the release: the two are one atomic fact.
            #
            # `leave_year=row.start_date.year`, NOT `_current_leave_year()`. The wrong helper is
            # defined 250 lines up in this very module and is already in scope, and reaching for it
            # would break AC6 in AC6's own motivating scenario: a year-`Y` request rejected DURING
            # year `Y+1` would recompute forward from `Y+1` and the top-up would never fire. The
            # mutator two lines above used `row.start_date.year`; this uses the same value. A request
            # never spans two Leave Years (DR-6), so `start_date.year` IS its Leave Year.
            rollover.recompute_carry_forward(
                session,
                employee_id=row.employee_id,
                leave_type_id=row.leave_type_id,
                leave_year=row.start_date.year,
            )

        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_LEAVE_REQUEST,
            subject_id=request_id,
            from_state=from_status,
            to_state=to_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            occurred_at=_now(),
        )

        view = _row_to_view(row, status=to_status)
        session.commit()
        return view


def approve_leave_request(actor: Employee, request_id: uuid.UUID) -> LeaveRequestView:
    """Approve a Direct Report's Pending request — `PENDING → APPROVED` (AC1, FR-09).

    Scope `REPORTS`: only the applicant's current Manager decides it (the role gate has already
    refused an Admin/Employee a 403 before this runs — AC6). Moves the days `reserved → consumed`
    via `consume_reserved` (Available unchanged, the days were committed at submission). One
    EMPLOYEE/APPROVED audit row.

    It does NOT pass `recompute_carry_forward` (Story 2.10, AC6), and that omission is deliberate:
    `consume_reserved` leaves `available(Y)` unchanged, so carry-forward is already correct and must
    never be clawed back. Recomputing here would be a no-op by arithmetic today — and would make the
    no-clawback guarantee an accident of the numbers rather than something the code decides.
    """
    return _decide(
        actor,
        request_id,
        from_status=vocabulary.STATUS_PENDING,
        to_status=vocabulary.STATUS_APPROVED,
        scope=Scope.REPORTS,
        reason=vocabulary.REASON_APPROVED,
        mutate=balances.consume_reserved,
        actor_type=vocabulary.ACTOR_EMPLOYEE,
        actor_id=actor.id,
    )


def reject_leave_request(actor: Employee, request_id: uuid.UUID) -> LeaveRequestView:
    """Reject a Direct Report's Pending request — `PENDING → REJECTED` (AC1, FR-09).

    Scope `REPORTS` (role gate refuses an Admin/Employee first, AC6). Releases the reservation via
    `release_reserved` (reserved down, Available back up). One EMPLOYEE/REJECTED audit row.

    `recompute_carry_forward=True` (Story 2.10, DR-7a): the release RAISES `available(Y)`, so if the
    Leave Year boundary has already been rolled, `carried_forward(Y+1)` tops up in this same
    transaction. A year-`Y` request rejected in February is exactly the scenario DR-7a exists for.
    """
    return _decide(
        actor,
        request_id,
        from_status=vocabulary.STATUS_PENDING,
        to_status=vocabulary.STATUS_REJECTED,
        scope=Scope.REPORTS,
        reason=vocabulary.REASON_REJECTED,
        mutate=balances.release_reserved,
        actor_type=vocabulary.ACTOR_EMPLOYEE,
        actor_id=actor.id,
        recompute_carry_forward=True,
    )


def cancel_leave_request(actor: Employee, request_id: uuid.UUID) -> LeaveRequestView:
    """Cancel one's OWN Pending request — `PENDING → CANCELLED` (AC3).

    Scope `SELF` (intrinsic to the applicant — role `any`): only the owner cancels, a non-owner
    gets a byte-identical 404, and a settled request gets a 409. Releases the reservation via
    `release_reserved`. One EMPLOYEE/CANCELLED audit row naming the applicant. This is the applicant
    cancelling their own PENDING request (`release_reserved`) — NOT Story 2.8's approved-leave
    cancellation via a separate table (`release_consumed`); do not conflate them.

    `recompute_carry_forward=True` (Story 2.10, DR-7a): like reject, the release raises
    `available(Y)`, so an already-rolled `carried_forward(Y+1)` tops up in this same transaction.
    """
    return _decide(
        actor,
        request_id,
        from_status=vocabulary.STATUS_PENDING,
        to_status=vocabulary.STATUS_CANCELLED,
        scope=Scope.SELF,
        reason=vocabulary.REASON_CANCELLED,
        mutate=balances.release_reserved,
        actor_type=vocabulary.ACTOR_EMPLOYEE,
        actor_id=actor.id,
        recompute_carry_forward=True,
    )


def get_leave_request(actor: Employee, request_id: uuid.UUID) -> LeaveRequestView:
    """Return one Leave Request by id, SCOPED to the caller (AC5, AC7).

    Scope resolves from the caller's role (`_scope_for_role`: Admin `ALL`, Manager `REPORTS`, else
    `SELF`). A READ session (no commit). The request is located UNDER that scope: `None` — a
    nonexistent id OR an out-of-scope one — is a byte-identical `404 RESOURCE_NOT_FOUND` (AD-10).
    The returned view carries the STORED `leave_days` (AD-18, never recomputed) and the row's
    current `status`, plus the Leave Type and applicant labels.
    """
    scope = _scope_for_role(actor.role)
    with Session(get_engine(), expire_on_commit=False) as session:
        row = leave_request_repo.get_leave_request(session, actor, request_id, scope)
        if row is None:
            authz.not_found()
        return _row_to_view(row)


def list_leave_requests(
    actor: Employee,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[LeaveRequestView], int]:
    """Return one page of Leave Requests AND the total, SCOPED to the caller (AC4).

    Same three-way role→scope resolution as `get_leave_request`: an Employee receives their own, a
    Manager their Direct Reports', an Admin all — the scope a SQL predicate, never a post-filter
    (AD-10). `status` narrows to one state when given (the single FR-03 filter here); `limit`/
    `offset` come from the clamped `PageParams`. A READ session. Returns `(views, total)` for the
    route to assemble the `Page` envelope.
    """
    scope = _scope_for_role(actor.role)
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = leave_request_repo.list_leave_requests(
            session,
            actor,
            scope=scope,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [_row_to_view(row) for row in rows], total
