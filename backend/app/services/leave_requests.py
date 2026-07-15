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
from pathlib import Path

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
from app.repositories import leave_type as leave_type_repo
from app.repositories import notification as notification_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import authorization as authz
from app.services import balances
from app.services import documents as documents_service
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
_SUPPORTING_DOCUMENT_REQUIRED_MESSAGE = (
    "This leave type requires a supporting document; attach one to submit."
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


def _supporting_document_required(leave_type_code: str) -> DomainError:
    """Build the `400 SUPPORTING_DOCUMENT_REQUIRED` refusal, naming the Leave Type (Story 4.1, AC4).

    Raised when a submission for a Leave Type whose `requires_supporting_document` is true
    arrives with no document part — THIS service is the one place the gate lives (FR-13).
    `details` names the code that forced it (NFR-17): the client knows WHICH type wants
    evidence, not merely that something did.
    """
    return DomainError(
        code=vocabulary.SUPPORTING_DOCUMENT_REQUIRED,
        message=_SUPPORTING_DOCUMENT_REQUIRED_MESSAGE,
        details={"leave_type_code": leave_type_code},
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


def row_to_view(row: Row, *, status: str | None = None) -> LeaveRequestView:  # type: ignore[type-arg]
    """Map a repository `_READ_COLUMNS` row to a `LeaveRequestView`.

    `status` overrides the row's stored status when set — a transition returns the view with the
    NEW state (the row still holds the OLD `from` state at read time), while a read passes `status=
    None` and keeps the row's current value. `leave_days` is read straight from the stored column
    (AD-18); nothing here recomputes it.

    PUBLIC (Story 3.3): `services/calendar.py` reuses this same mapper rather than copying it —
    the AD-18 guarantee (stored `leave_days`, never recomputed) lives in this ONE mapper reading
    `_READ_COLUMNS` verbatim, and a copy would be a second place for it to silently break.
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
    document: documents_service.UploadDocument | None = None,
) -> SubmitView:
    """Submit a Leave Request atomically — the first WRITE in the lifecycle (FR-08, AC3–AC5).

    `document` (Story 4.1, AC4/OD#1) is the multipart submission's rider — plain bytes +
    metadata (`UploadDocument`), never a framework type (contract 1). THIS function is the one
    place FR-13's gate lives: a Leave Type whose `requires_supporting_document` is true refuses
    a documentless submission with `400 SUPPORTING_DOCUMENT_REQUIRED` — decided after the pure
    range refusals and BEFORE any lock. A document that does ride along is validated, its row
    inserted and its file written INSIDE this same transaction, after the request insert
    flushes the id — one command, one commit: a refused submission (any refusal, including an
    invalid file) leaves no `leave_request` row, no document row and no file.

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

        # Step 1c — FR-13's gate, THE one place it is enforced (Story 4.1, AC4). After the pure
        # range refusals and the balance-existence 404, BEFORE any lock: a document-requiring
        # Leave Type refuses a documentless submission with a typed 400 naming the type's code.
        # The row exists — step 1b's materialized balance FK-guarantees the leave type — but the
        # `None` guard keeps this loud-safe rather than trusting the inference. An Admin who set
        # the flag true before this story shipped created a requirement that was configurable but
        # unenforced — "a deliberate act, not a latent gap" (PRD §7.3); it is enforced from here on.
        leave_type = leave_type_repo.get_leave_type(session, leave_type_id)
        if (
            leave_type is not None
            and leave_type.requires_supporting_document
            and document is None
        ):
            raise _supporting_document_required(leave_type.code)

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
            # Story 3.4 / AC4 — the managerless applicant is their OWN addressee, and the kind is
            # `REQUEST_APPROVED`, because that is what actually happened to their request. There is
            # deliberately NO `REQUEST_SUBMITTED` here: AC4 says why in as many words — "because it
            # would have no addressee." The recipient column is NOT NULL, so the naive unconditional
            # `REQUEST_SUBMITTED` insert with `recipient=actor.manager_id` would not merely be wrong,
            # it would violate the FK constraint on `None` and surface as a RAW 500 on this path.
            notify_kind = vocabulary.NOTIFICATION_REQUEST_APPROVED
            notify_recipient = actor.id
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
            # Story 3.4 / AC2 — the request is now waiting on a human, so tell that human. The
            # recipient is the applicant's MANAGER, read straight off the authenticated actor: no
            # lookup query is needed, and `actor.manager_id` is non-`None` in this branch by the
            # condition above.
            notify_kind = vocabulary.NOTIFICATION_REQUEST_SUBMITTED
            notify_recipient = actor.manager_id

        request = leave_request_repo.insert_leave_request(
            session,
            employee_id=actor.id,
            leave_type_id=leave_type_id,
            start_date=start,
            end_date=end,
            leave_days=leave_days,
            status=status,
        )

        # ---- AD-6: THE SUBMIT-SIDE CARRY-FORWARD RECOMPUTE (Story 3.4, Task 11) -----------------
        # AD-6 requires `carried_forward` be re-derived on "EVERY event that can change its inputs",
        # and its only input is `available(Y)`. Story 2.10 wired the recompute into the three sites
        # where `available(Y)` RISES (reject, self-cancel, approve-CR) and MISSED THIS ONE, the only
        # site where it FALLS. So once the rollover had run for `Y` — which it may, `run_rollover`
        # has no clock and merely WARNS when rolling an open year — a later year-`Y` submission left
        # the stored `carried_forward(Y+1)` HIGHER than `min(cap, available(Y))` now is. A leave
        # balance that is wrong and will be believed, which is PRD §1's central promise.
        #
        # Five stories deferred this (2.11 #8 → 2.12 #11 → 3.1 #6 → 3.2 #4 → 3.3 #7) and named 3.4 the
        # forcing point. It is closed HERE.
        #
        # 🚨 The call is safe ONLY because `recompute_carry_forward` is now FORWARD-CHECKED. The
        # one-line fix `deferred-work.md:67,75` prescribes — this call, without the guard — would have
        # shipped a NEW raw 500 on the most-trafficked write path in the application: submit LOWERS
        # `carried_forward(Y+1)`, hence `accrued(Y+1)`, and on a `Y+1` that is already spent that
        # drives `accrued < consumed + reserved` → `set_accrual`'s bare `ValueError` → no handler →
        # 500. The guard projects the walk purely first, and on refusal writes NO balance and raises
        # an `admin_review_flag` instead. **The submission ALWAYS commits**: refusing an Employee's
        # leave over a carry-forward artifact in a LATER year would be indefensible, and no error code
        # exists for it. The unreconcilable balance goes to an Admin, not to the applicant.
        #
        # `leave_year=start.year`, NOT `_current_leave_year()` — the wrong helper is defined ~60 lines
        # up in this module and is already in scope. A request never spans two Leave Years (DR-6), so
        # `start.year` IS its Leave Year, and it is the same value `reserve`/`consume_direct` were
        # given above. `_decide`'s standing warning is about exactly this trap.
        #
        # It runs AFTER the request insert so that a refusal flags a pair whose Reserved/Consumed
        # already include this request, and writes NO audit row (a balance re-derivation is not a
        # state transition — SM-4's exact count of 14 stays true).
        #
        # ONE instant for the whole transition (the cancellation.py principle, code review
        # 2026-07-15): the flag a refusal may raise, the audit row and the notification below all
        # record the same atomic fact, so they carry the same `occurred_at` — ordering artifacts by
        # time across tables must never interleave other transactions inside one logical event.
        occurred_at = _now()
        rollover.recompute_carry_forward(
            session,
            employee_id=actor.id,
            leave_type_id=leave_type_id,
            leave_year=start.year,
            cause=vocabulary.CAUSE_SUBMISSION_RECALCULATION,
            occurred_at=occurred_at,
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
            occurred_at=occurred_at,
        )

        # Exactly ONE Notification, in THIS SAME transaction (Story 3.4, AC2/AC4; AD-16's third
        # clause: "the service that performs a transition is the service that writes its
        # Notification, inside that transition's transaction"). So a submission that ROLLS BACK — an
        # `INSUFFICIENT_BALANCE` raised under the lock above, say — leaves NO notification claiming a
        # request was filed. One exists if and only if the submission committed.
        #
        # WHICH notification is decided in the branch above, and the two branches differ (Landmine 1):
        # a managed applicant notifies their MANAGER (`REQUEST_SUBMITTED`); a MANAGERLESS applicant
        # notifies THEMSELVES (`REQUEST_APPROVED`), and no `REQUEST_SUBMITTED` is ever written. It is
        # NOT one unconditional insert — that would violate the NOT NULL recipient FK on the
        # managerless path and fail AC4 twice over.
        #
        # This writes NO audit row (there is no `SUBJECT_NOTIFICATION` and there must not be one): a
        # Notification is a CONSEQUENCE of the transition, not a transition, so SM-4's exact count of
        # 14 audit rows stays literally true (AD-8's "and nothing else").
        notification_repo.insert_notification(
            session,
            recipient_employee_id=notify_recipient,
            leave_request_id=request.id,
            kind=notify_kind,
            created_at=occurred_at,
        )

        # Story 4.1 (AC4, OD#1/OD#4) — a document riding the submission is validated (type first,
        # then size — both refusals roll the WHOLE submission back: no request row, no document
        # row, no file), its row inserted and its file written INSIDE this transaction, after
        # `insert_leave_request` flushed the id it references. Placed LAST among the writes so the
        # orphan-file window (a crash between file write and commit — OD#4's accepted, unreachable
        # orphan) is as narrow as it can be. Writes NO audit row and NO notification of its own:
        # the document is part of THIS submission, not a second event.
        document_path: Path | None = None
        if document is not None:
            _, document_path = documents_service.store_new_document(
                session, leave_request_id=request.id, upload=document
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
        try:
            session.commit()
        except Exception:
            # OD#4: the commit failed after the file write — the rows roll back with the
            # transaction, so the file must not linger claiming a submission that never happened.
            # `unlink_quietly`: a failure here must not mask the commit error (2026-07-15 review).
            if document_path is not None:
                documents_service.unlink_quietly(document_path)
            raise
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
    notify_kind: str | None = None,
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

    --- Why the NOTIFICATION is conditional too, and for exactly the same reason (Story 3.4, AC3) ---

    🚨 THIS FUNCTION IS SHARED BY CANCEL. Of its three callers, exactly TWO notify: approve
    (`REQUEST_APPROVED`) and reject (`REQUEST_REJECTED`). **A self-cancellation notifies NOBODY** —
    no AC grants it, and the `kind` CHECK does not even admit a value for it, so an unconditional
    insert here would raise a CHECK violation as a raw 500 on the cancel path (or, worse, quietly
    write a `REQUEST_REJECTED` the applicant never earned). The complete cardinality table is in the
    story's Dev Notes; the short version is that a cancellation is the applicant acting on their own
    request, and there is no one to tell.

    So `notify_kind` is a keyword-only opt-in defaulting to `None`, deliberately mirroring
    `recompute_carry_forward` above — that parameter exists for PRECISELY this shape of problem ("a
    transition-specific side effect that must be a stated decision, not an accident of which callers
    happen to share a function"), and this is its second instance. `approve_leave_request` passes
    `NOTIFICATION_REQUEST_APPROVED`; `reject_leave_request` passes `NOTIFICATION_REQUEST_REJECTED`;
    `cancel_leave_request` PASSES NOTHING, and the `None` default means no notification.

    🚨 And the RECIPIENT is `row.employee_id` — the APPLICANT — never `actor.id`, who is the MANAGER
    doing the deciding. Getting that backwards notifies the Manager about their own decision, which
    is useless to everyone; and note that an AC5-style "I only see my own notifications" test would
    STILL PASS with the recipient inverted, because the Manager would legitimately see the (wrong)
    notification addressed to them. Only a test that asserts the recipient IS the applicant catches
    it.

    The notification rides THIS transaction (AD-16), so a 409'd transition — the guarded UPDATE
    matching zero rows at step 2 — writes none: the whole transaction rolls back. One exists if and
    only if the transition committed. It writes NO audit row (SM-4 stays at exactly 14).
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

        # ONE instant for the whole transition (the cancellation.py principle, code review
        # 2026-07-15): the flag a refused recompute may raise, the audit row and the notification
        # all record the same atomic fact and carry the same `occurred_at`.
        occurred_at = _now()

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
            #
            # `cause=CAUSE_TRANSITION_RECALCULATION` (Story 3.4, Task 11): this path RAISES
            # `available(Y)`, so the forward check can only refuse when a PRIOR refused policy change
            # left a stale cap on the pair. That used to be a raw 500 on an innocent third party's
            # reject (`deferred-work.md:74`); it is now a flag, and this reject still commits.
            rollover.recompute_carry_forward(
                session,
                employee_id=row.employee_id,
                leave_type_id=row.leave_type_id,
                leave_year=row.start_date.year,
                cause=vocabulary.CAUSE_TRANSITION_RECALCULATION,
                occurred_at=occurred_at,
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
            occurred_at=occurred_at,
        )

        if notify_kind is not None:
            # Story 3.4, AC3 — approve and reject notify the APPLICANT; cancel passes no
            # `notify_kind` and so writes nothing (see the docstring above). Same transaction as the
            # transition and the audit row: a 409'd decision rolls all three back together (AD-16).
            #
            # `row.employee_id` — the APPLICANT — and NOT `actor.id`, who is the deciding Manager.
            notification_repo.insert_notification(
                session,
                recipient_employee_id=row.employee_id,
                leave_request_id=request_id,
                kind=notify_kind,
                created_at=occurred_at,
            )

        view = row_to_view(row, status=to_status)
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

    It DOES pass `notify_kind` (Story 3.4, AC3): the applicant — `row.employee_id`, not this Manager
    — receives one `REQUEST_APPROVED` Notification, written inside this transaction.
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
        notify_kind=vocabulary.NOTIFICATION_REQUEST_APPROVED,
    )


def reject_leave_request(actor: Employee, request_id: uuid.UUID) -> LeaveRequestView:
    """Reject a Direct Report's Pending request — `PENDING → REJECTED` (AC1, FR-09).

    Scope `REPORTS` (role gate refuses an Admin/Employee first, AC6). Releases the reservation via
    `release_reserved` (reserved down, Available back up). One EMPLOYEE/REJECTED audit row.

    `recompute_carry_forward=True` (Story 2.10, DR-7a): the release RAISES `available(Y)`, so if the
    Leave Year boundary has already been rolled, `carried_forward(Y+1)` tops up in this same
    transaction. A year-`Y` request rejected in February is exactly the scenario DR-7a exists for.

    It also passes `notify_kind` (Story 3.4, AC3): the applicant — not this Manager — receives one
    `REQUEST_REJECTED` Notification, written inside this transaction.
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
        notify_kind=vocabulary.NOTIFICATION_REQUEST_REJECTED,
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

    🚨 It passes NO `notify_kind`, and that omission is a DECISION, not an oversight (Story 3.4,
    AC3). This is the applicant acting on their OWN request — there is no one to tell. FR-14's three
    kinds are exhaustive and none of them describes a cancellation; an unconditional insert inside
    the shared `_decide` would fire here and hit the `kind` CHECK as a raw 500. The `None` default is
    what makes "cancel notifies nobody" true by construction rather than by remembering.
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
        return row_to_view(row)


def list_leave_requests(
    actor: Employee,
    *,
    status: str | None,
    leave_type_id: uuid.UUID | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    limit: int,
    offset: int,
) -> tuple[list[LeaveRequestView], int]:
    """Return one page of Leave Requests AND the total, SCOPED to the caller (AC4).

    Same three-way role→scope resolution as `get_leave_request`: an Employee receives their own, a
    Manager their Direct Reports', an Admin all — the scope a SQL predicate, never a post-filter
    (AD-10). The optional filters compose as an intersection and only ever NARROW that scope
    (FR-12): `status` is Story 2.7's; `leave_type_id` and the overlap-semantics `date_from`/
    `date_to` window are Story 3.1's, forwarded verbatim to the repository. An absent filter
    applies no predicate — in particular no year default ever creeps in, so the unfiltered list is
    cross-Leave-Year by construction (FR-20). `limit`/`offset` come from the clamped `PageParams`.
    A READ session. Returns `(views, total)` for the route to assemble the `Page` envelope.
    """
    scope = _scope_for_role(actor.role)
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = leave_request_repo.list_leave_requests(
            session,
            actor,
            scope=scope,
            status=status,
            leave_type_id=leave_type_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
        return [row_to_view(row) for row in rows], total
