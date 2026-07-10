"""Fixtures for tests that need a real PostgreSQL.

Implements: the spine's *Testing* row — "`tests/integration/` runs against real
PostgreSQL, and owns SM-1's concurrent double-submit test".

Real PostgreSQL, not SQLite. SM-1's concurrent double-submit test turns on `SELECT
... FOR UPDATE` and on `REPEATABLE READ` semantics that SQLite does not have; a test
suite that swapped the engine would pass while proving nothing about the database the
system actually runs on.
"""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import get_settings


@pytest.fixture(scope="session")
def db_connection() -> Iterator[Connection]:
    """Connect to the configured database, or skip loudly.

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
        connection = engine.connect()
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
        yield connection
    finally:
        connection.close()
        engine.dispose()
