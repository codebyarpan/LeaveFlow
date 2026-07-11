"""Department reads, writes, and the emptiness count the DELETE guard depends on.

Implements: FR-05 (Departments are created, listed, renamed and removed), NFR-11 (the list
is page-bounded — this issues the `LIMIT`/`OFFSET` the `api/` layer computes), AD-5 (the
`count_employees_in_department` gate that keeps a non-empty delete a 409, not the FK's 500).

--- Why the getters here take no `actor` (and are EXEMPT from the scoped-getter rule) ---

`tests/test_scoped_getters.py` reflects over every `get_`/`list_`/`find_`/`fetch_` function
that takes a `session` and requires an `actor` parameter — the AD-10 rule that no getter
returns *another Employee's data* without scoping to who is asking. `list_departments` and
`get_department` match that net by name, but they fall genuinely OUTSIDE the rule: a
Department row is `{id, name}`, not Employee-derived data, and its api-contracts scope is
`all` — any authenticated role reads the whole list, there is no per-row predicate to apply.
So they are added to that test's EXEMPT registry with a broadened rationale, deliberately
and visibly, rather than given a misleading unused `actor` param. See Story 1.5 Trap 1.

`count_employees_in_department` is named with `count_`, not a read-verb prefix, precisely so
it is correctly NOT a scoped-getter candidate: it returns an `int`, not rows.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.models import Department, Employee


def list_departments(
    session: Session, limit: int, offset: int
) -> tuple[list[Department], int]:
    """Return one page of Departments AND the full count, in the same call (AC2, AC3).

    The page and the total travel together — one `SELECT ... LIMIT/OFFSET` for the rows and
    one `SELECT count(*)` for the total — so the `api/` layer can assemble the whole `Page`
    envelope (`items` + `total`) from a single repository round-trip. Ordered by `name, id`
    so pages are deterministic: without a stable `ORDER BY`, `LIMIT/OFFSET` may repeat or
    skip a row across pages as the planner's row order shifts.

    Scope is `all` (api-contracts §4.2): every row is returned to any authenticated role, so
    there is no actor and no predicate here — this getter is EXEMPT from the scoped-getter
    rule for the reason the module docstring states.
    """
    rows = list(
        session.scalars(
            select(Department).order_by(Department.name, Department.id).limit(limit).offset(offset)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(Department)) or 0
    return rows, total


def get_department(session: Session, department_id: uuid.UUID) -> Department | None:
    """Return the Department with this id, or `None` if there is none (AC5, AC6, Trap 4).

    Keyed by the primary key, so at most one row matches. `None` means no such row; the
    *service* decides what that means — a `PATCH`/`DELETE` of a nonexistent id becomes a
    `404` via `authorization.not_found()`, exactly as `employee.py`'s getters leave the
    missing-row meaning to their service. EXEMPT from the scoped-getter rule (scope `all`).
    """
    return session.get(Department, department_id)


def count_employees_in_department(session: Session, department_id: uuid.UUID) -> int:
    """Count EVERY Employee assigned to this Department — active or deactivated (Trap 3).

    The DELETE guard's input (AD-5). It counts regardless of `is_active`: a deactivated
    Employee's row persists and still references the Department via the NOT-NULL FK, so the
    database's RESTRICT would still block the delete. The count must match what the FK
    actually blocks — counting only active Employees would let a delete of a "looks empty"
    Department (everyone deactivated) slip past the gate and surface as the FK's raw 500.

    Named with `count_`, returning an `int`, so it is correctly not a scoped-getter
    candidate — the guardrail governs row-returning getters, not aggregate counts.
    """
    return (
        session.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.department_id == department_id)
        )
        or 0
    )


def create_department(session: Session, name: str) -> Department:
    """Insert a new Department and return it (AC1).

    A write, governed by the role gate rather than the scope contract, so it is not a
    guardrail candidate. `flush` assigns the server-default `id` so the caller can project
    it into the response before the surrounding transaction commits.
    """
    department = Department(name=name)
    session.add(department)
    session.flush()
    return department


def rename_department(department: Department, name: str) -> Department:
    """Rename an already-loaded Department in place and return it (PATCH).

    Takes the loaded row, not an id: the service loads-or-`not_found()`s first (Trap 4), so
    by the time this runs the row is known to exist. The assignment is flushed with the
    surrounding command's commit.
    """
    department.name = name
    return department


def delete_department(session: Session, department: Department) -> None:
    """Delete an already-loaded, already-verified-empty Department (AC6).

    The service has already loaded the row (Trap 4) and confirmed it holds no Employees
    (Trap 3) before this runs — this issues only the `DELETE`. The commit is the
    surrounding command's.
    """
    session.delete(department)
