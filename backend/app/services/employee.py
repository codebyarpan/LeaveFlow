"""Employee command orchestration: create, update, deactivate, and the four refusals.

Implements: FR-04 (an Admin creates, reads, updates and deactivates Employees, sets an
initial password, and never re-issues it), FR-17/PRD §6 (`PATCH` carries no password —
there is no re-issue path), AD-3 (one transaction per command), AD-5 (the `UNIQUE (email)`
and `CHECK (id <> manager_id)` constraints are BACKSTOPS; this service is the gate),
AD-10/AD-14 (`not_found()` on a missing row; every endpoint is role-gated at the boundary),
AD-22 (deactivation and demotion-below-`MANAGER` are refused while an active Employee
reports to them), AD-23 (a manager assignment that would close a reporting cycle is
refused). SM-6.

The four refusals this story raises:
  - `EMAIL_ALREADY_IN_USE` (409) — a duplicate email on create or update (`G2`, Trap 3).
  - `REPORTING_CYCLE` (400) — a manager assignment that would close a cycle (`G7`, Trap 2).
  - `EMPLOYEE_HAS_DIRECT_REPORTS` (409) — deactivate/demote with active reports (`G8`, Trap 4).
  - `EMPLOYEE_HAS_PENDING_REQUESTS` (409) — VACUOUS in Epic 1 (Trap 6): no `leave_request`
    table exists, so no Employee can hold a Pending request. The guard, and the code, land
    in Epic 2's Leave Request submission story, when the table it queries exists.

Each write command opens exactly one `with Session(get_engine(), expire_on_commit=False)`
and commits inside it (AD-3) — the idiom `services/auth.py` documents and
`services/departments.py` copies. All guard reads (the email lookup, the cycle walk, the
report count) run INSIDE the same transaction as the write, so the check and the write are
atomic up to the `IntegrityError` backstop. `expire_on_commit=False` keeps the returned
row's attributes readable after the block closes, so the `api/` route can project it.
"""

import datetime
import uuid
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import department as department_repo
from app.repositories import employee as employee_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.services import authorization as authz

# The mutable fields a `PATCH` may set — email, full name, role, department, manager and
# joining date. NEVER `password` (Trap 5): there is no re-issue path. The route builds the
# change set from these; the service applies only what it admits.
_MUTABLE_FIELDS = frozenset(
    {"email", "full_name", "role", "department_id", "manager_id", "joining_date"}
)

# One message per refusal, stated once at module level — mirrors `services/departments.py`'s
# `_DEPARTMENT_NOT_EMPTY_MESSAGE`. The email message names neither the holder nor whether
# they are active (`G2`): a duplicate-email refusal must not disclose that an account exists
# for that address, let alone its state.
_EMAIL_ALREADY_IN_USE_MESSAGE = "That email address is already in use."
_REPORTING_CYCLE_MESSAGE = (
    "That manager assignment would create a reporting cycle and was refused."
)
_EMPLOYEE_HAS_DIRECT_REPORTS_MESSAGE = (
    "This employee still has active direct reports and cannot be deactivated or demoted."
)


def _email_already_in_use() -> DomainError:
    """Build the `409 EMAIL_ALREADY_IN_USE` refusal (`G2`, `AD-5`).

    Shared by the pre-write gate and the `UNIQUE (email)` `IntegrityError` backstop so both
    paths raise a byte-identical envelope. `details` is empty — the refusal must not
    disclose whether the email's holder is active (`G2`), so it names no id and no state.
    """
    return DomainError(
        code=vocabulary.EMAIL_ALREADY_IN_USE,
        message=_EMAIL_ALREADY_IN_USE_MESSAGE,
        details={},
    )


def _reporting_cycle() -> DomainError:
    """Build the `400 REPORTING_CYCLE` refusal (`AD-23`, `G7`)."""
    return DomainError(
        code=vocabulary.REPORTING_CYCLE,
        message=_REPORTING_CYCLE_MESSAGE,
        details={},
    )


def _employee_has_direct_reports(active_direct_reports: int) -> DomainError:
    """Build the `409 EMPLOYEE_HAS_DIRECT_REPORTS` refusal, naming the count (`NFR-17`).

    Shared by the deactivation gate (AC8) and the demotion gate (AC9) — the same code,
    message and `details.active_direct_reports` shape. The number is what makes the refusal
    actionable: the Admin knows how many reports to reassign before retrying.
    """
    return DomainError(
        code=vocabulary.EMPLOYEE_HAS_DIRECT_REPORTS,
        message=_EMPLOYEE_HAS_DIRECT_REPORTS_MESSAGE,
        details={"active_direct_reports": active_direct_reports},
    )


def _email_conflicts(
    session: Session, email: str, exclude_id: uuid.UUID | None = None
) -> bool:
    """Does `email` already belong to a DIFFERENT Employee?

    The precise test behind the `UNIQUE (email)` `IntegrityError` backstop: it re-raises
    `EMAIL_ALREADY_IN_USE` for a genuine email collision ONLY, never for an unrelated
    constraint (an invalid `role`, an explicit `null` on a required field) that would
    otherwise be mislabeled as a duplicate email. A row whose id equals `exclude_id` (the
    Employee being edited itself) is not a conflict.
    """
    holder = employee_repo.get_by_email(session, email)
    return holder is not None and holder.id != exclude_id


def _would_close_cycle(
    target_id: uuid.UUID,
    start_manager_id: uuid.UUID,
    parent_of: Callable[[uuid.UUID], uuid.UUID | None],
) -> bool:
    """Would naming `start_manager_id` the manager of `target_id` close a reporting cycle?

    Walks the proposed manager's chain upward (`parent_of` yields each Employee's own
    `manager_id`). A cycle exists iff `target_id` is reached — i.e. the Employee being
    assigned a manager is already an ancestor of that manager, or IS that manager (the
    self-loop, which the walk catches on its first step). `AD-23`'s gate; the DB's
    `CHECK (id <> manager_id)` is only the backstop, and would reach a client as a 500.

    Pure over `parent_of`, so it is unit-testable with a plain dict and no database (Task 7).
    A `visited` set stops a walk over *pre-existing* corrupt data (a cycle that somehow
    already exists) from looping forever — defensive, not a normal path.
    """
    cur: uuid.UUID | None = start_manager_id
    visited: set[uuid.UUID] = set()
    while cur is not None:
        if cur == target_id:
            return True
        if cur in visited:
            return False
        visited.add(cur)
        cur = parent_of(cur)
    return False


def create_employee(
    email: str,
    full_name: str,
    role: str,
    department_id: uuid.UUID,
    joining_date: datetime.date,
    initial_password: str,
    manager_id: uuid.UUID | None = None,
) -> Employee:
    """Create an active Employee with an initial password and return it (AC1, AC2, AC6, AC7).

    One transaction (AD-3). In order:
      1. Email uniqueness pre-check via `get_by_email` — a row (active OR deactivated) →
         `409 EMAIL_ALREADY_IN_USE` before the write (Trap 3, `G2`).
      2. If `manager_id` is given, verify it names a real Employee — else the FK insert
         would 500; a named-but-absent manager is `not_found()` (404, Trap 2). The cycle
         walk is vacuous on create (the new row has no id, so nothing can reach it).
      3. Hash the password once (Trap 5); it is stored, never echoed.
      4. Insert `is_active=True` and `flush` for the id.
      5. Commit under `try/except IntegrityError` → re-raise `EMAIL_ALREADY_IN_USE`, the
         `UNIQUE (email)` TOCTOU backstop (`AD-5`, mirrors `delete_department`).

    Returns the row (reloaded with `department` eager-loaded) so the route can project it.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        if employee_repo.get_by_email(session, email) is not None:
            raise _email_already_in_use()

        if manager_id is not None and employee_repo.load_employee(session, manager_id) is None:
            # A named-but-nonexistent manager is, to the Admin, a resource that is not
            # there — 404, before the FK insert can surface a raw 500 (Trap 2 sub-trap).
            authz.not_found()

        if department_repo.get_department(session, department_id) is None:
            # A named-but-nonexistent department is, like a nonexistent manager, a resource
            # that is not there — 404, before the department FK can 500. Without this the FK
            # violation would be caught by the commit backstop below and mislabeled
            # EMAIL_ALREADY_IN_USE (a department can be deleted between the create form's
            # load and its submit, Story 1.5 permits deleting an empty one).
            authz.not_found()

        password_hash = security.hash_password(initial_password)
        created = employee_repo.create_employee(
            session,
            department_id=department_id,
            manager_id=manager_id,
            email=email,
            full_name=full_name,
            role=role,
            joining_date=joining_date,
            password_hash=password_hash,
        )
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            # The UNIQUE (email) TOCTOU backstop re-raises the typed 409 ONLY for a genuine
            # email collision (a concurrent insert of the same address between the pre-check
            # and the commit). Any other IntegrityError is re-raised untouched rather than
            # mislabeled as a duplicate email.
            if _email_conflicts(session, email):
                raise _email_already_in_use() from exc
            raise

        # Reload with `department` eager-loaded: the insert set `department_id`, not the
        # `department` relationship, so projecting `department.name` off `created` would
        # lazy-load on a detached row after the block closes. `load_employee` joins it in.
        return employee_repo.load_employee(session, created.id)


def update_employee(employee_id: uuid.UUID, changes: dict[str, object]) -> Employee:
    """Apply a partial update to an Employee, refusing the four ways it can be invalid.

    `changes` carries only the fields the request set (the route builds it with
    `exclude_unset=True`, so an omitted field is untouched and an explicit `null` for
    `manager_id` is distinguishable from absent). Load-or-`not_found()` first (Trap 4), then
    the guards IN ORDER (Task 4):
      (a) `email` now belonging to a *different* Employee → `EMAIL_ALREADY_IN_USE` (Trap 3).
      (b) `manager_id` set → verify the manager exists (`not_found()` if not) and run the
          transitive cycle walk → `REPORTING_CYCLE` on a self- or A→B→A cycle (Trap 2).
      (c) `role` lowered to `EMPLOYEE` while active reports exist → `EMPLOYEE_HAS_DIRECT_
          REPORTS`, role unchanged (Trap 4 / AC9).
    Then apply and commit under the `IntegrityError` → `EMAIL_ALREADY_IN_USE` backstop.

    Ignores any field outside `_MUTABLE_FIELDS` (Trap 5: a stray `password` is ignored, not
    rejected — that `FORBIDDEN_FIELD` behaviour is Story 1.8's `PATCH /me`, a different
    resource). Nothing persists when a guard raises (AC7): the guards run before the write.
    """
    changes = {k: v for k, v in changes.items() if k in _MUTABLE_FIELDS}

    with Session(get_engine(), expire_on_commit=False) as session:
        employee = employee_repo.load_employee(session, employee_id)
        if employee is None:
            authz.not_found()

        # (a) Email uniqueness — only when it changes to one a DIFFERENT Employee holds. A
        # no-op re-set of this Employee's own email is fine (Trap 3).
        if "email" in changes:
            holder = employee_repo.get_by_email(session, changes["email"])  # type: ignore[arg-type]
            if holder is not None and holder.id != employee.id:
                raise _email_already_in_use()

        # Department existence — a changed `department_id` naming no department is a 404
        # (mirrors the manager pre-check below), not a mislabeled 409 from the FK backstop.
        if "department_id" in changes and (
            department_repo.get_department(session, changes["department_id"])  # type: ignore[arg-type]
            is None
        ):
            authz.not_found()

        # (b) Manager assignment — existence, then the transitive cycle walk (Trap 2). A
        # self-assignment (`manager_id == employee.id`) is caught on the walk's first step.
        if "manager_id" in changes:
            new_manager_id = changes["manager_id"]
            if new_manager_id is not None:
                if employee_repo.load_employee(session, new_manager_id) is None:  # type: ignore[arg-type]
                    authz.not_found()
                if _would_close_cycle(
                    employee.id,
                    new_manager_id,  # type: ignore[arg-type]
                    lambda eid: employee_repo.manager_id_of(session, eid),
                ):
                    raise _reporting_cycle()

        # (c) Demotion below MANAGER — the same orphaning door as deactivation (AC9, G8).
        # "Below MANAGER" is exactly the new role EMPLOYEE; MANAGER→ADMIN is not guarded.
        if changes.get("role") == authz.ROLE_EMPLOYEE:
            active_reports = employee_repo.count_active_direct_reports(
                session, employee.id
            )
            if active_reports > 0:
                raise _employee_has_direct_reports(active_reports)

        employee_repo.apply_employee_changes(employee, changes)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            # As on create: re-raise the typed 409 ONLY for a genuine email collision (a
            # concurrent write taking the new address). Any other IntegrityError is
            # re-raised untouched rather than mislabeled as a duplicate email.
            new_email = changes.get("email")
            if isinstance(new_email, str) and _email_conflicts(
                session, new_email, exclude_id=employee_id
            ):
                raise _email_already_in_use() from exc
            raise

        # Reload so a changed `department_id` is reflected by a fresh `department` join
        # rather than the stale relationship loaded before the change.
        return employee_repo.load_employee(session, employee_id)


def deactivate_employee(employee_id: uuid.UUID) -> Employee:
    """Deactivate an Employee, refusing a nonexistent id (404) or one with active reports.

    Load-or-`not_found()` (Trap 4). Guard (AC8): if the Employee still has active direct
    reports → `409 EMPLOYEE_HAS_DIRECT_REPORTS`, row unchanged — deactivating them would
    orphan those reports (`AD-22`).

    The Pending-request guard `AD-22` also requires (AC10) lands in Epic 2, when
    `leave_request` exists: no such table exists in Epic 1, so no Employee can hold a
    Pending request and the guard cannot execute (Trap 6). Deliberately NOT queried here.

    On success sets `is_active=False`, commits, and returns the row so the client sees the
    new state. The row persists (AC11/AC12) — an Employee is never deleted, and the
    deactivated email stays reserved under `UNIQUE (email)`.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        employee = employee_repo.load_employee(session, employee_id)
        if employee is None:
            authz.not_found()

        active_reports = employee_repo.count_active_direct_reports(session, employee.id)
        if active_reports > 0:
            raise _employee_has_direct_reports(active_reports)

        employee_repo.deactivate_employee(employee)
        session.commit()
        return employee_repo.load_employee(session, employee_id)


def list_employees(
    limit: int, offset: int, actor: Employee
) -> tuple[list[Employee], int]:
    """Return one page of Employees and the full count, scoped to `actor` (AC3, AC4).

    A thin pass-through opening a read session and delegating with the actor threaded
    through (Trap 1). The `api/` route assembles the `Page` envelope from the `(rows,
    total)` this returns. Every `/employees` endpoint is Admin-only, so `actor`'s scope is
    `ALL` and the predicate is `true()` — but the getter takes it, keeping the guardrail
    honest and leaving Story 1.7's Manager-scoped variant a change of scope, not signature.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return employee_repo.list_employees(session, actor, limit, offset)


def get_employee(employee_id: uuid.UUID, actor: Employee) -> Employee:
    """Return one Employee by id, scoped to `actor`, or raise `404` (AC3, Trap 1).

    Delegates to the actor-scoped repository read; a `None` (no such row, or out of scope)
    becomes a byte-identical `not_found()` so the two are indistinguishable to a client
    (AD-10). The route projects the returned row.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        employee = employee_repo.get_employee(session, actor, employee_id)
        if employee is None:
            authz.not_found()
        return employee
