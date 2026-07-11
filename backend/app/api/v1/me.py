"""`GET /api/v1/me` — the caller's own profile.

Implements: FR-17, api-contracts §4.1 (`GET /me`, Role "any", Scope "self"), AD-10 (the
read is keyed by the token's own subject, so there is no cross-Employee identifier to
guess — the `401` gate protects it, not the 404-scope mechanic, which is Story 1.4), AC1.

The route declares the auth dependency and does nothing else of substance: the dependency
verifies the token and loads the actor, and this route projects that actor into the
response model. It imports neither `repositories/` nor `domain/` (contract 2) — the actor
is typed by the `Actor` Protocol from `dependencies`, which names the shape without
importing `Employee` (the same reason `errors.py` uses `DomainErrorLike`).
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee

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


@router.get("/me", tags=["identity"])
def read_me(current: Actor = Depends(get_current_employee)) -> MeResponse:
    """Return the authenticated caller's own profile (AC1, FR-17).

    All verification is the dependency's; a request that reaches this body is already
    authenticated. The body's only job is the projection — and its deliberate omissions
    (no hash, no balance) are the security-relevant part of the contract.
    """
    return MeResponse(
        id=current.id,
        full_name=current.full_name,
        email=current.email,
        role=current.role,
        department=DepartmentBrief(id=current.department.id, name=current.department.name),
        joining_date=current.joining_date,
    )
