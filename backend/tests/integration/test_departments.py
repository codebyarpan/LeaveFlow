"""The `/api/v1/departments` endpoints, end to end, against real PostgreSQL.

Implements the test side of: AC1 (an Admin creates a Department and it is returned), AC2
(any authenticated role reads the list, `200`), AC3 (the list is page-bounded and carries
the `items`/`page`/`page_size`/`total` envelope), AC4 (a non-Admin is `403
ACTION_NOT_PERMITTED` on every write, decided server-side before any row changes), AC5 (a
non-empty Department cannot be deleted — `409 DEPARTMENT_NOT_EMPTY`, and the row survives),
AC6 (an empty Department is removed), AC7 (no token → `401` on every endpoint), and Trap 4
(a `PATCH`/`DELETE` of a nonexistent id → `404 RESOURCE_NOT_FOUND`).

Real PostgreSQL, because the `409`-vs-500 distinction (AD-5) and the FK RESTRICT it guards
are database behaviour: a SQLite swap would prove nothing about the emptiness gate. The
`callers` fixture mirrors `test_role_gate.py` — one active Employee per role in a shared
department, a signed token for each — because the role gate reads the actor's role from the
DB-resolved row (AD-14), so the token alone is never trusted.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, select
from sqlalchemy.orm import Session

from app.api.v1.pagination import MAX_PAGE_SIZE
from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee

# Importing `app.main` runs its `CODE_TO_STATUS.update(...)`, so `DEPARTMENT_NOT_EMPTY` maps
# to 409, `ACTION_NOT_PERMITTED` to 403 and `RESOURCE_NOT_FOUND` to 404 when the app renders
# a refusal. Without this import the codes would fall through to the 500 default.
import app.main  # noqa: F401

# See test_me.py: starlette's httpx-deprecation warning is not spine-governed; silence it at
# import so it does not clutter this suite.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_client = TestClient(app)


class _Callers:
    """One token per role, and the shared department they belong to (for the AC5 delete)."""

    def __init__(
        self,
        tokens: dict[str, str],
        department_id: uuid.UUID,
        department_name: str,
    ) -> None:
        self.tokens = tokens
        self.department_id = department_id
        self.department_name = department_name


@pytest.fixture
def callers(db_connection: Connection) -> Iterator[_Callers]:
    """Create one active Employee per role in a shared department; sign a token for each.

    Depends on `db_connection` to inherit its skip-when-DB-absent behaviour; writes commit
    through the shared engine so the app (a fresh connection per command, AD-3) sees them.
    Email and department name are unique per run (uuid) so runs never collide. The shared
    department has three assigned Employees, which is exactly what AC5's non-empty delete
    needs.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)
    emails: list[str] = []

    tokens: dict[str, str] = {}
    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
        department_id = department.id

        made: dict[str, uuid.UUID] = {}
        for role in (
            vocabulary.ROLE_ADMIN,
            vocabulary.ROLE_MANAGER,
            vocabulary.ROLE_EMPLOYEE,
        ):
            email = f"dept-{role.lower()}-{suffix}@example.com"
            emails.append(email)
            employee = Employee(
                department_id=department_id,
                manager_id=None,
                email=email,
                full_name=f"Dept {role}",
                role=role,
                joining_date=datetime.date(2026, 1, 1),
                is_active=True,
                password_hash=hashed,
            )
            session.add(employee)
            session.flush()
            made[role] = employee.id
        session.commit()

    for role, employee_id in made.items():
        tokens[role] = security.create_token(str(employee_id), role)

    try:
        yield _Callers(tokens, department_id, department_name)
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(Employee).where(Employee.email.in_(emails)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


@pytest.fixture
def empty_department(db_connection: Connection) -> Iterator[uuid.UUID]:
    """Create a Department with no assigned Employees, for the AC6 delete; clean up after.

    The teardown deletes it only if the test did not (an empty department is deletable
    directly), so a passing AC6 test and a failing one both leave the table clean.
    """
    name = f"empty-{uuid.uuid4().hex[:12]}"
    with Session(get_engine()) as session:
        department = Department(name=name)
        session.add(department)
        session.commit()
        department_id = department.id

    try:
        yield department_id
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(Department).where(Department.id == department_id))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _department_exists(department_id: uuid.UUID) -> bool:
    with Session(get_engine()) as session:
        return session.get(Department, department_id) is not None


# --- AC1: an Admin creates a Department ------------------------------------------------


def test_admin_creates_a_department_and_it_is_returned(callers: _Callers) -> None:
    """AC1: `POST /departments` by an Admin creates the row and returns `{id, name}`."""
    name = f"new-{uuid.uuid4().hex[:12]}"

    response = _client.post(
        "/api/v1/departments",
        json={"name": name},
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name"}
    assert body["name"] == name
    assert uuid.UUID(body["id"])  # a real uuid was assigned and returned

    # Clean up the row this test created (it is empty, so a direct delete is fine).
    with Session(get_engine()) as session:
        session.execute(delete(Department).where(Department.id == uuid.UUID(body["id"])))
        session.commit()


# --- AC2 / AC3: any role reads a page-bounded list -------------------------------------


@pytest.mark.parametrize(
    "role",
    [vocabulary.ROLE_ADMIN, vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE],
)
def test_any_authenticated_role_reads_the_department_list(
    callers: _Callers, role: str
) -> None:
    """AC2: every role `GET`s the list with `200` and the pagination envelope."""
    response = _client.get("/api/v1/departments", headers=_auth(callers.tokens[role]))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    # The shared fixture department is one of the rows any role can see.
    assert any(item["id"] == str(callers.department_id) for item in body["items"]) or (
        body["total"] > body["page_size"]  # or it is simply on a later page
    )


def test_a_page_size_above_the_maximum_is_clamped_end_to_end(
    callers: _Callers, db_connection: Connection
) -> None:
    """AC3: with more than `MAX_PAGE_SIZE` rows, a larger `page_size` returns exactly the max.

    Proves the clamp through the real `Page` envelope (the DB-free `test_pagination.py`
    proves the arithmetic). Seeds `MAX_PAGE_SIZE + 1` empty departments so the table
    certainly holds more than one page, whatever else exists.
    """
    prefix = f"page-{uuid.uuid4().hex[:12]}"
    with Session(get_engine()) as session:
        session.add_all(
            [Department(name=f"{prefix}-{i:03d}") for i in range(MAX_PAGE_SIZE + 1)]
        )
        session.commit()

    try:
        response = _client.get(
            "/api/v1/departments",
            params={"page": 1, "page_size": MAX_PAGE_SIZE + 500},
            headers=_auth(callers.tokens[vocabulary.ROLE_EMPLOYEE]),
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "page", "page_size", "total"}
        # The requested 600 was carried down to the server maximum, not rejected (AC3).
        assert body["page_size"] == MAX_PAGE_SIZE
        assert len(body["items"]) == MAX_PAGE_SIZE
        assert body["total"] >= MAX_PAGE_SIZE + 1
    finally:
        with Session(get_engine()) as session:
            session.execute(
                delete(Department).where(Department.name.like(f"{prefix}-%"))
            )
            session.commit()


# --- AC4: a non-Admin is refused every write, server-side ------------------------------


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_a_non_admin_cannot_create(callers: _Callers, denied_role: str) -> None:
    """AC4: a Manager or Employee `POST` is `403 ACTION_NOT_PERMITTED`, and nothing is created."""
    name = f"denied-{uuid.uuid4().hex[:12]}"

    response = _client.post(
        "/api/v1/departments",
        json={"name": name},
        headers=_auth(callers.tokens[denied_role]),
    )

    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
    # The refusal happened before any write: no row by that name exists.
    with Session(get_engine()) as session:
        assert session.scalar(select(Department).where(Department.name == name)) is None


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_a_non_admin_cannot_rename(callers: _Callers, denied_role: str) -> None:
    """AC4: a Manager or Employee `PATCH` is `403`, and the department keeps its name."""
    response = _client.patch(
        f"/api/v1/departments/{callers.department_id}",
        json={"name": "renamed-by-a-non-admin"},
        headers=_auth(callers.tokens[denied_role]),
    )

    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
    with Session(get_engine()) as session:
        department = session.get(Department, callers.department_id)
        assert department is not None
        assert department.name == callers.department_name  # unchanged


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_a_non_admin_cannot_delete(callers: _Callers, denied_role: str) -> None:
    """AC4: a Manager or Employee `DELETE` is `403`, and the department survives."""
    response = _client.delete(
        f"/api/v1/departments/{callers.department_id}",
        headers=_auth(callers.tokens[denied_role]),
    )

    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
    assert _department_exists(callers.department_id)


# --- AC5 / AC6: the emptiness gate -----------------------------------------------------


def test_a_non_empty_department_cannot_be_deleted(callers: _Callers) -> None:
    """AC5: deleting a Department that still has Employees is `409 DEPARTMENT_NOT_EMPTY`.

    The shared fixture department holds three Employees. The refusal names the obstruction
    with a count (NFR-17), and the row is unchanged — the `409` gate fired, not the FK's 500.
    """
    response = _client.delete(
        f"/api/v1/departments/{callers.department_id}",
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == vocabulary.DEPARTMENT_NOT_EMPTY
    # NFR-17: the refusal names the obstruction with a number.
    assert body["details"]["employee_count"] == 3
    assert _department_exists(callers.department_id)


def test_an_empty_department_is_removed(
    callers: _Callers, empty_department: uuid.UUID
) -> None:
    """AC6: an Admin deletes a Department with no assigned Employees; it returns 204 and is gone."""
    response = _client.delete(
        f"/api/v1/departments/{empty_department}",
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 204
    assert response.content == b""  # 204 carries no body
    assert not _department_exists(empty_department)


def test_an_admin_can_rename_a_department(callers: _Callers) -> None:
    """The happy PATCH path: an Admin renames the fixture department and reads the new name back."""
    new_name = f"renamed-{uuid.uuid4().hex[:12]}"

    response = _client.patch(
        f"/api/v1/departments/{callers.department_id}",
        json={"name": new_name},
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(callers.department_id)
    assert body["name"] == new_name
    with Session(get_engine()) as session:
        assert session.get(Department, callers.department_id).name == new_name


# --- AC7: no token is 401 on every endpoint --------------------------------------------


def test_every_endpoint_is_401_without_a_token(callers: _Callers) -> None:
    """AC7: each `/departments` endpoint answers `401 TOKEN_INVALID` to an absent token."""
    unknown_id = uuid.uuid4()
    cases = [
        _client.get("/api/v1/departments"),
        _client.post("/api/v1/departments", json={"name": "x"}),
        _client.patch(f"/api/v1/departments/{unknown_id}", json={"name": "x"}),
        _client.delete(f"/api/v1/departments/{unknown_id}"),
    ]

    for response in cases:
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- Trap 4: a nonexistent id is 404, not 500 or a silent success ----------------------


def test_patch_of_a_nonexistent_id_is_404(callers: _Callers) -> None:
    """Trap 4: `PATCH` of an id that names no row → `404 RESOURCE_NOT_FOUND`."""
    response = _client.patch(
        f"/api/v1/departments/{uuid.uuid4()}",
        json={"name": "nowhere"},
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 404
    assert response.json()["code"] == vocabulary.RESOURCE_NOT_FOUND


def test_delete_of_a_nonexistent_id_is_404(callers: _Callers) -> None:
    """Trap 4: `DELETE` of an id that names no row → `404 RESOURCE_NOT_FOUND`."""
    response = _client.delete(
        f"/api/v1/departments/{uuid.uuid4()}",
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 404
    assert response.json()["code"] == vocabulary.RESOURCE_NOT_FOUND
