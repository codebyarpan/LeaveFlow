"""The leave-request preview, end to end against real PostgreSQL (Story 2.5, all ACs).

Implements the test side of: AC1 (the response carries `leave_days`, `available_before`,
`available_after`, and an `excluded_dates` breakdown naming each excluded date's reason, a HOLIDAY
carrying its name), AC5 (`count + len(excluded) == span`, verified on the happy path), AC8
(`available_*` derived at the projection), AC9 (the preview is READ-ONLY — the balance row is
byte-unchanged, `reserved` stays 0), AC10 (an unknown Leave Type is a byte-identical 404; no token
is 401), AC11 (an overspend returns 200 with a negative `available_after` and NO
`INSUFFICIENT_BALANCE`).

Real PostgreSQL: the scope predicate, the balance read, the holiday range query and the derivation
all run through the live database and the real router. A balance is materialized by creating a Leave
Type through the service (Story 2.4's hook materializes for every Employee); the caller joins on
1 January, so the balance is the full entitlement.
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
    CompanyHoliday,
    Department,
    Employee,
    LeaveBalance,
    LeaveType,
)
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 401/404 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
_ENTITLEMENT = 12
_client = TestClient(app)

# The canonical span — Fri → Wed, inclusive, over a weekend and a Monday holiday. Every weekday is
# stated in a comment (the domain-test discipline): a mis-remembered date fails the reader.
_FRI = datetime.date(2026, 8, 14)  # Friday    (weekday()==4)  — Working Day
_SAT = datetime.date(2026, 8, 15)  # Saturday  (weekday()==5)  — WEEKEND
_SUN = datetime.date(2026, 8, 16)  # Sunday    (weekday()==6)  — WEEKEND
_MON = datetime.date(2026, 8, 17)  # Monday    (weekday()==0)  — Company Holiday
_TUE = datetime.date(2026, 8, 18)  # Tuesday   (weekday()==1)  — Working Day
_WED = datetime.date(2026, 8, 19)  # Wednesday (weekday()==2)  — Working Day


class _World:
    def __init__(
        self, suffix: str, employee_id: uuid.UUID, token: str, leave_type_id: uuid.UUID
    ) -> None:
        self.suffix = suffix
        self.employee_id = employee_id
        self.token = token
        self.leave_type_id = leave_type_id


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """One Employee (full-year joiner) and one Leave Type (entitlement 12), balance materialized."""
    suffix = uuid.uuid4().hex[:12]
    department_name = f"lp-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()

        employee = Employee(
            department_id=department.id,
            manager_id=None,
            email=f"lp-caller-{suffix}@example.com",
            full_name="LP Caller",
            role=vocabulary.ROLE_EMPLOYEE,
            joining_date=datetime.date(_YEAR, 1, 1),  # full-year → full entitlement
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        employee_id = employee.id
        session.commit()

    token = security.create_token(str(employee_id), vocabulary.ROLE_EMPLOYEE)

    # A Leave Type through the service materializes a balance for every Employee (Story 2.4).
    leave_type_id = leave_types_service.create_leave_type(
        code=f"LP-{suffix}",
        name="Leave preview",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=False,
    ).id

    try:
        yield _World(suffix, employee_id, token, leave_type_id)
    finally:
        with Session(get_engine()) as session:
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id == leave_type_id)
            )
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.employee_id == employee_id)
            )
            session.execute(
                delete(CompanyHoliday).where(CompanyHoliday.name.like(f"%{suffix}%"))
            )
            session.execute(
                update(Employee).where(Employee.email.like(f"%{suffix}%")).values(manager_id=None)
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


def _read_balance_row(
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


def _preview(world: _World, start: datetime.date, end: datetime.date, token: str | None = ...):  # type: ignore[assignment]
    body = {
        "leave_type_id": str(world.leave_type_id),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    headers = _auth(world.token if token is ... else token)
    return _client.post("/api/v1/leave-requests/preview", json=body, headers=headers)


# --- AC1/AC5/AC8: the happy path — count, named breakdown, derived balance -----------------


def test_happy_path_counts_names_and_derives(world: _World) -> None:
    """AC1/AC4/AC5/AC8: Fri→Wed over a weekend and a named Monday holiday.

    `leave_days` is the 3 Working Days; `excluded_dates` names the two weekend days as WEEKEND
    (`name` null) and the holiday as HOLIDAY with its name; `available_before == accrued -
    consumed - reserved`; `available_after == available_before - leave_days`; and the consistency
    invariant `leave_days + len(excluded_dates) == span` holds. Reasons via `vocabulary`, never a
    literal (AC7).
    """
    holiday_name = f"Preview Holiday {world.suffix}"
    _seed_holiday(_MON, holiday_name)

    response = _preview(world, _FRI, _WED)
    assert response.status_code == 200
    body = response.json()

    assert body["leave_days"] == 3
    # The breakdown, chronological: Sat, Sun (WEEKEND, no name), Mon (HOLIDAY, named).
    assert body["excluded_dates"] == [
        {"date": _SAT.isoformat(), "reason": vocabulary.EXCLUSION_WEEKEND, "name": None},
        {"date": _SUN.isoformat(), "reason": vocabulary.EXCLUSION_WEEKEND, "name": None},
        {"date": _MON.isoformat(), "reason": vocabulary.EXCLUSION_HOLIDAY, "name": holiday_name},
    ]

    # available derived at the projection: full-year joiner → 12, nothing reserved/consumed.
    assert body["available_before"] == _ENTITLEMENT  # 12 - 0 - 0
    assert body["available_after"] == _ENTITLEMENT - 3  # 12 - 3 = 9

    # The consistency invariant (AC5), asserted on the wire.
    span = (_WED - _FRI).days + 1
    assert body["leave_days"] + len(body["excluded_dates"]) == span


# --- AC9: the preview is READ-ONLY — the balance row is byte-unchanged ----------------------


def test_preview_is_read_only_balance_unchanged(world: _World) -> None:
    """AC9/AD-3: a preview writes nothing — the balance row is identical before and after, and
    `reserved` stays 0 (no reservation happened). A preview can be issued any number of times."""
    before = _read_balance_row(world.employee_id, world.leave_type_id)
    assert before[1] == 0  # reserved starts at 0

    for _ in range(3):
        assert _preview(world, _FRI, _WED).status_code == 200

    after = _read_balance_row(world.employee_id, world.leave_type_id)
    assert after == before  # byte-unchanged
    assert after[1] == 0  # reserved never moved


# --- AC11: an overspend is not refused -----------------------------------------------------


def test_overspend_returns_200_with_negative_available_after(world: _World) -> None:
    """AC11: a range whose `leave_days` exceeds `available_before` returns 200 with a NEGATIVE
    `available_after` — the honest projection — and never raises `INSUFFICIENT_BALANCE`."""
    start = datetime.date(2026, 8, 3)  # Monday   (weekday()==0)
    end = datetime.date(2026, 8, 28)  # Friday   (weekday()==4) — 4 Mon–Fri weeks, no holidays
    response = _preview(world, start, end)

    assert response.status_code == 200
    body = response.json()
    assert body["leave_days"] == 20  # 4 weeks × 5 Working Days
    assert body["available_after"] == _ENTITLEMENT - 20  # 12 - 20 = -8, not clamped
    assert body["available_after"] < 0
    # Not an error envelope: no `INSUFFICIENT_BALANCE`, no `code` key.
    assert "code" not in body


# --- AC10: unknown Leave Type is a byte-identical 404; no token is 401 ----------------------


def test_unknown_leave_type_is_byte_identical_404(world: _World) -> None:
    """AC10: a `leave_type_id` naming no materialized balance is `404 RESOURCE_NOT_FOUND`,
    byte-identical to another not-found — a scope/absence miss discloses nothing."""
    body_one = {
        "leave_type_id": str(uuid.uuid4()),
        "start_date": _FRI.isoformat(),
        "end_date": _WED.isoformat(),
    }
    body_two = {
        "leave_type_id": str(uuid.uuid4()),
        "start_date": _FRI.isoformat(),
        "end_date": _WED.isoformat(),
    }
    first = _client.post("/api/v1/leave-requests/preview", json=body_one, headers=_auth(world.token))
    second = _client.post(
        "/api/v1/leave-requests/preview", json=body_two, headers=_auth(world.token)
    )

    assert first.status_code == 404
    assert first.json()["code"] == vocabulary.RESOURCE_NOT_FOUND
    assert second.status_code == 404
    assert first.content == second.content  # byte-identical (AD-10)


def test_no_token_is_401(world: _World) -> None:
    """AC10: no token (and an invalid token) is `401 TOKEN_INVALID`."""
    for token in (None, "not-a-real-token"):
        response = _preview(world, _FRI, _WED, token=token)
        assert response.status_code == 401
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --- Weekend-only span: 0 days, both WEEKEND, available unchanged ---------------------------


def test_weekend_only_span_is_zero_days(world: _World) -> None:
    """AC5: a Saturday→Sunday range costs 0 days, both excluded as WEEKEND, and
    `available_after == available_before` (nothing is spent)."""
    response = _preview(world, _SAT, _SUN)
    assert response.status_code == 200
    body = response.json()

    assert body["leave_days"] == 0
    assert [ex["reason"] for ex in body["excluded_dates"]] == [
        vocabulary.EXCLUSION_WEEKEND,
        vocabulary.EXCLUSION_WEEKEND,
    ]
    assert all(ex["name"] is None for ex in body["excluded_dates"])
    assert body["available_after"] == body["available_before"] == _ENTITLEMENT


# --- Resource guard: an oversized span is refused as malformed input (code review 2026-07-13) ---


def test_oversized_span_is_refused_as_malformed_input(world: _World) -> None:
    """A span beyond the preview's 366-day ceiling is a 422 (malformed input), not a 200.

    Defensive resource guard: an unbounded range would drive the pure count/breakdown through
    millions of day-by-day iterations. The refusal is framework input validation (422) — the same
    class as a bad UUID here — NOT a domain error code, so `INSUFFICIENT_BALANCE`/`RESOURCE_NOT_FOUND`
    are untouched, and range *validity* (incl. the cross-year refusal) remains Story 2.6's.
    """
    start = datetime.date(2026, 1, 1)
    end = datetime.date(2027, 12, 31)  # ~730 days — well over the 366-day ceiling
    response = _preview(world, start, end)
    assert response.status_code == 422

    # A span exactly at the ceiling (a full leap Leave Year, 366 days inclusive) is still accepted.
    at_ceiling = _preview(world, datetime.date(2028, 1, 1), datetime.date(2028, 12, 31))
    assert at_ceiling.status_code == 200
