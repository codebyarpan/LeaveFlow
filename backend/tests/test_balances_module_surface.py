"""AC4: the balance-mutation module exposes EXACTLY eight public operations.

Implements the test side of Story 2.4 AC4 / AD-17: `services/balances.py` is the one module
that mutates a `leave_balance` quantity, and it exposes exactly `reserve`, `consume_reserved`,
`consume_direct`, `release_reserved`, `release_consumed`, `adjust_reserved`, `adjust_consumed`
and `set_accrual` — no more, no fewer. A ninth public callable (a stray helper made public, a
read function that drifted in from `balance_reads.py`) fails the build here.

DB-free: it imports and reflects, it never connects. Mirrors the reflection style of
`tests/test_scoped_getters.py`. Reads (`GET /balances`, `GET /employees/<id>/balances`) live in
`services/balance_reads.py` precisely so this module stays the eight mutators.
"""

import inspect

from app.services import balances

# The eight balance-mutation operations AC4 fixes the module at. This list IS the contract.
_EXPECTED_PUBLIC_CALLABLES = frozenset(
    {
        "reserve",
        "consume_reserved",
        "consume_direct",
        "release_reserved",
        "release_consumed",
        "adjust_reserved",
        "adjust_consumed",
        "set_accrual",
    }
)


def _public_callables_defined_here() -> set[str]:
    """Every public function DEFINED in `services/balances.py` (not merely imported).

    Filtered to functions whose `__module__` is this module — so imported names (`Session`,
    `DomainError`) are excluded — and to names not starting with `_` (helpers are private).
    """
    return {
        name
        for name, obj in inspect.getmembers(balances, inspect.isfunction)
        if obj.__module__ == balances.__name__ and not name.startswith("_")
    }


def test_the_module_exposes_exactly_the_eight_operations() -> None:
    """AC4: exactly the eight named mutators are public — no ninth, none missing."""
    assert _public_callables_defined_here() == set(_EXPECTED_PUBLIC_CALLABLES), (
        "services/balances.py must expose EXACTLY the eight balance-mutation operations "
        "(AC4/AD-17). A ninth public callable — a read that belongs in balance_reads.py, or "
        "a helper that should be `_`-prefixed — breaks the one-mutation-module invariant."
    )


def test_there_are_exactly_eight() -> None:
    """The count is eight — a belt-and-braces guard on the set assertion above."""
    assert len(_public_callables_defined_here()) == 8
