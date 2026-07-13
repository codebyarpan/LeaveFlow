"""Cancellation Request orchestration — raise (applicant) and decide (Admin) (Story 2.8).

Implements: FR-09 (the approved-leave cancellation half of the lifecycle), BR-05 (an approved
Cancellation Request returns the target Leave Request's `consumed` days via `release_consumed`),
AD-13 (a Cancellation Request is its own entity, never a fifth Leave Request status), AD-4 (both the
CR transition and the target LR's `APPROVED → CANCELLED` move are guarded conditional UPDATEs),
AD-8 (one `audit_entry` per transition, same transaction, discriminated by `subject_type`), AD-10
(scope is a SQL predicate; absence is a byte-identical 404; a role denial is the route's 403),
AD-17 (approve reuses the EXISTING `release_consumed` — no ninth balance method), AD-18 (the
`leave_days` used is the STORED, frozen figure). SM-6.

The spine's capability map names this module explicitly (`services/cancellation`, distinct from
`services/leave_request`): the approved-leave cancellation is a SEPARATE object and flow from Story
2.7's `POST /leave-requests/<id>/cancel` (that cancels a PENDING request via `release_reserved`, one
guarded UPDATE on the LR itself). Do NOT conflate them.

--- The two flows, side by side (do NOT conflate) ---

  2.7 cancel : target PENDING · applicant (scope self) · release_reserved · one guarded UPDATE on LR
  2.8 (here) : target APPROVED · applicant RAISES (scope self), an ADMIN decides (scope all) ·
               release_consumed on approve · a SEPARATE cancellation_request row

--- The lock order (guarded UPDATEs BEFORE the balance move) ---

Approve is ONE transaction in strict order: locate the CR (plain SELECT) → guarded UPDATE the CR
`PENDING→APPROVED` → guarded UPDATE the LR `APPROVED→CANCELLED` → `release_consumed` → two audit
rows → commit. The guarded UPDATEs run BEFORE `release_consumed` on purpose: a race where the LR
already left `APPROVED` (a second CR approved first) is then a clean `409`, not a `release_consumed`
`ValueError` → a raw 500. A `0` rowcount on either guard rolls the whole transaction back — no
balance moves, no audit row lands.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import leave_request_rules as rules
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import audit_entry as audit_entry_repo
from app.repositories import cancellation_request as cancellation_request_repo
from app.repositories import leave_request as leave_request_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import authorization as authz
from app.services import balances

# The three Cancellation Request status values, re-exported for the `api/` status filter (AC5). The
# route cannot import `domain/` (contract 2) or type the literal (`test_vocabulary_literals.py`), so
# it reads the allowed filter values through this `api → services` edge — the same indirection the
# leave-status filter uses — and builds its query-param enum from them at runtime. They REUSE the
# shared `STATUS_*` constants (Open Decision #1): a CR's lifecycle is `PENDING/APPROVED/REJECTED`,
# the same strings a Leave Request uses, discriminated by `subject_type`, never re-declared.
CANCELLATION_STATUS_VALUES: tuple[str, ...] = (
    vocabulary.STATUS_PENDING,
    vocabulary.STATUS_APPROVED,
    vocabulary.STATUS_REJECTED,
)


@dataclass(frozen=True)
class CancellationRequestView:
    """A Cancellation Request as the service hands it up (AC5/AC6/AC7/AC10).

    Carries the CR's own `id`/`leave_request_id`/`status`, plus the applicant
    (`employee_id`/`employee_name`) and the target Leave Request summary
    (`start_date`/`end_date`/`leave_days`/`leave_type_code`/`leave_type_name`) — so the Admin screen
    renders "whose request, which leave, its dates" (AC10) without a second round-trip (Open
    Decision #5). `leave_days` is the STORED figure (AD-18) — nothing recomputes it. A decision
    returns this with `status` set to the NEW state. The `api/` route projects it by hand (it
    imports neither the ORM nor this dataclass — contract 2, the `LeaveRequestView` precedent).
    """

    id: uuid.UUID
    leave_request_id: uuid.UUID
    status: str
    employee_id: uuid.UUID
    employee_name: str
    start_date: datetime.date
    end_date: datetime.date
    leave_days: int
    leave_type_code: str
    leave_type_name: str


# One message per refusal, stated once at module level — the `services/leave_requests.py` idiom.
_LEAVE_ALREADY_TAKEN_MESSAGE = (
    "The leave has already been taken and can no longer be cancelled."
)
_TRANSITION_NOT_ALLOWED_MESSAGE = (
    "The request is no longer in a state that allows this action."
)


def _leave_already_taken() -> DomainError:
    """Build the `400 LEAVE_ALREADY_TAKEN` refusal — a CR raised against past-dated leave (AC3).

    A past-date refusal names no numbers, so `details` is empty — the leave simply has already been
    taken. Mirrors `leave_requests._past_date_range`: one `_MESSAGE` const, one factory.
    """
    return DomainError(
        code=vocabulary.LEAVE_ALREADY_TAKEN,
        message=_LEAVE_ALREADY_TAKEN_MESSAGE,
        details={},
    )


def _transition_not_allowed() -> DomainError:
    """Build the `409 TRANSITION_NOT_ALLOWED` refusal — a guarded UPDATE matched zero rows.

    Raised when the CR is not `PENDING` (a second decision), when the raise target is not
    `APPROVED` (Open Decision #2), or when the target LR already left `APPROVED` under an
    approve (a lost race). A state conflict names no numbers, so `details` is empty. Mirrors
    `leave_requests._transition_not_allowed` (the same code, message and shape).
    """
    return DomainError(
        code=vocabulary.TRANSITION_NOT_ALLOWED,
        message=_TRANSITION_NOT_ALLOWED_MESSAGE,
        details={},
    )


def _scope_for_role(role: str) -> Scope:
    """Resolve an actor's role to the read scope `GET /cancellation-requests` grants (AC5).

    A TWO-WAY resolver — `ALL` for an Admin, else `SELF` — NOT the three-way `leave_requests.
    _scope_for_role`: api-contracts §4.6 grants this endpoint scope `self, all` only. A Manager is
    NOT `REPORTS` here; they see their OWN filings as an applicant (`SELF`). A pure function of the
    role string alone — no I/O — so it is unit-testable DB-free with a bare role value (Task 10).
    The scope becomes a SQL predicate downstream (AD-10); it is never a post-filter.
    """
    if role == authz.ROLE_ADMIN:
        return Scope.ALL
    return Scope.SELF


def _now() -> datetime.datetime:
    """The current instant (UTC), from the shell clock (AD-1) — an audit row's `occurred_at`."""
    return datetime.datetime.now(datetime.timezone.utc)


def _today() -> datetime.date:
    """Today, from the shell clock (AD-1) — the `LEAVE_ALREADY_TAKEN` comparison's reference date."""
    return datetime.date.today()


def _row_to_view(row, *, status: str | None = None) -> CancellationRequestView:  # type: ignore[no-untyped-def]
    """Map a `cancellation_request` scoped-read row to a `CancellationRequestView`.

    `status` overrides the row's stored CR status when set — a decision returns the view with the
    NEW state (the row still holds the OLD `from` state at read time), while a read passes
    `status=None` and keeps `row.cancellation_status`. `leave_days` is read straight from the stored
    column (AD-18); nothing here recomputes it.
    """
    return CancellationRequestView(
        id=row.id,
        leave_request_id=row.leave_request_id,
        status=row.cancellation_status if status is None else status,
        employee_id=row.employee_id,
        employee_name=row.full_name,
        start_date=row.start_date,
        end_date=row.end_date,
        leave_days=row.leave_days,
        leave_type_code=row.code,
        leave_type_name=row.name,
    )


def raise_cancellation_request(
    actor: Employee, request_id: uuid.UUID
) -> CancellationRequestView:
    """Raise a Cancellation Request against one's OWN future-dated Approved request (AC2–AC4).

    Scope `SELF`, intrinsic to the applicant (role `any`). ONE write transaction, in order:

      1. Locate the target Leave Request UNDER `Scope.SELF` (`get_leave_request`). `None` ⇒
         `authz.not_found()` — a non-owner's target is out of scope, a byte-identical 404 (AC2).
      2. The located request must be `APPROVED` — a non-`APPROVED` target is refused `409
         TRANSITION_NOT_ALLOWED` (Open Decision #2; a Pending request is cancelled via 2.7's
         `/cancel`, not here).
      3. `LEAVE_ALREADY_TAKEN` (400) if the request's dates lie wholly in the past
         (`rules.is_wholly_past(end_date, today)` — the same predicate `PAST_DATE_RANGE` uses; AC3).
      4. Insert the Cancellation Request as `PENDING`.
      5. One `audit_entry` for the raise (`subject=CANCELLATION_REQUEST`, `NULL → PENDING`, reason
         `CANCELLATION_REQUESTED`) — Open Decision #3, Option A: every transition writes one audit
         row. The Leave Request is NOT transitioned and its balance is NOT touched (AC4).
      6. `commit()`; return the created CR as a frozen view.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        target = leave_request_repo.get_leave_request(
            session, actor, request_id, Scope.SELF
        )
        if target is None:
            authz.not_found()

        # Only an APPROVED request is cancellable through this path (Open Decision #2).
        if target.status != vocabulary.STATUS_APPROVED:
            raise _transition_not_allowed()

        # The leave must not already be in the past (AC3) — the same end<today test as submission.
        if rules.is_wholly_past(target.end_date, _today()):
            raise _leave_already_taken()

        # No SECOND concurrent PENDING Cancellation Request for this Leave Request (code review D2).
        # The table drops UNIQUE(leave_request_id) so a REJECTED filing may be followed by another,
        # but two simultaneous PENDING rows would duplicate the Admin queue and orphan the loser
        # against already-cancelled leave. Sequential re-raise after a decision stays allowed.
        if cancellation_request_repo.pending_exists_for_leave_request(
            session,
            leave_request_id=request_id,
            pending_status=vocabulary.STATUS_PENDING,
        ):
            raise _transition_not_allowed()

        cancellation = cancellation_request_repo.insert_cancellation_request(
            session,
            leave_request_id=request_id,
            status=vocabulary.STATUS_PENDING,
        )

        # One audit row for the raise (Option A) — the LR is untouched (AC4).
        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_CANCELLATION_REQUEST,
            subject_id=cancellation.id,
            from_state=None,
            to_state=vocabulary.STATUS_PENDING,
            actor_type=vocabulary.ACTOR_EMPLOYEE,
            actor_id=actor.id,
            reason=vocabulary.REASON_CANCELLATION_REQUESTED,
            occurred_at=_now(),
        )

        view = CancellationRequestView(
            id=cancellation.id,
            leave_request_id=request_id,
            status=vocabulary.STATUS_PENDING,
            employee_id=target.employee_id,
            employee_name=target.full_name,
            start_date=target.start_date,
            end_date=target.end_date,
            leave_days=target.leave_days,
            leave_type_code=target.code,
            leave_type_name=target.name,
        )
        session.commit()
        return view


def approve_cancellation_request(
    actor: Employee, cancellation_request_id: uuid.UUID
) -> CancellationRequestView:
    """Approve a Cancellation Request — cancel the leave and return its days (AC6, AC9).

    Scope `ALL`, role Admin (the route's `require_role(ADMIN)` gate has already refused a non-Admin
    with 403 — AC8). ONE write transaction in the strict lock order (guarded UPDATEs, then balance):

      1. Locate the CR UNDER `Scope.ALL`. `None` ⇒ `authz.not_found()` (404).
      2. Guarded transition of the CR `PENDING → APPROVED` → `0` ⇒ `_transition_not_allowed()` (409)
         and roll back.
      3. Guarded transition of the TARGET Leave Request `APPROVED → CANCELLED` → `0` ⇒ 409 and roll
         back (a race where the LR already left `APPROVED` — e.g. a second CR approved first — is a
         clean 409, not a `release_consumed` `ValueError` → 500).
      4. `balances.release_consumed(...)` — the AD-17 approved-cancellation path (BR-05), restoring
         Available. `leave_year = start_date.year` (a request never spans two Leave Years).
      5. TWO `audit_entry` rows (AC9): the CR `PENDING → APPROVED` (`subject=CANCELLATION_REQUEST`,
         reason `APPROVED`) and the LR `APPROVED → CANCELLED` (`subject=LEAVE_REQUEST`, reason
         `CANCELLED`); both `actor_type=EMPLOYEE`, `actor_id=<admin>`, same `occurred_at`.
      6. `commit()`; return the updated CR view (status `APPROVED`).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        row = cancellation_request_repo.get_cancellation_request(
            session, actor, cancellation_request_id, Scope.ALL
        )
        if row is None:
            authz.not_found()

        # AC3 re-checked at DECISION time (code review D1): a CR raised while the leave was future can
        # sit PENDING until the dates fully pass; approving it then would `release_consumed` days that
        # were actually taken. The raise-time `LEAVE_ALREADY_TAKEN` guard is not enough on its own —
        # enforce the same `end<today` test here so leave "already taken" cannot be un-taken on either
        # path. Reject is exempt (it refunds nothing and leaves the LR untouched — AC7).
        if rules.is_wholly_past(row.end_date, _today()):
            raise _leave_already_taken()

        moved_cr = cancellation_request_repo.transition_cancellation_status(
            session,
            cancellation_request_id=cancellation_request_id,
            from_status=vocabulary.STATUS_PENDING,
            to_status=vocabulary.STATUS_APPROVED,
        )
        if moved_cr == 0:
            raise _transition_not_allowed()

        moved_lr = leave_request_repo.transition_status(
            session,
            request_id=row.leave_request_id,
            from_status=vocabulary.STATUS_APPROVED,
            to_status=vocabulary.STATUS_CANCELLED,
        )
        if moved_lr == 0:
            raise _transition_not_allowed()

        balances.release_consumed(
            session,
            employee_id=row.employee_id,
            leave_type_id=row.leave_type_id,
            leave_year=row.start_date.year,
            days=row.leave_days,
        )

        # Two audit rows, both in THIS transaction, discriminated by subject_type (AC9).
        occurred_at = _now()
        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_CANCELLATION_REQUEST,
            subject_id=cancellation_request_id,
            from_state=vocabulary.STATUS_PENDING,
            to_state=vocabulary.STATUS_APPROVED,
            actor_type=vocabulary.ACTOR_EMPLOYEE,
            actor_id=actor.id,
            reason=vocabulary.REASON_APPROVED,
            occurred_at=occurred_at,
        )
        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_LEAVE_REQUEST,
            subject_id=row.leave_request_id,
            from_state=vocabulary.STATUS_APPROVED,
            to_state=vocabulary.STATUS_CANCELLED,
            actor_type=vocabulary.ACTOR_EMPLOYEE,
            actor_id=actor.id,
            reason=vocabulary.REASON_CANCELLED,
            occurred_at=occurred_at,
        )

        view = _row_to_view(row, status=vocabulary.STATUS_APPROVED)
        session.commit()
        return view


def reject_cancellation_request(
    actor: Employee, cancellation_request_id: uuid.UUID
) -> CancellationRequestView:
    """Reject a Cancellation Request — the leave is untouched (AC7, AC9).

    Scope `ALL`, role Admin (the route's gate refuses a non-Admin first, AC8). ONE write transaction:

      1. Locate the CR UNDER `Scope.ALL`. `None` ⇒ `authz.not_found()` (404).
      2. Guarded transition of the CR `PENDING → REJECTED` → `0` ⇒ `_transition_not_allowed()` (409).
      3. ONE `audit_entry` (the CR `PENDING → REJECTED`, reason `REJECTED`). The Leave Request is
         NOT transitioned and its balance is NOT touched (AC7).
      4. `commit()`; return the updated CR view (status `REJECTED`).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        row = cancellation_request_repo.get_cancellation_request(
            session, actor, cancellation_request_id, Scope.ALL
        )
        if row is None:
            authz.not_found()

        moved_cr = cancellation_request_repo.transition_cancellation_status(
            session,
            cancellation_request_id=cancellation_request_id,
            from_status=vocabulary.STATUS_PENDING,
            to_status=vocabulary.STATUS_REJECTED,
        )
        if moved_cr == 0:
            raise _transition_not_allowed()

        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_CANCELLATION_REQUEST,
            subject_id=cancellation_request_id,
            from_state=vocabulary.STATUS_PENDING,
            to_state=vocabulary.STATUS_REJECTED,
            actor_type=vocabulary.ACTOR_EMPLOYEE,
            actor_id=actor.id,
            reason=vocabulary.REASON_REJECTED,
            occurred_at=_now(),
        )

        view = _row_to_view(row, status=vocabulary.STATUS_REJECTED)
        session.commit()
        return view


def list_cancellation_requests(
    actor: Employee,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[CancellationRequestView], int]:
    """Return one page of Cancellation Requests AND the total, SCOPED to the caller (AC5).

    Two-way role→scope resolution (`_scope_for_role`: Admin `ALL`, else `SELF`) — an Admin receives
    every Cancellation Request, everyone else only their own, the scope a SQL predicate, never a
    post-filter (AD-10). `status` narrows to one state when given (the single filter §4.6 grants);
    `limit`/`offset` come from the clamped `PageParams`. A READ session (no commit). Returns
    `(views, total)` for the route to assemble the `Page` envelope.
    """
    scope = _scope_for_role(actor.role)
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = cancellation_request_repo.list_cancellation_requests(
            session,
            actor,
            scope=scope,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [_row_to_view(row) for row in rows], total
