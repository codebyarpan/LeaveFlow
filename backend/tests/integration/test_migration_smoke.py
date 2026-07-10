"""After `alembic upgrade head`, `alembic_version` exists and no domain table does.

Implements the test side of: AC6, AC1 (command two of the setup sequence), AD-11.
This is the third of the three substantive tests the story's *Testing standards*
section names.

Runs against real PostgreSQL. Assumes `alembic upgrade head` has already run — which
is exactly the state AC1's sequence leaves the database in.
"""

from sqlalchemy import Connection, text

# The single revision Story 1.1 ships. When Story 1.2 adds the first real migration,
# this constant moves and the assertion below keeps its meaning: "the database is
# stamped at head", not "the database is stamped at some revision or other".
BASELINE_REVISION = "0001_baseline"


def _public_tables(db_connection: Connection) -> set[str]:
    rows = db_connection.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return {row[0] for row in rows}


def test_alembic_version_exists_and_is_stamped(db_connection: Connection) -> None:
    """AC6: `alembic_version` exists and carries exactly one row.

    The row is what distinguishes "migrated and up to date" from "never migrated".
    With zero revision files Alembic would create this table and leave it EMPTY, and
    deployment tooling reads an empty `alembic_version` as the latter.
    """
    assert "alembic_version" in _public_tables(db_connection)

    versions = db_connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()

    assert versions == [BASELINE_REVISION]


def test_no_domain_table_exists(db_connection: Connection) -> None:
    """AC6: this story creates no domain table.

    Asserted as an exact set rather than a set of absences. `assert "employee" not in
    tables` would pass against a story that created `leave_request` instead; only
    equality catches the table nobody thought to name.
    """
    assert _public_tables(db_connection) == {"alembic_version"}


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
        "`leave_type` exists after Story 1.1's migration. AC6 forbids this story from "
        "creating a domain table, and AD-11 forbids any migration from inserting a "
        "Leave Type row."
    )
