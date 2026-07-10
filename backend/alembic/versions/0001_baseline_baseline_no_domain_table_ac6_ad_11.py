"""baseline: no domain table (AC6, AD-11)

Implements: AC6 (this story creates no domain table), AD-11 (no migration ever
inserts a Leave Type row), AC1 (`alembic upgrade head` is command two of setup).

--- Why an explicit no-op revision, rather than no revision at all ---

With ZERO revision files, `alembic upgrade head` exits 0, creates `alembic_version`,
and leaves it EMPTY — "head" resolves to nothing. An empty `alembic_version` reads to
deployment tooling as "this database has never been migrated", which is a different
claim from "this database is up to date", and the two diverge at the worst moment.

With ONE no-op revision it exits 0, creates `alembic_version`, and STAMPS it. That:

  - anchors `down_revision` for Story 1.2's first real migration, so the migration
    history has one root rather than several competing ones;
  - makes `alembic current` meaningful from the first deployment onward;
  - smoke-tests the `env.py` wiring — a broken DATABASE_URL fails here, during setup,
    instead of during Story 1.2's first schema change.

This revision creates nothing and inserts nothing. It is not a placeholder awaiting
content: it is the assertion, executable and permanent, that Story 1.1 added no table.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-10
"""

from collections.abc import Sequence

# `op` and `sa` are deliberately not imported. This revision touches no schema, and an
# unused import of `op` is an invitation to reach for `op.bulk_insert()` here — which
# is exactly what AD-11 forbids.

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Deliberately empty. AC6: no domain table is created by this story.

    AD-11: a migration never inserts a Leave Type row. When Story 2.1 adds the
    `leave_type` table, its EL/CL/FL rows still arrive through the seed command.
    `op.bulk_insert()` here would satisfy the letter of "seeded" while violating
    AD-11, which exists so SM-5 can add a fourth Leave Type with no migration.
    """


def downgrade() -> None:
    """Deliberately empty. There is nothing to undo."""
