"""Audit Entry writes — INSERT and SELECT only, the code-layer append-only guarantee (AD-8/AD-9).

Implements: AC2 (the append-only audit trail). This module is the CODE-LAYER realization of
"append-only": it exposes an INSERT (and, later, reads) and NO update or delete method for
`audit_entry` — ever. AD-8's own words: "no repository exposes an update or delete method for
either table." With the codebase running a single Postgres role, a DB-role `REVOKE UPDATE/DELETE`
would be a no-op (an owner cannot be denied on its own table), so this method surface — asserted by
`tests/integration/test_leave_request_submit.py` — is the binding, testable guarantee (Story 2.6
Decision Point, AD-9). SM-6.

--- One row per transition, same transaction (AD-8) ---

`insert_audit_entry` `flush`es but does NOT commit: the submission command writes exactly one
audit row in the SAME transaction as the `leave_request` insert and the balance mutation, so a
rolled-back submit leaves neither a request row nor an audit row. `from_state=None` records a
creation (there is no prior state). It is a write governed by the command's transaction, not a
getter — no `actor` scoping applies.
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.repositories.models import AuditEntry


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
