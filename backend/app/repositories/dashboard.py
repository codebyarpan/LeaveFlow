"""The dashboard's scoped aggregates — counts and one bounded DISTINCT list (Story 3.5).

Implements: FR-11 (the three role dashboards' figures), AD-10 (every aggregate takes the
`actor` and applies `employee_scope_predicate(scope, actor)` IN the SQL — an out-of-scope
row is never counted, NFR-04), AD-16 (every figure is derived by a query on every call,
never stored). SM-6.

--- Why this module exists, rather than these living in `repositories/leave_request.py` ---

`ARCHITECTURE-SPINE.md:394` maps FR-11 to "`api/v1/dashboard`, **scoped repository
aggregates**" — this module IS that scoped-aggregate module, sanctioned by the spine by
name. It could not be an addition to `repositories/leave_request.py` anyway: that module's
public surface is hard-pinned BY NAME at `tests/integration/test_leave_request_submit.py`
(the AD-8/AD-9 append-only guarantee is load-bearing on the pin), and a dashboard COUNT
does not qualify to widen it.

--- The join is unconditional, and the count idiom here is NOT the house one ---

The scope predicate is a predicate over the `Employee` table (`Employee.manager_id ==
:actor_id`), not over `leave_request` — so every aggregate JOINs `Employee` explicitly,
the `repositories/leave_request.list_leave_requests` count shape. The 14 bare
`select(func.count()).select_from(M)` sites elsewhere are single-table counts; copied here
they would emit an implicit CARTESIAN PRODUCT that SQLAlchemy only warns about, and a
wildly inflated figure would ship green. Under `Scope.ALL` the predicate is `true()` and
the join is a harmless no-op (the FK guarantees no row is dropped), so one code path
serves SELF, REPORTS and ALL.

--- People, not requests (Landmine 1) ---

"Employees on approved leave" counts PEOPLE: nothing forbids one Employee holding two
APPROVED requests overlapping the same window (submit has no overlap guard), so
`count_employees_on_leave` is `COUNT(DISTINCT leave_request.employee_id)` and
`list_employees_on_leave` is `SELECT DISTINCT (employee_id, full_name)`. The pending-queue
figures count REQUESTS (`COUNT(*)`) — a queue is a list of requests. These are different
numbers by design; `list_leave_requests`'s `total` cannot express the first two.

The two `count_*` names sit outside `tests/test_scoped_getters.py`'s `_READ_VERB_PREFIXES`;
they take the `actor` anyway and predicate on it — the `repositories/notification.py`
`count_unread` posture: "because the scope is a correctness requirement, not a test-passing
ritual." `list_employees_on_leave` IS a `list_` getter and takes the `actor` as the guard
requires. `limit` arrives as an argument from the caller (`api/` owns the bound and hands
it down through the service — `services/` may not import `app.api`, contract 1).
"""

import datetime

from sqlalchemy import ColumnElement, Row, func, select
from sqlalchemy.orm import Session

from app.repositories.models import Employee, LeaveRequest
from app.repositories.scoping import Scope, employee_scope_predicate


def _conditions(
    actor: Employee,
    scope: Scope,
    status: str,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
) -> list[ColumnElement[bool]]:
    """The one predicate list every aggregate shares: scope (AD-10), status, and the SETTLED
    3.1 overlap window (`end_date >= date_from AND start_date <= date_to`, each side optional
    — an absent side applies no predicate; an inverted range is an empty intersection, never
    an error). Every filter is on a LOCAL `leave_request` column beside the scope predicate,
    so no two figures can disagree about what "inside the range" means."""
    conditions: list[ColumnElement[bool]] = [
        employee_scope_predicate(scope, actor),
        LeaveRequest.status == status,
    ]
    if date_from is not None:
        conditions.append(LeaveRequest.end_date >= date_from)
    if date_to is not None:
        conditions.append(LeaveRequest.start_date <= date_to)
    return conditions


def count_leave_requests(
    session: Session,
    actor: Employee,
    *,
    scope: Scope,
    status: str,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
) -> int:
    """`COUNT(*)` of Leave Requests under `actor`'s scope — the two PENDING-queue figures
    (FR-11: the Employee's own pending count, the Manager's awaiting-decision count, the
    Admin's org-wide pending count). Counts REQUESTS: a queue is a list of requests
    (contrast `count_employees_on_leave`, which counts people)."""
    return (
        session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*_conditions(actor, scope, status, date_from, date_to))
        )
        or 0
    )


def count_employees_on_leave(
    session: Session,
    actor: Employee,
    *,
    scope: Scope,
    status: str,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
) -> int:
    """`COUNT(DISTINCT employee_id)` — PEOPLE on leave in the window, not requests
    (Landmine 1). An Employee holding two APPROVED requests overlapping the same window is
    one person on leave; a plain `COUNT(*)` would double-count them and ship green."""
    return (
        session.scalar(
            select(func.count(func.distinct(LeaveRequest.employee_id)))
            .select_from(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*_conditions(actor, scope, status, date_from, date_to))
        )
        or 0
    )


def list_employees_on_leave(
    session: Session,
    actor: Employee,
    *,
    scope: Scope,
    status: str,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
    limit: int,
) -> list[Row]:  # type: ignore[type-arg]
    """The DISTINCT `(employee_id, full_name)` pairs on leave in the window, ordered by
    name, bounded by `limit` (NFR-11 — the bound is the route's, handed down). `full_name`
    is IN the select list, which is what makes the `ORDER BY` legal under `SELECT
    DISTINCT`. Returns plain columns, not the ORM entity — the dashboard needs exactly the
    two fields it presents and nothing more (the minimal-disclosure posture)."""
    return list(
        session.execute(
            select(LeaveRequest.employee_id, Employee.full_name)
            .select_from(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*_conditions(actor, scope, status, date_from, date_to))
            .distinct()
            .order_by(Employee.full_name)
            .limit(limit)
        ).all()
    )
