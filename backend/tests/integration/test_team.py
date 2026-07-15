"""`GET /api/v1/team` — a Manager's Direct Reports, and nobody else's (Story 3.2, AC1-AC4).

Implements the test side of: FR-19 (a Manager sees who reports to them, each named by Full
Name and Department, deactivated reports distinguishable), AD-10 (the REPORTS scope is a SQL
predicate — an out-of-scope row is never retrieved), G3 / api-contracts §1 (the role-denied
refusal is `403 ACTION_NOT_PERMITTED` with the full envelope, decided by the role gate before
any row is read).

The ONE contract inversion this file pins: api-contracts §4.9 grants `/team` to the Manager
ALONE — the ADMIN is refused 403 alongside the Employee (AC4). An Admin sees everyone through
`GET /employees`; a team is a reporting edge only a Manager stands on.

Against real PostgreSQL through the REAL app (`TestClient(app.main.app)`): importing
`app.main` is what registers the v1 routes and the error handler — skip the import and every
request 404s against an empty app (a past false-green the template files record). The world
is built per-file in the house style (`test_role_gate.py` / `test_manager_scope.py`): no
shared role fixtures exist, and the teardown nulls `manager_id` before deleting because the
`employee -> employee` self-FK is RESTRICT.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee

# Importing `app.main` constructs the real app: routes registered on `api_v1_router`, the
# DomainError handler installed, `CODE_TO_STATUS` populated. The TestClient below targets it.
import app.main  # noqa: F401

# See test_me.py: silence starlette's httpx-deprecation warning at import so it does not
# clutter this suite; it is not spine-governed.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

_client = TestClient(app.main.app)

_KNOWN_PASSWORD = "correct-horse-battery-staple"

# The minimal disclosure contract (Open Decision #1): EXACTLY these keys, nothing more.
# `email`, `role`, `joining_date` and `manager_id` are the Admin view's — no requirement
# grants a Manager sight of them, and this pin is what keeps the decision made.
_EXPECTED_ITEM_KEYS = {"id", "full_name", "department", "is_active"}


class _Member:
    """One seeded Employee: its id, and (when the test needs to call as them) a token."""

    def __init__(self, employee_id: uuid.UUID, token: str) -> None:
        self.id = employee_id
        self.token = token


class _World:
    """The reporting topology AC1 needs: two managers, split reports, an Admin, an empty Manager.

    - `manager_m` — the Manager under test.
    - `report_active` / `report_inactive` — M's two Direct Reports; ONE is deactivated (AC3:
      present and distinguishable, never filtered out).
    - `other_manager` / `other_report` — a second reporting edge; `other_report` is also the
      EMPLOYEE-role caller AC4 refuses.
    - `admin` — the Admin AC4 refuses (the §4.9 inversion).
    - `empty_manager` — a MANAGER-role caller with zero reports (a real state: G8 blocks
      demotion only while reports exist; a new Manager may simply have none yet).
    """

    def __init__(self) -> None:
        self.admin: _Member = None  # type: ignore[assignment]
        self.manager_m: _Member = None  # type: ignore[assignment]
        self.report_active: _Member = None  # type: ignore[assignment]
        self.report_inactive: _Member = None  # type: ignore[assignment]
        self.other_manager: _Member = None  # type: ignore[assignment]
        self.other_report: _Member = None  # type: ignore[assignment]
        self.empty_manager: _Member = None  # type: ignore[assignment]


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """Build the topology; teardown nulls `manager_id` before deleting (self-FK is RESTRICT).

    Depends on `db_connection` to inherit the skip-when-DB-absent contract. Emails carry a
    per-run uuid suffix so parallel or aborted runs never collide.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"team-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)
    built = _World()

    def _insert(
        session: Session,
        label: str,
        role: str,
        *,
        manager_id: uuid.UUID | None = None,
        is_active: bool = True,
        department_id: uuid.UUID,
    ) -> _Member:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"{label}-{suffix}@example.com",
            full_name=f"Team {label}",
            role=role,
            joining_date=datetime.date(2026, 1, 1),
            is_active=is_active,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        return _Member(employee.id, security.create_token(str(employee.id), role))

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
        dept_id = department.id

        built.admin = _insert(session, "admin", vocabulary.ROLE_ADMIN, department_id=dept_id)
        built.manager_m = _insert(
            session, "manager-m", vocabulary.ROLE_MANAGER, department_id=dept_id
        )
        built.report_active = _insert(
            session,
            "report-active",
            vocabulary.ROLE_EMPLOYEE,
            manager_id=built.manager_m.id,
            department_id=dept_id,
        )
        built.report_inactive = _insert(
            session,
            "report-inactive",
            vocabulary.ROLE_EMPLOYEE,
            manager_id=built.manager_m.id,
            is_active=False,
            department_id=dept_id,
        )
        built.other_manager = _insert(
            session, "other-manager", vocabulary.ROLE_MANAGER, department_id=dept_id
        )
        built.other_report = _insert(
            session,
            "other-report",
            vocabulary.ROLE_EMPLOYEE,
            manager_id=built.other_manager.id,
            department_id=dept_id,
        )
        built.empty_manager = _insert(
            session, "empty-manager", vocabulary.ROLE_MANAGER, department_id=dept_id
        )
        session.commit()

    try:
        yield built
    finally:
        with Session(get_engine()) as session:
            like = f"%{suffix}%"
            session.execute(
                update(Employee).where(Employee.email.like(like)).values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(like)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _get_team(token: str | None, query: str = "") -> object:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return _client.get(f"/api/v1/team{query}", headers=headers)


def test_a_manager_sees_exactly_their_direct_reports(world: _World) -> None:
    """AC1: M's list is exactly M's reports — the other manager's report absent, M's own row
    absent (`manager_id == actor.id` can never match self), no Admin row — and `total` equals
    the report count. The exclusion is the SQL predicate's (AD-10), not a client filter."""
    response = _get_team(world.manager_m.token)

    assert response.status_code == 200
    body = response.json()
    returned_ids = {item["id"] for item in body["items"]}

    assert returned_ids == {str(world.report_active.id), str(world.report_inactive.id)}
    assert body["total"] == 2
    # Explicit exclusions, named one by one.
    assert str(world.other_report.id) not in returned_ids
    assert str(world.manager_m.id) not in returned_ids
    assert str(world.admin.id) not in returned_ids


def test_each_item_carries_exactly_the_minimal_key_set(world: _World) -> None:
    """AC2 + Open Decision #1: every item is EXACTLY `{id, full_name, department, is_active}`
    with `department == {id, name}` — identification by Full Name and Department, and any
    accidental email/role/joining_date/manager_id leakage fails this assertion."""
    response = _get_team(world.manager_m.token)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    for item in items:
        assert set(item) == _EXPECTED_ITEM_KEYS
        assert set(item["department"]) == {"id", "name"}
        assert item["full_name"].startswith("Team report-")
        assert item["department"]["name"].startswith("team-dept-")


def test_a_deactivated_report_is_present_and_distinguishable(world: _World) -> None:
    """AC3: the deactivated report is IN the list (`distinguishable` means PRESENT), carrying
    `is_active` false on the wire; the active one carries true. The REPORTS predicate has no
    `is_active` filter and must never grow one (Landmine 1)."""
    response = _get_team(world.manager_m.token)

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()["items"]}

    assert by_id[str(world.report_inactive.id)]["is_active"] is False
    assert by_id[str(world.report_active.id)]["is_active"] is True


@pytest.mark.parametrize("denied", ["admin", "other_report"])
def test_admin_and_employee_are_refused_403_by_the_role_gate(
    world: _World, denied: str
) -> None:
    """AC4 / Landmine 5: an Admin AND an Employee get `403 ACTION_NOT_PERMITTED` with the
    full `{code, message, details}` envelope and empty details — decided by `require_role`
    in the dependency, before any row is read. The Admin refusal is the §4.9 inversion:
    `/team` is granted to the Manager alone."""
    caller: _Member = getattr(world, denied)

    response = _get_team(caller.token)

    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.ACTION_NOT_PERMITTED
    assert body["details"] == {}


def test_an_absent_token_is_401_not_403(world: _World) -> None:
    """No token → 401 (`require_role` chains authentication first; a missing token is never
    turned into a 403). One cheap assertion while the file is here anyway."""
    response = _get_team(None)

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID


def test_envelope_and_page_size_clamp(world: _World) -> None:
    """The response is the standard `items/page/page_size/total` envelope, and an over-max
    `page_size` is CLAMPED to `MAX_PAGE_SIZE` (100), never a 422 — one assertion here; the
    clamp machinery itself is pinned globally in `test_pagination.py`."""
    response = _get_team(world.manager_m.token, "?page_size=200")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page_size"] == 100
    assert body["page"] == 1


def test_a_manager_with_no_reports_gets_an_empty_page(world: _World) -> None:
    """A MANAGER-role caller with zero reports is a real state (G8 blocks demotion only while
    reports exist; a new Manager may have none yet): `200`, empty items, `total == 0` — never
    an error."""
    response = _get_team(world.empty_manager.token)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
