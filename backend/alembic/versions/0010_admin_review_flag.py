"""The refusal register — the THIRD append-only table, with its own grant (Story 2.11)

Implements: AC1 (`admin_review_flag` carries the `employee_id` and `leave_type_id` pair the
recalculation left unchanged, the `leave_year`, a `cause` and `occurred_at`; it is NOT `audit_entry`,
and no endpoint updates or deletes a row in it), AD-19, AD-20, AD-9, NFR-09.

--- This table INHERITS NOTHING, and that is deliberate ---

`0008_audit_read_surface` provisioned the least-privilege application role and deliberately did NOT
issue `ALTER DEFAULT PRIVILEGES` — that would blanket-grant `UPDATE` and `DELETE` to every table the
owner creates from then on, INCLUDING this one. `0009_rollover_run` was the first table to pay for
that decision; this is the second. A table that adds itself must add its grant, deliberately.

The grant below is ONE line and one shape:

    GRANT INSERT, SELECT ON admin_review_flag TO <app_role>;

Not `UPDATE`. Not `DELETE`. The ABSENCE of those two verbs IS AC1 — "no endpoint updates or deletes
a row in it".

--- Why append-only here is a CALL, not a default ---

`0008` defines two grant shapes: `_APPEND_ONLY_TABLES` (INSERT, SELECT) and `_READ_WRITE_TABLES`
(all four verbs). This table takes the FIRST, and the tempting argument for the second — "an Admin
will want to resolve a flag" — is refused on the record:

`FR-10` grants the Admin only a READ of these flags. No requirement grants a resolve. ERD §6
(GAP-4) states the consequence outright: "there is no `resolved_at` column and no endpoint clears a
flag … The undefined behavior is gone because the behavior no longer exists." So there is no
`resolved_at` column above, and granting `UPDATE`/`DELETE` here would leave every test in the suite
green while quietly destroying the guarantee — exactly the failure mode `0009`'s docstring warns
about when it says copying the wrong loop "destroys NFR-09 without a single red mark".

--- Why `_quoted_role()` is re-declared rather than imported ---

Alembic revisions are loaded as standalone modules, not as a package: `from .0009_rollover_run import
_quoted_role` is not importable across revisions (and the helper is module-private anyway). "Reuse
0009's pattern" therefore means copy the SHAPE — the helper, its `psycopg.sql` quoting, and its
refusal to run offline — not import the symbol.

Nothing else is granted here. `GRANT USAGE ON SCHEMA public` and `GRANT USAGE ON ALL SEQUENCES` were
both issued by `0008` and are not re-issued: the schema grant is not per-table, and `uuidv7()` is a
server default that uses no sequence.

--- This migration writes no ROWS (AD-11) ---

`CREATE TABLE` and `GRANT` are schema and privilege statements, not data.
`tests/test_migrations_insert_nothing.py` governs this file and still passes: no `INSERT`, no
`UPDATE … SET`, no `DELETE FROM`.

Revision ID: 0010_admin_review_flag
Revises: 0009_rollover_run
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from psycopg import sql

from app.core.settings import get_settings

# `--sql` (offline) mode is REFUSED, exactly as `0008` and `0009` refuse it: resolving the app-role
# name is a settings read, and the `GRANT` must name a role that exists — neither is checkable
# without a live connection. Failing with a sentence beats emitting a script that silently grants
# nothing.
_OFFLINE_REFUSAL = (
    "0010_admin_review_flag cannot run in --sql (offline) mode: its GRANT names the application "
    "role resolved from settings, which requires a live connection to verify. Run `alembic upgrade "
    "head` against the database instead."
)

revision: str = "0010_admin_review_flag"
down_revision: str | None = "0009_rollover_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _quoted_role() -> tuple[str, sql.Identifier]:
    """Return the configured app-role name and its safely-quoted SQL identifier.

    Re-declared from `0009` rather than imported: Alembic revisions are not a package, and the
    helper is module-private there. The role name comes from the environment, so quoting it by hand
    is how an identifier containing a quote becomes an injection — `sql.Identifier` quotes it
    correctly by construction.
    """
    app_user = get_settings().app_db_user
    return app_user, sql.Identifier(app_user)


def upgrade() -> None:
    """Create `admin_review_flag`, then grant the app role INSERT and SELECT — and nothing else."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    # The PAIR (AC1), the year, the cause and the moment — plus the `uuidv7()` PK every table here
    # carries. No `resolved_at` (no requirement grants a resolve), and no single polymorphic
    # `subject_id`: AC1 requires the `employee_id` AND `leave_type_id` pair, so the stale ERD
    # diagram in `ARCHITECTURE-SPINE.md:317-321` is not what is built here.
    op.create_table(
        "admin_review_flag",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("leave_year", sa.Integer(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["leave_type_id"], ["leave_type.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # INSERT and SELECT. Not UPDATE. Not DELETE. This one statement is AC1.
    _, role = _quoted_role()
    op.execute(
        sql.SQL("GRANT INSERT, SELECT ON {table} TO {role}")
        .format(table=sql.Identifier("admin_review_flag"), role=role)
        .as_string()
    )


def downgrade() -> None:
    """Drop the table. The grant goes with it; the ROLE itself is `0008`'s to drop, not ours."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    op.drop_table("admin_review_flag")
