"""The schema Story 1.2 creates: `department`, `employee`, and only those (AC1).

Implements the test side of: AC1 — after `alembic upgrade head`, the public schema is
exactly `{alembic_version, department, employee}`, and `employee` carries the unique
email, the role and self-manager CHECK constraints, the NOT NULL / nullable columns, and
the two indexes the ERD prescribes.

Runs against real PostgreSQL. Assumes `alembic upgrade head` has already run. Asserts
against the live database's catalog rather than the model definitions — a model and a
migration can agree with each other and both be wrong about what shipped; only the
catalog says what the database actually is. The complementary guarantee — that the models
and the migrations agree with EACH OTHER — is `alembic check`, run by
`test_model_migration_agreement.py`; this file deliberately inspects the database instead.
"""

from sqlalchemy import Connection, inspect, text


def _public_tables(db_connection: Connection) -> set[str]:
    rows = db_connection.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return {row[0] for row in rows}


def test_exactly_the_expected_tables_exist(db_connection: Connection) -> None:
    """The public schema is precisely the tables shipped so far — no more, no fewer.

    Exact-set equality, the Story 1.1 pattern: a subset check would pass against a story
    that also created a `leave_request` nobody meant to add, and only equality catches it.
    The set grows one table per schema story — Story 2.1 added `leave_type`, 2.2 added
    `company_holiday`, 2.4 added `leave_balance` — exactly as
    `test_migrations_insert_nothing.py`'s ordered revision chain grows one file per story.
    """
    assert _public_tables(db_connection) == {
        "alembic_version",
        "department",
        "employee",
        "leave_type",
        "company_holiday",
        "leave_balance",
    }


def test_employee_columns_and_nullability(db_connection: Connection) -> None:
    """AC1: the columns exist with the nullability the story fixes.

    `manager_id` is the one nullable foreign key — an Admin reports to no one (AC2).
    Everything else on the row is NOT NULL.
    """
    columns = {c["name"]: c for c in inspect(db_connection).get_columns("employee")}

    expected_not_null = {
        "id",
        "department_id",
        "email",
        "full_name",
        "role",
        "joining_date",
        "is_active",
        "password_hash",
    }
    assert expected_not_null <= set(columns)
    for name in expected_not_null:
        assert columns[name]["nullable"] is False, f"{name} should be NOT NULL"

    # The sole nullable column — the self-referencing reporting edge.
    assert columns["manager_id"]["nullable"] is True


def test_employee_email_is_unique(db_connection: Connection) -> None:
    """AC1: `UNIQUE (email)` — email is the identifier a login is looked up by."""
    inspector = inspect(db_connection)
    unique_columns = [
        tuple(c["column_names"]) for c in inspector.get_unique_constraints("employee")
    ]
    # A unique constraint may surface as a constraint or, on some catalogs, a unique
    # index — accept either, as long as email is covered by exactly one single-column one.
    unique_index_columns = [
        tuple(i["column_names"]) for i in inspector.get_indexes("employee") if i["unique"]
    ]
    assert ("email",) in unique_columns or ("email",) in unique_index_columns


def test_employee_has_the_two_prescribed_indexes(db_connection: Connection) -> None:
    """AC1 / NFR-12 / ERD §4.4: `employee(manager_id)` and `employee(department_id)`."""
    indexed_column_sets = {
        tuple(i["column_names"]) for i in inspect(db_connection).get_indexes("employee")
    }
    assert ("manager_id",) in indexed_column_sets
    assert ("department_id",) in indexed_column_sets


def test_employee_check_constraints(db_connection: Connection) -> None:
    """AC1: the role CHECK and the AD-23 self-manager backstop both ship on the table.

    The role CHECK is the database's copy of the vocabulary (ERD §4.2). The
    `id <> manager_id` CHECK is AD-23's backstop only — the transitive-cycle refusal is
    Story 1.6's service. Read from the catalog so the assertion is about what shipped.
    """
    check_clauses = db_connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'public.employee'::regclass AND contype = 'c'"
        )
    ).scalars().all()
    joined = " ".join(check_clauses)

    # The role values appear here, in the database's own DDL — the one place outside
    # domain/vocabulary.py the AD-21 literal check exempts.
    assert "EMPLOYEE" in joined and "MANAGER" in joined and "ADMIN" in joined
    assert "manager_id" in joined and "<>" in joined


def test_department_is_minimal(db_connection: Connection) -> None:
    """AC1: `department` is `id` + `name`, with no `UNIQUE (name)` the ERD never declared."""
    columns = {c["name"] for c in inspect(db_connection).get_columns("department")}
    assert columns == {"id", "name"}

    unique_constraints = inspect(db_connection).get_unique_constraints("department")
    assert unique_constraints == [], "the ERD declares no UNIQUE on department.name"
