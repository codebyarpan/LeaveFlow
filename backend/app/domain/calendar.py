"""The leave-day count — the one implementation, nowhere else.

Implements: FR-08, DR-1, DR-2, AD-2, AD-18, NFR-08. This is the *only* module in the
entire system that knows what a weekend or a Company Holiday is. Every path that touches
a Leave Balance — the pre-submission preview (Story 2.5, which reaches both the count and
the reasoned/named `excluded_dates` breakdown that now live here), the submission that
freezes the count on the request (Story 2.6, AD-18), the holiday-change recalculation
(Story 2.11) — reaches a Leave Day count through here. A second implementation of
weekend-or-holiday logic anywhere in the codebase is, by DR-2, a defect.

Purity is the point (AD-1, NFR-08): this module imports no ORM, no web framework, and
performs no I/O, so weekend-and-holiday logic *cannot* be expressed anywhere a database
lives. The import-linter "domain/ is pure" contract fails the build on a violation, and
its tests (`tests/domain/test_calendar.py`) run with no fixture.
"""

import datetime
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from app.domain import vocabulary


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


@dataclass(frozen=True)
class ExcludedDate:
    """One picked date that costs no Leave Day, and why (Story 2.5, api-contracts §4.5).

    `reason` is one of `vocabulary.EXCLUSION_WEEKEND`/`_HOLIDAY` — never a bare string (AD-21).
    `name` carries the Company Holiday's name when `reason == EXCLUSION_HOLIDAY`, and is `None`
    for a `WEEKEND` (a Saturday/Sunday has no name). Frozen: an excluded date is a value, and a
    value is immutable — two equal breakdowns compare equal, which the DB-free tests rely on.
    """

    date: datetime.date
    reason: str
    name: str | None


def excluded_dates(
    start: datetime.date,
    end: datetime.date,
    holidays: Mapping[datetime.date, str],
) -> list[ExcludedDate]:
    """Enumerate every non-Working Day in the inclusive range `[start, end]`, with its reason.

    The companion to `count_leave_days`: it walks the SAME inclusive range with the SAME
    weekend/holiday rule, so the two can never disagree. For every input the load-bearing
    invariant holds (Story 2.5 AC5/AC6):

        count_leave_days(start, end, holidays.keys()) + len(excluded_dates(start, end, holidays))
            == span

    where `span = (end - start).days + 1` for `end >= start`, else `0`.

    Weekend-first precedence is what preserves that invariant: a day that is a Saturday or
    Sunday is reported as `WEEKEND` (name `None`) WITHOUT consulting the holiday map — exactly
    `count_leave_days`' `weekday() < 5 and day not in holiday_set` short-circuit, which never
    tests a weekend day against the holiday set. So a Company Holiday that falls on a weekend is
    reported ONCE, as `WEEKEND`. A weekday that is in `holidays` is a `HOLIDAY` carrying its
    name; a weekday that is not is a Working Day and is not appended.

    `holidays` is a `date → name` mapping (the count takes a bare `Collection[date]`; the
    breakdown needs the NAMES, which api-contracts §4.5 shows a `HOLIDAY` carrying). It is
    copied into a local dict under `_as_date` normalization, so a `datetime` key still matches
    its calendar day (the same silent-miss trap `count_leave_days` guards) and the caller's
    mapping is never mutated — membership is order/duplicate-independent.

    A pure function of its arguments (AD-2): same inputs → same output, no clock, no I/O, no
    mutation. It never raises on its inputs — an inverted range (`end < start`) yields `[]`, the
    empty iteration, mirroring `count_leave_days` returning 0. Range *validity* (start ≤ end, the
    zero-day and cross-year refusals) is enforced upstream at submission (Story 2.6), never here,
    so this same pure pair serves preview, submission and recalculation alike.

    Args:
        start: First day of the range (inclusive), a calendar `date` (AD-12).
        end: Last day of the range (inclusive), a calendar `date` (AD-12).
        holidays: The Company Holidays in scope, as a `date → name` mapping.

    Returns:
        The excluded dates in chronological (range) order, each an `ExcludedDate`.
    """
    start = _as_date(start)
    end = _as_date(end)
    # Copy under `_as_date` so a `datetime` key matches its calendar day and the caller is never
    # mutated — the dict mirrors `count_leave_days`' local `holiday_set` for the same reasons.
    holiday_map = {_as_date(key): value for key, value in holidays.items()}

    excluded: list[ExcludedDate] = []
    day = start
    while day <= end:
        if day.weekday() >= 5:
            # Weekend first (Sat/Sun): reported without consulting the holiday map, so a
            # holiday-on-a-weekend is a single `WEEKEND` entry — byte-for-byte the count's
            # short-circuit, which keeps the breakdown and the count in agreement.
            excluded.append(ExcludedDate(day, vocabulary.EXCLUSION_WEEKEND, None))
        elif day in holiday_map:
            excluded.append(
                ExcludedDate(day, vocabulary.EXCLUSION_HOLIDAY, holiday_map[day])
            )
        # else: a weekday not in the holiday map is a Working Day — not appended.
        day += datetime.timedelta(days=1)

    return excluded
