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

from sqlalchemy import select
from sqlalchemy.orm import Session

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
