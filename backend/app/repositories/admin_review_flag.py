"""Admin Review Flag persistence — an INSERT and a SELECT, and nothing else (AD-20, AD-9).

Implements: AC1/AC5 (the refusal is recorded, carrying its cause and the Employee and Leave Type it
left unchanged) and AC6 (an Admin reads the recorded refusals) of Story 2.11. One repository module
per table (the rule Story 2.9 fixed).

--- There is NO update method and NO delete method, and the absence IS the requirement ---

Exactly as `repositories/audit_entry.py` and `repositories/rollover_run.py` have none. `FR-10` grants
the Admin only a READ of these flags; NO requirement grants a resolve. AC6 says it outright — "no
endpoint clears a flag" — and ERD §6 (GAP-4) states the consequence: "there is no `resolved_at`
column and no endpoint clears a flag. A flag is a permanent record that a recalculation was refused
… The undefined behavior is gone because the behavior no longer exists."

The guarantee is enforced in TWO places, and the second is the real one: migration `0010` grants the
application role `INSERT` and `SELECT` on this table and NEITHER `UPDATE` NOR `DELETE`, so a write
against a flag is refused BY POSTGRES (`InsufficientPrivilege`). This method surface is what stops a
well-meaning future story from writing the update method in the first place — which is a better
failure than discovering it at runtime. Add one here and you have not defeated the database; you have
only moved the error later.

--- And it is not `audit_entry` (AD-20, Landmine 5) ---

A refused recalculation transitions no Leave Request, so it writes no audit row. `AD-8` reserves
`audit_entry` for state transitions and `AD-20` says flatly "Neither table is `audit_entry`" — the
same reasoning that gave `rollover_run` its own table, and the reason SM-4's one-to-one count of
audit rows against transitions stays literally true through a holiday edit. There is no
`SUBJECT_HOLIDAY` in `domain/vocabulary.py` and there must not be one.
"""

import datetime
import uuid

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.repositories.models import AdminReviewFlag, Employee, LeaveType

# Plain COLUMNS, never the ORM entity: a `Row` of columns is already detached, so nothing lazy-loads
# or expires when the read session closes (the `list_audit_entries` shape). `Employee.full_name` and
# `LeaveType.code` ride along from the joins, because AC9 requires the screen to NAME the pair a
# refusal left unchanged — a bare pair of UUIDs is not actionable.
_READ_COLUMNS = (
    AdminReviewFlag.id,
    AdminReviewFlag.employee_id,
    Employee.full_name,
    AdminReviewFlag.leave_type_id,
    LeaveType.code,
    AdminReviewFlag.leave_year,
    AdminReviewFlag.cause,
    AdminReviewFlag.occurred_at,
)


def insert_admin_review_flag(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    cause: str,
    occurred_at: datetime.datetime,
) -> None:
    """Append one row recording that a recalculation was REFUSED for this pair (AC5, AD-20).

    The pair (`employee_id`, `leave_type_id`) is the unit of refusal: it names what the recalculation
    left ENTIRELY unchanged, while the same Employee's other Leave Types still proceeded and the rest
    of the holiday edit still committed (AC4). `leave_year` is the EDITED year (`holiday_date.year`),
    never `date.today().year` — a flag that cannot say which year it refused is not actionable.
    `cause` is a `vocabulary.CAUSE_*` constant the caller passes (AD-21), never a bare literal.
    `occurred_at` is a timezone-aware instant from the service's shell clock (AD-1); a naive datetime
    against a `TIMESTAMPTZ` is a defect, not a nit.

    `flush()`, and deliberately NOT `commit()`: the flag is written in the SAME transaction as the
    recalculation it records, so a rolled-back holiday edit leaves no flag claiming it happened
    (AD-8's "because" clause, proved for `audit_entry` in Story 2.9 and for `rollover_run` in 2.10).
    The holiday command commits, once.

    Returns `None`. This is the ONLY write path for `admin_review_flag` — there is deliberately no
    update and no delete method (append-only, AD-20/AD-9), and no endpoint clears a flag.
    """
    session.add(
        AdminReviewFlag(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=leave_year,
            cause=cause,
            occurred_at=occurred_at,
        )
    )
    session.flush()


def flag_exists(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    cause: str,
) -> bool:
    """True if a flag with this exact (pair, year, cause) is already on the register.

    The dedupe read for the refusal writers (code review 2026-07-15): the register is append-only
    with NO resolved state (AC6 — "no endpoint clears a flag"), so every retry of the SAME refused
    event (an Employee re-submitting against an unreconcilable pair, a rollover re-run) would
    otherwise append another identical row and grow the Admin queue unboundedly for ONE underlying
    defect. Callers skip the insert when an identical flag already stands — one flag per (pair,
    year, cause) says everything N copies would. Distinct causes still get distinct rows, because a
    submission and a reject are different events (the `insert_admin_review_flag` rationale above).

    A SELECT, so it lives comfortably inside the table's INSERT+SELECT grant (migration 0010).
    """
    return (
        session.scalar(
            select(AdminReviewFlag.id)
            .where(
                AdminReviewFlag.employee_id == employee_id,
                AdminReviewFlag.leave_type_id == leave_type_id,
                AdminReviewFlag.leave_year == leave_year,
                AdminReviewFlag.cause == cause,
            )
            .limit(1)
        )
        is not None
    )


def list_admin_review_flags(
    session: Session, *, limit: int, offset: int
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of the recorded refusals, newest first, AND the full count (AC6, FR-10).

    WHY THIS GETTER IS EXEMPT FROM THE SCOPED-GETTER CONTRACT (`tests/test_scoped_getters.py`):
    api-contracts' scope for `/admin-review-flags` is `all`, and the gate is the ADMIN ROLE —
    `require_role` in `api/`, applied BEFORE any row is read (G3: "403 — denied by role grant,
    decided before any row is read"; 404 stays reserved for a scope miss, AD-10). The `employee_id`
    column names the SUBJECT OF A REFUSAL, not an owner whose scope should filter the Admin's read:
    scoping by it would hide from an Admin the very refusals they are the only one able to act on,
    which is the opposite of the register's purpose. So there is no per-row predicate to apply. It is
    registered in that test's EXEMPT frozenset with this rationale, rather than dodged by renaming it
    to a non-`list_` verb — Story 2.9's review settled that a surface claim gets revised with a
    rationale, never routed around.

    INNER JOIN both `employee` and `leave_type`, and correctly so — the contrast with
    `list_audit_entries` is deliberate. That one MUST outer-join, because `audit_entry.actor_id` is
    NULL for a SYSTEM row and an inner join would silently drop every managerless auto-approval. Here
    BOTH FKs are NOT NULL by construction (AC1: a flag always names the Employee AND the Leave Type
    it left unchanged), so there is nothing to outer-join FOR, and an inner join cannot drop a row.

    ORDER BY `occurred_at DESC, id DESC` — the `id` tiebreak is NOT decoration. ONE holiday edit
    refuses several pairs in a single transaction from a single `_now()` reading, so their
    `occurred_at` is byte-identical. `ORDER BY occurred_at DESC` alone is therefore not a TOTAL
    order: Postgres may return the tied rows in either order between two queries, and a paginated
    read would then show one row twice and skip another. `id` is a UUIDv7 — time-ordered by
    construction — so it breaks the tie deterministically and in the right direction. Story 2.9
    proved this the hard way on the CR-approve pair; it is the same trap.

    `total` recomputes over `admin_review_flag` ALONE: the count is of flags, and neither join adds
    or removes one (both are inner joins on many-to-one NOT NULL FKs). Returns `(rows, total)` so the
    service assembles the `Page` envelope from one round-trip.
    """
    rows = list(
        session.execute(
            select(*_READ_COLUMNS)
            .join(Employee, AdminReviewFlag.employee_id == Employee.id)
            .join(LeaveType, AdminReviewFlag.leave_type_id == LeaveType.id)
            .order_by(
                AdminReviewFlag.occurred_at.desc(), AdminReviewFlag.id.desc()
            )
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(AdminReviewFlag)) or 0
    return rows, total
