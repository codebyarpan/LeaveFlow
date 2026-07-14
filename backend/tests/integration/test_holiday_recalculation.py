"""A holiday change recalculates, and may be refused — against real PostgreSQL (Story 2.11).

Implements the test side of: AC1 (`admin_review_flag` exists and is APPEND-ONLY — proved LIVE, as
the app role, not read off the migration), AC2 (a Pending request is recalculated), AC3 (a future
Approved request is recalculated; a past one NEVER is), AC4 (the forward check refuses PER PAIR and
the rest proceeds — `200`, not a wholesale failure), AC5 (a refusal is RECORDED, and was PREDICTED
— never caught from a CHECK violation), AC6/AC7 (an Admin reads the refusals; nobody else does).
FR-10, AD-18, AD-19, AD-20.

--- Real PostgreSQL, because the whole story is about what the database is NOT allowed to decide ---

AC5 says the refusal must be "discovered by the forward check, never by an AD-5 CHECK violation".
That is a claim about which layer refuses, and it is only falsifiable against a database that HAS
those CHECKs and those GRANTs. So: `leave_balance`'s `available >= 0` CHECK, `leave_request`'s
`CHECK (leave_days > 0)`, and the `INSERT, SELECT`-only grant on `admin_review_flag` are all live
here, and `test_the_forward_check_is_what_refuses_not_the_constraint` proves the check is
load-bearing by DISABLING it and watching the write path blow up instead.

--- Why the year and the dates are derived from the clock, never hardcoded ---

Story 2.4's create hooks materialize balances for `date.today().year` and NO OTHER YEAR, so the
current calendar year is the only one with rows to recalculate. A hardcoded `2026` would silently
degrade into a test of the missing-row path the moment the calendar turned — passing against zeroes.
Same reasoning as Story 2.10's suite, and the same `pytest.skip` in the December corner where no
future work-week remains inside the Leave Year.

--- Teardown runs as the OWNER, and that IS AC1 ---

The app role holds `INSERT` and `SELECT` on `admin_review_flag` and neither `UPDATE` nor `DELETE`, so
a test cannot delete its own flags through `get_engine()` — the delete is REFUSED. That refusal is
the guarantee working, not a bug. Cleanup is maintenance, and maintenance is the owner's
(`owner_engine`), exactly as Stories 2.9 and 2.10 established.
"""

import datetime
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.main import app
from app.repositories.engine import get_engine
from app.repositories.models import (
    AdminReviewFlag,
    AuditEntry,
    CompanyHoliday,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from app.services import balances
from app.services import leave_types as leave_types_service

_KNOWN_PASSWORD = "correct-horse-battery-staple"

_YEAR = datetime.date.today().year
_NEXT_YEAR = _YEAR + 1
_JOINING_DATE = datetime.date(_YEAR, 1, 1)

# A full entitlement, with room to spare — the arithmetic below is about carry-forward and
# recalculation, and a prorated entitlement would make every expected figure a second calculation.
_ENTITLEMENT = 20
_HIGH_CAP = 30

_client = TestClient(app)


def _monday(weeks_out: int) -> datetime.date:
    """A future Monday inside `_YEAR`, `weeks_out` weeks from the coming one.

    Derived from the clock rather than hardcoded, for the reason the module docstring gives. Each
    test takes its own `weeks_out`, so no two tests collide on a `holiday_date` (which is UNIQUE).
    """
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    monday += datetime.timedelta(weeks=weeks_out)
    if monday.year != _YEAR:  # pragma: no cover - only reachable in late December
        pytest.skip(
            "No future work-week remains inside the current Leave Year, so a request cannot be "
            "submitted for the year under recalculation. Re-run outside the last weeks of December."
        )
    return monday


class _World:
    """A managed Employee (so their requests go PENDING), an Admin, and TWO Leave Types.

    TWO types, because AC4's load-bearing clause is that a refusal is scoped to the PAIR: "that
    Employee and Leave Type pair is left entirely unchanged, THE SAME EMPLOYEE'S OTHER LEAVE TYPES
    STILL PROCEED". One type cannot show that. Both are identical in every attribute — the only
    difference between them in these tests is what the fixtures do to their balances.
    """

    def __init__(
        self,
        suffix: str,
        alpha_id: uuid.UUID,
        beta_id: uuid.UUID,
        employee_id: uuid.UUID,
        employee_token: str,
        manager_id: uuid.UUID,
        manager_token: str,
        admin_id: uuid.UUID,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.alpha_id = alpha_id
        self.beta_id = beta_id
        self.employee_id = employee_id
        self.employee_token = employee_token
        self.manager_id = manager_id
        self.manager_token = manager_token
        self.admin_id = admin_id
        self.admin_token = admin_token


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """A Manager, their managed report, an Admin, and two identical Leave Types.

    The report has a MANAGER on purpose: a managerless Employee's submission is auto-APPROVED and
    consumes directly (FR-09), which would make every request in this suite an Approved one. A
    managed report's submission goes PENDING and RESERVES, which is what AC2 is about — and AC3's
    Approved rows are then built deliberately, where the test needs them.

    Leave Types are created through the service so Story 2.4's materialization hook writes each
    Employee a full-entitlement `_YEAR` balance — which is what gives the recalculation something to
    recalculate.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"hr-dept-{suffix}"
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
            email=f"hr-{label}-{suffix}@example.com",
            full_name=f"HR {label}",
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
            session,
            department.id,
            label="mgr",
            role=vocabulary.ROLE_MANAGER,
            manager_id=None,
        )
        employee_id = _employee(
            session,
            department.id,
            label="emp",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        admin_id = _employee(
            session,
            department.id,
            label="adm",
            role=vocabulary.ROLE_ADMIN,
            manager_id=None,
        )
        session.commit()

    employee_token = security.create_token(str(employee_id), vocabulary.ROLE_EMPLOYEE)
    manager_token = security.create_token(str(manager_id), vocabulary.ROLE_MANAGER)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    def _leave_type(label: str) -> uuid.UUID:
        return leave_types_service.create_leave_type(
            code=f"{label}-{suffix}",
            name=f"Recalc {label}",
            annual_entitlement=_ENTITLEMENT,
            carries_forward=True,
            carry_forward_cap=_HIGH_CAP,
            requires_supporting_document=False,
        ).id

    alpha_id = _leave_type("HA")
    beta_id = _leave_type("HB")

    try:
        yield _World(
            suffix,
            alpha_id,
            beta_id,
            employee_id,
            employee_token,
            manager_id,
            manager_token,
            admin_id,
            admin_token,
        )
    finally:
        # The OWNER engine (AD-9/AD-20): the app role can neither UPDATE nor DELETE
        # `admin_review_flag` or `audit_entry`, so these deletes are REFUSED through `get_engine()`
        # — which is AC1 working, not a bug. Cleanup is maintenance, and maintenance is the owner's.
        leave_type_ids = [alpha_id, beta_id]
        with Session(owner_engine) as session:
            lr_ids = select(LeaveRequest.id).where(
                LeaveRequest.leave_type_id.in_(leave_type_ids)
            )
            session.execute(delete(AuditEntry).where(AuditEntry.subject_id.in_(lr_ids)))
            session.execute(
                delete(AdminReviewFlag).where(
                    AdminReviewFlag.leave_type_id.in_(leave_type_ids)
                )
            )
            session.execute(
                delete(LeaveRequest).where(
                    LeaveRequest.leave_type_id.in_(leave_type_ids)
                )
            )
            session.execute(
                delete(LeaveBalance).where(
                    LeaveBalance.leave_type_id.in_(leave_type_ids)
                )
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id.in_(leave_type_ids)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


# --- helpers ---------------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_holiday(world: _World, on: datetime.date, name: str = "Recalc Day") -> dict:  # type: ignore[type-arg]
    """`POST /holidays` as the Admin. Returns the `200` envelope (Story 2.11's new shape)."""
    response = _client.post(
        "/api/v1/holidays",
        json={"holiday_date": on.isoformat(), "name": name},
        headers=_auth(world.admin_token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _delete_holiday(world: _World, holiday_id: str) -> dict:  # type: ignore[type-arg]
    """`DELETE /holidays/<id>` as the Admin. Returns the `200` envelope (no longer a `204`)."""
    response = _client.delete(
        f"/api/v1/holidays/{holiday_id}",
        headers=_auth(world.admin_token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _drop_holiday_row(on: datetime.date) -> None:
    """Remove a holiday WITHOUT going through the endpoint — i.e. without recalculating.

    Teardown only. Going through `DELETE /holidays/<id>` would run a recalculation, which is the
    thing under test; a test's cleanup must not re-run the code it just measured.
    """
    with Session(get_engine()) as session:
        session.execute(
            delete(CompanyHoliday).where(CompanyHoliday.holiday_date == on)
        )
        session.commit()


def _submit(
    world: _World, leave_type_id: uuid.UUID, start: datetime.date, end: datetime.date
) -> uuid.UUID:
    """Submit a Leave Request as the managed Employee — it lands PENDING and RESERVES its days."""
    response = _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=_auth(world.employee_token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == vocabulary.STATUS_PENDING
    return uuid.UUID(body["id"])


def _request(request_id: uuid.UUID) -> LeaveRequest:
    with Session(get_engine()) as session:
        row = session.get(LeaveRequest, request_id)
        assert row is not None
        return row


def _balance(
    world: _World, leave_type_id: uuid.UUID, leave_year: int
) -> LeaveBalance:
    with Session(get_engine()) as session:
        row = session.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == world.employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == leave_year,
            )
        ).first()
        assert row is not None
        return row


def _snapshot(world: _World, leave_type_id: uuid.UUID, leave_year: int) -> tuple:  # type: ignore[type-arg]
    """Every stored quantity on a balance row, for a byte-for-byte "nothing moved" assertion.

    AC4 requires a refused pair to be left ENTIRELY unchanged, and "entirely" is not proved by
    checking one column. `available` is deliberately absent — it is derived, never stored (DR-3).
    """
    row = _balance(world, leave_type_id, leave_year)
    return (
        row.accrued,
        row.prorated_entitlement,
        row.carried_forward,
        row.entitlement_basis,
        row.reserved,
        row.consumed,
    )


def _materialize_next_year(
    world: _World, leave_type_id: uuid.UUID, *, carried_forward: int
) -> None:
    """Open `_NEXT_YEAR` for the pair with an explicit carry-forward — i.e. run the rollover's write.

    Through `balances.set_accrual`, the ONE writer of a balance column (AD-17), never raw SQL.
    """
    with Session(get_engine()) as session:
        balances.set_accrual(
            session,
            employee_id=world.employee_id,
            leave_type_id=leave_type_id,
            leave_year=_NEXT_YEAR,
            prorated_entitlement=_ENTITLEMENT,
            carried_forward=carried_forward,
            entitlement_basis=_ENTITLEMENT,
        )
        session.commit()


def _spend_next_year(world: _World, leave_type_id: uuid.UUID, *, days: int) -> None:
    """Consume `days` in `_NEXT_YEAR` — the "already spent later year" every refusal turns on."""
    with Session(get_engine()) as session:
        balances.consume_direct(
            session,
            employee_id=world.employee_id,
            leave_type_id=leave_type_id,
            leave_year=_NEXT_YEAR,
            days=days,
        )
        session.commit()


def _flags(world: _World, leave_type_id: uuid.UUID) -> list[AdminReviewFlag]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AdminReviewFlag).where(
                    AdminReviewFlag.employee_id == world.employee_id,
                    AdminReviewFlag.leave_type_id == leave_type_id,
                )
            ).all()
        )


def _audit_count() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(AuditEntry)) or 0


# --- AC2: a Pending request is recalculated ---------------------------------------------------


def test_a_pending_request_is_recalculated(world: _World) -> None:
    """AC2: adding a holiday inside a Pending request's range lowers its days AND its Reserved.

    Mon–Wed is 3 Working Days, so the submission reserves 3 and Available falls to 17. Declare the
    Tuesday a holiday and the request costs 2: `leave_days` falls to 2, `reserved` falls to 2, and
    Available RISES to 18 — the day the organization declared a holiday is no longer charged against
    anyone's balance, which is the whole of FR-10.

    `leave_days` and `reserved` move TOGETHER (Landmine 2). Lowering one without the other is the
    latent 500 `deferred-work.md:56` predicted by name: the next approve would find `days > reserved`
    and raise a bare `ValueError`.
    """
    monday = _monday(2)
    wednesday = monday + datetime.timedelta(days=2)
    tuesday = monday + datetime.timedelta(days=1)

    request_id = _submit(world, world.alpha_id, monday, wednesday)
    assert _request(request_id).leave_days == 3
    assert _balance(world, world.alpha_id, _YEAR).reserved == 3

    try:
        envelope = _add_holiday(world, tuesday)

        assert _request(request_id).leave_days == 2
        balance = _balance(world, world.alpha_id, _YEAR)
        assert balance.reserved == 2
        assert balance.accrued - balance.consumed - balance.reserved == 18

        assert envelope["recalculation"]["requests_recalculated"] == 1
        assert envelope["recalculation"]["pairs_recalculated"] == 1
        assert envelope["recalculation"]["pairs_refused"] == []
    finally:
        _drop_holiday_row(tuesday)


def test_a_holiday_on_a_weekend_changes_nothing(world: _World) -> None:
    """A holiday on a Saturday costs nobody a day, so nothing is recalculated and nothing is written.

    Weekend precedence: `count_leave_days` excludes Sat/Sun BEFORE it ever consults the calendar, so
    a request spanning that Saturday never charged for it. The correct behaviour is a genuine no-op —
    a recalculation that rewrote the balance row here would be inventing work, and (worse) would
    quietly re-derive a stale `carried_forward` as a side effect nobody asked for.
    """
    monday = _monday(3)
    saturday = monday + datetime.timedelta(days=5)
    next_friday = monday + datetime.timedelta(days=11)

    request_id = _submit(world, world.alpha_id, monday, next_friday)
    before_days = _request(request_id).leave_days
    before_balance = _snapshot(world, world.alpha_id, _YEAR)

    try:
        envelope = _add_holiday(world, saturday)

        assert _request(request_id).leave_days == before_days
        assert _snapshot(world, world.alpha_id, _YEAR) == before_balance
        assert envelope["recalculation"] == {
            "requests_recalculated": 0,
            "pairs_recalculated": 0,
            "pairs_refused": [],
        }
    finally:
        _drop_holiday_row(saturday)


# --- AC3: a future Approved request is recalculated; a past one NEVER is -----------------------


def test_a_future_approved_request_is_recalculated(world: _World) -> None:
    """AC3: an Approved request whose dates lie WHOLLY IN THE FUTURE is recalculated (AD-18).

    Submitted, then approved by the Manager — so its days moved Reserved → Consumed and it holds
    them as `consumed`. Declaring a day inside its range a holiday must lower `leave_days` AND
    `consumed`, exactly as it lowers `reserved` for a Pending one.
    """
    monday = _monday(4)
    wednesday = monday + datetime.timedelta(days=2)
    tuesday = monday + datetime.timedelta(days=1)

    request_id = _submit(world, world.alpha_id, monday, wednesday)
    approved = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_token),
    )
    assert approved.status_code == 200, approved.text

    balance = _balance(world, world.alpha_id, _YEAR)
    assert (balance.reserved, balance.consumed) == (0, 3)

    try:
        _add_holiday(world, tuesday)

        assert _request(request_id).leave_days == 2
        balance = _balance(world, world.alpha_id, _YEAR)
        assert (balance.reserved, balance.consumed) == (0, 2)
    finally:
        _drop_holiday_row(tuesday)


def test_a_past_approved_request_is_NEVER_recalculated(world: _World) -> None:
    """AC3's second half, and it asserts the ABSENCE of change — byte for byte (AD-18).

    Leave already taken cannot be un-taken. An Approved request whose dates have passed keeps its
    frozen `leave_days` and its Consumed days FOREVER, however the calendar is edited under it. The
    balance row is compared as a whole tuple, not one column, because "never recalculated" is a claim
    about every stored quantity.

    The request is inserted directly with past dates and its days consumed through `consume_direct`:
    the submission endpoint refuses a past range outright (`PAST_DATE_RANGE`), so a past Approved row
    cannot be built through it — it is the state a request REACHES by the calendar moving on, which
    is exactly the state AD-18 protects.
    """
    last_monday = datetime.date.today() - datetime.timedelta(
        days=datetime.date.today().weekday() + 7
    )
    last_wednesday = last_monday + datetime.timedelta(days=2)
    last_tuesday = last_monday + datetime.timedelta(days=1)
    if last_monday.year != _YEAR:  # pragma: no cover - only in the first week of January
        pytest.skip("No past work-week remains inside the current Leave Year.")

    with Session(get_engine()) as session:
        row = LeaveRequest(
            employee_id=world.employee_id,
            leave_type_id=world.alpha_id,
            start_date=last_monday,
            end_date=last_wednesday,
            leave_days=3,
            status=vocabulary.STATUS_APPROVED,
        )
        session.add(row)
        session.flush()
        request_id = row.id
        balances.consume_direct(
            session,
            employee_id=world.employee_id,
            leave_type_id=world.alpha_id,
            leave_year=_YEAR,
            days=3,
        )
        session.commit()

    before_balance = _snapshot(world, world.alpha_id, _YEAR)

    try:
        envelope = _add_holiday(world, last_tuesday)

        # Byte-identical. Not "roughly unchanged" — unchanged.
        assert _request(request_id).leave_days == 3
        assert _snapshot(world, world.alpha_id, _YEAR) == before_balance
        assert envelope["recalculation"]["requests_recalculated"] == 0
        assert envelope["recalculation"]["pairs_refused"] == []
    finally:
        _drop_holiday_row(last_tuesday)


# --- AC4 / AC5: the refusal, per pair, and the rest proceeds -----------------------------------


def _arrange_delete_refusal(world: _World) -> tuple[datetime.date, uuid.UUID, uuid.UUID, str]:
    """Set up the DELETE refusal, and a SECOND Leave Type that must still recalculate.

    The construction, on Leave Type ALPHA:

      * A holiday on the Tuesday, so the Mon–Wed request costs 2 Working Days, not 3.
      * That request submitted → `reserved(Y) = 2`, `available(Y) = 18`.
      * `_NEXT_YEAR` materialized with `carried_forward = 18` (what the rollover would have written)
        → `accrued(Y+1) = 38` — and then SPENT to the last day: `consumed(Y+1) = 38`,
        `available(Y+1) = 0`.

    Now DELETE the holiday. The Tuesday becomes a working day again, the request costs 3, `reserved`
    rises to 3, `available(Y)` falls to 17 — so `carried_forward(Y+1)` must fall to 17,
    `accrued(Y+1)` to 37, and `available(Y+1)` to **−1**. That is the refusal AC4 names, and it does
    NOT surface at `Y`: year `Y` is perfectly fine.

    Leave Type BETA gets the same request over the same dates and nothing else — no spent later year
    — so it MUST recalculate cleanly while ALPHA is refused. That is AC4's load-bearing clause.
    """
    monday = _monday(5)
    wednesday = monday + datetime.timedelta(days=2)
    tuesday = monday + datetime.timedelta(days=1)

    envelope = _add_holiday(world, tuesday)
    holiday_id = envelope["holiday"]["id"]

    alpha_request = _submit(world, world.alpha_id, monday, wednesday)
    beta_request = _submit(world, world.beta_id, monday, wednesday)
    assert _request(alpha_request).leave_days == 2
    assert _request(beta_request).leave_days == 2

    _materialize_next_year(world, world.alpha_id, carried_forward=18)
    _spend_next_year(world, world.alpha_id, days=38)

    return tuesday, alpha_request, beta_request, holiday_id


def test_a_delete_that_would_go_negative_refuses_THAT_PAIR_and_the_rest_proceeds(
    world: _World,
) -> None:
    """AC4 + AC5: the pair is left ENTIRELY unchanged, flagged, and everything else still commits.

    The endpoint answers `200` — not a `400`, not a `500`. AD-19 is explicit that the operation does
    not fail wholesale: the refused pair is left alone, the flag records it, and the rest of the
    holiday change is committed. That is what makes this the system's first partially-refusable
    command.
    """
    tuesday, alpha_request, beta_request, holiday_id = _arrange_delete_refusal(world)

    alpha_year = _snapshot(world, world.alpha_id, _YEAR)
    alpha_next = _snapshot(world, world.alpha_id, _NEXT_YEAR)

    try:
        envelope = _delete_holiday(world, holiday_id)

        # --- ALPHA: refused, and left ENTIRELY unchanged (AC4) ---
        assert _request(alpha_request).leave_days == 2
        assert _snapshot(world, world.alpha_id, _YEAR) == alpha_year
        assert _snapshot(world, world.alpha_id, _NEXT_YEAR) == alpha_next

        # --- BETA: the SAME Employee's other Leave Type still proceeds (AC4) ---
        assert _request(beta_request).leave_days == 3
        assert _balance(world, world.beta_id, _YEAR).reserved == 3

        # --- The refusal is RECORDED (AC5) ---
        flags = _flags(world, world.alpha_id)
        assert len(flags) == 1
        assert flags[0].leave_year == _YEAR
        assert flags[0].cause == vocabulary.CAUSE_HOLIDAY_RECALCULATION
        assert flags[0].employee_id == world.employee_id
        assert not _flags(world, world.beta_id)

        # --- ...and the response tells the Admin, naming the pair (AC4, AC8) ---
        recalculation = envelope["recalculation"]
        assert recalculation["pairs_recalculated"] == 1
        assert recalculation["requests_recalculated"] == 1
        assert len(recalculation["pairs_refused"]) == 1
        refused = recalculation["pairs_refused"][0]
        assert refused["employee_id"] == str(world.employee_id)
        assert refused["employee_name"] == "HR emp"
        assert refused["leave_type_id"] == str(world.alpha_id)
        assert refused["leave_year"] == _YEAR
        assert refused["cause"] == vocabulary.CAUSE_HOLIDAY_RECALCULATION
    finally:
        _drop_holiday_row(tuesday)


def test_the_forward_check_is_what_refuses_not_the_constraint(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5, proved NON-VACUOUS: disable the forward check and the write path BLOWS UP.

    This is the sharpest form of the claim "the refusal was discovered by the forward check, never by
    an AD-5 CHECK violation". The test above passes; but does the FORWARD CHECK earn that pass, or
    would the code have stumbled into the same flag some other way?

    So: stub `project_forward` to always answer "not refused" — the check is now blind — and run the
    exact scenario the test above runs. The recalculation walks straight into the write it was
    supposed to prevent, and `set_accrual`'s `available >= 0` guard (the BACKSTOP, Story 2.10) fires:
    an unhandled `ValueError`, which through the endpoint is a raw 500.

    That is what the forward check is preventing, and it proves three things at once:
      * the check is load-bearing, not decoration — remove it and the story breaks;
      * the refusal is genuinely PREDICTED, not caught (nothing here catches that `ValueError`, and
        AC5 forbids doing so — see the module docstring of `domain/recalculation.py`);
      * AD-5's CHECKs really are only a backstop, and the gate really is the projection.

    Story 2.10 proved its own AC6 tests non-vacuous the same way.
    """
    from app.domain.recalculation import ForwardProjection
    from app.services import recalculation as recalculation_service

    tuesday, _alpha_request, _beta_request, holiday_id = _arrange_delete_refusal(world)

    def _blind_projection(**_kwargs: object) -> ForwardProjection:
        """The forward check, lobotomized: everything is fine, always."""
        return ForwardProjection(
            refused=False, refused_year=None, carried_forward_by_year={}
        )

    monkeypatch.setattr(
        recalculation_service, "project_forward", _blind_projection
    )

    try:
        with pytest.raises(ValueError, match="available negative"):
            _client.delete(
                f"/api/v1/holidays/{holiday_id}",
                headers=_auth(world.admin_token),
            )

        # And NOTHING was flagged — because nothing predicted the refusal. The transaction that
        # raised rolled back, so the holiday is still there and the pair is untouched.
        assert not _flags(world, world.alpha_id)
    finally:
        _drop_holiday_row(tuesday)


def test_an_ADD_refuses_a_request_priced_down_to_zero_working_days(world: _World) -> None:
    """AC4/AC5, the ADD-only refusal: a one-day request whose only Working Day becomes a holiday.

    `CHECK (leave_days > 0)` is a BACKSTOP (AD-5). A single-Monday request costs 1 Working Day;
    declare that Monday a holiday and the recalculated figure is 0 — which would fire that CHECK as a
    raw 500 AND violate AC5 (the failure discovered by a constraint, not by the forward check).

    So the pair is REFUSED and FLAGGED, and the request and balance are left entirely unchanged. It
    is deliberately NOT refused with `ZERO_LEAVE_DAYS`: that is an error code that ABORTS a
    submission, and AC4 requires this holiday edit to COMMIT (Open Decision #3). Auto-cancelling the
    request instead would invent a state transition no requirement grants — and would need an audit
    row, breaking SM-4's premise.

    This refusal is the reason `POST /holidays` cannot skip the forward check: a POST absolutely can
    refuse.
    """
    monday = _monday(6)

    request_id = _submit(world, world.alpha_id, monday, monday)
    assert _request(request_id).leave_days == 1
    before = _snapshot(world, world.alpha_id, _YEAR)

    try:
        envelope = _add_holiday(world, monday)

        # Unchanged — and specifically NOT written as zero.
        assert _request(request_id).leave_days == 1
        assert _snapshot(world, world.alpha_id, _YEAR) == before

        flags = _flags(world, world.alpha_id)
        assert len(flags) == 1
        assert flags[0].cause == vocabulary.CAUSE_HOLIDAY_RECALCULATION

        assert len(envelope["recalculation"]["pairs_refused"]) == 1
        assert envelope["recalculation"]["pairs_recalculated"] == 0
    finally:
        _drop_holiday_row(monday)


def test_an_ADD_refuses_when_carried_forward_is_STALE_HIGH(world: _World) -> None:
    """AC4/AC5: an ADD is NOT a documented no-op. It can refuse, and it must not 500.

    The trap the story's Orientation section calls out, and it is real. `reserve` (submission) LOWERS
    `available(Y)` and recomputes carry-forward NOT AT ALL — Story 2.10 wired `recompute_carry_forward`
    into only the three sites where `available(Y)` RISES. So a year-`Y` request submitted AFTER the
    rollover ran leaves `carried_forward(Y+1)` STALE-HIGH.

    Constructed here exactly so:

      * `_NEXT_YEAR` materialized with `carried_forward = 20` — what the rollover wrote when
        `available(Y)` was still a full 20 — giving `accrued(Y+1) = 40`, then SPENT to the last day.
      * THEN the Mon–Wed request is submitted: `reserved(Y) = 3`, `available(Y) = 17`. Nothing
        recomputed `carried_forward(Y+1)`, so it still says 20. It is now overstated by 3.

    Now ADD a holiday on the Tuesday. `available(Y)` RISES (to 18) — the direction that supposedly
    cannot hurt anyone. But `carry_forward_days` ASSIGNS a derived value rather than topping one up,
    so the recompute this ADD triggers LOWERS `carried_forward(Y+1)` from its stale 20 to 18,
    `accrued(Y+1)` from 40 to 38 — below the 40 already spent. `available(Y+1) = −2`.

    So the ADD is REFUSED, the pair is untouched, and the response is `200` — NOT a 500. The forward
    check runs unconditionally on both paths, which is exactly why.

    The stale-high condition is a PRE-EXISTING gap in Story 2.10 (Open Decision #8), not one this
    story introduces. This test proves the forward check CONTAINS its blast radius; it does not
    pretend to fix it.
    """
    monday = _monday(7)
    wednesday = monday + datetime.timedelta(days=2)
    tuesday = monday + datetime.timedelta(days=1)

    # The rollover ran while `available(Y)` was still a full 20, and `_NEXT_YEAR` was then spent.
    _materialize_next_year(world, world.alpha_id, carried_forward=_ENTITLEMENT)
    _spend_next_year(world, world.alpha_id, days=40)

    # ...and only THEN is the year-`Y` request submitted. Nothing recomputes carry-forward.
    request_id = _submit(world, world.alpha_id, monday, wednesday)
    assert _request(request_id).leave_days == 3
    assert _balance(world, world.alpha_id, _NEXT_YEAR).carried_forward == 20  # stale-high

    year_before = _snapshot(world, world.alpha_id, _YEAR)
    next_before = _snapshot(world, world.alpha_id, _NEXT_YEAR)

    try:
        envelope = _add_holiday(world, tuesday)

        # `200`, not a 500 — and the pair is entirely untouched.
        assert _request(request_id).leave_days == 3
        assert _snapshot(world, world.alpha_id, _YEAR) == year_before
        assert _snapshot(world, world.alpha_id, _NEXT_YEAR) == next_before

        assert len(_flags(world, world.alpha_id)) == 1
        assert len(envelope["recalculation"]["pairs_refused"]) == 1
    finally:
        _drop_holiday_row(tuesday)


# --- Landmine 5: the recalculation writes ZERO audit rows (SM-4 is undisturbed) -----------------


def test_a_recalculation_writes_no_audit_rows(world: _World) -> None:
    """SM-4 stays literally true: a balance re-derivation is NOT a state transition (AD-8, AD-20).

    `test_audit_entries.py` counts audit rows one-to-one against transitions and pins the total at
    exactly 14. A holiday edit that recalculates a request transitions NOTHING — no request changes
    status — so it must write ZERO audit rows, or that ledger silently breaks. `admin_review_flag`
    exists as a separate table for precisely this reason (AD-20: "Neither table is `audit_entry`").

    Both paths are measured: the one that recalculates cleanly, and the one that REFUSES. A flag is
    not an audit row either.
    """
    monday = _monday(8)
    wednesday = monday + datetime.timedelta(days=2)
    tuesday = monday + datetime.timedelta(days=1)
    lone_monday = _monday(9)

    _submit(world, world.alpha_id, monday, wednesday)
    zero_day_request = _submit(world, world.beta_id, lone_monday, lone_monday)
    assert _request(zero_day_request).leave_days == 1

    before = _audit_count()

    try:
        # A clean recalculation...
        _add_holiday(world, tuesday)
        assert _audit_count() == before

        # ...and a REFUSED one. Neither writes an audit row.
        _add_holiday(world, lone_monday)
        assert _audit_count() == before
        assert len(_flags(world, world.beta_id)) == 1
    finally:
        _drop_holiday_row(tuesday)
        _drop_holiday_row(lone_monday)


# --- AC1: `admin_review_flag` is append-only, and it is the GRANT that says so ------------------


def test_the_flag_table_is_append_only_as_the_app_role(world: _World) -> None:
    """AC1, proved LIVE: `UPDATE` and `DELETE` are REFUSED BY POSTGRES; `INSERT`/`SELECT` succeed.

    Not read off the migration file — exercised as the application's own database role, which is the
    only thing that settles it. `0010` grants `INSERT, SELECT` and neither `UPDATE` nor `DELETE`, and
    the ABSENCE of those two verbs is the acceptance criterion ("no endpoint updates or deletes a row
    in it"). Nothing is inherited: `0008` deliberately issued no `ALTER DEFAULT PRIVILEGES` precisely
    so each append-only table must grant for itself.

    Stories 2.9 and 2.10 verified their grants exactly this way. A test that only read the DDL would
    pass against a database where someone had since granted the app role `UPDATE`.
    """
    with get_engine().connect() as connection:
        # SELECT is granted.
        connection.execute(text("SELECT count(*) FROM admin_review_flag"))

        for statement in (
            "UPDATE admin_review_flag SET cause = 'x'",
            "DELETE FROM admin_review_flag",
        ):
            with pytest.raises(Exception) as refusal:
                connection.execute(text(statement))
            assert isinstance(refusal.value.orig, psycopg.errors.InsufficientPrivilege), (
                f"`{statement}` must be refused by POSTGRES, not merely absent from the repository "
                "surface — the GRANT is the guarantee (AC1, AD-20, NFR-09)"
            )
            connection.rollback()


# --- AC6 / AC7: the Admin reads the refusals; nobody else does ---------------------------------


def test_an_admin_reads_the_recorded_refusals(world: _World) -> None:
    """AC6: `GET /api/v1/admin-review-flags` → `200`, naming the pair, the year, the cause, the time.

    And there is no control that clears one — the route exposes a `GET` and nothing else, because
    `FR-10` grants the Admin a read and no requirement grants a resolve (AD-20). That absence is
    asserted by the app-role grant test above: even if a resolve endpoint were written, the database
    would refuse it.
    """
    monday = _monday(10)

    _submit(world, world.alpha_id, monday, monday)
    try:
        _add_holiday(world, monday)  # prices the request to zero Working Days → refused

        response = _client.get(
            "/api/v1/admin-review-flags", headers=_auth(world.admin_token)
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "page", "page_size", "total"}

        mine = [
            item
            for item in body["items"]
            if item["leave_type_id"] == str(world.alpha_id)
        ]
        assert len(mine) == 1
        flag = mine[0]
        assert flag["employee_id"] == str(world.employee_id)
        assert flag["employee_name"] == "HR emp"
        assert flag["leave_type_code"] == f"HA-{world.suffix}"
        assert flag["leave_year"] == _YEAR
        assert flag["cause"] == vocabulary.CAUSE_HOLIDAY_RECALCULATION
        assert flag["occurred_at"]
        # No resolve, anywhere on the row: a flag is a permanent record (AD-20, ERD GAP-4).
        assert "resolved_at" not in flag
    finally:
        _drop_holiday_row(monday)


@pytest.mark.parametrize(
    "denied_role", [vocabulary.ROLE_EMPLOYEE, vocabulary.ROLE_MANAGER]
)
def test_nobody_but_an_admin_reads_the_refusals(world: _World, denied_role: str) -> None:
    """AC7: an Employee or a Manager → `403 ACTION_NOT_PERMITTED`, decided before any row is read.

    The gate is `require_role(ADMIN)`, a dependency — so the refusal happens before the query runs
    (G3: "denied by role grant, decided before any row is read"; 404 stays reserved for a scope
    miss, AD-10). It needs NO new error code: `ACTION_NOT_PERMITTED` was already declared and already
    mapped to 403, which is why this story does not touch `main.py`.
    """
    token = (
        world.employee_token
        if denied_role == vocabulary.ROLE_EMPLOYEE
        else world.manager_token
    )

    response = _client.get("/api/v1/admin-review-flags", headers=_auth(token))

    assert response.status_code == 403
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED
