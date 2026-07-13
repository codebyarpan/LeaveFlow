"""The `/api/v1/balances` and `/api/v1/employees/{id}/balances` reads (Story 2.4, FR-07/FR-03).

Implements: FR-07 (`GET /balances` — the caller's own balances: `available` primary, with
`reserved`/`consumed`), FR-03 / AD-10 (`GET /employees/{id}/balances` — a Manager sees only
Direct Reports, an Admin anyone; a scope miss is a byte-identical 404), DR-3 / AC10 (`available`
is DERIVED here at the projection, `accrued − consumed − reserved`, never read from a column).
AC5, AC6.

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies` only — never `repositories/`
or `domain/` (contract 2). It cannot construct a `DomainError`: the service raises `not_found()`
(404) for a scope miss, and the role gate raises `403 ACTION_NOT_PERMITTED`; `main.py`'s single
handler renders them. Role literals reach here through `services.authorization` (`authz.ROLE_*`).

--- Why `available` is computed HERE ---

`available = accrued − consumed − reserved` is derived at THIS projection, from the three stored
quantities the read service hands up (DR-3, AD-5): no column, model, migration or lower layer
computes or stores it. The response carries `available` (primary), `reserved` and `consumed` —
the three the contract names (api-contracts §4.4); `accrued` is not surfaced. Balances are a
bounded set (one per Leave Type), so both endpoints return a plain list, NOT the `Page` envelope.

--- The 2xx success code (G6) ---

`200` for both reads, matching the React `balances.ts` hook.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee, require_role
from app.services import authorization as authz
from app.services import balance_reads as balance_reads_service

router = APIRouter()


class BalanceResponse(BaseModel):
    """One Leave Type's balance as the wire sees it (api-contracts §4.4).

    `available` is primary and DERIVED (`accrued − consumed − reserved`); `reserved` and
    `consumed` travel alongside. Whole-day integers. `accrued` is not surfaced (the contract
    names only the three).
    """

    leave_type_code: str
    leave_type_name: str
    available: int
    reserved: int
    consumed: int


def _to_response(balance: object) -> BalanceResponse:
    """Project a `BalanceView` into the response, DERIVING `available` here (DR-3, AC10).

    Typed `object` because `api/` may not import the service's dataclass or the ORM model; the
    read service guarantees the three stored quantities are present. `available` is computed at
    THIS projection from `accrued`/`consumed`/`reserved` — never read from a stored column.
    """
    available = balance.accrued - balance.consumed - balance.reserved
    return BalanceResponse(
        leave_type_code=balance.leave_type_code,
        leave_type_name=balance.leave_type_name,
        available=available,
        reserved=balance.reserved,
        consumed=balance.consumed,
    )


@router.get("/balances", tags=["balances"])
def list_own_balances(
    caller: Actor = Depends(get_current_employee),
) -> list[BalanceResponse]:
    """Return the caller's own current-year balances (AC5, FR-07). Auth only, any role.

    `get_current_employee`, NOT `require_role`: scope `self` is intrinsic to the token subject
    (like `GET /me`). No/invalid token is `401 TOKEN_INVALID` via the empty-token path. Each
    Leave Type returns `available` (primary), `reserved`, `consumed`; `available` is derived.
    """
    return [_to_response(view) for view in balance_reads_service.list_own_balances(caller)]


@router.get("/employees/{employee_id}/balances", tags=["balances"])
def list_employee_balances(
    employee_id: uuid.UUID,
    actor: Actor = Depends(require_role(authz.ROLE_MANAGER, authz.ROLE_ADMIN)),
) -> list[BalanceResponse]:
    """Return another Employee's current-year balances, scoped (AC6, FR-03, AD-10).

    Manager+Admin only — an Employee is `403 ACTION_NOT_PERMITTED`, decided in the `require_role`
    dependency before this body (no row read). The service resolves scope from the actor's role
    (Admin → all, Manager → reports) and resolves the target Employee under it first: a Manager
    naming a non-report, or any nonexistent id, is a byte-identical `404 RESOURCE_NOT_FOUND`.
    """
    return [
        _to_response(view)
        for view in balance_reads_service.list_employee_balances(employee_id, actor)
    ]
