"""The supporting_document table — the evidence a Leave Request carries (Story 4.1).

Implements: AC1 (`supporting_document` carries `leave_request_id` under a NAMED
`UNIQUE (leave_request_id)`, a `storage_name`, an `original_filename` and a `content_type`,
and NO `size_bytes` — size is validated before the bytes are written and no requirement
reads it afterwards, ERD §2.1), FR-13, NFR-05, AD-15.

--- What each column is, and what is deliberately absent ---

- `leave_request_id` — the ONE request this document evidences. `UNIQUE`: a request carries
  at most one document (ERD §4.2 names exactly this constraint and no other). The
  constraint is the AD-5 BACKSTOP, never the gate: `services/documents.py` resolves
  existing-document state (attach-or-replace while PENDING) before any INSERT, so a second
  upload is a decided UPDATE, never an `IntegrityError` surfacing as a raw 500.
- `storage_name` — a server-generated UUID; the file on the volume is named `str(uuid)`,
  NO extension (an extension would be derived from client input, the thing AD-15 forbids
  in paths; the stored `content_type` serves the stream). Typed `sa.Uuid()` per the ERD's
  logical model (erd.md:112).
- `original_filename` — the client-supplied filename, persisted VERBATIM as DATA (NFR-05):
  it never becomes a path component, and on GET it leaves only inside an RFC 5987-encoded
  `Content-Disposition` header.
- `content_type` — the declared type the upload validated against. NO CHECK constraint
  (Open Decision #7): erd.md §4.2 lists exactly one constraint for this table (the UNIQUE),
  and the allowlist is service-layer policy declared once in `domain/vocabulary.py` — a
  CHECK would be a second copy of a vocabulary that already lives in one place. This
  diverges from the `notification.kind` precedent because THERE the ERD named the CHECK;
  here it deliberately does not.
- NO `size_bytes` — AC1 pins its ABSENCE. NO timestamp — the ERD names none; an upload is
  not a state transition and writes no audit row (AD-8, SM-4 stays exactly 14).

--- The GRANT is `SELECT, INSERT, UPDATE` — the 0012 shape, per mutability ---

Open Decision #2's replace path MUTATES the row (a second upload while the request is
PENDING replaces `storage_name`/`original_filename`/`content_type` in place), so `UPDATE`
is granted — this is NOT one of the append-only tables (`0009`/`0010`/`0011`). `DELETE` is
WITHHELD: no requirement deletes a document, and tests clean up through the `owner_engine`
fixture (the Story 2.9 precedent). `0008` deliberately issued no `ALTER DEFAULT
PRIVILEGES`, so nothing is inherited: a migration that adds a table adds its grant,
deliberately.

--- No `ON DELETE` clause on the FK, and that is a decision ---

A Leave Request has no DELETE endpoint at all (the `0012` reasoning). The consequence is
owned rather than engineered away: an integration teardown that bulk-deletes
`leave_request` must delete `supporting_document` rows FIRST — and unlink the files those
rows name, because files outlive rows (Story 4.1, Landmine 8).

--- This migration writes no ROWS (AD-11) ---

`CREATE TABLE` and `GRANT` are schema and privilege statements, not data.
`tests/test_migrations_insert_nothing.py` governs this file: no `INSERT`, no
`UPDATE … SET`, no `DELETE FROM`.

Revision ID: 0013_supporting_document
Revises: 0012_notification
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from psycopg import sql

from app.core.settings import get_settings

# `--sql` (offline) mode is REFUSED, exactly as `0008`–`0012` refuse it: resolving the app-role name
# is a settings read, and the `GRANT` must name a role that exists — neither is checkable without a
# live connection. Failing with a sentence beats emitting a script that silently grants nothing.
_OFFLINE_REFUSAL = (
    "0013_supporting_document cannot run in --sql (offline) mode: its GRANT names the application "
    "role resolved from settings, which requires a live connection to verify. Run `alembic upgrade "
    "head` against the database instead."
)

revision: str = "0013_supporting_document"
down_revision: str | None = "0012_notification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _quoted_role() -> tuple[str, sql.Identifier]:
    """Return the configured app-role name and its safely-quoted SQL identifier.

    Re-declared from `0012` rather than imported: Alembic revisions are loaded as standalone
    modules, not as a package, so the helper is not importable across revisions. "Reuse the
    pattern" means copy the SHAPE — the helper, its `psycopg.sql` quoting, and its refusal to
    run offline — not import the symbol. The role name comes from the environment, so quoting
    it by hand is how an identifier containing a quote becomes an injection; `sql.Identifier`
    quotes it correctly by construction.
    """
    app_user = get_settings().app_db_user
    return app_user, sql.Identifier(app_user)


def upgrade() -> None:
    """Create `supporting_document`, then grant the app role SELECT, INSERT, UPDATE."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    # AC1's columns exactly, plus the `uuidv7()` PK every table here carries. NO `size_bytes`
    # (AC1 pins the absence), no timestamp (ERD names none), no `content_type` CHECK (OD#7).
    op.create_table(
        "supporting_document",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        # WHICH Leave Request this document evidences. NOT NULL, and UNIQUE below: a request
        # carries at most one document (ERD §4.2). No `ON DELETE` clause — see the docstring.
        sa.Column("leave_request_id", sa.Uuid(), nullable=False),
        # The server-generated name the file is stored under — `str(uuid)`, no extension.
        # Nothing client-supplied ever concatenates into a path (AD-15).
        sa.Column("storage_name", sa.Uuid(), nullable=False),
        # The client's filename, persisted VERBATIM as DATA (NFR-05) — never a path component.
        sa.Column("original_filename", sa.Text(), nullable=False),
        # The declared type the upload validated against; serves the GET's Content-Type.
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["leave_request_id"], ["leave_request.id"]),
        sa.PrimaryKeyConstraint("id"),
        # ERD §4.2's one constraint for this table, NAMED so the model mirrors it byte-for-byte
        # (`alembic check`). The AD-5 BACKSTOP — the service decides attach-or-replace first.
        sa.UniqueConstraint(
            "leave_request_id", name="supporting_document_leave_request_id_key"
        ),
    )

    # SELECT, INSERT and UPDATE — the `0012` shape, NOT the `INSERT, SELECT` append-only one:
    # OD#2's replace path UPDATEs the row in place. `DELETE` is withheld.
    _, role = _quoted_role()
    op.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE ON {table} TO {role}")
        .format(table=sql.Identifier("supporting_document"), role=role)
        .as_string()
    )


def downgrade() -> None:
    """Drop the table. The grant goes with it; the ROLE is `0008`'s to drop, not ours."""
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)

    op.drop_table("supporting_document")
