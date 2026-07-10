"""CLI entrypoint for the seed command: `python -m seed`.

Implements: AD-11, AC1 (command three of the setup sequence), AC6, NFR-21.

Mirrors the shape of `python -m app.jobs.rollover`, the other CLI entrypoint the
spine calls for (AD-7). Both are ordinary commands rather than endpoints or startup
hooks, so both are directly callable from a test with no running server.
"""

import datetime
import logging
import sys

from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.core.settings import get_settings
from app.domain import vocabulary
from app.repositories.models import Department, Employee

logger = logging.getLogger("seed")


def seed() -> None:
    """Insert LeaveFlow's seed data. Idempotent: running it twice changes nothing.

    Story 1.2 seeds exactly one Department and exactly one Admin Employee (AC2), both
    taken from the environment (`SEED_DEPARTMENT_NAME`, `SEED_ADMIN_*`). The Admin has
    `manager_id` NULL and `is_active` true — it is the top of every reporting chain and
    the only account that exists before Story 1.6 lets an Admin create others (G1/GAP-5,
    AD-11: the initial password is Admin-supplied, with no reset/change/complexity path).

    Connecting first verifies that DATABASE_URL is reachable and that `alembic upgrade
    head` has already run, which is what makes a failure here legible as "you skipped
    command two" rather than surfacing as a missing table.

    What arrives later:
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

            # Hash the Admin password up front. Settings already reject an empty or
            # CHANGE_ME value; a value over bcrypt's 72-byte limit still slips through,
            # and `hash_password` raises for it — caught here into a legible startup
            # error naming the variable, never a raw traceback (Task 6, trap 3).
            try:
                admin_password_hash = hash_password(settings.seed_admin_password)
            except ValueError as too_long:
                raise SystemExit(str(too_long)) from too_long

            # Department: select-by-name, insert if absent. The ERD declares no
            # `UNIQUE (name)`, so `ON CONFLICT` has no constraint to target here; the
            # seed is single-process, so select-then-insert cannot race. Idempotent:
            # a second run finds the row and reuses its id.
            department_id = connection.execute(
                select(Department.id).where(
                    Department.name == settings.seed_department_name
                )
            ).scalar_one_or_none()

            if department_id is None:
                department_id = connection.execute(
                    Department.__table__.insert()
                    .values(name=settings.seed_department_name)
                    .returning(Department.id)
                ).scalar_one()

            # Admin: INSERT ... ON CONFLICT (email) DO NOTHING, keyed on the UNIQUE
            # email. Idempotent by construction — a second run inserts nothing and
            # leaves the existing hash untouched (so re-seeding never re-salts the
            # Admin out from under a working login). `role` is `vocabulary.ROLE_ADMIN`,
            # never the literal "ADMIN": the AD-21 literal check scans seed/ too.
            connection.execute(
                pg_insert(Employee)
                .values(
                    department_id=department_id,
                    manager_id=None,
                    email=settings.seed_admin_email,
                    full_name=settings.seed_admin_full_name,
                    role=vocabulary.ROLE_ADMIN,
                    joining_date=datetime.date.today(),
                    is_active=True,
                    password_hash=admin_password_hash,
                )
                .on_conflict_do_nothing(index_elements=["email"])
            )

            connection.commit()

            logger.info(
                "Seed complete: one Department (%s) and one Admin (%s) present (AC2).",
                settings.seed_department_name,
                settings.seed_admin_email,
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
