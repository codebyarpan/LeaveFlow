"""The `/api/v1/team` endpoint: a Manager's Direct Reports — Manager-only (Story 3.2).

Implements: FR-19, api-contracts §4.9 (`GET /team` | Role `Manager` | Scope `reports`),
AD-10/AD-14 (the scope is a SQL predicate over the live reporting edge, resolved from the
DB actor at request time), G3 (a non-Manager is refused `403 ACTION_NOT_PERMITTED` by the
role gate in the dependency, before any row is read), NFR-11 (the list is page-bounded).

--- The one contract inversion: the ADMIN is refused here ---

Nearly every read in this app grants the Admin `ALL`; §4.9 grants `/team` to the Manager
ALONE, so `require_role(authz.ROLE_MANAGER)` refuses an Admin exactly as it refuses an
Employee (AC4). This is contract, not accident: an Admin sees everyone through
`GET /employees`; a team is a fact about a reporting edge, and only a Manager stands on one.

--- Why `TeamMemberResponse` is deliberately smaller than `EmployeeResponse` ---

FR-19 names exactly three facts a Manager is granted sight of: the Employee (Full Name —
erd.md GAP-2 settled that Full Name IS the identification), their Department, and the
active state. `EmployeeResponse` is the ADMIN view and additionally discloses `email`,
`role`, `joining_date` and `manager_id` — none of which any requirement grants a Manager.
Authority is granted per-surface, in the projection, never by convenience (AD-10), so this
response carries `{id, full_name, department, is_active}` and NOTHING else. `id` is the
uuidv7 React key and any later drill-down's handle; `manager_id` is omitted as tautological
(it is the caller).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, require_role
from app.api.v1.employees import DepartmentBrief
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import team as team_service

router = APIRouter()


class TeamMemberResponse(BaseModel):
    """One Direct Report, as FR-19 grants a Manager sight of them — and nothing more."""

    id: uuid.UUID
    full_name: str
    department: DepartmentBrief
    is_active: bool


def _to_response(member: object) -> TeamMemberResponse:
    """Project the service's returned `Employee` into the response, by hand (Trap 5).

    Typed `object` because `api/` may not import the ORM `Employee`; the service guarantees
    `department` is eager-loaded and readable after the session closes. The fields NOT read
    here — `email`, `role`, `joining_date`, `manager_id`, `password_hash` — are the
    disclosure decision (Open Decision #1); the omission is by construction.
    """
    return TeamMemberResponse(
        id=member.id,
        full_name=member.full_name,
        department=DepartmentBrief(
            id=member.department.id, name=member.department.name
        ),
        is_active=member.is_active,
    )


@router.get("/team", tags=["team"])
def list_team(
    params: PageParams = Depends(),
    manager: Actor = Depends(require_role(authz.ROLE_MANAGER)),
) -> Page[TeamMemberResponse]:
    """Return a page of the caller's Direct Reports (AC1, AC2). Manager-only — an Employee
    AND an Admin are `403` (AC4, the §4.9 inversion).

    The role gate runs in the `manager` dependency, before this body — a non-Manager never
    reaches the read (G3). The service applies the REPORTS scope in the SQL; a deactivated
    report is in the list, distinguishable by `is_active` (AC3). The page is bounded by
    `PageParams` (NFR-11); the body carries the `items`/`page`/`page_size`/`total` envelope.
    """
    rows, total = team_service.list_team(params.limit, params.offset, manager)
    return Page[TeamMemberResponse](
        items=[_to_response(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
