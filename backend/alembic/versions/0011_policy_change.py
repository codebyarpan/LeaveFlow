"""The policy-change log — the FOURTH append-only table, with its own grant (Story 2.12).

Implements: AC1 (`policy_change` carries the `leave_type_id`, the `attribute` changed, its
`old_value` and `new_value`, the `disposition` chosen, and `occurred_at`, with `CHECK (disposition
IN ('RECALCULATE','PRESERVE'))`; it carries NO actor column, BY DECISION; and it is NOT
`audit_entry`), FR-06, AD-8, AD-9, AD-20, NFR-09.

--- This table INHERITS NOTHING, and that is deliberate ---

`0008_audit_read_surface` provisioned the least-privilege application role and deliberately did NOT
issue `ALTER DEFAULT PRIVILEGES` — that would blanket-grant `UPDATE` and `DELETE` to every table the
owner creates from then on, INCLUDING this one. `0009_rollover_run` was the first table to pay for
that decision, `0010_admin_review_flag` the second, and this is the third. A table that adds itself
must add its grant, deliberately.

The grant below is ONE line and one shape:

    GRANT INSERT, SELECT ON policy_change TO <app_role>;

Not `UPDATE`. Not `DELETE`. A policy change is a historical fact: it happened, at a moment, under a
disposition the Admin chose. Rewriting it later would rewrite the reason a balance is the number it
is, which is exactly the "wrong figure that will be believed" PRD §1 exists to prevent.

--- There is NO actor column, and that is a DECISION, not an omission (AC1, AD-20) ---

PRD §1 promises attribution for LEAVE REQUEST state changes — that is `audit_entry`'s job, and
`audit_entry` has `actor_type`/`actor_id` for exactly that reason. It promises no attribution for a
configuration change, and the ERD (§POLICY_CHANGE) names no actor column. So none is invented here.
The row records WHAT changed, FROM what, TO what, under WHICH disposition, and WHEN — and the role
gate on `PATCH /leave-types/{id}` already guarantees only an Admin could have caused it.

--- Why `old_value` / `new_value` are TEXT ---

ONE column pair must carry three different types: an `int` (`annual_entitlement`), a NULLABLE int
(`carry_forward_cap`) and a `bool` (`carries_forward`). erd.md L151-152 types them TEXT for that
reason. The service stringifies at the boundary and renders a `None` cap as the string `"null"`, so
the columns stay NOT NULL and "the cap was REMOVED" stays distinguishable from "there never was a
cap" (Open Decision #6).

--- Why `_quoted_role()` is re-declared rather than imported ---

Alembic revisions are loaded as standalone modules, not as a package: `from .0010_admin_review_flag
import _quoted_role` is not importable across revisions (and the helper is module-private anyway).
"Reuse 0010's pattern" therefore means copy the SHAPE — the helper, its `psycopg.sql` quoting, and
its refusal to run offline — not import the symbol.

Nothing else is granted here. `GRANT USAGE ON SCHEMA public` and `GRANT USAGE ON ALL SEQUENCES` were
both issued by `0008` and are not re-issued: the schema grant is not per-table, and `uuidv7()` is a
server default that uses no sequence.

--- This migration writes no ROWS (AD-11) ---

`CREATE TABLE` and `GRANT` are schema and privilege statements, not data.
`tests/test_migrations_insert_nothing.py` governs this file and still passes: no `INSERT`, no
`UPDATE … SET`, no `DELETE FROM`.

Revision ID: 0011_policy_change
Revises: 0010_admin_review_flag
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from psycopg import sql

from app.core.settings import get_settings

# `--sql` (offline) mode is REFUSED, exactly as `0008`, `0009` and `0010` refuse it: resolving the
# app-role name is a settings read, and the `GRANT` must name a role that exists — neither is
# checkable without a live connection. Failing with a sentence beats emitting a script that silently
# grants nothing.
_OFFLINE_REFUSAL = (
    "0011_policy_change cannot run in --sql (offline) mode: its GRANT names the application role "
    "resolved from settings, which requires a live connection to verify. Run `alembic upgrade head` "
    "against the database instead."
)

revision: str = "0011_policy_change"
down_revision: str | None = "0010_admin_review_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _quoted_role() -> tuple[str, sql.Identifier]:
    """Return the configured app-role name and its safely-quoted SQL identifier.

    Re-declared from `0010` rather than imported: Alembic revisions are not a package, and the
    helper is module-private there. The role name comes from the environment, so quoting it by hand
    is how an identifier containing a quote becomes an injection — `sql.Identifier` quotes it
    correctly by construction.
    """
    app_user = get_settings().app_db_user
    return app_user, sql.Identifier(app_user)


def upgrade() -> None:
    """Create `policy_change`, then grant the app role INSERT and SELECT — and nothing else."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    # AC1's columns exactly, plus the `uuidv7()` PK every table here carries. NO actor column (by
    # decision, above). `occurred_at`, not the ERD's `changed_at`: the AC is binding, and
    # `audit_entry`, `rollover_run` and `admin_review_flag` all already ship `occurred_at` — the
    # same clash Story 2.11 hit (`raised_at`) and resolved in the AC's favour.
    op.create_table(
        "policy_change",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("attribute", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["leave_type_id"], ["leave_type.id"]),
        sa.PrimaryKeyConstraint("id"),
        # AC1's one non-negotiable constraint. A BACKSTOP, never a gate (AD-5): the service
        # validates the disposition against the two `vocabulary.DISPOSITION_*` constants and raises
        # a typed `400 POLICY_DISPOSITION_REQUIRED` first, so this CHECK never reaches a client as a
        # raw 500. It is the database's own copy of the vocabulary — the exemption
        # `test_vocabulary_literals.py` grants `alembic/versions/` (it is not scanned), exactly as
        # `employee.role` and `leave_request.status` do.
        sa.CheckConstraint(
            "disposition IN ('RECALCULATE', 'PRESERVE')",
            name="policy_change_disposition_check",
        ),
    )

    # INSERT and SELECT. Not UPDATE. Not DELETE. This one statement is what makes the log a log.
    _, role = _quoted_role()
    op.execute(
        sql.SQL("GRANT INSERT, SELECT ON {table} TO {role}")
        .format(table=sql.Identifier("policy_change"), role=role)
        .as_string()
    )


def downgrade() -> None:
    """Drop the table. The grant goes with it; the ROLE itself is `0008`'s to drop, not ours."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    op.drop_table("policy_change")
