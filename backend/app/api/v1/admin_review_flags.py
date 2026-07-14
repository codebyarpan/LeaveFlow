"""The `/api/v1/admin-review-flags` route: the Admin's read of the refusal register (Story 2.11).

Implements: AC6 (`GET /api/v1/admin-review-flags` → `200`; an Admin reads the recorded refusals, each
naming its cause, the Employee and Leave Type it left unchanged, and when it occurred), AC7 (an
Employee or a Manager → `403 ACTION_NOT_PERMITTED` — only an Admin reads them: FR-10, AD-20, G3).

--- The gate, and why there is no new error code ---

`require_role(authz.ROLE_ADMIN)` is a dependency, so it runs BEFORE this body: a non-Admin is refused
with `ACTION_NOT_PERMITTED` and NO row is ever read (G3 — "denied by role grant, decided before any
row is read"; 404 stays reserved for a scope miss, AD-10). That code is already declared in
`domain/vocabulary.py` and already mapped to 403 in `main.py`. So AC7 arrives with NO new error code,
and this story changes `main.py` NOT AT ALL — the one vocabulary value it does coin
(`CAUSE_HOLIDAY_RECALCULATION`) is a response REASON, not an error code, and maps to no HTTP status.

--- There is no PATCH, no DELETE, and no resolve. That is a requirement, not an omission. ---

AC6: "no endpoint clears a flag". `FR-10` grants the Admin only a READ, and no requirement grants a
resolve — so there is no `resolved_at` column (ERD §6/GAP-4: "The undefined behavior is gone because
the behavior no longer exists"), and migration `0010` grants the app role `INSERT, SELECT` and
neither `UPDATE` nor `DELETE`. A resolve endpoint here would be refused by the database anyway. The
register is a permanent record that a recalculation was refused.

--- No filters, and no path parameter ---

The ACs name no filter, so none is shipped — the Story 2.7/2.8/2.9 precedent ("those are Story
3.1's").

And this route is deliberately NOT registered in the SM-3 scope matrix: `tests/test_scope_matrix.py`
keys on `(METHOD, path-with-parameter)`, and `GET /admin-review-flags` takes no path parameter, so it
is out of that matrix BY CONSTRUCTION — registering it would trip
`test_no_registered_entry_names_a_route_the_app_does_not_expose`. `GET /audit-entries` sits outside it
for exactly the same reason, and says so at `api/v1/audit_entries.py:21-25`.

--- What this module may import ---

`api/` may import neither `repositories/` nor `domain/` (import-linter contract 2). So the response
model is hand-projected (no `from_attributes`), the view is duck-typed as `object`, and the Admin
role constant is reached through `services/authorization` — which re-exports it precisely so a route
can name a role without importing `domain/` (and without typing the bare literal that
`test_vocabulary_literals.py` AST-forbids).
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import admin_review_flags as admin_review_flags_service
from app.services import authorization as authz

router = APIRouter()


class AdminReviewFlagResponse(BaseModel):
    """One recorded refusal on the wire (AC6, AC9).

    Everything AC9's screen must show: the CAUSE, the Employee and Leave Type the recalculation left
    unchanged — by NAME and CODE, not merely by id, because "employee 3f2a…" is not something an
    Admin can act on — the LEAVE YEAR refused, and WHEN it occurred.

    `cause` travels VERBATIM as the vocabulary string (`HOLIDAY_RECALCULATION`), UPPER_SNAKE_CASE
    (AD-21); `occurred_at` is a `TIMESTAMPTZ` rendered RFC 3339 UTC (AD-12). No field is nullable —
    a flag always names its pair.

    There is no `resolved_at` and no `resolved` boolean, because there is no resolve (AD-20).
    """

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_year: int
    cause: str
    occurred_at: datetime.datetime


def _to_response(view: object) -> AdminReviewFlagResponse:
    """Project an `AdminReviewFlagView` onto the wire model, field by field.

    `view: object` — not the dataclass — because contract 2 forbids `api/` importing `services/`
    internals for typing (the `audit_entries.py` precedent).
    """
    return AdminReviewFlagResponse(
        id=view.id,  # type: ignore[attr-defined]
        employee_id=view.employee_id,  # type: ignore[attr-defined]
        employee_name=view.employee_name,  # type: ignore[attr-defined]
        leave_type_id=view.leave_type_id,  # type: ignore[attr-defined]
        leave_type_code=view.leave_type_code,  # type: ignore[attr-defined]
        leave_year=view.leave_year,  # type: ignore[attr-defined]
        cause=view.cause,  # type: ignore[attr-defined]
        occurred_at=view.occurred_at,  # type: ignore[attr-defined]
    )


@router.get("/admin-review-flags", tags=["admin-review-flags"])
def list_admin_review_flags(
    params: PageParams = Depends(),
    admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> Page[AdminReviewFlagResponse]:
    """Return a page of the recorded refusals to an Admin, newest first (AC6). Admin-only (AC7).

    The role gate is the `require_role` dependency above, so an Employee or a Manager is refused
    `403 ACTION_NOT_PERMITTED` before this body runs and before any row is read (AC7, G3). The page
    is bounded by `PageParams` (NFR-11); the body carries the `items`/`page`/`page_size`/`total`
    envelope every list endpoint carries.
    """
    views, total = admin_review_flags_service.list_admin_review_flags(
        admin, limit=params.limit, offset=params.offset
    )
    return Page[AdminReviewFlagResponse](
        items=[_to_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
