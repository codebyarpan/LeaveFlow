"""Leave Request writes and the pending-request count (Story 2.6, FR-08/AD-8/AD-22).

Implements: AC3/AC5 (`insert_leave_request` persists the row the submission command composed
under the balance lock — the `PENDING` managed path or the `APPROVED` managerless auto-approval),
AC7 (`count_pending_for_employee` is the input to Story 1.6's deactivation guard, made executable
now that `leave_request` exists). SM-6.

--- No update/delete surface (AD-8) ---

This module exposes an INSERT and a COUNT — and NOTHING that updates or deletes a `leave_request`
row. The lifecycle transitions (approve/reject/cancel) are Story 2.7's guarded `UPDATE … WHERE
status = :from` (AD-4), not a repository method here; the create is append-only from this story's
point of view, so no mutation path is offered that 2.7 would have to re-guard.

--- Why `count_pending_for_employee` is named `count_`, not `get_`/`list_` ---

`tests/test_scoped_getters.py` reflects over every `get_`/`list_`/`find_`/`fetch_` function taking
a `session`, requiring the AD-10 `actor` parameter. This function is named `count_`, returns an
`int`, and takes the target `employee_id` the deactivation guard already holds (the Admin has
loaded the Employee it is deactivating) — so it is correctly NOT a scoped-getter candidate,
mirroring `repositories/employee.count_active_direct_reports`. There is no per-row disclosure to
scope: it answers a bounded yes/no-shaped count about one already-authorized target.
"""

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.repositories.models import LeaveRequest


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
