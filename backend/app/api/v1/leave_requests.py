"""The `/api/v1/leave-requests` routes: the preview read (2.5) and the submit write (2.6).

Implements: FR-08 (`POST /leave-requests/preview` — the day count, its reasoned/named
`excluded_dates` breakdown, and the projected balance, before a request is submitted; the ONLY
way a client obtains a Leave Day count, AD-2 — AND `POST /leave-requests`, the atomic submission
that reserves the days and returns the persisted row), FR-09 (managerless auto-approval, surfaced
as a returned `status` of `APPROVED`). AD-3 (the preview is ADVISORY — it never decides admission;
submission re-reads the balance under lock and decides there). DR-3/AD-5 (`available_before`/
`available_after` are DERIVED HERE at the preview projection, never read from a column or computed
in a lower layer). AD-18 (the submit response reads the STORED `leave_days`, never recomputes it).
AC1, AC2, AC8, AC10, AC11 (2.5); AC3, AC4, AC8 (2.6).

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies` only — never `repositories/` or
`domain/` (contract 2). So it cannot import `services.leave_requests.PreviewView` or
`domain.calendar.ExcludedDate`: the view and each excluded-date item are duck-typed as `object`,
exactly the `balances.py`/`leave_types.py` precedent. Scope `self` is intrinsic to the token
subject, so the guard is `get_current_employee` (any authenticated role), NOT `require_role`.

--- Why `available_before`/`available_after` are computed HERE ---

`available_before = accrued − consumed − reserved` and `available_after = available_before −
leave_days` are derived at THIS projection, from the three stored quantities the read service
hands up (DR-3, AD-5) — the same projection `balances.py::_to_response` documents. No column,
model, migration or lower layer computes or stores an `available` figure. `available_after` may be
NEGATIVE (an overspend, AC11) — it is not clamped: the honest projection of "you would be over".

--- The 2xx success code ---

`200` — a preview is a computation over a `POST` body (the request carries a range), matching the
React `usePreviewLeaveRequest` hook.
"""

from __future__ import annotations

import datetime
import enum
import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, model_validator

from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import leave_requests as leave_requests_service

router = APIRouter()

# The `status` filter's accepted values (Story 2.7, AC4). Built at runtime from the service's
# re-exported `LEAVE_STATUS_VALUES` so no status LITERAL is typed in `api/` — `test_vocabulary_
# literals.py` forbids the string `"PENDING"` here, and contract 2 forbids importing `domain/`. As a
# FastAPI query-param type this yields a framework `422` on an unrecognized value (the same
# input-validation class as a bad UUID), never a domain error, so `CODE_TO_STATUS`/vocabulary stay
# untouched. A member's `.value` is the status string handed to the service.
LeaveStatusFilter = enum.Enum(  # type: ignore[misc]
    "LeaveStatusFilter",
    {value: value for value in leave_requests_service.LEAVE_STATUS_VALUES},
)

# Defensive resource guard (code review 2026-07-13; extended to submit, Story 2.6). Both endpoints
# are deliberately permissive on range *validity* — the real refusals are the domain's
# (`INVALID_DATE_RANGE`/`SPANS_TWO_LEAVE_YEARS`, decided under lock on submit) — but an unbounded
# span would drive `count_leave_days`/`excluded_dates` through millions of day-by-day iterations, a
# CPU/memory exhaustion vector for any authenticated caller. 366 (one leap Leave Year) is the
# tightest ceiling that never rejects a legitimate single-year request; a longer span is refused as
# MALFORMED INPUT (422) — the same framework input-validation class that already rejects a bad UUID
# or unparseable date, NOT a domain error code, so `CODE_TO_STATUS`/vocabulary stay untouched. The
# domain's `SPANS_TWO_LEAVE_YEARS` (a stricter, single-year rule) is what actually governs a valid
# submission; this cap only bounds iteration/allocation, and preview and submit share it.
_MAX_SPAN_DAYS = 366


def _assert_span_within_bound(start_date: datetime.date, end_date: datetime.date) -> None:
    """Refuse an oversized forward span as malformed input (422) — the shared resource guard.

    Only a forward span exceeding `_MAX_SPAN_DAYS` is refused; an inverted range yields a
    non-positive span and is left permissive (the preview treats it as 0 days; submit refuses it
    with the domain's `INVALID_DATE_RANGE`). Raising `ValueError` inside a `model_validator` makes
    Pydantic surface it as the framework's input-validation error, exactly like a bad UUID.
    """
    span = (end_date - start_date).days + 1
    if span > _MAX_SPAN_DAYS:
        raise ValueError(
            f"date range spans {span} days; at most {_MAX_SPAN_DAYS} are accepted"
        )


class PreviewRequest(BaseModel):
    """The preview request body — the Leave Type and the inclusive date range.

    The request shape is the Pydantic model's: api-contracts §4.5 fixes only the RESPONSE, as it
    does for `/balances`. snake_case, whole-day fields; FastAPI parses `YYYY-MM-DD` → `date`
    (api-contracts §1 date convention).
    """

    leave_type_id: uuid.UUID
    start_date: datetime.date
    end_date: datetime.date

    @model_validator(mode="after")
    def _span_within_bound(self) -> PreviewRequest:
        """Refuse an oversized span as malformed input (resource guard, code review 2026-07-13).

        Delegates to the shared `_assert_span_within_bound` — the same 366-day ceiling `submit`
        applies. An inverted range is left permissive (it previews as 0 days, AC5); validity
        refusals remain the submission path's.
        """
        _assert_span_within_bound(self.start_date, self.end_date)
        return self


class ExcludedDateResponse(BaseModel):
    """One excluded date on the wire (api-contracts §4.5): `{date, reason}`, plus `name` for a HOLIDAY.

    A `WEEKEND` entry serializes `name: null`; a `HOLIDAY` carries the Company Holiday's name —
    matching the §4.5 example. `reason` is the server-provided `WEEKEND`/`HOLIDAY` string.
    """

    date: datetime.date
    reason: str
    name: str | None = None


class PreviewResponse(BaseModel):
    """The preview payload (api-contracts §4.5).

    `leave_days` is the Working-Day count; `excluded_dates` names every non-Working day in the
    range (chronological); `available_before`/`available_after` are the DERIVED projection figures.
    Whole-day integers; `available_after` may be negative (AC11).
    """

    leave_days: int
    excluded_dates: list[ExcludedDateResponse]
    available_before: int
    available_after: int


def _to_response(view: object) -> PreviewResponse:
    """Project a `PreviewView` into the response, DERIVING `available_*` here (DR-3, AC8).

    Typed `object` because `api/` may not import the service dataclass or the ORM (contract 2),
    the `balances.py`/`leave_types.py` precedent; the read service guarantees the fields are
    present. `available_before = accrued − consumed − reserved`; `available_after` subtracts the
    `leave_days` — computed at THIS projection, never read from a stored column. Each excluded-date
    item is duck-typed too (read `.date`/`.reason`/`.name`, never importing `ExcludedDate`).
    `available_after` is NOT clamped: a negative figure is the honest overspend projection (AC11).
    """
    available_before = view.accrued - view.consumed - view.reserved
    available_after = available_before - view.leave_days
    return PreviewResponse(
        leave_days=view.leave_days,
        excluded_dates=[
            ExcludedDateResponse(date=item.date, reason=item.reason, name=item.name)
            for item in view.excluded_dates
        ],
        available_before=available_before,
        available_after=available_after,
    )


@router.post("/leave-requests/preview", tags=["leave-requests"])
def preview_leave_request(
    body: PreviewRequest,
    caller: Actor = Depends(get_current_employee),
) -> PreviewResponse:
    """Preview a request's cost for the caller (AC1, FR-08). Auth only, any role; scope `self`.

    `get_current_employee`, NOT `require_role`: scope `self` is intrinsic to the token subject
    (like `GET /balances`). No/invalid token is `401 TOKEN_INVALID`. An unknown `leave_type_id`
    (or an unmaterialized balance) is a byte-identical `404 RESOURCE_NOT_FOUND` from the service.
    Read-only and advisory (AD-3): no lock, no write, and no `INSUFFICIENT_BALANCE` on an overspend
    — `available_after` simply goes negative (AC11).
    """
    view = leave_requests_service.preview_leave_request(
        caller,
        leave_type_id=body.leave_type_id,
        start=body.start_date,
        end=body.end_date,
    )
    return _to_response(view)


class SubmitRequest(BaseModel):
    """The submission body — the Leave Type and the inclusive range (Story 2.6, §4.5 role any/self).

    Same shape as `PreviewRequest` and the same 366-day resource cap, applied via the shared
    validator. Everything beyond input shape — the range VALIDITY refusals and the balance decision
    — is the service's, decided under lock; this model bounds only iteration/allocation.
    """

    leave_type_id: uuid.UUID
    start_date: datetime.date
    end_date: datetime.date

    @model_validator(mode="after")
    def _span_within_bound(self) -> SubmitRequest:
        """Refuse an oversized span as malformed input (422) — the shared resource guard.

        Delegates to `_assert_span_within_bound`. An inverted range is left permissive here and
        refused by the service as `INVALID_DATE_RANGE`; the cross-year `SPANS_TWO_LEAVE_YEARS` is
        likewise the domain's, not this cap's.
        """
        _assert_span_within_bound(self.start_date, self.end_date)
        return self


class SubmitResponse(BaseModel):
    """The created Leave Request on the wire (Story 2.6, §4.5).

    The persisted row's projectable fields: `id`, `leave_type_id`, the range, the FROZEN
    `leave_days` (read from the stored value, never recomputed — AD-18), and `status`
    (`PENDING` for a managed applicant, `APPROVED` for the managerless auto-approval, FR-09).
    """

    id: uuid.UUID
    leave_type_id: uuid.UUID
    start_date: datetime.date
    end_date: datetime.date
    leave_days: int
    status: str


def _to_submit_response(view: object) -> SubmitResponse:
    """Project a `SubmitView` into the response, BY HAND (contract 2, the `balances.py` precedent).

    Typed `object` because `api/` may import neither the service dataclass nor the ORM; the
    submission service guarantees the fields are present. `leave_days` is read from the stored
    value the view carries — never recomputed here (AD-18). No `from_attributes`.
    """
    return SubmitResponse(
        id=view.id,
        leave_type_id=view.leave_type_id,
        start_date=view.start_date,
        end_date=view.end_date,
        leave_days=view.leave_days,
        status=view.status,
    )


@router.post(
    "/leave-requests",
    status_code=status.HTTP_201_CREATED,
    tags=["leave-requests"],
)
def submit_leave_request(
    body: SubmitRequest,
    caller: Actor = Depends(get_current_employee),
) -> SubmitResponse:
    """Submit a Leave Request for the caller (AC3, AC8, FR-08). Auth only, any role; scope `self`.

    `get_current_employee`, NOT `require_role`: scope `self` is intrinsic to the token subject (an
    Employee submits their OWN request — api-contracts §4.5, role any). No/invalid token is `401
    TOKEN_INVALID`. The service runs the whole submission as one transaction: the range-validity
    refusals (`INVALID_DATE_RANGE`/`PAST_DATE_RANGE`/`SPANS_TWO_LEAVE_YEARS`/`ZERO_LEAVE_DAYS`, all
    400) and `INSUFFICIENT_BALANCE` (400, decided under the balance lock) surface through the one
    domain-error handler. On success the response is `201` with the persisted row — a managerless
    applicant's is already `APPROVED` (FR-09), everyone else's `PENDING`.
    """
    view = leave_requests_service.submit_leave_request(
        caller,
        leave_type_id=body.leave_type_id,
        start=body.start_date,
        end=body.end_date,
    )
    return _to_submit_response(view)


class LeaveRequestResponse(BaseModel):
    """A Leave Request on the wire — the read/transition shape (Story 2.7, §4.5, Open Decision #2).

    The request's own fields plus the applicant (`employee_id`/`employee_name`, so a Manager's queue
    shows WHOSE request it is — AC9) and the Leave Type (`leave_type_code`/`leave_type_name`, AC5's
    "with its Leave Type"). `leave_days` is the STORED, frozen figure (read, never recomputed —
    AD-18); `status` is the current state (a transition returns the NEW state). The submit response
    stays its own minimal `SubmitResponse` — this is the fuller shape the queue and the by-id read
    need.
    """

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_type_name: str
    start_date: datetime.date
    end_date: datetime.date
    leave_days: int
    status: str


def _to_leave_request_response(view: object) -> LeaveRequestResponse:
    """Project a `LeaveRequestView` into the response, BY HAND (contract 2, the `balances.py` precedent).

    Typed `object` because `api/` may import neither the service dataclass nor the ORM; the service
    guarantees the fields are present. `leave_days` is read from the stored value the view carries —
    never recomputed here (AD-18). No `from_attributes`.
    """
    return LeaveRequestResponse(
        id=view.id,
        employee_id=view.employee_id,
        employee_name=view.employee_name,
        leave_type_id=view.leave_type_id,
        leave_type_code=view.leave_type_code,
        leave_type_name=view.leave_type_name,
        start_date=view.start_date,
        end_date=view.end_date,
        leave_days=view.leave_days,
        status=view.status,
    )


@router.post(
    "/leave-requests/{request_id}/approve",
    status_code=status.HTTP_200_OK,
    tags=["leave-requests"],
)
def approve_leave_request(
    request_id: uuid.UUID,
    caller: Actor = Depends(require_role(authz.ROLE_MANAGER)),
) -> LeaveRequestResponse:
    """Approve a Direct Report's Pending request (AC1, AC2, AC6, AC7).

    `require_role(ROLE_MANAGER)`: an Admin or Employee is refused `403 ACTION_NOT_PERMITTED` BEFORE
    the body runs (AC6, a role denial by G3 — decided before any row is read). Scope `REPORTS` then
    decides whether THIS Manager owns THIS applicant: a non-report gets a byte-identical `404`
    (AC7). A request no longer `PENDING` gets `409 TRANSITION_NOT_ALLOWED` (AC2). On success the
    days move `reserved → consumed` and the updated request is returned.
    """
    view = leave_requests_service.approve_leave_request(caller, request_id)
    return _to_leave_request_response(view)


@router.post(
    "/leave-requests/{request_id}/reject",
    status_code=status.HTTP_200_OK,
    tags=["leave-requests"],
)
def reject_leave_request(
    request_id: uuid.UUID,
    caller: Actor = Depends(require_role(authz.ROLE_MANAGER)),
) -> LeaveRequestResponse:
    """Reject a Direct Report's Pending request (AC1, AC2, AC6, AC7).

    Same gate and scope as approve: Admin/Employee → `403`, non-report → `404`, not-`PENDING` →
    `409`. On success the reservation is released (`release_reserved`) and the updated request is
    returned.
    """
    view = leave_requests_service.reject_leave_request(caller, request_id)
    return _to_leave_request_response(view)


@router.post(
    "/leave-requests/{request_id}/cancel",
    status_code=status.HTTP_200_OK,
    tags=["leave-requests"],
)
def cancel_leave_request(
    request_id: uuid.UUID,
    caller: Actor = Depends(get_current_employee),
) -> LeaveRequestResponse:
    """Cancel one's OWN Pending request (AC3). Auth only, any role; scope `self`.

    `get_current_employee`, NOT `require_role`: scope `self` is intrinsic to the applicant. A
    non-owner's request is out of scope → byte-identical `404`; a settled request → `409
    TRANSITION_NOT_ALLOWED`. On success the reservation is released and the updated request is
    returned.
    """
    view = leave_requests_service.cancel_leave_request(caller, request_id)
    return _to_leave_request_response(view)


@router.get("/leave-requests", tags=["leave-requests"])
def list_leave_requests(
    params: PageParams = Depends(),
    status_filter: LeaveStatusFilter | None = Query(default=None, alias="status"),
    caller: Actor = Depends(get_current_employee),
) -> Page[LeaveRequestResponse]:
    """List Leave Requests, scoped and paged, optionally filtered by status (AC4). Any role.

    `get_current_employee`: role `any`, scope resolved from the caller's role in the service — an
    Employee receives their own, a Manager their Direct Reports', an Admin all (a SQL predicate,
    never a post-filter). The `status` query param is validated against the four allowed values by
    `LeaveStatusFilter` (a bad value is a framework `422`); it narrows the page when present. The
    envelope is the shared `Page` — `items`/`page`/`page_size`/`total`, `page_size` clamped to the
    server maximum by `PageParams`.
    """
    views, total = leave_requests_service.list_leave_requests(
        caller,
        status=status_filter.value if status_filter is not None else None,
        limit=params.limit,
        offset=params.offset,
    )
    return Page[LeaveRequestResponse](
        items=[_to_leave_request_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.get("/leave-requests/{request_id}", tags=["leave-requests"])
def get_leave_request(
    request_id: uuid.UUID,
    caller: Actor = Depends(get_current_employee),
) -> LeaveRequestResponse:
    """Read one Leave Request by id, scoped to the caller (AC5, AC7). Any role.

    Scope resolves from the caller's role in the service; an out-of-scope id (a non-report Manager,
    a non-owner Employee) is a byte-identical `404` (AC7). Returns the request with its Leave Type,
    date range, STORED `leave_days` (AD-18, never recomputed) and current state.
    """
    view = leave_requests_service.get_leave_request(caller, request_id)
    return _to_leave_request_response(view)
