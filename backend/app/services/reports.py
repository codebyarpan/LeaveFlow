"""The leave CSV export service: compose the report as a CSV STRING (Story 4.2).

Implements: FR-15 (`GET /api/v1/reports/leave.csv` — a Manager exports their Direct Reports'
leave, an Admin the organization's; the filter set applied to the view is applied to the export).
AD-10 (scope is a SQL predicate via the shared repository read — never a Python post-filter).
AD-18 (each row carries the STORED `leave_days`, frozen at admission; nothing here can recompute
it — this module has no access to the day-count function and must not import it). AD-12 (dates
`YYYY-MM-DD`), AD-21 (status values travel verbatim UPPER_SNAKE_CASE). AC1–AC4.

--- Why the CSV string is built HERE, not in the route ---

Contract 4 forbids `app.services` from importing fastapi/starlette, and contract 2 forbids
`app.api` from importing `repositories/`. So the layering is: this service runs the scoped read
and serializes the rows to a CSV string (stdlib `csv` + `io` — both uncontracted); the route
wraps that string in the `Response` with the `text/csv` media type and the `Content-Disposition`
header. 7/7 import-linter contracts kept.

--- Why the read is UNPAGINATED ---

The export carries ALL matching rows (Story 4.2 Landmine 1 / Open Decision #1): the pagination
convention binds list endpoints — the `items/page/page_size/total` envelope — and this endpoint
returns CSV, not that envelope. FR-15 binds the applied FILTER SET, never a page. The same
repository function the paged list uses is called with `limit=None, offset=None`, so filter and
scope semantics are shared by construction and screen and export cannot disagree. NFR-10's data
scale (one small organization) makes the unbounded read safe; the endpoint is role-gated to
Manager/Admin.
"""

from __future__ import annotations

import csv
import datetime
import io
import uuid

from sqlalchemy.orm import Session

from app.repositories import leave_request as leave_request_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.services.leave_requests import (
    LEAVE_STATUS_VALUES as LEAVE_STATUS_VALUES,  # re-export for the route's filter enum
)
from app.services.leave_requests import _scope_for_role, row_to_view

# The exported column set (Story 4.2 Open Decision #2): the human-answerable fields of the
# shared `row_to_view` view — the applicant, the Leave Type, the date range, the STORED day
# count, and the state (FR-20's history entry plus the employee name, since this is a
# multi-employee report). Internal UUIDs answer no manager's question and are omitted. The
# header row is pinned verbatim by test.
CSV_COLUMNS: tuple[str, ...] = (
    "employee_full_name",
    "leave_type_code",
    "leave_type_name",
    "start_date",
    "end_date",
    "leave_days",
    "status",
)

# Spreadsheet formula triggers (2026-07-15 code review). RFC 4180 quoting does not neutralize
# them: Excel/Sheets evaluate a cell whose text begins with any of these, and `full_name` is
# SELF-EDITABLE (`PATCH /me`) — an employee named `=HYPERLINK(...)` would execute in the
# Manager's spreadsheet session on open. OWASP's mitigation: prefix a single quote, which
# spreadsheets read as "literal text" and drop from display.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_cell(value: str) -> str:
    """Neutralize a formula-leading text cell for spreadsheet consumption (CSV injection)."""
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def export_leave_csv(
    actor: Employee,
    *,
    status: str | None = None,
    leave_type_id: uuid.UUID | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> str:
    """Return the leave report as a CSV string, SCOPED to the caller (AC1–AC4).

    Scope resolves from the actor's role exactly as the paged list does (`_scope_for_role`:
    Admin `ALL`, Manager `REPORTS`) — a Manager's export EXCLUDES their own requests, because
    AD-10's REPORTS predicate is `employee.manager_id = :actor_id` and the endpoint's contract
    scope is `reports, all`, with no `self` (api-contracts §4.9). The optional filters are
    Story 3.1's, forwarded verbatim to the SAME repository read the list endpoint uses
    (`limit=None`: every matching row, Landmine 1) — OVERLAP date semantics, inverted range or
    unknown `leave_type_id` → zero rows, never an error. A READ session (AD-3, house pattern).

    Serialization: stdlib `csv.writer` over `io.StringIO`, default dialect (RFC 4180 quoting —
    `full_name`/`leave_type_name` may contain commas or quotes — and `\\r\\n` line endings).
    Header row + one row per request, newest first (the repository's UUIDv7 `id DESC` order).
    Dates via `date.isoformat()` (AD-12); `leave_days` the stored int (AD-18); `status`
    verbatim uppercase (AD-21). A zero-row result is the header row alone, not an error.
    """
    scope = _scope_for_role(actor.role)
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, _total = leave_request_repo.list_leave_requests(
            session,
            actor,
            scope=scope,
            status=status,
            leave_type_id=leave_type_id,
            date_from=date_from,
            date_to=date_to,
        )
        views = [row_to_view(row) for row in rows]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for view in views:
        writer.writerow(
            (
                # The three free-text-adjacent fields pass the formula guard; dates are
                # `isoformat()`, `leave_days` an int, `status` a vocabulary constant — none
                # can lead with a formula trigger.
                _sanitize_cell(view.employee_name),
                _sanitize_cell(view.leave_type_code),
                _sanitize_cell(view.leave_type_name),
                view.start_date.isoformat(),
                view.end_date.isoformat(),
                view.leave_days,
                view.status,
            )
        )
    return buffer.getvalue()
