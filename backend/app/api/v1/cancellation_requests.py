"""The `/api/v1/cancellation-requests` routes: the scoped list and the two Admin decisions (2.8).

Implements: FR-09 (an Admin decides a Cancellation Request — `approve` cancels the leave and returns
its days, `reject` changes nothing), AC5 (`GET /cancellation-requests` — scoped self/all, paged,
optionally status-filtered — the ONLY way an Admin discovers a Cancellation Request exists, since
none is announced by notification or dashboard), AC6/AC7/AC8. The raise route
(`POST /leave-requests/{id}/cancellation-requests`) lives on the leave-requests router (it is under
that path); this module holds the other three. `CancellationRequestResponse` and its hand-projector
are defined HERE and reused by the raise route.

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never
`repositories/` or `domain/` (contract 2). So it cannot import `services.cancellation.
CancellationRequestView`: the view is duck-typed `object` at the projector, exactly the
`leave_requests.py`/`balances.py` precedent. The `status` filter's accepted values come through the
service's `CANCELLATION_STATUS_VALUES` re-export (an `api → services` edge), so no status LITERAL is
typed here (`test_vocabulary_literals.py`).

--- The role gate: approve/reject are the ADMIN's (api-contracts §4.6) ---

`approve`/`reject` are `require_role(ROLE_ADMIN)` — a Cancellation Request is ADMIN-decided (NOT the
Manager, unlike a Leave Request's approve; NOT scope `reports`). A non-Admin is `403
ACTION_NOT_PERMITTED` BEFORE the body runs (AC8, a role denial by G3). `GET /cancellation-requests`
is `get_current_employee` (any role): scope `self`/`all` is resolved from the caller's role in the
service, so an Admin sees all and everyone else sees their own.
"""

from __future__ import annotations

import datetime
import enum
import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import cancellation as cancellation_service

router = APIRouter()

# The `status` filter's accepted values (AC5). Built at runtime from the service's re-exported
# `CANCELLATION_STATUS_VALUES` so no status LITERAL is typed in `api/` (`test_vocabulary_literals.
# py`) and contract 2's `api → domain` ban holds. As a FastAPI query-param type this yields a
# framework `422` on an unrecognized value (input validation), never a domain error, so
# `CODE_TO_STATUS`/vocabulary stay untouched. A member's `.value` is the status string handed to the
# service.
CancellationStatusFilter = enum.Enum(  # type: ignore[misc]
    "CancellationStatusFilter",
    {value: value for value in cancellation_service.CANCELLATION_STATUS_VALUES},
)


class CancellationRequestResponse(BaseModel):
    """A Cancellation Request on the wire (Story 2.8, §4.6, Open Decision #5).

    The CR's own `id`/`leave_request_id`/`status`, plus the applicant
    (`employee_id`/`employee_name`) and the target Leave Request summary
    (`start_date`/`end_date`/`leave_days`/`leave_type_code`/`leave_type_name`) — so the Admin screen
    renders "whose request, which leave, its dates" (AC10) without a second round-trip. `leave_days`
    is the STORED, frozen figure (read, never recomputed — AD-18); `status` is the current state (a
    decision returns the NEW state).
    """

    id: uuid.UUID
    leave_request_id: uuid.UUID
    status: str
    employee_id: uuid.UUID
    employee_name: str
    start_date: datetime.date
    end_date: datetime.date
    leave_days: int
    leave_type_code: str
    leave_type_name: str


def to_cancellation_request_response(view: object) -> CancellationRequestResponse:
    """Project a `CancellationRequestView` into the response, BY HAND (contract 2).

    Typed `object` because `api/` may import neither the service dataclass nor the ORM (the
    `balances.py`/`leave_requests.py` precedent); the service guarantees the fields are present.
    `leave_days` is read from the stored value the view carries — never recomputed here (AD-18). No
    `from_attributes`. Exported (no leading underscore) so the raise route on the leave-requests
    router reuses this one projector.
    """
    return CancellationRequestResponse(
        id=view.id,
        leave_request_id=view.leave_request_id,
        status=view.status,
        employee_id=view.employee_id,
        employee_name=view.employee_name,
        start_date=view.start_date,
        end_date=view.end_date,
        leave_days=view.leave_days,
        leave_type_code=view.leave_type_code,
        leave_type_name=view.leave_type_name,
    )


@router.get("/cancellation-requests", tags=["cancellation-requests"])
def list_cancellation_requests(
    params: PageParams = Depends(),
    status_filter: CancellationStatusFilter | None = Query(default=None, alias="status"),
    caller: Actor = Depends(get_current_employee),
) -> Page[CancellationRequestResponse]:
    """List Cancellation Requests, scoped and paged, optionally status-filtered (AC5). Any role.

    `get_current_employee`: scope resolved from the caller's role in the service — an Admin receives
    every Cancellation Request, everyone else only their own (a SQL predicate, never a post-filter).
    Without this endpoint an Admin could not discover a Cancellation Request exists (no notification,
    no dashboard entry). The `status` query param is validated against the three allowed values by
    `CancellationStatusFilter` (a bad value is a framework `422`); it narrows the page when present.
    The envelope is the shared `Page` — `items`/`page`/`page_size`/`total`, `page_size` clamped to
    the server maximum by `PageParams`.
    """
    views, total = cancellation_service.list_cancellation_requests(
        caller,
        status=status_filter.value if status_filter is not None else None,
        limit=params.limit,
        offset=params.offset,
    )
    return Page[CancellationRequestResponse](
        items=[to_cancellation_request_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.post(
    "/cancellation-requests/{cancellation_request_id}/approve",
    status_code=status.HTTP_200_OK,
    tags=["cancellation-requests"],
)
def approve_cancellation_request(
    cancellation_request_id: uuid.UUID,
    caller: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> CancellationRequestResponse:
    """Approve a Cancellation Request — cancel the leave and return its days (AC6, AC8).

    `require_role(ROLE_ADMIN)`: a non-Admin (Manager or Employee) is refused `403
    ACTION_NOT_PERMITTED` BEFORE the body runs (AC8, a role denial by G3 — decided before any row is
    read). Scope `all` then locates the CR: a nonexistent id is a `404`. On success the CR moves
    `PENDING → APPROVED`, the target Leave Request moves `APPROVED → CANCELLED`, and its days are
    returned (Available restored). A CR that is no longer `PENDING`, or a target LR no longer
    `APPROVED`, is `409 TRANSITION_NOT_ALLOWED` (the transaction rolls back).
    """
    view = cancellation_service.approve_cancellation_request(caller, cancellation_request_id)
    return to_cancellation_request_response(view)


@router.post(
    "/cancellation-requests/{cancellation_request_id}/reject",
    status_code=status.HTTP_200_OK,
    tags=["cancellation-requests"],
)
def reject_cancellation_request(
    cancellation_request_id: uuid.UUID,
    caller: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> CancellationRequestResponse:
    """Reject a Cancellation Request — the leave is untouched (AC7, AC8).

    Same gate as approve: a non-Admin is `403 ACTION_NOT_PERMITTED` before the body; a nonexistent
    id is `404`; a CR no longer `PENDING` is `409 TRANSITION_NOT_ALLOWED`. On success the CR moves
    `PENDING → REJECTED` and the target Leave Request remains `APPROVED` with its days still
    `consumed` — a rejection changes nothing about the leave itself.
    """
    view = cancellation_service.reject_cancellation_request(caller, cancellation_request_id)
    return to_cancellation_request_response(view)
