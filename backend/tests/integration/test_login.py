"""`POST /api/v1/auth/login` end to end, against real PostgreSQL.

Implements the test side of: AC3 (login succeeds, returns a JWT whose claims identify
subject and role, with an hours-lifetime `exp`), AC4 (failure discloses nothing — the
unknown-email and wrong-password responses are byte-identical), AC7 (a deactivated
Employee is refused identically), AC8 (the `{code, message, details}` envelope, exercised
for real on the first endpoint capable of a non-2xx response).

Runs against the same database the app's service opens its own connection to. The
fixture writes its rows through a committed session, so the app — which opens a fresh
connection per command (AD-3) — sees them under READ COMMITTED.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, text
from sqlalchemy.orm import Session

from app.core import security
from app.core.settings import get_settings
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee

# starlette 1.3.1 deprecates httpx in TestClient in favour of httpx2. Still a warning,
# still not spine-governed (Story 1.1 left it standing); silence it at import so it does
# not clutter this suite's output.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_client = TestClient(app)


class _Fixtures:
    """The rows one login test needs: an active Employee and a deactivated one."""

    def __init__(self, active_email: str, inactive_email: str) -> None:
        self.active_email = active_email
        self.inactive_email = inactive_email


@pytest.fixture
def users(db_connection: Connection) -> Iterator[_Fixtures]:
    """Create a department, an active Employee and a deactivated one; delete them after.

    Depends on `db_connection` only to inherit its skip-when-DB-absent behaviour; the
    writes go through a committed session on the shared engine so the app sees them.
    Emails are unique per test (uuid) so parallel or repeated runs never collide.
    """
    suffix = uuid.uuid4().hex[:12]
    active_email = f"active-{suffix}@example.com"
    inactive_email = f"inactive-{suffix}@example.com"
    department_name = f"dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()  # assign department.id before the employees reference it

        session.add_all(
            [
                Employee(
                    department_id=department.id,
                    manager_id=None,
                    email=active_email,
                    full_name="Active Person",
                    role=vocabulary.ROLE_EMPLOYEE,
                    joining_date=datetime.date(2026, 1, 1),
                    is_active=True,
                    password_hash=hashed,
                ),
                Employee(
                    department_id=department.id,
                    manager_id=None,
                    email=inactive_email,
                    full_name="Inactive Person",
                    role=vocabulary.ROLE_EMPLOYEE,
                    joining_date=datetime.date(2026, 1, 1),
                    is_active=False,
                    password_hash=hashed,
                ),
            ]
        )
        session.commit()

    try:
        yield _Fixtures(active_email, inactive_email)
    finally:
        with Session(get_engine()) as session:
            session.execute(
                delete(Employee).where(Employee.email.in_([active_email, inactive_email]))
            )
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _login(email: str, password: str):
    return _client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_correct_credentials_return_200_and_a_token(users: _Fixtures) -> None:
    """AC3: correct credentials → 200, a bearer token, claims for subject and role."""
    response = _login(users.active_email, _KNOWN_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"

    claims = security.decode_token(body["access_token"])
    assert claims["role"] == vocabulary.ROLE_EMPLOYEE
    # `sub` is the employee id as a string (PyJWT validates the claim type).
    assert isinstance(claims["sub"], str) and claims["sub"]


def test_token_lifetime_is_measured_in_hours_not_days(users: _Fixtures) -> None:
    """AC3 / NFR-02: `exp` lies within `jwt_expire_hours` of now, not days out."""
    response = _login(users.active_email, _KNOWN_PASSWORD)
    claims = security.decode_token(response.json()["access_token"])

    now = datetime.datetime.now(datetime.timezone.utc)
    exp = datetime.datetime.fromtimestamp(claims["exp"], tz=datetime.timezone.utc)
    lifetime = exp - now

    expected = datetime.timedelta(hours=get_settings().jwt_expire_hours)
    # Within a minute of the configured hours lifetime — and comfortably under a day,
    # which is the property NFR-02 actually cares about.
    assert abs(lifetime - expected) < datetime.timedelta(minutes=1)
    assert lifetime < datetime.timedelta(days=1)


def test_unknown_email_and_wrong_password_are_byte_identical(users: _Fixtures) -> None:
    """AC4: the two failures are indistinguishable — same status, byte-identical body.

    Compares `response.content` (raw bytes), not parsed JSON: key order or whitespace
    drift is exactly what "byte-identical" exists to catch. Holds by construction (one
    raise site, one handler); this test proves it stays true.
    """
    unknown = _login(f"nobody-{uuid.uuid4().hex}@example.com", "whatever")
    wrong = _login(users.active_email, "not-the-password")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.content == wrong.content


def test_deactivated_employee_is_refused_identically(users: _Fixtures) -> None:
    """AC7: a deactivated Employee with correct credentials gets the same refusal."""
    deactivated = _login(users.inactive_email, _KNOWN_PASSWORD)
    wrong = _login(users.active_email, "not-the-password")

    assert deactivated.status_code == 401
    assert deactivated.content == wrong.content


def test_the_failure_envelope_shape_is_exact(users: _Fixtures) -> None:
    """AC8: the 401 body is exactly `{code, message, details}` with code `AUTH_FAILED`."""
    response = _login(users.active_email, "not-the-password")

    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.AUTH_FAILED
    assert body["details"] == {}
    # The message discloses nothing about whether the account exists.
    assert isinstance(body["message"], str) and body["message"]
