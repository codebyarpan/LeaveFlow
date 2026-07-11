"""The scope resolver: an actor plus a scope becomes a SQL predicate, never a filter.

Implements: AD-10 (authorization is a query predicate applied IN the SQL, not a
post-retrieval filter over rows already read), NFR-04, architecture §7. This is "the
scope resolver introduced by Story 1.4" that `epics.md#Story 1.7` (line 817) consumes.

--- Why this is grounded in `Employee`, and not a resource-agnostic framework ---

The resolver's one guaranteed consumer shape today is the Employee reporting edge:
`Employee.manager_id == :actor_id`. The only scoped model that exists is `Employee`
(migration 0002). Its first *live* getter consumers are Story 1.7 (Employee reads) and
Epic 2's Leave Request reads — and the Leave Request table does not exist yet. So this
resolver is built against the concrete Employee predicate, not generalized over resources
that have no tables. Epic 2 extends it when a genuinely data-scoped resource arrives
(Trap 6). Generalizing now would be scope machinery for resources that do not exist.

--- Why it returns a predicate, never applies a filter ---

Every function here returns a SQLAlchemy `ColumnElement[bool]` to be composed into a
`select(...).where(...)`. It never receives rows and never filters them in Python. That
is AD-10 / NFR-04 structurally: the actor's scope is a predicate the database evaluates,
so an out-of-scope row is never retrieved in the first place — and a scope miss is a
missing row the service turns into a byte-identical 404.
"""

import enum
import uuid
from typing import Protocol

from sqlalchemy import ColumnElement, true

from app.repositories.models import Employee


class _Actor(Protocol):
    """The one attribute a scope predicate reads off the acting Employee: `id`.

    A structural shape, not the ORM `Employee`, so the resolver is unit-testable with a
    fake actor and no database. The Manager predicate binds `:actor_id` from `actor.id` at
    call time — never from a cached token claim (AD-14).
    """

    id: uuid.UUID


class Scope(enum.Enum):
    """The three authority scopes api-contracts §4 grants an endpoint against a resource.

    `SELF` — the actor's own row. `REPORTS` — the Employees who report to the actor.
    `ALL` — every row, no restriction (an Admin). These are the grants Story 1.7 gates
    Employee reads with; Epic 2 reuses them for Leave Requests.
    """

    SELF = "self"
    REPORTS = "reports"
    ALL = "all"


def employee_scope_predicate(scope: Scope, actor: _Actor) -> ColumnElement[bool]:
    """Resolve `scope` for `actor` into a predicate over the `Employee` table.

    - `SELF` → `Employee.id == actor.id` — the actor's own row.
    - `REPORTS` → `Employee.manager_id == actor.id` — the Manager reporting edge Story 1.7
      evaluates; the `:actor_id` bind comes from `actor.id` at call time (AD-10 / AD-14).
    - `ALL` → `true()` — an always-true predicate, so an Admin's read composes into the
      same `select(...).where(...)` shape without a special-cased unfiltered query.

    Returned for composition into a `select`, never applied as a Python-side filter (AC2).
    """
    if scope is Scope.SELF:
        return Employee.id == actor.id
    if scope is Scope.REPORTS:
        return Employee.manager_id == actor.id
    if scope is Scope.ALL:
        return true()
    # Every `Scope` member is handled explicitly above. A member added later without a
    # branch here must fail loud, NOT fall through to `true()` — an unrestricted read is
    # the exact AD-10 leak this resolver exists to prevent.
    raise ValueError(f"unhandled scope: {scope!r}")
