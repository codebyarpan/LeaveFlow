"""`domain/proration.py` — the base proration, at its boundaries. No database.

Implements the test side of Story 2.4: DR-9 (proration floors, never rounds to nearest),
DR-8 (the Leave Year is the calendar year), AD-1/NFR-08 (the function is pure — it imports
only `datetime` and the function under test, reaches no clock, and needs no fixture; mirror
`tests/domain/test_calendar.py`). Proration is a hard rule and carries tests (NFR-15).

Every case names the AC it closes. The canonical AC2 case is the September joiner with a
12-day entitlement prorating to 4; the floor cases prove the rounding is always DOWN.
"""

import datetime

from app.domain.proration import prorate_entitlement


def test_canonical_september_joiner_with_twelve_prorates_to_four() -> None:
    """AC2/DR-9: a September joiner with an Annual Entitlement of 12 prorates to 4.

    `12 × 4/12` — the joining month (September) through December inclusive is 4 months —
    is exactly 4. The single most important assertion of the proration rule.
    """
    joining = datetime.date(2026, 9, 15)  # September → 4 remaining months (Sep, Oct, Nov, Dec)
    assert prorate_entitlement(12, joining, 2026) == 4


def test_a_fractional_result_is_floored_never_rounded_to_nearest() -> None:
    """AC2/DR-9: a computed entitlement of 4.16 yields 4 — rounded DOWN, never to nearest.

    The AC's literal example: a November joiner with 25 days — `25 × 2/12 = 4.16` — yields 4,
    floored, never rounded up to 4 (and never to nearest). An October joiner with 10 days:
    `10 × 3/12 = 2.5`, floored to 2 (never 3). A September joiner with 15 days: `15 × 4/12 =
    5.0`, exactly 5. All three prove floor division IS the "rounded down" of DR-9 for these
    non-negative operands.
    """
    november = datetime.date(2026, 11, 1)  # 2 remaining months (Nov, Dec)
    assert prorate_entitlement(25, november, 2026) == 4  # 4.16 floored, never 5 and never rounded

    october = datetime.date(2026, 10, 1)  # 3 remaining months (Oct, Nov, Dec)
    assert prorate_entitlement(10, october, 2026) == 2  # 2.5 floored, never 3

    september = datetime.date(2026, 9, 1)  # 4 remaining months
    assert prorate_entitlement(15, september, 2026) == 5  # 5.0 exactly


def test_a_january_joiner_gets_the_full_entitlement() -> None:
    """DR-9: a January joiner is present for all 12 months → the full entitlement.

    `12 × 12/12 = 12` — January means `13 - 1 = 12` remaining months, so proration reduces
    nothing.
    """
    january = datetime.date(2026, 1, 1)
    assert prorate_entitlement(12, january, 2026) == 12


def test_a_december_joiner_gets_one_twelfth_floored() -> None:
    """DR-9: a December joiner is present for one month → `annual // 12`.

    December means `13 - 12 = 1` remaining month, so `24 × 1/12 = 2` and `12 × 1/12 = 1`.
    """
    december = datetime.date(2026, 12, 1)
    assert prorate_entitlement(24, december, 2026) == 2
    assert prorate_entitlement(12, december, 2026) == 1


def test_a_prior_year_joiner_gets_the_full_entitlement() -> None:
    """ERD §6 "Not a gap": an Employee who joined before the Leave Year was present the whole
    year, so proration reduces nothing — the full `annual_entitlement`, regardless of month."""
    joined_last_year = datetime.date(2025, 9, 15)  # month is irrelevant for a prior year
    assert prorate_entitlement(12, joined_last_year, 2026) == 12


def test_a_zero_entitlement_prorates_to_zero() -> None:
    """DR-9: a Leave Type with a zero Annual Entitlement prorates to 0 for any joiner."""
    september = datetime.date(2026, 9, 15)
    assert prorate_entitlement(0, september, 2026) == 0


def test_a_future_year_join_gets_zero() -> None:
    """The function is total: a `joining_date.year > leave_year` (an Employee has no
    entitlement for a year before they joined) returns 0. Defensive — unreachable via this
    story's current-year materialization, but the function never raises on its inputs."""
    joins_next_year = datetime.date(2027, 3, 1)
    assert prorate_entitlement(12, joins_next_year, 2026) == 0


def test_the_return_is_a_plain_int_never_a_bool() -> None:
    """DR-10: a proration is a whole number of days — an `int`, and not the `bool` subtype.

    `isinstance(True, int)` is True in Python, so the `bool` exclusion is explicit.
    """
    result = prorate_entitlement(12, datetime.date(2026, 9, 15), 2026)
    assert isinstance(result, int)
    assert not isinstance(result, bool)


def test_it_is_a_pure_function_of_its_arguments() -> None:
    """AD-1/NFR-08: same inputs → same output, no reliance on the clock. Passing `leave_year`
    explicitly (never `date.today()`) is what makes proration reproducible."""
    joining = datetime.date(2026, 9, 15)
    assert prorate_entitlement(12, joining, 2026) == prorate_entitlement(12, joining, 2026)
