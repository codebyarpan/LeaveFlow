"""The `/api/v1/policy-changes` route: the Admin's read of the policy-change log (Story 2.12).

Implements: AC7 (`GET /api/v1/policy-changes` → `200`; an Admin reads the recorded changes and their
dispositions — api-contracts §4.3), AC8 (an Employee or a Manager → `403 ACTION_NOT_PERMITTED` — only
an Admin reads them: G3), AC12 (the screen shows each change, its old and new value, and the
disposition applied).

--- The gate, and why there is no new error code ---

`require_role(authz.ROLE_ADMIN)` is a dependency, so it runs BEFORE this body: a non-Admin is refused
with `ACTION_NOT_PERMITTED` and NO row is ever read (G3 — "denied by role grant, decided before any
row is read"; 404 stays reserved for a scope miss, AD-10). That code is already declared in
`domain/vocabulary.py` and already mapped to 403 in `main.py`. So AC8 arrives with NO new error code.

(The story DOES touch `main.py`, unlike Story 2.11 — but for `POLICY_DISPOSITION_REQUIRED`, which is
`PATCH /leave-types/{id}`'s refusal, not this route's. `CAUSE_POLICY_RECALCULATION` and the two
`DISPOSITION_*` values are enumerated strings, not error codes, and map to no status.)

--- There is no PATCH, no DELETE, and no edit. That is a requirement, not an omission. ---

A policy change is a HISTORICAL FACT — the record of WHY a balance is the number it is. Migration
`0011` grants the app role `INSERT, SELECT` on `policy_change` and neither `UPDATE` nor `DELETE`, so a
write against a recorded change is refused BY POSTGRES even if someone wrote the route. The log is the
`rollover_run` / `admin_review_flag` shape: append-only, and read whole.

--- No filters, and no path parameter ---

The ACs name no filter, so none is shipped — the Story 2.7/2.8/2.9/2.11 precedent ("those are Story
3.1's").

And this route is deliberately NOT registered in the SM-3 scope matrix: `tests/test_scope_matrix.py`
keys on `(METHOD, path-with-parameter)`, and `GET /policy-changes` takes no path parameter, so it is
out of that matrix BY CONSTRUCTION — registering it would trip
`test_no_registered_entry_names_a_route_the_app_does_not_expose`. `GET /audit-entries` and `GET
/admin-review-flags` sit outside it for exactly the same reason. (`PATCH /leave-types/{id}` DOES carry
a path parameter, and IS registered — see `api/v1/leave_types.py`.)

--- What this module may import ---

`api/` may import neither `repositories/` nor `domain/` (import-linter contract 2). So the response
model is hand-projected (no `from_attributes`), the view is duck-typed as `object`, and the Admin role
constant is reached through `services/authorization` — which re-exports it precisely so a route can
name a role without importing `domain/` (and without typing the bare literal that
`test_vocabulary_literals.py` AST-forbids).
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import authorization as authz
from app.services import policy_changes as policy_changes_service

router = APIRouter()


class PolicyChangeResponse(BaseModel):
    """One recorded policy change on the wire (AC7, AC12).

    Everything AC12's screen must show: the LEAVE TYPE whose policy changed — by CODE, not merely by
    id, because "leave type 3f2a…" is not something an Admin can read — the ATTRIBUTE that moved, its
    OLD and NEW values, the DISPOSITION applied, and WHEN it occurred.

    `old_value` and `new_value` are STRINGS. One column pair on `policy_change` carries an `int`
    (`annual_entitlement`), a nullable `int` (`carry_forward_cap`) and a `bool` (`carries_forward`) —
    erd.md types them TEXT for that reason — and a removed cap travels as the literal string `"null"`,
    which is deliberately distinguishable from "there never was a cap". The screen renders them as
    received (AD-2); it parses nothing.

    `disposition` travels VERBATIM as the vocabulary string (`RECALCULATE` / `PRESERVE`),
    UPPER_SNAKE_CASE (AD-21); `occurred_at` is a `TIMESTAMPTZ` rendered RFC 3339 UTC (AD-12). No field
    is nullable.

    There is NO actor field, because there is no actor COLUMN, BY DECISION (AC1, AD-20): PRD §1
    promises attribution for Leave Request state changes, and this is not one.
    """

    id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_type_code: str
    attribute: str
    old_value: str
    new_value: str
    disposition: str
    occurred_at: datetime.datetime


def _to_response(view: object) -> PolicyChangeResponse:
    """Project a `PolicyChangeView` onto the wire model, field by field.

    `view: object` — not the dataclass — because contract 2 forbids `api/` importing `services/`
    internals for typing (the `audit_entries.py` / `admin_review_flags.py` precedent).
    """
    return PolicyChangeResponse(
        id=view.id,  # type: ignore[attr-defined]
        leave_type_id=view.leave_type_id,  # type: ignore[attr-defined]
        leave_type_code=view.leave_type_code,  # type: ignore[attr-defined]
        attribute=view.attribute,  # type: ignore[attr-defined]
        old_value=view.old_value,  # type: ignore[attr-defined]
        new_value=view.new_value,  # type: ignore[attr-defined]
        disposition=view.disposition,  # type: ignore[attr-defined]
        occurred_at=view.occurred_at,  # type: ignore[attr-defined]
    )


@router.get("/policy-changes", tags=["policy-changes"])
def list_policy_changes(
    params: PageParams = Depends(),
    admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> Page[PolicyChangeResponse]:
    """Return a page of the recorded policy changes to an Admin, newest first (AC7). Admin-only (AC8).

    The role gate is the `require_role` dependency above, so an Employee or a Manager is refused `403
    ACTION_NOT_PERMITTED` before this body runs and before any row is read (AC8, G3). The page is
    bounded by `PageParams` (NFR-11); the body carries the `items`/`page`/`page_size`/`total` envelope
    every list endpoint carries.
    """
    views, total = policy_changes_service.list_policy_changes(
        admin, limit=params.limit, offset=params.offset
    )
    return Page[PolicyChangeResponse](
        items=[_to_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
