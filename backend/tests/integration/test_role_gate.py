"""The role gate refuses at the boundary, in an `api/` dependency, before the route runs.

Implements the test side of: AC3 (a disallowed role gets `403 ACTION_NOT_PERMITTED`), AC5
(the refusal happens in an `api/` dependency — a client that never rendered the control is
still refused, and role-appropriate rendering is never the only thing preventing the
action). Against real PostgreSQL, because the gate reads the actor's role from the
DB-resolved row (AD-14), exactly like `get_current_employee` — a token claim is never
trusted.

The route below is mounted on a THROWAWAY, test-only app and discarded with it. It is
deliberately NOT registered on the real `api_v1_router`: this story ships no user-facing
endpoint (Story 1.1's Task-4 discipline — no permanent route that exists only to prove a
mechanism). It proves the gate refuses in the dependency, *before* the route body runs,
by observing that a refused caller gets the error envelope and never the body's sentinel.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete
from sqlalchemy.orm import Session

from app.api.v1.dependencies import Actor, require_role
from app.core import security
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee
from app.services import authorization as authz

# Importing `app.main` populates `CODE_TO_STATUS` (its `.update(...)` runs at import), so
# `ACTION_NOT_PERMITTED` maps to 403 when the throwaway app's handler renders a refusal.
import app.main  # noqa: F401
from app.api.v1.errors import domain_error_handler  # noqa: E402

# See test_me.py: silence starlette's httpx-deprecation warning at import so it does not
# clutter this suite; it is not spine-governed.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"

# The route body's sentinel. If a refused caller ever sees this, the gate let the body run
# — the exact failure AC5 forbids. A 403 caller must see the error envelope instead.
_BODY_REACHED = "the-route-body-ran"


def _throwaway_admin_only_app() -> FastAPI:
    """A test-only app with one ADMIN-gated route, wired as `main.py` wires the real app."""
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)

    @app.get("/admin-only")
    def _admin_only(actor: Actor = Depends(require_role(authz.ROLE_ADMIN))) -> dict:
        # Reached ONLY when the gate admits the caller. The gate returns the actor, so the
        # route can still read the caller — proving the chain `require_role -> actor`.
        return {"reached": _BODY_REACHED, "id": str(actor.id)}

    return app


_client = TestClient(_throwaway_admin_only_app())


class _Caller:
    """An Employee of a given role, and a freshly-signed valid token for them."""

    def __init__(self, employee_id: uuid.UUID, role: str, token: str) -> None:
        self.id = employee_id
        self.role = role
        self.token = token


@pytest.fixture
def callers(db_connection: Connection) -> Iterator[dict[str, _Caller]]:
    """Create one active Employee per role in a shared department; sign a token for each.

    Depends on `db_connection` to inherit its skip-when-DB-absent behaviour; writes commit
    through the shared engine so the app (a fresh connection per command, AD-3) sees them.
    Email and department name are unique per run (uuid) so runs never collide.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"gate-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)
    emails: list[str] = []

    made: dict[str, _Caller] = {}
    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()

        for role in (
            vocabulary.ROLE_ADMIN,
            vocabulary.ROLE_MANAGER,
            vocabulary.ROLE_EMPLOYEE,
        ):
            email = f"gate-{role.lower()}-{suffix}@example.com"
            emails.append(email)
            employee = Employee(
                department_id=department.id,
                manager_id=None,
                email=email,
                full_name=f"Gate {role}",
                role=role,
                joining_date=datetime.date(2026, 1, 1),
                is_active=True,
                password_hash=hashed,
            )
            session.add(employee)
            session.flush()
            made[role] = _Caller(employee.id, role, "")
        session.commit()

        for role, caller in made.items():
            caller.token = security.create_token(str(caller.id), role)

    try:
        yield made
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(Employee).where(Employee.email.in_(emails)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _get_admin_only(token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return _client.get("/admin-only", headers=headers)


def test_admin_passes_the_role_gate(callers: dict[str, _Caller]) -> None:
    """AC5: an ADMIN token is admitted, the route body runs, and it reads the actor back."""
    admin = callers[vocabulary.ROLE_ADMIN]

    response = _get_admin_only(admin.token)

    assert response.status_code == 200
    body = response.json()
    assert body["reached"] == _BODY_REACHED
    assert body["id"] == str(admin.id)


@pytest.mark.parametrize("denied_role", [vocabulary.ROLE_MANAGER, vocabulary.ROLE_EMPLOYEE])
def test_a_disallowed_role_is_refused_403_before_the_body_runs(
    callers: dict[str, _Caller], denied_role: str
) -> None:
    """AC3 / AC5: a MANAGER or EMPLOYEE gets `403 ACTION_NOT_PERMITTED`, and the body never ran.

    The refusal is decided in the `api/` dependency against the DB-resolved role — the
    caller reached the endpoint directly, rendered no control, and is refused anyway. The
    response is the error envelope, never the route body's sentinel, proving the gate ran
    before the body.
    """
    caller = callers[denied_role]

    response = _get_admin_only(caller.token)

    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.ACTION_NOT_PERMITTED
    assert body["details"] == {}
    assert _BODY_REACHED not in response.text


def test_an_absent_token_is_401_not_403() -> None:
    """The gate builds on authentication: no token is a `401 TOKEN_INVALID`, decided first.

    `require_role` chains `Depends(get_current_employee)`, so an unauthenticated caller is
    rejected by authentication (401) before the role comparison is ever reached — the role
    gate does not turn a missing token into a 403.

    Takes no `callers` fixture: it sends no token, so it touches no DB. Not gating it on
    `db_connection` lets the 401-before-403 guarantee run even in a Postgres-less leg.
    """
    response = _get_admin_only(None)

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID
