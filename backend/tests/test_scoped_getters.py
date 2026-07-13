"""The armed guardrail: no repository getter returns Employee-derived data actor-lessly.

Implements the test side of: AC1 (every getter that can return another Employee's data
takes the acting Employee as a parameter, and none exists without one) and AC2 (scope is
a SQL predicate — enforced here by refusing an unscoped getter to exist in the first
place; a getter that takes no actor cannot apply a scope predicate). NFR-04, AD-10,
architecture §7 ("there is no `get_leave_request(id)`").

--- Why a reflection test, and why an explicit EXEMPT registry ---

A reflection test reads *signatures*, not *intent*. It cannot know that
`get_by_id_with_department` is legitimately actor-less because it resolves the caller
themselves, before any scope exists. So the exempt getters are named in an explicit EXEMPT
registry, each already documenting *why* in its own docstring. Every other repository getter
must take the acting Employee.

There are two grounds for exemption, and the registry holds both:

  1. Actor RESOLUTION — a getter that answers "who is the caller" before any scope exists
     (`get_by_email`, `get_by_id_with_department`). AD-10's rule cannot apply: there is no
     actor yet to scope to.
  2. Scope-`all` REFERENCE reads — a getter over an organization-wide table whose
     api-contracts scope is `all`, returning rows that are NOT Employee-derived data, so
     there is no per-row predicate to apply and no cross-Employee disclosure to guard
     (`list_departments`, `get_department` — a Department is `{id, name}`; leave types and
     holidays follow in Epic 2, all api-contracts scope `all`). AD-10 (AC1) governs getters
     that return *another Employee's data*; these return none, so they are a convention-bound
     false positive of the name-matcher, exactly what "the reach of the net, stated honestly"
     below anticipates. The honest resolution is EXEMPT-with-rationale, never an unused
     `actor` param that would imply a scoping that does not happen.

--- Why this passes today, and what it is really for ---

The only getters today are the two exempt ones, so the check passes. That is intended: it
is an ARMED GUARDRAIL for Stories 1.5 / 1.6 / 1.7 and Epic 2, not a test of existing
scoped behaviour (none exists yet). A future story that adds `get_leave_request(session,
id)` — the exact unscoped getter AD-10 and architecture §7 forbid by name — fails the
build until the author either scopes it (adds the actor) or deliberately adds it to EXEMPT
with a justification. DB-free: it imports and reflects, it never connects.

--- The reach of the net, stated honestly ---

The matcher is convention-bound: it flags a function only if its name starts with one of
`_READ_VERB_PREFIXES` AND it takes a `session` parameter, and it is satisfied by a param
named `actor`. A getter that breaks those conventions — a non-standard verb (`read_`,
`employee_by_id`), a session parameter under another name (`db`, `conn`), or an acting
Employee under another name (`caller`, `acting_employee`) — is not caught (or, for the
last, is a false positive). Recursion is covered (`walk_packages`); naming is not. The
conventions are the enforced house style; if they are ever relaxed, widen the constants
below in the same change.
"""

import importlib
import inspect
import pkgutil
from types import ModuleType

import pytest

import app.repositories as repositories_pkg

# The getters that legitimately take no actor, on the two grounds the module docstring
# states: actor RESOLUTION (they run before any scope exists), and scope-`all` REFERENCE
# reads (they return no Employee-derived data, so AD-10's per-Employee scoping does not
# apply). Each carries a "why exempt" docstring at its definition. Adding to this set is a
# deliberate act a reviewer sees; it is not the default escape hatch. A new entry here must
# come with the same kind of docstring on the getter.
EXEMPT: frozenset[str] = frozenset(
    {
        # Actor-resolution getters (repositories/employee.py).
        "get_by_email",
        "get_by_id_with_department",
        # Scope-`all` reference reads (repositories/department.py) — Story 1.5, Trap 1.
        "list_departments",
        "get_department",
        # Scope-`all` reference reads (repositories/leave_type.py) — Story 2.1. A Leave
        # Type is organization-wide reference data (`{code, name, entitlement, ...}`), not
        # Employee-derived; api-contracts scope is `all`, so any role reads the whole list
        # and there is no per-row predicate to apply. Exactly the case the module docstring
        # anticipates: "leave types and holidays follow in Epic 2, all api-contracts scope
        # `all`". Each carries its own "why exempt" docstring at its definition.
        "list_leave_types",
        "get_leave_type",
    }
)

# A repository read is named with one of these verbs. Writes (`create_`, `update_`,
# `delete_`) are not getters and are governed by the role gate, not the scope contract.
_READ_VERB_PREFIXES = ("get_", "list_", "find_", "fetch_")

# The parameter name that carries the acting Employee. A getter satisfies AC1 by taking it.
_ACTOR_PARAM_NAMES = frozenset({"actor"})

# Repository data-access functions take the session first; this is what separates a getter
# that issues SQL (`get_by_email(session, ...)`) from a helper that does not
# (`get_engine()` builds the pool and takes no session — not a scoped getter).
_SESSION_PARAM_NAME = "session"


def _repository_modules() -> list[ModuleType]:
    """Import every module under `app.repositories` *recursively*, for reflection.

    `walk_packages`, not `iter_modules`, so a getter added one package deeper (e.g. a
    future `repositories/leave/reads.py`) is reflected too — `iter_modules` would see only
    top-level modules and let a subpackage getter escape the AC1 check entirely.
    """
    modules: list[ModuleType] = []
    for info in pkgutil.walk_packages(
        repositories_pkg.__path__, prefix=f"{repositories_pkg.__name__}."
    ):
        modules.append(importlib.import_module(info.name))
    return modules


def _is_scoped_getter_candidate(func) -> bool:  # type: ignore[no-untyped-def]
    """A public read function that issues SQL — i.e. one that takes a `session`.

    Reads (`get_`/`list_`/`find_`/`fetch_`) that take a `session` parameter are the getters
    AC1 governs. `get_engine()` shares the `get_` prefix but takes no session, so it is not
    a getter of persisted rows and is correctly excluded.
    """
    if not func.__name__.startswith(_READ_VERB_PREFIXES):
        return False
    params = inspect.signature(func).parameters
    return _SESSION_PARAM_NAME in params


def _scoped_getters() -> list:  # type: ignore[type-arg]
    """Every repository getter that issues SQL, across all `app.repositories` modules."""
    getters = []
    for module in _repository_modules():
        for _name, func in inspect.getmembers(module, inspect.isfunction):
            # Only functions DEFINED in this module — not names it merely imported (e.g.
            # `select`, `joinedload`), which would otherwise be reflected in every module.
            if func.__module__ != module.__name__:
                continue
            if func.__name__.startswith("_"):
                continue
            if _is_scoped_getter_candidate(func):
                getters.append(func)
    return getters


def test_there_are_getters_to_inspect() -> None:
    """A guardrail over zero getters passes vacuously and proves nothing.

    Today this finds exactly the two exempt actor-resolution getters. If it ever finds
    none, the reflection is broken (a moved package, a renamed prefix) and every
    per-getter assertion below is silently passing over an empty set.
    """
    assert _scoped_getters(), "no repository getters found to inspect — reflection broke"


@pytest.mark.parametrize(
    "getter", _scoped_getters(), ids=lambda f: f"{f.__module__}.{f.__name__}"
)
def test_every_getter_takes_the_actor_or_is_explicitly_exempt(getter) -> None:  # type: ignore[no-untyped-def]
    """AC1: a getter returning Employee-derived data takes the actor, or is EXEMPT.

    Parametrized per getter so a failure names the offending function directly, and so the
    set grows with the codebase without this test being revisited.
    """
    if getter.__name__ in EXEMPT:
        return

    params = inspect.signature(getter).parameters
    takes_actor = bool(_ACTOR_PARAM_NAMES & set(params))

    assert takes_actor, (
        f"{getter.__module__}.{getter.__name__} is a repository getter that can return "
        "another Employee's data without taking the acting Employee (AC1 / AD-10 / "
        "NFR-04). Either give it an `actor` parameter and apply the scope as a SQL "
        "predicate (repositories/scoping.py), OR — if it legitimately resolves the caller "
        "themselves, before any scope exists — add it to EXEMPT in this test with a "
        "docstring on the getter explaining why, as the two seeded getters do."
    )
