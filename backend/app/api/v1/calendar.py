"""The `/api/v1/calendar` endpoint: the Department Leave Calendar — Manager-only (Story 3.3).

Implements: FR-18 / api-contracts §4.9 (`GET /calendar` | Role `Manager` | Scope `reports` —
a Manager's Direct Reports' Approved AND Pending leave overlapping a date range, presented at
the moment of decision, UJ-2), G3 (a non-Manager is refused `403 ACTION_NOT_PERMITTED` by the
role gate in the dependency, before any row is read), NFR-11 (the list is page-bounded),
AD-18 (`leave_days` on every item is the stored figure, never recomputed).

--- The contract inversion, second verse: the ADMIN is refused here ---

§4.9 grants `/calendar` to the Manager ALONE — exactly like `/team`: a calendar over a team is
a fact about a reporting edge, and only a Manager stands on one. An Admin reads any request via
`GET /leave-requests` (scope ALL); here `require_role(authz.ROLE_MANAGER)` refuses an Admin
exactly as it refuses an Employee.

--- Why there is NO `status` query param, and no status name in this module ---

FR-18 defines the calendar as "Approved and Pending" — the set is fixed SERVER-SIDE in
`services/calendar.py` (Open Decision #4), so the client cannot widen or narrow it and no
status name ever appears in `api/` (which may import neither `domain/` nor `repositories/` —
contract 2; the `Scope.REPORTS` decision lives in the service for the same reason).

--- Why the response shape is `LeaveRequestResponse`, reused byte-for-byte ---

Open Decision #1: a Manager already reads every one of these ten fields for these exact rows
via `GET /leave-requests` (scope REPORTS) — a narrower calendar shape would be a second
projection to maintain with zero disclosure gained, and `employee_name` is the field that
answers "who else is away." Imported from `leave_requests.py` with its projection (the
`DepartmentBrief`-from-`employees.py` single-home precedent); never redeclared.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import Actor, require_role
from app.api.v1.leave_requests import LeaveRequestResponse, to_leave_request_response
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import calendar as calendar_service

router = APIRouter()


@router.get("/calendar", tags=["calendar"])
def list_calendar(
    params: PageParams = Depends(),
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    manager: Actor = Depends(require_role(authz.ROLE_MANAGER)),
) -> Page[LeaveRequestResponse]:
    """Return a page of the caller's Direct Reports' PENDING+APPROVED leave overlapping the
    window (AC1, AC2). Manager-only — an Employee AND an Admin are `403` (the §4.9 inversion).

    The role gate runs in the `manager` dependency, before this body — a non-Manager never
    reaches the read (G3). Both dates are optional (an absent side applies no predicate — never
    defaulted, so a window straddling Dec 31 works by construction); a malformed date is a
    framework `422` via the `datetime.date` typing; an inverted range is a well-formed empty
    intersection → `200` with `total == 0` (Landmine 5, the settled 3.1 semantics). The page is
    bounded by `PageParams` (NFR-11); the body carries the `items/page/page_size/total` envelope.
    """
    views, total = calendar_service.list_calendar(
        date_from=date_from,
        date_to=date_to,
        limit=params.limit,
        offset=params.offset,
        actor=manager,
    )
    return Page[LeaveRequestResponse](
        items=[to_leave_request_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
