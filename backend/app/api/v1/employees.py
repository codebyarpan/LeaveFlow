"""The `/api/v1/employees` endpoints: create, list, read, update, deactivate — Admin-only.

Implements: FR-04, api-contracts §4.2 (the five `/employees` endpoints; Role `Admin`, Scope
`all` throughout — EVERY endpoint, including the reads, unlike departments whose `GET` was
`any`), NFR-11 (the list is page-bounded), AD-10/AD-14 (a non-Admin is refused `403` by the
role gate in the dependency, before any row is read — `G3`, AC5). AC1, AC2, AC3, AC4, AC5,
AC8, AC11, AC12.

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never
`repositories/` or `domain/` (contract 2). It cannot construct a `DomainError`: the service
raises every refusal (`EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`, `EMPLOYEE_HAS_DIRECT_
REPORTS`, and `not_found()` for a nonexistent id or manager) and `main.py`'s single handler
renders them. Role literals reach here through `services.authorization` (`authz.ROLE_ADMIN`),
never `from app.domain.vocabulary import ...` — the indirection Story 1.4 established.

--- Why `EmployeeResponse` is projected by hand, and NEVER carries the password ---

The response is built field-by-field from the service's returned `Employee`, not
`from_attributes` off the ORM row (which `api/` may not import). The omission of
`password_hash` is by CONSTRUCTION — the projection simply never reads it (Trap 5). No
`/employees` response — create, read, update or deactivate — carries a password or a hash.
Unlike `MeResponse`, the Admin view DOES expose `manager_id` and `is_active`: an Admin
manages exactly the reporting line and the active flag.

--- The 2xx success codes (G6) ---

api-contracts fixes only non-2xx statuses. Chosen here, and matched by the React
`employees.ts` hooks: `201` for the created `POST`, `200` for `GET`/`PATCH`/deactivate.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import employee as employee_service

router = APIRouter()


class DepartmentBrief(BaseModel):
    """The Employee's department, named just enough to identify it — `{id, name}`."""

    id: uuid.UUID
    name: str


class CreateEmployeeRequest(BaseModel):
    """The body a create presents (AC1). `password` is the initial password, hashed once
    by the service and never echoed back (Trap 5). `manager_id` is optional — the top of a
    reporting chain, and an Admin, report to no one."""

    email: str
    full_name: str
    role: str
    department_id: uuid.UUID
    joining_date: datetime.date
    password: str
    manager_id: uuid.UUID | None = None


class UpdateEmployeeRequest(BaseModel):
    """The partial-update body (AC3). Every field optional, read with `exclude_unset` so an
    omitted field is left unchanged and an explicit `null` `manager_id` (clearing it) is
    distinguishable from absent. There is NO `password` field: a `PATCH` never re-issues a
    credential (Trap 5, FR-17)."""

    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    joining_date: datetime.date | None = None


class EmployeeResponse(BaseModel):
    """An Employee as the Admin view sees it (api-contracts §4.2). NEVER `password_hash`.

    Exposes `manager_id` and `is_active` — the reporting line and the active flag the Admin
    manages — which `MeResponse` deliberately hides. `department` is the `{id, name}` brief.
    """

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    department: DepartmentBrief
    manager_id: uuid.UUID | None
    joining_date: datetime.date
    is_active: bool


def _to_response(employee: object) -> EmployeeResponse:
    """Project the service's returned `Employee` into the response, by hand (Trap 5).

    Typed `object` because `api/` may not import the ORM `Employee`; the service guarantees
    the attributes are loaded and readable after commit (`expire_on_commit=False`, with
    `department` eager-loaded). `password_hash` is never read here — the omission is the
    security-relevant part of the contract.
    """
    return EmployeeResponse(
        id=employee.id,
        email=employee.email,
        full_name=employee.full_name,
        role=employee.role,
        department=DepartmentBrief(
            id=employee.department.id, name=employee.department.name
        ),
        manager_id=employee.manager_id,
        joining_date=employee.joining_date,
        is_active=employee.is_active,
    )


@router.post("/employees", tags=["employees"], status_code=status.HTTP_201_CREATED)
def create_employee(
    request: CreateEmployeeRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> EmployeeResponse:
    """Create an active Employee and return it (AC1, AC2). Admin-only; a non-Admin is `403`.

    The role gate runs in the `_admin` dependency, before this body — a non-Admin never
    reaches the create (AC5). The service hashes the initial password, enforces email
    uniqueness (`409`) and manager existence (`404`), and returns the row; the response
    never carries the password.
    """
    created = employee_service.create_employee(
        email=request.email,
        full_name=request.full_name,
        role=request.role,
        department_id=request.department_id,
        joining_date=request.joining_date,
        initial_password=request.password,
        manager_id=request.manager_id,
    )
    return _to_response(created)


@router.get("/employees", tags=["employees"])
def list_employees(
    params: PageParams = Depends(),
    admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> Page[EmployeeResponse]:
    """Return a page of Employees to an Admin (AC3, AC4, AC5). Admin-only — unlike
    departments, whose `GET` was `any` (api-contracts §4.2).

    The actor is threaded into the service so the read is honestly scoped (Trap 1); for an
    Admin the scope is `ALL`, so every Employee is returned. The page is bounded by
    `PageParams` (NFR-11); the body carries the `items`/`page`/`page_size`/`total` envelope.
    """
    rows, total = employee_service.list_employees(params.limit, params.offset, admin)
    return Page[EmployeeResponse](
        items=[_to_response(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.get("/employees/{employee_id}", tags=["employees"])
def read_employee(
    employee_id: uuid.UUID,
    admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> EmployeeResponse:
    """Return one Employee by id (AC3, AC5), or `404` for a nonexistent id (service
    `not_found()`). Admin-only. The actor is threaded through for the scoped read (Trap 1)."""
    return _to_response(employee_service.get_employee(employee_id, admin))


@router.patch("/employees/{employee_id}", tags=["employees"])
def update_employee(
    employee_id: uuid.UUID,
    request: UpdateEmployeeRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> EmployeeResponse:
    """Partially update an Employee (AC3, AC5, AC6, AC7, AC9). Admin-only.

    `exclude_unset=True` sends only the fields the client set, so an omitted field is left
    unchanged and an explicit `null` `manager_id` clears the reporting line. The service
    enforces the email (`409`), cycle (`400`) and demotion (`409`) refusals; a nonexistent
    id is `404`. There is no `password` field (Trap 5).
    """
    changes = request.model_dump(exclude_unset=True)
    return _to_response(employee_service.update_employee(employee_id, changes))


@router.post("/employees/{employee_id}/deactivate", tags=["employees"])
def deactivate_employee(
    employee_id: uuid.UUID,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> EmployeeResponse:
    """Deactivate an Employee (AC5, AC8, AC11). Admin-only; no body.

    A nonexistent id is `404`; an Employee who still has active direct reports is `409
    EMPLOYEE_HAS_DIRECT_REPORTS` (AC8), unchanged. On success returns the updated row with
    `is_active=false` so the client sees the new state (`200`). No endpoint deletes an
    Employee (AC12) — the row and its history persist.
    """
    return _to_response(employee_service.deactivate_employee(employee_id))
