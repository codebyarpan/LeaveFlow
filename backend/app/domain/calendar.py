"""The leave-day count — the one implementation, nowhere else.

Implements: FR-08, DR-1, DR-2, AD-2, AD-18, NFR-08. This is the *only* module in the
entire system that knows what a weekend or a Company Holiday is. Every path that touches
a Leave Balance — the pre-submission preview (Story 2.5), the submission that freezes the
count on the request (Story 2.6, AD-18), the holiday-change recalculation (Story 2.11) —
reaches a Leave Day count through here. A second implementation of weekend-or-holiday
logic anywhere in the codebase is, by DR-2, a defect.

Purity is the point (AD-1, NFR-08): this module imports no ORM, no web framework, and
performs no I/O, so weekend-and-holiday logic *cannot* be expressed anywhere a database
lives. The import-linter "domain/ is pure" contract fails the build on a violation, and
its tests (`tests/domain/test_calendar.py`) run with no fixture.
"""

import datetime
from collections.abc import Collection


def _as_date(value: datetime.date) -> datetime.date:
    """Return a plain calendar ``date``, narrowing a ``datetime`` to its date component.

    Module-private (AC1 exposes exactly ``count_leave_days``). ``datetime.datetime`` subclasses
    ``date``, so it would otherwise pass through the range/membership logic while never matching
    a ``date`` in the holiday set — a silent, holiday-eating miscount. This keeps the AD-12
    "dates are ``DATE``, never instants" discipline true even if a caller slips a ``datetime`` in.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def count_leave_days(
    start: datetime.date,
    end: datetime.date,
    holidays: Collection[datetime.date],
) -> int:
    """Count the Working Days in the inclusive range ``[start, end]``.

    A day is a Working Day iff it is a weekday (Mon–Fri) and not a Company Holiday
    (DR-1). Weekend days (Saturday, Sunday) and Company Holidays are excluded, for every
    Employee. Returns a whole number of Leave Days (DR-10 — an ``int``, never a float or
    ``Decimal``).

    The range is inclusive of both endpoints: a one-day request over a single Working Day
    costs 1. An inverted range (``end < start``) yields 0 — the inclusive iteration is
    simply empty. This counter never raises on its inputs; range *validity* (start ≤ end,
    contiguity, the zero-day-refusal) is enforced upstream at submission (Story 2.6), not
    here, so the same pure function serves preview, submission, and recalculation alike.

    The function is a pure function of its arguments (AD-2): same inputs → same output, no
    reliance on the clock or a timezone, no mutation of ``holidays``, and a result that is
    independent of the order or duplication of the holiday collection.

    Args:
        start: First day of the range (inclusive), a calendar ``date`` (AD-12).
        end: Last day of the range (inclusive), a calendar ``date`` (AD-12).
        holidays: The Company Holidays to exclude, in any collection. Holiday *names* are
            irrelevant to the count and are not a parameter here; they surface only in the
            preview breakdown (Story 2.5).

    Returns:
        The number of Working Days in ``[start, end]`` as an ``int``.
    """
    # Normalize to plain calendar dates. `datetime.datetime` is a *subclass* of `date`, so a
    # `datetime` argument type-checks and iterates — but a `datetime` never equals a `date` in
    # a set, which would silently defeat holiday exclusion (over-counting, charging leave for a
    # Company Holiday). AD-12 already forbids `datetime`/`TIMESTAMPTZ` here; this coercion makes
    # the guarantee defensive-by-construction rather than a trust in every future caller.
    start = _as_date(start)
    end = _as_date(end)
    # Copy into a local set: O(1), order- and duplicate-independent membership, and the
    # caller — a service holding company_holiday rows it still owns — is never mutated.
    holiday_set = {_as_date(holiday) for holiday in holidays}

    count = 0
    day = start
    while day <= end:
        # date.weekday() is Mon=0 … Sun=6, so `< 5` is Mon–Fri. NOT isoweekday()
        # (Mon=1 … Sun=7): the off-by-one there would misclassify the weekend.
        if day.weekday() < 5 and day not in holiday_set:
            count += 1
        day += datetime.timedelta(days=1)

    return count
