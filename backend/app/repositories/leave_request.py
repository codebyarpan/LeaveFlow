"""Leave Request persistence: the create, the pending count, the scoped reads, the AD-4 transition.

Implements: AC3/AC5 (`insert_leave_request` persists the row the submission command composed under
the balance lock — the `PENDING` managed path or the `APPROVED` managerless auto-approval; Story
2.6), the deactivation guard input (`count_pending_for_employee`, Story 1.6 made executable in 2.6),
and Story 2.7's transition half: `get_leave_request`/`list_leave_requests` (the FR-03-scoped reads a
Manager decides from) and `transition_status` (the single sanctioned AD-4 guarded conditional
UPDATE). SM-6.

--- The mutation surface: an INSERT and ONE guarded conditional transition; no free-form update ---

Through Story 2.6 this module exposed only an INSERT and a COUNT. Story 2.7 adds the lifecycle
transitions (approve/reject/cancel) as `transition_status` — a single `UPDATE … SET status = :to
WHERE id = :id AND status = :from` (AD-4). That is the ONLY mutation of a `leave_request` row this
module offers: there is no free-form `update_leave_request`/`delete_leave_request`. A transition is
guarded (it matches a row only in the required `from` state) and conditional (a lost race matches
zero rows → a clean 409, not a silent overwrite). The `audit_entry` table stays STRICTLY
append-only — INSERT only, forever (AD-8) — a distinction Story 2.7's revision of the 2.6 surface
test pins down.

--- Why `count_pending_for_employee` is named `count_`, not `get_`/`list_` ---

`tests/test_scoped_getters.py` reflects over every `get_`/`list_`/`find_`/`fetch_` function taking
a `session`, requiring the AD-10 `actor` parameter. `count_pending_for_employee` is named `count_`,
returns an `int`, and takes the target `employee_id` the deactivation guard already holds — so it is
correctly NOT a scoped-getter candidate (mirroring `count_active_direct_reports`). `get_leave_request`
and `list_leave_requests`, by contrast, ARE scoped getters: a Leave Request belongs to an Employee,
so each takes the `actor` and applies `employee_scope_predicate` in SQL (the `leave_balance` reads'
precedent). `transition_status` is a write governed by the command's transaction, not a getter.
"""

import datetime
import uuid

from sqlalchemy import Row, func, select, update
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.repositories.models import Employee, LeaveRequest, LeaveType
from app.repositories.scoping import Scope, employee_scope_predicate


def insert_leave_request(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start_date: datetime.date,
    end_date: datetime.date,
    leave_days: int,
    status: str,
) -> LeaveRequest:
    """Insert a Leave Request row and return it, with its server-default id assigned (AC3, AC5).

    `flush` assigns the `uuidv7()` `id` so the submission command can write the matching
    `audit_entry` (`subject_id = <this id>`) in the SAME transaction (AD-8) and the route can
    project it. It does NOT commit — the service owns the one transaction (AD-3). `status` is a
    `vocabulary.STATUS_*` constant the caller chose (`PENDING` for a managed applicant, `APPROVED`
    for the managerless auto-approval); `leave_days` is the frozen `count_leave_days` figure
    (AD-18).

    A write, governed by the command's transaction rather than the scope contract, so it is not a
    scoped-getter candidate — mirroring `create_holiday`/`create_leave_type`.
    """
    request = LeaveRequest(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        start_date=start_date,
        end_date=end_date,
        leave_days=leave_days,
        status=status,
    )
    session.add(request)
    session.flush()
    return request


def count_pending_for_employee(session: Session, employee_id: uuid.UUID) -> int:
    """Count the Employee's `PENDING` Leave Requests — the deactivation guard's input (AC7).

    The executable form of Story 1.6's withheld `EMPLOYEE_HAS_PENDING_REQUESTS` guard: an Employee
    holding a Pending request cannot be deactivated (AD-22), because there would be no possible
    approver for a request already reserving days. Only `PENDING` counts — an `APPROVED`/`REJECTED`
    /`CANCELLED` request is settled and does not block deactivation.

    Named `count_`, returning an `int`, so it is correctly not a scoped-getter candidate (mirrors
    `count_active_direct_reports`): the caller is the deactivation service, which already holds the
    authorized target `employee_id` and needs no per-row scoping.
    """
    return (
        session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == vocabulary.STATUS_PENDING,
            )
        )
        or 0
    )


# The projected columns every scoped read returns — the request's own fields plus the applicant's
# name and the Leave Type's code/name (Open Decision #2). One join to `employee` serves BOTH the
# scope predicate AND the applicant name; one join to `leave_type` carries the human-readable
# labels, so the Manager queue and the by-id read need no second round-trip. Plain columns (not the
# ORM entity) travel out, so nothing is a detached instance after the read session closes.
_READ_COLUMNS = (
    LeaveRequest.id,
    LeaveRequest.employee_id,
    Employee.full_name,
    LeaveRequest.leave_type_id,
    LeaveType.code,
    LeaveType.name,
    LeaveRequest.start_date,
    LeaveRequest.end_date,
    LeaveRequest.leave_days,
    LeaveRequest.status,
)


def get_leave_request(
    session: Session,
    actor: Employee,
    request_id: uuid.UUID,
    scope: Scope,
) -> Row | None:  # type: ignore[type-arg]
    """Return one Leave Request by id, SCOPED to `actor`, or `None` (AC5, AC7).

    The exact shape of `employee.get_employee` / `leave_balance.get_balance`: join
    `leave_request → employee` and apply `employee_scope_predicate(scope, actor)` in the `WHERE`
    alongside `LeaveRequest.id == request_id`. `None` for a nonexistent id OR an out-of-scope one
    (a non-report Manager, a non-owner Employee) — the service turns both into a byte-identical
    `404` (AD-10). A `get_` getter taking a `session`, so `test_scoped_getters.py` requires the
    `actor`, which it takes.

    A plain non-locking `SELECT` — NOT `with_for_update()`. The AD-4 guarded `UPDATE`
    (`transition_status`) locks the request row itself, and the transition performs that UPDATE
    BEFORE any balance mutation (the lock-order note in the 2.7 Dev Notes); locking here would add
    a redundant lock a lost race would then have to queue behind twice. This read only authorizes.
    Returns the `_READ_COLUMNS` projection — the request's own fields plus the applicant name and
    Leave Type code/name — so the transition commands read `employee_id`/`leave_type_id`/
    `leave_days`/`start_date` off it and the by-id read projects the full view.
    """
    return session.execute(
        select(*_READ_COLUMNS)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(
            LeaveRequest.id == request_id,
            employee_scope_predicate(scope, actor),
        )
    ).first()


def list_leave_requests(
    session: Session,
    actor: Employee,
    *,
    scope: Scope,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of Leave Requests AND the full count, SCOPED to `actor` (AC4).

    Joins `leave_request → employee` and applies `employee_scope_predicate(scope, actor)` in the
    `WHERE`, so an out-of-scope request is never retrieved — the scope is a SQL predicate, never a
    Python-side filter (AD-10, NFR-04). `scope` is resolved by the caller from the actor's role
    (`SELF`/`REPORTS`/`ALL`). The `status` filter is applied ONLY when `status is not None` — the
    single filter FR-03 grants here (`leave_type_id`/`date_from`/`date_to` are Story 3.1's). The
    page and total travel together (the `list_employees` shape) so the service assembles the whole
    `Page` envelope from one repository round-trip.

    Ordered by `LeaveRequest.id.desc()`: the primary key is UUIDv7, which is time-ordered by
    construction, so descending id is newest-first — the order a Manager's queue and an Employee's
    history both want, with no `created_at` column to sort on (ERD §4.5). `total` recomputes the
    same predicate + status filter (the LeaveType join is unneeded for a count, so it is omitted).
    Returns `(_READ_COLUMNS` rows, total)`, a `get_`/`list_` getter taking the `actor`.
    """
    predicate = employee_scope_predicate(scope, actor)
    conditions = [predicate]
    if status is not None:
        conditions.append(LeaveRequest.status == status)

    rows = list(
        session.execute(
            select(*_READ_COLUMNS)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
            .where(*conditions)
            .order_by(LeaveRequest.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = (
        session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*conditions)
        )
        or 0
    )
    return rows, total


def transition_status(
    session: Session,
    *,
    request_id: uuid.UUID,
    from_status: str,
    to_status: str,
) -> int:
    """The AD-4 guarded conditional transition — `UPDATE … WHERE id = :id AND status = :from`.

    The ONE sanctioned mutation of a `leave_request` row (there is no free-form update/delete). It
    matches the row only while it is still in `from_status`, so a lost race — a concurrent
    transition that already moved the row — matches ZERO rows. Returns `result.rowcount`: `1` on a
    clean transition, `0` when the guard failed. The service raises `409 TRANSITION_NOT_ALLOWED` on
    a `0` and lets the whole transaction roll back (nothing else has been written — the guarded
    UPDATE runs BEFORE the balance mutation, the 2.7 lock-order note). `:from`/`:to` are
    `vocabulary.STATUS_*` constants the command passes (AD-21), never bare literals.

    `synchronize_session=False`: the command does not reuse a stale ORM object's `status` after the
    UPDATE — it holds the row locked by the UPDATE itself and proceeds to the balance mutation — so
    no identity-map synchronization is needed. A write governed by the command's transaction, not a
    scoped getter; `flush` is implicit in `execute`, and the service owns the `commit`.
    """
    result = session.execute(
        update(LeaveRequest)
        .where(
            LeaveRequest.id == request_id,
            LeaveRequest.status == from_status,
        )
        .values(status=to_status)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount
