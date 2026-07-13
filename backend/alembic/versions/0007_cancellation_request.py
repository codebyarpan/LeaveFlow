"""cancellation_request — the approved-leave cancellation object (Story 2.8, AD-13/DR-14)

Implements: AC1 (this migration creates `cancellation_request` as its OWN table — not a fifth
`leave_request.status` — with `leave_request_id` FK, and `status` TEXT holding one of
`PENDING`/`APPROVED`/`REJECTED` under a named CHECK). AD-11 (schema only — no `insert()`/DML;
`test_migrations_insert_nothing.py` AST-forbids any and pins the ordered chain).

--- A Cancellation Request is an ENTITY, not a status (AD-13, DR-14) ---

An applicant raises a Cancellation Request against their own future-dated Approved Leave Request;
an Admin decides it. Modelling it as its own row — rather than a fifth Leave Request status — is
what makes "Approved, with a cancellation pending" representable: while the CR is `PENDING`, the
target Leave Request stays `APPROVED` with its days `consumed`; only an *approved* CR moves it to
`CANCELLED` and returns those days (`release_consumed`, BR-05). The polymorphic `audit_entry`
already carries `subject_type ∈ {LEAVE_REQUEST, CANCELLATION_REQUEST}` (0006), so a decision writes
one row per subject with no schema change here.

--- No UNIQUE, no index, no requester/decider/timestamp column (ERD §2.1, §3, §4.4) ---

There is deliberately NO `UNIQUE (leave_request_id)`: a Leave Request may have MULTIPLE
Cancellation Requests over time (a rejected one may be followed by another — ERD §3, "zero or
more"). The ERD names NO index for this table (unlike `leave_request`'s two): the Admin list
filters by `status` at Epic-2 scale (few rows), so inventing one the ERD does not name would break
`alembic check` unless mirrored in the model — and the ERD is the source of truth. There is no
requester column (the requester is `leave_request.employee_id`, FR-09), no decider column (the
deciding Admin is the `actor_id` on the audit row), and no `created_at` (creation order comes from
the time-ordered UUIDv7 PK), exactly like `leave_request`.

--- uuidv7() is native ---

PostgreSQL 18 ships `uuidv7()` as a built-in (`server_default=sa.text("uuidv7()")`, no extension),
mirroring `0002`–`0006`. The table must stay faithful to `app/repositories/models.py`: `alembic
check` (run by `tests/integration/test_model_migration_agreement.py`) emits an empty diff only
while they agree — the constraint `name` here is byte-identical to the model's.

Revision ID: 0007_cancellation_request
Revises: 0006_leave_request
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cancellation_request"
down_revision: str | Sequence[str] | None = "0006_leave_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `cancellation_request`. Schema only — no row is inserted (AD-11)."""
    op.create_table(
        "cancellation_request",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("leave_request_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["leave_request_id"], ["leave_request.id"]),
        sa.PrimaryKeyConstraint("id"),
        # AD-5 backstop — the service is the gate; name byte-identical to the model.
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED')",
            name="cancellation_request_status_check",
        ),
    )


def downgrade() -> None:
    """Drop the table (no other table FKs it, so the drop is unencumbered)."""
    op.drop_table("cancellation_request")
