"""Department command orchestration: the four operations, and the two refusals.

Implements: FR-05 (create, list, rename, remove a Department), AD-3 (one transaction per
command), AD-5 (the FK RESTRICT is a backstop; the emptiness count is the gate that raises
`409 DEPARTMENT_NOT_EMPTY`), AD-10 (the `not_found()` convention on a real resource — this
is its first live use, Story 1.5 Trap 4). SM-6.

Each write command opens exactly one `with Session(get_engine(), expire_on_commit=False)`
and commits inside it — the idiom `services/auth.py` documents. `expire_on_commit=False`
keeps the returned row's attributes readable after the block closes, so the `api/` route
can project it into the response without a `DetachedInstanceError`.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import department as department_repo
from app.repositories.engine import get_engine
from app.repositories.models import Department
from app.services import authorization as authz

# One message per refusal, stated once at module level — mirrors `services/auth.py`'s
# `_AUTH_FAILED_MESSAGE`. The not-found message is `authorization.not_found()`'s own; this
# module states only the emptiness refusal, whose `details` carry the obstruction as a
# NUMBER (`employee_count`) so NFR-17's "names the obstruction" is satisfied with data.
_DEPARTMENT_NOT_EMPTY_MESSAGE = (
    "This department still has assigned employees and cannot be deleted."
)


def _department_not_empty(employee_count: int) -> DomainError:
    """Build the `409 DEPARTMENT_NOT_EMPTY` refusal, naming the obstruction with its count.

    Shared by the count-first gate and the FK-RESTRICT backstop (AD-5) so both paths raise a
    byte-identical envelope — the same code, message and `details.employee_count` shape.
    """
    return DomainError(
        code=vocabulary.DEPARTMENT_NOT_EMPTY,
        message=_DEPARTMENT_NOT_EMPTY_MESSAGE,
        details={"employee_count": employee_count},
    )


def create_department(name: str) -> Department:
    """Create a Department and return it (AC1).

    One transaction (AD-3). The repository `flush` assigns the server-default `id` before
    the commit, so the returned row carries an `id` the route can project.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        department = department_repo.create_department(session, name)
        session.commit()
        return department


def rename_department(department_id: uuid.UUID, name: str) -> Department:
    """Rename a Department and return it, or raise `404` if the id names no row (Trap 4).

    Load-or-`not_found()` first: a `PATCH` of a nonexistent id is a `404 RESOURCE_NOT_FOUND`,
    never a silent success or a 500. `not_found()` is reached through the `services/`
    authorization module (the route cannot import `domain/`), byte-identical every time.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        department = department_repo.get_department(session, department_id)
        if department is None:
            authz.not_found()
        department_repo.rename_department(department, name)
        session.commit()
        return department


def delete_department(department_id: uuid.UUID) -> None:
    """Delete a Department, refusing a nonexistent id (404) or a non-empty one (409).

    In order (Trap 3, Trap 4):
      1. Load the row; if `None` → `not_found()` (`404 RESOURCE_NOT_FOUND`).
      2. Count the Employees assigned to it; if any → raise `409 DEPARTMENT_NOT_EMPTY`,
         naming the obstruction with the count. The count includes deactivated Employees,
         because the FK RESTRICT would block their delete too (Trap 3).
      3. Only then delete the row and commit.

    The `count`-first gate is what keeps a non-empty delete a clean `409` rather than the
    FK RESTRICT's `IntegrityError` → 500 (AD-5): the constraint is the backstop, this is
    the gate.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        department = department_repo.get_department(session, department_id)
        if department is None:
            authz.not_found()

        employee_count = department_repo.count_employees_in_department(
            session, department_id
        )
        if employee_count > 0:
            raise _department_not_empty(employee_count)

        department_repo.delete_department(session, department)
        try:
            session.commit()
        except IntegrityError as exc:
            # The count-first gate above is not atomic: an Employee assigned to this
            # Department between the count and this commit makes the FK RESTRICT fire here.
            # That is the backstop AD-5 names — but it must reach the client as the same
            # `409 DEPARTMENT_NOT_EMPTY` the gate raises, not as the raw IntegrityError's
            # 500. Roll back, recount (the session is usable again after rollback), and
            # raise the typed refusal that names the obstruction.
            session.rollback()
            raise _department_not_empty(
                department_repo.count_employees_in_department(session, department_id)
            ) from exc


def list_departments(limit: int, offset: int) -> tuple[list[Department], int]:
    """Return one page of Departments and the full count (AC2, AC3).

    A thin pass-through opening a read session and delegating to the repository; the `api/`
    route assembles the `Page` envelope from the `(rows, total)` this returns. Scope is
    `all` — any authenticated role reads the whole list — so there is no actor here.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return department_repo.list_departments(session, limit, offset)
