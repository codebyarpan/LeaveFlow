"""`domain/leave_request_rules` + the zero-day count — the submission's pure predicates. No database.

Implements the test side of Story 2.6 AC4's range refusals AT THE PURE LAYER: `INVALID_DATE_RANGE`
(`is_inverted_range`), `PAST_DATE_RANGE` (`is_wholly_past`, the `end < today` rule), and
`SPANS_TWO_LEAVE_YEARS` (`spans_two_leave_years` + the named `leave_year_end_boundary`); plus
`ZERO_LEAVE_DAYS` as `count_leave_days == 0`. Like `test_calendar.py`/`test_excluded_dates.py`,
every test runs with NO fixture — these are pure functions of their arguments (the `today` a
past-check needs is passed IN, never read from a clock), so there is no database or clock to reach
for. The typed `DomainError` raising, the precedence and the lock-decided `INSUFFICIENT_BALANCE`
are the SERVICE's, exercised in `tests/integration/test_leave_request_submit.py`.

Every chosen date states its weekday in a comment (the domain-test discipline): a mis-remembered
date should fail the reader, not just the run.
"""

import datetime

from app.domain.calendar import count_leave_days
from app.domain.leave_request_rules import (
    is_inverted_range,
    is_wholly_past,
    leave_year_end_boundary,
    spans_two_leave_years,
)

# The canonical worked example, mirroring test_calendar.py.
_FRI = datetime.date(2026, 8, 14)  # Friday    (weekday()==4)  — Working Day
_SAT = datetime.date(2026, 8, 15)  # Saturday  (weekday()==5)  — WEEKEND
_SUN = datetime.date(2026, 8, 16)  # Sunday    (weekday()==6)  — WEEKEND
_MON = datetime.date(2026, 8, 17)  # Monday    (weekday()==0)  — Working Day (no holiday here)


# --- INVALID_DATE_RANGE: an inverted range (end < start) ------------------------------------


def test_inverted_range_is_invalid() -> None:
    """`end` strictly before `start` is inverted; `start == end` (a one-day request) is not."""
    assert is_inverted_range(_MON, _FRI) is True  # Mon → Fri, end before start
    assert is_inverted_range(_FRI, _MON) is False  # Fri → Mon, forward
    assert is_inverted_range(_FRI, _FRI) is False  # single day is valid


# --- PAST_DATE_RANGE: the range lies wholly in the past (end < today) -----------------------


def test_wholly_past_is_end_before_today() -> None:
    """`end < today` is refused; a range whose last day is today-or-later is still actionable."""
    today = _TUE = datetime.date(2026, 8, 18)  # the reference "today", passed IN (no clock)
    # end strictly before today → wholly past.
    assert is_wholly_past(_MON, today) is True  # Mon 17 < Tue 18
    # end == today → NOT wholly past (a range ending today is still actionable).
    assert is_wholly_past(_TUE, today) is False
    # end after today → not past.
    assert is_wholly_past(datetime.date(2026, 8, 20), today) is False


# --- SPANS_TWO_LEAVE_YEARS: start.year != end.year, and the named boundary ------------------


def test_cross_year_range_spans_two_leave_years_and_names_the_boundary() -> None:
    """A Dec→Jan range spans two Leave Years; the boundary named is that 31 December."""
    dec = datetime.date(2026, 12, 30)  # Wednesday (weekday()==2)
    jan = datetime.date(2027, 1, 4)  # Monday    (weekday()==0)
    assert spans_two_leave_years(dec, jan) is True
    assert leave_year_end_boundary(dec) == datetime.date(2026, 12, 31)


def test_same_year_range_does_not_span_two_leave_years() -> None:
    """A range wholly inside one calendar year does not span two Leave Years."""
    assert spans_two_leave_years(_FRI, _MON) is False
    # The boundary helper is a pure function of the start's year, whatever the end.
    assert leave_year_end_boundary(_FRI) == datetime.date(2026, 12, 31)


# --- ZERO_LEAVE_DAYS: the range contains no Working Day (count_leave_days == 0) --------------


def test_zero_leave_days_is_count_of_zero_working_days() -> None:
    """A weekend-only range has 0 Working Days — the `ZERO_LEAVE_DAYS` predicate the service uses.

    Range validity lives in `leave_request_rules`, but the zero-day refusal is `count_leave_days
    == 0` (the count is the day-count authority, AD-2) — asserted here so the two live together.
    """
    assert count_leave_days(_SAT, _SUN, []) == 0  # Sat + Sun, no working day
    assert count_leave_days(_FRI, _FRI, []) == 1  # a single Friday is one working day
    # A weekday that is a Company Holiday also yields zero.
    assert count_leave_days(_MON, _MON, [_MON]) == 0
