"""The two balance reads, end to end against real PostgreSQL (Story 2.4, AC5/AC6/AC9/AC10).

Implements the test side of: AC5 (`GET /balances` returns the caller's own balances, `available`
primary and DERIVED, with `reserved`/`consumed`; no `accrued`/no stored-`available` leakage),
AC6/AC9 (`GET /employees/<id>/balances` — an Admin sees anyone; a Manager sees a Direct Report;
a Manager gets a byte-identical `404` for a non-report, and an Employee gets `403
ACTION_NOT_PERMITTED`), AC10 (`available` is derived at the projection — proven by reserving days
and watching `available` drop while `reserved` rises).

Real PostgreSQL: the scope predicate, the 404-vs-403 distinction and the derivation all run
through the live database and the real router. Balances are materialized by creating two Leave
Types through the service (which materializes for every Employee, Story 2.4's hook).
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee, LeaveBalance, LeaveType
from app.services import balances
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 403/404 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
_client = TestClient(app)


class _World:
    def __init__(self, suffix: str, ids: dict[str, uuid.UUID], tokens: dict[str, str],
                 type_a: uuid.UUID, type_b: uuid.UUID) -> None:
        self.suffix = suffix
        self.ids = ids
        self.tokens = tokens
        self.type_a = type_a  # code RB-A-*, entitlement 12
        self.type_b = type_b  # code RB-B-*, entitlement 6


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """Admin / Manager / a Manager's report / a non-report; two Leave Types materialized for all.

    Employees are inserted directly (a controlled reporting topology), then two Leave Types are
    created through the service so a balance materializes for every Employee (Story 2.4). Every
    Employee joins on 1 January, so each balance is the full entitlement (12 and 6).
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"rb-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()

        def make(role: str, label: str, manager_id: uuid.UUID | None) -> uuid.UUID:
            employee = Employee(
                department_id=department.id,
                manager_id=manager_id,
                email=f"rb-{label}-{suffix}@example.com",
                full_name=f"RB {label}",
                role=role,
                joining_date=datetime.date(_YEAR, 1, 1),  # full-year → full entitlement
                is_active=True,
                password_hash=hashed,
            )
            session.add(employee)
            session.flush()
            return employee.id

        admin_id = make(vocabulary.ROLE_ADMIN, "admin", None)
        manager_id = make(vocabulary.ROLE_MANAGER, "manager", None)
        report_id = make(vocabulary.ROLE_EMPLOYEE, "report", manager_id)
        nonreport_id = make(vocabulary.ROLE_EMPLOYEE, "nonreport", None)
        session.commit()

    ids = {"admin": admin_id, "manager": manager_id, "report": report_id, "nonreport": nonreport_id}
    roles = {
        "admin": vocabulary.ROLE_ADMIN,
        "manager": vocabulary.ROLE_MANAGER,
        "report": vocabulary.ROLE_EMPLOYEE,
        "nonreport": vocabulary.ROLE_EMPLOYEE,
    }
    tokens = {k: security.create_token(str(v), roles[k]) for k, v in ids.items()}

    # Two Leave Types through the service — materializes a balance for every Employee.
    type_a = leave_types_service.create_leave_type(
        code=f"RB-A-{suffix}", name="Read balance A", annual_entitlement=12,
        carries_forward=False, carry_forward_cap=None, requires_supporting_document=False,
    ).id
    type_b = leave_types_service.create_leave_type(
        code=f"RB-B-{suffix}", name="Read balance B", annual_entitlement=6,
        carries_forward=False, carry_forward_cap=None, requires_supporting_document=False,
    ).id

    try:
        yield _World(suffix, ids, tokens, type_a, type_b)
    finally:
        with Session(get_engine()) as session:
            # Balances reference both employee and type; clear this run's types' balances (which
            # span every Employee incl. seed) and our employees' balances, then the rows.
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id.in_([type_a, type_b]))
            )
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.employee_id.in_(list(ids.values())))
            )
            session.execute(
                update(Employee).where(Employee.email.like(f"%{suffix}%")).values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id.in_([type_a, type_b])))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


_BALANCE_KEYS = {"leave_type_code", "leave_type_name", "available", "reserved", "consumed"}


# --- AC5: GET /balances returns the caller's own balances, available derived ---------------


def test_self_read_returns_own_balances_available_derived(world: _World) -> None:
    """AC5/AC10: `GET /balances` returns the caller's balances; `available` is derived, and the
    body never leaks `accrued` or a stored `available` column."""
    response = _client.get("/api/v1/balances", headers=_auth(world.tokens["report"]))

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)  # a plain collection, not the Page envelope
    # Two Leave Types, ordered by code (RB-A before RB-B).
    ours = [b for b in body if b["leave_type_code"].startswith(("RB-A-", "RB-B-"))]
    assert [b["leave_type_code"][:4] for b in ours] == ["RB-A", "RB-B"]

    for item in ours:
        # Exactly the three contract quantities plus the labels — no `accrued` key.
        assert set(item) == _BALANCE_KEYS
        assert "accrued" not in item
    # Full-year joiner → available equals the full entitlement, reserved/consumed 0.
    by_code = {b["leave_type_code"]: b for b in ours}
    assert by_code[f"RB-A-{world.suffix}"]["available"] == 12
    assert by_code[f"RB-B-{world.suffix}"]["available"] == 6
    assert by_code[f"RB-A-{world.suffix}"]["reserved"] == 0


def test_available_is_derived_reserving_days_drops_it(world: _World) -> None:
    """AC10: `available` is `accrued − consumed − reserved`, computed at read time — reserve 3
    days and `available` drops from 12 to 9 while `reserved` rises to 3."""
    with Session(get_engine()) as session:
        balances.reserve(
            session,
            employee_id=world.ids["report"],
            leave_type_id=world.type_a,
            leave_year=_YEAR,
            days=3,
        )
        session.commit()

    response = _client.get("/api/v1/balances", headers=_auth(world.tokens["report"]))
    assert response.status_code == 200
    a = next(b for b in response.json() if b["leave_type_code"] == f"RB-A-{world.suffix}")
    assert a["available"] == 9  # 12 - 0 - 3
    assert a["reserved"] == 3
    assert a["consumed"] == 0


def test_self_read_requires_a_valid_token(world: _World) -> None:
    """AC5: `GET /balances` with no/invalid token is `401 TOKEN_INVALID`."""
    for headers in ({}, _auth("not-a-real-token")):
        response = _client.get("/api/v1/balances", headers=headers)
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- AC6: GET /employees/<id>/balances — Admin anyone, Manager reports, else 404/403 -------


def test_admin_reads_any_employees_balances(world: _World) -> None:
    """AC6: an Admin reads any Employee's balances (scope `all`)."""
    response = _client.get(
        f"/api/v1/employees/{world.ids['nonreport']}/balances",
        headers=_auth(world.tokens["admin"]),
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_manager_reads_a_direct_reports_balances(world: _World) -> None:
    """AC6: a Manager reads a Direct Report's balances (scope `reports`)."""
    response = _client.get(
        f"/api/v1/employees/{world.ids['report']}/balances",
        headers=_auth(world.tokens["manager"]),
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_manager_gets_404_for_a_non_report_byte_identical_to_nonexistent(world: _World) -> None:
    """AC6/AC9/AD-10: a Manager naming a non-report gets `404 RESOURCE_NOT_FOUND`, byte-identical
    to a nonexistent id — a scope miss is indistinguishable from "no such Employee"."""
    non_report = _client.get(
        f"/api/v1/employees/{world.ids['nonreport']}/balances",
        headers=_auth(world.tokens["manager"]),
    )
    nonexistent = _client.get(
        f"/api/v1/employees/{uuid.uuid4()}/balances",
        headers=_auth(world.tokens["manager"]),
    )

    assert non_report.status_code == 404
    assert non_report.json()["code"] == vocabulary.RESOURCE_NOT_FOUND
    # Byte-identical: same status and the very same response bytes (AD-10).
    assert nonexistent.status_code == 404
    assert non_report.content == nonexistent.content


def test_an_employee_is_403_before_any_row_is_read(world: _World) -> None:
    """AC6: an Employee (role not granted) calling `GET /employees/<id>/balances` is `403
    ACTION_NOT_PERMITTED`, decided by the role gate before any row is read."""
    response = _client.get(
        f"/api/v1/employees/{world.ids['report']}/balances",
        headers=_auth(world.tokens["nonreport"]),  # an EMPLOYEE-role token
    )
    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
