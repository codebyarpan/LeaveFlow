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
HEAD_REVISION = "0002_department_and_employee"


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


def test_no_leave_type_row_was_inserted_by_a_migration(db_connection: Connection) -> None:
    """AD-11: seeding is the seed command's job, never a migration's.

    Vacuous today — `leave_type` does not exist, so a migration cannot have populated
    it. Asserted here anyway so that the day Story 2.1 creates the table, the
    assertion is already standing and already watching.
    """
    leave_type_exists = db_connection.execute(
        text("SELECT to_regclass('public.leave_type') IS NOT NULL")
    ).scalar_one()

    assert not leave_type_exists, (
        "`leave_type` exists before Story 2.1. AD-11 forbids any migration from "
        "inserting a Leave Type row — the table and its rows arrive via the seed."
    )
