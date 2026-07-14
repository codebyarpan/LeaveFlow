"""The `/api/v1/holidays` endpoints, end to end, against real PostgreSQL.

⚠️ REVISED BY STORY 2.11 — the two write endpoints' success codes CHANGED, and these assertions
were revised rather than deleted. `POST /holidays` was `201 + HolidayResponse` and is now `200 +
{holiday, recalculation}`; `DELETE /holidays/<id>` was `204` with an empty body and is now `200`
with the same summary shape. api-contracts §4.3 is binding ("these endpoints return `200` with a
summary rather than failing wholesale"), and Story 2.2's own docstring predicted this change and
assigned it to 2.11 by name. A holiday write is no longer CRUD: it recalculates every Leave Request
the change affects, and it may REFUSE a given (Employee, Leave Type) pair while the rest of the
operation commits (AD-19) — which is a fact no status code can carry and a `204` could not have
carried at all. The recalculation's OWN behaviour is tested in `test_holiday_recalculation.py`;
these tests keep proving what they always proved, at the new codes.

Implements the test side of: AC3 (an Admin `POST`s a holiday and it is returned by `GET`,
`200`; an Admin `DELETE`s it, `200`, and a subsequent `GET` no longer lists it), AC2 (the
`holiday_date` is transported as `YYYY-MM-DD`), AC7 (any authenticated role reads the list,
`200`), AC9 (the list is page-bounded and carries the `items`/`page`/`page_size`/`total`
envelope), AC6 (a non-Admin `POST`/`DELETE` is `403 ACTION_NOT_PERMITTED`, decided server-side
before any row is written or deleted), AC7-auth (no OR invalid token → `401 TOKEN_INVALID` on
all three endpoints), AC5 (a duplicate `holiday_date` → `409 HOLIDAY_DATE_IN_USE`, naming the
date, and no second row), and AC8 (a `DELETE` of a nonexistent id → `404 RESOURCE_NOT_FOUND`).

Real PostgreSQL, because the `409`-vs-500 distinction (AD-5) and the `UNIQUE (holiday_date)`
it guards are database behaviour: the duplicate-date refusal proves the pre-check AND that the
constraint stays a backstop, not a raw 500. The `callers` fixture mirrors
`test_leave_types.py` — one active Employee per role in a shared department, a signed token
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
from app.repositories.models import CompanyHoliday, Department, Employee

# Importing `app.main` runs its `CODE_TO_STATUS.update(...)`, so `HOLIDAY_DATE_IN_USE` maps to
# 409, `ACTION_NOT_PERMITTED` to 403, `RESOURCE_NOT_FOUND` to 404 and `TOKEN_INVALID` to 401
# when the app renders a refusal. Without this import the domain codes would fall through to
# the 500 default.
import app.main  # noqa: F401

# See test_leave_types.py: starlette's httpx-deprecation warning is not spine-governed.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_client = TestClient(app)


class _Callers:
    """One token per role — the holiday endpoints need no shared resource beyond auth."""

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
    department_name = f"hol-dept-{suffix}"
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
            email = f"hol-{role.lower()}-{suffix}@example.com"
            emails.append(email)
            employee = Employee(
                department_id=department_id,
                manager_id=None,
                email=email,
                full_name=f"HOL {role}",
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


def _unique_date() -> datetime.date:
    """A holiday date unlikely to collide with a concurrent run — spread across ~27 years."""
    day = uuid.uuid4().int % 9999
    return datetime.date(2000, 1, 1) + datetime.timedelta(days=day)


def _valid_body(holiday_date: datetime.date, name: str = "Test Holiday") -> dict[str, object]:
    """A well-formed create body — the `holiday_date` as the `YYYY-MM-DD` string the wire uses."""
    return {"holiday_date": holiday_date.isoformat(), "name": name}


def _delete_date(holiday_date: datetime.date) -> None:
    with Session(get_engine()) as session:
        session.execute(
            delete(CompanyHoliday).where(CompanyHoliday.holiday_date == holiday_date)
        )
        session.commit()


def _count_date(holiday_date: datetime.date) -> int:
    with Session(get_engine()) as session:
        return session.scalar(
            select(func.count())
            .select_from(CompanyHoliday)
            .where(CompanyHoliday.holiday_date == holiday_date)
        )


def _date_is_listed(token: str, holiday_date: datetime.date) -> bool:
    """Does `GET /holidays` return a holiday on this date, across all pages?"""
    wanted = holiday_date.isoformat()
    page = 1
    while True:
        response = _client.get(
            "/api/v1/holidays",
            params={"page": page, "page_size": MAX_PAGE_SIZE},
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        if any(item["holiday_date"] == wanted for item in body["items"]):
            return True
        if page * body["page_size"] >= body["total"]:
            return False
        page += 1


# --- AC3 / AC2: Admin creates a holiday, GET returns it with a YYYY-MM-DD date -----------


def test_admin_creates_a_holiday_and_it_is_returned_by_get(callers: _Callers) -> None:
    """AC3/AC2: `POST` by an Admin creates the row (200) and `GET` then lists it as YYYY-MM-DD.

    `200`, not `201` — Story 2.11 (api-contracts §4.3). The holiday now travels under a `holiday`
    key alongside the `recalculation` summary, because the write recalculates the requests it
    affects and must be able to report what it declined to touch.
    """
    holiday_date = _unique_date()
    try:
        created = _client.post(
            "/api/v1/holidays",
            json=_valid_body(holiday_date, name="Founders' Day"),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )

        assert created.status_code == 200
        envelope = created.json()
        assert set(envelope) == {"holiday", "recalculation"}

        body = envelope["holiday"]
        assert set(body) == {"id", "holiday_date", "name"}
        # AC2: transported as the calendar-date string, never a timestamp.
        assert body["holiday_date"] == holiday_date.isoformat()
        assert body["name"] == "Founders' Day"
        assert uuid.UUID(body["id"])  # a real uuid was assigned and returned

        # A holiday nobody's request covers recalculates nothing and refuses nobody — and it says
        # so honestly rather than omitting the summary (AC8's "never an unqualified success" has a
        # quiet converse: a genuinely clean run must still report its zeros).
        assert envelope["recalculation"] == {
            "requests_recalculated": 0,
            "pairs_recalculated": 0,
            "pairs_refused": [],
        }

        # It is now returned by GET (any role) — walk pages to be robust to volume.
        assert _date_is_listed(callers.tokens[vocabulary.ROLE_EMPLOYEE], holiday_date)
    finally:
        _delete_date(holiday_date)


# --- AC3: Admin deletes a holiday, and a subsequent GET no longer lists it ----------------


def test_admin_deletes_a_holiday_and_it_disappears_from_get(callers: _Callers) -> None:
    """AC3: an Admin `DELETE` removes the holiday (200 + a summary) and `GET` no longer lists it.

    `200` with a body, not `204` with none — Story 2.11. A DELETE is the path most likely to refuse
    (it makes a working day reappear, so more days are charged and a later, already-spent Leave Year
    can be driven negative), and a `204` cannot carry the summary that says so.
    """
    holiday_date = _unique_date()
    try:
        created = _client.post(
            "/api/v1/holidays",
            json=_valid_body(holiday_date),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )
        assert created.status_code == 200
        holiday_id = created.json()["holiday"]["id"]

        deleted = _client.delete(
            f"/api/v1/holidays/{holiday_id}",
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )
        assert deleted.status_code == 200
        envelope = deleted.json()
        # The deleted holiday is NAMED in the response — the row is gone, but the answer still says
        # which one went, which a `204` never could.
        assert envelope["holiday"]["id"] == holiday_id
        assert envelope["holiday"]["holiday_date"] == holiday_date.isoformat()
        assert envelope["recalculation"]["pairs_refused"] == []

        # It is gone from the list, and gone from the table.
        assert not _date_is_listed(callers.tokens[vocabulary.ROLE_ADMIN], holiday_date)
        assert _count_date(holiday_date) == 0
    finally:
        _delete_date(holiday_date)


# --- AC8: a DELETE of a nonexistent id is 404, never a silent success or a 500 ------------


def test_delete_of_a_nonexistent_id_is_404(callers: _Callers) -> None:
    """AC8: `DELETE /holidays/<random uuid>` is `404 RESOURCE_NOT_FOUND`."""
    response = _client.delete(
        f"/api/v1/holidays/{uuid.uuid4()}",
        headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
    )

    assert response.status_code == 404
    assert response.json()["code"] == vocabulary.RESOURCE_NOT_FOUND


# --- AC7: any authenticated role reads the list ------------------------------------------


@pytest.mark.parametrize(
    "role",
    [vocabulary.ROLE_ADMIN, vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE],
)
def test_any_authenticated_role_reads_the_holiday_list(
    callers: _Callers, role: str
) -> None:
    """AC7: every role `GET`s the list with `200` and the pagination envelope."""
    response = _client.get("/api/v1/holidays", headers=_auth(callers.tokens[role]))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}


# --- AC9: the list is page-bounded -------------------------------------------------------


def test_a_page_size_above_the_maximum_is_clamped_end_to_end(
    callers: _Callers, db_connection: Connection
) -> None:
    """AC9: with more than `MAX_PAGE_SIZE` rows, a larger `page_size` returns exactly the max.

    Proves the clamp through the real `Page` envelope. Seeds `MAX_PAGE_SIZE + 1` throwaway
    holidays (distinct dates in a reserved far-future window) so the table certainly holds
    more than one page, whatever else exists.
    """
    base = datetime.date(2200, 1, 1)
    seeded = [base + datetime.timedelta(days=i) for i in range(MAX_PAGE_SIZE + 1)]
    with Session(get_engine()) as session:
        session.add_all(
            [
                CompanyHoliday(holiday_date=d, name=f"clamp {i}")
                for i, d in enumerate(seeded)
            ]
        )
        session.commit()

    try:
        response = _client.get(
            "/api/v1/holidays",
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
            session.execute(
                delete(CompanyHoliday).where(CompanyHoliday.holiday_date.in_(seeded))
            )
            session.commit()


# --- AC6: a non-Admin write is 403, server-side, before any row is written or deleted -----


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_a_non_admin_cannot_create(callers: _Callers, denied_role: str) -> None:
    """AC6: a Manager or Employee `POST` is `403 ACTION_NOT_PERMITTED`, and nothing is created."""
    holiday_date = _unique_date()
    response = _client.post(
        "/api/v1/holidays",
        json=_valid_body(holiday_date),
        headers=_auth(callers.tokens[denied_role]),
    )

    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
    # The refusal happened before any write: no row on that date exists.
    assert _count_date(holiday_date) == 0


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE]
)
def test_a_non_admin_cannot_delete(callers: _Callers, denied_role: str) -> None:
    """AC6: a non-Admin `DELETE` is `403 ACTION_NOT_PERMITTED`, and the row still exists.

    An Admin seeds the holiday first; the non-Admin's delete is refused before any row is
    removed, so the row is still present afterwards.
    """
    holiday_date = _unique_date()
    try:
        created = _client.post(
            "/api/v1/holidays",
            json=_valid_body(holiday_date),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )
        assert created.status_code == 200
        holiday_id = created.json()["holiday"]["id"]

        response = _client.delete(
            f"/api/v1/holidays/{holiday_id}",
            headers=_auth(callers.tokens[denied_role]),
        )

        assert response.status_code == 403
        assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
        # The refusal happened before any delete: the row is still present.
        assert _count_date(holiday_date) == 1
    finally:
        _delete_date(holiday_date)


# --- AC7-auth: no OR invalid token is 401 on all three endpoints --------------------------


def test_all_endpoints_are_401_without_a_valid_token() -> None:
    """AC7: `GET`/`POST`/`DELETE /holidays` answer `401 TOKEN_INVALID` to no OR an invalid token.

    Both branches are exercised on all three endpoints: an absent `Authorization` header AND a
    present-but-unverifiable bearer token (garbage that is not a signed JWT). Both resolve to
    the same `401 TOKEN_INVALID` — the endpoints never leak a different status for a malformed
    credential (the 2.1 code-review lesson: cover both the absent and invalid paths).
    """
    a_date = _unique_date()
    an_id = uuid.uuid4()
    cases = [
        # Absent token.
        _client.get("/api/v1/holidays"),
        _client.post("/api/v1/holidays", json=_valid_body(a_date)),
        _client.delete(f"/api/v1/holidays/{an_id}"),
        # Present-but-invalid token.
        _client.get("/api/v1/holidays", headers=_auth("not-a-real-token")),
        _client.post(
            "/api/v1/holidays",
            json=_valid_body(a_date),
            headers=_auth("not-a-real-token"),
        ),
        _client.delete(
            f"/api/v1/holidays/{an_id}", headers=_auth("not-a-real-token")
        ),
    ]

    for response in cases:
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- AC5: a duplicate date is a typed 409, not a raw 500, and writes no second row --------


def test_a_duplicate_holiday_date_is_409_and_no_second_row(callers: _Callers) -> None:
    """AC5: a second `POST` on an existing `holiday_date` is `409 HOLIDAY_DATE_IN_USE`.

    The `UNIQUE (holiday_date)` constraint stays a backstop (AD-5): the refusal is the typed
    409 the service raises, not a raw `IntegrityError`/500; `details.holiday_date` names the
    date; and exactly one row falls on that date.
    """
    holiday_date = _unique_date()
    try:
        first = _client.post(
            "/api/v1/holidays",
            json=_valid_body(holiday_date, name="First name"),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )
        assert first.status_code == 200

        second = _client.post(
            "/api/v1/holidays",
            json=_valid_body(holiday_date, name="A different name, same date"),
            headers=_auth(callers.tokens[vocabulary.ROLE_ADMIN]),
        )

        assert second.status_code == 409
        body = second.json()
        assert body["code"] == vocabulary.HOLIDAY_DATE_IN_USE
        assert body["details"]["holiday_date"] == holiday_date.isoformat()
        # Exactly one row exists — the collision did not write a second.
        assert _count_date(holiday_date) == 1
    finally:
        _delete_date(holiday_date)
