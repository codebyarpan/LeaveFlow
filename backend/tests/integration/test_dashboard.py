"""`GET /api/v1/dashboard/{employee,manager,admin}` — a dashboard per role (Story 3.5).

Implements the test side of:
- AC1 (FR-11): the Employee dashboard carries, per Leave Type, Available/Reserved/Consumed
  (Available DERIVED at the projection — proved by moving `reserved` and watching it drop)
  plus a count of the caller's own PENDING requests. Balances are NEVER date-filtered
  (Landmine 3 / Open Decision #2); `leave_year` travels so the year is visible.
- AC2 (FR-11, AD-10): the Manager dashboard counts PENDING requests from THEIR reports only,
  and lists their Direct Reports on APPROVED leave in the default `today..today+6` window —
  seven calendar days inclusive of today, both edges pinned (ends-on-day-6 IN, starts-on-day-7
  OUT). A report is a PERSON: two overlapping APPROVED requests appear exactly once
  (Landmine 1 — the DISTINCT is what this file proves real). A deactivated report is IN
  (Open Decision #6, the 3.2/3.3 inheritance).
- AC3 (FR-11): the Admin dashboard counts DISTINCT Employees on approved leave (default
  "today") and PENDING Leave Requests org-wide — a PENDING Cancellation Request seeded in
  the world moves NOTHING (Landmine 5, settled twice: readiness report :565/:819).
- AC4 (FR-11): a supplied `date_from`/`date_to` REPLACES the default window (Open Decision
  #1); an absent side applies no predicate (one-sided → the echoed window end is null); an
  inverted range is a well-formed `200` with zero figures (3.1 Open Decision #2, inherited).
- AC5 (FR-03, G3): `/dashboard/manager` refuses the Admin AND the Employee `403
  ACTION_NOT_PERMITTED` (the §4.9 inversion, third verse — Landmine 4); `/dashboard/admin`
  refuses Manager AND Employee; a Manager on `/dashboard/employee` gets **their own**
  balances, never a report's.
- AD-18: `leave_days` is stored, never recomputed — a request whose stored count (99)
  provably disagrees with its 3-calendar-day range flows through every dashboard figure
  untouched, and NO dashboard response carries a day count at all.

Rows are seeded by DIRECT repository-level inserts (the 3.1/3.3 precedent): read-only rows
need no submit-path validation, no balance reservation and write no audit row — SM-4's
exact ledger of 14 stays undisturbed. Because the dashboards' default windows are pinned to
`date.today()` ("today", "next seven days"), every seeded range is relative to TODAY — the
Epic-3 `_NEXT`-year convention would put every row outside both windows and pass vacuously
(Landmine 6). The clock is never mocked.

Teardown uses the plain app-role engine (the `test_team.py` shape): this file performs no
write through the API, so no audit row and no notification row ever exists for the owner
engine to be needed for. The one FK to mind is `cancellation_request → leave_request`
(Landmine 5's seeded PENDING CR), deleted first.

Against real PostgreSQL through the REAL app: importing `app.main` registers the v1 routes
and the error handler — skip it and every request 404s against an empty app (false green).
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import (
    CancellationRequest,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)

import app.main  # noqa: F401 — constructs the real app; without it every route 404s

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

_client = TestClient(app.main.app)

_KNOWN_PASSWORD = "correct-horse-battery-staple"

# Landmine 6: everything is relative to TODAY, because the default windows are. `_D(n)` is
# `today + n days`; requests seeded via direct insert never brush `PAST_DATE_RANGE`.
# UTC, matching the service's `_today()` (code review 2026-07-15): a local `date.today()` here
# makes every window-edge assertion off by one for the hours the host's local date and the UTC
# date disagree — the exact near-midnight drift the service fix exists to prevent.
_TODAY = datetime.datetime.now(datetime.timezone.utc).date()


def _d(days: int) -> datetime.date:
    return _TODAY + datetime.timedelta(days=days)


# The exact wire shapes this story fixes (Dev Notes → *The response shapes*). Accidental
# widening is a disclosure and fails the build (the 3.2/3.3/3.4 house rule).
_EMPLOYEE_KEYS = {"leave_year", "balances", "pending_request_count"}
_BALANCE_ITEM_KEYS = {
    "leave_type_code",
    "leave_type_name",
    "available",
    "reserved",
    "consumed",
}
_MANAGER_KEYS = {
    "pending_decision_count",
    "reports_on_leave_count",
    "reports_on_approved_leave",
    "leave_window_from",
    "leave_window_to",
}
_REPORT_ITEM_KEYS = {"employee_id", "full_name"}
_ADMIN_KEYS = {
    "employees_on_approved_leave",
    "pending_request_count",
    "leave_window_from",
    "leave_window_to",
}

# AD-18's non-vacuous pin: a 3-calendar-day range whose stored `leave_days` is 99 — no
# recomputation could produce it; the dashboards never surface OR recompute a day count.
_STORED_DISAGREES = 99


class _Member:
    """One seeded Employee: its id, and (when the test calls as them) a token."""

    def __init__(self, employee_id: uuid.UUID, token: str) -> None:
        self.id = employee_id
        self.token = token


class _World:
    """The topology + request/balance rows the ACs need.

    - `manager_m` — the Manager under test; reports `r1`, `r2`, `r3`, and `r4` (deactivated).
    - `other_manager` / `other_report` — a second reporting edge (scope exclusion).
    - `admin` and a scope-less `employee` — the role-gate cases and the AC1 caller.
    - Two Leave Types: `lt_a` hosts every request and the employee/r1 balances; `lt_b`
      holds the MANAGER's only balance — so AC5's "their own balances, not their reports'"
      is a key-set fact (the manager's response names `lt_b` and never `lt_a`).
    """

    def __init__(self) -> None:
        self.suffix: str = ""
        self.lt_a_id: uuid.UUID = None  # type: ignore[assignment]
        self.lt_a_code: str = ""
        self.lt_b_id: uuid.UUID = None  # type: ignore[assignment]
        self.lt_b_code: str = ""
        self.admin: _Member = None  # type: ignore[assignment]
        self.employee: _Member = None  # type: ignore[assignment]
        self.manager_m: _Member = None  # type: ignore[assignment]
        self.other_manager: _Member = None  # type: ignore[assignment]
        self.other_report: _Member = None  # type: ignore[assignment]
        self.r1: _Member = None  # type: ignore[assignment]
        self.r2: _Member = None  # type: ignore[assignment]
        self.r3: _Member = None  # type: ignore[assignment]
        self.r4: _Member = None  # type: ignore[assignment]


def _insert_request(
    session: Session,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
    *,
    status: str,
    leave_days: int = 3,
) -> str:
    """Seed one request row at repository level (the 3.1/3.3 precedent).

    A read-only dashboard row needs no balance and writes no audit row — the fixture cleans
    up only what it created and SM-4's exact-count ledger is undisturbed. `leave_days` is any
    positive frozen figure; no dashboard figure reads it (AD-18).
    """
    row = LeaveRequest(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        start_date=start,
        end_date=end,
        leave_days=leave_days,
        status=status,
    )
    session.add(row)
    session.flush()
    return str(row.id)


def _insert_balance(
    session: Session,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    *,
    reserved: int,
    consumed: int,
) -> None:
    """One current-Leave-Year balance row: accrued 20 (= prorated 20 + carried 0), so the
    composition CHECK holds and `available = 20 − consumed − reserved` is the derivation
    AC1 watches."""
    session.add(
        LeaveBalance(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=_TODAY.year,
            accrued=20,
            prorated_entitlement=20,
            carried_forward=0,
            entitlement_basis=20,
            reserved=reserved,
            consumed=consumed,
        )
    )


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """Build the topology, the requests around today's default windows, the balances, and
    Landmine 5's PENDING Cancellation Request. Teardown nulls `manager_id` first (self-FK
    RESTRICT) and runs as the app role — this file writes no audit or notification row."""
    suffix = uuid.uuid4().hex[:12]
    department_name = f"dash-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)
    built = _World()
    built.suffix = suffix

    def _insert_employee(
        session: Session,
        label: str,
        role: str,
        *,
        manager_id: uuid.UUID | None = None,
        is_active: bool = True,
        department_id: uuid.UUID,
    ) -> _Member:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"dash-{label}-{suffix}@example.com",
            full_name=f"Dash {label}",
            role=role,
            joining_date=datetime.date(2026, 1, 1),
            is_active=is_active,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        return _Member(employee.id, security.create_token(str(employee.id), role))

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
        dept_id = department.id

        built.admin = _insert_employee(
            session, "admin", vocabulary.ROLE_ADMIN, department_id=dept_id
        )
        built.employee = _insert_employee(
            session, "employee", vocabulary.ROLE_EMPLOYEE, department_id=dept_id
        )
        built.manager_m = _insert_employee(
            session, "manager-m", vocabulary.ROLE_MANAGER, department_id=dept_id
        )
        built.other_manager = _insert_employee(
            session, "other-manager", vocabulary.ROLE_MANAGER, department_id=dept_id
        )
        built.other_report = _insert_employee(
            session,
            "other-report",
            vocabulary.ROLE_EMPLOYEE,
            manager_id=built.other_manager.id,
            department_id=dept_id,
        )
        for label in ("r1", "r2", "r3"):
            setattr(
                built,
                label,
                _insert_employee(
                    session,
                    label,
                    vocabulary.ROLE_EMPLOYEE,
                    manager_id=built.manager_m.id,
                    department_id=dept_id,
                ),
            )
        built.r4 = _insert_employee(
            session,
            "r4",
            vocabulary.ROLE_EMPLOYEE,
            manager_id=built.manager_m.id,
            is_active=False,
            department_id=dept_id,
        )

        lt_a = LeaveType(
            code=f"DSA-{suffix}",
            name="Dashboard type A",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        lt_b = LeaveType(
            code=f"DSB-{suffix}",
            name="Dashboard type B",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        session.add_all([lt_a, lt_b])
        session.flush()
        built.lt_a_id, built.lt_a_code = lt_a.id, lt_a.code
        built.lt_b_id, built.lt_b_code = lt_b.id, lt_b.code
        lt = lt_a.id

        # --- Balances (current Leave Year; accrued 20 = prorated 20 + carried 0) ----------
        # employee: available = 20 − 5 − 3 = 12. r1's numbers differ from the manager's so a
        # scope leak would be visible in the figures, not just the key set.
        _insert_balance(session, built.employee.id, lt, reserved=3, consumed=5)
        _insert_balance(session, built.r1.id, lt, reserved=7, consumed=1)
        # The MANAGER's only balance lives on lt_b: available = 20 − 2 − 1 = 17 (AC5).
        _insert_balance(session, built.manager_m.id, built.lt_b_id, reserved=1, consumed=2)

        # --- APPROVED leave around the default windows -------------------------------------
        # r1 holds TWO overlapping APPROVED requests (deferred-work.md:50 — nothing forbids
        # it): the DISTINCT pin (Landmine 1). The first is also AD-18's 99-days-over-3 pin.
        _insert_request(  # ids unused: dashboard responses never carry request ids
            session, built.r1.id, lt, _d(0), _d(2),
            status=vocabulary.STATUS_APPROVED, leave_days=_STORED_DISAGREES,
        )
        _insert_request(
            session, built.r1.id, lt, _d(1), _d(2),
            status=vocabulary.STATUS_APPROVED,
        )
        # r2 ends EXACTLY on today+6 — the default window's far edge, IN (AC2 boundary).
        _insert_request(
            session, built.r2.id, lt, _d(4), _d(6),
            status=vocabulary.STATUS_APPROVED,
        )
        # r3 starts EXACTLY on today+7 — one past the default window, OUT (AC2 boundary).
        _insert_request(
            session, built.r3.id, lt, _d(7), _d(9),
            status=vocabulary.STATUS_APPROVED,
        )
        # r4 is DEACTIVATED and on leave today — IN (Open Decision #6, inherited from 3.2/3.3).
        _insert_request(
            session, built.r4.id, lt, _d(0), _d(1),
            status=vocabulary.STATUS_APPROVED,
        )
        # The manager's OWN approved leave — never in REPORTS; org-wide for the Admin.
        _insert_request(
            session, built.manager_m.id, lt, _d(0), _d(1),
            status=vocabulary.STATUS_APPROVED,
        )
        # The other manager's report, on leave today — out of manager_m's scope; org-wide in.
        _insert_request(
            session, built.other_report.id, lt, _d(0), _d(1),
            status=vocabulary.STATUS_APPROVED,
        )

        # --- PENDING requests (the queue figures) ------------------------------------------
        # employee's own two: one near today, one far out (AC4's range filter).
        _insert_request(
            session, built.employee.id, lt, _d(0), _d(2),
            status=vocabulary.STATUS_PENDING,
        )
        _insert_request(
            session, built.employee.id, lt, _d(30), _d(32),
            status=vocabulary.STATUS_PENDING,
        )
        # manager_m's queue: r1 near, r2 far — pending_decision_count == 2, unwindowed.
        _insert_request(
            session, built.r1.id, lt, _d(0), _d(1),
            status=vocabulary.STATUS_PENDING,
        )
        _insert_request(
            session, built.r2.id, lt, _d(30), _d(31),
            status=vocabulary.STATUS_PENDING,
        )
        # The other manager's queue: excluded from manager_m's count; in the Admin's 5.
        _insert_request(
            session, built.other_report.id, lt, _d(0), _d(1),
            status=vocabulary.STATUS_PENDING,
        )

        # --- Landmine 5: a PENDING Cancellation Request exists the whole time ---------------
        # It targets r4's APPROVED request and must move NO dashboard figure: the Admin's
        # "Pending request count" is LEAVE Requests (settled twice — readiness :565, :819).
        cr_target = _insert_request(
            session, built.r4.id, lt, _d(40), _d(41),
            status=vocabulary.STATUS_APPROVED,
        )
        session.add(
            CancellationRequest(
                leave_request_id=uuid.UUID(cr_target),
                status=vocabulary.STATUS_PENDING,
            )
        )
        session.commit()

    try:
        yield built
    finally:
        with Session(get_engine()) as session:
            like = f"%{suffix}%"
            # FK order: the seeded PENDING Cancellation Request references a leave_request
            # row (Landmine 5), so it goes first.
            for lt_id in (built.lt_a_id, built.lt_b_id):
                session.execute(
                    delete(CancellationRequest).where(
                        CancellationRequest.leave_request_id.in_(
                            select(LeaveRequest.id).where(
                                LeaveRequest.leave_type_id == lt_id
                            )
                        )
                    )
                )
                session.execute(
                    delete(LeaveRequest).where(LeaveRequest.leave_type_id == lt_id)
                )
                session.execute(
                    delete(LeaveBalance).where(LeaveBalance.leave_type_id == lt_id)
                )
            session.execute(
                update(Employee).where(Employee.email.like(like)).values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(like)))
            session.execute(
                delete(LeaveType).where(
                    LeaveType.id.in_([built.lt_a_id, built.lt_b_id])
                )
            )
            session.execute(
                delete(Department).where(Department.name == department_name)
            )
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _get(path: str, token: str | None, **params: object) -> object:
    return _client.get(f"/api/v1/dashboard/{path}", params=params, headers=_auth(token))


def _dashboard(path: str, token: str, **params: object) -> dict:
    response = _get(path, token, **params)
    assert response.status_code == 200, response.text
    return response.json()


def _no_key_anywhere(payload: object, key: str) -> bool:
    """True iff `key` appears in NO dict anywhere in the (nested) JSON payload."""
    if isinstance(payload, dict):
        if key in payload:
            return False
        return all(_no_key_anywhere(value, key) for value in payload.values())
    if isinstance(payload, list):
        return all(_no_key_anywhere(item, key) for item in payload)
    return True


# --- AC1: the Employee dashboard ---------------------------------------------------------------


def test_employee_dashboard_carries_balances_and_own_pending_count(world: _World) -> None:
    """AC1: per Leave Type Available/Reserved/Consumed plus the caller's own PENDING count.
    The exact key set is pinned at both levels (widening is a disclosure and fails the
    build); `leave_year` is the current Leave Year (Decision #2 made visible); the pending
    count is UNWINDOWED by default (Decision #1 — a queue is work, not a report)."""
    body = _dashboard("employee", world.employee.token)

    assert set(body) == _EMPLOYEE_KEYS
    assert body["leave_year"] == _TODAY.year
    assert body["pending_request_count"] == 2

    assert len(body["balances"]) == 1
    balance = body["balances"][0]
    assert set(balance) == _BALANCE_ITEM_KEYS
    assert balance["leave_type_code"] == world.lt_a_code
    assert balance["leave_type_name"] == "Dashboard type A"
    assert balance["available"] == 12  # 20 accrued − 5 consumed − 3 reserved
    assert balance["reserved"] == 3
    assert balance["consumed"] == 5


def test_available_is_derived_not_stored(world: _World) -> None:
    """AC1: `available` is DERIVED at the projection (DR-3/AD-5) — move `reserved` under the
    caller and the figure drops by exactly the delta on the next read, with no other field
    moving (the `test_balances_read.py` precedent)."""
    before = _dashboard("employee", world.employee.token)
    assert before["balances"][0]["available"] == 12

    with Session(get_engine()) as session:
        session.execute(
            update(LeaveBalance)
            .where(
                LeaveBalance.employee_id == world.employee.id,
                LeaveBalance.leave_type_id == world.lt_a_id,
            )
            .values(reserved=5)
        )
        session.commit()

    after = _dashboard("employee", world.employee.token)
    assert after["balances"][0]["available"] == 10  # 20 − 5 − 5
    assert after["balances"][0]["reserved"] == 5
    assert after["balances"][0]["consumed"] == 5


def test_balances_are_never_date_filtered(world: _World) -> None:
    """AC4 × Landmine 3: a `leave_balance` row has no dates — a supplied range narrows the
    PENDING count and leaves the balances byte-identical (Decision #2). The far-out pending
    request drops; the balance row does not."""
    body = _dashboard(
        "employee",
        world.employee.token,
        date_from=_d(0).isoformat(),
        date_to=_d(3).isoformat(),
    )

    assert body["pending_request_count"] == 1  # the day-30 request no longer overlaps
    assert len(body["balances"]) == 1
    assert body["balances"][0]["available"] == 12  # unmoved by the range
    assert body["leave_year"] == _TODAY.year


# --- AC2: the Manager dashboard ------------------------------------------------------------------


def test_manager_pending_count_is_exactly_their_reports_queue(world: _World) -> None:
    """AC2: `pending_decision_count` counts PENDING requests from manager_m's reports and
    NOBODY else's — the world holds 5 PENDING rows (r1, r2, the employee's two, the other
    manager's report), and the scoped count is exactly the 2 from r1 and r2. Unwindowed by
    default (Decision #1)."""
    body = _dashboard("manager", world.manager_m.token)

    assert set(body) == _MANAGER_KEYS
    assert body["pending_decision_count"] == 2


def test_reports_on_approved_leave_defaults_to_the_next_seven_days(world: _World) -> None:
    """AC2: the default window is `today..today+6` — seven calendar days inclusive of today
    — and the list is DISTINCT Employees ordered by name. Both edges pinned: r2's leave ends
    EXACTLY on day 6 (in); r3's starts EXACTLY on day 7 (out). r4 is deactivated and IN
    (Decision #6). The manager's own leave and the other manager's report are absent (the
    REPORTS predicate). The effective window is echoed so the UI label is derived."""
    body = _dashboard("manager", world.manager_m.token)

    items = body["reports_on_approved_leave"]
    for item in items:
        assert set(item) == _REPORT_ITEM_KEYS
    returned = {item["employee_id"] for item in items}

    assert returned == {str(world.r1.id), str(world.r2.id), str(world.r4.id)}
    # Explicit exclusions, named one by one.
    assert str(world.r3.id) not in returned  # starts day 7 — one past the edge
    assert str(world.manager_m.id) not in returned  # REPORTS never matches self
    assert str(world.other_report.id) not in returned  # the other manager's edge
    assert str(world.employee.id) not in returned  # reports to nobody

    # The headline figure is the SERVER's DISTINCT people-count (code review 2026-07-15) —
    # here it agrees with the list because the world sits far below the cap; the point of the
    # field is that past the cap it would NOT, and the client renders it, never `len(items)`.
    assert body["reports_on_leave_count"] == 3

    names = [item["full_name"] for item in items]
    assert names == sorted(names)  # ordered by full_name

    assert body["leave_window_from"] == _d(0).isoformat()
    assert body["leave_window_to"] == _d(6).isoformat()


def test_a_double_booked_report_appears_exactly_once(world: _World) -> None:
    """AC2 × Landmine 1: r1 holds TWO overlapping APPROVED requests (nothing forbids it —
    deferred-work.md:50) and appears EXACTLY once. Without the DISTINCT this ships a
    double-count; this test is what proves the DISTINCT is real."""
    body = _dashboard("manager", world.manager_m.token)

    ids = [item["employee_id"] for item in body["reports_on_approved_leave"]]
    assert ids.count(str(world.r1.id)) == 1
    assert len(ids) == len(set(ids))


# --- AC3: the Admin dashboard --------------------------------------------------------------------


def test_admin_dashboard_defaults_to_today_org_wide(world: _World) -> None:
    """AC3: org-wide, default window "today" — the DISTINCT Employees whose APPROVED leave
    covers today are r1, r4, the manager, and the other manager's report (4 people), and the
    org-wide PENDING count is all 5 LEAVE requests. The seeded PENDING Cancellation Request
    moves neither figure (Landmine 5 — settled twice; 2.8's Admin queue is the only CR
    surface). The effective window is echoed."""
    body = _dashboard("admin", world.admin.token)

    assert set(body) == _ADMIN_KEYS
    assert body["employees_on_approved_leave"] == 4
    assert body["pending_request_count"] == 5
    assert body["leave_window_from"] == _d(0).isoformat()
    assert body["leave_window_to"] == _d(0).isoformat()


def test_admin_counts_a_double_booked_employee_once(world: _World) -> None:
    """AC3 × Landmine 1: over `today..today+2` r1's TWO overlapping APPROVED requests count
    as ONE Employee — a naive `COUNT(*)` would say 5 (r1 twice + r4 + manager + other
    report); the requirement's number is 4 people."""
    body = _dashboard(
        "admin",
        world.admin.token,
        date_from=_d(0).isoformat(),
        date_to=_d(2).isoformat(),
    )

    assert body["employees_on_approved_leave"] == 4


# --- AC4: the date-range filter ------------------------------------------------------------------


def test_a_supplied_range_replaces_the_default_window(world: _World) -> None:
    """AC4 × Decision #1: `date_from/date_to` REPLACE the default window on every figure.
    Over `today+7..today+9`: the Manager's list is exactly r3 (outside the default, inside
    the supplied range), the pending counts are 0 (no PENDING row overlaps), the Admin's
    people-count is 1, and both responses echo the supplied window verbatim."""
    manager = _dashboard(
        "manager",
        world.manager_m.token,
        date_from=_d(7).isoformat(),
        date_to=_d(9).isoformat(),
    )
    returned = {item["employee_id"] for item in manager["reports_on_approved_leave"]}
    assert returned == {str(world.r3.id)}
    assert manager["pending_decision_count"] == 0
    assert manager["leave_window_from"] == _d(7).isoformat()
    assert manager["leave_window_to"] == _d(9).isoformat()

    admin = _dashboard(
        "admin",
        world.admin.token,
        date_from=_d(7).isoformat(),
        date_to=_d(9).isoformat(),
    )
    assert admin["employees_on_approved_leave"] == 1
    assert admin["pending_request_count"] == 0


def test_a_one_sided_range_leaves_one_end_unbounded(world: _World) -> None:
    """AC4 × Decision #1's stated consequence: `date_from` alone applies `end_date >=
    date_from` with NO upper bound — r3's leave (days 7–9), r4's leave arbitrarily far out
    (days 40–41, the CR target), and r2's far-out PENDING request (days 30–31) are ALL in —
    and the echoed window's upper end is null, so the UI can say "from … onwards" rather
    than invent an end date."""
    body = _dashboard(
        "manager", world.manager_m.token, date_from=_d(7).isoformat()
    )

    returned = {item["employee_id"] for item in body["reports_on_approved_leave"]}
    assert returned == {str(world.r3.id), str(world.r4.id)}
    assert body["pending_decision_count"] == 1  # r2's day-30 request; r1's ended day 1
    assert body["leave_window_from"] == _d(7).isoformat()
    assert body["leave_window_to"] is None


def test_an_inverted_range_is_200_with_zero_figures(world: _World) -> None:
    """AC4 × Decision #11: `date_from > date_to` is a well-formed empty intersection — 200
    with zero figures on all three dashboards, never a 422 (3.1's ruling, zero code). The
    Employee's balances are STILL present: they are never date-filtered (Decision #2)."""
    inverted = {"date_from": _d(9).isoformat(), "date_to": _d(0).isoformat()}

    employee = _dashboard("employee", world.employee.token, **inverted)
    assert employee["pending_request_count"] == 0
    assert len(employee["balances"]) == 1  # untouched by any range

    manager = _dashboard("manager", world.manager_m.token, **inverted)
    assert manager["pending_decision_count"] == 0
    assert manager["reports_on_approved_leave"] == []

    admin = _dashboard("admin", world.admin.token, **inverted)
    assert admin["employees_on_approved_leave"] == 0
    assert admin["pending_request_count"] == 0


def test_a_malformed_date_is_a_framework_422(world: _World) -> None:
    """A malformed date rides the pinned framework-422 path (bare FastAPI `{"detail": ...}`)
    via the `datetime.date` typing — no error code is invented (the settled 3.1 posture)."""
    response = _get("employee", world.employee.token, date_from="not-a-date")

    assert response.status_code == 422
    assert "detail" in response.json()  # the framework shape, not the domain envelope


# --- AC5: the mixed gate -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "denied"),
    [
        ("manager", "admin"),  # the §4.9 inversion, third verse (Landmine 4)
        ("manager", "employee"),
        ("admin", "manager_m"),
        ("admin", "employee"),
    ],
)
def test_the_wrong_role_is_refused_403_with_the_envelope(
    world: _World, path: str, denied: str
) -> None:
    """AC5 (G3): the role gate refuses BEFORE any row is read — `403 ACTION_NOT_PERMITTED`
    with the full `{code, message, details}` envelope and empty details. The Admin refusal
    on `/dashboard/manager` is the contract's inversion: an Admin has their own dashboard;
    a team is a reporting edge only a Manager stands on."""
    caller: _Member = getattr(world, denied)

    response = _get(path, caller.token)

    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.ACTION_NOT_PERMITTED
    assert body["details"] == {}


def test_a_manager_on_the_employee_dashboard_sees_their_own_balances(
    world: _World,
) -> None:
    """AC5: `/dashboard/employee` is role `any`, scope `self` — a Manager gets 200 carrying
    THEIR OWN balances (lt_b, available 17 = 20−2−1), never a report's (r1's lt_a row is
    absent), and their own pending count (0 — the queue rows are their REPORTS', not
    theirs)."""
    body = _dashboard("employee", world.manager_m.token)

    codes = {item["leave_type_code"] for item in body["balances"]}
    assert codes == {world.lt_b_code}  # their own; r1's lt_a is absent
    assert body["balances"][0]["available"] == 17
    assert body["balances"][0]["reserved"] == 1
    assert body["balances"][0]["consumed"] == 2
    assert body["pending_request_count"] == 0


@pytest.mark.parametrize("path", ["employee", "manager", "admin"])
def test_an_absent_token_is_401_not_403(world: _World, path: str) -> None:
    """No token → 401 (`require_role` and `get_current_employee` both authenticate first;
    a missing token is never turned into a 403)."""
    response = _get(path, None)

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- AD-18: the stored day count is never recomputed — or surfaced -------------------------------


def test_no_dashboard_recomputes_or_surfaces_a_day_count(world: _World) -> None:
    """AD-18 names the dashboard by name: every read path "reads the stored value and never
    recomputes it." r1's in-window request stores `leave_days == 99` over a 3-calendar-day
    range — a figure no recomputation could produce. All three dashboards return 200 with
    r1 present where scope admits, and NO response carries a `leave_days` (or any day count)
    anywhere — the dashboards aggregate people and requests, never days."""
    manager = _dashboard("manager", world.manager_m.token)
    assert str(world.r1.id) in {
        item["employee_id"] for item in manager["reports_on_approved_leave"]
    }

    employee = _dashboard("employee", world.employee.token)
    admin = _dashboard("admin", world.admin.token)

    for payload in (manager, employee, admin):
        assert _no_key_anywhere(payload, "leave_days")
