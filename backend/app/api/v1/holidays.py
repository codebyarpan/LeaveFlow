"""The `/api/v1/holidays` endpoints: create and delete (Admin), list (any role).

Implements: FR-10, api-contracts §4.3 (Role `Admin` for the create and the delete, `any` for
the read; Scope `all` throughout), NFR-11 (the list is page-bounded), AD-12/DR-2a (a holiday
is a `DATE`, transported `YYYY-MM-DD`), AD-14 (the writes are refused by ROLE at the boundary
— the `403`, before any row is written or deleted). AC2, AC3, AC6, AC7, AC8, AC9.

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never
`repositories/` or `domain/` (contract 2). It cannot construct a `DomainError`: the service
raises `HOLIDAY_DATE_IN_USE` and the `not_found()` for an absent id, and `main.py`'s single
handler renders them. The role literal reaches here through `services.authorization`
(`authz.ROLE_ADMIN`), never `from app.domain.vocabulary import ...` — the indirection Story
1.4's role gate established.

--- Why `HolidayResponse` is projected by hand ---

The response is built field-by-field from the service's returned `CompanyHoliday`, not
`from_attributes` off the ORM row (which `api/` may not import anyway). Pydantic serialises
the `holiday_date` field — typed `datetime.date` — as `YYYY-MM-DD`, which is what delivers
AC2 on the wire.

--- The 2xx success codes (G6 — this story's to choose) ---

api-contracts fixes only non-2xx statuses; the success codes are this story's to choose
(Story 1.5 Trap 5), matched by the React `holidays.ts` hooks: `201` create, `204` delete,
`200` list — identical to departments/leave-types. This is NOT the api-contracts §4.3
"200 with a summary" form: that shape is Story 2.11's, a consequence of AD-19's forward-checked
recalculation, which needs `leave_request`/`leave_balance` (Stories 2.4/2.6) to exist. In
Story 2.2 there is nothing to recalculate, so plain CRUD codes ship.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import holidays as holidays_service

router = APIRouter()


class HolidayWriteRequest(BaseModel):
    """The body a create presents — a Company Holiday is `{holiday_date, name}` on the way in.

    `holiday_date` is a `datetime.date`: Pydantic parses the `YYYY-MM-DD` string the client
    sends into a `date`, which is exactly the DATE discipline AC2/AD-12 require.
    """

    holiday_date: datetime.date
    name: str


class HolidayResponse(BaseModel):
    """A Company Holiday as the wire sees it: `{id, holiday_date, name}` (api-contracts §4.3).

    `holiday_date` is typed `datetime.date`, so Pydantic serialises it as `YYYY-MM-DD` — the
    round-trip that carries AC2 out onto the wire.
    """

    id: uuid.UUID
    holiday_date: datetime.date
    name: str


def _to_response(holiday: object) -> HolidayResponse:
    """Project the service's returned `CompanyHoliday` into the response model, by hand.

    Typed `object` because `api/` may not import the ORM `CompanyHoliday`; the service
    guarantees every attribute is present and readable after commit (`expire_on_commit=False`).
    """
    return HolidayResponse(
        id=holiday.id,
        holiday_date=holiday.holiday_date,
        name=holiday.name,
    )


@router.post("/holidays", tags=["holidays"], status_code=status.HTTP_201_CREATED)
def create_holiday(
    request: HolidayWriteRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> HolidayResponse:
    """Create a Company Holiday and return it (AC3). Admin-only; a non-Admin is `403` (AC6).

    The role gate runs in the `_admin` dependency, before this body — a non-Admin never
    reaches the create, so no row is written (AD-14). A duplicate `holiday_date` is refused
    by the service with `409 HOLIDAY_DATE_IN_USE` (AC5).
    """
    return _to_response(
        holidays_service.create_holiday(
            holiday_date=request.holiday_date,
            name=request.name,
        )
    )


@router.delete(
    "/holidays/{holiday_id}",
    tags=["holidays"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_holiday(
    holiday_id: uuid.UUID,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> None:
    """Delete a Company Holiday, or refuse (AC6, AC8). Admin-only; a non-Admin is `403`.

    The role gate runs before this body — a non-Admin never reaches the delete, so no row is
    removed (AD-14). An id that names no row is `404 RESOURCE_NOT_FOUND`, raised by the
    service's load-or-`not_found()`. On success, `204` with no body.
    """
    holidays_service.delete_holiday(holiday_id)


@router.get("/holidays", tags=["holidays"])
def list_holidays(
    params: PageParams = Depends(),
    _caller: Actor = Depends(get_current_employee),
) -> Page[HolidayResponse]:
    """Return a page of Company Holidays to any authenticated role (AC3, AC7, AC9).

    Authentication only — `get_current_employee`, NOT `require_role`: every role reads the
    list (scope `all`). No/invalid token is `401 TOKEN_INVALID` via the empty-token path
    already in `get_current_employee`. The page is bounded by `PageParams` (NFR-11); the body
    carries the `items`, `page`, `page_size`, `total` envelope.
    """
    rows, total = holidays_service.list_holidays(params.limit, params.offset)
    return Page[HolidayResponse](
        items=[_to_response(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
