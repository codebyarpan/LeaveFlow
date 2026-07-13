"""After `alembic upgrade head`, `alembic_version` is stamped at the current head.

Implements the test side of: AC1 (command two of the setup sequence), AD-11.

Runs against real PostgreSQL. Assumes `alembic upgrade head` has already run — which
is exactly the state AC1's sequence leaves the database in.

The exact *shape* of the schema at head — that it is precisely `department` and
`employee` and their constraints — is `test_schema_1_2.py`'s job (Story 1.2). This file
keeps only the migration-mechanics smoke: the version table is stamped, and no migration
ever seeded a Leave Type row.
"""

from sqlalchemy import Connection, text

# The current head revision. It moves forward one story at a time; the assertion below
# keeps its meaning — "the database is stamped at head", not "at some revision or other".
# Story 2.1 advanced it to `0003_leave_type`.
HEAD_REVISION = "0003_leave_type"


def _public_tables(db_connection: Connection) -> set[str]:
    rows = db_connection.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return {row[0] for row in rows}


def test_alembic_version_exists_and_is_stamped_at_head(db_connection: Connection) -> None:
    """`alembic_version` exists and carries exactly the head revision.

    The row is what distinguishes "migrated and up to date" from "never migrated".
    With zero revision files Alembic would create this table and leave it EMPTY, and
    deployment tooling reads an empty `alembic_version` as the latter.
    """
    assert "alembic_version" in _public_tables(db_connection)

    versions = db_connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()

    assert versions == [HEAD_REVISION]


def test_leave_type_table_shipped_with_its_columns_and_unique_code(
    db_connection: Connection,
) -> None:
    """Story 2.1: `0003` created `leave_type` with its seven columns and `UNIQUE (code)`.

    This assertion stood vacuously through Story 1.2 as a tripwire — "the day Story 2.1
    creates the table, the assertion is already standing" — and now that the table exists it
    is repointed at what it can still prove from the live catalog: the table shipped, with the
    ERD's seven columns and the `UNIQUE (code)` the whole duplicate-`code` 409 story rests on.

    Its original claim — that no *migration* inserted a Leave Type row — is not a stable
    DB-runtime fact once the seed legitimately populates the table, so AD-11's row-provenance
    is enforced where it can be proven unambiguously: statically in
    `tests/test_migrations_insert_nothing.py` (every migration's AST, `0003` included) for the
    migration side, and in `tests/integration/test_seed.py` for the seed side.
    """
    columns = db_connection.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'leave_type'"
        )
    ).scalars().all()
    assert set(columns) == {
        "id",
        "code",
        "name",
        "annual_entitlement",
        "carries_forward",
        "carry_forward_cap",
        "requires_supporting_document",
    }

    unique_defs = db_connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'public.leave_type'::regclass AND contype = 'u'"
        )
    ).scalars().all()
    assert any("(code)" in definition for definition in unique_defs), (
        "leave_type must carry UNIQUE (code) — the AD-5 backstop the duplicate-code 409 "
        "story depends on"
    )
