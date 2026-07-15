"""The Manager's team read — the Direct Reports behind `GET /api/v1/team` (Story 3.2).

Implements: FR-19 (a Manager sees the Employees who report to them, so they know whose
leave is theirs to decide), AD-10 (the REPORTS scope is a SQL predicate bound to the
actor's id at call time — an out-of-scope row is never retrieved), G3 (the role refusal
happens in `api/`'s `require_role(MANAGER)` dependency, BEFORE this function runs).

--- Why the `Scope.REPORTS` decision lives HERE, and not in the route ---

`Scope` lives in `app/repositories/scoping.py`, and import-linter contract 2 forbids
`api/` importing `app.repositories` — so the route cannot name a scope at all. This module
hardcodes `Scope.REPORTS` because that is the ONLY scope `/team` is ever granted
(api-contracts §4.9: Role Manager, Scope reports — the Admin is refused 403 by the gate,
alongside the Employee; an Admin sees everyone through `GET /employees` instead). The role
gate guarantees the caller is a Manager by the time this runs; no second role check here —
it would be dead code that quietly implies the first one is optional (the `services/audit.py`
posture).

--- Read-only, deliberately ---

The small-read-module shape (`services/balance_reads.py`, `services/audit.py`): one read
session, opened, queried, closed, never committed. Note the REPORTS predicate carries no
`is_active` filter — a deactivated Direct Report is IN the list, distinguishable on the
wire by their `is_active` flag (FR-19's "distinguishable" means PRESENT, never filtered).
"""

from sqlalchemy.orm import Session

from app.repositories import employee as employee_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope


def list_team(limit: int, offset: int, actor: Employee) -> tuple[list[Employee], int]:
    """Return one page of `actor`'s Direct Reports AND the full count (FR-19, AD-10).

    A thin pass-through opening a read session and delegating to the one existing employee
    list read with `Scope.REPORTS` — `Employee.manager_id == actor.id`, bound at call time
    (AD-14: a reassignment takes effect on the next request). Ordering (`full_name, id`),
    the eager-loaded `department` and the `(rows, total)` single round-trip are the
    repository's; the `api/` route assembles the `Page` envelope from what this returns.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return employee_repo.list_employees(
            session, actor, limit, offset, scope=Scope.REPORTS
        )
