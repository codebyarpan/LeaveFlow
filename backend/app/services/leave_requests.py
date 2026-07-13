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
from dataclasses import dataclass

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
