"""Company Holiday command orchestration: the create, the delete, the list, and one refusal.

Implements: FR-10 (add, list and remove Company Holidays), AD-3 (one transaction per
command), AD-5 (the `UNIQUE (holiday_date)` constraint is a BACKSTOP; this service is the
gate that raises `409 HOLIDAY_DATE_IN_USE`), AD-10 (the `not_found()` convention on the
DELETE of an absent id). SM-6.

The single refusal this story raises on create:
  - `HOLIDAY_DATE_IN_USE` (409) — a duplicate `holiday_date`. Pre-checked before the write,
    with an `IntegrityError` backstop around the insert-and-commit that re-raises the typed
    409 for a genuine TOCTOU collision — the exact shape `services/leave_types.py` uses for
    `LEAVE_TYPE_CODE_IN_USE`.

The DELETE raises `404 RESOURCE_NOT_FOUND` (through `authorization.not_found()`) for an id
that names no row. There is no `IntegrityError` backstop on the delete: no FK RESTRICT points
at `company_holiday` (ERD §3), so a delete is unconditional beyond the 404 — simpler than the
departments delete, which must guard its FK dependents.

Each write command opens exactly one `with Session(get_engine(), expire_on_commit=False)` and
commits inside it (AD-3) — the idiom `services/leave_types.py`/`services/departments.py`
document. `expire_on_commit=False` keeps the returned row's attributes readable after the
block closes, so the `api/` route can project it into the response.
"""

import datetime
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import holiday as holiday_repo
from app.repositories.engine import get_engine
from app.repositories.models import CompanyHoliday
from app.services import authorization as authz

# One message per refusal, stated once at module level — mirrors `services/leave_types.py`'s
# `_LEAVE_TYPE_CODE_IN_USE_MESSAGE`. The `details` carry the conflicting `holiday_date` so
# NFR-17's "names the obstruction" is satisfied — a date is not sensitive, so naming it is
# helpful rather than a disclosure.
_HOLIDAY_DATE_IN_USE_MESSAGE = "A holiday already exists on that date."


def _holiday_date_in_use(holiday_date: datetime.date) -> DomainError:
    """Build the `409 HOLIDAY_DATE_IN_USE` refusal, naming the conflicting date (AD-5).

    Shared by the pre-write gate and the `UNIQUE (holiday_date)` `IntegrityError` backstop so
    both paths raise a byte-identical envelope — the same code, message and `details`. The
    date is carried as an ISO `YYYY-MM-DD` string (`.isoformat()`): that is the wire shape,
    and a raw `date` is not JSON-serialisable in the envelope's `details`.
    """
    return DomainError(
        code=vocabulary.HOLIDAY_DATE_IN_USE,
        message=_HOLIDAY_DATE_IN_USE_MESSAGE,
        details={"holiday_date": holiday_date.isoformat()},
    )


def create_holiday(*, holiday_date: datetime.date, name: str) -> CompanyHoliday:
    """Create a Company Holiday and return it, refusing a duplicate date (AC3, AC5).

    One transaction (AD-3). In order:
      1. Pre-check the `holiday_date` — an existing row → `409 HOLIDAY_DATE_IN_USE` before
         the write.
      2. Insert and `flush` (for the server-default id) INSIDE the `try` — the repo's
         `flush()` is what emits the INSERT, so a concurrent duplicate raises the
         `IntegrityError` HERE, not at commit. Wrapping only `commit()` would let that raw
         500 escape (the pre-check hides it in every non-concurrent test) — the exact bug the
         2.1 code review fixed.
      3. Commit; a `UNIQUE (holiday_date)` `IntegrityError` from the flush OR the commit rolls
         back and re-raises the typed 409 ONLY for a genuine `holiday_date` collision (a
         concurrent insert between the pre-check and the commit) — the TOCTOU backstop (AD-5).
         Any other IntegrityError is re-raised untouched rather than mislabeled as a duplicate.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        if holiday_repo.holiday_date_exists(session, holiday_date):
            raise _holiday_date_in_use(holiday_date)

        try:
            holiday = holiday_repo.create_holiday(
                session, holiday_date=holiday_date, name=name
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if holiday_repo.holiday_date_exists(session, holiday_date):
                raise _holiday_date_in_use(holiday_date) from exc
            raise
        return holiday


def delete_holiday(holiday_id: uuid.UUID) -> None:
    """Delete a Company Holiday, or raise `404` if the id names no row (AC8).

    Load-or-`not_found()` first: a `DELETE` of a nonexistent id is `404 RESOURCE_NOT_FOUND`,
    never a silent success or a 500. `not_found()` is reached through the `services/`
    authorization module (the route cannot import `domain/`), byte-identical every time.
    There is no FK RESTRICT pointing at `company_holiday` (ERD §3), so no `IntegrityError`
    backstop is needed — the delete is unconditional beyond the 404.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        holiday = holiday_repo.get_holiday(session, holiday_id)
        if holiday is None:
            authz.not_found()
        holiday_repo.delete_holiday(session, holiday)
        session.commit()


def list_holidays(limit: int, offset: int) -> tuple[list[CompanyHoliday], int]:
    """Return one page of Company Holidays and the full count (AC3, AC9).

    A thin pass-through opening a read session and delegating to the repository; the `api/`
    route assembles the `Page` envelope from the `(rows, total)` this returns. Scope is
    `all` — any authenticated role reads the whole list — so there is no actor here.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return holiday_repo.list_holidays(session, limit, offset)
