"""The three role dashboards — scoped read services behind `/api/v1/dashboard/*` (Story 3.5).

Implements: FR-11 (a dashboard per role: the Employee's balances + own pending count, the
Manager's awaiting-decision count + Direct Reports on approved leave, the Admin's org-wide
figures), AD-10 (each figure is one scoped SQL aggregate — never a loop over reports, never
a Python-side filter; NFR-04), AD-16 (every figure derived per call, never stored), AD-8
(a dashboard read is not a transition: this module imports neither `audit_entry_repo` nor
`notification_repo` — zero audit rows, zero notifications, by construction). SM-6.

Read-only, deliberately (the `services/calendar.py` / `services/team.py` shape): one read
session per dashboard, opened, queried, closed, never committed. The Employee dashboard's
balances additionally reuse `balance_reads.list_own_balances` verbatim (an intra-layer
`services → services` import — contract 1 is a layers contract; the `services/calendar.py`
precedent), which owns its own short read session rather than re-reading `leave_balance`
here.

--- The decisions this module owns (and `api/` cannot) ---

1. Scope is HARDCODED per dashboard — `SELF` / `REPORTS` / `ALL` (the belt-and-braces
   `services/team.py` precedent): `Scope` lives in `repositories/`, which import-linter
   contract 2 forbids `api/` from importing, so the decision lives here, not in the route.
2. The status sets are FIXED server-side, exactly as `CALENDAR_STATUSES` is: the
   leave-presence figures read APPROVED, the queue figures read PENDING. No status query
   param exists, so no status name ever appears in `api/`.
3. The FR-11 default windows and their interaction with the caller's range (Open Decision
   #1): if BOTH `date_from`/`date_to` are absent, the FR-11 default window applies to the
   leave-presence figure ("the next seven days" / "today"); if EITHER is supplied, the
   supplied predicates apply verbatim and the default is not used (an absent side applies
   no predicate — the settled 3.1/3.3 rule, so a one-sided range leaves one end genuinely
   unbounded and the echoed window says so with a null). The PENDING-queue counts carry NO
   default window at all: a queue is WORK, not a report, and windowing it by default would
   silently hide requests awaiting decision — FR-11 attaches a window to the leave-presence
   figures only. The effective window is echoed back on the view so the UI's card label is
   DERIVED from what was actually computed, never a hard-coded string that becomes a lie
   the moment a range is supplied.

`available` is NOT computed here: the three stored quantities travel up in `BalanceView`
and `api/` derives it at the projection (DR-3, AD-5). The Manager's list bound arrives as
a `limit` parameter from the route — `services/` may not import `app.api.v1.pagination`
(an upward import breaks contract 1), so `api/` owns the bound and hands it down (the
`api/v1/team.py` → `services/team.py` shape).
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.repositories import dashboard as dashboard_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import balance_reads
from app.services.balance_reads import BalanceView

# The dashboards' fixed status sets (the `CALENDAR_STATUSES` posture): leave-presence
# figures read APPROVED; queue figures read PENDING. Fixed server-side — the client cannot
# widen or narrow them, and no status name ever appears in `api/`.
LEAVE_PRESENCE_STATUS: str = vocabulary.STATUS_APPROVED
QUEUE_STATUS: str = vocabulary.STATUS_PENDING


@dataclass(frozen=True)
class EmployeeDashboardView:
    """The Employee dashboard: the caller's own balances and pending count (FR-11).

    `balances` carries the three STORED quantities per Leave Type (`BalanceView`);
    `available` is derived at the `api/` projection, never here (DR-3). `leave_year` names
    which year's balances these are (Open Decision #2 made visible on the wire).
    """

    leave_year: int
    balances: list[BalanceView]
    pending_request_count: int


@dataclass(frozen=True)
class ReportOnLeaveView:
    """One Direct Report on approved leave — a PERSON, DISTINCT per Employee (Landmine 1)."""

    employee_id: uuid.UUID
    full_name: str


@dataclass(frozen=True)
class ManagerDashboardView:
    """The Manager dashboard: the queue count and the reports on approved leave (FR-11).

    `leave_window_from`/`leave_window_to` echo the EFFECTIVE window the leave-presence list
    was computed over — nullable, because a one-sided range leaves one end unbounded (Open
    Decision #1's stated consequence).

    `reports_on_leave_count` is the TRUE `COUNT(DISTINCT employee_id)` over the window —
    the SERVER figure the card's headline renders (code review 2026-07-15). The list beside
    it is `limit`-bounded, so its length is NOT the count: deriving the headline client-side
    from a truncated list understates the truth past the cap with no signal, which is both
    an AD-2/AD-18 violation ("the client computes NOTHING") and the one failure mode PRD §1
    names as worse than absence — a figure that is wrong and will be believed.
    """

    pending_decision_count: int
    reports_on_leave_count: int
    reports_on_approved_leave: list[ReportOnLeaveView]
    leave_window_from: datetime.date | None
    leave_window_to: datetime.date | None


@dataclass(frozen=True)
class AdminDashboardView:
    """The Admin dashboard: org-wide totals (FR-11). `pending_request_count` counts LEAVE
    Requests, never Cancellation Requests (settled twice — the Admin's CR queue at
    `GET /cancellation-requests` is their only CR surface, by 2.8's design)."""

    employees_on_approved_leave: int
    pending_request_count: int
    leave_window_from: datetime.date | None
    leave_window_to: datetime.date | None


def _today() -> datetime.date:
    """The clock lives in the shell, never in `domain/` (AD-1) — the
    `services/leave_requests.py` / `services/cancellation.py` posture.

    UTC, not server-local (code review 2026-07-15): every stored instant in this system
    (`created_at`, `occurred_at`) is UTC, so the dashboard's "today"/"next seven days" windows
    must flip at UTC midnight too — a server-local `date.today()` would make near-midnight
    dashboards disagree with the UTC-stamped lists they summarize on any host not running UTC.
    """
    return datetime.datetime.now(datetime.timezone.utc).date()


def _effective_window(
    date_from: datetime.date | None,
    date_to: datetime.date | None,
    *,
    default_from: datetime.date,
    default_to: datetime.date,
) -> tuple[datetime.date | None, datetime.date | None]:
    """Open Decision #1's rule, stated once: if BOTH params are absent, the FR-11 default
    window applies; if EITHER is supplied, the supplied predicates apply verbatim and the
    default is not used (an absent side applies no predicate — the settled 3.1/3.3 rule)."""
    if date_from is None and date_to is None:
        return default_from, default_to
    return date_from, date_to


def employee_dashboard(
    actor: Employee,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
) -> EmployeeDashboardView:
    """The caller's own dashboard (FR-11, scope SELF — role `any`: a Manager here sees
    THEIR OWN balances, never a report's, AC5).

    Balances are the caller's CURRENT Leave Year, ALWAYS, and are never date-filtered
    (Open Decision #2 / Landmine 3): a `leave_balance` row is keyed by an integer
    `leave_year`, not dates — a range does not select one. The range filters the pending
    count only, and that count carries NO default window (FR-11 attaches none). The year is
    read ONCE (DR-8: the Leave Year IS the calendar year) and passed into `list_own_balances`
    alongside THIS module's session (code review 2026-07-15): one clock read means the echoed
    `leave_year` always names the year the balances were read for (two independent reads
    could straddle a New Year midnight and label year-N data year-N+1), and one session means
    both figures come from one snapshot — a submit committing between two sessions would
    return pre-submit balances beside a post-submit pending count. The year-rollover cliff
    is owned by deferred-work.md and is not fixed here.
    """
    leave_year = _today().year
    with Session(get_engine(), expire_on_commit=False) as session:
        balances = balance_reads.list_own_balances(
            actor, session=session, leave_year=leave_year
        )
        pending = dashboard_repo.count_leave_requests(
            session,
            actor,
            scope=Scope.SELF,
            status=QUEUE_STATUS,
            date_from=date_from,
            date_to=date_to,
        )
    return EmployeeDashboardView(
        leave_year=leave_year,
        balances=balances,
        pending_request_count=pending,
    )


def manager_dashboard(
    actor: Employee,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
    *,
    limit: int,
) -> ManagerDashboardView:
    """The Manager's dashboard (FR-11, scope REPORTS — hardcoded here, the belt-and-braces
    `services/team.py` precedent; the route's gate already refused every non-Manager).

    `pending_decision_count` gets the SUPPLIED range only (no default — the queue is work);
    `reports_on_approved_leave` gets the EFFECTIVE window, defaulting to `today..today+6` —
    FR-11's "within the next seven days": seven calendar days, inclusive of today. The list
    is DISTINCT people (Landmine 1), name-ordered, bounded by the route-supplied `limit`
    (NFR-11). The REPORTS predicate carries no `is_active` filter (Open Decision #6,
    inherited from 3.2/3.3: a deactivated report's approved absence is still a fact about
    the team's dates) and can never match the Manager's own row.
    """
    today = _today()
    window_from, window_to = _effective_window(
        date_from,
        date_to,
        default_from=today,
        default_to=today + datetime.timedelta(days=6),
    )
    with Session(get_engine(), expire_on_commit=False) as session:
        pending = dashboard_repo.count_leave_requests(
            session,
            actor,
            scope=Scope.REPORTS,
            status=QUEUE_STATUS,
            date_from=date_from,
            date_to=date_to,
        )
        # The TRUE people-count, from the same aggregate the Admin dashboard uses — never
        # `len(rows)`, which is bounded by `limit` and silently understates past the cap.
        on_leave = dashboard_repo.count_employees_on_leave(
            session,
            actor,
            scope=Scope.REPORTS,
            status=LEAVE_PRESENCE_STATUS,
            date_from=window_from,
            date_to=window_to,
        )
        rows = dashboard_repo.list_employees_on_leave(
            session,
            actor,
            scope=Scope.REPORTS,
            status=LEAVE_PRESENCE_STATUS,
            date_from=window_from,
            date_to=window_to,
            limit=limit,
        )
    return ManagerDashboardView(
        pending_decision_count=pending,
        reports_on_leave_count=on_leave,
        reports_on_approved_leave=[
            ReportOnLeaveView(employee_id=employee_id, full_name=full_name)
            for employee_id, full_name in rows
        ],
        leave_window_from=window_from,
        leave_window_to=window_to,
    )


def admin_dashboard(
    actor: Employee,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
) -> AdminDashboardView:
    """The Admin's org-wide dashboard (FR-11, scope ALL — hardcoded; the route's gate
    already refused every non-Admin).

    `employees_on_approved_leave` is `COUNT(DISTINCT employee_id)` — PEOPLE, not requests
    (Landmine 1) — over the effective window, defaulting to `today..today` (FR-11's
    "today"). `pending_request_count` counts LEAVE Requests over the supplied range only —
    never Cancellation Requests (Landmine 5, settled twice) and never a default window.
    """
    today = _today()
    window_from, window_to = _effective_window(
        date_from, date_to, default_from=today, default_to=today
    )
    with Session(get_engine(), expire_on_commit=False) as session:
        on_leave = dashboard_repo.count_employees_on_leave(
            session,
            actor,
            scope=Scope.ALL,
            status=LEAVE_PRESENCE_STATUS,
            date_from=window_from,
            date_to=window_to,
        )
        pending = dashboard_repo.count_leave_requests(
            session,
            actor,
            scope=Scope.ALL,
            status=QUEUE_STATUS,
            date_from=date_from,
            date_to=date_to,
        )
    return AdminDashboardView(
        employees_on_approved_leave=on_leave,
        pending_request_count=pending,
        leave_window_from=window_from,
        leave_window_to=window_to,
    )
