"""Balance READS — the self read and the scoped read of another Employee's balances.

Implements: FR-07 (`GET /balances` — the caller's own balances), FR-03 / AD-10 (`GET
/employees/<id>/balances` — a Manager sees only their Direct Reports, an Admin sees anyone; a
scope miss is a byte-identical 404), DR-3 (the three STORED quantities travel out; `available`
is derived at the `api/` projection, never here). SM-6.

This is a SEPARATE module from `services/balances.py` on purpose: AC4 fixes the mutation module
at exactly eight public callables, so the reads live here. Reads issue no balance write and open
no write transaction — they open a read session, apply the scope, and project.

--- Why `leave_balance` is the first genuinely data-scoped resource (AD-10) ---

A balance belongs to an Employee, so a read that could return ANOTHER Employee's balance scopes
in SQL (`repositories/leave_balance.list_balances` takes the `actor` and applies
`employee_scope_predicate`). `GET /balances` is scope `self` (intrinsic to the token subject);
`GET /employees/<id>/balances` resolves scope from the actor's role — `ALL` for an Admin,
`REPORTS` for a Manager — and first resolves the target Employee UNDER that scope (`get_employee`
returns `None` for nonexistent-OR-out-of-scope), so a Manager naming a non-report gets a 404
indistinguishable from a nonexistent id.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import employee as employee_repo
from app.repositories import leave_balance as leave_balance_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import authorization as authz


@dataclass(frozen=True)
class BalanceView:
    """One Leave Type's balance as the read layer hands it up — the three STORED quantities.

    `available` is NOT here: it is derived (`accrued − consumed − reserved`) at the `api/`
    projection, from `accrued`/`reserved`/`consumed`, so no layer below `api/` computes or
    stores it (DR-3, AD-5, AC10). `accrued` travels so the projection can derive `available`.
    """

    leave_type_code: str
    leave_type_name: str
    accrued: int
    reserved: int
    consumed: int


def _current_leave_year() -> int:
    """The current Leave Year — `date.today().year` (DR-8). The clock lives in the shell (AD-1)."""
    return datetime.date.today().year


def _to_views(rows: list) -> list[BalanceView]:  # type: ignore[type-arg]
    """Map the repository's `(code, name, accrued, reserved, consumed)` rows to `BalanceView`s."""
    return [
        BalanceView(
            leave_type_code=code,
            leave_type_name=name,
            accrued=accrued,
            reserved=reserved,
            consumed=consumed,
        )
        for code, name, accrued, reserved, consumed in rows
    ]


def list_own_balances(actor: Employee) -> list[BalanceView]:
    """Return the CALLER's own current-year balances (FR-07, scope `self`).

    Scope `SELF` is intrinsic to the token subject (like `GET /me`): `employee_id = actor.id`,
    and the `SELF` predicate (`Employee.id == actor.id`) is the whole enforcement. The rows are
    a bounded set (one per Leave Type), returned as a plain list, not a `Page`.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        rows = leave_balance_repo.list_balances(
            session,
            actor,
            employee_id=actor.id,
            leave_year=_current_leave_year(),
            scope=Scope.SELF,
        )
        return _to_views(rows)


def list_employee_balances(employee_id: uuid.UUID, actor: Employee) -> list[BalanceView]:
    """Return another Employee's current-year balances, SCOPED to `actor` (FR-03, AD-10).

    Role is gated at the boundary (Manager+Admin only; an Employee is `403` before this runs).
    Here scope is resolved from the actor's role — Admin → `ALL`, Manager → `REPORTS` — and the
    target Employee is resolved UNDER that scope first: `get_employee` returns `None` for a
    nonexistent id OR an out-of-scope one (a Manager's non-report), which becomes a byte-identical
    `404 RESOURCE_NOT_FOUND` (AD-10). Only then are that Employee's balances read, scoped again.
    """
    scope = Scope.ALL if actor.role == authz.ROLE_ADMIN else Scope.REPORTS
    with Session(get_engine(), expire_on_commit=False) as session:
        target = employee_repo.get_employee(session, actor, employee_id, scope)
        if target is None:
            authz.not_found()

        rows = leave_balance_repo.list_balances(
            session,
            actor,
            employee_id=employee_id,
            leave_year=_current_leave_year(),
            scope=scope,
        )
        return _to_views(rows)
