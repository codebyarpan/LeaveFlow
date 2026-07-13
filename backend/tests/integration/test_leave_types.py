"""The `/api/v1/leave-types` endpoints, end to end, against real PostgreSQL.

Implements the test side of: AC3/SM-5 (an Admin `POST`s a fourth Leave Type and it is
returned by `GET`, with no schema migration), AC4 (any authenticated role reads the list,
`200`), AC9 (the list is page-bounded and carries the `items`/`page`/`page_size`/`total`
envelope), AC7 (a non-Admin `POST` is `403 ACTION_NOT_PERMITTED`, decided server-side before
any row is written), AC8 (no token → `401 TOKEN_INVALID` on both endpoints), AC6 (a duplicate
`code` → `409 LEAVE_TYPE_CODE_IN_USE`, and no second row), and AC1's nullable column (a
created type carries `carry_forward_cap = null` when omitted).

Real PostgreSQL, because the `409`-vs-500 distinction (AD-5) and the `UNIQUE (code)` it
guards are database behaviour: the duplicate-`code` refusal proves the pre-check AND that the
constraint stays a backstop, not a raw 500. The `callers` fixture mirrors
`test_departments.py` — one active Employee per role in a shared department, a signed token
for each — because the role gate reads the actor's role from the DB-resolved row (AD-14).
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, func, select
from sqlalchemy.orm import Session

from app.api.v1.pagination import MAX_PAGE_SIZE
from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee, LeaveType

# Importing `app.main` runs its `CODE_TO_STATUS.update(...)`, so `LEAVE_TYPE_CODE_IN_USE`
# maps to 409, `ACTION_NOT_PERMITTED` to 403 and `TOKEN_INVALID` to 401 when the app renders
# a refusal. Without this import the domain codes would fall through to the 500 default.
import app.main  # noqa: F401

# See test_departments.py: starlette's httpx-deprecation warning is not spine-governed.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_client = TestClient(app)


class _Callers:
    """One token per role — the leave-type endpoints need no shared resource beyond auth."""

    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = tokens


@pytest.fixture
def callers(db_connection: Connection) -> Iterator[_Callers]:
    """Create one active Employee per role in a throwaway department; sign a token for each.

    Depends on `db_connection` to inherit its skip-when-DB-absent behaviour; writes commit
    through the shared engine so the app (a fresh connection per command, AD-3) sees them.
    Email and department name are unique per run (uuid) so runs never collide.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"lt-dept-{suffix}"
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
            email = f"lt-{role.lower()}-{suffix}@example.com"
            emails.append(email)
            employee = Employee(
                department_id=department_id,
                manager_id=None,
                email=email,
                full_name=f"LT {role}",
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
        yield _Callers(tokens)
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(Employee).where(Employee.email.in_(emails)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _valid_body(code: str) -> dict[str, object]:
    """A well-formed create body for `code` — an EL-shaped type that carries forward."""
    return {
        "code": code,
        "name": f"Type {code}",
        "annual_entitlement": 15,
        "carries_forward": True,
        "carry_forward_cap": 20,
        "requires_supporting_document": False,
    }


def _delete_code(code: str) -> None:
    with Session(get_engine()) as session:
        session.execute(delete(LeaveType).where(LeaveType.code == code))
        session.commit()


def _count_code(code: str) -> int:
    with Session(get_engine()) as session:
        return session.scalar(
            select(func.count()).select_from(LeaveType).where(LeaveType.code == code)
        )


# --- AC3 / SM-5: an Admin creates a fourth Leave Type, returned by GET, no migration ----


def test_admin_creates_a_leave_type_and_it_is_returned_by_get(callers: _Callers) -> None:
    """AC3/SM-5: `POST` by an Admin creates the row (201) and `GET` then lists it.

    A fourth Leave Type is added through the API alone — no schema migration ran — which is
    exactly the SM-5 acceptance.
    """
    code = f"T{uuid.uuid4().hex[:6].upper()}"
    try:
        created = _client.post(
            "/api/v1/leave-types",
            json=_valid_body(code),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )

        assert created.status_code == 201
        body = created.json()
        assert set(body) == {
            "id",
            "code",
            "name",
            "annual_entitlement",
            "carries_forward",
            "carry_forward_cap",
            "requires_supporting_document",
        }
        assert body["code"] == code
        assert body["annual_entitlement"] == 15
        assert body["carries_forward"] is True
        assert body["carry_forward_cap"] == 20
        assert body["requires_supporting_document"] is False
        assert uuid.UUID(body["id"])  # a real uuid was assigned and returned

        # It is now returned by GET (any role) — walk pages to be robust to seed volume.
        assert _code_is_listed(callers.tokens[vocabulary.ROLE_EMPLOYEE], code)
    finally:
        _delete_code(code)


def _code_is_listed(token: str, code: str) -> bool:
    """Does `GET /leave-types` return a type with this `code`, across all pages?"""
    page = 1
    while True:
        response = _client.get(
            "/api/v1/leave-types",
            params={"page": page, "page_size": MAX_PAGE_SIZE},
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        if any(item["code"] == code for item in body["items"]):
            return True
        if page * body["page_size"] >= body["total"]:
            return False
        page += 1


def test_created_type_carries_null_cap_when_omitted(callers: _Callers) -> None:
    """AC1 (nullable): omitting `carry_forward_cap` stores and returns `null`, not 0.

    A non-carrying type has no meaningful cap (ERD §6); the column is genuinely nullable.
    """
    code = f"N{uuid.uuid4().hex[:6].upper()}"
    try:
        response = _client.post(
            "/api/v1/leave-types",
            json={
                "code": code,
                "name": "No carry",
                "annual_entitlement": 5,
                "carries_forward": False,
                "requires_supporting_document": False,
            },
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )

        assert response.status_code == 201
        assert response.json()["carry_forward_cap"] is None
        # And it is null in the row, not coerced to 0.
        with Session(get_engine()) as session:
            row = session.scalar(select(LeaveType).where(LeaveType.code == code))
            assert row is not None
            assert row.carry_forward_cap is None
    finally:
        _delete_code(code)


# --- AC4: any authenticated role reads the list ----------------------------------------


@pytest.mark.parametrize(
    "role",
    [vocabulary.ROLE_ADMIN, vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE],
)
def test_any_authenticated_role_reads_the_leave_type_list(
    callers: _Callers, role: str
) -> None:
    """AC4: every role `GET`s the list with `200` and the pagination envelope."""
    response = _client.get("/api/v1/leave-types", headers=_auth(callers.tokens[role]))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}


# --- AC9: the list is page-bounded -----------------------------------------------------


def test_a_page_size_above_the_maximum_is_clamped_end_to_end(
    callers: _Callers, db_connection: Connection
) -> None:
    """AC9: with more than `MAX_PAGE_SIZE` rows, a larger `page_size` returns exactly the max.

    Proves the clamp through the real `Page` envelope. Seeds `MAX_PAGE_SIZE + 1` throwaway
    types so the table certainly holds more than one page, whatever else exists.
    """
    prefix = f"P{uuid.uuid4().hex[:5].upper()}"
    with Session(get_engine()) as session:
        session.add_all(
            [
                LeaveType(
                    code=f"{prefix}{i:03d}",
                    name=f"page {i}",
                    annual_entitlement=1,
                    carries_forward=False,
                    carry_forward_cap=None,
                    requires_supporting_document=False,
                )
                for i in range(MAX_PAGE_SIZE + 1)
            ]
        )
        session.commit()

    try:
        response = _client.get(
            "/api/v1/leave-types",
            params={"page": 1, "page_size": MAX_PAGE_SIZE + 500},
            headers=_auth(callers.tokens[vocabulary.ROLE_EMPLOYEE]),
        )

        assert response.status_code == 200
        body = response.json()
        # The requested 600 was carried down to the server maximum, not rejected (AC9).
        assert body["page_size"] == MAX_PAGE_SIZE
        assert len(body["items"]) == MAX_PAGE_SIZE
        assert body["total"] >= MAX_PAGE_SIZE + 1
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(LeaveType).where(LeaveType.code.like(f"{prefix}%")))
            session.commit()


# --- AC7: a non-Admin write is 403, server-side, before any row is written -------------


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_a_non_admin_cannot_create(callers: _Callers, denied_role: str) -> None:
    """AC7: a Manager or Employee `POST` is `403 ACTION_NOT_PERMITTED`, and nothing is created."""
    code = f"D{uuid.uuid4().hex[:6].upper()}"
    response = _client.post(
        "/api/v1/leave-types",
        json=_valid_body(code),
        headers=_auth(callers.tokens[denied_role]),
    )

    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
    # The refusal happened before any write: no row by that code exists.
    assert _count_code(code) == 0


# --- AC8: no token is 401 on both endpoints --------------------------------------------


def test_both_endpoints_are_401_without_a_token() -> None:
    """AC8: `GET`/`POST /leave-types` answer `401 TOKEN_INVALID` to no OR an invalid token.

    The AC wording is "no/**invalid** token", so both branches are exercised: an absent
    `Authorization` header AND a present-but-unverifiable bearer token (garbage that is not a
    signed JWT). Both resolve to the same `401 TOKEN_INVALID` — the endpoints never leak a
    different status for a malformed credential.
    """
    cases = [
        _client.get("/api/v1/leave-types"),
        _client.post("/api/v1/leave-types", json=_valid_body("X0")),
        _client.get("/api/v1/leave-types", headers=_auth("not-a-real-token")),
        _client.post(
            "/api/v1/leave-types",
            json=_valid_body("X1"),
            headers=_auth("not-a-real-token"),
        ),
    ]

    for response in cases:
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- AC6: a duplicate code is a typed 409, not a raw 500, and writes no second row ------


def test_a_duplicate_code_is_409_and_no_second_row(callers: _Callers) -> None:
    """AC6: a second `POST` with an existing `code` is `409 LEAVE_TYPE_CODE_IN_USE`.

    The `UNIQUE (code)` constraint stays a backstop (AD-5): the refusal is the typed 409 the
    service raises, not a raw `IntegrityError`/500, and exactly one row carries the `code`.
    """
    code = f"U{uuid.uuid4().hex[:6].upper()}"
    try:
        first = _client.post(
            "/api/v1/leave-types",
            json=_valid_body(code),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )
        assert first.status_code == 201

        second = _client.post(
            "/api/v1/leave-types",
            json=_valid_body(code) | {"name": "A different name, same code"},
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )

        assert second.status_code == 409
        body = second.json()
        assert body["code"] == vocabulary.LEAVE_TYPE_CODE_IN_USE
        assert body["details"]["code"] == code
        # Exactly one row exists — the collision did not write a second.
        assert _count_code(code) == 1
    finally:
        _delete_code(code)
