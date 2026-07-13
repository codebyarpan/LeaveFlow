"""Employee reads and writes — authentication's lookups, and Story 1.6's Admin management.

Implements: FR-01 (login looks an Employee up by email), FR-04 (an Admin creates, reads,
updates and deactivates Employees — Story 1.6), AD-10 (every read that returns *another*
Employee's data is scoped to the actor's authority — see below), AD-22/AD-23 (the guard
counts and the reporting-chain step the deactivation/demotion and cycle refusals consume).

--- The scoped-getter rule, and how the reads here satisfy it (Story 1.6, Trap 1) ---

Story 1.4 introduces the rule that every row-returning getter takes the acting Employee
and scopes its read to what that actor may see (`tests/test_scoped_getters.py` enforces it
by reflection over `get_`/`list_`/`find_`/`fetch_` functions that take a `session`).

- `get_by_email` / `get_by_id_with_department` are EXEMPT: they resolve *the caller
  themselves* before any scope exists (actor-resolution ground). See their docstrings.
- `list_employees` / `get_employee` (Story 1.6) return *another* Employee's data — exactly
  what AD-10 governs — so they are NOT exempt. They take the `actor` and apply
  `scoping.employee_scope_predicate(Scope.ALL, actor)` in the `WHERE`. For an Admin the
  predicate resolves to `true()`, so the read is unrestricted (an Admin's scope genuinely
  IS everyone), but the getter still takes the actor and composes a scope predicate,
  keeping the guardrail's invariant literally true. This is `scoping.py`'s first live
  consumer; Story 1.7 later varies the *scope* (Admin→ALL, Manager→REPORTS) without
  touching these signatures.
- `count_active_direct_reports` (`count_`, returns an `int`) and `manager_id_of` (`_of`,
  returns a scalar) are correctly NOT scoped-getter candidates: the guardrail governs
  row-returning reads, not aggregate counts or a single-column lookup.
- `load_employee` is the WRITE path's loader (update/deactivate load the row to mutate it,
  and a manager-existence probe). It is named `load_`, not a read-verb prefix, precisely
  because it is not a scoped read: the writes it serves are governed by the role gate at
  the boundary (Admin-only), not the scope contract, so scoping the load would add nothing
  an always-`true()` Admin predicate does not. It eager-loads `department` so the route can
  project the mutated row after the session closes.
"""

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.repositories.models import Employee
from app.repositories.scoping import Scope, employee_scope_predicate


def get_by_email(session: Session, email: str) -> Employee | None:
    """Return the Employee with this exact email, or `None` if there is none.

    Email is `UNIQUE` (migration 0002), so at most one row matches — `.first()` over the
    unique column is exact, not a "pick one of many". Returning `None` rather than
    raising is deliberate: the *service* decides what a missing row means (an
    `AUTH_FAILED` that discloses nothing), and it must run the same fallback hash
    comparison a present row does. A raise here would let the caller short-circuit,
    which is exactly what AC5 forbids.
    """
    return session.scalars(select(Employee).where(Employee.email == email)).first()


def get_by_id_with_department(
    session: Session, employee_id: uuid.UUID
) -> Employee | None:
    """Return the Employee with this id, with `department` eager-loaded, or `None`.

    Implements: FR-17 (`GET /me` reads the caller's own profile), AD-14 (the actor is
    resolved from the database by the token's subject). Keyed by the primary key, so at
    most one row matches. `None` means no such row — the *service* decides what that
    means (a `TOKEN_INVALID` that discloses nothing), exactly as `get_by_email` leaves
    the missing-row meaning to the login service.

    `joinedload(Employee.department)` loads the department in the same query, so a
    consumer can read `employee.department` after the session closes. Without it, `/me`'s
    projection of `department` would trigger a lazy load on a detached instance and raise
    `DetachedInstanceError` — `expire_on_commit=False` preserves *loaded* attributes but
    does not load a lazy relationship after close. `/me` is this getter's only consumer
    and always needs the department, so the eager load is baked in rather than left to
    each caller to remember.

    --- Why this getter is exempt from Story 1.4's scoped-getter rule ---

    Like `get_by_email`, this resolves *the actor themself* from the token's subject, not
    another Employee's data. It runs to establish who the caller is, before any scope
    exists to apply — so Story 1.4's rule that a getter takes the acting Employee and
    scopes its read does not, cannot, wrap this one. Story 1.4/1.7 must not.
    """
    return session.scalars(
        select(Employee)
        .options(joinedload(Employee.department))
        .where(Employee.id == employee_id)
    ).first()


# --- Story 1.6: the Admin's scoped reads (Trap 1) --------------------------------------


def list_employees(
    session: Session, actor: Employee, limit: int, offset: int
) -> tuple[list[Employee], int]:
    """Return one page of Employees AND the full count, scoped to `actor` (AC3, AC4).

    Takes the acting Employee and applies `employee_scope_predicate(Scope.ALL, actor)` in
    the `WHERE` (Trap 1) — for an Admin the predicate is `true()`, so every row is
    returned, but the getter is honestly scoped rather than EXEMPT. `department` is
    eager-loaded so the route can project `{id, name}` after the session closes
    (`expire_on_commit=False` preserves a *loaded* attribute but does not lazy-load a
    relationship on a detached row). Ordered by `full_name, id` so pages are deterministic
    across `LIMIT`/`OFFSET`. The page and the total travel together so the `api/` layer
    assembles the whole `Page` envelope from one repository round-trip.
    """
    predicate = employee_scope_predicate(Scope.ALL, actor)
    rows = list(
        session.scalars(
            select(Employee)
            .options(joinedload(Employee.department))
            .where(predicate)
            .order_by(Employee.full_name, Employee.id)
            .limit(limit)
            .offset(offset)
        )
        .unique()
        .all()
    )
    total = (
        session.scalar(select(func.count()).select_from(Employee).where(predicate)) or 0
    )
    return rows, total


def get_employee(
    session: Session,
    actor: Employee,
    employee_id: uuid.UUID,
    scope: Scope = Scope.ALL,
) -> Employee | None:
    """Return one Employee by id, scoped to `actor`, or `None` (AC3, Trap 1).

    Composes `Employee.id == employee_id` with `employee_scope_predicate(scope, actor)`.
    `scope` defaults to `Scope.ALL` — the Admin-only `/employees/{id}` read (Story 1.6), whose
    predicate is `true()`, so that call is a plain by-id lookup. Story 2.4's Manager balance
    endpoint passes `Scope.REPORTS`, so a Manager naming a non-report gets `None` — the "returns
    None for nonexistent-OR-out-of-scope" the balance service relies on to raise a byte-identical
    404 (AD-10). The getter still takes the actor and applies a scope predicate either way, so
    the guardrail's invariant holds. `department` is eager-loaded for the response projection;
    the service turns a `None` into `not_found()` (404), so nonexistent and out-of-scope are
    indistinguishable to a client (AD-10).
    """
    return (
        session.scalars(
            select(Employee)
            .options(joinedload(Employee.department))
            .where(Employee.id == employee_id, employee_scope_predicate(scope, actor))
        )
        .unique()
        .first()
    )


# --- Story 2.4: the materialization full-table read (AD-17 create hook) -----------------


def all_employees(session: Session) -> list[Employee]:
    """Return EVERY Employee, unpaginated, for Story 2.4's balance materialization.

    A write-path full-table read: `create_leave_type` materializes a `leave_balance` row for the
    new Leave Type × every Employee (AC3/SM-5), which needs all of them, not a page. Named
    `all_`, NOT `list_`/`get_`, precisely so it is correctly not a scoped-getter candidate — it
    feeds a materialization loop inside an Admin command (the Admin's scope is everyone anyway),
    not a read projection that could leak another Employee's data through an endpoint. Ordered by
    `id` so the materialization is deterministic (AD-3's ascending lock order for balance rows).
    """
    return list(session.scalars(select(Employee).order_by(Employee.id)).all())


# --- Story 1.6: the guard inputs (AD-22, AD-23) ----------------------------------------


def count_active_direct_reports(session: Session, manager_id: uuid.UUID) -> int:
    """Count the ACTIVE Employees who name `manager_id` as their Manager (AC8, AC9).

    The input to both the deactivation guard (AC8) and the demotion-below-`MANAGER` guard
    (AC9). Only *active* reports count: `AD-22`'s orphaning concern is a Pending request
    with no approver, and a deactivated report cannot submit one. Named with `count_`,
    returning an `int`, so it is correctly not a scoped-getter candidate.
    """
    return (
        session.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.manager_id == manager_id, Employee.is_active.is_(True))
        )
        or 0
    )


def manager_id_of(session: Session, employee_id: uuid.UUID) -> uuid.UUID | None:
    """Return just the `manager_id` of one Employee — the cycle walk's single step (Trap 2).

    Returns the scalar `manager_id` column (or `None` when the Employee has no manager, or
    when no such Employee exists — the service's cycle walk treats a `None` as "chain ends
    here" either way). Named with `_of`, not a read-verb prefix, and returning a scalar
    rather than rows, so it is correctly not a scoped-getter candidate.
    """
    return session.scalar(
        select(Employee.manager_id).where(Employee.id == employee_id)
    )


# --- Story 1.6: the write path (role-gated, not scope-gated) ---------------------------


def load_employee(session: Session, employee_id: uuid.UUID) -> Employee | None:
    """Load one Employee by id for a WRITE (update/deactivate) or an existence probe.

    Not a scoped read (hence `load_`, not `get_`/`list_`): the commands it serves are
    Admin-only at the boundary, so scoping the load would only ever apply an Admin's
    `true()` predicate. `department` is eager-loaded so the route can project the mutated
    row after the session closes. `None` means no such row; the service turns that into a
    `404` (a `PATCH`/`deactivate` of a nonexistent id) or, for a proposed `manager_id`,
    into `not_found()` before the FK insert can 500 (Trap 2).

    `populate_existing=True` overwrites any state already in the session's identity map
    with the DB row and the freshly-joined `department`. Without it, a post-commit reload
    of a row whose `department` relationship was loaded *before* a `department_id` change
    would return the stale department object — the column updates, the relationship does
    not. The service reloads through this after every write, so the projection must be the
    DB truth, not the pre-change relationship.
    """
    return session.scalars(
        select(Employee)
        .options(joinedload(Employee.department))
        .where(Employee.id == employee_id)
        .execution_options(populate_existing=True)
    ).first()


def create_employee(
    session: Session,
    *,
    department_id: uuid.UUID,
    manager_id: uuid.UUID | None,
    email: str,
    full_name: str,
    role: str,
    joining_date: datetime.date,
    password_hash: str,
) -> Employee:
    """Insert a new active Employee and return it (AC1).

    A write, governed by the role gate rather than the scope contract, so it is not a
    guardrail candidate. `is_active=True` — an Admin-created Employee is active immediately
    (AC1). `flush` assigns the server-default `id` so the caller can project it into the
    response before the surrounding transaction commits (mirrors `create_department`).
    """
    employee = Employee(
        department_id=department_id,
        manager_id=manager_id,
        email=email,
        full_name=full_name,
        role=role,
        joining_date=joining_date,
        is_active=True,
        password_hash=password_hash,
    )
    session.add(employee)
    session.flush()
    return employee


def apply_employee_changes(employee: Employee, changes: dict[str, object]) -> Employee:
    """Apply the validated field changes to an already-loaded Employee, in place (PATCH).

    Takes the loaded row, not an id: the service loads-or-`not_found()`s and runs every
    guard (email, cycle, demotion) before this sets a single attribute, so by the time this
    runs the change set is known-good. `changes` carries only the mutable fields the service
    admitted (never `password`); the assignments are flushed with the command's commit.
    """
    for field, value in changes.items():
        setattr(employee, field, value)
    return employee


def deactivate_employee(employee: Employee) -> Employee:
    """Mark an already-loaded, already-guarded Employee inactive and return it (AC11).

    The service has loaded the row and confirmed it has no active direct reports (AC8)
    before this runs — this only flips the flag. `is_active=False` is what stops the
    Employee authenticating while its row (and history) persists; the row is never deleted
    (AC12). The commit is the surrounding command's.
    """
    employee.is_active = False
    return employee
