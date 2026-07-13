"""`domain/calendar.excluded_dates` — the reasoned/named breakdown, at its boundaries. No database.

Implements the test side of Story 2.5: FR-08, AD-2, AD-21, DR-2, NFR-15, and the load-bearing
consistency invariant `count_leave_days + len(excluded_dates) == span`. Like `test_calendar.py`,
every one of these runs with no fixture — `excluded_dates` is a pure function of its arguments,
so there is no database to reach for. The reasons are asserted through `vocabulary.EXCLUSION_*`,
never a bare `"WEEKEND"`/`"HOLIDAY"` literal (AD-21).

Every chosen date states its weekday in a comment (the `test_calendar.py` discipline): a
mis-remembered date should fail the reader, not just the run.
"""

import datetime

from app.domain import vocabulary
from app.domain.calendar import ExcludedDate, count_leave_days, excluded_dates

# --- The canonical worked example, mirroring test_calendar.py -----------------------
# Friday → Tuesday, inclusive, spanning a Saturday, a Sunday, and a Monday holiday.
_FRI = datetime.date(2026, 8, 14)  # Friday    (weekday()==4)  — Working Day
_SAT = datetime.date(2026, 8, 15)  # Saturday  (weekday()==5)  — WEEKEND
_SUN = datetime.date(2026, 8, 16)  # Sunday    (weekday()==6)  — WEEKEND
_MON = datetime.date(2026, 8, 17)  # Monday    (weekday()==0)  — Company Holiday
_TUE = datetime.date(2026, 8, 18)  # Tuesday   (weekday()==1)  — Working Day


def test_a_weekend_only_span_reports_both_days_as_weekend() -> None:
    """AC5: a Saturday→Sunday range yields two `WEEKEND` entries, each with `name is None`."""
    result = excluded_dates(_SAT, _SUN, {})
    assert result == [
        ExcludedDate(_SAT, vocabulary.EXCLUSION_WEEKEND, None),
        ExcludedDate(_SUN, vocabulary.EXCLUSION_WEEKEND, None),
    ]
    assert all(ex.name is None for ex in result)


def test_a_named_holiday_carries_its_name() -> None:
    """AC1/AC5: a weekday Company Holiday is a `HOLIDAY` entry carrying its exact name.

    Tue→Wed with the Wednesday a holiday: only the Wednesday is excluded, as `HOLIDAY`,
    and its `name` is the mapping's value verbatim.
    """
    tue = datetime.date(2026, 8, 18)  # Tuesday   (weekday()==1) — Working Day
    wed = datetime.date(2026, 8, 19)  # Wednesday (weekday()==2) — holiday
    result = excluded_dates(tue, wed, {wed: "Founders' Day"})
    assert result == [ExcludedDate(wed, vocabulary.EXCLUSION_HOLIDAY, "Founders' Day")]


def test_a_holiday_on_a_saturday_is_reported_once_as_weekend() -> None:
    """AC5: weekend precedence — a Company Holiday falling on a Saturday reports once, as `WEEKEND`.

    This is what keeps the breakdown byte-for-byte consistent with `count_leave_days`, whose
    `weekday() < 5 and day not in holiday_set` short-circuit never even consults the holiday set
    on a weekend. Reporting it as `HOLIDAY` would double-book the reason and diverge the rules.
    """
    result = excluded_dates(_SAT, _SAT, {_SAT: "A holiday that lands on a Saturday"})
    assert result == [ExcludedDate(_SAT, vocabulary.EXCLUSION_WEEKEND, None)]


def test_an_all_working_day_span_is_empty() -> None:
    """AC5: a Mon→Fri span with no holidays excludes nothing — `[]`."""
    monday = datetime.date(2026, 8, 10)  # Monday (weekday()==0)
    friday = datetime.date(2026, 8, 14)  # Friday (weekday()==4)
    assert excluded_dates(monday, friday, {}) == []


def test_an_inverted_range_is_empty_and_never_raises() -> None:
    """AC5: `end < start` yields `[]` (the inclusive iteration is empty), not an exception.

    Mirrors `count_leave_days` returning 0 on an inverted range — range *validity* is enforced
    upstream at submission (Story 2.6), never in this pure breakdown.
    """
    assert excluded_dates(_TUE, _FRI, {_MON: "irrelevant"}) == []  # end (_FRI) < start (_TUE)


def test_the_consistency_invariant_holds_over_a_mixed_span() -> None:
    """AC5/AC6: `count_leave_days + len(excluded_dates) == span` across a mixed span.

    Fri→Tue spans a Working Friday, a weekend, a holiday Monday, and a Working Tuesday. The
    count is 2, the breakdown enumerates the other 3 (Sat, Sun, Mon), and 2 + 3 == 5 == span.
    This is the single assertion a reviewer checks first: the count and the breakdown can never
    disagree on which days were excluded, because they iterate the same range with the same rule.
    """
    holidays = {_MON: "Public Holiday"}
    span = (_TUE - _FRI).days + 1
    result = excluded_dates(_FRI, _TUE, holidays)

    assert count_leave_days(_FRI, _TUE, holidays.keys()) + len(result) == span
    # And the breakdown names exactly the three non-Working days, weekend-first precedence.
    assert result == [
        ExcludedDate(_SAT, vocabulary.EXCLUSION_WEEKEND, None),
        ExcludedDate(_SUN, vocabulary.EXCLUSION_WEEKEND, None),
        ExcludedDate(_MON, vocabulary.EXCLUSION_HOLIDAY, "Public Holiday"),
    ]


def test_a_datetime_key_still_matches_its_date() -> None:
    """AC5: a `datetime` holiday key is narrowed to its date, so it still excludes the day.

    The `_as_date` normalization applies to the holiday-mapping keys too — a `datetime` key
    would otherwise never equal a `date` day, silently miscounting (the trap the module guards).
    """
    wed = datetime.date(2026, 8, 19)  # Wednesday (weekday()==2) — holiday
    as_datetime = datetime.datetime(2026, 8, 19, 9, 30)
    result = excluded_dates(wed, wed, {as_datetime: "Given as a datetime"})
    assert result == [ExcludedDate(wed, vocabulary.EXCLUSION_HOLIDAY, "Given as a datetime")]


def test_the_caller_holiday_mapping_is_not_mutated() -> None:
    """AC5/AC6: the breakdown copies the holidays locally; the caller's mapping is its own.

    The preview service passes a mapping it still owns after the call (it derives `available`
    from the same rows), exactly as `count_leave_days` guarantees for its collection.
    """
    holidays = {_MON: "Public Holiday"}
    before = dict(holidays)
    excluded_dates(_FRI, _TUE, holidays)
    assert holidays == before
