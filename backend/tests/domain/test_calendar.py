"""`domain/calendar.py` — the one leave-day count, at its boundaries. No database.

Implements the test side of Story 2.3: FR-08, DR-1, DR-2, SM-2, AD-1, AD-2, NFR-08,
NFR-15. This is one of the five correctness metrics of the product (SM-2), and every one
of these tests runs in milliseconds with no fixture — `tests/domain/` defines no
`db_connection`, and a pure counter has no database to reach for (spine *Testing*).

Every chosen date states its weekday in a comment. A date-based fixture rots silently the
day someone mis-remembers 2026-08-14 as a Thursday; stating the weekday makes a wrong date
fail the reader, not just the run.
"""

import datetime

from app.domain.calendar import count_leave_days

# --- The canonical worked example (AC2 / SM-2) -------------------------------------
# Friday → Tuesday, inclusive, spanning a Saturday, a Sunday, and a Monday holiday.
_FRI = datetime.date(2026, 8, 14)  # Friday    (weekday()==4)  — counts
_SAT = datetime.date(2026, 8, 15)  # Saturday  (weekday()==5)  — weekend
_SUN = datetime.date(2026, 8, 16)  # Sunday    (weekday()==6)  — weekend
_MON = datetime.date(2026, 8, 17)  # Monday    (weekday()==0)  — Company Holiday
_TUE = datetime.date(2026, 8, 18)  # Tuesday   (weekday()==1)  — counts


def test_canonical_friday_to_tuesday_over_weekend_and_holiday_is_two() -> None:
    """AC2/SM-2: Fri→Tue spanning Sat, Sun, and a holiday Monday costs exactly 2.

    The single most important assertion in the story: only the Friday and the Tuesday
    are Working Days; the weekend and the Company Holiday come out of nobody's balance.
    """
    assert count_leave_days(_FRI, _TUE, [_MON]) == 2


def test_a_saturday_sunday_range_is_zero() -> None:
    """AC3: a range of only weekend days costs 0."""
    assert count_leave_days(_SAT, _SUN, []) == 0


def test_a_range_of_only_weekends_and_holidays_is_zero() -> None:
    """AC3: a range consisting only of weekend days and Company Holidays costs 0.

    Sat 08-15, Sun 08-16 (weekend) and Mon 08-17 (holiday) — nothing counts.
    """
    assert count_leave_days(_SAT, _MON, [_MON]) == 0


def test_boundary_starts_sunday_ends_saturday_counts_the_interior_week() -> None:
    """AC4(a): endpoints on non-working days are excluded; interior Working Days count.

    Sun 2026-08-16 → Sat 2026-08-22 inclusive. The Sunday start and Saturday end do not
    count; Mon–Fri (08-17 … 08-21) do → 5. Here 08-17 is supplied as *not* a holiday.
    """
    start = datetime.date(2026, 8, 16)  # Sunday    (weekday()==6)
    end = datetime.date(2026, 8, 22)  # Saturday  (weekday()==5)
    assert count_leave_days(start, end, []) == 5


def test_single_day_on_a_working_day_is_one() -> None:
    """AC4(b): a one-day range over a single Working Day costs 1 (inclusive endpoints)."""
    assert count_leave_days(_FRI, _FRI, []) == 1  # Friday


def test_single_day_on_a_weekend_is_zero() -> None:
    """AC4(c): a one-day range on a Saturday costs 0."""
    assert count_leave_days(_SAT, _SAT, []) == 0  # Saturday


def test_single_day_on_a_holiday_is_zero() -> None:
    """AC4(d): a one-day range on a Company Holiday costs 0."""
    assert count_leave_days(_MON, _MON, [_MON]) == 0  # Monday, supplied as holiday


def test_a_full_monday_to_sunday_week_with_no_holidays_is_five() -> None:
    """AC7: Saturday and Sunday are both excluded for every Employee; Mon–Fri → 5.

    Mon 2026-08-10 → Sun 2026-08-16 inclusive, no holidays: the five weekdays count and
    the weekend does not. This is the weekend-exclusion semantics, stated positively.
    """
    monday = datetime.date(2026, 8, 10)  # Monday (weekday()==0)
    sunday = datetime.date(2026, 8, 16)  # Sunday (weekday()==6)
    assert count_leave_days(monday, sunday, []) == 5


def test_the_return_is_a_plain_int_never_a_bool() -> None:
    """AC8/DR-10: a Leave Day is a whole number — an `int`, and not the `bool` subtype.

    `isinstance(True, int)` is True in Python, so the `bool` exclusion is explicit: no
    path should ever hand back `True`/`False` masquerading as a count.
    """
    result = count_leave_days(_FRI, _TUE, [_MON])
    assert isinstance(result, int)
    assert not isinstance(result, bool)


def test_repeated_calls_are_deterministic() -> None:
    """AC9: a pure function of its arguments — same inputs, same output."""
    assert count_leave_days(_FRI, _TUE, [_MON]) == count_leave_days(_FRI, _TUE, [_MON])


def test_holiday_order_and_duplication_do_not_change_the_count() -> None:
    """AC9: the result is independent of the order or duplication of the holidays.

    A scrambled `list` with a duplicate holiday yields the same count as the holidays as
    a `set` — proving the internal `set(holidays)` copy and O(1), order-free membership.
    """
    scrambled_with_dup = [_MON, _TUE, _MON, _FRI]  # duplicated _MON, out of order
    as_set = {_MON, _TUE, _FRI}
    assert count_leave_days(_FRI, _TUE, scrambled_with_dup) == count_leave_days(
        _FRI, _TUE, as_set
    )


def test_the_passed_holiday_collection_is_not_mutated() -> None:
    """AC9: the counter copies the holidays into a local set; the caller's object is its own.

    Story 2.5/2.6's service passes a collection it still owns after the call.
    """
    holidays = [_MON]
    before = list(holidays)
    count_leave_days(_FRI, _TUE, holidays)
    assert holidays == before


def test_an_inverted_range_is_zero_and_never_raises() -> None:
    """AC10: `end < start` yields 0 (the inclusive iteration is empty), not an exception.

    Range *validity* (start ≤ end, contiguity, zero-day refusal) is enforced upstream at
    submission (Story 2.6), never in this pure counter.
    """
    assert count_leave_days(_TUE, _FRI, [_MON]) == 0  # end (_FRI) < start (_TUE)


def test_an_empty_holiday_calendar_as_list_and_as_set_counts_all_weekdays() -> None:
    """AC7/AC9: the `Collection` contract holds for both an empty list and an empty set.

    A Mon–Fri range with no holidays → 5 whether the calendar arrives as `[]` or `set()`.
    """
    monday = datetime.date(2026, 8, 10)  # Monday  (weekday()==0)
    friday = datetime.date(2026, 8, 14)  # Friday  (weekday()==4)
    assert count_leave_days(monday, friday, []) == 5
    assert count_leave_days(monday, friday, set()) == 5
