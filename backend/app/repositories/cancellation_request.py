"""Cancellation Request persistence: the insert, the scoped reads, the AD-4 guarded transition.

Implements (Story 2.8): AC1/AC2 (`insert_cancellation_request` persists the `PENDING` row the raise
command composed, its `uuidv7()` id assigned so the same transaction can write the audit row),
AC5/AC6/AC7 (`get_cancellation_request`/`list_cancellation_requests` — the scoped reads the Admin
decides from and the applicant tracks their filings through, joining
`cancellation_request → leave_request → employee` and applying `employee_scope_predicate` IN SQL),
and the ONE sanctioned mutation of a CR row (`transition_cancellation_status` — a single AD-4
guarded conditional `UPDATE … WHERE status = :from`). SM-6.

--- A genuinely NEW resource module (AD-13) ---

A Cancellation Request is its own table (AD-13 — not a fifth `leave_request.status`), so this is a
new repository module, NOT bolted onto `leave_request.py`: the append-only surface test
(`test_leave_request_submit.py`) pins `leave_request`'s exact surface, and the target Leave
Request's `APPROVED → CANCELLED` move reuses the EXISTING `leave_request.transition_status` — this
module adds no mutator there. The shapes below mirror `leave_request.py`'s
`insert`/`get`/`list`/`transition_status` precedents exactly.

--- The mutation surface: an INSERT and ONE guarded conditional transition; no free-form update ---

`transition_cancellation_status` is the ONLY mutation of a `cancellation_request` row — a guarded
conditional `UPDATE` that matches a row only in the required `from` state (a lost race matches zero
rows → a clean 409). There is no free-form `update_`/`delete_`. The scoped reads (`get_`/`list_`)
take the `actor` (`test_scoped_getters.py`): a Cancellation Request belongs — through its target
Leave Request — to an Employee, so a read that could return another Employee's filing scopes in SQL.
"""

import uuid

from sqlalchemy import Row, func, select, update
from sqlalchemy.orm import Session

from app.repositories.models import (
    CancellationRequest,
    Employee,
    LeaveRequest,
    LeaveType,
)
from app.repositories.scoping import Scope, employee_scope_predicate


def insert_cancellation_request(
    session: Session,
    *,
    leave_request_id: uuid.UUID,
    status: str,
) -> CancellationRequest:
    """Insert a Cancellation Request row and return it, with its server-default id assigned (AC2).

    `flush` assigns the `uuidv7()` `id` so the raise command can write the matching `audit_entry`
    (`subject_id = <this id>`) in the SAME transaction (AD-8) and the route can project it. It does
    NOT commit — the service owns the one transaction (AD-3). `status` is the `vocabulary.STATUS_*`
    constant the caller chose (`PENDING` at filing). A write governed by the command's transaction,
    not a scoped getter — mirroring `insert_leave_request`.
    """
    request = CancellationRequest(
        leave_request_id=leave_request_id,
        status=status,
    )
    session.add(request)
    session.flush()
    return request


def pending_exists_for_leave_request(
    session: Session,
    *,
    leave_request_id: uuid.UUID,
    pending_status: str,
) -> bool:
    """True if an unresolved (`PENDING`) Cancellation Request already exists for this Leave Request.

    The raise command's concurrent-duplicate guard (code review 2026-07-13, D2). The table has NO
    `UNIQUE (leave_request_id)` — ERD §3 permits MULTIPLE Cancellation Requests over time (a
    `REJECTED` one may be followed by another), so sequential re-raises stay allowed — but two
    SIMULTANEOUS `PENDING` rows are not: they would duplicate the Admin queue and leave the loser
    pointing at already-cancelled leave. A CR targets exactly one Leave Request (FK), which the raise
    has already located under `Scope.SELF`, so any `PENDING` CR on that LR is the applicant's own —
    no actor scoping is needed here. `pending_status` is the `vocabulary.STATUS_*` constant the
    command passes (AD-21), never a bare literal. The service refuses `409 TRANSITION_NOT_ALLOWED`
    on `True`.
    """
    return (
        session.scalar(
            select(CancellationRequest.id)
            .where(
                CancellationRequest.leave_request_id == leave_request_id,
                CancellationRequest.status == pending_status,
            )
            .limit(1)
        )
        is not None
    )


# The projected columns every scoped read returns — the Cancellation Request's own `id`/`status`,
# its target `leave_request_id`, and the fields the decision + the Admin screen need off the TARGET
# Leave Request: the applicant (`employee_id` + `full_name`), the Leave Type (`code`/`name`), the
# range, the frozen `leave_days`, and the LR's OWN `status` (to guard `release_consumed` and to make
# a race where the LR already left `APPROVED` a clean 409). The two `status` columns are labelled
# distinctly so a `Row` exposes both unambiguously. Plain columns (not the ORM entity) travel out,
# so nothing is detached after the read session closes.
_READ_COLUMNS = (
    CancellationRequest.id,
    CancellationRequest.leave_request_id,
    CancellationRequest.status.label("cancellation_status"),
    LeaveRequest.employee_id,
    Employee.full_name,
    LeaveRequest.leave_type_id,
    LeaveType.code,
    LeaveType.name,
    LeaveRequest.start_date,
    LeaveRequest.end_date,
    LeaveRequest.leave_days,
    LeaveRequest.status.label("leave_request_status"),
)


def get_cancellation_request(
    session: Session,
    actor: Employee,
    cancellation_request_id: uuid.UUID,
    scope: Scope,
) -> Row | None:  # type: ignore[type-arg]
    """Return one Cancellation Request by id, SCOPED to `actor`, or `None` (AC6, AC7).

    The exact shape of `leave_request.get_leave_request`: join
    `cancellation_request → leave_request → employee` (and `leave_type` for the labels) and apply
    `employee_scope_predicate(scope, actor)` in the `WHERE` alongside
    `CancellationRequest.id == cancellation_request_id`. `None` for a nonexistent id OR an
    out-of-scope one — the service turns both into a byte-identical `404` (AD-10). A `get_` getter
    taking a `session`, so `test_scoped_getters.py` requires the `actor`, which it takes.

    A plain non-locking `SELECT` — the AD-4 guarded `UPDATE`s lock the CR and LR rows themselves,
    and the decision performs those UPDATEs BEFORE the balance mutation (the lock-order note). This
    read only authorizes. Returns the `_READ_COLUMNS` projection, so the decision reads
    `employee_id`/`leave_type_id`/`leave_days`/`start_date` and the LR's status off it.
    """
    return session.execute(
        select(*_READ_COLUMNS)
        .join(LeaveRequest, CancellationRequest.leave_request_id == LeaveRequest.id)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(
            CancellationRequest.id == cancellation_request_id,
            employee_scope_predicate(scope, actor),
        )
    ).first()


def list_cancellation_requests(
    session: Session,
    actor: Employee,
    *,
    scope: Scope,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of Cancellation Requests AND the full count, SCOPED to `actor` (AC5).

    Joins `cancellation_request → leave_request → employee` and applies
    `employee_scope_predicate(scope, actor)` in the `WHERE`, so an out-of-scope filing is never
    retrieved — the scope is a SQL predicate, never a Python-side filter (AD-10, NFR-04). `scope`
    is resolved by the caller from the actor's role (two-way: Admin `ALL`, else `SELF`). The
    `status` filter is applied ONLY when `status is not None` — the single filter §4.6 grants here.

    Ordered by `CancellationRequest.id.desc()`: the primary key is UUIDv7 (time-ordered), so
    descending id is newest-first — the order the Admin queue and an applicant's list both want,
    with no `created_at` column to sort on (ERD §2.1). `total` recomputes the same predicate +
    status filter (the LeaveType join is unneeded for a count, so it is omitted). Returns
    `(_READ_COLUMNS rows, total)`, the `list_leave_requests` shape, taking the `actor`.
    """
    predicate = employee_scope_predicate(scope, actor)
    conditions = [predicate]
    if status is not None:
        conditions.append(CancellationRequest.status == status)

    rows = list(
        session.execute(
            select(*_READ_COLUMNS)
            .join(
                LeaveRequest, CancellationRequest.leave_request_id == LeaveRequest.id
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
            .where(*conditions)
            .order_by(CancellationRequest.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = (
        session.scalar(
            select(func.count())
            .select_from(CancellationRequest)
            .join(
                LeaveRequest, CancellationRequest.leave_request_id == LeaveRequest.id
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*conditions)
        )
        or 0
    )
    return rows, total


def transition_cancellation_status(
    session: Session,
    *,
    cancellation_request_id: uuid.UUID,
    from_status: str,
    to_status: str,
) -> int:
    """The AD-4 guarded conditional transition — `UPDATE … WHERE id = :id AND status = :from`.

    The ONE sanctioned mutation of a `cancellation_request` row (there is no free-form
    update/delete). It matches the row only while it is still in `from_status`, so a lost race — a
    concurrent decision that already moved the row — matches ZERO rows. Returns `result.rowcount`:
    `1` on a clean transition, `0` when the guard failed. The service raises `409
    TRANSITION_NOT_ALLOWED` on a `0` and lets the whole transaction roll back (the guarded UPDATE
    runs BEFORE the balance mutation, the lock-order note). `:from`/`:to` are `vocabulary.STATUS_*`
    constants the command passes (AD-21), never bare literals. Exactly the shape of
    `leave_request.transition_status`.
    """
    result = session.execute(
        update(CancellationRequest)
        .where(
            CancellationRequest.id == cancellation_request_id,
            CancellationRequest.status == from_status,
        )
        .values(status=to_status)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount
