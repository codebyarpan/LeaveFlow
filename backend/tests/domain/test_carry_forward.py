"""`carry_forward_days` — the pure carry-forward arithmetic (Story 2.10, AC3, AC4, AC9).

DB-free by construction, like `test_proration.py`: `tests/domain/conftest.py` defines no fixtures
at all, deliberately, and the integration `conftest` is out of reach from here. NFR-15 names
carry-forward and the year boundary as unit-tested rules, and this is that unit test — no server,
no database, no clock (AC9).

The function under test never receives a Leave Type CODE, and cannot: its parameters are
`available`, `carries_forward` and `carry_forward_cap`. That is what makes AC4 —"the behaviour was
decided by reading the attribute, not by testing the Leave Type's name" — unfalsifiable rather than
merely asserted. There is no `code` in scope to test against.
"""

import pytest

from app.domain.carry_forward import carry_forward_days


def test_a_carrying_type_under_the_cap_carries_everything_available() -> None:
    """AC3: below the ceiling, the whole Available balance carries into `Y + 1`."""
    assert carry_forward_days(available=8, carries_forward=True, carry_forward_cap=30) == 8


def test_a_carrying_type_over_the_cap_carries_the_cap_and_the_excess_lapses() -> None:
    """AC3: `min(cap, available)` — the excess above the cap LAPSES, it does not accumulate.

    This is the assertion that makes the cap mean something: 40 days available against a cap of 30
    carries 30, and the other 10 are gone. Carry-forward is `min(...)`, never a running total.
    """
    assert carry_forward_days(available=40, carries_forward=True, carry_forward_cap=30) == 30


def test_a_cap_exactly_equal_to_available_carries_all_of_it() -> None:
    """The boundary: `min(30, 30) == 30`. Neither off-by-one direction lapses a day it shouldn't."""
    assert carry_forward_days(available=30, carries_forward=True, carry_forward_cap=30) == 30


def test_a_lapsing_type_with_a_cap_set_still_carries_nothing() -> None:
    """AC4 — THE test: `carries_forward=False` carries 0 even with a cap of 30 sitting right there.

    The cap being set is the entire point. If the implementation consulted the cap first — or, worse,
    branched on a Leave Type code — this case would carry 30. It carries 0, because the ATTRIBUTE is
    read first and the cap is never consulted for a lapsing type (ERD: the cap is "meaningless when
    `carries_forward` is false", which is why it is nullable).
    """
    assert carry_forward_days(available=30, carries_forward=False, carry_forward_cap=30) == 0


def test_a_lapsing_type_with_a_null_cap_carries_nothing() -> None:
    """AC4: the seeded shape of CL and FL — lapsing, cap NULL. Their unused days lapse."""
    assert carry_forward_days(available=12, carries_forward=False, carry_forward_cap=None) == 0


def test_a_carrying_type_with_a_null_cap_is_uncapped() -> None:
    """Open Decision #2: a NULL cap on a CARRYING type means NO CEILING — carry all of Available.

    The one genuinely under-determined point in the specification. The ERD explains the column's
    nullability only for lapsing types ("meaningless when `carries_forward` is false"); no artifact
    says what a NULL cap means on a type that DOES carry, and AD-6's `min(cap, available)` is simply
    undefined for NULL. Resolved as uncapped: it is what `min()` degenerates to with no ceiling, and
    the alternative (NULL means zero) would make a carrying type silently lapse EVERYTHING — a wrong
    balance that would be believed, which is the exact failure PRD §1 exists to prevent.
    """
    assert carry_forward_days(available=25, carries_forward=True, carry_forward_cap=None) == 25


def test_nothing_available_carries_nothing() -> None:
    """An Employee who spent their whole entitlement carries 0 — not a negative, not the cap."""
    assert carry_forward_days(available=0, carries_forward=True, carry_forward_cap=30) == 0


def test_a_zero_cap_carries_nothing_even_on_a_carrying_type() -> None:
    """A cap of 0 is a real, legal configuration: the type carries, but the ceiling is zero.

    Distinct from NULL (uncapped) above — which is precisely why NULL cannot be treated as 0.
    """
    assert carry_forward_days(available=15, carries_forward=True, carry_forward_cap=0) == 0


@pytest.mark.parametrize("carries_forward", [True, False])
def test_a_negative_available_never_produces_a_negative_carry(carries_forward: bool) -> None:
    """The function is TOTAL: it clamps at 0 rather than propagating a negative into `set_accrual`.

    `available` cannot actually be negative — `leave_balance`'s `accrued - consumed - reserved >= 0`
    CHECK guarantees it — so this input is unreachable through the rollover. The clamp costs nothing
    and means the function has no input on which it returns nonsense, which is worth more than an
    assertion that the caller behaved.
    """
    assert carry_forward_days(
        available=-5, carries_forward=carries_forward, carry_forward_cap=30
    ) == 0
