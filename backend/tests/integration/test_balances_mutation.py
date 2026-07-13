"""The eight balance-mutation operations, each exercised directly against real PostgreSQL.

Implements the test side of Story 2.4 AC4 / AC8 / AD-17 / AD-5: each of the eight operations
performs its REAL mutation (not a stub) under the row lock, with the non-negativity refusal
built in. Materialize a row via `set_accrual`, call the method, assert the row — for every one
of the eight.

Real PostgreSQL (not SQLite): `ON CONFLICT`, `SELECT … FOR UPDATE` and the CHECK backstops are
database behaviour SQLite lacks. The SM-1 concurrent double-submit test is NOT here — it lands
at the submission path (Story 2.6); 2.4 tests each method single-transaction (Dev Notes,
"Scope boundary").
"""

import datetime
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, select
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee, LeaveBalance, LeaveType
from app.services import balances

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = 2026


class _World:
    """One Employee, and a factory for throwaway Leave Types so each test owns its balance key."""

    def __init__(self, employee_id: uuid.UUID, department_id: uuid.UUID, suffix: str) -> None:
        self.employee_id = employee_id
        self.department_id = department_id
        self.suffix = suffix

    def make_leave_type(self) -> uuid.UUID:
        """Insert a throwaway Leave Type (test setup) and return its id."""
        with Session(get_engine()) as session:
            leave_type = LeaveType(
                code=f"BM-{uuid.uuid4().hex[:8]}",
                name="Balance mutation type",
                annual_entitlement=30,
                carries_forward=False,
                carry_forward_cap=None,
                requires_supporting_document=False,
            )
            session.add(leave_type)
            session.commit()
            return leave_type.id

    def materialize(
        self,
        leave_type_id: uuid.UUID,
        *,
        prorated: int,
        carried: int = 0,
        basis: int | None = None,
    ) -> None:
        """Materialize the balance row through `set_accrual` — the only create path (AD-17)."""
        with Session(get_engine()) as session:
            balances.set_accrual(
                session,
                employee_id=self.employee_id,
                leave_type_id=leave_type_id,
                leave_year=_YEAR,
                prorated_entitlement=prorated,
                carried_forward=carried,
                entitlement_basis=basis if basis is not None else prorated,
            )
            session.commit()

    def read(self, leave_type_id: uuid.UUID) -> LeaveBalance:
        """Return a detached snapshot of the balance row for assertions."""
        with Session(get_engine(), expire_on_commit=False) as session:
            return session.scalars(
                select(LeaveBalance).where(
                    LeaveBalance.employee_id == self.employee_id,
                    LeaveBalance.leave_type_id == leave_type_id,
                    LeaveBalance.leave_year == _YEAR,
                )
            ).one()


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """One department, one Employee; teardown deletes balances, employee, leave types, dept."""
    suffix = uuid.uuid4().hex[:12]
    department_name = f"bm-dept-{suffix}"
    email = f"bm-{suffix}@example.com"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
        employee = Employee(
            department_id=department.id,
            manager_id=None,
            email=email,
            full_name="Balance Mutation Subject",
            role=vocabulary.ROLE_EMPLOYEE,
            joining_date=datetime.date(_YEAR, 1, 1),
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.commit()
        employee_id = employee.id
        department_id = department.id

    try:
        yield _World(employee_id, department_id, suffix)
    finally:
        with Session(get_engine()) as session:
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.employee_id == employee_id)
            )
            session.execute(delete(Employee).where(Employee.id == employee_id))
            session.execute(delete(LeaveType).where(LeaveType.code.like("BM-%")))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


# --- set_accrual: the materializer (create-or-update) -------------------------------------


def test_set_accrual_on_a_fresh_key_inserts_with_reserved_and_consumed_zero(
    world: _World,
) -> None:
    """AC8: a fresh `set_accrual` inserts the accrual triple; reserved/consumed default to 0."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, carried=2, basis=12)

    row = world.read(lt)
    assert row.accrued == 12  # prorated_entitlement + carried_forward
    assert row.prorated_entitlement == 10
    assert row.carried_forward == 2
    assert row.entitlement_basis == 12
    assert row.reserved == 0
    assert row.consumed == 0


def test_set_accrual_on_an_existing_key_updates_accrual_without_disturbing_reserved_consumed(
    world: _World,
) -> None:
    """AC8/AD-17: a second `set_accrual` re-derives the accrual triple; reserved/consumed stay.

    Reserve and consume first, then re-accrue: the recalculation touches only accrual, never
    the committed/spent columns — the idempotent re-materialization AD-17 needs.
    """
    lt = world.make_leave_type()
    world.materialize(lt, prorated=12, carried=0, basis=12)

    with Session(get_engine()) as session:
        balances.reserve(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=3)
        balances.consume_direct(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=2)
        session.commit()

    # Re-accrue with a different basis (a policy change, Story 2.12's shape).
    world.materialize(lt, prorated=20, carried=0, basis=20)

    row = world.read(lt)
    assert row.accrued == 20
    assert row.entitlement_basis == 20
    # reserved/consumed untouched by the re-accrual.
    assert row.reserved == 3
    assert row.consumed == 2


# --- reserve ------------------------------------------------------------------------------


def test_reserve_reduces_available(world: _World) -> None:
    """AC8: `reserve` moves days into `reserved`, reducing available by the same amount."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)

    with Session(get_engine()) as session:
        balances.reserve(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=4)
        session.commit()

    row = world.read(lt)
    assert row.reserved == 4
    assert row.consumed == 0
    # available = accrued - consumed - reserved = 10 - 0 - 4 = 6
    assert row.accrued - row.consumed - row.reserved == 6


def test_reserve_refuses_an_overspend_with_insufficient_balance(world: _World) -> None:
    """AC8/AD-5: reserving more than available raises 400 INSUFFICIENT_BALANCE naming the numbers,
    and nothing is written (the gate fires before the write; no CHECK reaches the client)."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=5, basis=5)

    with Session(get_engine()) as session:
        with pytest.raises(DomainError) as raised:
            balances.reserve(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=6)
        session.rollback()

    assert raised.value.code == vocabulary.INSUFFICIENT_BALANCE
    assert raised.value.details == {"days_requested": 6, "days_available": 5}
    # Nothing was written.
    row = world.read(lt)
    assert row.reserved == 0


# --- consume_reserved ---------------------------------------------------------------------


def test_consume_reserved_moves_reserved_to_consumed_leaving_available_unchanged(
    world: _World,
) -> None:
    """AC8: `consume_reserved` transfers reserved→consumed; available is unchanged."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)

    with Session(get_engine()) as session:
        balances.reserve(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=4)
        session.commit()
    before = world.read(lt)
    available_before = before.accrued - before.consumed - before.reserved

    with Session(get_engine()) as session:
        balances.consume_reserved(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=4)
        session.commit()

    row = world.read(lt)
    assert row.reserved == 0
    assert row.consumed == 4
    assert row.accrued - row.consumed - row.reserved == available_before  # unchanged


def test_consume_reserved_beyond_reserved_is_guarded_not_a_check_500(world: _World) -> None:
    """AC8: consuming more than reserved is a caller-invariant break — guarded (ValueError),
    never left to fire the reserved >= 0 CHECK."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)
    with Session(get_engine()) as session:
        balances.reserve(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=2)
        session.commit()

    with Session(get_engine()) as session:
        with pytest.raises(ValueError):
            balances.consume_reserved(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=3)
        session.rollback()


# --- consume_direct -----------------------------------------------------------------------


def test_consume_direct_consumes_and_never_touches_reserved(world: _World) -> None:
    """AC8/FR-09: `consume_direct` consumes without reserving; `reserved` stays 0."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)

    with Session(get_engine()) as session:
        balances.consume_direct(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=3)
        session.commit()

    row = world.read(lt)
    assert row.consumed == 3
    assert row.reserved == 0  # never touched — the FR-09 managerless auto-approval path


def test_consume_direct_refuses_an_overspend(world: _World) -> None:
    """AC8/AD-5: consuming more than available raises 400 INSUFFICIENT_BALANCE, nothing written."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=3, basis=3)

    with Session(get_engine()) as session:
        with pytest.raises(DomainError) as raised:
            balances.consume_direct(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=4)
        session.rollback()

    assert raised.value.code == vocabulary.INSUFFICIENT_BALANCE
    assert raised.value.details == {"days_requested": 4, "days_available": 3}
    assert world.read(lt).consumed == 0


# --- release_reserved / release_consumed --------------------------------------------------


def test_release_reserved_decrements_reserved(world: _World) -> None:
    """AC8: `release_reserved` decrements `reserved` (a rejection/cancellation of a Pending)."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)
    with Session(get_engine()) as session:
        balances.reserve(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=5)
        session.commit()

    with Session(get_engine()) as session:
        balances.release_reserved(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=5)
        session.commit()

    assert world.read(lt).reserved == 0


def test_release_consumed_decrements_consumed(world: _World) -> None:
    """AC8/BR-05: `release_consumed` returns consumed days (an approved-leave cancellation)."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)
    with Session(get_engine()) as session:
        balances.consume_direct(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=4)
        session.commit()

    with Session(get_engine()) as session:
        balances.release_consumed(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, days=4)
        session.commit()

    assert world.read(lt).consumed == 0


# --- adjust_reserved / adjust_consumed ----------------------------------------------------


def test_adjust_reserved_re_derives_the_column(world: _World) -> None:
    """AC8: `adjust_reserved` sets Reserved to an absolute recomputed value under the lock."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)

    with Session(get_engine()) as session:
        balances.adjust_reserved(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, reserved=6)
        session.commit()

    assert world.read(lt).reserved == 6


def test_adjust_consumed_re_derives_the_column(world: _World) -> None:
    """AC8: `adjust_consumed` sets Consumed to an absolute recomputed value under the lock."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=10, basis=10)

    with Session(get_engine()) as session:
        balances.adjust_consumed(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, consumed=7)
        session.commit()

    assert world.read(lt).consumed == 7


def test_adjust_reserved_that_would_make_available_negative_is_guarded(world: _World) -> None:
    """AC8: an adjustment that would drive available below 0 is guarded (ValueError), never a
    CHECK 500."""
    lt = world.make_leave_type()
    world.materialize(lt, prorated=5, basis=5)

    with Session(get_engine()) as session:
        with pytest.raises(ValueError):
            balances.adjust_reserved(session, employee_id=world.employee_id, leave_type_id=lt, leave_year=_YEAR, reserved=6)
        session.rollback()
