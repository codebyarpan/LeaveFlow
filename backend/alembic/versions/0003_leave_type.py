"""leave_type — leave policy as configuration (FR-06, AD-11, DR-11, SM-5)

Implements: AC1 (this migration creates the `leave_type` table, and only that), AC2/AD-11
(it INSERTS NOTHING — EL/CL/FL arrive through `python -m seed`, so SM-5's "a fourth Leave
Type needs no migration and no code change" holds).

--- Why a table, and why it inserts nothing ---

A Leave Type is DATA (AD-11): a row, never a PostgreSQL `ENUM` and never a Python `Enum`.
So this migration defines the *shape* — seven columns and `UNIQUE (code)` — and stops
there. The three seed rows enter through the seed command; `tests/test_migrations_insert_
nothing.py` parses this file and fails the build if it ever grows an `insert()`.

--- uuidv7() is native ---

PostgreSQL 18 ships `uuidv7()` as a built-in, so `server_default=sa.text("uuidv7()")` is
all it takes — no extension, mirroring `0002`. This migration must stay faithful to
`app/repositories/models.py`'s `LeaveType`: `alembic check` (exercised by
`tests/integration/test_model_migration_agreement.py`) emits an empty diff only while the
two agree.

Revision ID: 0003_leave_type
Revises: 0002_department_and_employee
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_leave_type"
down_revision: str | Sequence[str] | None = "0002_department_and_employee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `leave_type`. Schema only — no row is inserted (AD-11)."""
    op.create_table(
        "leave_type",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("annual_entitlement", sa.Integer(), nullable=False),
        sa.Column("carries_forward", sa.Boolean(), nullable=False),
        # Nullable: the carry-forward cap is meaningless where `carries_forward` is false.
        sa.Column("carry_forward_cap", sa.Integer(), nullable=True),
        sa.Column("requires_supporting_document", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="leave_type_code_key"),
    )


def downgrade() -> None:
    """Drop the table."""
    op.drop_table("leave_type")
