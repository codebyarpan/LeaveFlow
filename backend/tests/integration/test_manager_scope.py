"""The Manager reporting-edge scope, proved against real PostgreSQL (Story 1.7, AC1-AC3).

Story 1.7 does not re-implement the Manager predicate — Story 1.4 built it in
`repositories/scoping.py` and unit-tested its *compiled* form in `tests/domain/test_scoping.py`.
This module supplies the other half that a compiled-SQL assertion cannot: **behavioural proof
against the database the system actually runs on** that the predicate, once composed into a
real `select`, selects exactly a Manager's direct reports and nothing else.

Real PostgreSQL, not a compiled-string check, because all three ACs are database behaviour:
- AC1 — `employee_scope_predicate(Scope.REPORTS, manager)` composed into `select(Employee)`
  returns the reporting edge *from the SQL* (AD-10: the scope is applied IN the query, never a
  Python-side filter over rows already read).
- AC2 — reassigning a report through the real `PATCH /employees/<id>` write path
  (`employee_service.update_employee`) shifts scope membership on the *next evaluation*, with
  the Manager's actor object held UNCHANGED — no new token, no re-login, no re-resolve
  (DR-12: authority is evaluated at decision time).
- AC3 — a `NULL` `manager_id` row falls inside no Manager's scope, because `NULL = :actor_id`
  is never true in SQL — asserted explicitly, not assumed.

No live Manager-facing read endpoint exists in Epic 1 (api-contracts §4.2 grants every
`/employees` endpoint to the Admin alone), so the proof is at the predicate/repository level,
which is exactly what the ACs describe ("*when the resolver/scope is evaluated*"). Epic 2 wires
`Scope.REPORTS` into its first genuinely data-scoped resource (the Leave Request) and runs the
end-to-end HTTP round trip there; fabricating a throwaway Manager route here would prove nothing
the direct predicate evaluation does not.

The `world` fixture mirrors `test_employees.py`: a shared department, a `make` factory for the
manager/report topology, `import app.main` at the top, and a teardown that nulls `manager_id`
before deleting so the `employee -> employee` self-FK (RESTRICT) never blocks cleanup.
"""

import datetime
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee
from app.repositories.scoping import Scope, employee_scope_predicate
from app.services import employee as employee_service

# Import so the app (and its route/exception wiring) is fully constructed, matching the other
# integration modules — the scope proof itself reads the schema, but the write path AC2
# exercises (`update_employee`) shares the app's engine and vocabulary.
import app.main  # noqa: F401

_KNOWN_PASSWORD = "correct-horse-battery-staple"


class _Actor:
    """A held stand-in for the acting Manager — only the `id` a scope predicate binds.

    AC2 turns on this object being reused *unchanged* across a reassignment: the predicate
    binds `:actor_id` from `actor.id` at call time, so re-evaluating the SAME actor after the
    report moves — with no new token and no re-resolve — is precisely the "no re-login" proof.
    """

    def __init__(self, actor_id: uuid.UUID) -> None:
        self.id = actor_id


class _World:
    """A shared department and a factory for the Employees a reporting topology needs."""

    def __init__(self, suffix: str, department_id: uuid.UUID, password_hash: str) -> None:
        self.suffix = suffix
        self.department_id = department_id
        self.password_hash = password_hash

    def make(
        self,
        role: str,
        *,
        manager_id: uuid.UUID | None = None,
        label: str | None = None,
    ) -> uuid.UUID:
        """Insert an Employee directly (test setup, not the code under test) and return its id."""
        label = label or f"emp-{uuid.uuid4().hex[:6]}"
        with Session(get_engine()) as session:
            employee = Employee(
                department_id=self.department_id,
                manager_id=manager_id,
                email=f"{label}-{self.suffix}@example.com",
                full_name=f"Employee {label}",
                role=role,
                joining_date=datetime.date(2026, 1, 1),
                is_active=True,
                password_hash=self.password_hash,
            )
            session.add(employee)
            session.commit()
            return employee.id


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """A shared department; a `make` factory for the reporting topology; self-FK-safe teardown.

    Depends on `db_connection` to inherit the skip-when-DB-absent contract. The teardown nulls
    every `manager_id` among this run's rows before deleting them — the `employee -> employee`
    self-FK is RESTRICT, so a report still pointing at its manager would otherwise block delete.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"mgr-scope-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.commit()
        department_id = department.id

    try:
        yield _World(suffix, department_id, hashed)
    finally:
        with Session(get_engine()) as session:
            like = f"%{suffix}%"
            session.execute(
                update(Employee).where(Employee.email.like(like)).values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(like)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _reports_of(actor: _Actor) -> set[uuid.UUID]:
    """Every Employee id the REPORTS scope selects for `actor`, read straight from the SQL.

    Composes the predicate into a real `select(Employee).where(...)` and returns the ids the
    database returns — so what is asserted is what the query selected, never a post-retrieval
    Python filter (AD-10 / NFR-04). A fresh session each call means the read reflects the
    latest committed state (AC2's reassignment), not a cached identity map.
    """
    with Session(get_engine()) as session:
        rows = session.scalars(
            select(Employee).where(employee_scope_predicate(Scope.REPORTS, actor))
        ).all()
        return {row.id for row in rows}


def test_reports_scope_selects_exactly_the_managers_direct_reports(world: _World) -> None:
    """AC1: `Scope.REPORTS` for Manager A returns exactly A's report R — not B's report, not
    A or B themselves. The reporting edge is selected IN the SQL, proving a data scope, not a
    role check: A and B hold the same MANAGER role, yet A's scope contains only A's report."""
    manager_a = world.make(vocabulary.ROLE_MANAGER, label="mgr-a")
    manager_b = world.make(vocabulary.ROLE_MANAGER, label="mgr-b")
    report_r = world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager_a, label="report-r")
    control = world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager_b, label="control")

    selected = _reports_of(_Actor(manager_a))

    assert selected == {report_r}
    # Explicit exclusions: another Manager's report, and the Managers themselves, are absent.
    assert control not in selected
    assert manager_a not in selected
    assert manager_b not in selected


def test_reassignment_shifts_scope_membership_with_no_re_login(world: _World) -> None:
    """AC2: reassigning R from A to B through the real PATCH write path flips membership on the
    next evaluation — with A's and B's actor objects held UNCHANGED (no new token, no
    re-resolve). Authority is evaluated at decision time (DR-12), so the reporting-edge change
    is all it takes."""
    manager_a = world.make(vocabulary.ROLE_MANAGER, label="reassign-a")
    manager_b = world.make(vocabulary.ROLE_MANAGER, label="reassign-b")
    report_r = world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager_a, label="reassign-r")

    # The two actors are captured ONCE here and never rebuilt — this is the "no re-login".
    actor_a = _Actor(manager_a)
    actor_b = _Actor(manager_b)

    # Before: R is in A's scope, absent from B's.
    assert report_r in _reports_of(actor_a)
    assert report_r not in _reports_of(actor_b)

    # Reassign R to B via the exact write path `PATCH /employees/<id>` uses — no token minted.
    employee_service.update_employee(report_r, {"manager_id": manager_b})

    # After: the SAME actor objects, re-evaluated, see the flipped membership.
    assert report_r in _reports_of(actor_b)
    assert report_r not in _reports_of(actor_a)


def test_a_managerless_employee_is_in_no_managers_scope(world: _World) -> None:
    """AC3: an Employee with `manager_id = NULL` falls inside no Manager's REPORTS scope,
    because `NULL = :actor_id` is never true in SQL. Asserted for EVERY seeded Manager, so the
    exclusion is a property of the predicate, not an accident of one Manager's id.

    A positive control (a real report of A) is seeded so the NULL-exclusion is proven against a
    NON-EMPTY scope: a predicate that (wrongly) compiled to select nothing would fail the control
    rather than pass this test vacuously."""
    manager_a = world.make(vocabulary.ROLE_MANAGER, label="null-mgr-a")
    manager_b = world.make(vocabulary.ROLE_MANAGER, label="null-mgr-b")
    report_a = world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager_a, label="null-report-a")
    managerless = world.make(vocabulary.ROLE_EMPLOYEE, manager_id=None, label="managerless")

    # Positive control: A's real report IS in scope, so "excluded" is distinguished from "empty".
    assert report_a in _reports_of(_Actor(manager_a))

    for manager_id in (manager_a, manager_b):
        assert managerless not in _reports_of(_Actor(manager_id))
