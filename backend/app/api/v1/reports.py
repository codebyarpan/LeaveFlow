"""The `/api/v1/reports/leave.csv` route: the CSV export of leave (Story 4.2).

Implements: FR-15 (a Manager exports their Direct Reports' leave, an Admin the organization's;
the filter set applied to the view is applied to the export — filters, never pages). AC1 (scope
`reports, all` — Manager/Admin only, and a Manager's export EXCLUDES their own row), AC4 (the
format is CSV; no PDF export exists, a declared non-goal — PRD §7.4).

--- The gate, and why there is no new error code ---

`require_role(authz.ROLE_MANAGER, authz.ROLE_ADMIN)` — the `balances.py` multi-role precedent —
runs BEFORE this body: an Employee is refused `403 ACTION_NOT_PERMITTED` and no row is ever read
(G3; 404 stays reserved for scope misses, and this endpoint has no path parameter so it has no
404 case at all). This story coins NO vocabulary, NO error code, and touches `main.py` not at
all. Every non-2xx still carries the JSON envelope; only the 200 is CSV.

--- NOT a list endpoint: no `PageParams`, deliberately ---

The pagination convention binds list endpoints — the `items/page/page_size/total` envelope.
This endpoint returns CSV, and the export carries ALL matching rows (Landmine 1: `MAX_PAGE_SIZE`
would silently truncate at 100). There is no `page`/`page_size` here by design, and no
scope-matrix entry either (no path parameter — the `audit_entries.py` precedent).

--- What this module may import ---

`api/` may import neither `repositories/` nor `domain/` (contract 2): the role constants come
through `services/authorization`, and the status filter values through the service's re-exported
`LEAVE_STATUS_VALUES` — the `leave_requests.py` runtime-enum idiom, so no status literal is
typed here (`test_vocabulary_literals.py`). The response is a plain `fastapi.Response` — a
non-JSON 200 has no Pydantic envelope; its surface is pinned by header + parsed-body tests
instead (the 4.1 document-GET convention).
"""

from __future__ import annotations

import datetime
import enum
import uuid

from fastapi import APIRouter, Depends, Query, Response

from app.api.v1.dependencies import Actor, require_role
from app.services import authorization as authz
from app.services import reports as reports_service

router = APIRouter()

# The `status` filter's accepted values — built at runtime from the service's re-exported
# `LEAVE_STATUS_VALUES` so no status LITERAL is typed in `api/` (AD-21, the `leave_requests.py`
# idiom). An unrecognized value is a framework `422`, never a domain error.
LeaveStatusFilter = enum.Enum(  # type: ignore[misc]
    "LeaveStatusFilter",
    {value: value for value in reports_service.LEAVE_STATUS_VALUES},
)


@router.get("/reports/leave.csv", tags=["reports"])
def export_leave_csv(
    status_filter: LeaveStatusFilter | None = Query(default=None, alias="status"),
    leave_type_id: uuid.UUID | None = Query(default=None),
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    actor: Actor = Depends(require_role(authz.ROLE_MANAGER, authz.ROLE_ADMIN)),
) -> Response:
    """Export leave as CSV, scoped and filtered (AC1–AC4). Manager and Admin only.

    Scope resolves from the caller's role in the service (Manager → their Direct Reports,
    EXCLUDING their own requests; Admin → every Employee — AD-10, a SQL predicate). The filters
    are Story 3.1's, verbatim: OVERLAP date window, inverted range or nonexistent
    `leave_type_id` → 200 with the header row only, malformed values → framework 422. Every
    matching row is exported — no page bound (FR-15 binds the filter set, not a page). The body
    is UTF-8 CSV, no BOM; `Content-Disposition` names the download (Open Decision #3).
    """
    csv_text = reports_service.export_leave_csv(
        actor,
        status=status_filter.value if status_filter is not None else None,
        leave_type_id=leave_type_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leave.csv"'},
    )
