"""Fixtures for tests that need a real PostgreSQL.

Implements: the spine's *Testing* row — "`tests/integration/` runs against real
PostgreSQL, and owns SM-1's concurrent double-submit test".

Real PostgreSQL, not SQLite. SM-1's concurrent double-submit test turns on `SELECT
... FOR UPDATE` and on `REPEATABLE READ` semantics that SQLite does not have; a test
suite that swapped the engine would pass while proving nothing about the database the
system actually runs on.

--- Two roles, so two engines (AD-9, Story 2.9) ---

Since Story 2.9 the application connects as a NON-OWNER role that holds `INSERT` and
`SELECT` on `audit_entry` and neither `UPDATE` nor `DELETE` — that missing grant is what
makes the trail append-only in the database (AC3, NFR-09). `app.repositories.engine.
get_engine()` is that app-role engine, and it is what the code under test uses.

It follows that a test CANNOT clean up its own audit rows through `get_engine()`: the
delete is refused, which is exactly the guarantee working. Cleanup is a MAINTENANCE
operation, so it runs as the OWNER — `owner_engine` below. That asymmetry is the point;
a test tempted to "fix" it by granting the app role `DELETE` would be deleting AC3.
"""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import get_settings
from app.repositories.engine import get_engine


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    """The OWNER-role engine: schema inspection and test cleanup (AD-9).

    The owner owns every table and is the role Alembic runs as, so it is the only role
    that can delete an `audit_entry` row — which is what teardown must do to leave the
    database as it found it. Test SETUP and the code under test both go through the
    app-role `get_engine()`; only teardown reaches for this.

    Skipping rather than failing when PostgreSQL is absent is a deliberate trade: a
    developer running `pytest` without `docker compose up` should see a clear reason,
    not a stack trace. That promise has to cover every way setup can be incomplete —
    a missing or placeholder `.env` (ValidationError) and a malformed URL
    (ArgumentError) as much as an unreachable server (OperationalError) — or the
    "skip with a reason" is a lie on exactly the machines that need it. The risk of
    a skip that silently masks a real failure is covered by Task 10, which runs the
    whole sequence from a clean state.
    """
    try:
        engine = create_engine(get_settings().database_url)
        engine.connect().close()
    except ValidationError as incomplete:
        pytest.skip(
            "Settings are incomplete or still placeholders — integration tests "
            f"skipped. Fix .env (see .env.example). ({incomplete.error_count()} "
            "invalid value(s))"
        )
    except SQLAlchemyError as unreachable:
        pytest.skip(
            "PostgreSQL is not reachable with the configured settings — integration "
            "tests skipped. Run `docker compose up -d` first, then "
            "`docker compose exec api alembic upgrade head`. "
            f"({type(unreachable).__name__})"
        )

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def db_connection(owner_engine: Engine) -> Iterator[Connection]:
    """An owner connection, and the proof that the APP role can connect too.

    The app role is created by migration `0008`, not by the container's init path — so
    "Postgres is up but the app role does not exist" is a REAL state: it is precisely a
    database on which setup command two has not been run. Left unchecked it would surface
    as an `OperationalError` inside the first test that opened an app-role session, i.e. a
    hard failure where the whole point of this module is a loud, actionable skip. So the
    app-role connection is proved HERE, once, and its absence skips with the command that
    fixes it.
    """
    try:
        get_engine().connect().close()
    except SQLAlchemyError as no_app_role:
        pytest.skip(
            "The application database role cannot connect — integration tests skipped. "
            "It is provisioned by migration 0008, so run `alembic upgrade head` (setup "
            "command two); check APP_DB_USER / APP_DB_PASSWORD in .env against it. "
            f"({type(no_app_role).__name__})"
        )

    connection = owner_engine.connect()
    try:
        yield connection
    finally:
        connection.close()
