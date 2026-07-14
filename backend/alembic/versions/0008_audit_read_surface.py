"""The audit read surface: the least-privilege app role, its grants, and the ERD's index (Story 2.9)

Implements: AC3 (append-only is a GRANT, not a habit — the application's database role is granted
`INSERT` and `SELECT` on `audit_entry` and is granted NEITHER `UPDATE` NOR `DELETE`, so the database
refuses them "because the grant was never made"), NFR-09, AD-9; and NFR-12 / ERD §4.4's
`audit_entry (subject_type, subject_id)` index — named there "the audit read surface (FR-16)", which
is precisely what this story opens.

--- Why this migration provisions a ROLE, which no migration before it has done ---

Story 2.6 recorded a Decision Point and took the honest short option: the codebase ran a SINGLE
Postgres role, which OWNS `audit_entry`. Against an owner, `REVOKE UPDATE, DELETE` is a NO-OP — an
owner cannot be denied on its own table — so AD-9's guarantee did not exist in the database. Only
the code-layer surface test (`repositories/audit_entry.py` exposes no update and no delete) held it
up. That was defensible for 2.6. It is NOT defensible for AC3, which says in as many words: *the
database refuses, because the grant was never made.*

So this migration splits the roles AD-9 and ERD §4.3 have specified all along:

  OWNER (`POSTGRES_USER`) — owns every table; runs Alembic; is the role executing THIS file.
  APP   (`APP_DB_USER`)   — what FastAPI connects as (`repositories/engine.py`) and what `seed`
                            runs as. Created below `NOSUPERUSER NOCREATEDB NOCREATEROLE`, and
                            granted its privileges table by table.

--- Why the role is created HERE and not in the container's init path ---

`docker-compose.yml` provisions the database through the postgres image's entrypoint, which runs
`/docker-entrypoint-initdb.d/*` ONLY on a fresh data directory. A role created there would never
appear in any database that already exists — every developer's, and every deployed one. Creating it
in the owner-run migration instead means `alembic upgrade head` provisions it, so:

  * setup stays THREE commands (NFR-21, AC1) — nothing new to run;
  * an EXISTING database picks the role up on the next upgrade;
  * a changed `APP_DB_PASSWORD` re-syncs on the next upgrade (the `ALTER ROLE` below).

--- This migration writes no ROWS (AD-11) ---

`CREATE ROLE` and `GRANT` are privilege statements, not data. `tests/test_migrations_insert_nothing.
py` still governs this file, and it still passes: no `INSERT`, no `UPDATE … SET`, no `DELETE FROM`.

--- Identifier and literal quoting is psycopg's job, not a format string's ---

The role name and password come from the environment, so interpolating them into SQL by hand is how
a password containing a quote becomes an injection. `psycopg.sql.Identifier` / `sql.Literal` quote
them correctly by construction — the same guarantee `settings.py` gets from `quote()` for the DSN.

Revision ID: 0008_audit_read_surface
Revises: 0007_cancellation_request
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from psycopg import sql

from app.core.settings import get_settings

# `--sql` (offline) mode is REFUSED by this migration, loudly, rather than half-working.
#
# Two reasons, either sufficient. It cannot work: the role bootstrap must ask the live database
# whether the role already exists (`CREATE ROLE` has no `IF NOT EXISTS`), and offline mode has no
# connection to ask. And it must not work: an emitted `.sql` script would carry APP_DB_PASSWORD as a
# plaintext literal into a file someone would then paste into a terminal, commit, or mail. Failing
# with a sentence beats emitting a script that leaks a credential and still does not run.
_OFFLINE_REFUSAL = (
    "0008_audit_read_surface cannot run in --sql (offline) mode: it provisions a database ROLE, "
    "which requires a live connection to check for existence, and an emitted script would contain "
    "APP_DB_PASSWORD in plaintext. Run `alembic upgrade head` against the database instead."
)

revision: str = "0008_audit_read_surface"
down_revision: str | None = "0007_cancellation_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Every table the application both reads and writes. The app role gets the four verbs on each —
# it must keep working, and a missed grant here breaks an endpoint, not a test.
_READ_WRITE_TABLES: tuple[str, ...] = (
    "department",
    "employee",
    "leave_type",
    "company_holiday",
    "leave_balance",
    "leave_request",
    "cancellation_request",
)

# `audit_entry` is the exception, and the exception is the point of the story: INSERT and SELECT,
# and NOTHING ELSE. The ABSENCE of `UPDATE` and `DELETE` from this tuple IS the AD-9 guarantee.
# Adding either verb here silently destroys NFR-09 while every other test stays green.
_APPEND_ONLY_TABLES: tuple[str, ...] = ("audit_entry",)

# `alembic_version` is deliberately granted NOTHING: the schema version is the owner's business.
# The seed command's "did you run command two?" check uses `to_regclass`, a catalog lookup that
# needs no privilege on the table itself, so this costs the app nothing.
#
# NOTE — no `ALTER DEFAULT PRIVILEGES`. It is the obvious way to keep future tables working
# automatically, and it is wrong here: it would blanket-grant UPDATE and DELETE to every table the
# owner creates from now on, INCLUDING Story 2.10's `rollover_run`, which AD-9 requires to be
# append-only for the same reason `audit_entry` is. A migration that adds a table must add its
# grant, deliberately. That is a feature.


def _quoted_role() -> tuple[str, sql.Identifier]:
    """Return the configured app-role name and its safely-quoted SQL identifier."""
    app_user = get_settings().app_db_user
    return app_user, sql.Identifier(app_user)


def upgrade() -> None:
    """Create the app role, grant it exactly what it needs, and add the ERD's audit index."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    bind = op.get_bind()
    app_user, role = _quoted_role()
    password = get_settings().app_db_password

    # --- The role (idempotent: `CREATE ROLE` has no `IF NOT EXISTS`) ----------------------------
    already_exists = bind.scalar(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": app_user}
    )
    if not already_exists:
        op.execute(
            sql.SQL(
                "CREATE ROLE {role} LOGIN PASSWORD {password} "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE"
            )
            .format(role=role, password=sql.Literal(password))
            .as_string()
        )
    else:
        # Re-sync the password with `.env` on every upgrade, so rotating APP_DB_PASSWORD needs no
        # out-of-band `psql`. Also repairs a database whose role predates a password change.
        op.execute(
            sql.SQL("ALTER ROLE {role} WITH PASSWORD {password}")
            .format(role=role, password=sql.Literal(password))
            .as_string()
        )

    # --- The grants ------------------------------------------------------------------------------
    # Schema USAGE first: without it, every table grant below is unreachable.
    op.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {role}").format(role=role).as_string())

    for table in _READ_WRITE_TABLES:
        op.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}")
            .format(table=sql.Identifier(table), role=role)
            .as_string()
        )

    for table in _APPEND_ONLY_TABLES:
        # INSERT and SELECT. Not UPDATE. Not DELETE. This one line is AC3.
        op.execute(
            sql.SQL("GRANT INSERT, SELECT ON {table} TO {role}")
            .format(table=sql.Identifier(table), role=role)
            .as_string()
        )

    # No sequence carries a value the app writes through — every primary key is a `uuidv7()` server
    # default, so there is no `SERIAL` and no sequence to advance. The grant is issued anyway (a
    # no-op today) so that the intent is on the record; a future table with a sequence must still
    # add its own grant, exactly as it must add its table grant.
    op.execute(
        sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {role}")
        .format(role=role)
        .as_string()
    )

    # --- The index ERD §4.4 names: "the audit read surface (FR-16)" (NFR-12) ---------------------
    # 0006 created `audit_entry` and said it "needs none this story" — true then: nothing read the
    # trail. Story 2.9 opens the read, so the index lands with the read it serves. Mirrored on
    # `models.AuditEntry.__table_args__` in the same commit, or `alembic check` emits a diff.
    #
    # No index on `occurred_at`, which this story's list actually ORDERs by: the ERD does not name
    # one, and adding an unnamed index is a scope decision this story does not own (Story 2.8's
    # precedent). A sequential scan plus sort is acceptable at Epic-2 volume.
    op.create_index(
        "ix_audit_entry_subject", "audit_entry", ["subject_type", "subject_id"]
    )


def downgrade() -> None:
    """Drop the index, then strip the role of every privilege and drop it.

    `DROP OWNED BY` before `DROP ROLE`: Postgres refuses to drop a role that still holds privileges
    on any object, and `DROP OWNED` is what clears them (the role owns nothing — it was created
    `NOCREATEDB`/`NOCREATEROLE` and every table belongs to the owner — so this drops grants only).
    """
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    op.drop_index("ix_audit_entry_subject", table_name="audit_entry")

    bind = op.get_bind()
    app_user, role = _quoted_role()

    exists = bind.scalar(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": app_user}
    )
    if exists:
        op.execute(sql.SQL("DROP OWNED BY {role}").format(role=role).as_string())
        op.execute(sql.SQL("DROP ROLE {role}").format(role=role).as_string())
