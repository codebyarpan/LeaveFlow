"""The base proration — how an Annual Entitlement is reduced for a mid-year joiner.

Implements: DR-9 (proration is floored — rounded DOWN, never to nearest), DR-8 (the Leave
Year is the calendar year 1 Jan–31 Dec), AD-1 / NFR-08. Like `domain/calendar.py`, this is
a pure module: it imports the standard library only, reaches no clock, performs no I/O and
imports no ORM. The `leave_year` is passed in — the function never calls `date.today()`, so
"the current Leave Year" is a decision the imperative shell (`services/`) makes, and this
stays a pure function of `(annual_entitlement, joining_date, leave_year)` (AD-1: the clock
lives in the shell, never in `domain/`). The import-linter "domain/ is pure" contract fails
the build on a violation, and its tests (`tests/domain/test_proration.py`) run with no fixture.

Proration is one of the product's hard rules, so it carries tests (NFR-15).
"""

import datetime


def prorate_entitlement(
    annual_entitlement: int,
    joining_date: datetime.date,
    leave_year: int,
) -> int:
    """Prorate `annual_entitlement` for an Employee joining `joining_date`, for `leave_year`.

    Returns a whole number of Leave Days (DR-10 — an ``int``, never a float or ``Decimal``),
    reduced for the months of `leave_year` the Employee was NOT present, and rounded DOWN.

    Three cases, by the relationship of the joining year to the Leave Year:

    - `joining_date.year < leave_year` — the Employee was present the whole year, so proration
      reduces nothing and the full `annual_entitlement` is returned (ERD §6, "Not a gap").
    - `joining_date.year == leave_year` — the Employee was present from their joining month
      through December inclusive: `remaining_months = 13 - joining_date.month` (January → 12,
      September → 4, December → 1). The prorated entitlement is
      `(annual_entitlement × remaining_months) // 12`. Integer floor division **is** floor for
      these non-negative operands — that is the "rounded down, never to nearest" of DR-9
      (`12 × 4 // 12 == 4`; `10 × 3 // 12 == 2`, i.e. `2.5` floored, never `3`).
    - `joining_date.year > leave_year` — defensive: an Employee has no entitlement for a year
      before they joined, so 0. Unreachable via this story's materialization (which creates
      only current-year rows for existing Employees), but the function stays total — it never
      raises on its inputs.

    Args:
        annual_entitlement: The full-year Leave Days a Leave Type grants (`LeaveType.annual_
            entitlement`), a whole number.
        joining_date: The Employee's `joining_date`, a calendar ``date``.
        leave_year: The calendar year (1 Jan–31 Dec) the balance is for (DR-8). Passed in —
            the function never reads the clock (AD-1).

    Returns:
        The prorated entitlement for `leave_year` as an ``int``, rounded down.
    """
    if joining_date.year < leave_year:
        # Present the whole Leave Year — proration reduces nothing (ERD §6).
        return annual_entitlement
    if joining_date.year > leave_year:
        # No entitlement for a year before the Employee joined (defensive; keeps the
        # function total). This story never materializes such a row.
        return 0

    # Joined during the Leave Year: present from the joining month through December inclusive.
    # January → 12 months, September → 4, December → 1. Floor division IS floor here (both
    # operands are non-negative), which is exactly DR-9's "rounded down, never to nearest".
    remaining_months = 13 - joining_date.month
    return (annual_entitlement * remaining_months) // 12
