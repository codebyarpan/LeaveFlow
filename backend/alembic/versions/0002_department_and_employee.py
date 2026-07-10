"""department and employee — the first two domain tables (AC1, AD-10, AD-14, AD-23)

Implements: AC1 (this story creates `department` and `employee`, and only those),
AD-23 (`CHECK (id <> manager_id)` ships here as the database's backstop, because ERD
§4.2 puts it on the table; the service-layer cycle gate is Story 1.6's), AD-11 (this
migration creates schema and inserts NOTHING — the Admin and the Department arrive
through `python -m seed`, so SM-5's "a fourth Leave Type needs no migration" holds).

--- Why these two tables, together, now ---

`employee.department_id` is NOT NULL: every Employee belongs to exactly one Department
(PRD §3). The Admin seeded in Story 1.2 (AC2) therefore needs a Department to point at,
so `department` cannot wait for Story 1.5 — Story 1.5 adds its *endpoints*, not its row.

--- uuidv7() is native ---

PostgreSQL 18 ships `uuidv7()` as a built-in (verified on `postgres:18.4`). No
`uuid-ossp`, no `pgcrypto`, no `CREATE EXTENSION` — `server_default=sa.text("uuidv7()")`
is all it takes, and the keys are time-ordered, which keeps the primary-key index from
fragmenting the way random v4 keys do.

This migration must stay faithful to `app/repositories/models.py` — `alembic check`
(exercised by `tests/integration/test_schema_1_2.py`) emits an empty diff only while the
two agree. It also sits under `tests/test_migrations_insert_nothing.py`, which parses
this file and fails the build if it ever grows an `insert()`.

Revision ID: 0002_department_and_employee
Revises: 0001_baseline
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_department_and_employee"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `department` and `employee`. Schema only — no row is inserted (AD-11)."""
    op.create_table(
        "department",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "employee",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        # Nullable: an Admin, and the top of any reporting chain, reports to no one (AC2).
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("joining_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["manager_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        # The database's copy of the role vocabulary — prescribed verbatim by ERD §4.2,
        # exempt from the AD-21 literal check because a migration is immutable.
        sa.CheckConstraint(
            "role IN ('EMPLOYEE', 'MANAGER', 'ADMIN')",
            name="employee_role_check",
        ),
        # AD-23 backstop only — the transitive-cycle refusal lives in Story 1.6's service.
        sa.CheckConstraint("id <> manager_id", name="employee_not_own_manager_check"),
    )
    op.create_index("ix_employee_department_id", "employee", ["department_id"])
    op.create_index("ix_employee_manager_id", "employee", ["manager_id"])


def downgrade() -> None:
    """Drop both tables. `employee` first — its foreign key references `department`."""
    op.drop_index("ix_employee_manager_id", table_name="employee")
    op.drop_index("ix_employee_department_id", table_name="employee")
    op.drop_table("employee")
    op.drop_table("department")
