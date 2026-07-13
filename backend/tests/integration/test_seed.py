"""The seed creates exactly one Department and one Admin, and is idempotent (AC2).

Implements the test side of: AC2 — after the seed, exactly one Department and exactly one
Admin Employee exist, both from the environment, the Admin with `manager_id` NULL and
`is_active` true — and Task 6's requirement that running the seed twice changes nothing.

Runs against real PostgreSQL. Calls `seed.__main__.seed()` directly (no subprocess), the
same entrypoint `python -m seed` invokes, so a test needs no running server.
"""

from sqlalchemy import Connection, text

from app.core.settings import get_settings
from app.domain import vocabulary
from seed.__main__ import seed


def _count(db_connection: Connection, table: str, where: str, value: str) -> int:
    return db_connection.execute(
        text(f"SELECT count(*) FROM {table} WHERE {where} = :value"), {"value": value}
    ).scalar_one()


def test_seed_creates_one_admin_and_one_department(db_connection: Connection) -> None:
    """AC2: exactly one seed Department and one seed Admin exist after seeding."""
    settings = get_settings()
    seed()  # idempotent — safe whether or not a prior run already seeded

    assert _count(db_connection, "department", "name", settings.seed_department_name) == 1
    assert _count(db_connection, "employee", "email", settings.seed_admin_email) == 1


def test_seeded_admin_is_a_top_of_chain_active_admin(db_connection: Connection) -> None:
    """AC2: the Admin has `manager_id` NULL, `is_active` true, and the ADMIN role."""
    settings = get_settings()
    seed()

    row = db_connection.execute(
        text(
            "SELECT role, is_active, manager_id IS NULL AS no_manager "
            "FROM employee WHERE email = :email"
        ),
        {"email": settings.seed_admin_email},
    ).one()

    assert row.role == vocabulary.ROLE_ADMIN
    assert row.is_active is True
    assert row.no_manager is True


def test_running_the_seed_twice_changes_nothing(db_connection: Connection) -> None:
    """Task 6: the seed is idempotent — a second run inserts no duplicate rows."""
    settings = get_settings()

    seed()
    seed()

    assert _count(db_connection, "department", "name", settings.seed_department_name) == 1
    assert _count(db_connection, "employee", "email", settings.seed_admin_email) == 1


# --- Story 2.1 (AC2): EL/CL/FL arrive as data, false-documented, idempotently -----------


def test_seed_creates_the_three_leave_types_document_free(db_connection: Connection) -> None:
    """AC2: after the seed, EL/CL/FL exist, each with `requires_supporting_document = false`.

    They enter through the seed command as DATA (AD-11), never a migration — which is what
    `test_migrations_insert_nothing.py` enforces from the other side.
    """
    seed()

    for code in ("EL", "CL", "FL"):
        row = db_connection.execute(
            text(
                "SELECT requires_supporting_document AS needs_doc "
                "FROM leave_type WHERE code = :code"
            ),
            {"code": code},
        ).one()
        assert row.needs_doc is False


def test_running_the_seed_twice_leaves_one_row_per_leave_type(
    db_connection: Connection,
) -> None:
    """AC2 idempotency: a second seed run inserts no duplicate Leave Type (ON CONFLICT)."""
    seed()
    seed()

    for code in ("EL", "CL", "FL"):
        assert _count(db_connection, "leave_type", "code", code) == 1
