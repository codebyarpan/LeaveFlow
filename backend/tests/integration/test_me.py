"""`GET /api/v1/me` end to end, against real PostgreSQL.

Implements the test side of: AC1 (`/me` returns the caller's own profile, and never the
`password_hash` or a Leave Balance quantity), AC2 (absent token → `401 TOKEN_INVALID`),
AC3 (expired token → `401 TOKEN_INVALID`), AC4 (a tampered token fails signature
verification and its altered role is never honoured), AC5 (the actor — and the role — are
read from the database row keyed by the token's subject, not from anything the client
sent).

The single most load-bearing test here is `test_role_is_read_from_the_db_not_the_token`:
it signs a *validly-signed* token whose `role` claim disagrees with the row, and proves
`/me` reports the row's role. That is the whole of AD-14 / NFR-03 — nothing beyond `sub`
is trusted — reduced to one assertion.

There is deliberately NO test that a deactivated Employee's token is rejected: AD-14
enumerates exactly three rejection cases and that is not one of them (G4 is open). See
Story 1.3 Dev Notes, Trap 2.
"""

import base64
import datetime
import json
import uuid
import warnings
from collections.abc import Iterator

import jwt
import pytest
from sqlalchemy import Connection, delete
from sqlalchemy.orm import Session

from app.core import security
from app.core.settings import get_settings
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee

# See test_login.py: starlette's httpx-deprecation warning is not spine-governed; silence
# it at import so it does not clutter this suite.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_client = TestClient(app)


class _Actor:
    """One Employee, their department, and a freshly-signed valid token for them."""

    def __init__(
        self,
        employee_id: uuid.UUID,
        email: str,
        full_name: str,
        role: str,
        department_id: uuid.UUID,
        department_name: str,
        token: str,
    ) -> None:
        self.id = employee_id
        self.email = email
        self.full_name = full_name
        self.role = role
        self.department_id = department_id
        self.department_name = department_name
        self.token = token


@pytest.fixture
def actor(db_connection: Connection) -> Iterator[_Actor]:
    """Create a department and one active EMPLOYEE, sign a token, clean up after.

    Depends on `db_connection` only to inherit its skip-when-DB-absent behaviour; the
    writes commit through the shared engine so the app (a fresh connection per command,
    AD-3) sees them. Email and department name are unique per test (uuid) so runs never
    collide. Role is EMPLOYEE so the AC5 role-from-DB test can sign a divergent ADMIN
    claim and watch it be ignored.
    """
    suffix = uuid.uuid4().hex[:12]
    email = f"me-{suffix}@example.com"
    department_name = f"dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()  # assign department.id before the employee references it

        employee = Employee(
            department_id=department.id,
            manager_id=None,
            email=email,
            full_name="Mona Actor",
            role=vocabulary.ROLE_EMPLOYEE,
            joining_date=datetime.date(2026, 1, 1),
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.commit()

        employee_id = employee.id
        department_id = department.id

    token = security.create_token(str(employee_id), vocabulary.ROLE_EMPLOYEE)

    try:
        yield _Actor(
            employee_id,
            email,
            "Mona Actor",
            vocabulary.ROLE_EMPLOYEE,
            department_id,
            department_name,
            token,
        )
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(Employee).where(Employee.email == email))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _get_me(token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return _client.get("/api/v1/me", headers=headers)


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _tamper_role(token: str, forged_role: str) -> str:
    """Alter a token's `role` claim WITHOUT re-signing — so the signature no longer matches.

    Splits the compact JWT, rewrites the payload's `role`, re-base64url-encodes it, and
    keeps the original signature. Presenting it must fail `InvalidSignatureError` (AC4).
    """
    header, payload, signature = token.split(".")
    claims = json.loads(_b64url_decode(payload))
    claims["role"] = forged_role
    forged_payload = _b64url_encode(json.dumps(claims).encode("utf-8"))
    return f"{header}.{forged_payload}.{signature}"


def test_valid_token_returns_the_callers_own_profile(actor: _Actor) -> None:
    """AC1: 200 with exactly the six enumerated fields — no hash, no balance."""
    response = _get_me(actor.token)

    assert response.status_code == 200
    body = response.json()

    assert body["id"] == str(actor.id)
    assert body["full_name"] == actor.full_name
    assert body["email"] == actor.email
    assert body["role"] == vocabulary.ROLE_EMPLOYEE
    assert body["department"] == {"id": str(actor.department_id), "name": actor.department_name}
    assert body["joining_date"] == "2026-01-01"

    # AC1's exclusions, asserted as exclusions: exactly the six fields, and nothing that
    # discloses the hash, the reporting line, the active flag, or a balance quantity.
    assert set(body) == {"id", "full_name", "email", "role", "department", "joining_date"}
    assert "password_hash" not in body
    assert "manager_id" not in body
    assert "is_active" not in body
    for leaked in ("balance", "allocated", "taken", "pending", "remaining"):
        assert leaked not in body


def test_absent_authorization_header_is_rejected(actor: _Actor) -> None:
    """AC2: no `Authorization` header → 401 `TOKEN_INVALID`, the exact envelope."""
    response = _get_me(None)

    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.TOKEN_INVALID
    assert body["details"] == {}


def test_expired_token_is_rejected(actor: _Actor) -> None:
    """AC3 / NFR-02: a token whose `exp` has passed → 401 `TOKEN_INVALID`.

    Forged with the REAL secret so only the expiry, not the signature, is what fails —
    isolating the `ExpiredSignatureError` path `decode_token` lets propagate.
    """
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    expired = jwt.encode(
        {
            "sub": str(actor.id),
            "role": actor.role,
            "exp": now - datetime.timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = _get_me(expired)

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID


def test_tampered_token_fails_signature_and_altered_role_is_not_honoured(actor: _Actor) -> None:
    """AC4: a payload-altered token fails signature verification; the forged role never lands."""
    forged = _tamper_role(actor.token, vocabulary.ROLE_ADMIN)

    response = _get_me(forged)

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID
    # The altered role is never reflected back — the response is a rejection envelope, not
    # a profile, and it names no role at all.
    assert vocabulary.ROLE_ADMIN not in response.text


def test_role_is_read_from_the_db_not_the_token(actor: _Actor) -> None:
    """AC5 (the load-bearing one): a validly-signed ADMIN claim on an EMPLOYEE row is ignored.

    Signs a genuine, verifiable token whose `role` claim says ADMIN for an Employee whose
    row says EMPLOYEE. `/me` must report EMPLOYEE — proving the dependency trusts nothing
    beyond `sub`, and reads the role from the database (AD-14 / NFR-03).
    """
    forged_role_token = security.create_token(str(actor.id), vocabulary.ROLE_ADMIN)

    response = _get_me(forged_role_token)

    assert response.status_code == 200
    assert response.json()["role"] == vocabulary.ROLE_EMPLOYEE


def test_rejections_are_byte_identical_across_reasons(actor: _Actor) -> None:
    """AD-14 / AC5: absent, expired and tampered rejections disclose nothing distinguishing.

    One raise site in `resolve_actor` guarantees it by construction; this proves it stays
    true. Compares raw `content` (bytes), so key order or whitespace drift is caught.
    """
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    expired = jwt.encode(
        {"sub": str(actor.id), "role": actor.role, "exp": now - datetime.timedelta(hours=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    absent = _get_me(None)
    expired_response = _get_me(expired)
    tampered = _get_me(_tamper_role(actor.token, vocabulary.ROLE_ADMIN))
    garbage = _get_me("not-a-jwt")

    statuses = {absent.status_code, expired_response.status_code, tampered.status_code, garbage.status_code}
    assert statuses == {401}
    assert absent.content == expired_response.content == tampered.content == garbage.content
