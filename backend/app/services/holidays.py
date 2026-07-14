"""Company Holiday command orchestration: the create, the delete, the list, and one refusal.

Implements: FR-10 (add, list and remove Company Holidays — and, since Story 2.11, CORRECT the
requests each change affects), AD-3 (one transaction per command), AD-5 (the `UNIQUE
(holiday_date)` constraint is a BACKSTOP; this service is the gate that raises `409
HOLIDAY_DATE_IN_USE`), AD-10 (the `not_found()` convention on the DELETE of an absent id),
AD-19 (the recalculation runs INSIDE this command's one transaction, and may refuse per pair
while the rest of the operation commits). SM-6.

--- Since Story 2.11, a holiday write is not CRUD. It is a recalculation. ---

Story 2.2 shipped these commands as plain CRUD and said so in the code, because there was
nothing yet to recalculate. `leave_request` and `leave_balance` exist now, so `FR-10`'s second
half comes due: a change to the holiday calendar must CORRECT the requests it affects, "so that
a day the organization declared a holiday is not still charged against someone's balance".

So both write commands now, inside their ONE existing transaction and BEFORE the commit:

  1. flush the holiday INSERT/DELETE, so the calendar the recalculation reads is the NEW one —
     which is exactly why the recalculation cannot be a separate transaction (AD-19: "within
     the same transaction");
  2. call `services/recalculation.recalculate_for_holiday_change`, which re-derives every
     affected request's `leave_days` and the balances behind them, per (Employee, Leave Type)
     pair, and LEAVES A PAIR ENTIRELY UNCHANGED (recording an `admin_review_flag`) if the
     recalculation would drive its Available negative;
  3. commit once.

Both therefore return the holiday AND a `RecalculationSummary`, and both endpoints return `200`
with that summary rather than `201`/`204` — api-contracts §4.3, and the shape Story 2.2's own
docstring predicted would be this story's.

The refusals:
  - `HOLIDAY_DATE_IN_USE` (409) — a duplicate `holiday_date` on create. Pre-checked before the
    write, with an `IntegrityError` backstop around the insert-recalculate-commit that re-raises
    the typed 409 for a genuine TOCTOU collision — the exact shape `services/leave_types.py`
    uses for `LEAVE_TYPE_CODE_IN_USE`.
  - `404 RESOURCE_NOT_FOUND` (through `authorization.not_found()`) on a DELETE of an id that
    names no row. There is no `IntegrityError` backstop on the delete: no FK RESTRICT points at
    `company_holiday` (ERD §3), so a delete is unconditional beyond the 404.

A per-pair recalculation refusal is NOT in that list, and that is the whole of AD-19: it does
not fail the command. The edit commits, the endpoint answers `200`, and the refused pair is
named in the summary and recorded in `admin_review_flag`.

Each write command opens exactly one `with Session(get_engine(), expire_on_commit=False)` and
commits inside it (AD-3) — the idiom `services/leave_types.py`/`services/departments.py`
document. `expire_on_commit=False` keeps the returned row's attributes readable after the
block closes, so the `api/` route can project it into the response.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import holiday as holiday_repo
from app.repositories.engine import get_engine
from app.repositories.models import CompanyHoliday
from app.services import authorization as authz
from app.services import recalculation as recalculation_service
from app.services.recalculation import RecalculationSummary

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


@dataclass(frozen=True)
class HolidayView:
    """The Company Holiday a write command acted on, as plain values (Story 2.11).

    A SNAPSHOT, not the ORM row, and that matters on the DELETE path: `delete_holiday` removes the
    row, so the instance is deleted-then-detached by the time the route projects it, and reading
    attributes off it would be reading a corpse. Capturing the three fields BEFORE the delete makes
    the response's `holiday` block honest — it names the holiday that WAS deleted — with no reliance
    on what SQLAlchemy leaves readable on a deleted instance.

    The create path returns the same shape, so the route projects one type for both commands.
    """

    id: uuid.UUID
    holiday_date: datetime.date
    name: str


@dataclass(frozen=True)
class HolidayCommandResult:
    """What a holiday write did: the row it wrote, and the recalculation it triggered (AD-19).

    The pair the endpoints answer `200` with (api-contracts §4.3). The `recalculation` half is not
    decoration — AC8 forbids showing the Admin an unqualified success for an operation that
    partially refused, so the summary travels all the way to the screen.
    """

    holiday: HolidayView
    recalculation: RecalculationSummary


def create_holiday(
    *, holiday_date: datetime.date, name: str
) -> HolidayCommandResult:
    """Create a Company Holiday, recalculate what it affects, and return both (AC2–AC5).

    ONE transaction (AD-3, AD-19). In order:
      1. Pre-check the `holiday_date` — an existing row → `409 HOLIDAY_DATE_IN_USE` before the
         write.
      2. Insert and `flush` (for the server-default id) INSIDE the `try` — the repo's `flush()` is
         what emits the INSERT, so a concurrent duplicate raises the `IntegrityError` HERE, not at
         commit. Wrapping only `commit()` would let that raw 500 escape (the pre-check hides it in
         every non-concurrent test) — the exact bug the 2.1 code review fixed.
      3. RECALCULATE, on the flushed calendar, before the commit. An ADD removes a working day, so
         every affected request's `leave_days` FALLS and Available RISES — but this is NOT a
         documented no-op path, and it absolutely can refuse: only an ADD can price a request down
         to ZERO working days, and a stale-high `carried_forward(Y+1)` means even an ADD's recompute
         can LOWER a later year's accrual into a year that is already spent (Open Decision #8). The
         forward check runs unconditionally on both paths.
      4. Commit; a `UNIQUE (holiday_date)` `IntegrityError` from the flush OR the commit rolls back
         and re-raises the typed 409 ONLY for a genuine `holiday_date` collision (a concurrent
         insert between the pre-check and the commit) — the TOCTOU backstop (AD-5). Any other
         IntegrityError is re-raised untouched rather than mislabeled as a duplicate.

    ⚠️ The recalculation call sits INSIDE that `try`, and the consequence is worth stating: any
    `IntegrityError` the recalculation raised would land in the `except` below, where
    `holiday_date_exists()` returns `False` after the rollback and the raw error is re-raised as a
    500 — an unhelpful traceback pointing at the wrong cause. That is precisely the AC5 failure mode,
    and it is one more reason the forward check must make an `IntegrityError` IMPOSSIBLE rather than
    catchable. It cannot be narrowed out of the `try`: the TOCTOU backstop must still cover the
    `commit()` that follows it.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        if holiday_repo.holiday_date_exists(session, holiday_date):
            raise _holiday_date_in_use(holiday_date)

        try:
            holiday = holiday_repo.create_holiday(
                session, holiday_date=holiday_date, name=name
            )
            view = HolidayView(
                id=holiday.id, holiday_date=holiday.holiday_date, name=holiday.name
            )
            # The calendar is flushed, so `holidays_in_range` inside the recalculation already sees
            # the new holiday. Same session, same transaction (AD-19).
            summary = recalculation_service.recalculate_for_holiday_change(
                session, holiday_date=holiday_date
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if holiday_repo.holiday_date_exists(session, holiday_date):
                raise _holiday_date_in_use(holiday_date) from exc
            raise
        return HolidayCommandResult(holiday=view, recalculation=summary)


def delete_holiday(holiday_id: uuid.UUID) -> HolidayCommandResult:
    """Delete a Company Holiday, recalculate what it affects, and return both (AC2–AC5).

    Load-or-`not_found()` first: a `DELETE` of a nonexistent id is `404 RESOURCE_NOT_FOUND`, never a
    silent success or a 500. `not_found()` is reached through the `services/` authorization module
    (the route cannot import `domain/`), byte-identical every time. There is no `IntegrityError`
    backstop: no FK RESTRICT points at `company_holiday` (ERD §3), so a delete is unconditional
    beyond the 404.

    Then, in the SAME transaction (AD-19), the recalculation. A DELETE makes a working day REAPPEAR,
    so every affected request's `leave_days` RISES, `reserved`/`consumed` rise, and `available(Y)`
    FALLS — which is how a later, already-spent Leave Year is driven negative. That is the refusal
    AC4/AC5 are built around, and it is DELETE-only: the pair is left entirely unchanged, an
    `admin_review_flag` records it, the rest of the operation commits, and this still returns
    normally for a `200`.

    ⚠️ Two traps, both handled here:
      * `holiday.holiday_date` is captured BEFORE the delete — `delete_holiday(session, holiday)`
        returns `None` and the row is gone by the time the recalculation needs its date.
      * `holiday_repo.delete_holiday` does NOT flush (unlike `create_holiday`, which does). Autoflush
        would probably save us when the recalculation issues its first `SELECT`, but "probably" is
        not a guarantee that the calendar the recount reads is the NEW one — so the flush is explicit.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        holiday = holiday_repo.get_holiday(session, holiday_id)
        if holiday is None:
            authz.not_found()

        # Snapshot BEFORE the delete: the row is about to cease to exist, and the recalculation and
        # the response both still need its date.
        view = HolidayView(
            id=holiday.id, holiday_date=holiday.holiday_date, name=holiday.name
        )

        holiday_repo.delete_holiday(session, holiday)
        # EXPLICIT, not left to autoflush: the recount must read a calendar this holiday is already
        # gone from, or it recomputes the same `leave_days` it started with and corrects nothing.
        session.flush()

        summary = recalculation_service.recalculate_for_holiday_change(
            session, holiday_date=view.holiday_date
        )
        session.commit()
        return HolidayCommandResult(holiday=view, recalculation=summary)


def list_holidays(limit: int, offset: int) -> tuple[list[CompanyHoliday], int]:
    """Return one page of Company Holidays and the full count (AC3, AC9).

    A thin pass-through opening a read session and delegating to the repository; the `api/`
    route assembles the `Page` envelope from the `(rows, total)` this returns. Scope is
    `all` — any authenticated role reads the whole list — so there is no actor here.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return holiday_repo.list_holidays(session, limit, offset)
