"""Audit Entry persistence — INSERT and SELECT only, and now a GRANT says so (AD-8/AD-9).

Implements: AC2 of Story 2.6 (the append-only audit trail) and AC1/AC3 of Story 2.9 (the Admin's
read of it). This module exposes exactly two functions — an INSERT and a SELECT — and NO update and
NO delete method for `audit_entry`, ever. AD-8's own words: "no repository exposes an update or
delete method for either table." SM-6.

--- Append-only is now enforced in TWO places, and the second one is the real one (Story 2.9) ---

Through Story 2.8 this guarantee lived only HERE, in the method surface, because the codebase ran a
SINGLE Postgres role that OWNED `audit_entry` — and an owner cannot be denied on its own table, so
a `REVOKE UPDATE, DELETE` against it was a no-op (the Story 2.6 Decision Point). Story 2.9 closed
that: migration `0008` provisions a non-owner APPLICATION role and grants it `INSERT, SELECT` on
this table and NOTHING ELSE. `repositories/engine.py` connects as that role, so an `UPDATE` or
`DELETE` against the trail is now refused BY POSTGRES (`InsufficientPrivilege`), not merely absent
from this file.

Both layers stay. The GRANT is the guarantee (AC3); this method surface — asserted by
`tests/integration/test_leave_request_submit.py` — is what stops a well-meaning future story from
WRITING the update method in the first place, which is a better failure than discovering it at
runtime. Add one here and you have not defeated the database; you have only moved the error later.

--- One row per transition, same transaction (AD-8) ---

`insert_audit_entry` `flush`es but does NOT commit: the submission command writes exactly one
audit row in the SAME transaction as the `leave_request` insert and the balance mutation, so a
rolled-back submit leaves neither a request row nor an audit row. `from_state=None` records a
creation (there is no prior state). It is a write governed by the command's transaction, not a
getter — no `actor` scoping applies.
"""

import datetime
import uuid

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.repositories.models import AuditEntry, Employee

# Plain COLUMNS, never the ORM entity: a `Row` of columns is already detached, so nothing
# lazy-loads or expires when the read session closes (the `list_leave_requests` shape).
# `Employee.full_name` rides along from the OUTER join — NULL for a SYSTEM row, which is the
# point, not an oversight (see `list_audit_entries`).
_READ_COLUMNS = (
    AuditEntry.id,
    AuditEntry.subject_type,
    AuditEntry.subject_id,
    AuditEntry.from_state,
    AuditEntry.to_state,
    AuditEntry.actor_type,
    AuditEntry.actor_id,
    AuditEntry.reason,
    AuditEntry.occurred_at,
    Employee.full_name,
)


def insert_audit_entry(
    session: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    from_state: str | None,
    to_state: str,
    actor_type: str,
    actor_id: uuid.UUID | None,
    reason: str,
    occurred_at: datetime.datetime,
) -> None:
    """Append one audit row for a state transition, in the caller's transaction (AC2, AD-8).

    Exactly one row per transition; `flush` without commit keeps it atomic with the transition it
    records. `from_state=None` for a creation (`NULL → PENDING`/`APPROVED`); `actor_id=None` iff
    `actor_type == vocabulary.ACTOR_SYSTEM` (the biconditional CHECK, the managerless
    auto-approval). `occurred_at` is the instant the service read from the shell clock (AD-1).

    Returns `None`: the audit row is written for the trail, never projected to a client. This is
    the ONLY write path for `audit_entry` — there is deliberately no update or delete method
    (append-only, AD-8/AD-9).
    """
    session.add(
        AuditEntry(
            subject_type=subject_type,
            subject_id=subject_id,
            from_state=from_state,
            to_state=to_state,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            occurred_at=occurred_at,
        )
    )
    session.flush()


def list_audit_entries(
    session: Session, *, limit: int, offset: int
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of the audit trail, newest first, AND the full count (AC1, FR-16).

    WHY THIS GETTER IS EXEMPT FROM THE SCOPED-GETTER CONTRACT (`tests/test_scoped_getters.py`):
    `audit_entry` has NO Employee-owner column. `actor_id` records who ACTED, not who OWNS the row —
    scoping the trail by it would be semantically wrong, and it would hide from an Admin every
    transition they did not personally perform, which is the opposite of an audit trail. The gate is
    the ADMIN ROLE, applied in `api/` by `require_role` BEFORE this query runs (DR-13, G3: "403 —
    denied by role grant, decided before any row is read"). The api-contracts scope is `all`, so
    there is no per-row predicate to apply and no cross-Employee disclosure to guard: this is the
    same scope-`all` reference-read exemption `list_departments`/`list_leave_types`/`list_holidays`
    carry, and it is registered in that test's EXEMPT frozenset with the same rationale.

    LEFT OUTER JOIN, and it MUST stay outer. `actor_id` is NULL exactly when `actor_type = 'SYSTEM'`
    (the biconditional CHECK) — the managerless auto-approval, which has no human actor. An INNER
    join would silently DROP every SYSTEM row: AC6 would become unobservable through the endpoint,
    and SM-4's one-to-one count would quietly UNDER-count. `full_name` therefore arrives as `None`
    for those rows, and the service passes that `None` up untouched rather than fabricating a name.

    ORDER BY `occurred_at DESC, id DESC` — the `id` tiebreak is NOT decoration. A Cancellation
    Request approval writes TWO rows (the CR and the Leave Request) in one transaction from a single
    `_now()` reading, so their `occurred_at` is byte-identical. `ORDER BY occurred_at DESC` alone is
    therefore not a TOTAL order: Postgres may return the tied rows in either order between two
    queries, and a paginated read would then show one row twice and skip another. `id` is a UUIDv7 —
    time-ordered by construction — so it breaks the tie deterministically and in the right direction.

    `total` recomputes the same (empty) predicate over `audit_entry` ALONE: the count is of audit
    rows, and the actor join neither adds nor removes one (it is outer, and `actor_id` is a
    many-to-one FK). Returns `(rows, total)` so the service assembles the `Page` envelope from one
    round-trip.
    """
    rows = list(
        session.execute(
            select(*_READ_COLUMNS)
            .outerjoin(Employee, AuditEntry.actor_id == Employee.id)
            .order_by(AuditEntry.occurred_at.desc(), AuditEntry.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(AuditEntry)) or 0
    return rows, total
