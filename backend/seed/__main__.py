"""CLI entrypoint for the seed command: `python -m seed`.

Implements: AD-11, AC1 (command three of the setup sequence), AC6, NFR-21.

Mirrors the shape of `python -m app.jobs.rollover`, the other CLI entrypoint the
spine calls for (AD-7). Both are ordinary commands rather than endpoints or startup
hooks, so both are directly callable from a test with no running server.
"""

import logging
import sys

from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.logging import configure_logging
from app.core.settings import get_settings

logger = logging.getLogger("seed")


def seed() -> None:
    """Insert LeaveFlow's seed data. Idempotent: running it twice changes nothing.

    Story 1.1 seeds nothing. There is nothing to seed — this story creates no domain
    table (AC6). The command still connects and still exits 0, because AC1 fixes the
    setup as three commands and a third command that cannot run is not a setup step.

    Connecting rather than returning immediately is the point: it verifies that
    DATABASE_URL is reachable and that `alembic upgrade head` has already run, which
    is what makes a failure here legible as "you skipped command two" rather than
    surfacing three stories later as a missing table.

    What arrives, and where:
      - Story 1.2 — the Admin employee and their Department, from SEED_ADMIN_* and
        SEED_DEPARTMENT_NAME.
      - Story 2.1 — the EL, CL and FL Leave Types, each with
        `requires_supporting_document = false`. AD-11: as data, from here. Never from
        a migration, and never as constants in `domain/vocabulary.py` — SM-5 requires
        a fourth Leave Type to be addable with no code change and no schema migration.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)

    try:
        with engine.connect() as connection:
            # Assert that command two of the setup sequence has already run. Alembic
            # creates `alembic_version` on `upgrade`; its absence means the operator ran
            # the seed before the migration.
            stamped = connection.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar_one()

            if not stamped:
                raise SystemExit(
                    "No `alembic_version` table: the database has never been migrated.\n"
                    "Run `alembic upgrade head` (setup command two) before the seed."
                )

            # Story 1.1 seeds nothing, so nothing is inserted and nothing is committed.
            # The seeds that arrive later are idempotent by construction — an
            # INSERT ... ON CONFLICT DO NOTHING keyed on the natural key, never a
            # "SELECT then INSERT if absent", which races against a concurrent seed.
            logger.info(
                "Seed complete: nothing to seed in Story 1.1 "
                "(no domain table exists yet — AC6, AD-11)."
            )
    finally:
        # On every path, including failure — an abandoned pool is a leak the
        # operator cannot see.
        engine.dispose()


def main() -> int:
    """Run the seed, returning a process exit status.

    Every anticipated failure exits with a message legible as a setup mistake —
    "you skipped command two", "postgres is not up", "your .env is incomplete" —
    never a raw traceback. An unanticipated failure still tracebacks, and should:
    it is a bug here, not an operator error.
    """
    configure_logging()

    try:
        seed()
    except SystemExit as exit_request:
        logger.error("%s", exit_request)
        return 1
    except OperationalError as unreachable:
        logger.error(
            "Cannot connect to the database: %s\n"
            "Is the stack running? `docker compose up` is setup command one.",
            unreachable.orig,
        )
        return 1
    except ValidationError as invalid:
        logger.error(
            "Settings are incomplete or still placeholders — fix .env "
            "(see .env.example):\n%s",
            invalid,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
