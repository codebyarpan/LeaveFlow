"""The notification table — the FIRST NON-append-only table since `0008` (Story 3.4).

Implements: AC1 (`notification` carries `recipient_employee_id`, `leave_request_id`, a `kind` of
`REQUEST_SUBMITTED`/`REQUEST_APPROVED`/`REQUEST_REJECTED`, a NULLABLE `read_at`, and `created_at`;
and a PARTIAL index on `recipient_employee_id WHERE read_at IS NULL`), FR-14, AD-16, NFR-09.

--- 🚨 THE GRANT IS `SELECT, INSERT, UPDATE` — NOT the append-only shape ---

`0009_rollover_run`, `0010_admin_review_flag` and `0011_policy_change` ALL created APPEND-ONLY
tables and ALL wrote `GRANT INSERT, SELECT`. This table is not one of them, and copying the nearest
template is the single most likely way to break it: `read_at` is MUTABLE — `PATCH
/notifications/{id}/read` writes it — so without `UPDATE` that endpoint fails at RUNTIME with
`InsufficientPrivilege`, while every unit test stays green (only an integration test against real
PostgreSQL catches it). AD-9's append-only list is exactly `audit_entry` and `rollover_run`;
`notification` is deliberately not on it.

`DELETE` is WITHHELD, deliberately: no requirement deletes a Notification, and a read notification
is a fact that happened. Tests clean up through the `owner_engine` fixture (the Story 2.9
precedent), NOT by granting the app role `DELETE` — a test that "fixes" its teardown that way is
deleting the guarantee.

`0008` deliberately issued NO `ALTER DEFAULT PRIVILEGES` (`0008:100-104`) precisely so that "a
migration that adds a table must add its grant, deliberately. That is a feature." Nothing is
inherited here. `0008`'s own `_READ_WRITE_TABLES` tuple is NOT edited: it is historical, it has
already run, and appending to it would change nothing on an existing database while misleading the
next reader into thinking it were a live registry.

--- 🚨 The PARTIAL index, and why `alembic check` cannot defend it ---

`ix_notification_recipient_unread` is the codebase's FIRST partial index (`postgresql_where` appears
nowhere else in `alembic/versions/` or `models.py`). ERD §4.4 names it, and AD-16 is why: the unread
count is `COUNT(*) WHERE read_at IS NULL` and is NEVER stored, so the index that serves it must
carry the same predicate or the count scans the whole table per request.

VERIFIED AGAINST THE INSTALLED PACKAGES: Alembic 1.18.5 contains NO reference to `postgresql_where`
— its PostgreSQL `_dialect_options()` compares only `nulls_not_distinct`. So `alembic check` neither
false-fails on predicate normalization NOR detects a MISSING predicate: a plain, non-partial index
would pass `alembic check`, pass `test_model_migration_agreement`, and pass a name-only `pg_indexes`
assertion, while silently failing AC1. The partial-ness is therefore pinned in
`tests/integration/test_notifications.py` by asserting `pg_indexes.indexdef` CONTAINS the `read_at
IS NULL` predicate — a name-only assertion (the `test_migration_smoke.py` precedent) is NOT
sufficient here, and that test is the only thing standing between this index and a silent
regression.

--- No `ON DELETE` clause on either FK, and that is a decision ---

Neither parent is ever deleted: an Employee is DEACTIVATED, never deleted (AD-22), and a Leave
Request has no DELETE endpoint at all. `ON DELETE CASCADE` would signal a deletion path the product
forbids. The consequence is owned rather than engineered away: an integration teardown that
bulk-deletes `leave_request`/`employee` must delete the notification rows FIRST (Story 3.4, Task 8b)
— exactly where `delete(AuditEntry)` already sits in those same teardowns.

--- `kind` is TEXT + CHECK, never a PostgreSQL ENUM (erd.md:338) ---

The `employee.role` / `leave_request.status` / `policy_change.disposition` shape. The CHECK is an
AD-5 BACKSTOP, never a gate: the three `vocabulary.NOTIFICATION_*` constants are what the services
write, and a `kind` reaching this CHECK as a violation would be a defect and a 500. It is the
database's own copy of the vocabulary — the exemption `test_vocabulary_literals.py` grants
`alembic/versions/` (it is not scanned).

--- This migration writes no ROWS (AD-11) ---

`CREATE TABLE`, `CREATE INDEX` and `GRANT` are schema and privilege statements, not data.
`tests/test_migrations_insert_nothing.py` governs this file and still passes: no `INSERT`, no
`UPDATE … SET`, no `DELETE FROM`.

Revision ID: 0012_notification
Revises: 0011_policy_change
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from psycopg import sql

from app.core.settings import get_settings

# `--sql` (offline) mode is REFUSED, exactly as `0008`–`0011` refuse it: resolving the app-role name
# is a settings read, and the `GRANT` must name a role that exists — neither is checkable without a
# live connection. Failing with a sentence beats emitting a script that silently grants nothing.
_OFFLINE_REFUSAL = (
    "0012_notification cannot run in --sql (offline) mode: its GRANT names the application role "
    "resolved from settings, which requires a live connection to verify. Run `alembic upgrade head` "
    "against the database instead."
)

revision: str = "0012_notification"
down_revision: str | None = "0011_policy_change"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _quoted_role() -> tuple[str, sql.Identifier]:
    """Return the configured app-role name and its safely-quoted SQL identifier.

    Re-declared from `0011` rather than imported: Alembic revisions are loaded as standalone
    modules, not as a package, so `from .0011_policy_change import _quoted_role` is not importable
    across revisions (and the helper is module-private there). "Reuse the pattern" means copy the
    SHAPE — the helper, its `psycopg.sql` quoting, and its refusal to run offline — not import the
    symbol. The role name comes from the environment, so quoting it by hand is how an identifier
    containing a quote becomes an injection; `sql.Identifier` quotes it correctly by construction.
    """
    app_user = get_settings().app_db_user
    return app_user, sql.Identifier(app_user)


def upgrade() -> None:
    """Create `notification` + its PARTIAL index, then grant the app role SELECT, INSERT, UPDATE."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    # AC1's columns exactly, plus the `uuidv7()` PK every table here carries. `read_at` is the ONLY
    # nullable column — and its nullability IS the unread state (AD-16: the count is
    # `COUNT(*) WHERE read_at IS NULL`, never a stored flag).
    op.create_table(
        "notification",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        # WHO it is addressed to. NOT NULL — a notification with no addressee is exactly what AC4
        # forbids (the managerless applicant's submission writes NO `REQUEST_SUBMITTED`, "because it
        # would have no addressee"), and this constraint is what makes that failure loud.
        sa.Column("recipient_employee_id", sa.Uuid(), nullable=False),
        # WHICH Leave Request it concerns. NOT NULL — all three kinds concern one (AD-16).
        sa.Column("leave_request_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        # The ONLY nullable column, and the only MUTABLE one. NULL ⇒ unread.
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # No `ON DELETE` clause on either FK — see the module docstring.
        sa.ForeignKeyConstraint(["recipient_employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["leave_request_id"], ["leave_request.id"]),
        sa.PrimaryKeyConstraint("id"),
        # AC1's enumerated `kind`. TEXT + CHECK, never a PG ENUM (erd.md:338). AD-5 backstop.
        sa.CheckConstraint(
            "kind IN ('REQUEST_SUBMITTED', 'REQUEST_APPROVED', 'REQUEST_REJECTED')",
            name="notification_kind_check",
        ),
    )

    # AC1's PARTIAL index (ERD §4.4, AD-16) — the codebase's first. The predicate is the whole
    # point: it indexes ONLY the unread rows, which is exactly the set `count_unread` counts and the
    # only set anyone queries by recipient. `alembic check` cannot see this predicate (see the module
    # docstring) — `tests/integration/test_notifications.py` asserts it against `pg_indexes.indexdef`.
    op.create_index(
        "ix_notification_recipient_unread",
        "notification",
        ["recipient_employee_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )

    # The LIST index (code review 2026-07-15). The partial index above serves the unread COUNT and
    # nothing else: `GET /notifications` reads `WHERE recipient_employee_id = :x ORDER BY created_at
    # DESC, id DESC` over ALL rows, and read rows fall OUTSIDE the partial predicate — without this,
    # a long-tenured recipient's every page is a full scan + sort over a table that only ever grows
    # (`DELETE` is deliberately withheld). Ascending btree; PostgreSQL walks it backward for the
    # DESC-DESC order.
    op.create_index(
        "ix_notification_recipient_created",
        "notification",
        ["recipient_employee_id", "created_at", "id"],
    )

    # The `leave_request_id` FK carries no index of its own otherwise — and the integration
    # teardowns this table forced on six fixtures (Task 8b) delete notifications BY their parent
    # request, which is a per-delete sequential scan without it.
    op.create_index(
        "ix_notification_leave_request",
        "notification",
        ["leave_request_id"],
    )

    # SELECT, INSERT and UPDATE — NOT the `INSERT, SELECT` append-only shape of `0009`/`0010`/`0011`.
    # `UPDATE` is what makes `PATCH /notifications/{id}/read` work at all. `DELETE` is withheld.
    _, role = _quoted_role()
    op.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE ON {table} TO {role}")
        .format(table=sql.Identifier("notification"), role=role)
        .as_string()
    )


def downgrade() -> None:
    """Drop the table. The index and the grant go with it; the ROLE is `0008`'s to drop, not ours."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    op.drop_table("notification")
