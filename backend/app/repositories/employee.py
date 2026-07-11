"""Employee reads. The persistence side of authentication and, later, authorization.

Implements: FR-01 (login looks an Employee up by email), AD-10 (every read is scoped to
the actor's authority — see the exemption below).

--- Why `get_by_email` is exempt from Story 1.4's scoped-getter rule ---

Story 1.4 introduces the rule that every getter takes the acting Employee and scopes
its read to what that actor may see. `get_by_email` predates any actor: it runs during
*authentication*, before a session exists, so there is no actor to scope to. It is the
one getter that answers "who is this, by email" for the login path, and Story 1.4's
rule does not — cannot — apply to it. Later getters that run under an authenticated
session take the actor; this one never will.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.repositories.models import Employee


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
