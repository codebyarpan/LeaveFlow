"""Leave Request orchestration — Story 2.5 ships the read-only preview command.

Implements: FR-08 (the day count and its reasoned/named breakdown, plus the projected balance,
BEFORE a request is submitted), AD-2 (this is the sole caller-facing entry to `domain.calendar`'s
count + breakdown for the preview — the client computes nothing), AD-3 (the preview is ADVISORY
and side-effect-free: this command opens a READ session, acquires NO lock, writes NOTHING, and
creates no `leave_request` row — that table arrives in Story 2.6). DR-3/AD-5 (the three STORED
balance quantities travel up; `available_before`/`available_after` are derived at the `api/`
projection, never here). SM-6.

The file name is plural (`leave_requests`) to match `api/v1/leave_requests.py` and the codebase's
`leave_types`/`balances` idiom; it is the spine's `services/leave_request`. Story 2.6 extends it
into the full submission command (the reservation, the validity refusals, the request row).

--- Scope boundary: what 2.5 ships vs. what 2.6 owns ---

The preview is TOTAL and permissive (AC5): `count_leave_days`/`excluded_dates` never raise on
their inputs, so a start-after-end range previews as `0` days with an empty breakdown, and a
zero-Working-Day range previews as `0`. Range validity and its refusals — `INVALID_DATE_RANGE`,
`ZERO_LEAVE_DAYS`, `SPANS_TWO_LEAVE_YEARS`, `PAST_DATE_RANGE` — are the submission path's (2.6),
decided under lock. `INSUFFICIENT_BALANCE` is likewise NOT raised here (AC11): an overspend shows
a negative `available_after`, never a refusal. This module imports neither `services/balances.py`
nor `INSUFFICIENT_BALANCE`.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import calendar
from app.domain.calendar import ExcludedDate
from app.repositories import holiday as holiday_repo
from app.repositories import leave_balance as leave_balance_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import authorization as authz


@dataclass(frozen=True)
class PreviewView:
    """The preview as the service hands it up — the day count, the breakdown, the three quantities.

    `available_before`/`available_after` are NOT here: they are derived (`accrued − consumed −
    reserved`, then minus `leave_days`) at the `api/` projection, mirroring `BalanceView` (DR-3,
    AD-5, AC8). `accrued` travels so the projection can derive `available_before`; `excluded_dates`
    is the `domain.ExcludedDate` type (a service may import `domain/`). `leave_days` is the domain
    count.
    """

    leave_days: int
    excluded_dates: list[ExcludedDate]
    accrued: int
    reserved: int
    consumed: int


def _current_leave_year() -> int:
    """The current Leave Year — `date.today().year` (DR-8). The clock lives in the shell (AD-1)."""
    return datetime.date.today().year


def preview_leave_request(
    actor: Employee,
    *,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
) -> PreviewView:
    """Preview what a request would cost the caller — read-only, side-effect-free (FR-08, AD-3).

    Scope `SELF`, intrinsic to the token subject (like `GET /balances`): the caller previews
    their OWN current-year balance. In order:

      1. Open one READ session — no `commit()`, nothing is written (AD-3).
      2. Read the caller's `(accrued, reserved, consumed)` for this Leave Type, scoped to `SELF`.
         A `None` — an unknown `leave_type_id`, or no materialized balance — is a byte-identical
         `404 RESOURCE_NOT_FOUND` via `authz.not_found()` (AC10).
      3. Read the Company Holidays in `[start, end]` and build the `date → name` map.
      4. Reach `domain.calendar` for BOTH the count and the reasoned/named breakdown — the single
         day-count authority (AD-2). The client renders these; it computes nothing.

    Returns a `PreviewView`; the `api/` layer derives `available_before`/`available_after` from
    its three stored quantities (DR-3). No lock, no write, no reservation, no `INSUFFICIENT_BALANCE`
    (AC9, AC11).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        row = leave_balance_repo.get_balance(
            session,
            actor,
            employee_id=actor.id,
            leave_type_id=leave_type_id,
            leave_year=_current_leave_year(),
            scope=Scope.SELF,
        )
        if row is None:
            authz.not_found()

        holidays = holiday_repo.holidays_in_range(session, start, end)
        holiday_map = {holiday.holiday_date: holiday.name for holiday in holidays}

        leave_days = calendar.count_leave_days(start, end, holiday_map.keys())
        excluded = calendar.excluded_dates(start, end, holiday_map)

        return PreviewView(
            leave_days=leave_days,
            excluded_dates=excluded,
            accrued=row.accrued,
            reserved=row.reserved,
            consumed=row.consumed,
        )
