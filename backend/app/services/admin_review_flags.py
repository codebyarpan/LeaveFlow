"""The refusal register's READ. The only capability this module has, and the only one it may have.

Implements: AC6 (an Admin reads the recorded refusals — each naming its cause, the Employee and
Leave Type it left unchanged, and when it occurred), FR-10, AD-20.

--- This module reads. There is nowhere for a write to go, and nowhere for a RESOLVE to go ---

`services/recalculation.py` appends a flag inside the holiday command's own transaction (AD-19), and
that is the only write path. This module is not its new home: it opens no write transaction, and the
repository it calls offers no mutator to open one for (`repositories/admin_review_flag.py` exposes an
INSERT and this SELECT, and the application's database role is granted `INSERT, SELECT` on the table
and neither `UPDATE` nor `DELETE` — AD-9/AD-20, migration `0010`).

There is deliberately no `resolve_flag`, and no `PATCH`/`DELETE` route for one to serve. `FR-10`
grants the Admin only a READ. ERD §6 (GAP-4): "there is no `resolved_at` column and no endpoint
clears a flag. A flag is a permanent record that a recalculation was refused … The undefined
behavior is gone because the behavior no longer exists." AC6 restates it: "no endpoint clears a
flag". The absence is the feature — a resolve would need a `resolved_at` column, which would need an
`UPDATE` grant, which AC1 forbids.

--- The role gate is NOT here, deliberately ---

`list_admin_review_flags` takes an `actor` and does not check its role. That is not an omission: the
gate is `require_role(ROLE_ADMIN)` in `api/v1/admin_review_flags.py`, a dependency FastAPI resolves
BEFORE this function is called. G3 states the rule — "403, denied by role grant, decided before any
row is read" — and a second check here would be dead code that quietly implies the first one is
optional. The `actor` is taken because a service command takes the acting Employee; the register's
scope is `all`, so it applies no per-row predicate (see the repository's "why exempt" docstring).
This is the `services/audit.py` shape, and it is deliberately the same one.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import admin_review_flag as admin_review_flag_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee


@dataclass(frozen=True)
class AdminReviewFlagView:
    """One recorded refusal as the service hands it up — exactly the four things AC9 names.

    The CAUSE, the EMPLOYEE and LEAVE TYPE it left unchanged (by NAME and CODE, not only by id — a
    screen cannot act on a pair of UUIDs), the LEAVE YEAR it refused, and WHEN it occurred.

    Unlike `AuditEntryView`, no field here is ever `None`: `employee_id` and `leave_type_id` are both
    NOT NULL on the table (AC1 — a flag always names the pair), so the repository INNER-joins both
    and there is no SYSTEM-row equivalent to preserve. That asymmetry is the data's, not an
    oversight.

    The `api/` route projects this by hand and duck-types it as `object` — it may import neither
    `repositories/` nor this dataclass (import-linter contract 2), the `AuditEntryView` precedent.
    """

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_year: int
    cause: str
    occurred_at: datetime.datetime


def _row_to_view(row) -> AdminReviewFlagView:  # type: ignore[no-untyped-def]
    """Map one `admin_review_flag` read row (with its joined Employee and Leave Type) to a view."""
    return AdminReviewFlagView(
        id=row.id,
        employee_id=row.employee_id,
        employee_name=row.full_name,
        leave_type_id=row.leave_type_id,
        leave_type_code=row.code,
        leave_year=row.leave_year,
        cause=row.cause,
        occurred_at=row.occurred_at,
    )


def list_admin_review_flags(
    actor: Employee, *, limit: int, offset: int
) -> tuple[list[AdminReviewFlagView], int]:
    """Return one page of the recorded refusals, newest first, AND the total (AC6).

    A READ session: opened, queried, closed. It does NOT commit — there is nothing to commit, and a
    commit on a read path is how a "read" quietly becomes a write (the Story 2.5 precedent).
    `expire_on_commit=False` matches the house shape; the rows are plain columns and are already
    detached, so nothing expires when the session closes.

    The caller is an Admin — `require_role` in `api/` has already refused everyone else, before any
    row was read (AC7, G3). Scope is `all`: every refusal, unfiltered. `limit`/`offset` come from the
    clamped `PageParams` (NFR-11); the ordering and the joins are the repository's business.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = admin_review_flag_repo.list_admin_review_flags(
            session, limit=limit, offset=offset
        )
        return [_row_to_view(row) for row in rows], total
