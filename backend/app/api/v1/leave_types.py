"""The `/api/v1/leave-types` endpoints: create (Admin) and list (any role).

Implements: FR-06, SM-5 (a fourth Leave Type is added through `POST` with no schema
migration and no code change), api-contracts §4.3 (Role `Admin` for the create, `any` for
the read; Scope `all` on both), NFR-11 (the list is page-bounded), AD-14 (the create is
refused by ROLE at the boundary — the `403`, before any row is written). AC3, AC4, AC7,
AC8, AC9.

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never
`repositories/` or `domain/` (contract 2). It cannot construct a `DomainError`: the service
raises `LEAVE_TYPE_CODE_IN_USE` and `main.py`'s single handler renders it. The role literal
reaches here through `services.authorization` (`authz.ROLE_ADMIN`), never `from
app.domain.vocabulary import ...` — the same indirection Story 1.4's role gate established.

--- Why `LeaveTypeResponse` is projected by hand ---

The response is built field-by-field from the service's returned `LeaveType`, not
`from_attributes` off the ORM row (which `api/` may not import anyway). The seven exposed
fields are decided here by construction, as `departments.py` projects `DepartmentResponse`.

--- The 2xx success codes (G6) ---

api-contracts fixes only non-2xx statuses; the success codes are this story's to choose
(Story 1.5 Trap 5), matched by the React `leaveTypes.ts` hooks: `201` for a created `POST`,
`200` for the `GET` list — identical to departments.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import leave_types as leave_types_service

router = APIRouter()


class LeaveTypeWriteRequest(BaseModel):
    """The body a create presents. `carry_forward_cap` is optional (null when omitted)."""

    code: str
    name: str
    annual_entitlement: int
    carries_forward: bool
    carry_forward_cap: int | None = None
    requires_supporting_document: bool


class LeaveTypeResponse(BaseModel):
    """A Leave Type as the wire sees it: all seven fields (api-contracts §4.3)."""

    id: uuid.UUID
    code: str
    name: str
    annual_entitlement: int
    carries_forward: bool
    carry_forward_cap: int | None
    requires_supporting_document: bool


def _to_response(leave_type: object) -> LeaveTypeResponse:
    """Project the service's returned `LeaveType` into the response model, by hand.

    Typed `object` because `api/` may not import the ORM `LeaveType`; the service guarantees
    every attribute is present and readable after commit (`expire_on_commit=False`).
    """
    return LeaveTypeResponse(
        id=leave_type.id,
        code=leave_type.code,
        name=leave_type.name,
        annual_entitlement=leave_type.annual_entitlement,
        carries_forward=leave_type.carries_forward,
        carry_forward_cap=leave_type.carry_forward_cap,
        requires_supporting_document=leave_type.requires_supporting_document,
    )


@router.post("/leave-types", tags=["leave-types"], status_code=status.HTTP_201_CREATED)
def create_leave_type(
    request: LeaveTypeWriteRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> LeaveTypeResponse:
    """Create a Leave Type and return it (AC3, SM-5). Admin-only; a non-Admin is `403` (AC7).

    The role gate runs in the `_admin` dependency, before this body — a non-Admin never
    reaches the create, so no row is written (AD-14). A duplicate `code` is refused by the
    service with `409 LEAVE_TYPE_CODE_IN_USE` (AC6). Adding a fourth type is exactly this
    path: no schema migration, no code change.
    """
    return _to_response(
        leave_types_service.create_leave_type(
            code=request.code,
            name=request.name,
            annual_entitlement=request.annual_entitlement,
            carries_forward=request.carries_forward,
            carry_forward_cap=request.carry_forward_cap,
            requires_supporting_document=request.requires_supporting_document,
        )
    )


@router.get("/leave-types", tags=["leave-types"])
def list_leave_types(
    params: PageParams = Depends(),
    _caller: Actor = Depends(get_current_employee),
) -> Page[LeaveTypeResponse]:
    """Return a page of Leave Types to any authenticated role (AC4, AC8, AC9).

    Authentication only — `get_current_employee`, NOT `require_role`: every role reads the
    list (scope `all`). No token is `401 TOKEN_INVALID` via the empty-token path already in
    `get_current_employee`. The page is bounded by `PageParams` (NFR-11); the body carries
    the `items`, `page`, `page_size`, `total` envelope.
    """
    rows, total = leave_types_service.list_leave_types(params.limit, params.offset)
    return Page[LeaveTypeResponse](
        items=[_to_response(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
