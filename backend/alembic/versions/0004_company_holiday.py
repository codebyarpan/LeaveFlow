"""company_holiday — the global calendar of non-working days (FR-10, AD-12, DR-1)

Implements: AC1 (this migration creates the `company_holiday` table, and only that, with
`holiday_date DATE` + `UNIQUE (holiday_date)` and NO scope column), AC2 (the date column is
`sa.Date()`, never `sa.DateTime()` — a holiday is a calendar `DATE`, not a timestamp).

--- Why a table, and why it inserts nothing ---

The holiday calendar is DATA (AD-11-adjacent): the Admin populates it through
`POST /holidays`, one row at a time. So this migration defines the *shape* — three columns
and `UNIQUE (holiday_date)` — and stops there, INSERTING NOTHING. The calendar starts empty;
`tests/test_migrations_insert_nothing.py` parses this file's AST and fails the build if it
ever grows an `insert()`.

--- uuidv7() is native ---

PostgreSQL 18 ships `uuidv7()` as a built-in, so `server_default=sa.text("uuidv7()")` is all
it takes — no extension, mirroring `0002`/`0003`. This migration must stay faithful to
`app/repositories/models.py`'s `CompanyHoliday`: `alembic check` (exercised by
`tests/integration/test_model_migration_agreement.py`) emits an empty diff only while the two
agree — the `UNIQUE` constraint name in particular (`company_holiday_holiday_date_key`) is
what SQLAlchemy derives from `unique=True`, the `_key` suffix `0003` used for
`leave_type_code_key`.

Revision ID: 0004_company_holiday
Revises: 0003_leave_type
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_company_holiday"
down_revision: str | Sequence[str] | None = "0003_leave_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `company_holiday`. Schema only — no row is inserted (AD-11-adjacent)."""
    op.create_table(
        "company_holiday",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        # `sa.Date()`, NOT `sa.DateTime()` — a holiday is a calendar DATE (AC2, AD-12).
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("holiday_date", name="company_holiday_holiday_date_key"),
    )


def downgrade() -> None:
    """Drop the table."""
    op.drop_table("company_holiday")
