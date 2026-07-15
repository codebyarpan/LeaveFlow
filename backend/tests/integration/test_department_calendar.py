"""`GET /api/v1/calendar` — the Department Leave Calendar, at the moment of decision (Story 3.3).

Implements the test side of:
- AC1 (FR-18, AD-10): a Manager's calendar is their Direct Reports' PENDING + APPROVED leave
  overlapping the range — and NOBODY else's. REJECTED/CANCELLED are absent (the status set is
  fixed server-side, Open Decision #4), the other manager's report is absent (the REPORTS SQL
  predicate), and the Manager's OWN leave is absent (`manager_id == actor.id` can never match
  self — the keep-REPORTS invariant `test_leave_request_decide.py:602` pinned and
  `test_leave_request_history.py:469` re-held).
- AC2 (FR-18): both statuses are on the wire, each row carrying its status verbatim — the
  visual distinction is the status word the frontend renders as received.
- AC4 (BR-06, DR-15, Landmine 7): with two reports already APPROVED across a date, approving a
  third report's overlapping PENDING request through the REAL decide endpoint is a plain 200
  with the pre-story response keys — no warning field, no block, no acknowledgement round-trip.
  The calendar informs; the decision endpoint decides.
- AC5 (AD-18): `leave_days` is the STORED figure, returned verbatim — a row seeded with a count
  that provably disagrees with any recomputation of its short range proves no read recomputes.
- The binding §4.9 contract (the 3.2 inversion, second verse): `/calendar` is Manager-ONLY —
  an Employee AND an Admin get `403 ACTION_NOT_PERMITTED` with the full envelope from the role
  gate, before any row is read (G3).
- Landmine 5: overlap semantics are the SETTLED 3.1 ones (`end_date >= date_from AND
  start_date <= date_to`, each side optional) — straddlers in, the ends-day-before row out,
  inverted range a well-formed 200-empty, a Dec-31 straddler returned for a cross-year window.
- Open Decision #3: a DEACTIVATED report's leave is IN — the REPORTS predicate carries no
  `is_active` filter, and an approved absence is still a fact about the team's dates.

Calendar rows are seeded by DIRECT repository-level inserts (the 3.1 precedent — read-only
rows need no balance and write no audit rows, leaving SM-4's ledger undisturbed). The ONE
exception is `r3`'s PENDING request, which AC4 approves through the real endpoint: `_decide`
calls `balances.consume_reserved` under the balance lock, so its (employee, type, year)
balance row is seeded with `reserved == leave_days` — a missing row would be a raw-500
`LookupError`, and "fixing" that in `_decide` would violate Landmine 7.

Against real PostgreSQL through the REAL app: importing `app.main` registers the v1 routes
and the error handler — skip it and every request 404s against an empty app (false green).

Named `test_department_calendar.py`, NOT the story's `test_calendar.py`: `tests/domain/
test_calendar.py` (Story 2.3's pure day-count tests) already owns that basename, and the test
tree has no `__init__.py` packages — a duplicate basename is a pytest "import file mismatch"
collection error that aborts the WHOLE suite. A declared deviation (Dev Agent Record);
renaming 2.3's pinned file was not an option.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, delete, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import (
    AuditEntry,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
)

import app.main  # noqa: F401 — constructs the real app; without it every route 404s

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

_client = TestClient(app.main.app)

_KNOWN_PASSWORD = "correct-horse-battery-staple"

# Every seeded range lies NEXT year, so AC4's approve-through-the-real-endpoint never brushes
# any past-date rule and no clock is ever mocked. `_NEXT + 1` hosts the cross-year straddler's
# far end.
_NEXT = datetime.date.today().year + 1

# The window every in-range assertion queries: [Mar 10, Mar 20] of next year.
_FROM = datetime.date(_NEXT, 3, 10)
_TO = datetime.date(_NEXT, 3, 20)

# The exact wire shape (Open Decision #1): `LeaveRequestResponse`, byte-for-byte — reused, not
# narrowed. Accidental widening (or a per-caller marker field) fails this pin.
_EXPECTED_ITEM_KEYS = {
    "id",
    "employee_id",
    "employee_name",
    "leave_type_id",
    "leave_type_code",
    "leave_type_name",
    "start_date",
    "end_date",
    "leave_days",
    "status",
}

# AC5's non-vacuous pin: a 3-calendar-day range whose stored `leave_days` is 99 — no
# recomputation of that range could produce it, so 99 on the wire proves the read is stored-only.
_STORED_DISAGREES = 99


class _Member:
    """One seeded Employee: its id, and (when the test calls as them) a token."""

    def __init__(self, employee_id: uuid.UUID, token: str) -> None:
        self.id = employee_id
        self.token = token


class _World:
    """The topology + calendar rows the ACs need.

    - `manager_m` — the Manager under test; reports `r1`, `r2`, `r3`, and `r4` (deactivated).
    - `other_manager` / `other_report` — a second reporting edge (scope exclusion).
    - `admin` and a scope-less `employee` — the two roles the gate refuses (the §4.9 inversion).
    - Request rows: see the fixture body; each id is kept so assertions name rows exactly.
    """

    def __init__(self) -> None:
        self.suffix: str = ""
        self.leave_type_id: uuid.UUID = None  # type: ignore[assignment]
        self.admin: _Member = None  # type: ignore[assignment]
        self.employee: _Member = None  # type: ignore[assignment]
        self.manager_m: _Member = None  # type: ignore[assignment]
        self.other_manager: _Member = None  # type: ignore[assignment]
        self.other_report: _Member = None  # type: ignore[assignment]
        self.r1: _Member = None  # type: ignore[assignment]
        self.r2: _Member = None  # type: ignore[assignment]
        self.r3: _Member = None  # type: ignore[assignment]
        self.r4: _Member = None  # type: ignore[assignment]
        # Request row ids (str, as the wire carries them).
        self.r1_approved: str = ""
        self.r2_approved: str = ""
        self.r3_pending: str = ""
        self.r3_pending_days: int = 0
        self.r1_rejected: str = ""
        self.r2_cancelled: str = ""
        self.other_approved: str = ""
        self.r4_approved: str = ""
        self.mgr_own_approved: str = ""
        self.straddles_from: str = ""
        self.straddles_to: str = ""
        self.ends_before_from: str = ""
        self.cross_year: str = ""


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
    """Seed one request row at repository level (the 3.1 precedent).

    A read-only calendar row needs no balance and writes no audit row — the fixture cleans up
    only what it created and SM-4's exact-count ledger is undisturbed. `leave_days` is any
    positive frozen figure; the read path returns it verbatim (AD-18).
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


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """Build the topology and every calendar row; teardown nulls `manager_id` first (self-FK
    RESTRICT) and runs as the OWNER (the app role cannot delete the audit row AC4's approve
    writes — that refusal IS Story 2.9's AC3 working)."""
    suffix = uuid.uuid4().hex[:12]
    department_name = f"cal-dept-{suffix}"
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
            email=f"cal-{label}-{suffix}@example.com",
            full_name=f"Cal {label}",
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

        leave_type = LeaveType(
            code=f"CAL-{suffix}",
            name="Calendar type",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        session.add(leave_type)
        session.flush()
        built.leave_type_id = leave_type.id
        lt = leave_type.id

        # --- The calendar rows (all NEXT year; window [Mar 10, Mar 20]) --------------------
        # In-window, PENDING+APPROVED — the rows AC1 returns:
        built.r1_approved = _insert_request(  # AC5's pin: 99 days over a 3-day range
            session, built.r1.id, lt,
            datetime.date(_NEXT, 3, 14), datetime.date(_NEXT, 3, 16),
            status=vocabulary.STATUS_APPROVED, leave_days=_STORED_DISAGREES,
        )
        built.r2_approved = _insert_request(
            session, built.r2.id, lt,
            datetime.date(_NEXT, 3, 15), datetime.date(_NEXT, 3, 17),
            status=vocabulary.STATUS_APPROVED,
        )
        built.r4_approved = _insert_request(  # deactivated report — IN (Open Decision #3)
            session, built.r4.id, lt,
            datetime.date(_NEXT, 3, 11), datetime.date(_NEXT, 3, 12),
            status=vocabulary.STATUS_APPROVED,
        )
        built.straddles_from = _insert_request(  # overlaps the window's left edge
            session, built.r1.id, lt,
            datetime.date(_NEXT, 3, 5), datetime.date(_NEXT, 3, 12),
            status=vocabulary.STATUS_APPROVED,
        )
        built.straddles_to = _insert_request(  # overlaps the window's right edge
            session, built.r2.id, lt,
            datetime.date(_NEXT, 3, 18), datetime.date(_NEXT, 3, 25),
            status=vocabulary.STATUS_APPROVED,
        )
        # In-window but excluded by the fixed status set:
        built.r1_rejected = _insert_request(
            session, built.r1.id, lt,
            datetime.date(_NEXT, 3, 11), datetime.date(_NEXT, 3, 12),
            status=vocabulary.STATUS_REJECTED,
        )
        built.r2_cancelled = _insert_request(
            session, built.r2.id, lt,
            datetime.date(_NEXT, 3, 11), datetime.date(_NEXT, 3, 12),
            status=vocabulary.STATUS_CANCELLED,
        )
        # In-window but out of scope:
        built.other_approved = _insert_request(  # the other manager's report
            session, built.other_report.id, lt,
            datetime.date(_NEXT, 3, 14), datetime.date(_NEXT, 3, 16),
            status=vocabulary.STATUS_APPROVED,
        )
        built.mgr_own_approved = _insert_request(  # the Manager's OWN leave — never in REPORTS
            session, built.manager_m.id, lt,
            datetime.date(_NEXT, 3, 14), datetime.date(_NEXT, 3, 16),
            status=vocabulary.STATUS_APPROVED,
        )
        # Out of the window entirely:
        built.ends_before_from = _insert_request(  # ends the day before date_from
            session, built.r1.id, lt,
            datetime.date(_NEXT, 3, 1), datetime.date(_NEXT, 3, 9),
            status=vocabulary.STATUS_APPROVED,
        )
        built.cross_year = _insert_request(  # straddles Dec 31 — a cross-year window's row
            session, built.r2.id, lt,
            datetime.date(_NEXT, 12, 28), datetime.date(_NEXT + 1, 1, 3),
            status=vocabulary.STATUS_APPROVED,
        )

        # --- r3's PENDING request — the ONE AC4 approves through the real endpoint ---------
        # `_decide` runs `consume_reserved` under the balance row lock: a missing row is a
        # raw-500 `LookupError`, and `reserved < leave_days` a raw-500 `ValueError`. So this
        # request alone gets a balance row seeded with `reserved == leave_days` (and the
        # composition CHECK satisfied: accrued = prorated + carried).
        r3_days = 2
        built.r3_pending_days = r3_days
        built.r3_pending = _insert_request(
            session, built.r3.id, lt,
            datetime.date(_NEXT, 3, 14), datetime.date(_NEXT, 3, 16),
            status=vocabulary.STATUS_PENDING, leave_days=r3_days,
        )
        session.add(
            LeaveBalance(
                employee_id=built.r3.id,
                leave_type_id=lt,
                leave_year=_NEXT,
                accrued=20,
                prorated_entitlement=20,
                carried_forward=0,
                entitlement_basis=20,
                reserved=r3_days,
                consumed=0,
            )
        )
        session.commit()

    try:
        yield built
    finally:
        # The OWNER engine: AC4's approve wrote an audit row the app role may not delete
        # (Story 2.9's AC3 — INSERT and SELECT only). Cleanup is maintenance, run as owner.
        with Session(owner_engine) as session:
            session.execute(
                delete(AuditEntry).where(
                    AuditEntry.subject_id.in_(
                        select(LeaveRequest.id).where(
                            LeaveRequest.leave_type_id == built.leave_type_id
                        )
                    )
                )
            )
            # Story 3.4 (Landmine 16): notification rows FIRST. Every submission/decision through
            # the API now writes one, and it FK-references BOTH `leave_request` and `employee` with
            # NO `ON DELETE` clause (by decision — an Employee is deactivated, never deleted; a
            # Leave Request has no DELETE endpoint). So deleting either parent first raises
            # `ForeignKeyViolation` and errors this whole module. Deleting them explicitly, ahead of
            # their parents, is the sanctioned fix — NOT granting the app role `DELETE` (this block
            # already runs as the owner) and NOT `ON DELETE CASCADE` (it would signal a deletion
            # path the product forbids). Every recipient is one of this fixture's own Employees.
            session.execute(
                delete(Notification).where(
                    Notification.recipient_employee_id.in_(
                        select(Employee.id).where(Employee.email.like(f"%{suffix}%"))
                    )
                )
            )
            session.execute(
                delete(LeaveRequest).where(
                    LeaveRequest.leave_type_id == built.leave_type_id
                )
            )
            session.execute(
                delete(LeaveBalance).where(
                    LeaveBalance.leave_type_id == built.leave_type_id
                )
            )
            session.execute(
                update(Employee)
                .where(Employee.email.like(f"%{suffix}%"))
                .values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(
                delete(LeaveType).where(LeaveType.id == built.leave_type_id)
            )
            session.execute(
                delete(Department).where(Department.name == department_name)
            )
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _get_calendar(token: str | None, **params: object) -> object:
    return _client.get("/api/v1/calendar", params=params, headers=_auth(token))


def _calendar(token: str, **params: object) -> dict:
    response = _get_calendar(token, **params)
    assert response.status_code == 200, response.text
    return response.json()


# --- AC1 + AC2: exactly the reports' PENDING+APPROVED overlap, both statuses distinguished ----


def test_calendar_is_exactly_the_reports_pending_and_approved_overlap(
    world: _World,
) -> None:
    """AC1 exactness: the in-window call returns ONLY manager_m's reports' PENDING+APPROVED
    rows — REJECTED/CANCELLED absent (the fixed status set), the other manager's report absent
    (scope), the Manager's OWN leave absent (REPORTS excludes self — the :602 invariant), the
    ends-day-before row absent (overlap), `total` exact. The deactivated report's row is IN
    (Open Decision #3)."""
    body = _calendar(
        world.manager_m.token,
        date_from=_FROM.isoformat(),
        date_to=_TO.isoformat(),
    )

    expected = {
        world.r1_approved,
        world.r2_approved,
        world.r3_pending,
        world.r4_approved,
        world.straddles_from,
        world.straddles_to,
    }
    returned = {item["id"] for item in body["items"]}
    assert returned == expected
    assert body["total"] == len(expected)

    # Explicit exclusions, named one by one.
    assert world.r1_rejected not in returned
    assert world.r2_cancelled not in returned
    assert world.other_approved not in returned
    assert world.mgr_own_approved not in returned
    assert world.ends_before_from not in returned
    assert world.cross_year not in returned  # out of this window (it has its own test)


def test_both_statuses_are_on_the_wire_distinguished_by_the_status_word(
    world: _World,
) -> None:
    """AC2: APPROVED and PENDING rows are BOTH returned, each carrying its status verbatim —
    the status word IS the visual distinction the frontend renders as received (Open
    Decision #6). No third status ever appears (Open Decision #4)."""
    body = _calendar(
        world.manager_m.token,
        date_from=_FROM.isoformat(),
        date_to=_TO.isoformat(),
    )

    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[world.r1_approved]["status"] == vocabulary.STATUS_APPROVED
    assert by_id[world.r3_pending]["status"] == vocabulary.STATUS_PENDING
    statuses = {item["status"] for item in body["items"]}
    assert statuses == {vocabulary.STATUS_APPROVED, vocabulary.STATUS_PENDING}


def test_each_item_carries_exactly_the_leave_request_response_keys(
    world: _World,
) -> None:
    """Open Decision #1's pin: every item is EXACTLY the ten `LeaveRequestResponse` keys —
    reused byte-for-byte, so accidental widening (email, is_active, a "this is yours" marker)
    fails the build, and narrowing (a second projection) cannot creep in either."""
    body = _calendar(
        world.manager_m.token,
        date_from=_FROM.isoformat(),
        date_to=_TO.isoformat(),
    )

    assert len(body["items"]) > 0
    for item in body["items"]:
        assert set(item) == _EXPECTED_ITEM_KEYS
    names = {item["employee_name"] for item in body["items"]}
    assert "Cal r1" in names  # the field that answers "who else is away"


# --- Landmine 5: the settled overlap semantics, each side optional ----------------------------


def test_one_sided_windows_and_the_unbounded_call_work(world: _World) -> None:
    """`date_from` alone (everything still running on or after it), `date_to` alone
    (everything starting on or before it), and no dates at all (no predicate — every
    PENDING+APPROVED report row) all follow the pinned 3.1 semantics."""
    in_scope_pending_approved = {
        world.r1_approved,
        world.r2_approved,
        world.r3_pending,
        world.r4_approved,
        world.straddles_from,
        world.straddles_to,
        world.ends_before_from,
        world.cross_year,
    }

    from_only = _calendar(world.manager_m.token, date_from=_FROM.isoformat())
    assert {item["id"] for item in from_only["items"]} == (
        in_scope_pending_approved - {world.ends_before_from}
    )

    to_only = _calendar(world.manager_m.token, date_to=_TO.isoformat())
    assert {item["id"] for item in to_only["items"]} == (
        in_scope_pending_approved - {world.cross_year}
    )

    unbounded = _calendar(world.manager_m.token)
    assert {item["id"] for item in unbounded["items"]} == in_scope_pending_approved


def test_a_cross_year_window_returns_the_dec_31_straddler(world: _World) -> None:
    """A window spanning Dec 31 returns the straddling row — no year predicate exists to get
    in the way (Landmine 5: no `leave_year` column, no `_current_leave_year()` on a read
    path), so a calendar range across the Leave Year edge works by construction."""
    body = _calendar(
        world.manager_m.token,
        date_from=datetime.date(_NEXT, 12, 30).isoformat(),
        date_to=datetime.date(_NEXT + 1, 1, 2).isoformat(),
    )

    assert {item["id"] for item in body["items"]} == {world.cross_year}
    assert body["total"] == 1


def test_an_inverted_range_is_a_well_formed_empty_page(world: _World) -> None:
    """`date_from > date_to` is a well-formed predicate whose intersection is EMPTY: 200,
    `items == []`, `total == 0` — it falls out of the SQL, never a 422 (3.1 Open Decision #2,
    inherited)."""
    body = _calendar(
        world.manager_m.token,
        date_from=_TO.isoformat(),
        date_to=_FROM.isoformat(),
    )

    assert body["items"] == []
    assert body["total"] == 0


def test_a_malformed_date_is_a_framework_422(world: _World) -> None:
    """Malformed dates ride the pinned framework-422 path (bare FastAPI `{"detail": ...}`) —
    no domain error code exists for a read filter and none is invented (Landmine 5)."""
    response = _get_calendar(world.manager_m.token, date_from="not-a-date")

    assert response.status_code == 422
    assert "detail" in response.json()  # the framework shape, not the domain envelope


# --- AC5 / AD-18: the stored day count, never recomputed --------------------------------------


def test_leave_days_is_the_stored_figure_verbatim(world: _World) -> None:
    """AC5 non-vacuous: `r1_approved` spans 3 calendar days but stores `leave_days == 99` — a
    figure no recomputation of that range could produce. The wire carries 99 verbatim, so the
    read is provably stored-only (AD-18: "history, dashboard, calendar, export — reads the
    stored value and never recomputes it")."""
    body = _calendar(
        world.manager_m.token,
        date_from=_FROM.isoformat(),
        date_to=_TO.isoformat(),
    )

    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[world.r1_approved]["leave_days"] == _STORED_DISAGREES


# --- The §4.9 inversion: Manager-only, both wrong roles refused with the envelope -------------


@pytest.mark.parametrize("denied", ["admin", "employee"])
def test_admin_and_employee_are_refused_403_by_the_role_gate(
    world: _World, denied: str
) -> None:
    """The binding §4.9 contract (Landmine 4): an Admin AND an Employee get `403
    ACTION_NOT_PERMITTED` with the full `{code, message, details}` envelope and empty details
    — decided by `require_role(MANAGER)` before any row is read (G3). The Admin refusal is the
    inversion: an Admin reads any request via `GET /leave-requests` (scope ALL), but a
    calendar is a reporting edge only a Manager stands on."""
    caller: _Member = getattr(world, denied)

    response = _get_calendar(caller.token)

    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.ACTION_NOT_PERMITTED
    assert body["details"] == {}


def test_an_absent_token_is_401_not_403(world: _World) -> None:
    """No token → 401 (`require_role` chains authentication first; a missing token is never
    turned into a 403)."""
    response = _get_calendar(None)

    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- AC4: approving into a known overlap is a plain 200 — inform, never block -----------------


def test_approving_into_a_two_report_overlap_is_a_plain_200(world: _World) -> None:
    """AC4 (BR-06, DR-15, Landmine 7): r1 and r2 are already APPROVED across Mar 15; the
    Manager approves r3's overlapping PENDING request through the REAL decide endpoint. The
    approval succeeds — plain 200, request APPROVED — and the response carries EXACTLY the
    pre-story `LeaveRequestResponse` keys: no warning field, no overlap payload, no
    acknowledgement round-trip. The decide path gained no overlap awareness whatsoever."""
    # The calendar SHOWS the overlap first (the informed-choice half of BR-06)…
    before = _calendar(
        world.manager_m.token,
        date_from=datetime.date(_NEXT, 3, 14).isoformat(),
        date_to=datetime.date(_NEXT, 3, 16).isoformat(),
    )
    overlapping = {item["id"] for item in before["items"]}
    assert {world.r1_approved, world.r2_approved, world.r3_pending} <= overlapping

    # …and the decision endpoint then decides, with no new behavior at all.
    response = _client.post(
        f"/api/v1/leave-requests/{world.r3_pending}/approve",
        headers=_auth(world.manager_m.token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == _EXPECTED_ITEM_KEYS  # the pre-story decide shape, unchanged
    assert body["status"] == vocabulary.STATUS_APPROVED
    assert body["leave_days"] == world.r3_pending_days

    # The calendar now reports the decided row as APPROVED — same read, fresher facts.
    after = _calendar(
        world.manager_m.token,
        date_from=datetime.date(_NEXT, 3, 14).isoformat(),
        date_to=datetime.date(_NEXT, 3, 16).isoformat(),
    )
    by_id = {item["id"]: item for item in after["items"]}
    assert by_id[world.r3_pending]["status"] == vocabulary.STATUS_APPROVED


# --- The envelope and the clamp ----------------------------------------------------------------


def test_envelope_and_page_size_clamp(world: _World) -> None:
    """The response is the standard `items/page/page_size/total` envelope, and an over-max
    `page_size` is CLAMPED to `MAX_PAGE_SIZE` (100), never a 422 — `PageParams` protects this
    endpoint for free (3.1 Open Decision #5's machinery, pinned globally in
    `test_pagination.py`)."""
    response = _get_calendar(world.manager_m.token, page_size=200)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page_size"] == 100
    assert body["page"] == 1
