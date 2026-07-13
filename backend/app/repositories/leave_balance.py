"""Leave Balance SQL: the row lock, the accrual upsert, and the scoped read.

Implements: AD-3 (the `SELECT … FOR UPDATE` lock that the balance-mutation module decides
under), AD-17 (the `set_accrual` upsert is the only write path into the accrual triple),
AD-10 / NFR-04 (the read getter is genuinely data-scoped — `leave_balance` is the first
Employee-derived resource, so `list_balances` takes the `actor` and applies the scope as a
SQL predicate, never a post-fetch filter). SM-6.

The repository issues the SQL; `services/balances.py` holds the balance arithmetic and the
`INSUFFICIENT_BALANCE` refusal (AD-1). This module never decides an outcome — it locks a
row, upserts an accrual, or returns scoped rows.

--- On the scoped-getter guard (`tests/test_scoped_getters.py`) ---

`list_balances` and `get_balance` are `list_`/`get_` getters that take a `session`, so the guard
requires each to take the `actor` — and both do, because `leave_balance` is EXACTLY the "first
genuinely data-scoped resource" `repositories/scoping.py`'s docstring anticipates. Neither is
exempt like the reference-data getters (leave types, holidays): a balance belongs to an Employee,
so a read that could return another Employee's balance MUST scope in SQL. `get_balance` (Story
2.5) is the preview's single-row, non-locking counterpart to `list_balances`. `lock_balance`
(`lock_` prefix, a write-path primitive) and `upsert_accrual` (a write) are correctly not
scoped-getter candidates — the mutation flow is governed by AD-3's single transaction, and
materialization by the Admin role gate, not the scope contract.
"""

import datetime
import uuid

from sqlalchemy import Row, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.repositories.models import Employee, LeaveBalance, LeaveType
from app.repositories.scoping import Scope, employee_scope_predicate


def lock_balance(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
) -> LeaveBalance | None:
    """Return the balance row for `(employee_id, leave_type_id, leave_year)`, locked FOR UPDATE.

    The mutation methods decide `available` from THIS locked row, in the caller's single
    transaction (AD-3's TOCTOU rule) — never from a value a preview returned earlier. The
    `UNIQUE (employee_id, leave_type_id, leave_year)` index is the access path (ERD §4.4), so
    the lookup is exact. `None` means no such row: a materialization gap, which the service
    treats as a programming error (the balance should have been materialized on create).

    Named `lock_`, not `get_`/`list_`, precisely because it is a write-path locking primitive
    governed by AD-3, not a scoped read — mirroring `repositories/employee.py`'s `load_employee`.

    `populate_existing=True` overwrites any state already in the session's identity map with the
    freshly-locked row, so the mutation methods decide from the value on disk in THIS
    transaction — never a stale attribute a caller's earlier preview loaded (AD-3's TOCTOU rule).
    `load_employee`, the sibling write-path loader, sets the same option for the same reason.
    """
    return session.scalars(
        select(LeaveBalance)
        .where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.leave_year == leave_year,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def get_balance(
    session: Session,
    actor: Employee,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    scope: Scope,
) -> Row[tuple[int, int, int]] | None:
    """Return `(accrued, reserved, consumed)` for one `(employee, leave_type, year)`, SCOPED.

    The preview's advisory read (Story 2.5) — the NON-LOCKING counterpart to `lock_balance`.
    Contrast the two deliberately: `lock_balance` is the write-path primitive that takes the row
    `FOR UPDATE` so the balance-mutation module decides admission under the lock (AD-3); this
    issues a plain `SELECT` and decides nothing. A preview reads, it never admits, so it MUST NOT
    lock (AD-3, Story 2.5 AC9).

    Genuinely data-scoped, exactly like `list_balances`: a balance belongs to an Employee, so it
    joins `leave_balance → employee` and applies `employee_scope_predicate(scope, actor)` in SQL
    — it takes the `actor` and matches the scoped-getter net by name (`get_`), and is NOT exempt.
    The preview passes `Scope.SELF` (intrinsic to the token subject, like `GET /balances`).

    Returns a single column `Row` — `(accrued, reserved, consumed)`, the three STORED quantities
    the `api/` projection derives `available` from (DR-3) — or `None` when the pair has no row: an
    unknown `leave_type_id`, or an Employee with no materialized current-year balance, which the
    service turns into a byte-identical `404` (AC10). It does NOT join `leave_type` for a
    `code`/`name` (the preview surfaces neither) and does NOT `with_for_update()`.
    """
    predicate = employee_scope_predicate(scope, actor)
    return session.execute(
        select(
            LeaveBalance.accrued,
            LeaveBalance.reserved,
            LeaveBalance.consumed,
        )
        .join(Employee, LeaveBalance.employee_id == Employee.id)
        .where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.leave_year == leave_year,
            predicate,
        )
    ).first()


def upsert_accrual(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    accrued: int,
    prorated_entitlement: int,
    carried_forward: int,
    entitlement_basis: int,
) -> None:
    """Insert or update the accrual triple for one balance row, in ONE statement (AD-17).

    `INSERT … ON CONFLICT (employee_id, leave_type_id, leave_year) DO UPDATE` — one statement,
    which the non-deferrable `accrued = prorated_entitlement + carried_forward` equality CHECK
    requires (`accrued` and its two parts must move together). On a FRESH insert, `reserved`
    and `consumed` fall to their `server_default` `0`; the DO-UPDATE branch names ONLY the
    accrual columns, so a recalculation (Story 2.11/2.12) re-derives accrual WITHOUT disturbing
    committed (`reserved`) or spent (`consumed`) — the idempotent re-materialization AD-17 needs.

    A write, not a getter: governed by the command's transaction, not the scope contract. The
    service (`set_accrual`) computes `accrued` from its two parts and calls this.
    """
    statement = pg_insert(LeaveBalance).values(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        leave_year=leave_year,
        accrued=accrued,
        prorated_entitlement=prorated_entitlement,
        carried_forward=carried_forward,
        entitlement_basis=entitlement_basis,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["employee_id", "leave_type_id", "leave_year"],
        set_={
            "accrued": statement.excluded.accrued,
            "prorated_entitlement": statement.excluded.prorated_entitlement,
            "carried_forward": statement.excluded.carried_forward,
            "entitlement_basis": statement.excluded.entitlement_basis,
        },
    )
    session.execute(statement)


def list_balances(
    session: Session,
    actor: Employee,
    *,
    employee_id: uuid.UUID,
    leave_year: int,
    scope: Scope,
) -> list[Row[tuple[str, str, int, int, int]]]:
    """Return one Employee's balances for `leave_year`, SCOPED to `actor` (AD-10, NFR-04).

    Joins `leave_balance → employee` and applies `employee_scope_predicate(scope, actor)` on
    the joined `Employee`, so an out-of-scope balance is never retrieved in the first place —
    the scope is a SQL predicate, never a Python-side filter (AC9). `scope` is resolved by the
    caller from the actor's authority: `SELF` for `GET /balances`, `ALL`(Admin)/`REPORTS`
    (Manager) for `GET /employees/<id>/balances`. `employee_id` narrows to the one Employee;
    together with the scope predicate, a Manager naming a non-report selects nothing.

    Also joins `leave_type` for each row's `code` and `name` (the response's primary labels).
    Returns column `Row`s — `(leave_type_code, leave_type_name, accrued, reserved, consumed)`,
    ordered by `code` — NOT ORM instances: the three stored quantities travel out, and
    `available` is derived at the `api/` projection (AC10, DR-3), never here. Balances are a
    bounded set (one per Leave Type), so this returns a plain list, not a `Page`.
    """
    predicate = employee_scope_predicate(scope, actor)
    return list(
        session.execute(
            select(
                LeaveType.code,
                LeaveType.name,
                LeaveBalance.accrued,
                LeaveBalance.reserved,
                LeaveBalance.consumed,
            )
            .join(Employee, LeaveBalance.employee_id == Employee.id)
            .join(LeaveType, LeaveBalance.leave_type_id == LeaveType.id)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_year == leave_year,
                predicate,
            )
            .order_by(LeaveType.code, LeaveType.id)
        ).all()
    )
