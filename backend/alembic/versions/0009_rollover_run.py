"""The rollover's execution log — the SECOND append-only table, with its own grant (Story 2.10)

Implements: AC1 (`rollover_run` carries `leave_year` and `occurred_at`, and is append-only — the
application's database role is granted `INSERT` and `SELECT` and NEITHER `UPDATE` NOR `DELETE`,
with migrations running as the owner), AD-8, AD-9, NFR-09.

--- Why this migration issues its own grant, and inherits nothing ---

`0008_audit_read_surface` provisioned the least-privilege application role and left a note
addressed to THIS migration by name: it deliberately did NOT issue `ALTER DEFAULT PRIVILEGES`,
because that would blanket-grant `UPDATE` and `DELETE` to every table the owner creates from then
on — INCLUDING this one, which AD-9 requires to be append-only for exactly the reason `audit_entry`
is. So there is no inherited grant, and a table that adds itself must add its grant, deliberately.
That is a feature, and this file is the first to pay for it.

The grant below is ONE line and one shape:

    GRANT INSERT, SELECT ON rollover_run TO <app_role>;

Not `UPDATE`. Not `DELETE`. The ABSENCE of those two verbs IS AC1 — the same way the absence of
them from `0008`'s `_APPEND_ONLY_TABLES` is AC3 of Story 2.9. Copying `0008`'s `_READ_WRITE_TABLES`
loop instead would grant all four verbs, leave every test in the suite green, and destroy NFR-09
without a single red mark. That is the failure mode this docstring exists to prevent.

Nothing else is granted here. `GRANT USAGE ON SCHEMA public` and `GRANT USAGE ON ALL SEQUENCES`
were both issued by `0008` and are not re-issued: the schema grant is not per-table, and `uuidv7()`
is a server default that uses no sequence. Re-issuing either would be copy-paste noise.

--- Why `_quoted_role()` is re-declared rather than imported ---

Alembic revisions are loaded as standalone modules, not as a package: `from .0008_audit_read_surface
import _quoted_role` is not importable across revisions (and the helper is module-private anyway).
"Reuse 0008's pattern" therefore means copy the SHAPE — the helper, its `psycopg.sql` quoting, and
its refusal to run offline — not import the symbol.

--- This migration writes no ROWS (AD-11) ---

`CREATE TABLE` and `GRANT` are schema and privilege statements, not data.
`tests/test_migrations_insert_nothing.py` governs this file and still passes: no `INSERT`, no
`UPDATE … SET`, no `DELETE FROM`.

Revision ID: 0009_rollover_run
Revises: 0008_audit_read_surface
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from psycopg import sql

from app.core.settings import get_settings

# `--sql` (offline) mode is REFUSED, exactly as `0008` refuses it: resolving the app-role name is a
# settings read, and the `GRANT` must name a role that exists — neither is checkable without a live
# connection. Failing with a sentence beats emitting a script that silently grants nothing.
_OFFLINE_REFUSAL = (
    "0009_rollover_run cannot run in --sql (offline) mode: its GRANT names the application role "
    "resolved from settings, which requires a live connection to verify. Run `alembic upgrade "
    "head` against the database instead."
)

revision: str = "0009_rollover_run"
down_revision: str | None = "0008_audit_read_surface"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _quoted_role() -> tuple[str, sql.Identifier]:
    """Return the configured app-role name and its safely-quoted SQL identifier.

    Re-declared from `0008` rather than imported: Alembic revisions are not a package, and the
    helper is module-private there. The role name comes from the environment, so quoting it by
    hand is how an identifier containing a quote becomes an injection — `sql.Identifier` quotes it
    correctly by construction.
    """
    app_user = get_settings().app_db_user
    return app_user, sql.Identifier(app_user)


def upgrade() -> None:
    """Create `rollover_run`, then grant the app role INSERT and SELECT on it — and nothing else."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    # Exactly the ERD's two attributes, plus the `uuidv7()` PK every table here carries. No `actor`
    # column (the actor is always SYSTEM), and no `UNIQUE (leave_year)`: the table logs EXECUTIONS,
    # so a second run against one year appends a second row. Idempotence is a property of the
    # BALANCES (`set_accrual` assigns a derived value), never of this log.
    op.create_table(
        "rollover_run",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("leave_year", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # INSERT and SELECT. Not UPDATE. Not DELETE. This one statement is AC1.
    _, role = _quoted_role()
    op.execute(
        sql.SQL("GRANT INSERT, SELECT ON {table} TO {role}")
        .format(table=sql.Identifier("rollover_run"), role=role)
        .as_string()
    )


def downgrade() -> None:
    """Drop the table. The grant goes with it; the ROLE itself is `0008`'s to drop, not ours."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    op.drop_table("rollover_run")
