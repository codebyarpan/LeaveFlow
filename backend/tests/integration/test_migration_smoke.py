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
# Story 2.6 advanced it to `0006_leave_request` (leave_request + audit_entry); Story 2.8 to
# `0007_cancellation_request` (the cancellation_request table); Story 2.9 to
# `0008_audit_read_surface` (the least-privilege app role + its grants + the ERD's audit index —
# the first migration that moves PRIVILEGES rather than tables). Story 2.10 to
# `0009_rollover_run` (the rollover's append-only execution log, with its own INSERT/SELECT grant).
# Story 2.11 to `0010_admin_review_flag` (the refusal register — the THIRD append-only table, again
# with its own INSERT/SELECT grant and neither UPDATE nor DELETE, because nothing is inherited).
# Story 2.12 to `0011_policy_change` (the policy-change log — the FOURTH, same shape, plus the one
# CHECK AC1 makes non-negotiable: `disposition IN ('RECALCULATE','PRESERVE')`). Story 3.4 to
# `0012_notification` — the FIRST non-append-only table since 0008 (`read_at` is mutable, so it
# grants `SELECT, INSERT, UPDATE`, not `INSERT, SELECT`) and the first PARTIAL index. ⚠️ The index
# assertions in THIS file check `indexname` only; that is NOT sufficient for a partial index (a
# plain one would pass), so `tests/integration/test_notifications.py` pins the predicate itself
# against `pg_indexes.indexdef`. Story 4.1 to `0013_supporting_document` — the supporting-document
# table (UNIQUE (leave_request_id), NO size_bytes — its test pins the absence), mutable like
# `notification` (`SELECT, INSERT, UPDATE` for the attach-or-replace path; DELETE withheld).
HEAD_REVISION = "0013_supporting_document"


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


def test_leave_request_table_shipped_with_its_columns_checks_and_indexes(
    db_connection: Connection,
) -> None:
    """Story 2.6: `0006` created `leave_request` with its columns, three CHECKs and two indexes.

    From the live catalog: the DATE range, the INTEGER `leave_days`, the TEXT `status`; NO
    `created_at` and NO `leave_year` (ERD §2.1/§4.5 — both derivable); the four-state status CHECK,
    the `end_date >= start_date` order CHECK, the `leave_days > 0` CHECK (all AD-5 backstops); and
    the two ERD §4.4 read indexes.
    """
    columns = {
        row[0]: row[1]
        for row in db_connection.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'leave_request'"
            )
        )
    }
    assert set(columns) == {
        "id",
        "employee_id",
        "leave_type_id",
        "start_date",
        "end_date",
        "leave_days",
        "status",
    }
    # No `created_at`, no `leave_year` — both derivable (ERD §2.1, §4.5).
    assert "created_at" not in columns
    assert "leave_year" not in columns
    # The range is whole calendar DATEs (AD-12); `leave_days` is INTEGER (DR-10).
    assert columns["start_date"] == "date"
    assert columns["end_date"] == "date"
    assert columns["leave_days"] == "integer"

    check_defs = " ".join(
        db_connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'public.leave_request'::regclass AND contype = 'c'"
            )
        ).scalars().all()
    )
    # The four-state status CHECK (PostgreSQL may render `IN (...)` as `= ANY (ARRAY[...])`).
    for state in ("PENDING", "APPROVED", "REJECTED", "CANCELLED"):
        assert state in check_defs, f"leave_request status CHECK must admit {state}"
    assert "end_date >= start_date" in check_defs, (
        "leave_request must carry CHECK (end_date >= start_date) — the AD-5 backstop"
    )
    assert "leave_days > 0" in check_defs, (
        "leave_request must carry CHECK (leave_days > 0) — the AD-5 backstop"
    )

    index_names = set(
        db_connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'leave_request'"
            )
        ).scalars().all()
    )
    assert "ix_leave_request_employee_status" in index_names
    assert "ix_leave_request_start_end" in index_names


def test_audit_entry_table_shipped_with_columns_and_system_actor_check(
    db_connection: Connection,
) -> None:
    """Story 2.6: `0006` created `audit_entry` with its columns and the SYSTEM-actor CHECK.

    From the live catalog: the polymorphic `subject_type`/`subject_id`, the nullable `from_state`
    and `actor_id`, the `TIMESTAMP WITH TIME ZONE` `occurred_at` (the one instant in the schema),
    and the `(actor_type = 'SYSTEM') = (actor_id IS NULL)` biconditional CHECK — the append-only
    trail's guarantee that a SYSTEM row has no human actor and vice versa (AD-8).
    """
    columns = {
        row[0]: (row[1], row[2])
        for row in db_connection.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'audit_entry'"
            )
        )
    }
    assert set(columns) == {
        "id",
        "subject_type",
        "subject_id",
        "from_state",
        "to_state",
        "actor_type",
        "actor_id",
        "reason",
        "occurred_at",
    }
    # `from_state` and `actor_id` are the two nullable columns (a creation / a SYSTEM actor).
    assert columns["from_state"][1] == "YES"
    assert columns["actor_id"][1] == "YES"
    assert columns["to_state"][1] == "NO"
    # The one instant in the schema is a timestamptz (ERD §2), never a naive timestamp.
    assert columns["occurred_at"][0] == "timestamp with time zone"

    check_defs = " ".join(
        db_connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'public.audit_entry'::regclass AND contype = 'c'"
            )
        ).scalars().all()
    )
    # The biconditional — PostgreSQL keeps the equality of the two boolean predicates.
    assert "SYSTEM" in check_defs and "actor_id IS NULL" in check_defs, (
        "audit_entry must carry CHECK ((actor_type = 'SYSTEM') = (actor_id IS NULL)) — the "
        "append-only trail's SYSTEM-actor guarantee (AD-8)"
    )


def test_rollover_run_table_shipped_with_exactly_its_three_columns(
    db_connection: Connection,
) -> None:
    """Story 2.10: `0009` created `rollover_run` with `id`, `leave_year` and `occurred_at`.

    An EXACT column set, like every smoke above. The ERD's ROLLOVER_RUN table lists only the two
    attributes — `leave_year` ("the Leave Year rolled") and `occurred_at` ("the moment") — but
    every table in this schema carries a `uuidv7()` primary key and this one is no exception, so
    the set is three, not two. There is deliberately NO `actor` column: the ERD says "Actor is
    always SYSTEM; no column is needed to say so."

    And NO `UNIQUE (leave_year)`. The table logs EXECUTIONS, not years: a second run against the
    same year appends a second row, and that is correct. Idempotence (AC5) is a property of the
    BALANCES, not of this log — a unique constraint here would turn a legal, no-op second run into
    an `IntegrityError`.
    """
    columns = {
        row[0]: (row[1], row[2])
        for row in db_connection.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'rollover_run'"
            )
        )
    }
    assert set(columns) == {"id", "leave_year", "occurred_at"}
    assert columns["leave_year"][0] == "integer"
    # The moment is a timestamptz (ERD §2), never a naive timestamp — same rule as `audit_entry`.
    assert columns["occurred_at"][0] == "timestamp with time zone"
    assert columns["leave_year"][1] == "NO"
    assert columns["occurred_at"][1] == "NO"

    # The log records executions, so a second run for one year is legal. Assert the ABSENCE of a
    # unique constraint on `leave_year` — the constraint a tidy-minded reader would add.
    unique_defs = " ".join(
        db_connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'public.rollover_run'::regclass AND contype = 'u'"
            )
        ).scalars().all()
    )
    assert "leave_year" not in unique_defs, (
        "rollover_run must NOT carry UNIQUE (leave_year): a second run against the same year is "
        "legal and appends a second row (AC5 makes it a no-op on the balances, not an error)"
    )
