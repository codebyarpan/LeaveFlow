"""The `/api/v1/dashboard/{employee,manager,admin}` reads — a dashboard per role (Story 3.5).

Implements: FR-11 / api-contracts §4.9 (`GET /dashboard/employee` | any | self;
`GET /dashboard/manager` | Manager | reports; `GET /dashboard/admin` | Admin | all), G3
(the wrong role is refused `403 ACTION_NOT_PERMITTED` by the gate in the dependency,
BEFORE any row is read), DR-3 / AD-5 (`available` is DERIVED at THIS projection —
`accrued − consumed − reserved` — never below, never stored), NFR-11 (the one list is
server-capped at `MAX_PAGE_SIZE`, declared here).

--- Three LITERAL paths, deliberately — never `GET /dashboard/{role}` ---

A parameterized route would (1) create a path param and drag these reads into the SM-3
scope matrix the three literal paths are OUT of by construction (the `/team`, `/calendar`,
`/notifications` precedent), and (2) turn AC5's role mismatch from the gate's 403 into a
scope-miss 404 — the wrong code under the G3 settlement ("does the actor's role admit them
to this endpoint at all? If no → 403, decided before any row is read"). Three routes,
three different gates:

- `/dashboard/employee` — `get_current_employee`: role `any`, scope `self` (the
  `GET /balances` shape). It can produce no 403 and no 404; a Manager here sees their OWN
  balances (AC5).
- `/dashboard/manager` — `require_role(MANAGER)`: the §4.9 inversion, third verse — the
  ADMIN is refused alongside the Employee (an Admin has their own dashboard; a team is a
  reporting edge only a Manager stands on).
- `/dashboard/admin` — `require_role(ADMIN)`.

--- Why THIS module supplies the Manager-list bound ---

`MAX_PAGE_SIZE` lives in `app.api.v1.pagination` — the TOP layer — and `services/` may not
import it (an upward `services → api` import breaks import-linter contract 1). So the
bound is the route's to supply, handed down as `limit=` (the `api/v1/team.py` →
`services/team.py` shape). A Manager's direct reports are inherently few; the cap exists
so NFR-11 holds by construction rather than by luck.

Role constants reach here through the sanctioned re-export (`services.authorization`), and
no status name or `Scope` appears in this module at all — those decisions live in
`services/dashboard.py` (contract 2; the `services/calendar.py` posture). A malformed date
is a framework `422` via the `datetime.date` typing; no error code is invented (the
settled 3.1 posture) and `main.py` is untouched.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.v1.balances import BalanceResponse
from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import MAX_PAGE_SIZE
from app.services import authorization as authz
from app.services import dashboard as dashboard_service

router = APIRouter()


class EmployeeDashboardResponse(BaseModel):
    """The Employee dashboard (FR-11): per-Leave-Type balances plus the caller's own
    PENDING count. `balances` reuses `BalanceResponse` byte-for-byte (the
    `LeaveRequestResponse`-into-`calendar.py` single-home precedent); `leave_year` names
    which year's balances these are."""

    leave_year: int
    balances: list[BalanceResponse]
    pending_request_count: int


class ReportOnLeaveResponse(BaseModel):
    """One Direct Report on approved leave — a person, not a request (Landmine 1). Exactly
    the two fields the card presents; dates are deliberately absent (a Manager who wants
    *when* has `GET /calendar`, rendered inline on the approval screen — the dashboard
    summarizes, the calendar details)."""

    employee_id: uuid.UUID
    full_name: str


class ManagerDashboardResponse(BaseModel):
    """The Manager dashboard (FR-11). `leave_window_from`/`leave_window_to` echo the
    EFFECTIVE window the list was computed over — nullable: a one-sided range leaves one
    end genuinely unbounded, and the wire says so rather than fabricate an end date.
    `reports_on_leave_count` is the SERVER's `COUNT(DISTINCT employee_id)` and is the card's
    headline figure (code review 2026-07-15): the list beside it is capped at
    `MAX_PAGE_SIZE`, so its length is not the count and the client must never derive one
    from it (AD-2/AD-18)."""

    pending_decision_count: int
    reports_on_leave_count: int
    reports_on_approved_leave: list[ReportOnLeaveResponse]
    leave_window_from: datetime.date | None
    leave_window_to: datetime.date | None


class AdminDashboardResponse(BaseModel):
    """The Admin dashboard (FR-11): org-wide totals. `pending_request_count` counts LEAVE
    Requests, never Cancellation Requests (settled twice — readiness report :565)."""

    employees_on_approved_leave: int
    pending_request_count: int
    leave_window_from: datetime.date | None
    leave_window_to: datetime.date | None


def _to_balance_response(balance: object) -> BalanceResponse:
    """Project a `BalanceView` into the response, DERIVING `available` here (DR-3, AD-5) —
    the `api/v1/balances.py` derivation, at this projection and nowhere lower. Typed
    `object` because `api/` may not import the service's dataclass (contract 2)."""
    available = balance.accrued - balance.consumed - balance.reserved  # type: ignore[attr-defined]
    return BalanceResponse(
        leave_type_code=balance.leave_type_code,  # type: ignore[attr-defined]
        leave_type_name=balance.leave_type_name,  # type: ignore[attr-defined]
        available=available,
        reserved=balance.reserved,  # type: ignore[attr-defined]
        consumed=balance.consumed,  # type: ignore[attr-defined]
    )


@router.get("/dashboard/employee", tags=["dashboard"])
def get_employee_dashboard(
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    caller: Actor = Depends(get_current_employee),
) -> EmployeeDashboardResponse:
    """The caller's own dashboard (AC1, AC5). Auth only, any role — `get_current_employee`,
    NOT `require_role`: scope `self` is intrinsic to the token subject (the `GET /balances`
    shape), so a Manager sees their OWN balances here, never a report's. Balances are the
    current Leave Year and are never date-filtered (a `leave_balance` row has no dates);
    the range narrows the pending count only. No token is `401`; no 403 and no 404 can
    happen here."""
    view = dashboard_service.employee_dashboard(caller, date_from, date_to)
    return EmployeeDashboardResponse(
        leave_year=view.leave_year,
        balances=[_to_balance_response(balance) for balance in view.balances],
        pending_request_count=view.pending_request_count,
    )


@router.get("/dashboard/manager", tags=["dashboard"])
def get_manager_dashboard(
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    manager: Actor = Depends(require_role(authz.ROLE_MANAGER)),
) -> ManagerDashboardResponse:
    """The Manager's dashboard (AC2, AC5). Manager-only — an Employee AND an Admin are
    `403 ACTION_NOT_PERMITTED`, decided in the dependency before any row is read (G3, the
    §4.9 inversion). The queue count is unwindowed by default; the reports-on-leave list
    defaults to the next seven days and is DISTINCT people, capped at `MAX_PAGE_SIZE`
    (NFR-11 — the bound is this route's to supply; `services/` may not import it)."""
    view = dashboard_service.manager_dashboard(
        manager, date_from, date_to, limit=MAX_PAGE_SIZE
    )
    return ManagerDashboardResponse(
        pending_decision_count=view.pending_decision_count,
        reports_on_leave_count=view.reports_on_leave_count,
        reports_on_approved_leave=[
            ReportOnLeaveResponse(employee_id=report.employee_id, full_name=report.full_name)
            for report in view.reports_on_approved_leave
        ],
        leave_window_from=view.leave_window_from,
        leave_window_to=view.leave_window_to,
    )


@router.get("/dashboard/admin", tags=["dashboard"])
def get_admin_dashboard(
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> AdminDashboardResponse:
    """The Admin's org-wide dashboard (AC3). Admin-only — a Manager AND an Employee are
    `403 ACTION_NOT_PERMITTED` from the gate (G3). Employees on approved leave is a
    DISTINCT count of people (default window "today"); the pending count is LEAVE Requests
    only, unwindowed by default."""
    view = dashboard_service.admin_dashboard(admin, date_from, date_to)
    return AdminDashboardResponse(
        employees_on_approved_leave=view.employees_on_approved_leave,
        pending_request_count=view.pending_request_count,
        leave_window_from=view.leave_window_from,
        leave_window_to=view.leave_window_to,
    )
