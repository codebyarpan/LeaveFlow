"""`GET /api/v1/me` and `PATCH /api/v1/me` — the caller's own profile, read and one write.

Implements: FR-17, api-contracts §4.1 (`GET /me` + `PATCH /me`, Role "any", Scope "self"),
AD-10 (the read/write is keyed by the token's own subject, so there is no cross-Employee
identifier to guess — the `401` gate protects it, not the 404-scope mechanic, which is
Story 1.4), G5 (the `PATCH` accepts exactly `full_name` and refuses every other field with
`400 FORBIDDEN_FIELD`), AC1–AC4.

The routes declare the auth dependency and do nothing else of substance: the dependency
verifies the token and loads the actor, the read projects that actor into the response
model, and the write hands the submitted body to `services.me` and projects the row it
returns. This module imports neither `repositories/` nor `domain/` (contract 2) — the actor
is typed by the `Actor` Protocol from `dependencies`, and the `PATCH`'s refusal is
constructed by the service (the only layer allowed to raise a `DomainError`), never here.

--- Why `PATCH /me` does NOT reject extras with Pydantic (`extra="forbid"`) ---

`extra="forbid"` would make Pydantic raise `RequestValidationError` → a bare `422` without
the `{code, message, details}` envelope (breaking AC3/NFR-17). Instead `UpdateMeRequest`
uses `extra="allow"` so unknown keys reach the service in `model_dump(exclude_unset=True)`,
and the service raises the typed `FORBIDDEN_FIELD` `DomainError` — a `400` with the
envelope. `full_name` is optional (not required) so a body omitting it does not `422`
before the forbidden-field gate can run.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.v1.dependencies import Actor, get_current_employee
from app.services import me as me_service

router = APIRouter()


class DepartmentBrief(BaseModel):
    """The caller's department, named just enough to identify it (AC1).

    `id` and `name` only — `/me` states who the caller is, not the department's full
    record. The Department endpoints (Story 1.5) own that.
    """

    id: uuid.UUID
    name: str


class MeResponse(BaseModel):
    """The caller's own profile — exactly the six fields AC1 enumerates, and no more.

    NEVER `password_hash`, `manager_id`, `is_active`, or any Leave Balance quantity: AC1
    excludes the hash and balances explicitly, and disclosing the reporting line or the
    active flag here is scope this story does not have. The projection is built by hand in
    `read_me` (not `from_attributes`) so the set of exposed fields is decided here, once,
    by construction rather than by which attributes an ORM row happens to carry.
    """

    id: uuid.UUID
    full_name: str
    email: str
    role: str
    department: DepartmentBrief
    joining_date: datetime.date


class UpdateMeRequest(BaseModel):
    """The `PATCH /me` body — `full_name` and nothing else (AC2, api-contracts §4.1).

    `extra="allow"` is the crux (see the module docstring): an unknown key is collected
    into `model_dump(exclude_unset=True)` and carried to the service, which refuses it with
    `400 FORBIDDEN_FIELD` — rather than being silently dropped, or triggering a bare `422`
    that `extra="forbid"` would. `full_name` is optional so a body omitting it does not
    `422` before the forbidden-field gate runs; the service treats an absent `full_name`
    (with no forbidden field) as a graceful no-op.

    `full_name` is typed `Any`, not `str | None`, on purpose (code review 2026-07-13): a
    `str` annotation would make Pydantic reject a non-string value with a bare `422` before
    the request reaches the service — the same envelope hole `extra="forbid"` opens, on the
    type axis. Typing it `Any` lets every value flow to `services.me`, which validates it and
    raises `400 INVALID_NAME` inside the `{code,message,details}` envelope (NFR-17). The
    OpenAPI body stays present for the AC6 enumeration; only its declared type widens.
    """

    model_config = ConfigDict(extra="allow")

    full_name: Any = None


def _to_me_response(source: object) -> MeResponse:
    """Project a profile source into `MeResponse`, by hand — never `from_attributes`.

    Typed `object` because `api/` may not import the ORM `Employee` (contract 2); the source
    is either the `Actor` the dependency resolved (`read_me`) or the row the service returns
    (`update_me`), both of which carry the six fields as loaded, readable attributes. The set
    of exposed fields is decided here, once, by construction — the omission of
    `password_hash`, `manager_id`, `is_active` and every balance is the security-relevant
    part of the contract.
    """
    return MeResponse(
        id=source.id,
        full_name=source.full_name,
        email=source.email,
        role=source.role,
        department=DepartmentBrief(id=source.department.id, name=source.department.name),
        joining_date=source.joining_date,
    )


@router.get("/me", tags=["identity"])
def read_me(current: Actor = Depends(get_current_employee)) -> MeResponse:
    """Return the authenticated caller's own profile (AC1, FR-17).

    All verification is the dependency's; a request that reaches this body is already
    authenticated. The body's only job is the projection — and its deliberate omissions
    (no hash, no balance) are the security-relevant part of the contract.
    """
    return _to_me_response(current)


@router.patch("/me", tags=["identity"])
def update_me(
    request: UpdateMeRequest,
    current: Actor = Depends(get_current_employee),
) -> MeResponse:
    """Update the caller's own Full Name, refusing any other field (AC1–AC4, FR-17, G5).

    Auth only — `Depends(get_current_employee)`, no `require_role`: Role is "any", and the
    write targets the caller's own row (Scope "self" is intrinsic, AD-14). `exclude_unset`
    sends only the keys the client set, so `extra="allow"` surfaces an unknown field to the
    service, which raises `400 FORBIDDEN_FIELD` naming it (nothing persists). On success the
    returned row is projected into the same `MeResponse` shape the read exposes, at `200`.
    """
    submitted = request.model_dump(exclude_unset=True)
    updated = me_service.rename_me(current.id, submitted)
    return _to_me_response(updated)
