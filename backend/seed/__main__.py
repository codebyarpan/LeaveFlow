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
from sqlalchemy.orm import Session

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.core.settings import get_settings
from app.domain import vocabulary
from app.domain.proration import prorate_entitlement
from app.repositories.models import Department, Employee, LeaveType
from app.services import balances

logger = logging.getLogger("seed")

# The three Leave Types that ship with LeaveFlow, seeded as DATA (AD-11) — never a
# migration, never a `vocabulary.py` constant — so SM-5 holds: a fourth Leave Type is added
# through `POST /leave-types` with no code change and no schema migration. The `code` is the
# only pinned value (EL/CL/FL, ERD §2). No artifact pins the numeric policy, so these are
# sensible project defaults, documented as such in the Story 2.1 Completion Notes:
#   - EL (Earned Leave): 12 days/yr, carries forward, capped at 30 accumulated days.
#   - CL (Casual Leave): 12 days/yr, does not carry forward (cap is meaningless → NULL).
#   - FL (Floater Leave): 2 days/yr, does not carry forward (cap NULL).
# All three seed `requires_supporting_document=False` (spine *Seeding*, PRD §7.3): Story 4.1
# turns the flag on for a later type, and is safe to arrive last because these seed false.
_SEED_LEAVE_TYPES: tuple[dict[str, object], ...] = (
    {
        "code": "EL",
        "name": "Earned Leave",
        "annual_entitlement": 12,
        "carries_forward": True,
        "carry_forward_cap": 30,
        "requires_supporting_document": False,
    },
    {
        "code": "CL",
        "name": "Casual Leave",
        "annual_entitlement": 12,
        "carries_forward": False,
        "carry_forward_cap": None,
        "requires_supporting_document": False,
    },
    {
        "code": "FL",
        "name": "Floater Leave",
        "annual_entitlement": 2,
        "carries_forward": False,
        "carry_forward_cap": None,
        "requires_supporting_document": False,
    },
)


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

    Story 2.1 adds the EL, CL and FL Leave Types, each with
    `requires_supporting_document = false` (`_SEED_LEAVE_TYPES`). AD-11: as data, from
    here — never from a migration, and never as constants in `domain/vocabulary.py`, so
    SM-5 holds and a fourth Leave Type is addable with no code change and no migration.
    Each is inserted with `ON CONFLICT (code) DO NOTHING`, so a re-seed changes nothing.
    """
    settings = get_settings()
    # The APPLICATION role, not the owner (AD-9, Story 2.9). The seed writes the same
    # domain rows the running application writes, so it needs no privilege the app lacks
    # — and running it under the app role makes setup command three a live check of the
    # grants migration 0008 issued. A missing grant fails HERE, loudly, at setup, rather
    # than at the first request that happens to touch the ungranted table.
    engine = create_engine(settings.app_database_url)

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

            # Department: select-by-name, insert if absent. The ERD declares no
            # `UNIQUE (name)`, so `ON CONFLICT` has no constraint to target here.
            # `.limit(1).first()` reuses an existing row and — unlike
            # `scalar_one_or_none()` — does NOT crash if a later story (1.5 onward) has
            # created a second department sharing this name: the seed's contract is to
            # reuse a row, not to police uniqueness the schema deliberately omits. The
            # seed is single-process, so select-then-insert cannot race.
            department_id = connection.execute(
                select(Department.id)
                .where(Department.name == settings.seed_department_name)
                .limit(1)
            ).scalars().first()

            if department_id is None:
                department_id = connection.execute(
                    Department.__table__.insert()
                    .values(name=settings.seed_department_name)
                    .returning(Department.id)
                ).scalar_one()

            # Admin: insert only when absent. The existence check lets a re-seed skip the
            # bcrypt hash (~250ms, cost-12) it would otherwise compute and immediately
            # throw away — the common case, since the Admin already exists after the first
            # run. The INSERT still carries `ON CONFLICT (email) DO NOTHING`, so the
            # check-then-insert is race-safe even though the seed is single-process today.
            admin_exists = (
                connection.execute(
                    select(Employee.id)
                    .where(Employee.email == settings.seed_admin_email)
                    .limit(1)
                ).scalars().first()
                is not None
            )

            if not admin_exists:
                # Hash only on the insert path. Settings already reject an empty or
                # CHANGE_ME value; a value over bcrypt's 72-byte limit still slips
                # through, and `hash_password` raises for it — caught here into a legible
                # startup error naming the variable, never a raw traceback (Task 6,
                # trap 3). `role` is `vocabulary.ROLE_ADMIN`, never the literal "ADMIN":
                # the AD-21 literal check scans seed/ too.
                try:
                    admin_password_hash = hash_password(settings.seed_admin_password)
                except ValueError as too_long:
                    raise SystemExit(str(too_long)) from too_long

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

            # Leave Types (Story 2.1): EL/CL/FL as data. `ON CONFLICT (code) DO NOTHING`
            # against the `UNIQUE (code)` constraint makes each insert idempotent — a
            # re-seed leaves an existing row exactly as it was, matching the Admin idiom
            # above. The seed is single-process, so this cannot race with itself.
            for leave_type in _SEED_LEAVE_TYPES:
                connection.execute(
                    pg_insert(LeaveType)
                    .values(**leave_type)
                    .on_conflict_do_nothing(index_elements=["code"])
                )

            # Story 2.4: materialize the Admin's balance rows (one per Leave Type, current Leave
            # Year), so the seeded Admin has a viewable balance — the create hooks in
            # `create_employee`/`create_leave_type` never fire for the seed's raw inserts. Routes
            # through `balances.set_accrual` only (AD-17), on a Session bound to THIS connection so
            # it shares the seed's single transaction (the outer `connection.commit()` commits it).
            # `set_accrual` is an upsert, so a re-seed leaves exactly one row per pair (idempotent,
            # matching the Admin/Leave-Type idiom above). `carried_forward = 0` (first year).
            admin_id, admin_joining_date = connection.execute(
                select(Employee.id, Employee.joining_date)
                .where(Employee.email == settings.seed_admin_email)
                .limit(1)
            ).one()
            leave_type_rows = connection.execute(
                select(LeaveType.id, LeaveType.annual_entitlement)
            ).all()

            current_year = datetime.date.today().year
            with Session(bind=connection) as session:
                for leave_type_id, annual_entitlement in leave_type_rows:
                    balances.set_accrual(
                        session,
                        employee_id=admin_id,
                        leave_type_id=leave_type_id,
                        leave_year=current_year,
                        prorated_entitlement=prorate_entitlement(
                            annual_entitlement, admin_joining_date, current_year
                        ),
                        carried_forward=0,
                        entitlement_basis=annual_entitlement,
                    )
                session.flush()

            connection.commit()

            logger.info(
                "Seed complete: one Department (%s), one Admin (%s) and %d Leave Types "
                "present (AC2, Story 2.1).",
                settings.seed_department_name,
                settings.seed_admin_email,
                len(_SEED_LEAVE_TYPES),
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
