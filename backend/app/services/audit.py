"""The audit trail's READ. The only capability this module has, and the only one it should ever have.

Implements: AC1 (an Admin reads the trail — every entry names its subject, the transition, the actor
and the timestamp), FR-16, DR-13.

--- This module reads. It does not write, and there is nowhere for a write to go ---

Six call sites across `services/leave_requests.py` and `services/cancellation.py` already append
exactly one `audit_entry` row per state transition, inside that transition's own transaction (AD-8).
Story 2.9 changed NONE of them, and this module is not their new home: it opens no write
transaction, and the repository it calls offers no mutator to open one for (`repositories/
audit_entry.py` exposes an INSERT and this SELECT, and the application's database role is granted
`INSERT, SELECT` on the table and neither `UPDATE` nor `DELETE` — AD-9, migration `0008`).

--- The role gate is NOT here, deliberately ---

`list_audit_entries` takes an `actor` and does not check its role. That is not an omission: the gate
is `require_role(ROLE_ADMIN)` in `api/v1/audit_entries.py`, a dependency FastAPI resolves BEFORE this
function is called. G3 states the rule — "403, denied by role grant, decided before any row is read"
— and a second check here would be dead code that quietly implies the first one is optional. The
`actor` is taken because a service command takes the acting Employee; the trail's scope is `all`, so
it applies no per-row predicate (see the repository's "why exempt" docstring).
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import audit_entry as audit_entry_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee


@dataclass(frozen=True)
class AuditEntryView:
    """One recorded transition as the service hands it up — exactly the four things AC1 names.

    The SUBJECT (`subject_type` + the polymorphic `subject_id`), the TRANSITION (`from_state` →
    `to_state`; `from_state` is `None` for a creation, which has no prior state), the ACTOR
    (`actor_type`, `actor_id`, `actor_name`) and the TIMESTAMP (`occurred_at`), plus the `reason`
    that names WHY and the row's own `id`.

    `actor_name` is `None` FOR A SYSTEM ROW, AND IT STAYS `None`. The managerless auto-approval has
    no human actor — `actor_type = 'SYSTEM'`, `actor_id IS NULL`, enforced by a biconditional CHECK
    — and AC6's requirement is that "no human approver is fabricated". Substituting `"System"`,
    `"—"`, `"(automatic)"` or any other placeholder HERE would launder a fact about the data into a
    display string one layer too early, and a later reader could no longer tell an automatic
    approval from an approver whose name happened to be "System". A display string is the frontend's
    business; the absence of a name is the trail's.

    The `api/` route projects this by hand and duck-types it as `object` — it may import neither
    `repositories/` nor this dataclass (import-linter contract 2), the `LeaveRequestView` precedent.
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


def _row_to_view(row) -> AuditEntryView:  # type: ignore[no-untyped-def]
    """Map one `audit_entry` read row (with the outer-joined actor) to an `AuditEntryView`.

    `row.full_name` arrives as `None` for a SYSTEM row — the LEFT OUTER JOIN matched no `employee`
    because `actor_id` is NULL — and it is passed straight through. Nothing here invents a name.
    """
    return AuditEntryView(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        from_state=row.from_state,
        to_state=row.to_state,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        actor_name=row.full_name,
        reason=row.reason,
        occurred_at=row.occurred_at,
    )


def list_audit_entries(
    actor: Employee, *, limit: int, offset: int
) -> tuple[list[AuditEntryView], int]:
    """Return one page of the audit trail, newest first, AND the total (AC1).

    A READ session: opened, queried, closed. It does NOT commit — there is nothing to commit, and a
    commit on a read path is how a "read" quietly becomes a write (the Story 2.5 precedent).
    `expire_on_commit=False` matches the house shape; the rows are plain columns and are already
    detached, so nothing expires when the session closes.

    The caller is an Admin — `require_role` in `api/` has already refused everyone else, before any
    row was read (G3). Scope is `all`: the whole trail, unfiltered, which is what makes it an audit
    trail rather than a personalized feed. `limit`/`offset` come from the clamped `PageParams`
    (NFR-11); ordering and the SYSTEM-row-preserving outer join are the repository's business.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = audit_entry_repo.list_audit_entries(
            session, limit=limit, offset=offset
        )
        return [_row_to_view(row) for row in rows], total
