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

--- The 2xx success codes: `200` with a summary, on BOTH writes (Story 2.11) ---

Story 2.2 shipped `201` create / `204` delete / `200` list and wrote a note here saying the
api-contracts §4.3 "200 with a summary" form "is Story 2.11's, a consequence of AD-19's
forward-checked recalculation, which needs `leave_request`/`leave_balance` (Stories 2.4/2.6) to
exist. In Story 2.2 there is nothing to recalculate, so plain CRUD codes ship."

They exist now, so that note is spent and this is the change it predicted:

    POST   /api/v1/holidays        201 + HolidayResponse   →   200 + HolidayCommandResponse
    DELETE /api/v1/holidays/{id}   204, empty body         →   200 + HolidayCommandResponse

api-contracts §4.3 is binding — "these endpoints return `200` with a summary rather than failing
wholesale" — and AC4 and AC8 both name `200`. A holiday write is no longer CRUD: it recalculates
every Leave Request the change affects, and it may REFUSE a given (Employee, Leave Type) pair
while the rest of the operation commits (AD-19). There is no status code that can carry "it
worked, mostly, and here is what I declined to touch", so the summary is the body — and a
`204` with no body could not have carried it at all.

`GET /api/v1/holidays` is untouched: `200`, the `Page` envelope, any authenticated role.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends
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


class RefusedPairResponse(BaseModel):
    """One (Employee, Leave Type) pair the recalculation left ENTIRELY unchanged (AC4, AC8).

    NAMES, not bare UUIDs. AC8 requires the screen to name each refused pair, and "employee
    3f2a…-… / leave type 91bc…-…" is not something an Admin can act on. The ids travel too, so a
    client can link, but `employee_name` and `leave_type_code` are what make the refusal legible
    — the `CancellationRequest` response carries the same two fields for the same reason.

    `cause` is the vocabulary constant (`HOLIDAY_RECALCULATION`), verbatim (AD-21).
    """

    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_year: int
    cause: str


class RecalculationResponse(BaseModel):
    """What the holiday change corrected — and what it DECLINED to correct (AD-19, AC4, AC8).

    `pairs_refused` is the half that matters. AC8: the Admin "is never shown an unqualified
    success for an operation that partially refused". An empty list is the honest way to say
    "nothing was refused"; a non-empty one names every pair whose balance was left alone, so the
    Admin can act on it. The same refusals are also recorded durably in `admin_review_flag` and
    readable at `GET /admin-review-flags` — the summary is the immediate telling, the flag is the
    permanent one, because a refusal reported only in a response nobody kept is a refusal nobody
    sees.
    """

    requests_recalculated: int
    pairs_recalculated: int
    pairs_refused: list[RefusedPairResponse]


class HolidayCommandResponse(BaseModel):
    """The body BOTH writes now answer `200` with (api-contracts §4.3, Story 2.11).

    The holiday that was created or deleted, and the recalculation that ran in the same
    transaction. This replaces Story 2.2's `201 + HolidayResponse` and its `204` + empty body:
    a holiday write is a recalculation now, and a `204` cannot carry a summary.
    """

    holiday: HolidayResponse
    recalculation: RecalculationResponse


def _to_response(holiday: object) -> HolidayResponse:
    """Project a Company Holiday into the response model, by hand.

    Typed `object` because `api/` may not import the ORM `CompanyHoliday` (contract 2). It serves
    BOTH the list route (which passes ORM rows) and the two write routes (which pass the service's
    `HolidayView` snapshot) — the two duck-type identically on `{id, holiday_date, name}`.
    """
    return HolidayResponse(
        id=holiday.id,  # type: ignore[attr-defined]
        holiday_date=holiday.holiday_date,  # type: ignore[attr-defined]
        name=holiday.name,  # type: ignore[attr-defined]
    )


def _to_command_response(result: object) -> HolidayCommandResponse:
    """Project the service's `HolidayCommandResult` onto the wire, field by field.

    `result: object` — not the dataclass — because contract 2 forbids `api/` importing `services/`
    internals for typing as much as anywhere else (the `audit_entries.py` / `leave_requests.py`
    precedent). The nested `RefusedPair`s are projected one by one for the same reason.
    """
    recalculation = result.recalculation  # type: ignore[attr-defined]
    return HolidayCommandResponse(
        holiday=_to_response(result.holiday),  # type: ignore[attr-defined]
        recalculation=RecalculationResponse(
            requests_recalculated=recalculation.requests_recalculated,
            pairs_recalculated=recalculation.pairs_recalculated,
            pairs_refused=[
                RefusedPairResponse(
                    employee_id=pair.employee_id,
                    employee_name=pair.employee_name,
                    leave_type_id=pair.leave_type_id,
                    leave_type_code=pair.leave_type_code,
                    leave_year=pair.leave_year,
                    cause=pair.cause,
                )
                for pair in recalculation.pairs_refused
            ],
        ),
    )


@router.post("/holidays", tags=["holidays"])
def create_holiday(
    request: HolidayWriteRequest,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> HolidayCommandResponse:
    """Create a Company Holiday, recalculate, and return `200` + the summary (AC2–AC5, AC8).

    `200`, not `201` — the Story 2.2 status code is superseded (api-contracts §4.3). The role gate
    runs in the `_admin` dependency, before this body, so a non-Admin never reaches the create and
    no row is written (AD-14). A duplicate `holiday_date` is still refused by the service with
    `409 HOLIDAY_DATE_IN_USE`.

    A per-pair recalculation refusal does NOT fail this request (AD-19): the edit commits and the
    refused pairs are named in `recalculation.pairs_refused`, which is what AC8's screen reads.
    """
    return _to_command_response(
        holidays_service.create_holiday(
            holiday_date=request.holiday_date,
            name=request.name,
        )
    )


@router.delete("/holidays/{holiday_id}", tags=["holidays"])
def delete_holiday(
    holiday_id: uuid.UUID,
    _admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> HolidayCommandResponse:
    """Delete a Company Holiday, recalculate, and return `200` + the summary (AC2–AC5, AC8).

    `200` with a body, not `204` with none — a `204` cannot carry the summary AD-19 requires, and
    this is the path where a refusal is most likely: a DELETE makes a working day reappear, so more
    days are charged and a later, already-spent Leave Year can be driven negative.

    The role gate runs before this body — a non-Admin never reaches the delete, so no row is removed
    (AD-14). An id that names no row is `404 RESOURCE_NOT_FOUND`, raised by the service's
    load-or-`not_found()`.
    """
    return _to_command_response(holidays_service.delete_holiday(holiday_id))


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
