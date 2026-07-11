"""The `/api/v1/departments` endpoints: create, list, rename, remove — role-gated.

Implements: FR-05, api-contracts §4.2 (the four `/departments` endpoints; Role `Admin` for
the writes, `any` for the read; Scope `all` throughout), NFR-11 (the list is page-bounded),
AD-14 (the writes are refused by ROLE at the boundary, before any row is read — the `403`,
not a post-filter). AC1, AC2, AC3, AC4, AC6, AC7.

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never
`repositories/` or `domain/` (contract 2). It cannot construct a `DomainError`: the service
raises the refusals (`DEPARTMENT_NOT_EMPTY`, and `not_found()` for a nonexistent id) and
`main.py`'s single handler renders them. The role literals reach here through
`services.authorization` (`authz.ROLE_ADMIN`), never `from app.domain.vocabulary import ...`
— the same indirection Story 1.4's role gate established.

--- Why `DepartmentResponse` is projected by hand ---

The response model is built field-by-field from the service's returned `Department`, not
`from_attributes` off the ORM row (which `api/` may not import anyway). The set of exposed
fields — `id`, `name` — is decided here by construction, as `me.py` projects `MeResponse`.

--- The 2xx success codes (G6) ---

api-contracts fixes only non-2xx statuses; the success codes are this story's to choose
(Story 1.5 Trap 5). Chosen, and matched by the React `departments.ts` hooks: `201` for a
created `POST`, `200` for an updated `PATCH`, `204` (no body) for a `DELETE`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import departments as departments_service

router = APIRouter()


class DepartmentWriteRequest(BaseModel):
    """The body a create or rename presents — a Department is `{name}` on the way in."""

    name: str


class DepartmentResponse(BaseModel):
    """A Department as the wire sees it: `{id, name}` and nothing more (api-contracts §4.2)."""

    id: uuid.UUID
    name: str


def _to_response(department: object) -> DepartmentResponse:
    """Project the service's returned `Department` into the response model, by hand.

    Typed `object` because `api/` may not import the ORM `Department`; the service
    guarantees the `id`/`name` attributes are present and readable after commit
    (`expire_on_commit=False`).
    """
    return DepartmentResponse(id=department.id, name=department.name)


@router.post("/departments", tags=["departments"], status_code=status.HTTP_201_CREATED)
def create_department(
    request: DepartmentWriteRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> DepartmentResponse:
    """Create a Department and return it (AC1). Admin-only; a non-Admin is `403` (AC4).

    The role gate runs in the `_admin` dependency, before this body — a non-Admin never
    reaches the create. The actor itself is not read here (scope is `all`); the dependency
    exists to enforce the role, not to feed the body.
    """
    return _to_response(departments_service.create_department(request.name))


@router.get("/departments", tags=["departments"])
def list_departments(
    params: PageParams = Depends(),
    _caller: Actor = Depends(get_current_employee),
) -> Page[DepartmentResponse]:
    """Return a page of Departments to any authenticated role (AC2, AC3, AC7).

    Authentication only — `get_current_employee`, NOT `require_role`: every role reads the
    list (scope `all`). No token is `401 TOKEN_INVALID` via the empty-token path already in
    `get_current_employee`. The page is bounded by `PageParams` (NFR-11); the body carries
    the `items`, `page`, `page_size`, `total` envelope.
    """
    rows, total = departments_service.list_departments(params.limit, params.offset)
    return Page[DepartmentResponse](
        items=[_to_response(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.patch("/departments/{department_id}", tags=["departments"])
def rename_department(
    department_id: uuid.UUID,
    request: DepartmentWriteRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> DepartmentResponse:
    """Rename a Department (AC4 for a non-Admin `403`; Trap 4 for a nonexistent id `404`).

    Admin-only. A `PATCH` of an id that names no row is a `404 RESOURCE_NOT_FOUND`, raised
    by the service's load-or-`not_found()`.
    """
    return _to_response(
        departments_service.rename_department(department_id, request.name)
    )


@router.delete(
    "/departments/{department_id}",
    tags=["departments"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_department(
    department_id: uuid.UUID,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> None:
    """Delete a Department, or refuse (AC5, AC6, AC4, Trap 4).

    Admin-only (`403` for a non-Admin). A nonexistent id is `404`; a Department that still
    has assigned Employees is `409 DEPARTMENT_NOT_EMPTY` — both raised by the service, which
    counts before it deletes so the FK RESTRICT never surfaces as a 500 (AD-5). On success,
    `204` with no body.
    """
    departments_service.delete_department(department_id)
