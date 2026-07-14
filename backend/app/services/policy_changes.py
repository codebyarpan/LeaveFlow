"""The policy-change log's READ. The only capability this module has, and the only one it may have.

Implements: AC7 (an Admin reads the recorded changes and their dispositions — each naming the Leave
Type, the attribute, its old and new values, and the moment), AC12, FR-06, AD-8.

--- This module reads. There is nowhere for a write to go ---

`services/leave_types.update_leave_type` appends a `policy_change` row inside the edit command's own
transaction (AD-3, AD-19), and that is the only write path. This module is not its new home: it opens
no write transaction, and the repository it calls offers no mutator to open one for
(`repositories/policy_change.py` exposes an INSERT and this SELECT, and the application's database
role is granted `INSERT, SELECT` on the table and neither `UPDATE` nor `DELETE` — AD-9/NFR-09,
migration `0011`).

A policy change is a HISTORICAL FACT: it happened, at a moment, under a disposition the Admin was
forced to choose. It is the record of WHY a balance is the number it is — and a balance whose
justification can be quietly rewritten is exactly PRD §1's "wrong figure that will be believed". So
there is no `update_policy_change`, and no `PATCH`/`DELETE` route for one to serve. The absence is the
feature.

--- The role gate is NOT here, deliberately ---

`list_policy_changes` takes an `actor` and does not check its role. That is not an omission: the gate
is `require_role(ROLE_ADMIN)` in `api/v1/policy_changes.py`, a dependency FastAPI resolves BEFORE this
function is called. G3 states the rule — "403, denied by role grant, decided before any row is read" —
and a second check here would be dead code that quietly implies the first one is optional. The `actor`
is taken because a service command takes the acting Employee; the log's scope is `all`, so it applies
no per-row predicate (see the repository's "why exempt" docstring). This is the `services/audit.py` /
`services/admin_review_flags.py` shape, and it is deliberately the same one.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import policy_change as policy_change_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee


@dataclass(frozen=True)
class PolicyChangeView:
    """One recorded policy change as the service hands it up — exactly what AC12's screen shows.

    The LEAVE TYPE it changed (by CODE, not merely by id — "leave type 3f2a…" is not something an
    Admin can read), the ATTRIBUTE that moved, its OLD and NEW values, the DISPOSITION applied, and
    WHEN.

    `old_value`/`new_value` are STRINGS, and travel to the screen exactly as stored (AD-2 — the client
    computes nothing and reformats nothing). One column pair carries an `int`, a nullable `int` and a
    `bool` (erd.md L151-152), and a removed cap is the literal string `"null"` — which is
    distinguishable from "there never was a cap", and is meant to be.

    There is NO actor field, because there is no actor COLUMN, by decision (AC1, AD-20): PRD §1
    promises attribution for Leave Request state changes, not for configuration. The `api/` route
    projects this by hand and duck-types it as `object` — it may import neither `repositories/` nor
    this dataclass (import-linter contract 2), the `AuditEntryView`/`AdminReviewFlagView` precedent.
    """

    id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_type_code: str
    attribute: str
    old_value: str
    new_value: str
    disposition: str
    occurred_at: datetime.datetime


def _row_to_view(row) -> PolicyChangeView:  # type: ignore[no-untyped-def]
    """Map one `policy_change` read row (with its joined Leave Type) to a view."""
    return PolicyChangeView(
        id=row.id,
        leave_type_id=row.leave_type_id,
        leave_type_code=row.code,
        attribute=row.attribute,
        old_value=row.old_value,
        new_value=row.new_value,
        disposition=row.disposition,
        occurred_at=row.occurred_at,
    )


def list_policy_changes(
    actor: Employee, *, limit: int, offset: int
) -> tuple[list[PolicyChangeView], int]:
    """Return one page of the recorded policy changes, newest first, AND the total (AC7).

    A READ session: opened, queried, closed. It does NOT commit — there is nothing to commit, and a
    commit on a read path is how a "read" quietly becomes a write (the Story 2.5 precedent).
    `expire_on_commit=False` matches the house shape; the rows are plain columns and are already
    detached, so nothing expires when the session closes.

    The caller is an Admin — `require_role` in `api/` has already refused everyone else, before any
    row was read (AC8, G3). Scope is `all`: every recorded change, unfiltered. `limit`/`offset` come
    from the clamped `PageParams` (NFR-11); the ordering and the join are the repository's business.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = policy_change_repo.list_policy_changes(
            session, limit=limit, offset=offset
        )
        return [_row_to_view(row) for row in rows], total
