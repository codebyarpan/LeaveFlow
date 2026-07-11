"""`repositories/scoping` — the scope resolver produces SQL predicates, DB-free.

Implements the test side of: AC2 (the actor's scope is a predicate IN the SQL, never a
Python-side filter over retrieved rows) and Story 1.7's Manager-predicate AC
(`employee.manager_id == :actor_id`, bound from the actor at call time). No database: the
resolver returns a SQLAlchemy expression, and we assert on its *compiled* form — the SQL
it would issue — which needs no connection.
"""

import uuid

from app.repositories.models import Employee
from app.repositories.scoping import Scope, employee_scope_predicate


class _FakeActor:
    """A structural stand-in for the acting Employee — only the `id` a predicate binds."""

    def __init__(self, actor_id: uuid.UUID) -> None:
        self.id = actor_id


def test_reports_scope_is_the_manager_reporting_edge() -> None:
    """Story 1.7's AC: `REPORTS` resolves to `employee.manager_id = :actor_id`.

    Asserted on the compiled SQL text and its bound parameter — proving the predicate is
    the reporting edge and that `:actor_id` binds the *actor's* id, evaluated at call time,
    never a value cached from the token.
    """
    actor = _FakeActor(uuid.uuid4())

    predicate = employee_scope_predicate(Scope.REPORTS, actor)
    compiled = predicate.compile()

    assert str(compiled) == "employee.manager_id = :manager_id_1"
    # The one bound value is the actor's id, read off the actor now — not the token.
    assert list(compiled.params.values()) == [actor.id]


def test_self_scope_is_the_actors_own_row() -> None:
    """`SELF` resolves to `employee.id = :actor_id` — the actor's own Employee row."""
    actor = _FakeActor(uuid.uuid4())

    predicate = employee_scope_predicate(Scope.SELF, actor)
    compiled = predicate.compile()

    assert str(compiled) == "employee.id = :id_1"
    assert list(compiled.params.values()) == [actor.id]


def test_all_scope_is_an_always_true_predicate() -> None:
    """`ALL` resolves to an always-true predicate, so an Admin read composes into the same
    `select(...).where(...)` shape without a special-cased unfiltered query."""
    actor = _FakeActor(uuid.uuid4())

    predicate = employee_scope_predicate(Scope.ALL, actor)

    # `true()` compiles to the dialect's always-true literal; on PostgreSQL, `true`.
    assert str(predicate.compile()) == "true"


def test_the_predicate_targets_the_employee_table_not_a_python_filter() -> None:
    """AC2: the resolver returns a column expression over `employee`, not a row filter.

    The predicate references `Employee.manager_id` — a mapped column — so it can only be
    composed into SQL. There is no code path here that receives rows and filters them.
    """
    actor = _FakeActor(uuid.uuid4())

    predicate = employee_scope_predicate(Scope.REPORTS, actor)

    assert Employee.manager_id.name in str(predicate.compile())
