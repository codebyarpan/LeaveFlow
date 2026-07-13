"""Balance rows are materialized on Employee-create and Leave-Type-create (Story 2.4, AC3).

Implements the test side of AC3 / SM-5 / AD-17: creating an Employee materializes a
`leave_balance` row for that Employee × every Leave Type; creating a Leave Type materializes a
row for that Leave Type × every Employee — both for the current Leave Year, with proration
applied and `carried_forward = 0`, routed through `balances.set_accrual` only. This is the
`SM-5` guarantee that a Leave Type added through the API immediately has a balance to apply
against.

Real PostgreSQL: proration lands in the actual `leave_balance` rows, and the materialization
loop runs inside the create command's single transaction (AD-3). Exercises the service layer
(`employee_service.create_employee` / `leave_types_service.create_leave_type`) — exactly what
the `POST /employees` / `POST /leave-types` routes call; the HTTP layer itself is unchanged
and covered by `test_employees.py` / `test_leave_types.py`.
"""

import datetime
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, func, select
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.domain.proration import prorate_entitlement
from app.repositories.engine import get_engine
from app.repositories.models import Department, Employee, LeaveBalance, LeaveType
from app.services import employee as employee_service
from app.services import leave_types as leave_types_service

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_CURRENT_YEAR = datetime.date.today().year


class _World:
    def __init__(self, department_id: uuid.UUID, suffix: str) -> None:
        self.department_id = department_id
        self.suffix = suffix

    def insert_leave_type(self, annual_entitlement: int) -> uuid.UUID:
        """Insert a throwaway Leave Type directly (setup, not the code under test)."""
        with Session(get_engine()) as session:
            leave_type = LeaveType(
                code=f"MZ-{uuid.uuid4().hex[:8]}",
                name="Materialization type",
                annual_entitlement=annual_entitlement,
                carries_forward=False,
                carry_forward_cap=None,
                requires_supporting_document=False,
            )
            session.add(leave_type)
            session.commit()
            return leave_type.id

    def insert_employee(self, joining_date: datetime.date) -> uuid.UUID:
        """Insert a throwaway Employee directly (setup, not the code under test)."""
        with Session(get_engine()) as session:
            employee = Employee(
                department_id=self.department_id,
                manager_id=None,
                email=f"mz-{uuid.uuid4().hex[:10]}-{self.suffix}@example.com",
                full_name="Materialization subject",
                role=vocabulary.ROLE_EMPLOYEE,
                joining_date=joining_date,
                is_active=True,
                password_hash=security.hash_password(_KNOWN_PASSWORD),
            )
            session.add(employee)
            session.commit()
            return employee.id


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """A shared department; teardown removes this run's balances, employees, types, department."""
    suffix = uuid.uuid4().hex[:12]
    department_name = f"mz-dept-{suffix}"
    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.commit()
        department_id = department.id

    try:
        yield _World(department_id, suffix)
    finally:
        with Session(get_engine()) as session:
            emp_ids = session.scalars(
                select(Employee.id).where(Employee.email.like(f"%{suffix}%"))
            ).all()
            if emp_ids:
                session.execute(
                    delete(LeaveBalance).where(LeaveBalance.employee_id.in_(emp_ids))
                )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            # Balances against this run's throwaway types, then the types themselves.
            mz_type_ids = session.scalars(
                select(LeaveType.id).where(LeaveType.code.like("MZ-%"))
            ).all()
            if mz_type_ids:
                session.execute(
                    delete(LeaveBalance).where(LeaveBalance.leave_type_id.in_(mz_type_ids))
                )
            session.execute(delete(LeaveType).where(LeaveType.code.like("MZ-%")))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _balance(employee_id: uuid.UUID, leave_type_id: uuid.UUID) -> LeaveBalance:
    with Session(get_engine(), expire_on_commit=False) as session:
        return session.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == _CURRENT_YEAR,
            )
        ).one()


def _count_balances_for_employee(employee_id: uuid.UUID) -> int:
    with Session(get_engine()) as session:
        return session.scalar(
            select(func.count())
            .select_from(LeaveBalance)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_year == _CURRENT_YEAR,
            )
        )


def _count_balances_for_type(leave_type_id: uuid.UUID) -> int:
    with Session(get_engine()) as session:
        return session.scalar(
            select(func.count())
            .select_from(LeaveBalance)
            .where(
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == _CURRENT_YEAR,
            )
        )


def _total_leave_types() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(LeaveType))


def _total_employees() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(Employee))


# --- AC3: POST /employees materializes a balance for every Leave Type ---------------------


def test_creating_an_employee_materializes_a_balance_for_every_leave_type(
    world: _World,
) -> None:
    """AC3: a new Employee gets a current-year balance for every Leave Type, prorated, carry 0.

    Two known Leave Types (entitlements 12 and 30) are seeded; a September joiner prorates to
    `annual × 4/12` floored (12→4, 30→10). The new Employee's balance-row count equals the total
    number of Leave Types — no type is missed.
    """
    lt_twelve = world.insert_leave_type(12)
    lt_thirty = world.insert_leave_type(30)
    joining = datetime.date(_CURRENT_YEAR, 9, 1)  # September → 4 remaining months

    total_types_before = _total_leave_types()
    employee_id = employee_service.create_employee(
        email=f"joiner-{world.suffix}@example.com",
        full_name="September Joiner",
        role=vocabulary.ROLE_EMPLOYEE,
        department_id=world.department_id,
        joining_date=joining,
        initial_password=_KNOWN_PASSWORD,
    ).id

    # A balance exists for each known type, prorated and floored, accrued == prorated, carry 0.
    b12 = _balance(employee_id, lt_twelve)
    assert b12.prorated_entitlement == prorate_entitlement(12, joining, _CURRENT_YEAR) == 4
    assert b12.accrued == b12.prorated_entitlement
    assert b12.carried_forward == 0
    assert b12.entitlement_basis == 12
    assert b12.reserved == 0 and b12.consumed == 0

    b30 = _balance(employee_id, lt_thirty)
    assert b30.prorated_entitlement == prorate_entitlement(30, joining, _CURRENT_YEAR) == 10
    assert b30.accrued == 10

    # Exactly one balance per Leave Type — the new Employee's count equals the type count.
    assert _count_balances_for_employee(employee_id) == total_types_before


# --- AC3 / SM-5: POST /leave-types materializes a balance for every Employee ---------------


def test_creating_a_leave_type_materializes_a_balance_for_every_employee(
    world: _World,
) -> None:
    """AC3/SM-5: a new Leave Type gets a current-year balance for every Employee, prorated.

    Two Employees are seeded (a January joiner → full entitlement, a September joiner → 4/12);
    a new Leave Type (entitlement 12) materializes a balance for each. The new type's balance-row
    count equals the total number of Employees — this is SM-5: a fourth type is immediately
    applicable by everyone, no migration, no code change.
    """
    jan_joiner = world.insert_employee(datetime.date(_CURRENT_YEAR, 1, 1))
    sep_joiner = world.insert_employee(datetime.date(_CURRENT_YEAR, 9, 1))

    total_employees_before = _total_employees()
    leave_type = leave_types_service.create_leave_type(
        code=f"MZ-{uuid.uuid4().hex[:8]}",
        name="A new policy, added through the API",
        annual_entitlement=12,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=False,
    )

    b_jan = _balance(jan_joiner, leave_type.id)
    assert b_jan.prorated_entitlement == 12  # full year
    assert b_jan.accrued == 12 and b_jan.carried_forward == 0

    b_sep = _balance(sep_joiner, leave_type.id)
    assert b_sep.prorated_entitlement == 4  # 12 × 4/12

    # Exactly one balance per Employee — the new type's count equals the employee count.
    assert _count_balances_for_type(leave_type.id) == total_employees_before
