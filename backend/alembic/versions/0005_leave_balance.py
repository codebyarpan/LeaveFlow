"""leave_balance — three quantities stored, one derived (FR-07, DR-3, AD-5, AD-17)

Implements: AC1 (this migration creates `leave_balance` with `accrued`, `reserved`,
`consumed`, `prorated_entitlement`, `carried_forward`, `entitlement_basis` and `leave_year`,
all INTEGER, plus the three CHECKs and the UNIQUE, and NO `available` column), AC11 (the
migration inserts NOTHING — rows are materialized only by the service hooks in Story 2.4),
AD-11 (schema only, no DML).

--- Why three CHECKs and a UNIQUE, and no `available` column ---

`available` is derived (`accrued − consumed − reserved`) at the projection, never stored
(DR-3, AD-5). The three CHECKs are the AD-5 BACKSTOP behind the balance algebra — the service
pre-checks under the row lock and raises `INSUFFICIENT_BALANCE`, so a CHECK reaching a client
is a defect. `UNIQUE (employee_id, leave_type_id, leave_year)` is one balance per pair per
year; its implicit btree index IS the `SELECT … FOR UPDATE` access path (ERD §4.4), so NO
separate index is created here.

--- uuidv7() is native ---

PostgreSQL 18 ships `uuidv7()` as a built-in, so `server_default=sa.text("uuidv7()")` is all
it takes — no extension, mirroring `0002`/`0003`/`0004`. This migration must stay faithful to
`app/repositories/models.py`'s `LeaveBalance`: `alembic check` (exercised by
`tests/integration/test_model_migration_agreement.py`) emits an empty diff only while the two
agree — every constraint `name` here is byte-identical to the model's.

Revision ID: 0005_leave_balance
Revises: 0004_company_holiday
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_leave_balance"
down_revision: str | Sequence[str] | None = "0004_company_holiday"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `leave_balance`. Schema only — no row is inserted (AD-11)."""
    op.create_table(
        "leave_balance",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("leave_year", sa.Integer(), nullable=False),
        sa.Column("accrued", sa.Integer(), nullable=False),
        sa.Column("prorated_entitlement", sa.Integer(), nullable=False),
        sa.Column("carried_forward", sa.Integer(), nullable=False),
        sa.Column("entitlement_basis", sa.Integer(), nullable=False),
        # `reserved`/`consumed` default to 0 so a materializing insert need not name them —
        # only reserve/consume_* ever change a committed/spent quantity.
        sa.Column("reserved", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("consumed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["leave_type_id"], ["leave_type.id"]),
        sa.PrimaryKeyConstraint("id"),
        # AD-5 backstops — the service is the gate; names byte-identical to the model.
        sa.CheckConstraint(
            "accrued - consumed - reserved >= 0",
            name="leave_balance_available_nonneg_check",
        ),
        sa.CheckConstraint(
            "reserved >= 0 AND consumed >= 0",
            name="leave_balance_reserved_consumed_nonneg_check",
        ),
        sa.CheckConstraint(
            "accrued = prorated_entitlement + carried_forward",
            name="leave_balance_accrued_composition_check",
        ),
        # One balance per (Employee, Leave Type, Leave Year). Its implicit btree index is the
        # FOR UPDATE access path (ERD §4.4), so no separate `op.create_index` is added.
        sa.UniqueConstraint(
            "employee_id",
            "leave_type_id",
            "leave_year",
            name="leave_balance_employee_type_year_key",
        ),
    )


def downgrade() -> None:
    """Drop the table."""
    op.drop_table("leave_balance")
