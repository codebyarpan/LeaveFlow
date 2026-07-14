"""The `/api/v1/audit-entries` route: the Admin's read of the append-only trail (Story 2.9).

Implements: AC1 (`GET /api/v1/audit-entries` → 200; every entry names its subject, the transition,
the actor and the timestamp), AC2 (an Employee or a Manager → `403 ACTION_NOT_PERMITTED` — full
audit-log read access is the Admin's alone: FR-16, DR-13, G3).

--- The gate, and why there is no new error code ---

`require_role(authz.ROLE_ADMIN)` is a dependency, so it runs BEFORE this body: a non-Admin is
refused with `ACTION_NOT_PERMITTED` and NO row is ever read (G3 — "denied by role grant, decided
before any row is read"; 404 stays reserved for a scope miss, AD-10). That code is already declared
in `domain/vocabulary.py` and already mapped to 403 in `main.py`. This story coins NO vocabulary and
NO error code, and changes `main.py` not at all.

--- No filters, and no path parameter ---

The ACs name no filter, so none is shipped — the Story 2.7 and 2.8 precedent ("those are Story
3.1's"). A `subject_type` filter would additionally drag in the AD-21 runtime-enum machinery to
avoid typing a bare literal, all for a criterion no AC states.

And this route is deliberately NOT registered in the SM-3 scope matrix: `tests/test_scope_matrix.py`
keys on `(METHOD, path-with-parameter)`, and `GET /audit-entries` takes no path parameter, so it is
out of that matrix BY CONSTRUCTION — registering it would trip
`test_no_registered_entry_names_a_route_the_app_does_not_expose`. `GET /leave-requests` and
`GET /cancellation-requests` sit outside it for the same reason.

--- What this module may import ---

`api/` may import neither `repositories/` nor `domain/` (import-linter contract 2). So the response
model is hand-projected (no `from_attributes`), the view is duck-typed as `object`, and the Admin
role constant is reached through `services/authorization` — which re-exports it precisely so a route
can name a role without importing `domain/` (and without typing the bare literal that
`test_vocabulary_literals.py` AST-forbids). `PageParams`/`Page[T]` are the shared `api/` pagination:
the server-side bound already exists (NFR-11) and is not re-implemented here.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, require_role
from app.api.v1.pagination import Page, PageParams
from app.services import audit as audit_service
from app.services import authorization as authz

router = APIRouter()


class AuditEntryResponse(BaseModel):
    """One recorded state transition on the wire (AC1, api-contracts §4.9).

    The four things AC1 requires an entry to name — its SUBJECT (`subject_type` + the polymorphic
    `subject_id`), the TRANSITION (`from_state` → `to_state`), the ACTOR and the TIMESTAMP — plus
    the `reason`. Vocabulary values travel VERBATIM, UPPER_SNAKE_CASE (AD-21); `occurred_at` is a
    `TIMESTAMPTZ` rendered RFC 3339 UTC (AD-12).

    `from_state` is `null` for a creation: a submitted request had no prior state.

    `actor_id` AND `actor_name` are BOTH `null` when `actor_type` is `SYSTEM` — the managerless
    auto-approval (`reason: AUTO_APPROVED_NO_MANAGER`). That is AC6 on the wire: no human approver
    is fabricated, not even as a display string. A client that wants to show something for those
    rows renders `actor_type`, which says `SYSTEM` — it does not get a name here, because there was
    no person.
    """

    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    from_state: str | None
    to_state: str
    actor_type: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    reason: str
    occurred_at: datetime.datetime


def _to_audit_entry_response(view: object) -> AuditEntryResponse:
    """Project an `AuditEntryView` onto the wire model, field by field.

    `view: object` — not the dataclass — because contract 2 forbids `api → services`' internals
    being imported for typing here as much as anywhere else (the `leave_requests.py` /
    `cancellation_requests.py` precedent). `actor_name` is copied as-is, including its `None`.
    """
    return AuditEntryResponse(
        id=view.id,  # type: ignore[attr-defined]
        subject_type=view.subject_type,  # type: ignore[attr-defined]
        subject_id=view.subject_id,  # type: ignore[attr-defined]
        from_state=view.from_state,  # type: ignore[attr-defined]
        to_state=view.to_state,  # type: ignore[attr-defined]
        actor_type=view.actor_type,  # type: ignore[attr-defined]
        actor_id=view.actor_id,  # type: ignore[attr-defined]
        actor_name=view.actor_name,  # type: ignore[attr-defined]
        reason=view.reason,  # type: ignore[attr-defined]
        occurred_at=view.occurred_at,  # type: ignore[attr-defined]
    )


@router.get("/audit-entries", tags=["audit-entries"])
def list_audit_entries(
    params: PageParams = Depends(),
    admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
) -> Page[AuditEntryResponse]:
    """Return a page of the audit trail to an Admin, newest first (AC1). Admin-only (AC2).

    The role gate is the `require_role` dependency above, so an Employee or a Manager is refused
    `403 ACTION_NOT_PERMITTED` before this body runs and before any row is read (AC2, G3). The page
    is bounded by `PageParams` (NFR-11); the body carries the `items`/`page`/`page_size`/`total`
    envelope every list endpoint carries.
    """
    views, total = audit_service.list_audit_entries(
        admin, limit=params.limit, offset=params.offset
    )
    return Page[AuditEntryResponse](
        items=[_to_audit_entry_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
