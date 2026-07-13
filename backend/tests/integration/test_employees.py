"""The `/api/v1/employees` endpoints, end to end, against real PostgreSQL.

Implements the test side of Story 1.6's thirteen criteria (AC1–AC12 exercised here; AC13 is
the frontend's, proved by build/lint/click-through). Real PostgreSQL because the refusals
this story adds are database behaviour: the `UNIQUE (email)` backstop (AC6), the manager
self-FK the cycle walk protects (AC7), and the `is_active`-qualified report count (AC8/AC9)
all depend on the engine the system actually runs on — a SQLite swap would prove none of it.

The `world` fixture mirrors `test_departments.py`'s `callers`: one active Employee per role
in a shared department, a signed token each, `import app.main` at the top so `CODE_TO_STATUS`
is populated. It adds a `make` factory for the report/manager topologies AC7–AC9 need, and a
teardown that nulls `manager_id` before deleting so the self-FK never blocks cleanup.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, select, update
from sqlalchemy.orm import Session

from app.api.v1.pagination import MAX_PAGE_SIZE
from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee, LeaveBalance

# Populates `CODE_TO_STATUS` so EMAIL_ALREADY_IN_USE→409, REPORTING_CYCLE→400,
# EMPLOYEE_HAS_DIRECT_REPORTS→409, ACTION_NOT_PERMITTED→403, RESOURCE_NOT_FOUND→404 render.
import app.main  # noqa: F401

# See test_me.py: starlette's httpx-deprecation warning is not spine-governed; silence it.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_client = TestClient(app)


class _World:
    """The shared department, one token per role, and a factory for extra Employees."""

    def __init__(
        self,
        suffix: str,
        department_id: uuid.UUID,
        department_name: str,
        tokens: dict[str, str],
        password_hash: str,
    ) -> None:
        self.suffix = suffix
        self.department_id = department_id
        self.department_name = department_name
        self.tokens = tokens
        self.password_hash = password_hash

    def email(self, label: str) -> str:
        """A unique email for this run — suffixed so parallel runs never collide, and so the
        teardown can sweep every row it created with one `LIKE`."""
        return f"{label}-{self.suffix}@example.com"

    def make(
        self,
        role: str,
        *,
        manager_id: uuid.UUID | None = None,
        is_active: bool = True,
        label: str | None = None,
    ) -> uuid.UUID:
        """Insert an Employee directly (test setup, not the endpoint under test) and return
        its id. Used to stand up the manager/report topologies AC7–AC9 need."""
        label = label or f"emp-{uuid.uuid4().hex[:6]}"
        with Session(get_engine()) as session:
            employee = Employee(
                department_id=self.department_id,
                manager_id=manager_id,
                email=self.email(label),
                full_name=f"Employee {label}",
                role=role,
                joining_date=datetime.date(2026, 1, 1),
                is_active=is_active,
                password_hash=self.password_hash,
            )
            session.add(employee)
            session.commit()
            return employee.id


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """One active Employee per role in a shared department; a signed token for each.

    Depends on `db_connection` to inherit skip-when-DB-absent. The teardown first nulls every
    `manager_id` among this run's rows, then deletes them — the `employee → employee` self-FK
    is RESTRICT, so a report still pointing at its manager would otherwise block the delete.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"emp-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    made: dict[str, uuid.UUID] = {}
    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
        department_id = department.id

        for role in (
            vocabulary.ROLE_ADMIN,
            vocabulary.ROLE_MANAGER,
            vocabulary.ROLE_EMPLOYEE,
        ):
            employee = Employee(
                department_id=department_id,
                manager_id=None,
                email=f"caller-{role.lower()}-{suffix}@example.com",
                full_name=f"Caller {role}",
                role=role,
                joining_date=datetime.date(2026, 1, 1),
                is_active=True,
                password_hash=hashed,
            )
            session.add(employee)
            session.flush()
            made[role] = employee.id
        session.commit()

    tokens = {role: security.create_token(str(eid), role) for role, eid in made.items()}

    try:
        yield _World(suffix, department_id, department_name, tokens, hashed)
    finally:
        with Session(get_engine()) as session:
            like = f"%{suffix}%"
            # Story 2.4: an Employee created through POST /employees has a materialized
            # leave_balance row per Leave Type; clear them before the FK-guarded Employee delete.
            session.execute(
                delete(LeaveBalance).where(
                    LeaveBalance.employee_id.in_(
                        select(Employee.id).where(Employee.email.like(like))
                    )
                )
            )
            session.execute(
                update(Employee).where(Employee.email.like(like)).values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(like)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _admin(world: _World) -> dict[str, str]:
    return _auth(world.tokens[vocabulary.ROLE_ADMIN])


def _get_row(employee_id: uuid.UUID) -> Employee | None:
    with Session(get_engine()) as session:
        return session.get(Employee, employee_id)


def _create_payload(world: _World, **overrides: object) -> dict[str, object]:
    """A valid create body, with a unique email and a per-call password; overridable."""
    payload: dict[str, object] = {
        "email": world.email(f"hire-{uuid.uuid4().hex[:6]}"),
        "full_name": "New Hire",
        "role": vocabulary.ROLE_EMPLOYEE,
        "department_id": str(world.department_id),
        "joining_date": "2026-02-01",
        "password": _KNOWN_PASSWORD,
    }
    payload.update(overrides)
    return payload


# --- AC1: an Admin creates an active Employee who can immediately authenticate ----------


def test_admin_creates_an_active_employee_who_can_authenticate(world: _World) -> None:
    """AC1: `POST /employees` creates an active Employee; the initial password works end-to-end."""
    email = world.email("can-login")
    password = "initial-pass-1.6"

    response = _client.post(
        "/api/v1/employees",
        json=_create_payload(world, email=email, password=password, full_name="Ada Lovelace"),
        headers=_admin(world),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "email",
        "full_name",
        "role",
        "department",
        "manager_id",
        "joining_date",
        "is_active",
    }
    assert body["email"] == email
    assert body["is_active"] is True
    assert body["manager_id"] is None
    assert body["department"] == {
        "id": str(world.department_id),
        "name": world.department_name,
    }

    # AC1: the created Employee can immediately authenticate with the supplied password.
    login = _client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_assigning_a_manager_on_create_establishes_the_reporting_edge(world: _World) -> None:
    """AC1: a create with a `manager_id` persists the Direct Report relationship FR-03 needs."""
    manager_id = world.make(vocabulary.ROLE_MANAGER, label="mgr")

    response = _client.post(
        "/api/v1/employees",
        json=_create_payload(world, manager_id=str(manager_id)),
        headers=_admin(world),
    )

    assert response.status_code == 201
    assert response.json()["manager_id"] == str(manager_id)
    created = _get_row(uuid.UUID(response.json()["id"]))
    assert created is not None and created.manager_id == manager_id


# --- AC2: the password is hashed once, and never disclosed ------------------------------


def test_no_response_discloses_a_password_or_hash_and_the_stored_hash_verifies(
    world: _World,
) -> None:
    """AC2: no create/read/update/deactivate body carries `password`/`password_hash`, and the
    stored hash verifies against the supplied password (hashed once, through `pwdlib`)."""
    email = world.email("secret")
    password = "hash-me-once-please"

    created = _client.post(
        "/api/v1/employees",
        json=_create_payload(world, email=email, password=password),
        headers=_admin(world),
    )
    assert created.status_code == 201
    employee_id = uuid.UUID(created.json()["id"])

    read = _client.get(f"/api/v1/employees/{employee_id}", headers=_admin(world))
    updated = _client.patch(
        f"/api/v1/employees/{employee_id}",
        json={"full_name": "Renamed Person"},
        headers=_admin(world),
    )
    deactivated = _client.post(
        f"/api/v1/employees/{employee_id}/deactivate", headers=_admin(world)
    )

    for response in (created, read, updated, deactivated):
        assert response.status_code in (200, 201)
        assert "password" not in response.json()
        assert "password_hash" not in response.json()

    # The stored hash is a real salted digest of the supplied password (AD-14, NFR-01).
    row = _get_row(employee_id)
    assert row is not None
    assert row.password_hash != password
    assert security.verify_password(password, row.password_hash) is True


# --- AC3: the Admin reads and updates every Employee; PATCH ignores a password ----------


def test_admin_reads_the_list_and_a_single_employee(world: _World) -> None:
    """AC3: an Admin `GET`s the list (envelope + the caller rows) and a single Employee by id."""
    list_response = _client.get("/api/v1/employees", headers=_admin(world))
    assert list_response.status_code == 200
    body = list_response.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["total"] >= 3  # at least the three caller rows

    admin_id = uuid.UUID(
        next(
            item["id"]
            for item in body["items"]
            if item["email"] == f"caller-admin-{world.suffix}@example.com"
        )
    )
    one = _client.get(f"/api/v1/employees/{admin_id}", headers=_admin(world))
    assert one.status_code == 200
    assert one.json()["id"] == str(admin_id)
    assert one.json()["role"] == vocabulary.ROLE_ADMIN


def test_admin_updates_every_mutable_field(world: _World) -> None:
    """AC3: an Admin changes email, full name, role, department, manager and joining date."""
    target = world.make(vocabulary.ROLE_EMPLOYEE, label="mutable")
    manager_id = world.make(vocabulary.ROLE_MANAGER, label="new-mgr")
    other_department = f"other-{world.suffix}"
    with Session(get_engine()) as session:
        department = Department(name=other_department)
        session.add(department)
        session.commit()
        other_department_id = department.id

    try:
        new_email = world.email("updated-email")
        response = _client.patch(
            f"/api/v1/employees/{target}",
            json={
                "email": new_email,
                "full_name": "Updated Name",
                "role": vocabulary.ROLE_MANAGER,
                "department_id": str(other_department_id),
                "manager_id": str(manager_id),
                "joining_date": "2027-03-04",
            },
            headers=_admin(world),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == new_email
        assert body["full_name"] == "Updated Name"
        assert body["role"] == vocabulary.ROLE_MANAGER
        assert body["department"] == {"id": str(other_department_id), "name": other_department}
        assert body["manager_id"] == str(manager_id)
        assert body["joining_date"] == "2027-03-04"
    finally:
        with Session(get_engine()) as session:
            session.execute(
                update(Employee).where(Employee.id == target).values(department_id=world.department_id)
            )
            session.commit()
            session.execute(delete(Department).where(Department.id == other_department_id))
            session.commit()


def test_patch_ignores_a_password_field_there_is_no_reissue(world: _World) -> None:
    """AC3: a `PATCH` carrying a `password` leaves the stored hash unchanged (no re-issue)."""
    email = world.email("no-reissue")
    original = "original-password"
    created = _client.post(
        "/api/v1/employees",
        json=_create_payload(world, email=email, password=original),
        headers=_admin(world),
    )
    employee_id = uuid.UUID(created.json()["id"])
    before = _get_row(employee_id).password_hash

    response = _client.patch(
        f"/api/v1/employees/{employee_id}",
        json={"password": "attempted-new-password", "full_name": "Still Them"},
        headers=_admin(world),
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Still Them"  # the legitimate field changed
    after = _get_row(employee_id).password_hash
    assert after == before  # the password field was ignored, not applied
    assert security.verify_password(original, after) is True


# --- AC4: the list is page-bounded --------------------------------------------------------


def test_a_page_size_above_the_maximum_is_clamped(world: _World) -> None:
    """AC4: with more than `MAX_PAGE_SIZE` employees, a larger `page_size` returns the max."""
    with Session(get_engine()) as session:
        session.add_all(
            [
                Employee(
                    department_id=world.department_id,
                    manager_id=None,
                    email=world.email(f"page-{i:03d}"),
                    full_name=f"Page Filler {i}",
                    role=vocabulary.ROLE_EMPLOYEE,
                    joining_date=datetime.date(2026, 1, 1),
                    is_active=True,
                    password_hash=world.password_hash,
                )
                for i in range(MAX_PAGE_SIZE + 1)
            ]
        )
        session.commit()

    response = _client.get(
        "/api/v1/employees",
        params={"page": 1, "page_size": MAX_PAGE_SIZE + 500},
        headers=_admin(world),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page_size"] == MAX_PAGE_SIZE
    assert len(body["items"]) == MAX_PAGE_SIZE
    assert body["total"] >= MAX_PAGE_SIZE + 1


# --- AC5: every endpoint is 403 for a non-Admin, before any row is touched --------------


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_every_endpoint_is_403_for_a_non_admin(world: _World, denied_role: str) -> None:
    """AC5: POST, GET list, GET by-id, PATCH and deactivate all refuse a Manager/Employee
    with `403 ACTION_NOT_PERMITTED`, and nothing is written."""
    headers = _auth(world.tokens[denied_role])
    target = world.make(vocabulary.ROLE_EMPLOYEE, label="untouched")
    before = _get_row(target).full_name
    new_email = world.email("should-not-exist")

    cases = [
        _client.post("/api/v1/employees", json=_create_payload(world, email=new_email), headers=headers),
        _client.get("/api/v1/employees", headers=headers),
        _client.get(f"/api/v1/employees/{target}", headers=headers),
        _client.patch(f"/api/v1/employees/{target}", json={"full_name": "Hacked"}, headers=headers),
        _client.post(f"/api/v1/employees/{target}/deactivate", headers=headers),
    ]

    for response in cases:
        assert response.status_code == 403
        assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED

    # Nothing was read or written: the create's email never landed, the target is unchanged.
    with Session(get_engine()) as session:
        assert session.scalar(select(Employee).where(Employee.email == new_email)) is None
    after = _get_row(target)
    assert after.full_name == before
    assert after.is_active is True


# --- AC6: a duplicate email is refused 409, active or deactivated -----------------------


def test_create_with_an_email_already_held_is_409(world: _World) -> None:
    """AC6: creating with an email an ACTIVE Employee holds → `409 EMAIL_ALREADY_IN_USE`."""
    email = world.email("taken")
    first = _client.post(
        "/api/v1/employees", json=_create_payload(world, email=email), headers=_admin(world)
    )
    assert first.status_code == 201

    second = _client.post(
        "/api/v1/employees", json=_create_payload(world, email=email), headers=_admin(world)
    )
    assert second.status_code == 409
    assert second.json()["code"] == vocabulary.EMAIL_ALREADY_IN_USE


def test_create_with_a_deactivated_employees_email_is_409(world: _World) -> None:
    """AC6: the email of a DEACTIVATED Employee is still refused `409` — the guard counts
    deactivated rows and does not leak the holder's active-ness (`G2`)."""
    email = world.email("deactivated-holder")
    world.make(vocabulary.ROLE_EMPLOYEE, is_active=False, label="deactivated-holder")

    response = _client.post(
        "/api/v1/employees", json=_create_payload(world, email=email), headers=_admin(world)
    )
    assert response.status_code == 409
    assert response.json()["code"] == vocabulary.EMAIL_ALREADY_IN_USE
    # The refusal does not disclose whether the holder is active — details carry no state.
    assert response.json()["details"] == {}


def test_patch_to_an_email_another_employee_holds_is_409(world: _World) -> None:
    """AC6: a `PATCH` changing email to one another Employee holds → `409`."""
    holder_email = world.email("holder")
    world.make(vocabulary.ROLE_EMPLOYEE, label="holder")
    target = world.make(vocabulary.ROLE_EMPLOYEE, label="patch-target")

    response = _client.patch(
        f"/api/v1/employees/{target}",
        json={"email": holder_email},
        headers=_admin(world),
    )
    assert response.status_code == 409
    assert response.json()["code"] == vocabulary.EMAIL_ALREADY_IN_USE
    # A no-op re-set of the target's OWN email is allowed (not a duplicate of another).
    own_email = _get_row(target).email
    ok = _client.patch(
        f"/api/v1/employees/{target}", json={"email": own_email}, headers=_admin(world)
    )
    assert ok.status_code == 200


# --- AC7: a manager assignment that would close a cycle is refused 400 ------------------


def test_patch_assigning_self_as_manager_is_400(world: _World) -> None:
    """AC7: assigning an Employee as their own manager → `400 REPORTING_CYCLE`, nothing persisted."""
    target = world.make(vocabulary.ROLE_MANAGER, label="self-mgr")

    response = _client.patch(
        f"/api/v1/employees/{target}",
        json={"manager_id": str(target)},
        headers=_admin(world),
    )
    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.REPORTING_CYCLE
    assert _get_row(target).manager_id is None  # unchanged


def test_patch_closing_a_two_node_cycle_is_400(world: _World) -> None:
    """AC7: with B already reporting to A, assigning A's manager = B closes A→B→A → `400`."""
    a = world.make(vocabulary.ROLE_MANAGER, label="cycle-a")
    b = world.make(vocabulary.ROLE_MANAGER, manager_id=a, label="cycle-b")  # B reports to A

    response = _client.patch(
        f"/api/v1/employees/{a}", json={"manager_id": str(b)}, headers=_admin(world)
    )
    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.REPORTING_CYCLE
    assert _get_row(a).manager_id is None  # A's manager is unchanged — nothing persisted


def test_patch_to_a_nonexistent_manager_is_404(world: _World) -> None:
    """Trap 2 sub-trap: a `manager_id` naming no Employee is `404`, before the FK can 500."""
    target = world.make(vocabulary.ROLE_EMPLOYEE, label="orphan-mgr")

    response = _client.patch(
        f"/api/v1/employees/{target}",
        json={"manager_id": str(uuid.uuid4())},
        headers=_admin(world),
    )
    assert response.status_code == 404
    assert response.json()["code"] == vocabulary.RESOURCE_NOT_FOUND


# --- AC8: deactivation is refused while an active Employee reports to them ---------------


def test_deactivate_is_refused_while_an_active_report_exists(world: _World) -> None:
    """AC8: deactivating a Manager with an ACTIVE report → `409 EMPLOYEE_HAS_DIRECT_REPORTS`,
    still active; the count names the obstruction (NFR-17)."""
    manager = world.make(vocabulary.ROLE_MANAGER, label="has-report")
    world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager, label="active-report")

    response = _client.post(
        f"/api/v1/employees/{manager}/deactivate", headers=_admin(world)
    )
    assert response.status_code == 409
    assert response.json()["code"] == vocabulary.EMPLOYEE_HAS_DIRECT_REPORTS
    assert response.json()["details"]["active_direct_reports"] == 1
    assert _get_row(manager).is_active is True  # unchanged


def test_deactivate_succeeds_when_the_only_report_is_already_deactivated(world: _World) -> None:
    """AC8: a Manager whose only report is DEACTIVATED may be deactivated — `is_active` is the
    qualifier; a deactivated report cannot be orphaned."""
    manager = world.make(vocabulary.ROLE_MANAGER, label="stale-report-mgr")
    world.make(
        vocabulary.ROLE_EMPLOYEE, manager_id=manager, is_active=False, label="stale-report"
    )

    response = _client.post(
        f"/api/v1/employees/{manager}/deactivate", headers=_admin(world)
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert _get_row(manager).is_active is False


# --- AC9: demotion below MANAGER is refused while an active Employee reports to them ------


def test_demotion_below_manager_is_refused_while_an_active_report_exists(world: _World) -> None:
    """AC9: lowering role to `EMPLOYEE` while holding an active report → `409`, role unchanged."""
    manager = world.make(vocabulary.ROLE_MANAGER, label="demote-me")
    report = world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager, label="demote-report")

    refused = _client.patch(
        f"/api/v1/employees/{manager}",
        json={"role": vocabulary.ROLE_EMPLOYEE},
        headers=_admin(world),
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == vocabulary.EMPLOYEE_HAS_DIRECT_REPORTS
    assert _get_row(manager).role == vocabulary.ROLE_MANAGER  # unchanged

    # After the report is deactivated, the same demotion succeeds (the door is the ACTIVE count).
    _client.post(f"/api/v1/employees/{report}/deactivate", headers=_admin(world))
    allowed = _client.patch(
        f"/api/v1/employees/{manager}",
        json={"role": vocabulary.ROLE_EMPLOYEE},
        headers=_admin(world),
    )
    assert allowed.status_code == 200
    assert allowed.json()["role"] == vocabulary.ROLE_EMPLOYEE


def test_promotion_to_admin_while_holding_reports_is_allowed(world: _World) -> None:
    """AC9 boundary: `MANAGER→ADMIN` is not "below MANAGER" and is NOT guarded, even with reports."""
    manager = world.make(vocabulary.ROLE_MANAGER, label="promote-me")
    world.make(vocabulary.ROLE_EMPLOYEE, manager_id=manager, label="kept-report")

    response = _client.patch(
        f"/api/v1/employees/{manager}",
        json={"role": vocabulary.ROLE_ADMIN},
        headers=_admin(world),
    )
    assert response.status_code == 200
    assert response.json()["role"] == vocabulary.ROLE_ADMIN


# --- AC11 / AC12: deactivation persists the row; no endpoint deletes --------------------


def test_deactivation_persists_the_row_and_stops_authentication(world: _World) -> None:
    """AC11: an Employee with no active report deactivates; the row persists and they can no
    longer authenticate."""
    email = world.email("will-deactivate")
    password = "still-works-until-deactivated"
    created = _client.post(
        "/api/v1/employees",
        json=_create_payload(world, email=email, password=password),
        headers=_admin(world),
    )
    employee_id = uuid.UUID(created.json()["id"])

    # They can authenticate while active…
    assert (
        _client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code
        == 200
    )

    response = _client.post(f"/api/v1/employees/{employee_id}/deactivate", headers=_admin(world))
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # …the row persists (never deleted)…
    row = _get_row(employee_id)
    assert row is not None and row.is_active is False

    # …and they can no longer authenticate (FR-04 / AC11).
    denied = _client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert denied.status_code == 401


def test_the_api_exposes_no_delete_operation_under_employees(world: _World) -> None:
    """AC12: the generated OpenAPI has no `delete` operation on any `/employees` path."""
    schema = app.openapi()
    employee_paths = {
        path: operations
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/employees")
    }
    assert employee_paths  # the routes are registered
    for operations in employee_paths.values():
        assert "delete" not in operations


# --- Cross-cutting: 401 without a token; 404 for a nonexistent id -----------------------


def test_every_endpoint_is_401_without_a_token(world: _World) -> None:
    """No token → `401 TOKEN_INVALID` on every `/employees` endpoint (the auth gate runs first)."""
    unknown = uuid.uuid4()
    cases = [
        _client.post("/api/v1/employees", json=_create_payload(world)),
        _client.get("/api/v1/employees"),
        _client.get(f"/api/v1/employees/{unknown}"),
        _client.patch(f"/api/v1/employees/{unknown}", json={"full_name": "x"}),
        _client.post(f"/api/v1/employees/{unknown}/deactivate"),
    ]
    for response in cases:
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


@pytest.mark.parametrize("method_path", ["get", "patch", "deactivate"])
def test_a_nonexistent_id_is_404(world: _World, method_path: str) -> None:
    """A GET/PATCH/deactivate of an id that names no Employee → `404 RESOURCE_NOT_FOUND`."""
    unknown = uuid.uuid4()
    if method_path == "get":
        response = _client.get(f"/api/v1/employees/{unknown}", headers=_admin(world))
    elif method_path == "patch":
        response = _client.patch(
            f"/api/v1/employees/{unknown}", json={"full_name": "x"}, headers=_admin(world)
        )
    else:
        response = _client.post(
            f"/api/v1/employees/{unknown}/deactivate", headers=_admin(world)
        )
    assert response.status_code == 404
    assert response.json()["code"] == vocabulary.RESOURCE_NOT_FOUND
