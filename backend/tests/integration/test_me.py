"""`GET /api/v1/me` and `PATCH /api/v1/me` end to end, against real PostgreSQL.

Implements the test side of Story 1.3's read: AC1 (`/me` returns the caller's own profile,
and never the `password_hash` or a Leave Balance quantity), AC2 (absent token → `401
TOKEN_INVALID`), AC3 (expired token → `401 TOKEN_INVALID`), AC4 (a tampered token fails
signature verification and its altered role is never honoured), AC5 (the actor — and the
role — are read from the database row keyed by the token's subject, not from anything the
client sent).

--- And Story 1.8's write (the `PATCH` side, below the read's tests) ---

`PATCH /me` accepts exactly `full_name` and refuses every other field with `400
FORBIDDEN_FIELD` (`G5`). The tests here cover: the happy rename (AC1), each forbidden field
refused with the exact envelope and nothing persisted (AC2/AC3), `full_name` alongside a
forbidden field still refused (AC2), the write touching only the caller's own row (AC4),
and two routing assertions — no `/me/<id>` cross-edit route (AC4) and no `/me` route that
accepts a `password` field (AC6, a "no new endpoint" assertion). Email stays Admin-only
(AC5): `PATCH /me` never accepts it, which the forbidden-field test proves.

--- And the code-review addition (2026-07-13): the `full_name` value is validated ---

A present-but-unusable `full_name` (`null`, a non-string, or empty/whitespace-only) is
refused with `400 INVALID_NAME` — the exact envelope, nothing persisted — rather than
leaking a bare Pydantic `422` (wrong type) or a NOT NULL `500` (`null`), either of which
would break NFR-17. An accepted value is `strip()`ed before it is stored.

The single most load-bearing read test is `test_role_is_read_from_the_db_not_the_token`:
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
from collections.abc import Callable, Iterator

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


def _provision_actor(full_name: str) -> tuple[_Actor, Callable[[], None]]:
    """Create a department and one active EMPLOYEE, sign a token; return it and its teardown.

    The writes commit through the shared engine so the app (a fresh connection per command,
    AD-3) sees them. Email and department name are unique per call (uuid) so concurrent
    provisions — the `actor` and `second_actor` fixtures, for AC4 — never collide. Role is
    EMPLOYEE so the AC5 role-from-DB test can sign a divergent ADMIN claim and watch it be
    ignored. The returned teardown deletes both rows; the fixture calls it in a `finally`.
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
            full_name=full_name,
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
    provisioned = _Actor(
        employee_id,
        email,
        full_name,
        vocabulary.ROLE_EMPLOYEE,
        department_id,
        department_name,
        token,
    )

    def teardown() -> None:
        with Session(get_engine()) as session:
            session.execute(delete(Employee).where(Employee.email == email))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()

    return provisioned, teardown


@pytest.fixture
def actor(db_connection: Connection) -> Iterator[_Actor]:
    """One active EMPLOYEE with a valid token, cleaned up after.

    Depends on `db_connection` only to inherit its skip-when-DB-absent behaviour.
    """
    provisioned, teardown = _provision_actor("Mona Actor")
    try:
        yield provisioned
    finally:
        teardown()


@pytest.fixture
def second_actor(db_connection: Connection) -> Iterator[_Actor]:
    """A SECOND active EMPLOYEE, distinct from `actor` — the other party AC4 protects.

    Its own department, email and token, so a `PATCH /me` by `actor` can be shown to leave
    this row untouched (only the caller's own record changes).
    """
    provisioned, teardown = _provision_actor("Ravi Second")
    try:
        yield provisioned
    finally:
        teardown()


def _get_me(token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return _client.get("/api/v1/me", headers=headers)


def _patch_me(token: str | None, body: dict[str, object]):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return _client.patch("/api/v1/me", headers=headers, json=body)


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


# --- Story 1.8: PATCH /me — the one self-service write, and its one refusal --------------


def test_patch_updates_the_callers_full_name(actor: _Actor) -> None:
    """AC1 (FR-17): PATCH with `full_name` → 200, and a subsequent GET returns the new name."""
    new_name = "Mona Renamed"
    response = _patch_me(actor.token, {"full_name": new_name})

    assert response.status_code == 200
    assert response.json()["full_name"] == new_name

    # The write persisted: the read side, keyed by the same token, now reports the new name.
    after = _get_me(actor.token)
    assert after.status_code == 200
    assert after.json()["full_name"] == new_name


def test_patch_response_is_the_me_shape_and_leaks_nothing(actor: _Actor) -> None:
    """AC1: the PATCH response is exactly the six `/me` fields — no hash, line or balance."""
    body = _patch_me(actor.token, {"full_name": "Mona Reshaped"}).json()

    assert set(body) == {"id", "full_name", "email", "role", "department", "joining_date"}
    assert "password_hash" not in body
    assert "manager_id" not in body
    assert "is_active" not in body
    for leaked in ("balance", "allocated", "taken", "pending", "remaining"):
        assert leaked not in body


# One representative value per forbidden field. `role` uses the vocabulary symbol (never the
# literal, AD-21); `allocated` stands in for "any Leave Balance quantity" (AC2). Each is a
# field `PATCH /me` must refuse — email included, because email is Admin-maintained (AC5).
_FORBIDDEN_CASES = [
    ("email", "someone-else@example.com"),
    ("role", vocabulary.ROLE_ADMIN),
    ("department_id", str(uuid.uuid4())),
    ("manager_id", str(uuid.uuid4())),
    ("joining_date", "2020-01-01"),
    ("allocated", 30),
]


@pytest.mark.parametrize("field,value", _FORBIDDEN_CASES, ids=[case[0] for case in _FORBIDDEN_CASES])
def test_patch_with_a_forbidden_field_is_400_and_persists_nothing(
    actor: _Actor, field: str, value: object
) -> None:
    """AC2/AC3/AC5: any field other than `full_name` → 400 FORBIDDEN_FIELD, nothing written.

    The body is the exact `{code, message, details}` envelope (AC3 — a `400`, never a bare
    `422`), `details.forbidden_fields` names the rejected key (`G5`), and a follow-up GET
    proves the row is unchanged. The code is referenced by symbol, never the literal (AD-21).
    """
    response = _patch_me(actor.token, {field: value})

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.FORBIDDEN_FIELD
    assert field in body["details"]["forbidden_fields"]

    # Nothing persisted: the forbidden-field gate runs before any write (AC2).
    after = _get_me(actor.token)
    assert after.json()["full_name"] == actor.full_name


def test_patch_names_every_rejected_field(actor: _Actor) -> None:
    """AC2: several forbidden fields at once → all named in `details.forbidden_fields`."""
    response = _patch_me(actor.token, {"email": "x@example.com", "role": vocabulary.ROLE_ADMIN})

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.FORBIDDEN_FIELD
    assert set(body["details"]["forbidden_fields"]) == {"email", "role"}


def test_patch_full_name_with_a_forbidden_field_is_refused(actor: _Actor) -> None:
    """AC2: `full_name` alongside a forbidden field → the forbidden gate wins; nothing changes."""
    response = _patch_me(
        actor.token, {"full_name": "Should Not Apply", "role": vocabulary.ROLE_ADMIN}
    )

    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.FORBIDDEN_FIELD
    # The name did not change — the whole request was refused before any write.
    assert _get_me(actor.token).json()["full_name"] == actor.full_name


def test_patch_with_an_empty_body_is_a_no_op(actor: _Actor) -> None:
    """Edge case (Task 2): an empty body forbids nothing and changes nothing → 200, same name."""
    response = _patch_me(actor.token, {})

    assert response.status_code == 200
    assert response.json()["full_name"] == actor.full_name


# Code review 2026-07-13: `full_name` is present but its VALUE is unusable. Each must be
# refused with `400 INVALID_NAME` inside the envelope — never a bare 422 (wrong type) or a
# NOT NULL 500 (`null`). `null` and the non-string cases reach the service because
# `UpdateMeRequest.full_name` is typed `Any`, so Pydantic never rejects them first.
_INVALID_NAME_CASES = [
    ("null", None),
    ("integer", 123),
    ("boolean", True),
    ("list", ["Mona"]),
    ("object", {"first": "Mona"}),
    ("empty_string", ""),
    ("whitespace_only", "   "),
]


@pytest.mark.parametrize(
    "case_id,value", _INVALID_NAME_CASES, ids=[case[0] for case in _INVALID_NAME_CASES]
)
def test_patch_with_an_unusable_full_name_is_400_invalid_name(
    actor: _Actor, case_id: str, value: object
) -> None:
    """AC-adjacent (code review): an unusable `full_name` value → 400 INVALID_NAME, no write.

    The body is the exact `{code, message, details}` envelope (never a bare 422 or a 500),
    `details.field` names `full_name`, and a follow-up GET proves the row is unchanged. The
    code is referenced by symbol, never the literal (AD-21).
    """
    response = _patch_me(actor.token, {"full_name": value})

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.INVALID_NAME
    assert body["details"]["field"] == "full_name"

    # Nothing persisted: the value gate runs before the session opens.
    assert _get_me(actor.token).json()["full_name"] == actor.full_name


def test_patch_trims_surrounding_whitespace_before_persisting(actor: _Actor) -> None:
    """Code review: an accepted `full_name` is `strip()`ed — leading/trailing space is never stored."""
    response = _patch_me(actor.token, {"full_name": "  Mona Trimmed  "})

    assert response.status_code == 200
    assert response.json()["full_name"] == "Mona Trimmed"
    assert _get_me(actor.token).json()["full_name"] == "Mona Trimmed"


def test_patch_changes_only_the_callers_own_row(actor: _Actor, second_actor: _Actor) -> None:
    """AC4: one Employee's PATCH changes only their own record; the other's is untouched."""
    response = _patch_me(actor.token, {"full_name": "Only Mine Changed"})
    assert response.status_code == 200

    # The second Employee, reading with their own token, still sees their original name.
    other = _get_me(second_actor.token)
    assert other.status_code == 200
    assert other.json()["full_name"] == second_actor.full_name


def test_absent_token_cannot_patch(actor: _Actor) -> None:
    """AC4 (auth): PATCH /me with no token → 401 TOKEN_INVALID, and nothing is written."""
    response = _patch_me(None, {"full_name": "Anonymous"})

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID
    assert _get_me(actor.token).json()["full_name"] == actor.full_name


def test_no_me_subpath_route_exists() -> None:
    """AC4/AC6: `/me` is the only `/me`-rooted path — no `/me/<id>` cross-edit endpoint.

    A routing assertion over the OpenAPI schema (the stable enumeration of every registered
    path — this FastAPI version nests included routers inside `app.routes`, so the schema is
    the clean surface). The profile surface is exactly one path, `/api/v1/me`, carrying only
    `GET` and `PATCH` — there is no endpoint by which one Employee edits another's profile,
    and none nested under `/me`.
    """
    schema = app.openapi()
    me_paths = {path for path in schema["paths"] if path.startswith("/api/v1/me")}
    assert me_paths == {"/api/v1/me"}
    assert set(schema["paths"]["/api/v1/me"]) == {"get", "patch"}


def _request_model_properties(schema: dict, operation: dict) -> set[str]:
    """The declared property names of an operation's JSON request body (empty if none)."""
    body = operation.get("requestBody")
    if body is None:
        return set()
    node = body["content"]["application/json"]["schema"]
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        node = schema["components"]["schemas"][name]
    return set(node.get("properties", {}))


def test_no_me_route_accepts_a_password_field() -> None:
    """AC6: no `/me` route accepts a `password` field — there is no self password-change.

    Inspects each `/me` operation's request-body model in the OpenAPI schema. A password is
    a credential, not a profile field, so FR-17's editable surface stays Full Name alone.
    (Scoped to `/me`: the Admin's `POST /employees` legitimately sets an initial password —
    that is not a *self* change.) A "no new endpoint" assertion: it adds nothing, it forbids.
    """
    schema = app.openapi()
    for operation in schema["paths"]["/api/v1/me"].values():
        assert "password" not in _request_model_properties(schema, operation)
