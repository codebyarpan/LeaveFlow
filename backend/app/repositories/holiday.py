"""Company Holiday reads, the create, the delete, and the duplicate-date pre-check.

Implements: FR-10 (Company Holidays are created, listed and removed as data), NFR-11 (the
list is page-bounded — this issues the `LIMIT`/`OFFSET` the `api/` layer computes), AD-5 (the
`holiday_date_exists` gate that keeps a duplicate `holiday_date` a typed 409, not the
`UNIQUE`'s raw 500), AD-10 (the `get_holiday` load-or-404 input for the DELETE).

--- Why the getters here take no `actor` (and are EXEMPT from the scoped-getter rule) ---

`tests/test_scoped_getters.py` reflects over every `get_`/`list_`/`find_`/`fetch_` function
that takes a `session`, requiring the AD-10 `actor` parameter so no getter returns *another
Employee's data* unscoped. `list_holidays` and `get_holiday` match that net by name, but fall
genuinely OUTSIDE the rule: a Company Holiday is organization-wide reference data
(`{holiday_date, name}`), not Employee-derived, and its api-contracts scope is `all` — any
authenticated role reads the whole list, there is no per-row predicate to apply. So they are
added to that test's EXEMPT registry with a rationale, exactly as Story 2.1 did for leave
types and 1.5 for departments, rather than given a misleading unused `actor` param.

`holiday_date_exists` is named with neither a read-verb prefix nor a row return — it answers a
`bool` — precisely so it is correctly NOT a scoped-getter candidate.
"""

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.models import CompanyHoliday


def list_holidays(
    session: Session, limit: int, offset: int
) -> tuple[list[CompanyHoliday], int]:
    """Return one page of Company Holidays AND the full count, in the same call (AC3, AC9).

    The page and the total travel together — one `SELECT ... LIMIT/OFFSET` for the rows and
    one `SELECT count(*)` for the total — so the `api/` layer assembles the whole `Page`
    envelope from a single repository round-trip. Ordered by `holiday_date, id`: a calendar
    reads chronologically, and `id` is the deterministic tiebreaker so `LIMIT/OFFSET` never
    repeats or skips a row across pages.

    Scope is `all` (api-contracts §4.3): every row is returned to any authenticated role, so
    there is no actor and no predicate here — this getter is EXEMPT from the scoped-getter
    rule for the reason the module docstring states.
    """
    rows = list(
        session.scalars(
            select(CompanyHoliday)
            .order_by(CompanyHoliday.holiday_date, CompanyHoliday.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(CompanyHoliday)) or 0
    return rows, total


def get_holiday(session: Session, holiday_id: uuid.UUID) -> CompanyHoliday | None:
    """Return the Company Holiday with this id, or `None` if there is none.

    Keyed by the primary key, so at most one row matches. It is the DELETE's load-or-404
    input (AC8): the service loads it, and a `None` becomes `404 RESOURCE_NOT_FOUND`. EXEMPT
    from the scoped-getter rule (scope `all`, reference data — see the module docstring),
    mirroring `get_leave_type`/`get_department`.
    """
    return session.get(CompanyHoliday, holiday_id)


def holiday_date_exists(session: Session, holiday_date: datetime.date) -> bool:
    """Does a Company Holiday already fall on this `holiday_date`? The pre-write duplicate gate.

    Named with neither a read-verb prefix nor a row return (it answers a `bool`), so it is
    correctly not a scoped-getter candidate — the guardrail governs row-returning getters.
    The `UNIQUE (holiday_date)` constraint remains the AD-5 backstop; this is the gate that
    keeps a duplicate a typed 409 rather than the constraint's raw 500 (mirrors `code_exists`).
    """
    return (
        session.scalar(
            select(CompanyHoliday.id)
            .where(CompanyHoliday.holiday_date == holiday_date)
            .limit(1)
        )
        is not None
    )


def create_holiday(
    session: Session, *, holiday_date: datetime.date, name: str
) -> CompanyHoliday:
    """Insert a new Company Holiday and return it (AC3).

    A write, governed by the role gate rather than the scope contract, so it is not a
    guardrail candidate. `flush` assigns the server-default `id` so the caller can project
    it into the response before the surrounding transaction commits; it does NOT commit —
    the service owns the transaction.
    """
    holiday = CompanyHoliday(holiday_date=holiday_date, name=name)
    session.add(holiday)
    session.flush()
    return holiday


def delete_holiday(session: Session, holiday: CompanyHoliday) -> None:
    """Delete an already-loaded Company Holiday (AC8's success path).

    The service loads-or-404s first, then hands the row here. No emptiness guard:
    `company_holiday` stands alone with no FK dependents in this epic (ERD §3), so a delete
    is unconditional beyond the 404. (Recalculating existing requests on a holiday change is
    Story 2.11, not here.)
    """
    session.delete(holiday)
