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
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

# `api/ → api/` is allowed by import-linter contract 2, and these two response models are REUSED
# rather than redeclared: a policy recalculation and a holiday recalculation produce the SAME summary
# (`services/recalculation.RecalculationSummary` serves both), so a second copy of its wire shape here
# would be pure drift — two models that must be kept in step by hand, with nothing to notice when they
# are not.
from app.api.v1.holidays import RecalculationResponse, RefusedPairResponse
from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import leave_types as leave_types_service

router = APIRouter()


class LeaveTypeWriteRequest(BaseModel):
    """The body a create presents. `carry_forward_cap` is optional (null when omitted).

    `annual_entitlement` is `ge=0` (Story 2.12, Open Decision #3, closing `deferred-work.md:44`). A
    negative entitlement reaches `prorate_entitlement` and fires a raw 500; on create that was a
    curiosity, but Story 2.12's `PATCH … RECALCULATE` makes it reachable ON AN ADMIN'S EDIT, against
    live balances.

    This DOES raise a bare Pydantic `422`, outside the `{code,message,details}` envelope — and that is
    a considered difference from the `extra="allow"` decision on the PATCH below, not an inconsistency.
    A MALFORMED NUMBER is a schema-level fault, and `422` is the honest code for it. `extra="allow"`
    exists because PATCH semantics need "absent" ≠ "null", and because `FORBIDDEN_FIELD` is a DOMAIN
    rule about authority rather than a statement about shape. "This must be a non-negative integer" is
    a shape.
    """

    code: str
    name: str
    annual_entitlement: int = Field(ge=0)
    carries_forward: bool
    carry_forward_cap: int | None = None
    requires_supporting_document: bool


class LeaveTypeUpdateRequest(BaseModel):
    """The `PATCH /leave-types/{id}` body (Story 2.12, AC2). Every field optional; one is special.

    --- Why `extra="allow"` and not `extra="forbid"` (the `PATCH /me` precedent) ---

    `extra="forbid"` would make Pydantic raise `RequestValidationError` → a bare `422` WITHOUT the
    `{code, message, details}` envelope, breaking NFR-17. So unknown keys are ALLOWED through to the
    service, which refuses them with a typed `400 FORBIDDEN_FIELD` — the shape `api/v1/me.py:16-21`
    documents and Story 1.8 established.

    `model_dump(exclude_unset=True)` in the route is the other half: it sends the service ONLY the
    keys the client actually set. That is what keeps "`carry_forward_cap` was set to `null`" (a policy
    change — the cap was REMOVED, meaning uncapped) distinguishable from "`carry_forward_cap` was not
    submitted" (no change at all). With a plain default those two are the same request, and one of
    them silently triggers a recalculation nobody asked for.

    --- ⚠️ `disposition` is `Any`, and it CANNOT be a `Literal` (Landmine 9) ---

    `Literal["RECALCULATE", "PRESERVE"]` is UNWRITABLE in this codebase. `tests/test_vocabulary_
    literals.py` walks the AST of everything under `app/` and flags any string constant equal to an
    exported `vocabulary.__all__` value — ANNOTATIONS INCLUDED — and the two `DISPOSITION_*` constants
    are exported. `Literal[vocabulary.DISPOSITION_RECALCULATE, ...]` is not valid typing either (PEP
    586 needs literal values, not names). And `api/` may not import `domain/` anyway (contract 2).

    That constraint pushes toward the right answer regardless. Typed as a `Literal`, an invalid
    disposition (`"FOO"`) would yield a bare `422` outside the envelope; typed `str` and left
    unvalidated it would reach `CHECK (disposition IN (…))` and fire a RAW 500 — an AD-5 violation,
    since the CHECK is a backstop and never a gate. So it is typed `Any` (the `full_name: Any` shape
    `me.py:89` uses for exactly this reason) and VALIDATED IN THE SERVICE, which raises
    `400 POLICY_DISPOSITION_REQUIRED` — one code for "absent" and for "not one of the two", because
    they are the same question with the same answer and api-contracts defines no second code.

    --- Why the OTHER five keep their real types, and a `None` default that is never validated ---

    Pydantic does not validate a DEFAULT (`validate_default` is off), so `name: str = None` means
    exactly "absent → `None`, and `exclude_unset` will not send it" while still rejecting an explicit
    `{"name": null}` with a `422`. That is the honest code for it: "name must be a string" is a SHAPE
    fault, the same class as `annual_entitlement: "abc"`, and the same argument the create's `ge=0`
    rests on. Only the four non-nullable attributes work this way.

    `carry_forward_cap` is the ONE genuinely nullable attribute, so it alone is typed `int | None`:
    `{"carry_forward_cap": null}` is a LEGAL and MEANINGFUL edit — it removes the ceiling (UNCAPPED,
    not zero — Story 2.10's Open Decision #2, inherited here for free through `carry_forward_days`).
    It is a cap change, so it triggers the disposition and AC6's recomputation like any other.

    `ge=0` on both integers closes `deferred-work.md:44` (Open Decision #3): a negative
    `annual_entitlement` reaches `prorate_entitlement` and fires a raw 500 — a curiosity on create,
    and a live 500 on an Admin's `PATCH … RECALCULATE` against real balances.
    """

    model_config = ConfigDict(extra="allow")

    name: str = None
    annual_entitlement: int = Field(default=None, ge=0)
    carries_forward: bool = None
    # The one nullable attribute: `null` REMOVES the cap (uncapped), and that is a policy change.
    carry_forward_cap: int | None = Field(default=None, ge=0)
    requires_supporting_document: bool = None
    # ⚠️ `Any`, never a `Literal` — see above. Validated in the service.
    disposition: Any = None


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


class LeaveTypeCommandResponse(BaseModel):
    """The `200` body the EDIT answers with (Story 2.12, AC5, AC11): the row, and the recalculation.

    The `HolidayCommandResponse` shape, and the same reasoning: a policy edit is not CRUD. It may
    REFUSE a given (Employee, Leave Type) pair — leaving that balance ENTIRELY unchanged — while the
    rest of the operation commits and this returns `200` (AD-19). There is no status code that can
    carry "it worked, mostly, and here is what I declined to touch", so the summary is the body.

    A name-only edit carries an EMPTY summary (`0, 0, []`), never a `null` — one shape, no optional
    branch for the client to forget.

    ⚠️ `POST /leave-types` is UNTOUCHED and still answers `201 + LeaveTypeResponse`. Unlike Story
    2.11 (which had to move `POST`/`DELETE /holidays` off `201`/`204`), `PATCH` is a NEW route, so
    this story makes no breaking change and none is invented for symmetry's sake.
    """

    leave_type: LeaveTypeResponse
    recalculation: RecalculationResponse


def _to_command_response(result: object) -> LeaveTypeCommandResponse:
    """Project the service's `LeaveTypeCommandResult` onto the wire, field by field.

    `result: object` — not the dataclass — because contract 2 forbids `api/` importing `services/`
    internals for typing (the `holidays.py` / `audit_entries.py` precedent). The nested `RefusedPair`s
    are projected one by one into the SAME `RefusedPairResponse` the holidays route uses; `api/ →
    api/` is allowed by contract 2, and a second declaration of that model would be drift.
    """
    recalculation = result.recalculation  # type: ignore[attr-defined]
    return LeaveTypeCommandResponse(
        leave_type=_to_response(result.leave_type),  # type: ignore[attr-defined]
        recalculation=RecalculationResponse(
            requests_recalculated=recalculation.requests_recalculated,
            pairs_recalculated=recalculation.pairs_recalculated,
            pairs_refused=[
                RefusedPairResponse(
                    employee_id=pair.employee_id,
                    employee_name=pair.employee_name,
                    leave_type_id=pair.leave_type_id,
                    leave_type_code=pair.leave_type_code,
                    leave_year=pair.leave_year,
                    cause=pair.cause,
                )
                for pair in recalculation.pairs_refused
            ],
        ),
    )


@router.patch("/leave-types/{leave_type_id}", tags=["leave-types"])
def update_leave_type(
    leave_type_id: uuid.UUID,
    request: LeaveTypeUpdateRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> LeaveTypeCommandResponse:
    """Change a Leave Type's policy, with an explicit disposition, and return `200` (AC2, AC5, AC7).

    FR-06's last clause. The role gate runs in the `_admin` dependency, before this body, so a
    non-Admin never reaches the edit and no row is written (AD-14). An id that names no row is `404
    RESOURCE_NOT_FOUND` from the service's load-or-`not_found()`.

    If the change would affect balances that already exist, the service refuses a missing or invalid
    disposition with `400 POLICY_DISPOSITION_REQUIRED` and NOTHING is applied — not the `leave_type`
    row, not a `policy_change` row (AC2).

    `exclude_unset=True` sends the service only the keys the client actually set, which is what keeps
    "the cap was set to null" (uncapped — a policy change) distinguishable from "the cap was not
    submitted" (no change). `disposition` is popped OUT of that dict and passed separately: it is a
    parameter of the COMMAND, not an attribute of the Leave Type, and leaving it in `submitted` would
    have the service try to write a `disposition` column onto a table that has none.

    A per-pair recalculation refusal does NOT fail this request (AD-19): the edit commits, and the
    refused pairs are named in `recalculation.pairs_refused`, which is what AC11's screen reads.
    """
    submitted = request.model_dump(exclude_unset=True)
    disposition = submitted.pop("disposition", None)
    return _to_command_response(
        leave_types_service.update_leave_type(leave_type_id, submitted, disposition)
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
