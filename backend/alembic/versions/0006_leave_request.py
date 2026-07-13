"""leave_request + audit_entry — the first two lifecycle tables (Story 2.6, FR-08/AD-8)

Implements: AC1 (this migration creates `leave_request` with `start_date`/`end_date` as DATE,
`leave_days` as INTEGER, `status` as TEXT with the four-state CHECK, plus `end_date >= start_date`
and `leave_days > 0`, and NO `created_at`/NO `leave_year` column), AC2 (this migration creates
`audit_entry` with the polymorphic `subject_*`, the nullable `from_state`/`actor_id`, and the
SYSTEM-actor biconditional CHECK), AD-11 (schema only — no `insert()`/DML;
`test_migrations_insert_nothing.py` fails the build on any).

--- The AD-9 grant decision (AC2) ---

AC2 also asks that the *application database role* hold `INSERT`+`SELECT` on `audit_entry` and
NEITHER `UPDATE` nor `DELETE`, with migrations running as the owner. This codebase runs a SINGLE
Postgres role (docker-compose provisions one `POSTGRES_USER`; migrations and the app connect as
it), so a `GRANT`/`REVOKE` against the owning role is a no-op — an owner cannot be denied on its
own table. The binding, testable form of "append-only" is therefore realized at the CODE LAYER
(AD-8's own words: "no repository exposes an update or delete method for either table") — see
`repositories/audit_entry.py`, which exposes only `insert`/`select`, and
`tests/integration/test_leave_request_submit.py`, which asserts the surface. A DB-role GRANT is
deferred pending a least-privilege role split; issuing one here would be a no-op with the current
single-role infra. This is declared, never silently dropped (Story 2.6 Decision Point).

--- uuidv7() is native, and the two `leave_request` indexes ---

PostgreSQL 18 ships `uuidv7()` as a built-in (`server_default=sa.text("uuidv7()")`, no extension),
mirroring `0002`–`0005`. `leave_request` carries the two ERD §4.4 read indexes explicitly
(employee+status, and the date-range scan); `audit_entry` needs none this story. Both tables must
stay faithful to `app/repositories/models.py`: `alembic check` (run by
`tests/integration/test_model_migration_agreement.py`) emits an empty diff only while they agree —
every constraint/index `name` here is byte-identical to the model's.

Revision ID: 0006_leave_request
Revises: 0005_leave_balance
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_leave_request"
down_revision: str | Sequence[str] | None = "0005_leave_balance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `leave_request` and `audit_entry`. Schema only — no row is inserted (AD-11)."""
    op.create_table(
        "leave_request",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("leave_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["leave_type_id"], ["leave_type.id"]),
        sa.PrimaryKeyConstraint("id"),
        # AD-5 backstops — the service is the gate; names byte-identical to the model.
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
            name="leave_request_status_check",
        ),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="leave_request_date_order_check",
        ),
        sa.CheckConstraint(
            "leave_days > 0",
            name="leave_request_leave_days_positive_check",
        ),
    )
    # The two ERD §4.4 read indexes.
    op.create_index(
        "ix_leave_request_employee_status",
        "leave_request",
        ["employee_id", "status"],
    )
    op.create_index(
        "ix_leave_request_start_end",
        "leave_request",
        ["start_date", "end_date"],
    )

    op.create_table(
        "audit_entry",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.Text(), nullable=False),
        # Polymorphic — NO foreign key (ERD §2): the trail spans subject types.
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        # NULL for a creation — no prior state.
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        # NULL iff SYSTEM (the biconditional CHECK). FKs employee.id when a human acted.
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        # The one instant in the schema — TIMESTAMP WITH TIME ZONE (ERD §2), set in the shell.
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
        # The SYSTEM-actor biconditional: actor_type == 'SYSTEM' iff actor_id IS NULL.
        sa.CheckConstraint(
            "(actor_type = 'SYSTEM') = (actor_id IS NULL)",
            name="audit_entry_system_actor_null_check",
        ),
    )


def downgrade() -> None:
    """Drop both tables (audit_entry first — neither FKs the other, so order is cosmetic)."""
    op.drop_table("audit_entry")
    op.drop_index("ix_leave_request_start_end", table_name="leave_request")
    op.drop_index("ix_leave_request_employee_status", table_name="leave_request")
    op.drop_table("leave_request")
