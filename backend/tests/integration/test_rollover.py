"""The Leave Year rollover, against real PostgreSQL (Story 2.10, AC1, AC3–AC9).

Implements the test side of: FR-07 (carry-forward, lapse, idempotence), DR-7/DR-7a, AD-6, AD-7,
AD-8, AD-9, SM-5.

--- AC9: no server, and no clock ---

Every test below calls `rollover.run_rollover(...)` DIRECTLY, as an ordinary Python function. There
is no `TestClient` for the job, no `freezegun`, and no monkeypatched `date.today` anywhere in this
file. That is possible only because `--year` is a required argument rather than something the job
derives from a clock — which is exactly why AC2 insists the year be a parameter.

--- Why the year under test is `date.today().year` and not a literal ---

Story 2.4's create hooks materialize balances for `date.today().year` AND NO OTHER YEAR
(`services/employee.py`, `services/leave_types.py`, `seed`). So in an integration test the only year
that HAS balance rows is the current calendar year. A test that hardcoded `run_rollover(2026)` would
be correct only while today is 2026: on 1 January 2027 every `carried_forward` assertion here would
silently degrade into a test of the missing-row path (Open Decision #4) and PASS AGAINST ZEROES.

So `_YEAR` is read from the clock and `Y + 1` is derived from it. This is not clock manipulation —
AC9 forbids MOCKING a clock, not reading one to pick a fixture year — it is the coupling that makes
the fixtures exist at all.

--- Teardown runs as the OWNER, and that is AC1 working ---

The app role holds `INSERT` and `SELECT` on `rollover_run` and NEITHER `UPDATE` NOR `DELETE`, so a
test cannot delete its own `rollover_run` rows through `get_engine()` — the delete is REFUSED. That
refusal is the guarantee, not a bug. Cleanup is maintenance, and maintenance is the owner's
(`owner_engine`), exactly as Story 2.9 established for `audit_entry`.
"""

import datetime
import uuid
from collections.abc import Iterator

import psycopg
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.main import app
from app.repositories.engine import get_engine
from app.repositories.models import (
    AuditEntry,
    CancellationRequest,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    RolloverRun,
)
from app.services import leave_types as leave_types_service
from app.services import rollover

_KNOWN_PASSWORD = "correct-horse-battery-staple"

# The year the rollover CLOSES. Read from the clock (see the module docstring): Story 2.4's create
# hooks materialize THIS year and no other, so it is the only year with balance rows to roll.
_YEAR = datetime.date.today().year
_NEXT_YEAR = _YEAR + 1

# Every Employee joins 1 January of `_YEAR`, so proration reduces nothing and each starts the year
# with the full entitlement — `prorate_entitlement` returns `annual_entitlement` for both `_YEAR`
# and `_NEXT_YEAR`. Keeping proration out of the arithmetic is deliberate: these tests are about
# CARRY-FORWARD, and a prorated entitlement would make every expected figure a second calculation.
_JOINING_DATE = datetime.date(_YEAR, 1, 1)

_ENTITLEMENT = 20

# The cap on the two capped carrying types. `_LOW_CAP` is below a full entitlement, so the excess
# above it must LAPSE (AC3); `_HIGH_CAP` is above it, so everything available carries (AC3's other
# half, and the DR-7a arithmetic below).
_LOW_CAP = 5
_HIGH_CAP = 30

_client = TestClient(app)


def _workweek(weeks_out: int) -> tuple[datetime.date, datetime.date]:
    """A future Monday→Wednesday inside `_YEAR` — exactly 3 Working Days, no weekend, no holiday.

    Derived from today rather than hardcoded, for the same reason `_YEAR` is: a literal date range
    is a test that expires. Mon–Wed spans no weekend, and the seed creates no Company Holidays, so
    `count_leave_days` returns 3 for every range this yields.
    """
    monday = datetime.date.today() + datetime.timedelta(days=(7 - datetime.date.today().weekday()))
    monday += datetime.timedelta(weeks=weeks_out)
    if monday.year != _YEAR:  # pragma: no cover - only reachable in late December
        pytest.skip(
            "No future work-week remains inside the current Leave Year, so a request cannot be "
            "submitted for the year under roll. Re-run outside the last weeks of December."
        )
    return monday, monday + datetime.timedelta(days=2)


_EXPECTED_DAYS = 3


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        carry_id: uuid.UUID,
        capped_id: uuid.UUID,
        lapse_id: uuid.UUID,
        report_id: uuid.UUID,
        report_token: str,
        manager_id: uuid.UUID,
        manager_token: str,
        admin_id: uuid.UUID,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        # carries_forward=True, cap 30 — a full entitlement fits under it.
        self.carry_id = carry_id
        # carries_forward=True, cap 5 — a full entitlement does NOT fit; the excess lapses (AC3).
        self.capped_id = capped_id
        # carries_forward=False, cap 30 SET — the AC4 type. The cap is set precisely so that a
        # implementation consulting the cap before the attribute would carry 30 and fail.
        self.lapse_id = lapse_id
        self.report_id = report_id
        self.report_token = report_token
        self.manager_id = manager_id
        self.manager_token = manager_token
        self.admin_id = admin_id
        self.admin_token = admin_token

    @property
    def leave_type_ids(self) -> list[uuid.UUID]:
        return [self.carry_id, self.capped_id, self.lapse_id]


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """A Manager, their report, an Admin, and THREE Leave Types that differ only in their attributes.

    The three types are the AC3/AC4 matrix, and nothing else distinguishes them — same entitlement,
    same everything, different `carries_forward`/`carry_forward_cap`:

        carry   carries_forward=True   cap=30   → a full 20 fits under the cap
        capped  carries_forward=True   cap=5    → 20 available, 5 carries, 15 LAPSES (AC3)
        lapse   carries_forward=False  cap=30   → carries 0 DESPITE the cap (AC4)

    Created through `leave_types_service.create_leave_type(...)` so Story 2.4's materialization hook
    writes each Employee a full-entitlement `_YEAR` balance — which is what gives the rollover
    something to roll. All join 1 January, so proration reduces nothing.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"ro-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    def _employee(
        session: Session,
        department_id: uuid.UUID,
        *,
        label: str,
        role: str,
        manager_id: uuid.UUID | None,
    ) -> uuid.UUID:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"ro-{label}-{suffix}@example.com",
            full_name=f"RO {label}",
            role=role,
            joining_date=_JOINING_DATE,
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        return employee.id

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()

        manager_id = _employee(
            session, department.id, label="mgr", role=vocabulary.ROLE_MANAGER, manager_id=None
        )
        report_id = _employee(
            session,
            department.id,
            label="rep",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        admin_id = _employee(
            session, department.id, label="adm", role=vocabulary.ROLE_ADMIN, manager_id=None
        )
        session.commit()

    report_token = security.create_token(str(report_id), vocabulary.ROLE_EMPLOYEE)
    manager_token = security.create_token(str(manager_id), vocabulary.ROLE_MANAGER)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    def _leave_type(label: str, *, carries: bool, cap: int | None) -> uuid.UUID:
        return leave_types_service.create_leave_type(
            code=f"{label}-{suffix}",
            name=f"Rollover {label}",
            annual_entitlement=_ENTITLEMENT,
            carries_forward=carries,
            carry_forward_cap=cap,
            requires_supporting_document=False,
        ).id

    carry_id = _leave_type("RC", carries=True, cap=_HIGH_CAP)
    capped_id = _leave_type("RP", carries=True, cap=_LOW_CAP)
    lapse_id = _leave_type("RL", carries=False, cap=_HIGH_CAP)

    try:
        yield _World(
            suffix,
            department_name,
            carry_id,
            capped_id,
            lapse_id,
            report_id,
            report_token,
            manager_id,
            manager_token,
            admin_id,
            admin_token,
        )
    finally:
        # The OWNER engine (AD-9): the app role can neither UPDATE nor DELETE `rollover_run` or
        # `audit_entry`, so these deletes would be REFUSED through `get_engine()` — which is AC1 and
        # Story 2.9's AC3 working, not a bug. Cleanup is maintenance, and maintenance is the owner's.
        leave_type_ids = [carry_id, capped_id, lapse_id]
        with Session(owner_engine) as session:
            lr_ids = select(LeaveRequest.id).where(
                LeaveRequest.leave_type_id.in_(leave_type_ids)
            )
            cr_ids = (
                select(CancellationRequest.id)
                .join(LeaveRequest, CancellationRequest.leave_request_id == LeaveRequest.id)
                .where(LeaveRequest.leave_type_id.in_(leave_type_ids))
            )
            session.execute(delete(AuditEntry).where(AuditEntry.subject_id.in_(cr_ids)))
            session.execute(delete(AuditEntry).where(AuditEntry.subject_id.in_(lr_ids)))
            session.execute(
                delete(CancellationRequest).where(
                    CancellationRequest.leave_request_id.in_(lr_ids)
                )
            )
            session.execute(
                delete(LeaveRequest).where(LeaveRequest.leave_type_id.in_(leave_type_ids))
            )
            # This world's balances, in EVERY year...
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id.in_(leave_type_ids))
            )
            # ...and the `_NEXT_YEAR` rows the rollover materialized for everybody ELSE — the seeded
            # Admin against the seeded EL/CL/FL. The rollover is global by design (it rolls every
            # Employee × every Leave Type), so it writes rows this fixture did not create, and
            # leaving them behind would leak `_NEXT_YEAR` state into the next test. No other story
            # materializes a future year, so this delete is precise.
            session.execute(delete(LeaveBalance).where(LeaveBalance.leave_year == _NEXT_YEAR))
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id.in_(leave_type_ids)))
            session.execute(delete(Department).where(Department.name == department_name))
            # Every run this test appended. The app role cannot do this; the owner can.
            session.execute(delete(RolloverRun))
            session.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _balance(
    employee_id: uuid.UUID, leave_type_id: uuid.UUID, leave_year: int
) -> LeaveBalance | None:
    """Read one balance row straight from the database, as the app role."""
    with Session(get_engine()) as session:
        return session.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == leave_year,
            )
        ).first()


def _carried(employee_id: uuid.UUID, leave_type_id: uuid.UUID) -> int:
    """`carried_forward` on the `_NEXT_YEAR` row — the figure every AC here is about."""
    row = _balance(employee_id, leave_type_id, _NEXT_YEAR)
    assert row is not None, f"the rollover did not materialize a {_NEXT_YEAR} row"
    return row.carried_forward


def _submit(token: str, leave_type_id: uuid.UUID, weeks_out: int) -> uuid.UUID:
    """Submit a 3-Working-Day request through the real endpoint; return its id."""
    start, end = _workweek(weeks_out)
    response = _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["leave_days"] == _EXPECTED_DAYS
    return uuid.UUID(body["id"])


def _rollover_run_count() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(RolloverRun)) or 0


def _audit_count() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(AuditEntry)) or 0


# --- AC3: carry-forward is derived and capped -------------------------------------------------


def test_ac3_the_excess_above_the_cap_lapses(world: _World) -> None:
    """AC3: `carried_forward(Y+1) = min(cap, available(Y))` — 20 available, cap 5, carries 5.

    The other 15 days LAPSE. This is the assertion that makes the cap mean something: carry-forward
    is a `min(...)`, never a running total that accumulates year on year.
    """
    rollover.run_rollover(_YEAR)

    assert _carried(world.report_id, world.capped_id) == _LOW_CAP

    # And `accrued` moved with it, in one statement: the non-deferrable
    # `accrued = prorated_entitlement + carried_forward` CHECK is satisfied, which is only possible
    # because the write went through `set_accrual` (AD-17) rather than touching a column directly.
    row = _balance(world.report_id, world.capped_id, _NEXT_YEAR)
    assert row is not None
    assert row.prorated_entitlement == _ENTITLEMENT
    assert row.accrued == _ENTITLEMENT + _LOW_CAP
    assert row.entitlement_basis == _ENTITLEMENT
    # A fresh `_NEXT_YEAR` row starts unspent — the rollover carries days, never commitments.
    assert row.reserved == 0
    assert row.consumed == 0


def test_ac3_below_the_cap_the_whole_available_balance_carries(world: _World) -> None:
    """AC3: 20 available against a cap of 30 carries all 20 — the ceiling binds nothing."""
    rollover.run_rollover(_YEAR)

    assert _carried(world.report_id, world.carry_id) == _ENTITLEMENT


# --- AC4: lapse is decided by the attribute, never by the name ---------------------------------


def test_ac4_a_lapsing_type_carries_nothing_even_with_a_cap_set(world: _World) -> None:
    """AC4: `carries_forward=False` carries 0 — and the type has a cap of 30 sitting right there.

    The cap being set is the whole point of this test. An implementation that consulted the cap
    before the attribute would carry 30 here; one that branched on a Leave Type CODE would have to
    guess at `RL-<suffix>`, a code that did not exist when the rollover was written. It carries 0
    because `carry_forward_days` reads `carries_forward` FIRST and the cap never enters the
    arithmetic — the function is not even given the Leave Type, only its two attributes.
    """
    rollover.run_rollover(_YEAR)

    assert _carried(world.report_id, world.lapse_id) == 0

    # The row still exists and is fully materialized — the days lapsed, the balance did not vanish.
    row = _balance(world.report_id, world.lapse_id, _NEXT_YEAR)
    assert row is not None
    assert row.accrued == _ENTITLEMENT  # a fresh entitlement, and nothing carried in


# --- AC5: idempotence, by construction ---------------------------------------------------------


def test_ac5_a_second_run_against_the_same_year_changes_no_balance(world: _World) -> None:
    """AC5: run it twice; every balance row is byte-identical, because the value is ASSIGNED.

    The snapshot covers all six quantity columns of every row in the database, not just this world's
    — a rollover that accumulated would show up somewhere, and "somewhere" is the point.

    `rollover_run` gains a SECOND row, and that is correct and asserted (Open Decision #6): the table
    logs EXECUTIONS, not years, so it carries no `UNIQUE (leave_year)`. The run genuinely happened
    twice and the log is honest about it; the BALANCES did not move, and that is where idempotence
    lives. A unique constraint would have turned this legal second run into an `IntegrityError`.
    """

    def _snapshot() -> dict[tuple[uuid.UUID, uuid.UUID, int], tuple[int, ...]]:
        with Session(get_engine()) as session:
            return {
                (row.employee_id, row.leave_type_id, row.leave_year): (
                    row.accrued,
                    row.prorated_entitlement,
                    row.carried_forward,
                    row.entitlement_basis,
                    row.reserved,
                    row.consumed,
                )
                for row in session.scalars(select(LeaveBalance)).all()
            }

    rollover.run_rollover(_YEAR)
    after_first = _snapshot()
    assert after_first, "the first run must have materialized something to compare"

    rollover.run_rollover(_YEAR)
    after_second = _snapshot()

    assert after_second == after_first, (
        "AC5: a second rollover of the same year must change NOTHING. `set_accrual` ASSIGNS "
        "`carried_forward = min(cap, available(Y))` rather than accumulating it, so re-deriving a "
        "derived value yields the same value. A diff here means something wrote `+=`."
    )

    # The log recorded both executions — two rows, no unique constraint, no IntegrityError.
    assert _rollover_run_count() == 2


# --- AC6 (DR-7a): Reserved days survive the boundary, and top up when released -----------------


def test_ac6_reserved_days_do_not_carry_at_the_boundary_and_top_up_on_reject(
    world: _World,
) -> None:
    """AC6 / DR-7a — the story's centrepiece, in three beats.

    1. A Pending request RESERVES 3 days in year `Y`, so `available(Y)` is 17, not 20.
    2. The rollover carries **17**, not 20 — the reserved days are not available, so they do not
       carry. And they have not LAPSED either: they are still reserved against year `Y`, held by a
       request that is still Pending (DR-7a — "Reserved days do not lapse at the Leave Year
       boundary").
    3. The Manager REJECTS it in the new year. `release_reserved` raises `available(Y)` back to 20 —
       and `carried_forward(Y+1)` TOPS UP to 20 in the same transaction. The days were never lost;
       they were held, and then they arrived.

    Beat 3 is the one the whole story exists for, and it is the one that does not live in the job:
    the rollover ran in January and is long finished. The top-up is a hook in Story 2.7's reject
    path, and without it those 3 days would vanish silently.
    """
    request_id = _submit(world.report_token, world.carry_id, weeks_out=1)

    source = _balance(world.report_id, world.carry_id, _YEAR)
    assert source is not None
    assert source.reserved == _EXPECTED_DAYS  # available(Y) == 20 - 3 == 17

    rollover.run_rollover(_YEAR)

    # Beat 2: the reserved days did not carry.
    assert _carried(world.report_id, world.carry_id) == _ENTITLEMENT - _EXPECTED_DAYS == 17

    # Beat 3: reject, and the carry-forward tops up.
    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/reject", headers=_auth(world.manager_token)
    )
    assert response.status_code == 200, response.text

    released = _balance(world.report_id, world.carry_id, _YEAR)
    assert released is not None
    assert released.reserved == 0  # available(Y) is back to 20

    assert _carried(world.report_id, world.carry_id) == _ENTITLEMENT, (
        "DR-7a: rejecting a Pending year-Y request AFTER the boundary raises available(Y), so "
        "carried_forward(Y+1) must be re-derived and top up. If this is 17, the recompute hook in "
        "`leave_requests._decide` did not fire — or it recomputed from the CURRENT year instead of "
        "`row.start_date.year`, which is the same bug wearing a different hat."
    )


def test_ac6_approval_never_claws_back_the_carry_forward(world: _World) -> None:
    """AC6, second clause: approval leaves `available(Y)` unchanged, so carry-forward does not move.

    `consume_reserved` shifts the 3 days Reserved → Consumed. Available is `accrued − consumed −
    reserved`, so it is 17 before the approval and 17 after: the days were already committed at
    submission. The carried figure stays 17 — it is never clawed back.

    This is why `_decide` takes `recompute_carry_forward` as a flag rather than always recomputing:
    a recompute here would be a no-op by arithmetic, and a guarantee that holds by accident of the
    numbers is not a guarantee.
    """
    request_id = _submit(world.report_token, world.carry_id, weeks_out=1)
    rollover.run_rollover(_YEAR)

    carried_before = _carried(world.report_id, world.carry_id)
    assert carried_before == _ENTITLEMENT - _EXPECTED_DAYS

    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve", headers=_auth(world.manager_token)
    )
    assert response.status_code == 200, response.text

    consumed = _balance(world.report_id, world.carry_id, _YEAR)
    assert consumed is not None
    assert consumed.reserved == 0
    assert consumed.consumed == _EXPECTED_DAYS
    # available(Y) = 20 - 3 - 0 = 17, exactly as before the approval.

    assert _carried(world.report_id, world.carry_id) == carried_before, (
        "AC6: approval must NEVER claw back carry-forward. Available did not move, so the derived "
        "figure must not move either."
    )


def test_ac6_an_approved_cancellation_request_also_tops_up(world: _World) -> None:
    """AC6, third site: `release_consumed` raises `available(Y)` too, so it tops up as well.

    The path Story 2.8 shipped: an Approved request is cancelled through a Cancellation Request that
    an Admin approves, which returns the consumed days (BR-05). That RAISES `available(Y)` — the
    third and last place in the system where it rises — so `carried_forward(Y+1)` must top up here
    exactly as it does on reject. A hook that covered only `leave_requests._decide` would miss this
    one entirely, and the days would be lost.
    """
    request_id = _submit(world.report_token, world.carry_id, weeks_out=1)
    approve = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve", headers=_auth(world.manager_token)
    )
    assert approve.status_code == 200, approve.text

    rollover.run_rollover(_YEAR)
    assert _carried(world.report_id, world.carry_id) == _ENTITLEMENT - _EXPECTED_DAYS

    raised = _client.post(
        f"/api/v1/leave-requests/{request_id}/cancellation-requests",
        headers=_auth(world.report_token),
    )
    assert raised.status_code == 201, raised.text
    cancellation_id = raised.json()["id"]

    decided = _client.post(
        f"/api/v1/cancellation-requests/{cancellation_id}/approve",
        headers=_auth(world.admin_token),
    )
    assert decided.status_code == 200, decided.text

    restored = _balance(world.report_id, world.carry_id, _YEAR)
    assert restored is not None
    assert restored.consumed == 0  # available(Y) is back to 20

    assert _carried(world.report_id, world.carry_id) == _ENTITLEMENT, (
        "DR-7a: approving a Cancellation Request returns the days via `release_consumed`, raising "
        "available(Y) — so carried_forward(Y+1) must top up. If this is 17, the hook in "
        "`cancellation.approve_cancellation_request` is missing."
    )


# --- AC7 (SM-5): a fourth Leave Type rolls over with no code change ----------------------------


def test_ac7_sm_5_a_fourth_leave_type_created_through_the_api_rolls_over(world: _World) -> None:
    """AC7 / SM-5: create a Leave Type through `POST /leave-types`, then roll it — no code change.

    Created through the LIVE endpoint, not a direct insert, because that is what the AC says and
    because it is what the metric means: a Leave Type is CONFIGURATION (DR-11/AD-11). Between
    creating it and rolling it over there is no code change and no schema migration — the rollover
    loops `all_leave_types()` and hands each one's attributes to a pure function that has never
    heard of EL, CL, FL, or this one.

    That is the whole of SM-5, and it is why `carry_forward_days` is forbidden from seeing a code.
    """
    response = _client.post(
        "/api/v1/leave-types",
        json={
            "code": f"SM5-{world.suffix}",
            "name": "The fourth Leave Type",
            "annual_entitlement": 10,
            "carries_forward": True,
            "carry_forward_cap": 7,
            "requires_supporting_document": False,
        },
        headers=_auth(world.admin_token),
    )
    assert response.status_code == 201, response.text
    fourth_id = uuid.UUID(response.json()["id"])

    try:
        # 10 days entitlement, nothing spent → available(Y) = 10, capped at 7 → 7 carries, 3 lapse.
        rollover.run_rollover(_YEAR)

        assert _carried(world.report_id, fourth_id) == 7, (
            "SM-5: a fourth Leave Type added through configuration must roll over with NO code "
            "change. If this fails, something in the rollover knows how many Leave Types there are."
        )
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(LeaveBalance).where(LeaveBalance.leave_type_id == fourth_id))
            session.execute(delete(LeaveType).where(LeaveType.id == fourth_id))
            session.commit()


# --- AC8: the rollover is not an Audit Entry ---------------------------------------------------


def test_ac8_the_rollover_writes_no_audit_row_and_one_rollover_run_row(world: _World) -> None:
    """AC8: `audit_entry` is untouched; `rollover_run` gains exactly one row.

    Load-bearing for SM-4, not a style preference. Story 2.9 pinned an EXACT audit ledger — 14 rows,
    with an exact per-`subject_type` breakdown — and `test_leave_request_decide.py` asserts a decide
    count that goes 1 → 2 and stays 2. The rollover transitions no Leave Request, so it must write
    ZERO audit rows: a single row here would take that ledger from 14 to 17 and SM-4's one-to-one
    count against transitions would stop being literally true.

    There is no `SUBJECT_ROLLOVER`, and there must not be one. A balance re-derivation is not a
    state transition. `services/rollover.py` does not import `audit_entry_repo` at all, and its
    absence is the proof this test checks.
    """
    audit_before = _audit_count()
    runs_before = _rollover_run_count()

    rollover.run_rollover(_YEAR)

    assert _audit_count() == audit_before, (
        "AC8: the rollover must write ZERO audit_entry rows — it transitions no Leave Request, and "
        "SM-4's one-to-one count of audit rows against transitions must stay literally true."
    )
    assert _rollover_run_count() == runs_before + 1, (
        "AC8: the rollover records its execution in `rollover_run` — exactly one row per run."
    )

    with Session(get_engine()) as session:
        run = session.scalars(select(RolloverRun)).first()
        assert run is not None
        # The year ROLLED is the year CLOSED (`Y`), never the year opened (Open Decision #1).
        assert run.leave_year == _YEAR
        # `occurred_at` is timezone-AWARE — the column is TIMESTAMPTZ and a naive datetime is a
        # defect, not a nit.
        assert run.occurred_at.tzinfo is not None


def test_the_dr7a_top_up_writes_no_audit_row_of_its_own(world: _World) -> None:
    """The recompute hook adds no audit row either — a reject still writes exactly ONE (AC8).

    The DR-7a hook lands INSIDE `_decide`, the code path `test_leave_request_decide.py`'s exact
    audit count exercises. If the recompute wrote a row "for traceability", that count would go from
    2 to 3 and Story 2.9's 14-row ledger to 17. This asserts the hook is silent, at the one site
    where it fires hardest: a reject that genuinely tops the carry-forward up.
    """
    request_id = _submit(world.report_token, world.carry_id, weeks_out=1)
    rollover.run_rollover(_YEAR)

    audit_before = _audit_count()

    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/reject", headers=_auth(world.manager_token)
    )
    assert response.status_code == 200, response.text

    # The top-up demonstrably happened...
    assert _carried(world.report_id, world.carry_id) == _ENTITLEMENT
    # ...and it wrote exactly ONE audit row: the REJECTED transition, and nothing for the recompute.
    assert _audit_count() == audit_before + 1, (
        "A rejection writes exactly one audit row (the transition). The DR-7a carry-forward "
        "recompute must write NONE — a balance re-derivation is not a state transition (AD-8)."
    )


# --- AC1: append-only is a GRANT, and the database refuses the rest ----------------------------


@pytest.mark.parametrize(
    "statement",
    [
        f"UPDATE rollover_run SET leave_year = {_YEAR + 99}",
        "DELETE FROM rollover_run",
    ],
    ids=["update", "delete"],
)
def test_ac1_the_database_refuses_to_mutate_the_rollover_log(world: _World, statement: str) -> None:
    """AC1: connected AS THE APPLICATION ROLE, Postgres refuses UPDATE and DELETE on `rollover_run`.

    "And the application's database role is granted INSERT and SELECT on it and NEITHER UPDATE NOR
    DELETE" — migration `0009` grants exactly those two verbs and stops. Nothing was inherited:
    `0008` deliberately issued no `ALTER DEFAULT PRIVILEGES`, precisely so that this table would not
    silently acquire UPDATE and DELETE along with every other table the owner creates.

    The assertion is on the PRIVILEGE error specifically — `psycopg.errors.InsufficientPrivilege`. A
    test that merely asserted "no rows changed" would pass just as happily because the table was
    empty or the SQL was malformed, and would prove nothing. A real row is guaranteed to exist first
    (the run below), so "refused" cannot be confused with "nothing to refuse".

    This is the ONLY test that can verify AC1: a schema inspection cannot see a grant that was never
    made.
    """
    rollover.run_rollover(_YEAR)
    assert _rollover_run_count() > 0

    with pytest.raises(sa.exc.ProgrammingError) as refused:
        with get_engine().begin() as connection:
            connection.execute(sa.text(statement))

    assert isinstance(refused.value.orig, psycopg.errors.InsufficientPrivilege), (
        "the application role must be REFUSED by Postgres — not merely fail to match a row. "
        f"Got {type(refused.value.orig).__name__}."
    )

    # And the row is still there: a refused mutation changes nothing.
    assert _rollover_run_count() > 0


def test_ac1_the_application_role_can_insert_and_select_the_rollover_log(world: _World) -> None:
    """AC1, the other half: the two verbs that WERE granted work.

    A grant test that only proved the refusals would pass just as well against a role with NO
    privileges at all on the table — and that role would break the job on its first run. INSERT and
    SELECT must both succeed, and they are exercised here through the job itself (which inserts) and
    a direct read (which selects).
    """
    rollover.run_rollover(_YEAR)

    with Session(get_engine()) as session:
        runs = session.scalars(select(RolloverRun)).all()

    assert len(runs) == 1
    assert runs[0].leave_year == _YEAR
