"""Submitting a Leave Request, end to end against real PostgreSQL (Story 2.6, all ACs).

Implements the test side of: AC3 (the happy PENDING path stores the frozen `leave_days` and moves
`reserved` up by exactly that, with one audit row), AC4 (each of the five refusals returns 400 with
its code + `details`, and the balance CHECK never surfaces as a 500), AC5 (a managerless applicant
is auto-`APPROVED` via `consume_direct` — `reserved` stays 0, `consumed` rises — with a
`SYSTEM`/`AUTO_APPROVED_NO_MANAGER` audit row), AC6 (SM-1: two concurrent submissions that together
exceed Available — exactly one succeeds, the other is `INSUFFICIENT_BALANCE`, the balance neither
negative nor double-counted), AC7 (an Admin deactivating an Employee who holds a Pending request
gets 409 `EMPLOYEE_HAS_PENDING_REQUESTS`).

Real PostgreSQL: the balance lock, the `SELECT … FOR UPDATE` reservation, the one-transaction
submit and the SM-1 race all run through the live database and the real router. SM-1 CANNOT be
served by SQLite (no real `FOR UPDATE`); conftest skips loudly if Postgres is unreachable.
"""

import datetime
import threading
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories.engine import get_engine
from app.repositories.models import (
    AuditEntry,
    CompanyHoliday,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from app.services import leave_requests as leave_requests_service
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 400/409 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
# Entitlement 5 — a full Mon–Fri work week saturates it exactly, which is what SM-1 needs (two
# 5-day submits cannot both fit). The 3-day happy path and the managerless 3-day path fit inside it.
_ENTITLEMENT = 5
_client = TestClient(app)

# Future dates (today is 2026-07-13), so no range trips PAST_DATE_RANGE by accident.
_FRI = datetime.date(2026, 8, 14)  # Friday    (weekday()==4)  — Working Day
_SAT = datetime.date(2026, 8, 15)  # Saturday  (weekday()==5)  — WEEKEND
_SUN = datetime.date(2026, 8, 16)  # Sunday    (weekday()==6)  — WEEKEND
_MON = datetime.date(2026, 8, 17)  # Monday    (weekday()==0)  — Company Holiday (seeded)
_TUE = datetime.date(2026, 8, 18)  # Tuesday   (weekday()==1)  — Working Day
_WED = datetime.date(2026, 8, 19)  # Wednesday (weekday()==2)  — Working Day

# A full work week, no holidays — 5 Working Days, exactly the entitlement (SM-1 saturation).
_WEEK_MON = datetime.date(2026, 8, 3)  # Monday    (weekday()==0)
_WEEK_FRI = datetime.date(2026, 8, 7)  # Friday    (weekday()==4)


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        managed_id: uuid.UUID,
        managed_token: str,
        solo_id: uuid.UUID,
        solo_token: str,
        admin_token: str,
        leave_type_id: uuid.UUID,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.managed_id = managed_id
        self.managed_token = managed_token
        self.solo_id = solo_id
        self.solo_token = solo_token
        self.admin_token = admin_token
        self.leave_type_id = leave_type_id


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """A manager, a managed Employee, a managerless Employee and an Admin, one Leave Type (5).

    All are full-year joiners (joining 1 January), so a Leave Type created through the service
    materializes each a balance of the full entitlement (Story 2.4's hook).
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"ls-dept-{suffix}"
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
            email=f"ls-{label}-{suffix}@example.com",
            full_name=f"LS {label}",
            role=role,
            joining_date=datetime.date(_YEAR, 1, 1),
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
        managed_id = _employee(
            session,
            department.id,
            label="emp",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        solo_id = _employee(
            session, department.id, label="solo", role=vocabulary.ROLE_EMPLOYEE, manager_id=None
        )
        admin_id = _employee(
            session, department.id, label="adm", role=vocabulary.ROLE_ADMIN, manager_id=None
        )
        session.commit()

    managed_token = security.create_token(str(managed_id), vocabulary.ROLE_EMPLOYEE)
    solo_token = security.create_token(str(solo_id), vocabulary.ROLE_EMPLOYEE)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    # A Leave Type through the service materializes a balance for every Employee (Story 2.4).
    leave_type_id = leave_types_service.create_leave_type(
        code=f"LS-{suffix}",
        name="Leave submit",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=False,
    ).id

    try:
        yield _World(
            suffix,
            department_name,
            managed_id,
            managed_token,
            solo_id,
            solo_token,
            admin_token,
            leave_type_id,
        )
    finally:
        with Session(get_engine()) as session:
            # Audit rows first (no FK to leave_request, so delete them BEFORE the requests they
            # name). subject_id catches BOTH the EMPLOYEE rows and the SYSTEM rows (NULL actor_id).
            session.execute(
                delete(AuditEntry).where(
                    AuditEntry.subject_id.in_(
                        select(LeaveRequest.id).where(
                            LeaveRequest.leave_type_id == leave_type_id
                        )
                    )
                )
            )
            session.execute(
                delete(LeaveRequest).where(LeaveRequest.leave_type_id == leave_type_id)
            )
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id == leave_type_id)
            )
            session.execute(
                delete(CompanyHoliday).where(CompanyHoliday.name.like(f"%{suffix}%"))
            )
            session.execute(
                update(Employee)
                .where(Employee.email.like(f"%{suffix}%"))
                .values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id == leave_type_id))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _seed_holiday(date: datetime.date, name: str) -> None:
    with Session(get_engine()) as session:
        session.add(CompanyHoliday(holiday_date=date, name=name))
        session.commit()


def _balance_row(
    employee_id: uuid.UUID, leave_type_id: uuid.UUID
) -> tuple[int, int, int]:
    with Session(get_engine()) as session:
        row = session.execute(
            select(LeaveBalance.accrued, LeaveBalance.reserved, LeaveBalance.consumed).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == _YEAR,
            )
        ).one()
        return (row.accrued, row.reserved, row.consumed)


def _set_accrued(employee_id: uuid.UUID, leave_type_id: uuid.UUID, accrued: int) -> None:
    """Force a balance's accrued/prorated to `accrued` for a saturation test (SM-1 setup)."""
    with Session(get_engine()) as session:
        session.execute(
            update(LeaveBalance)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == _YEAR,
            )
            .values(accrued=accrued, prorated_entitlement=accrued, entitlement_basis=accrued)
        )
        session.commit()


def _audit_rows_for(subject_id: uuid.UUID) -> list[AuditEntry]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditEntry).where(AuditEntry.subject_id == subject_id)
            ).all()
        )


def _submit(world: _World, token: str | None, start: datetime.date, end: datetime.date):
    body = {
        "leave_type_id": str(world.leave_type_id),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    return _client.post("/api/v1/leave-requests", json=body, headers=_auth(token))


def _load_employee(employee_id: uuid.UUID) -> Employee:
    """Load a detached Employee (with manager_id) for a direct service call (SM-1 threads)."""
    with Session(get_engine(), expire_on_commit=False) as session:
        return session.get(Employee, employee_id)


# --- AC3: the happy PENDING path -----------------------------------------------------------


def test_managed_submit_reserves_and_writes_one_audit_row(world: _World) -> None:
    """AC3: a managed applicant's submit stores the frozen `leave_days`, moves `reserved` up by
    exactly that, admits the request as PENDING, and writes exactly one EMPLOYEE/SUBMITTED audit
    row (`NULL → PENDING`)."""
    _seed_holiday(_MON, f"Submit Holiday {world.suffix}")
    before = _balance_row(world.managed_id, world.leave_type_id)

    response = _submit(world, world.managed_token, _FRI, _WED)
    assert response.status_code == 201
    body = response.json()

    assert body["leave_days"] == 3  # Fri, Tue, Wed (Sat/Sun weekend, Mon holiday)
    assert body["status"] == vocabulary.STATUS_PENDING
    assert body["start_date"] == _FRI.isoformat()
    assert body["end_date"] == _WED.isoformat()

    # reserved rose by exactly the frozen day count; accrued/consumed unchanged.
    after = _balance_row(world.managed_id, world.leave_type_id)
    assert after == (before[0], before[1] + 3, before[2])

    audit = _audit_rows_for(uuid.UUID(body["id"]))
    assert len(audit) == 1
    entry = audit[0]
    assert entry.subject_type == vocabulary.SUBJECT_LEAVE_REQUEST
    assert entry.from_state is None
    assert entry.to_state == vocabulary.STATUS_PENDING
    assert entry.actor_type == vocabulary.ACTOR_EMPLOYEE
    assert entry.actor_id == world.managed_id
    assert entry.reason == vocabulary.REASON_SUBMITTED


# --- AC5: managerless auto-approval ---------------------------------------------------------


def test_managerless_submit_auto_approves_via_consume_direct(world: _World) -> None:
    """AC5/FR-09: a managerless applicant is admitted directly as APPROVED, consuming its days
    through `consume_direct` (reserved stays 0, consumed rises), with a SYSTEM/AUTO_APPROVED_NO_
    MANAGER audit row and `actor_id` NULL. The Available check still applied (it fit)."""
    before = _balance_row(world.solo_id, world.leave_type_id)
    assert before[1] == 0  # reserved starts at 0

    # No holiday seeded here, so Fri→Wed is 4 Working Days (Fri, Mon, Tue, Wed; Sat/Sun weekend).
    response = _submit(world, world.solo_token, _FRI, _WED)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == vocabulary.STATUS_APPROVED
    assert body["leave_days"] == 4

    after = _balance_row(world.solo_id, world.leave_type_id)
    # consumed rose by 4; reserved NEVER moved (consume_direct never touches it).
    assert after == (before[0], 0, before[2] + 4)

    audit = _audit_rows_for(uuid.UUID(body["id"]))
    assert len(audit) == 1
    entry = audit[0]
    assert entry.to_state == vocabulary.STATUS_APPROVED
    assert entry.from_state is None
    assert entry.actor_type == vocabulary.ACTOR_SYSTEM
    assert entry.actor_id is None
    assert entry.reason == vocabulary.REASON_AUTO_APPROVED_NO_MANAGER


def test_managerless_overspend_is_refused_insufficient_balance(world: _World) -> None:
    """AC5: "the Available check still applied" — a managerless applicant is NOT exempt. An
    overspend on the `consume_direct` path is a typed 400 INSUFFICIENT_BALANCE, the balance CHECK
    never surfaces as a 500, and nothing is written (reserved AND consumed both stay 0)."""
    before = _balance_row(world.solo_id, world.leave_type_id)  # accrued 5, reserved 0, consumed 0
    start = _WEEK_MON  # Monday
    end = datetime.date(2026, 8, 14)  # Friday of the next week → 10 Working Days > 5 Available
    response = _submit(world, world.solo_token, start, end)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.INSUFFICIENT_BALANCE
    assert body["details"]["days_requested"] == 10
    assert body["details"]["days_available"] == _ENTITLEMENT
    # consume_direct gated before any write: no request row, and reserved/consumed byte-unchanged.
    assert _balance_row(world.solo_id, world.leave_type_id) == before


# --- AC4: the five refusals, all 400, balance untouched -------------------------------------


def test_invalid_date_range_is_400(world: _World) -> None:
    """AC4: `end < start` → 400 INVALID_DATE_RANGE, nothing reserved."""
    before = _balance_row(world.managed_id, world.leave_type_id)
    response = _submit(world, world.managed_token, _WED, _FRI)  # inverted
    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.INVALID_DATE_RANGE
    assert _balance_row(world.managed_id, world.leave_type_id) == before


def test_past_date_range_is_400(world: _World) -> None:
    """AC4: a range wholly in the past (end < today) → 400 PAST_DATE_RANGE."""
    start = datetime.date(_YEAR, 1, 5)  # Monday   (weekday()==0) — long before today (Jul 13)
    end = datetime.date(_YEAR, 1, 9)  # Friday   (weekday()==4)
    response = _submit(world, world.managed_token, start, end)
    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.PAST_DATE_RANGE


def test_spans_two_leave_years_is_400_and_names_the_boundary(world: _World) -> None:
    """AC4: a Dec→Jan range → 400 SPANS_TWO_LEAVE_YEARS, `details.boundary` the 31 December."""
    start = datetime.date(_YEAR, 12, 30)  # Wednesday (weekday()==2)
    end = datetime.date(_YEAR + 1, 1, 4)  # Monday    (weekday()==0)
    response = _submit(world, world.managed_token, start, end)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.SPANS_TWO_LEAVE_YEARS
    assert body["details"]["boundary"] == datetime.date(_YEAR, 12, 31).isoformat()


def test_zero_leave_days_is_400(world: _World) -> None:
    """AC4: a weekend-only range (0 Working Days) → 400 ZERO_LEAVE_DAYS."""
    response = _submit(world, world.managed_token, _SAT, _SUN)  # Sat→Sun, future, same year
    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.ZERO_LEAVE_DAYS


def test_insufficient_balance_is_400_and_the_check_never_surfaces(world: _World) -> None:
    """AC4: an overspend is a typed 400 INSUFFICIENT_BALANCE (naming the numbers), NOT a CHECK 500,
    and the balance is byte-unchanged after the refusal."""
    before = _balance_row(world.managed_id, world.leave_type_id)  # accrued 5
    # A full week (5) then another full week would exceed 5; here request 5+? Instead request a
    # range costing more than 5: two consecutive full weeks = 10 Working Days > 5.
    start = _WEEK_MON  # Monday
    end = datetime.date(2026, 8, 14)  # Friday of the next week → 10 Working Days
    response = _submit(world, world.managed_token, start, end)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.INSUFFICIENT_BALANCE
    assert body["details"]["days_requested"] == 10
    assert body["details"]["days_available"] == _ENTITLEMENT
    # The refusal wrote nothing (no request row, no reservation).
    assert _balance_row(world.managed_id, world.leave_type_id) == before


def test_unknown_leave_type_is_404_not_500(world: _World) -> None:
    """A `leave_type_id` naming no materialized balance is `404 RESOURCE_NOT_FOUND`, never a raw
    500 from `balances._lock` — submit mirrors the preview's existence guard (code review
    2026-07-13). A valid, future range that survives the pure gates but has no balance row for its
    `leave_year` fails the same way."""
    response = _submit(world, world.managed_token, _MON, _WED)
    # (a control: this range against a REAL leave type succeeds — proves the range itself is valid.)
    # Here we point at an unknown type instead:
    unknown = _client.post(
        "/api/v1/leave-requests",
        headers=_auth(world.managed_token),
        json={
            "leave_type_id": str(uuid.uuid4()),
            "start_date": _MON.isoformat(),
            "end_date": _WED.isoformat(),
        },
    )
    assert response.status_code == 201  # the control range is genuinely submittable
    assert unknown.status_code == 404
    assert unknown.json()["code"] == vocabulary.RESOURCE_NOT_FOUND


# --- AC7: the pending-request deactivation guard becomes executable -------------------------


def test_admin_cannot_deactivate_employee_with_pending_request(world: _World) -> None:
    """AC7: an Employee holding a Pending request cannot be deactivated — 409
    EMPLOYEE_HAS_PENDING_REQUESTS (naming the count)."""
    submit = _submit(world, world.managed_token, _FRI, _WED)
    assert submit.status_code == 201  # a PENDING request now exists

    response = _client.post(
        f"/api/v1/employees/{world.managed_id}/deactivate",
        headers=_auth(world.admin_token),
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == vocabulary.EMPLOYEE_HAS_PENDING_REQUESTS
    assert body["details"]["pending_requests"] == 1


# --- AC6: SM-1 concurrent double-submit, real PostgreSQL ------------------------------------


def test_sm1_concurrent_double_submit_admits_exactly_one(world: _World) -> None:
    """AC6/SM-1: two concurrent submissions that together exceed Available — exactly one succeeds,
    the other is refused INSUFFICIENT_BALANCE, and the balance is neither negative nor
    double-counted.

    Available is set to exactly one full week (5). Both threads submit the SAME 5-day week
    concurrently; the second blocks on `SELECT … FOR UPDATE` until the first commits, then reads
    the post-reservation balance and is refused. This is the correctness test Story 2.4 built
    `reserve` lock-correct for; SQLite could not serve it (no real `FOR UPDATE`)."""
    # Saturate: available == 5 == the week's Working Days, so only ONE submit can fit.
    _set_accrued(world.managed_id, world.leave_type_id, _ENTITLEMENT)
    actor = _load_employee(world.managed_id)

    barrier = threading.Barrier(2)
    results: list[object] = []
    lock = threading.Lock()

    def _attempt() -> None:
        barrier.wait()  # both threads enter the service as simultaneously as possible
        try:
            view = leave_requests_service.submit_leave_request(
                actor,
                leave_type_id=world.leave_type_id,
                start=_WEEK_MON,
                end=_WEEK_FRI,
            )
            outcome: object = view
        except DomainError as exc:
            outcome = exc
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    successes = [r for r in results if not isinstance(r, DomainError)]
    refusals = [r for r in results if isinstance(r, DomainError)]
    assert len(successes) == 1, f"exactly one submit must succeed, got {results}"
    assert len(refusals) == 1
    assert refusals[0].code == vocabulary.INSUFFICIENT_BALANCE

    # The balance is neither negative nor double-counted: reserved == 5, available == 0.
    accrued, reserved, consumed = _balance_row(world.managed_id, world.leave_type_id)
    assert reserved == _ENTITLEMENT
    assert accrued - consumed - reserved == 0  # available, never negative

    # Exactly one leave_request row landed for this employee (the other rolled back entirely).
    with Session(get_engine()) as session:
        count = session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .where(LeaveRequest.employee_id == world.managed_id)
        )
    assert count == 1


# --- AC2: the code-layer append-only guarantee (no update/delete surface) -------------------


def test_audit_and_request_repositories_expose_no_update_or_delete() -> None:
    """AC2 (AD-8/AD-9): the binding, testable form of "append-only" is the code layer — neither
    `repositories/audit_entry` nor `repositories/leave_request` exposes an update or delete method.

    With the codebase running a single Postgres role, a DB-role REVOKE UPDATE/DELETE would be a
    no-op (an owner cannot be denied on its own table — Story 2.6 Decision Point), so THIS surface
    is the guarantee. `audit_entry` offers only INSERT; `leave_request` offers INSERT + a COUNT.
    The request row's lifecycle transitions are Story 2.7's guarded UPDATE, not a method here.
    """
    from app.repositories import audit_entry as audit_entry_repo
    from app.repositories import leave_request as leave_request_repo

    def _public_callables(module: object) -> set[str]:
        return {
            name
            for name in dir(module)
            if not name.startswith("_") and callable(getattr(module, name))
        }

    audit_surface = {
        name
        for name in _public_callables(audit_entry_repo)
        # Ignore imported symbols (Session, AuditEntry, the datetime/uuid modules); keep the
        # module's OWN functions, identified by their `__module__`.
        if getattr(getattr(audit_entry_repo, name), "__module__", "")
        == audit_entry_repo.__name__
    }
    assert audit_surface == {"insert_audit_entry"}, (
        f"audit_entry repo must expose ONLY insert (append-only, AD-8); found {audit_surface}"
    )

    request_surface = {
        name
        for name in _public_callables(leave_request_repo)
        if getattr(getattr(leave_request_repo, name), "__module__", "")
        == leave_request_repo.__name__
    }
    assert request_surface == {"insert_leave_request", "count_pending_for_employee"}, (
        "leave_request repo must expose no update/delete of a request row (create + count only); "
        f"found {request_surface}"
    )


# --- Auth: no token is 401 -----------------------------------------------------------------


def test_no_token_is_401(world: _World) -> None:
    """No token (and an invalid token) is 401 TOKEN_INVALID, never a write."""
    for token in (None, "not-a-real-token"):
        response = _submit(world, token, _FRI, _WED)
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID
