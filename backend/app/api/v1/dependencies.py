"""The `api/v1` authentication dependency: resolve the caller from a Bearer token.

Implements: FR-02 / FR-17, AD-14 (the check happens in an `api/` dependency, against the
database, independently of anything the client sent beyond the token's subject), AC2/AC5.

--- What this module may import, and what it may not ---

Only `api/` may import `fastapi`, and this dependency is where the framework's Bearer
scheme meets the service. It imports `fastapi`, `fastapi.security` and `app.services.auth`
— nothing lower. It must NOT import `app.repositories`, `app.domain` or `app.core`
(contract 2): the token verification, the JWT-error → `DomainError(TOKEN_INVALID)`
translation, and the row load ALL live in `services.auth.resolve_actor`, on the far side
of the layer boundary. This module's whole job is to lift the raw Bearer string off the
request and hand it to that service (see Story 1.3 Dev Notes, Trap 1).

--- Why the actor is typed as a Protocol, not `Employee` ---

`api/` cannot import `app.repositories.models.Employee` — contract 2 forbids it, and
import-linter flags the import even under `TYPE_CHECKING` (it reasons over the AST, not
the runtime graph; `exclude_type_checking_imports` is off). So the actor's *shape* is
named here with a structural `Protocol`, exactly as `api/v1/errors.py` names a domain
exception with `DomainErrorLike` rather than importing `DomainError`. The service returns
a real `Employee`; it satisfies `Actor` structurally, and the route reads the caller's
attributes with the type checker's help but no forbidden import.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Callable, Protocol

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services import auth as auth_service
from app.services import authorization as authz


class DepartmentShape(Protocol):
    """The department fields `GET /me` reads off the actor (AC1). Named, not imported."""

    id: uuid.UUID
    name: str


class Actor(Protocol):
    """The authenticated caller, described by the attributes the routes read.

    The structural counterpart to `repositories.models.Employee` on the `api/` side of
    the layer boundary. Story 1.4 extends the dependencies that produce it into role- and
    scope-gated variants; this Protocol is the authentication-only actor they build on.
    """

    id: uuid.UUID
    full_name: str
    email: str
    role: str
    joining_date: datetime.date
    department: DepartmentShape


# `auto_error=False` is deliberate (Story 1.3 Dev Notes, Trap 4). The default
# `auto_error=True` makes FastAPI raise its OWN `HTTPException(403, "Not authenticated")`
# on a missing/malformed `Authorization` header — a bare body, the wrong status, and
# bypassing the `{code, message, details}` envelope entirely. With `auto_error=False`, a
# missing header yields `credentials = None`, which we route through the same
# `resolve_actor` rejection so the absent-header case becomes a `401 TOKEN_INVALID`
# envelope like every other rejection (AC2).
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_employee(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Actor:
    """Resolve and return the authenticated caller, or raise `TOKEN_INVALID` (AC1, AC2, AC5).

    Authentication only. Story 1.4 extends this into role- and scope-gated dependencies;
    this one asserts nothing about *what* the caller may do — only *who* they are.

    An absent or malformed header gives `credentials is None`; that empty-token path flows
    through `resolve_actor` so it raises the one `TOKEN_INVALID` `DomainError` every other
    rejection does (AC2). Otherwise the raw Bearer string is handed to the service, which
    owns the verification and the database load — this dependency does neither.
    """
    token = credentials.credentials if credentials is not None else ""
    return auth_service.resolve_actor(token)


def require_role(*allowed: str) -> Callable[..., Actor]:
    """Build a dependency that admits only callers whose role is one of `allowed` (AC3, AC5).

    A dependency *factory*: `require_role(authz.ROLE_ADMIN)` captures the allowed roles and
    returns the inner callable FastAPI resolves. The inner dependency chains
    `Depends(get_current_employee)` — so authentication runs first, unchanged — then calls
    `authz.assert_role`, which raises `403 ACTION_NOT_PERMITTED` before the route body runs
    when the role is not admitted (AD-14: the refusal is in an `api/` dependency, at the
    boundary, decided against the DB-resolved actor, never a token claim or a rendered
    control). On success it returns the `actor`, so a route can write
    `actor: Actor = Depends(require_role(...))` and still read the caller.

    The role literals come through `app.services.authorization` (an allowed `api →
    services` edge); this module must not `from app.domain.vocabulary import ...` — contract
    2 forbids it even under `TYPE_CHECKING`, and the literal scan forbids the bare string.
    The gate builds ON TOP of `get_current_employee`; it does not replace it, and that
    dependency stays authentication-only.

    At least one role must be passed. `require_role()` with no arguments would build a gate
    whose `allowed` is empty, so `assert_role`'s `role not in ()` refuses *every* caller —
    a permanently-closed endpoint with no import- or startup-time signal. Fail loud on the
    mis-declaration instead.
    """
    if not allowed:
        raise ValueError("require_role() needs at least one allowed role")

    def _require_role(actor: Actor = Depends(get_current_employee)) -> Actor:
        authz.assert_role(actor, allowed)
        return actor

    return _require_role
