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
# Story 2.4 advanced it to `0005_leave_balance`.
HEAD_REVISION = "0005_leave_balance"


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


def test_company_holiday_table_shipped_with_its_columns_and_unique_date(
    db_connection: Connection,
) -> None:
    """Story 2.2: `0004` created `company_holiday` with its three columns and `UNIQUE (holiday_date)`.

    Mirrors the leave_type smoke: the table shipped with exactly the ERD's columns, and — the
    point of AC2 — `holiday_date`'s `data_type` is `date`, closing the DATE discipline
    (AD-12/DR-2a) at the live catalog rather than only in the model. The `UNIQUE (holiday_date)`
    is the AD-5 backstop the duplicate-date 409 story rests on.
    """
    columns = {
        row[0]: row[1]
        for row in db_connection.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'company_holiday'"
            )
        )
    }
    assert set(columns) == {"id", "holiday_date", "name"}
    # AC2 at the catalog: the column is a calendar DATE, never a timestamp.
    assert columns["holiday_date"] == "date"

    unique_defs = db_connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'public.company_holiday'::regclass AND contype = 'u'"
        )
    ).scalars().all()
    assert any("(holiday_date)" in definition for definition in unique_defs), (
        "company_holiday must carry UNIQUE (holiday_date) — the AD-5 backstop the "
        "duplicate-date 409 story depends on"
    )


def test_leave_balance_table_shipped_with_its_columns_checks_and_unique(
    db_connection: Connection,
) -> None:
    """Story 2.4: `0005` created `leave_balance` with its columns, the three CHECKs and the UNIQUE.

    Mirrors the leave_type/company_holiday smokes, proving from the live catalog what the story
    rests on: the seven quantity columns (all INTEGER) plus the two FKs and `id`; NO `available`
    column (DR-3/AD-5 — it is derived, never stored); the three AD-5 backstop CHECKs; and the
    `UNIQUE (employee_id, leave_type_id, leave_year)` whose implicit btree index serves the
    `FOR UPDATE` lock (ERD §4.4).
    """
    columns = {
        row[0]: row[1]
        for row in db_connection.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'leave_balance'"
            )
        )
    }
    assert set(columns) == {
        "id",
        "employee_id",
        "leave_type_id",
        "leave_year",
        "accrued",
        "prorated_entitlement",
        "carried_forward",
        "entitlement_basis",
        "reserved",
        "consumed",
    }
    # No stored `available` — it is derived at the projection (DR-3, AD-5).
    assert "available" not in columns
    # The quantity columns are INTEGER (DR-10), never NUMERIC/float.
    for quantity in (
        "leave_year",
        "accrued",
        "prorated_entitlement",
        "carried_forward",
        "entitlement_basis",
        "reserved",
        "consumed",
    ):
        assert columns[quantity] == "integer"

    check_defs = db_connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'public.leave_balance'::regclass AND contype = 'c'"
        )
    ).scalars().all()
    # PostgreSQL normalizes and re-parenthesizes the expression (`(accrued - consumed) - reserved`),
    # so match the normalized forms rather than the source SQL string.
    joined_checks = " ".join(check_defs)
    assert "(accrued - consumed) - reserved" in joined_checks, (
        "leave_balance must carry CHECK (accrued - consumed - reserved >= 0) — the AD-5 backstop"
    )
    assert "reserved >= 0" in joined_checks and "consumed >= 0" in joined_checks
    assert "prorated_entitlement + carried_forward" in joined_checks, (
        "leave_balance must carry the accrual-composition CHECK (AD-5)"
    )

    unique_defs = db_connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'public.leave_balance'::regclass AND contype = 'u'"
        )
    ).scalars().all()
    assert any(
        "(employee_id, leave_type_id, leave_year)" in definition
        for definition in unique_defs
    ), (
        "leave_balance must carry UNIQUE (employee_id, leave_type_id, leave_year) — one balance "
        "per pair per year, whose implicit index is the FOR UPDATE access path (ERD §4.4)"
    )
