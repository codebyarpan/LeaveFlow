"""The `/api/v1/notifications` routes: the addressee's list, their unread count, and mark-read.

Implements: FR-14, api-contracts §4.8 (`GET /notifications`, `GET /notifications/unread-count`,
`PATCH /notifications/{id}/read` — all three Role `any`, Scope `self`), AD-16, AD-10, NFR-11 (the
list is server-bounded). AC5, AC6.

--- 🚨 Role `any`: the guard is `get_current_employee`, NOT `require_role` ---

THE inversion of this story, and this is the file where getting it wrong would be invisible. Every
other read surface in this app has a role gate, and the two stories immediately before this one
(3.2 `/team`, 3.3 `/calendar`) BOTH shipped a Manager-only gate — so the muscle memory is to reach
for `require_role`. Do not. api-contracts §4.8 grants all three of these endpoints to Role `any`:
scope `self` is intrinsic to the token subject, so the guard is `get_current_employee`, exactly as
`POST /leave-requests` reasons ("Scope `self` is intrinsic to the token subject, so the guard is
`get_current_employee` (any authenticated role)").

A MANAGER is in fact the PRIMARY recipient of a notification — `REQUEST_SUBMITTED` is addressed to
them, and telling a Manager that a decision is waiting is the first half of FR-14's whole purpose.
An `EMPLOYEE`-role gate here would hide precisely the notification this feature exists to deliver.

--- And therefore: a non-addressee gets 404, never 403 ---

The G3 settlement (`api-contracts.md:37-44`) decides this the moment the role gate always admits:
"does the actor's role admit them to this endpoint at all? If no → 403 … If yes → the scope predicate
runs, and a miss is 404." Nobody is denied by role here, so the scope predicate always runs, and
someone else's Notification is a SCOPE MISS — a 404 byte-identical to a nonexistent id (AD-10). The
refusal is raised in `services/notifications.py`; this module contains no authorization logic at all,
which is the point.

--- What this module may import, and what it may not ---

`api/` imports `fastapi`, `pydantic`, `app.api.v1.*` and `app.services.*` — and NEITHER
`app.repositories` NOR `app.domain`, even under `TYPE_CHECKING` (import-linter contract 2 reasons
over the AST, not the runtime graph). So this module cannot name `Scope`, cannot import
`vocabulary`, cannot import the ORM `Notification`, and cannot import `NotificationView`. The service
view is duck-typed as `object` and projected BY HAND — the `team.py::_to_response` precedent. The
`kind` values are never typed as a `Literal` here either: `test_vocabulary_literals.py` makes that
literally unwritable under `app/` once they are exported from `domain/vocabulary.py`.

--- Route ordering ---

`GET /notifications/unread-count` is declared BEFORE any `/notifications/{id}`-shaped GET, so a
literal path segment can never be captured as a UUID path param and 422 on the parse. This story
specs no `GET /notifications/{id}`, so the hazard is latent rather than live — but the ordering costs
nothing and the next story to add one inherits it already correct.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee
from app.api.v1.pagination import Page, PageParams
from app.services import notifications as notifications_service

router = APIRouter()


class NotificationResponse(BaseModel):
    """One Notification, in the minimal shape Open Decision #5 fixes — and nothing more.

    `read_at` is `None` for an unread Notification; there is no separate `is_read` boolean, because
    the nullable timestamp already carries that fact and a second field would be a second source of
    truth for it (AD-16). `created_at` travels as the instant it is — the client renders it verbatim
    and performs no date arithmetic (AD-2's spirit; the `auditEntries` precedent).

    The Leave Request's dates, status, Leave Type and applicant are deliberately ABSENT: no
    requirement grants them here, and a Notification is not a projection of the request it concerns.
    """

    id: uuid.UUID
    kind: str
    leave_request_id: uuid.UUID
    read_at: datetime.datetime | None
    created_at: datetime.datetime


class UnreadCountResponse(BaseModel):
    """The derived unread count (AC5, AD-16).

    A single-key OBJECT rather than a bare integer (Open Decision #2). No binding artifact fixes this
    shape — deliberately: api-contracts §5 hands per-endpoint schemas to the generated OpenAPI
    document ("fixing them twice would guarantee they diverge"), so this Pydantic model IS the
    contract. An object keeps it extensible and consistent with every other response in this app
    being a JSON object; the exact key set is pinned by test so an accidental widening fails the
    build.

    The value is COUNTED, never stored (AD-16) — see `services/notifications.unread_count`.
    """

    unread: int


def _to_response(view: object) -> NotificationResponse:
    """Project the service's `NotificationView` into the response, by hand.

    Typed `object` because `api/` may not import the service's dataclass (contract 2) — the
    `team.py::_to_response` / `balances.py` precedent. The projection is one-to-one; nothing is
    derived here and nothing is dropped.
    """
    return NotificationResponse(
        id=view.id,  # type: ignore[attr-defined]
        kind=view.kind,  # type: ignore[attr-defined]
        leave_request_id=view.leave_request_id,  # type: ignore[attr-defined]
        read_at=view.read_at,  # type: ignore[attr-defined]
        created_at=view.created_at,  # type: ignore[attr-defined]
    )


@router.get("/notifications/unread-count", tags=["notifications"])
def get_unread_count(
    actor: Actor = Depends(get_current_employee),
) -> UnreadCountResponse:
    """Return the caller's unread Notification count (AC5).

    Declared BEFORE any `{id}`-shaped GET so `unread-count` is never parsed as a path parameter.
    Role `any` — the guard is `get_current_employee`, and the scope (`self`) is the token subject's,
    applied as a SQL predicate in the service. The count is `COUNT(*) WHERE read_at IS NULL`, derived
    on every call and NEVER stored (AD-16).

    No path parameter ⇒ OUT of the SM-3 scope matrix by construction (`tests/test_scope_matrix.py`
    enumerates only templates carrying a `{`), exactly like `GET /leave-requests` and `GET /team`.
    """
    return UnreadCountResponse(unread=notifications_service.unread_count(actor))


@router.get("/notifications", tags=["notifications"])
def list_notifications(
    params: PageParams = Depends(),
    actor: Actor = Depends(get_current_employee),
) -> Page[NotificationResponse]:
    """Return a page of the caller's OWN Notifications, newest first (AC5).

    Role `any`, scope `self`: an Employee, a Manager and an Admin each see exactly their own
    notifications and nobody else's — the predicate is in the SQL, never a post-filter (AD-10,
    NFR-04). A Manager sees the `REQUEST_SUBMITTED` notifications addressed to them; that is the
    point of the endpoint, not an edge case.

    The page is bounded by `PageParams` (NFR-11); the body carries the `items`/`page`/`page_size`/
    `total` envelope. No path parameter ⇒ out of the SM-3 matrix by construction.
    """
    views, total = notifications_service.list_notifications(
        params.limit, params.offset, actor
    )
    return Page[NotificationResponse](
        items=[_to_response(view) for view in views],
        page=params.page,
        page_size=params.page_size,
        total=total,
    )


@router.patch("/notifications/{notification_id}/read", tags=["notifications"])
def mark_notification_read(
    notification_id: uuid.UUID,
    actor: Actor = Depends(get_current_employee),
) -> None:
    """Mark one of the caller's own Notifications read — idempotently (AC6).

    `200`. Calling it TWICE is a success both times and the unread count decrements exactly ONCE:
    the second call finds `read_at` already set and succeeds as a no-op. It is NOT a 409 — that
    reflex (a guarded UPDATE matching zero rows ⇒ `TRANSITION_NOT_ALLOWED`) is right everywhere else
    in this codebase and wrong here; `services/notifications.mark_notification_read` states why at
    length.

    No Employee other than the ADDRESSEE may mark it read (AC6). A non-addressee — and a nonexistent
    id — receives a byte-identical `404 RESOURCE_NOT_FOUND`, never a 403 (AD-10, G3; the role gate
    admits everyone here, so the refusal can only come from the scope predicate).

    🚨 This route HAS a path parameter, so it IS registered in the SM-3 scope matrix
    (`tests/test_scope_matrix.py`, `{Scope.SELF}`) — the first guard-file entry Epic 3 has needed
    (3.1, 3.2 and 3.3 each shipped none). It is deliberately NOT `include_in_schema=False`: hiding it
    would let it escape that completeness gate, which is the one thing the gate exists to prevent.
    """
    notifications_service.mark_notification_read(actor, notification_id)
