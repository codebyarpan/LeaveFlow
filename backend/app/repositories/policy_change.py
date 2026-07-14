"""Policy Change persistence — an INSERT and a SELECT, and nothing else (AD-8, AD-9, AD-20).

Implements: AC3 (a `policy_change` row records the Leave Type, the attribute, its old and new values,
the disposition and the moment) and AC7 (an Admin reads the recorded changes and their dispositions)
of Story 2.12. One repository module per table (the rule Story 2.9 fixed).

--- There is NO update method and NO delete method, and the absence IS the requirement ---

Exactly as `repositories/audit_entry.py`, `repositories/rollover_run.py` and
`repositories/admin_review_flag.py` have none. A policy change is a HISTORICAL FACT: it happened, at
a moment, under a disposition the Admin was FORCED to choose (FR-06). It is the record of WHY a
balance is the number it is. Rewriting it later would rewrite that reason — and a balance whose
justification has been quietly edited is precisely PRD §1's "wrong figure that will be believed".

The guarantee is enforced in TWO places, and the second is the real one: migration `0011` grants the
application role `INSERT` and `SELECT` on this table and NEITHER `UPDATE` NOR `DELETE`, so a write
against a recorded change is refused BY POSTGRES (`InsufficientPrivilege`). This method surface is
what stops a well-meaning future story from writing the update method in the first place. Add one
here and you have not defeated the database; you have only moved the error later.

--- And it is not `audit_entry` (AD-8, AD-20, Landmine 6) ---

A policy change transitions no Leave Request, so it writes no audit row. `AD-8` reserves
`audit_entry` for state transitions, and SM-4's one-to-one count of audit rows against transitions
(`tests/integration/test_audit_entries.py` pins it at exactly 14, with its per-`subject_type`
breakdown) must stay LITERALLY true through a policy edit. There is no `SUBJECT_POLICY_CHANGE` and no
`SUBJECT_LEAVE_TYPE` in `domain/vocabulary.py` and — echoing `services/rollover.py`'s "there is no
`SUBJECT_ROLLOVER` and there must not be one" — there must not be one. `policy_change` IS the log,
exactly as `rollover_run` and `admin_review_flag` are.
"""

import datetime
import uuid

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.repositories.models import LeaveType, PolicyChange

# Plain COLUMNS, never the ORM entity: a `Row` of columns is already detached, so nothing lazy-loads
# or expires when the read session closes (the `list_audit_entries` / `list_admin_review_flags`
# shape). `LeaveType.code` rides along from the join, because AC12's screen must NAME the Leave Type
# whose policy changed — a bare UUID is not something an Admin can act on.
_READ_COLUMNS = (
    PolicyChange.id,
    PolicyChange.leave_type_id,
    LeaveType.code,
    PolicyChange.attribute,
    PolicyChange.old_value,
    PolicyChange.new_value,
    PolicyChange.disposition,
    PolicyChange.occurred_at,
)


def insert_policy_change(
    session: Session,
    *,
    leave_type_id: uuid.UUID,
    attribute: str,
    old_value: str,
    new_value: str,
    disposition: str,
    occurred_at: datetime.datetime,
) -> None:
    """Append one row recording that a Leave Type's policy changed, and under what disposition (AC3).

    ONE ROW PER CHANGED BALANCE-AFFECTING ATTRIBUTE (Open Decision #4): the table is singular
    (`attribute`, `old_value`, `new_value`), so a `PATCH` moving both `annual_entitlement` and
    `carry_forward_cap` calls this TWICE, and the two rows share one `occurred_at` and one
    `disposition`. That shared timestamp is exactly why the read below needs an `id` tiebreak.

    `old_value`/`new_value` are TEXT and arrive ALREADY STRINGIFIED by the service (Open Decision
    #6): one column pair must carry an `int` (`annual_entitlement`), a NULLABLE int
    (`carry_forward_cap`) and a `bool` (`carries_forward`). A `None` cap is rendered as the string
    `"null"`, so the columns stay NOT NULL and "the cap was REMOVED" stays distinguishable from
    "there never was a cap".

    `disposition` is a `vocabulary.DISPOSITION_*` constant the caller passes (AD-21), never a bare
    literal, and it has already been VALIDATED against the two permitted values — the `CHECK
    (disposition IN (…))` on the table is the AD-5 BACKSTOP, never the gate. `occurred_at` is a
    timezone-aware instant from the service's shell clock (AD-1); a naive datetime against a
    `TIMESTAMPTZ` is a defect, not a nit.

    `flush()`, and deliberately NOT `commit()`: the row is written in the SAME transaction as the
    `leave_type` UPDATE and the recalculation it records, so a rolled-back policy edit leaves no row
    claiming it happened (AD-8's "because" clause, proved for `audit_entry` in Story 2.9, for
    `rollover_run` in 2.10 and for `admin_review_flag` in 2.11). The leave-type command commits, once.

    Returns `None`. This is the ONLY write path for `policy_change` — there is deliberately no update
    and no delete method (append-only, AD-9/AD-20), and no endpoint alters a recorded change.
    """
    session.add(
        PolicyChange(
            leave_type_id=leave_type_id,
            attribute=attribute,
            old_value=old_value,
            new_value=new_value,
            disposition=disposition,
            occurred_at=occurred_at,
        )
    )
    session.flush()


def list_policy_changes(
    session: Session, *, limit: int, offset: int
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of the recorded policy changes, newest first, AND the full count (AC7, AC12).

    WHY THIS GETTER IS EXEMPT FROM THE SCOPED-GETTER CONTRACT (`tests/test_scoped_getters.py`):
    api-contracts' scope for `/policy-changes` is `all`, and the gate is the ADMIN ROLE —
    `require_role` in `api/`, applied BEFORE any row is read (G3: "403 — denied by role grant,
    decided before any row is read"; 404 stays reserved for a scope miss, AD-10). A policy change is
    organization-wide CONFIGURATION HISTORY: the table has no Employee column at all, so there is not
    even a candidate predicate to scope by, let alone a cross-Employee disclosure to guard. It is
    registered in that test's EXEMPT frozenset with this rationale, rather than dodged by renaming it
    to a non-`list_` verb — Story 2.9's review settled that a surface claim gets revised with a
    rationale, never routed around.

    INNER JOIN `leave_type` for its `code`, and correctly so: `policy_change.leave_type_id` is NOT
    NULL by construction (a change is always a change TO something), so there is nothing to
    outer-join FOR and an inner join cannot drop a row. The contrast with `list_audit_entries` — which
    MUST outer-join, because `audit_entry.actor_id` is NULL on a SYSTEM row — is deliberate.

    ORDER BY `occurred_at DESC, id DESC` — and THE `id` TIEBREAK IS LOAD-BEARING. One `PATCH` writes
    one row per changed balance-affecting attribute, all from a single `_now()` reading, so their
    `occurred_at` is byte-identical. `ORDER BY occurred_at DESC` alone is therefore not a TOTAL
    order: Postgres may return the tied rows in either order between two queries, and a paginated
    read would then show one row twice and skip another. `id` is a UUIDv7 — time-ordered by
    construction — so it breaks the tie deterministically and in the right direction. Story 2.9 found
    this the hard way on the CR-approve pair, and 2.11 inherited it; it is the same trap a third time.

    `total` counts `policy_change` ALONE: the join adds and removes no row (a many-to-one on a NOT
    NULL FK). Returns `(rows, total)` so the service assembles the `Page` envelope from one round-trip.
    """
    rows = list(
        session.execute(
            select(*_READ_COLUMNS)
            .join(LeaveType, PolicyChange.leave_type_id == LeaveType.id)
            .order_by(PolicyChange.occurred_at.desc(), PolicyChange.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(PolicyChange)) or 0
    return rows, total
