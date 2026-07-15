"""The addressee's three notification capabilities: list, count unread, mark read (Story 3.4).

Implements: AC5 (both reads return ONLY the caller's own Notifications; the unread count is
`COUNT(*) WHERE read_at IS NULL` and is never stored), AC6 (mark-read is idempotent, and permitted
ONLY to the addressee), FR-14, AD-16, AD-10, AD-3.

--- This module does NOT write notifications. The transitions do ---

AD-16's third clause: "the service that performs a transition is the service that writes its
Notification, INSIDE that transition's transaction … no OTHER service writes notifications." So the
two INSERT sites are `submit_leave_request` and `_decide`, both in `services/leave_requests.py`,
each riding a transaction that already exists (AD-3). This module never inserts one. Its only write
is `mark_notification_read`, which moves `read_at` on a notification that already exists — a
different thing entirely, and the ONE write transaction this module opens.

--- 🚨 Role `any`, scope `self` — and therefore NO role check here, and a 404 rather than a 403 ---

api-contracts §4.8 (`:215-223`) grants all three notification endpoints to Role `any`, Scope `self`.
This inverts the app's habit twice over, and both inversions live in this file:

1. **There is no role check, here or in the route.** The guard is `get_current_employee` (any
   authenticated caller), NOT `require_role`. A role check in this module would be dead code that
   quietly implies the gate is optional — the `services/audit.py` posture, inverted: there, the
   Admin gate is real and lives in `api/`; here, there is no gate to live anywhere. Stories 3.2 and
   3.3 each shipped a Manager-ONLY inversion, so the muscle memory points exactly the wrong way.
   Note WHO the primary recipient is: a MANAGER, since `REQUEST_SUBMITTED` is addressed to them.
   Gating this on the `EMPLOYEE` role would hide the very notification FR-14 exists to deliver.

2. **A non-addressee gets 404, not 403.** This follows from (1) by the G3 settlement
   (`api-contracts.md:37-44`): "does the actor's role admit them to this endpoint at all? If no →
   403 … If YES → the scope predicate runs, and a miss is 404." The role gate here always admits, so
   the scope predicate always runs, so a Notification belonging to someone else is a SCOPE MISS —
   byte-identical to a nonexistent id (AD-10). 403 `ACTION_NOT_PERMITTED` means "denied by role
   grant, decided before any row is read", which cannot happen on an endpoint that denies no role.

--- The one scope, decided HERE ---

A Notification is intrinsically scope `self` — it has exactly one addressee, and only they may read
or mark it. That single scope is decided in this module and nowhere else: `api/` may not import
`Scope` at all (import-linter contract 2 forbids `api → repositories`, even under `TYPE_CHECKING`),
and the repository takes no `scope` parameter because there is no second scope to pass. The
predicate itself is the direct column compare `recipient_employee_id == actor.id` (Open Decision #3;
defended in the repository's module docstring).
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import notification as notification_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.services import authorization as authz


@dataclass(frozen=True)
class NotificationView:
    """One Notification as the service hands it up — the minimal shape (Open Decision #5).

    Exactly this table's own columns: the row's `id` (the handle `PATCH …/read` needs), the `kind`
    discriminator the UI renders as a sentence, the `leave_request_id` it concerns, the nullable
    `read_at` (NULL ⇒ unread — there is no separate `is_read` flag, because the timestamp already
    carries the fact), and `created_at`.

    Deliberately NOT carried: the Leave Request's dates, its status, its Leave Type, the applicant's
    name. No AC asks a Notification to reproduce the request — AC7 asks only that a count is visible
    and that opening one marks it read — and each of those fields would be a disclosure widening no
    requirement grants, on a read whose scope is the addressee alone. It also keeps the read a single
    table with no join, so the page query and the count query cannot disagree and `total` cannot lie
    (3.1's Landmine 3).

    The `api/` route projects this by hand and duck-types it as `object` — it may import neither
    `repositories/` nor this dataclass (contract 2), the `AuditEntryView`/`LeaveRequestView` precedent.
    """

    id: uuid.UUID
    kind: str
    leave_request_id: uuid.UUID
    read_at: datetime.datetime | None
    created_at: datetime.datetime


def _row_to_view(row) -> NotificationView:  # type: ignore[no-untyped-def]
    """Map one `notification` read row to a `NotificationView` — the columns, one-to-one."""
    return NotificationView(
        id=row.id,
        kind=row.kind,
        leave_request_id=row.leave_request_id,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def _now() -> datetime.datetime:
    """The current instant (UTC), from the shell clock (AD-1) — a `read_at` stamp.

    The clock lives in the service shell, never in a repository: `mark_read` takes the instant as a
    parameter rather than calling `datetime.now()` itself, exactly as `insert_audit_entry` does.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def list_notifications(
    limit: int, offset: int, actor: Employee
) -> tuple[list[NotificationView], int]:
    """Return one page of the caller's OWN Notifications AND the full count (AC5).

    The small-read-module shape (`services/team.py`, `services/audit.py`): one READ session, opened,
    queried, closed, never committed — a commit on a read path is how a "read" quietly becomes a
    write (the 2.5 precedent).

    Scope `self`, applied as a SQL predicate in the repository (AD-10, NFR-04) — so an Employee, a
    Manager and an Admin all see exactly their own notifications and nobody else's. Ordering
    (`created_at DESC, id DESC`, with the load-bearing `id` tiebreak) and the single-round-trip
    `(rows, total)` are the repository's business; the `api/` route assembles the `Page` envelope
    (NFR-11) from what this returns.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = notification_repo.list_notifications(
            session, actor, limit=limit, offset=offset
        )
        return [_row_to_view(row) for row in rows], total


def unread_count(actor: Employee) -> int:
    """Return the caller's unread Notification count — DERIVED, never stored (AC5, AD-16).

    `COUNT(*) WHERE recipient_employee_id = :actor AND read_at IS NULL`, computed on every call. AD-16
    forbids storing it, and nothing here caches it: a stored count is a second source of truth for a
    fact the rows already carry, and the first thing it does is drift. The PARTIAL index
    `ix_notification_recipient_unread` exists to make exactly this query cheap — the index and this
    count were designed as one thing, which is why the index carries the `read_at IS NULL` predicate
    rather than being a plain index on the recipient.

    A read session; no commit.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return notification_repo.count_unread(session, actor)


def mark_notification_read(actor: Employee, notification_id: uuid.UUID) -> None:
    """Mark one of the caller's OWN Notifications read — idempotently (AC6, AD-16).

    ONE write transaction (AD-3), opened and committed here. In order, and the order IS the logic:

      1. **Locate the row UNDER THE ACTOR'S SCOPE** (`get_notification`). `None` ⇒ `authz.not_found()`
         — a 404 that is byte-identical for a nonexistent id AND for a Notification addressed to
         somebody else (AD-10), so no one can probe which notifications exist. 🚨 NOT a 403: the role
         gate admits every authenticated caller here (role `any`), so by G3 the scope predicate runs
         and a miss is a 404. No Employee other than the addressee may mark it read (AC6), and this is
         the step that enforces it.
      2. **The guarded UPDATE** (`mark_read`): `SET read_at = now WHERE id = :id AND recipient = :actor
         AND read_at IS NULL`.
      3. **`rowcount == 0` ⇒ SUCCESS (200), not a conflict.** 🚨 This is the deliberate departure from
         the AD-4 reflex, and it is stated here so a reviewer does not read it as a bug. EVERY other
         guarded UPDATE in this codebase treats a zero rowcount as a lost race and raises `409
         TRANSITION_NOT_ALLOWED`. Here it cannot mean that: step 1 has ALREADY ruled out "not yours"
         and "nonexistent", so the only remaining cause is that `read_at` was already set — the
         notification was ALREADY READ. And "already read" is precisely what a SECOND `PATCH` is
         supposed to be: AC6 requires marking read to be IDEMPOTENT, and that "the count decrements
         ONCE". A 409 there would make the second call an error, which is the opposite of idempotent.

    Returns `None`: the endpoint answers 200 with no body content of its own, and the client refetches
    the count. Nothing is returned that a caller could mistake for a state machine.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        row = notification_repo.get_notification(session, actor, notification_id)
        if row is None:
            authz.not_found()

        # A rowcount of 0 here means ALREADY READ (step 1 excluded every other cause) — a no-op that
        # SUCCEEDS. It is deliberately not inspected: both outcomes are a 200, and branching on it
        # would only invite a future reader to "fix" one branch into a 409.
        notification_repo.mark_read(
            session,
            notification_id=notification_id,
            recipient_employee_id=actor.id,
            read_at=_now(),
        )
        session.commit()
