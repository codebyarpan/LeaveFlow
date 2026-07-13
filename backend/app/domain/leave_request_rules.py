"""The pure range-validity predicates a Leave Request submission decides on (Story 2.6, AD-2/AD-1).

Implements: FR-08 (the range refusals `INVALID_DATE_RANGE`, `PAST_DATE_RANGE`,
`SPANS_TWO_LEAVE_YEARS` — `ZERO_LEAVE_DAYS` is `count_leave_days == 0`, decided in
`domain/calendar`). These are the date-property checks a submission makes BEFORE it locks the
balance; `services/leave_requests` calls them and raises the typed `DomainError` (the service is
the gate — the predicates only answer questions).

Purity is the point (AD-1, AD-2): this module imports no ORM, no clock and no web framework. The
"today" a `PAST_DATE_RANGE` check needs is passed IN by the service (the clock lives in the shell,
AD-1), so these functions are pure functions of their arguments and DB-/clock-free-testable
(`tests/domain/test_leave_request_rules.py`, no fixture). They are deliberately SEPARATE from
`count_leave_days`/`excluded_dates`, which Story 2.3/2.5 kept total and permissive (never raising
on their inputs so the same pair serves preview, submit and recalculation) — range VALIDITY is
2.6's, and it belongs here, beside the count, not inside it.

The refusal PRECEDENCE (which check fires first when several would) is the service's, documented
there: `INVALID_DATE_RANGE → PAST_DATE_RANGE → SPANS_TWO_LEAVE_YEARS → ZERO_LEAVE_DAYS`. These
predicates are independent booleans; the order in which they are consulted is the caller's.
"""

import datetime


def is_inverted_range(start: datetime.date, end: datetime.date) -> bool:
    """Is the range inverted — `end` before `start` (`INVALID_DATE_RANGE`)?

    A single-day request (`start == end`) is valid, so the test is strict `<`. This is the one
    range shape `count_leave_days` treats as 0 Working Days rather than refusing (it is total);
    the submission refuses it instead, because a request whose end precedes its start is malformed,
    not merely zero-cost.
    """
    return end < start


def is_wholly_past(end: datetime.date, today: datetime.date) -> bool:
    """Does the range lie WHOLLY in the past — `end` before `today` (`PAST_DATE_RANGE`)?

    The rule is `end < today` (Story 2.6 Open Question 3): a range with ANY day today-or-later is
    still actionable (leave can begin today), so only a range whose LAST day is already behind us
    is refused. `today` is supplied by the service from the shell clock (AD-1) — never read here —
    so this stays a pure function of its two dates.
    """
    return end < today


def spans_two_leave_years(start: datetime.date, end: datetime.date) -> bool:
    """Does the range cross a Leave-Year boundary — `start.year != end.year` (`SPANS_TWO_...`)?

    The Leave Year is the calendar year (DR-8), so a request may not straddle 31 December: its
    days would draw on two different years' balances, which the single-balance reservation this
    story performs cannot express. A same-year range (including an inverted one, caught earlier)
    returns `False`.
    """
    return start.year != end.year


def leave_year_end_boundary(start: datetime.date) -> datetime.date:
    """The 31 December the `SPANS_TWO_LEAVE_YEARS` refusal names as the crossed boundary.

    The last day of `start`'s Leave Year — the boundary a cross-year range steps over. The service
    carries its ISO string in the refusal's `details` so the caller sees exactly where to split the
    request. A pure function of `start`'s year.
    """
    return datetime.date(start.year, 12, 31)
