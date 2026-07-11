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
from typing import Protocol

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services import auth as auth_service


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
