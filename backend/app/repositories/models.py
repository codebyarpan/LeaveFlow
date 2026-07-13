"""The ORM models. Persistence is `repositories/`' business (AD-1, the spine's source tree).

Implements: FR-01 (an Employee authenticates with email + password), FR-04 (a
deactivated Employee cannot authenticate), AD-10 (every read is scoped — the columns
that scope it, `department_id` and `manager_id`, live here), AD-14 (`password_hash` is
where the bcrypt digest is stored, never the password), AD-23 (`CHECK (id <> manager_id)`
is a *backstop* for the reporting-cycle refusal — the gate itself is the employee
service in Story 1.6). SM-6: every model names the requirements it serves.

Why `department` and `employee` arrive together, in this story rather than Story 1.5:
`employee.department_id` is NOT NULL (PRD §3 — every Employee belongs to exactly one
Department), so the Admin seeded here (AC2) needs a Department to belong to. Story 1.5
adds the Department *endpoints*; the table has to exist before an Admin can be seeded.

These models must stay byte-for-byte faithful to migration `0002` — `alembic check`
emits an empty diff only while they agree, and `tests/integration/test_model_migration_agreement.py`
runs that check in the suite so a drift fails the build. Change one, change both, in the
same commit.
"""

import datetime
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.repositories.base import Base


class Department(Base):
    """A unit of the organization every Employee belongs to (FR-01, PRD §3).

    No `UNIQUE (name)`: the ERD does not declare one, and inventing schema the ERD
    does not name is how two sources of truth begin to disagree. The seed reconciles
    a duplicate name by select-then-insert (Story 1.2 Task 6), not by a constraint.
    """

    __tablename__ = "department"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension, no CREATE EXTENSION (ERD §4.4).
        server_default=text("uuidv7()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


class Employee(Base):
    """A person who authenticates and, later, requests leave (FR-01, FR-04, AD-10, AD-14).

    `manager_id` is nullable — an Admin, and the top of any reporting chain, reports to
    no one (AC2). `CHECK (id <> manager_id)` is AD-23's backstop only: it refuses the
    one-node self-loop the database can see cheaply, but the transitive cycle refusal is
    the employee service's (Story 1.6). A CHECK violation reaching a client is a defect
    and a 500 (AD-5), never a validation message — the service is the gate.
    """

    __tablename__ = "employee"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("department.id"),
        nullable=False,
        index=True,  # NFR-12; ERD §4.4 — reads filter by department.
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id"),
        nullable=True,
        index=True,  # NFR-12; ERD §4.4 — "my team" walks this edge.
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    joining_date: Mapped[datetime.date] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    department: Mapped["Department"] = relationship(back_populates="employees")
    manager: Mapped["Employee | None"] = relationship(remote_side="Employee.id")

    __table_args__ = (
        CheckConstraint(
            "role IN ('EMPLOYEE', 'MANAGER', 'ADMIN')",
            name="employee_role_check",
        ),
        # AD-23 backstop. Named so the migration and the model agree on it.
        CheckConstraint("id <> manager_id", name="employee_not_own_manager_check"),
    )


class LeaveType(Base):
    """A leave policy expressed as DATA, never an enum (FR-06, AD-11, DR-11, SM-5).

    A Leave Type is a table row, so changing leave policy — adding a fourth type, retuning
    an entitlement — is configuration, not a code change and not a schema migration (SM-5).
    It is NEVER a Python `Enum` and NEVER a PostgreSQL `ENUM` (AD-11): the attributes below
    are read at runtime, and no branch anywhere tests a Leave Type by `code` or `name`. The
    three seed rows (EL/CL/FL) enter through `python -m seed`, never a migration (AD-11).

    `UNIQUE (code)` is the one constraint departments lacks: the service pre-checks a
    duplicate `code` and re-raises the `IntegrityError` as a typed `409 LEAVE_TYPE_CODE_IN_USE`
    (AD-5), so the constraint stays a backstop and never surfaces as a raw 500.

    Like `Department` and `Employee`, this model must stay byte-for-byte faithful to its
    migration (`0003_leave_type`): `alembic check` emits an empty diff only while they agree,
    and `tests/integration/test_model_migration_agreement.py` runs that check in the suite.
    """

    __tablename__ = "leave_type"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension (ERD §4.4), mirroring `Department`.
        server_default=text("uuidv7()"),
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Plain INTEGER — Leave Days for a full year; the base Proration reduces it. Never
    # NUMERIC, never float (ERD §4.1): a day count is a whole number of days.
    annual_entitlement: Mapped[int] = mapped_column(nullable=False)
    carries_forward: Mapped[bool] = mapped_column(nullable=False)
    # NULLABLE: the maximum carried across the year boundary, meaningless (and null) where
    # `carries_forward` is false (ERD §6).
    carry_forward_cap: Mapped[int | None] = mapped_column(nullable=True)
    requires_supporting_document: Mapped[bool] = mapped_column(nullable=False)


class CompanyHoliday(Base):
    """A day the whole organization does not work — global, scoped to nothing (FR-10, DR-1).

    A Company Holiday is a calendar `DATE`, never a `TIMESTAMPTZ` (AD-12, DR-2a): a holiday
    is a whole day, and it is transported `YYYY-MM-DD`. The Python type is `datetime.date`
    (which SQLAlchemy maps to PostgreSQL `DATE`), mirroring `Employee.joining_date` — a
    `datetime.datetime` here would map to `TIMESTAMP` and violate AC2/AD-12.

    The calendar is GLOBAL: there is no `department_id`, no `location`, no scope column of
    any kind (ERD §3: "COMPANY_HOLIDAY stands alone by design … scoped to no Department or
    location"). It stands alone — no foreign key into it, and none out of it — so there is
    no relationship to declare.

    `UNIQUE (holiday_date)` is the AD-5 backstop behind the duplicate-date refusal: the
    service pre-checks a duplicate `holiday_date` and re-raises the `IntegrityError` as a
    typed `409 HOLIDAY_DATE_IN_USE` (mirroring `LeaveType`'s `UNIQUE (code)`), so the
    constraint never surfaces as a raw 500.

    Like every model here, this must stay byte-for-byte faithful to its migration
    (`0004_company_holiday`): `alembic check` emits an empty diff only while they agree, and
    `tests/integration/test_model_migration_agreement.py` runs that check in the suite.
    """

    __tablename__ = "company_holiday"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension (ERD §4.4), mirroring `LeaveType`.
        server_default=text("uuidv7()"),
    )
    # `datetime.date`, never `datetime.datetime` — SQLAlchemy maps `date → DATE` (the
    # precedent is `Employee.joining_date` above); a `datetime` would map to `TIMESTAMP`
    # and break AC2/AD-12/DR-2a.
    holiday_date: Mapped[datetime.date] = mapped_column(nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class LeaveBalance(Base):
    """An Employee's balance for one Leave Type in one Leave Year — three quantities, one derived.

    Implements: FR-07 (a balance is `available` with `reserved`/`consumed` alongside), DR-3 /
    AD-5 (there is NO `available` column — it is derived `accrued − consumed − reserved` at the
    projection, never stored), AD-17 (only `services/balances.py` writes any quantity column
    here), SM-5 (a Leave Type added through the API immediately has a balance to apply against).

    Three quantities are STORED — `accrued` (what was granted), `reserved` (committed to Pending
    requests) and `consumed` (spent on approved leave); `available` is DERIVED. `prorated_
    entitlement` and `carried_forward` are the two parts `accrued` composes from (`accrued =
    prorated_entitlement + carried_forward`, a non-deferrable equality CHECK — so `set_accrual`
    writes all three in one statement). `entitlement_basis` records the `annual_entitlement` the
    row was accrued under, which FR-06's RECALCULATE recalculates *from* (ERD §2.1). Every column
    is plain `INTEGER` — a Leave Day is a whole number of days, never `NUMERIC`/float (DR-10).

    `reserved` and `consumed` carry `server_default=0` so a freshly materialized row (through
    `set_accrual`'s insert, which names only the accrual triple) defaults them to 0 — keeping
    `reserve`/`consume_*` the only paths that ever *change* a committed/spent quantity.

    The three CHECKs are the AD-5 BACKSTOP, never the gate: the service pre-checks `available ≥
    days` under the row lock and raises `INSUFFICIENT_BALANCE`; a CHECK reaching a client is a
    defect and a 500. `UNIQUE (employee_id, leave_type_id, leave_year)` is one balance per pair
    per year — and its implicit btree index IS the `SELECT … FOR UPDATE` access path (ERD §4.4),
    so no second index is declared.

    Like every model here, this must stay byte-for-byte faithful to its migration
    (`0005_leave_balance`): `alembic check` emits an empty diff only while they agree, and
    `tests/integration/test_model_migration_agreement.py` runs that check in the suite. Each
    constraint carries an explicit `name=` byte-identical to the migration's.
    """

    __tablename__ = "leave_balance"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension (ERD §4.4), mirroring every table.
        server_default=text("uuidv7()"),
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leave_type.id"), nullable=False
    )
    # The calendar year the balance is for (DR-8). The "current Leave Year" is decided in
    # `services/` (`date.today().year`), never here — the model carries the value, not the clock.
    leave_year: Mapped[int] = mapped_column(nullable=False)
    # The three composition columns. `accrued = prorated_entitlement + carried_forward` (the
    # equality CHECK); `set_accrual` writes all three in one statement.
    accrued: Mapped[int] = mapped_column(nullable=False)
    prorated_entitlement: Mapped[int] = mapped_column(nullable=False)
    carried_forward: Mapped[int] = mapped_column(nullable=False)
    # What the row was accrued under — RECALCULATE's input (ERD §2.1).
    entitlement_basis: Mapped[int] = mapped_column(nullable=False)
    # Committed and spent. Default to 0 on a fresh materialization so `set_accrual`'s insert need
    # not name them; only `reserve`/`consume_*`/`release_*`/`adjust_*` ever change them.
    reserved: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    consumed: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))

    # No `available` column — it is derived (DR-3, AD-5).

    __table_args__ = (
        # AD-5 backstops. The service is the gate; these never surface to a client.
        CheckConstraint(
            "accrued - consumed - reserved >= 0",
            name="leave_balance_available_nonneg_check",
        ),
        CheckConstraint(
            "reserved >= 0 AND consumed >= 0",
            name="leave_balance_reserved_consumed_nonneg_check",
        ),
        CheckConstraint(
            "accrued = prorated_entitlement + carried_forward",
            name="leave_balance_accrued_composition_check",
        ),
        # One balance per (Employee, Leave Type, Leave Year); its implicit btree index is the
        # FOR UPDATE access path (ERD §4.4), so no separate index is declared.
        UniqueConstraint(
            "employee_id",
            "leave_type_id",
            "leave_year",
            name="leave_balance_employee_type_year_key",
        ),
    )


class LeaveRequest(Base):
    """One Employee's request for leave over a date range — the first lifecycle row (Story 2.6).

    Implements: FR-08 (a request reserves its days at submission), AD-18 (`leave_days` is
    computed ONCE by `domain/calendar.count_leave_days` at admission and FROZEN on the row —
    no read path ever recomputes it), DR-10 (`leave_days` is a whole-day `INTEGER`, never a
    float/`NUMERIC`), AD-5 (the three CHECKs are the BACKSTOP; `services/leave_requests.py` is
    the gate — a CHECK reaching a client is a defect and a 500). SM-6.

    NO `created_at` and NO `leave_year` column (ERD §2.1, §4.5): the Leave Year is derivable
    from `start_date` (a request may not span two Leave Years, Story 2.6's `SPANS_TWO_LEAVE_YEARS`
    refusal), and creation order comes from the UUIDv7 primary key (time-ordered by construction),
    so neither is stored.

    `status` is TEXT with a `CHECK (status IN (...))` — it IS code (four states the application
    handles exhaustively), the AD-11 counterpart to a Leave Type being a row. The lifecycle
    TRANSITIONS (approve/reject/cancel) are Story 2.7's guarded `UPDATE`; this story only creates
    a row as `PENDING` (managed applicant) or `APPROVED` (managerless auto-approval, FR-09).

    Like every model here, this must stay byte-for-byte faithful to its migration
    (`0006_leave_request`): `alembic check` (run by
    `tests/integration/test_model_migration_agreement.py`) emits an empty diff only while they
    agree — every constraint and index `name` is byte-identical to the migration's.
    """

    __tablename__ = "leave_request"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension (ERD §4.4), mirroring every table. UUIDv7
        # is time-ordered, so the PK also carries creation order (why no `created_at`).
        server_default=text("uuidv7()"),
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leave_type.id"), nullable=False
    )
    # Whole calendar DATEs (AD-12), never TIMESTAMPs — a leave range is whole days. The
    # inclusive `[start_date, end_date]` `count_leave_days` walks.
    start_date: Mapped[datetime.date] = mapped_column(nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(nullable=False)
    # The frozen Working-Day count (AD-18) — plain INTEGER (DR-10). Computed once at admission,
    # never recomputed by a read path.
    leave_days: Mapped[int] = mapped_column(nullable=False)
    # One of the four PENDING/APPROVED/REJECTED/CANCELLED states, stored as TEXT with a CHECK.
    status: Mapped[str] = mapped_column(Text, nullable=False)

    # No `created_at`, no `leave_year` — both derivable (ERD §2.1, §4.5).

    __table_args__ = (
        # AD-5 backstops — the service is the gate; names byte-identical to the migration.
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
            name="leave_request_status_check",
        ),
        CheckConstraint(
            "end_date >= start_date",
            name="leave_request_date_order_check",
        ),
        CheckConstraint(
            "leave_days > 0",
            name="leave_request_leave_days_positive_check",
        ),
        # The two ERD §4.4 read indexes: "my pending requests" (employee+status) and the
        # date-range overlap scan the team calendar (Story 3.3) will walk.
        Index("ix_leave_request_employee_status", "employee_id", "status"),
        Index("ix_leave_request_start_end", "start_date", "end_date"),
    )


class AuditEntry(Base):
    """One recorded state transition — the append-only audit trail's row (Story 2.6, AD-8).

    Implements: FR-08/AD-8 (exactly ONE audit row per transition, inserted in the SAME
    transaction as the transition; a rolled-back submit leaves neither a request row nor an
    audit row), AD-9 (append-only — no repository exposes an update or delete for this table;
    see the Story 2.6 Decision Point on why the guarantee is realized at the code layer, not a
    DB `GRANT`, while the codebase runs a single Postgres role). SM-6.

    `subject_id` is POLYMORPHIC — it names the row a transition is about (a `leave_request` here,
    other subjects in later stories) — so it carries NO foreign key (ERD §2): an FK would bind
    the trail to one table and forbid the polymorphism. `subject_type` (e.g. `LEAVE_REQUEST`)
    disambiguates it.

    `from_state` is NULLABLE — a creation has no prior state (`NULL → PENDING`/`APPROVED`).
    `actor_id` is NULLABLE and FKs `employee.id`: it is NULL exactly when `actor_type = 'SYSTEM'`
    (the managerless auto-approval has no human actor, FR-09), enforced by the `CHECK
    ((actor_type = 'SYSTEM') = (actor_id IS NULL))` biconditional. `occurred_at` is a
    `TIMESTAMP WITH TIME ZONE` (the clock lives in the service shell, AD-1) — the one instant
    in the schema, distinct from the whole-day DATEs everywhere else.

    Byte-for-byte faithful to `0006_leave_request`, like every model here — the constraint
    `name` matches the migration's exactly.
    """

    __tablename__ = "audit_entry"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Polymorphic — the id of the subject row, NO foreign key (ERD §2): the trail spans subject
    # types, and an FK would pin it to one table.
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    # NULL for a creation — there is no prior state to record.
    from_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL iff SYSTEM (the biconditional CHECK below). FKs `employee.id` when a human acted.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # The one instant in the schema — a TIMESTAMP WITH TIME ZONE (ERD §2), set from the service
    # shell (AD-1). `DateTime(timezone=True)` is explicit: a bare `Mapped[datetime]` would map to
    # a naive `TIMESTAMP`, dropping the offset the trail must retain.
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        # The SYSTEM-actor biconditional: actor_type == 'SYSTEM' iff actor_id IS NULL. AD-5
        # backstop; name byte-identical to the migration.
        CheckConstraint(
            "(actor_type = 'SYSTEM') = (actor_id IS NULL)",
            name="audit_entry_system_actor_null_check",
        ),
    )


class CancellationRequest(Base):
    """A request to cancel an Approved Leave Request — its OWN row, not a status (Story 2.8).

    Implements: AD-13 / DR-14 (a Cancellation Request is an ENTITY with its own
    `PENDING/APPROVED/REJECTED` lifecycle, targeting one Approved Leave Request via
    `leave_request_id` — NEVER a fifth `leave_request.status`; that is what makes "Approved, with
    a cancellation pending" representable). The applicant raises one against their own future-dated
    Approved request; an Admin decides it. An approved Cancellation Request moves the target Leave
    Request to `CANCELLED` and returns its days via `release_consumed` (BR-05); a rejected one
    changes nothing. AD-5 (the `status` CHECK is the BACKSTOP; `services/cancellation.py` is the
    gate — a CHECK reaching a client is a defect and a 500). AD-11 (`status` IS code — three states
    handled exhaustively, stored as TEXT with a CHECK). SM-6.

    NO `UNIQUE (leave_request_id)` (ERD §3): a Leave Request may have MULTIPLE Cancellation Requests
    over time (a rejected one may be followed by another). NO requester column (the requester is
    `leave_request.employee_id`, FR-09), NO decider column (the deciding Admin is the `actor_id` on
    the audit row), NO `created_at` (creation order comes from the time-ordered UUIDv7 PK) — exactly
    like `LeaveRequest` (ERD §2.1). NO index — the ERD §4.4 names none for this table.

    Like every model here, this must stay byte-for-byte faithful to its migration
    (`0007_cancellation_request`): `alembic check` (run by
    `tests/integration/test_model_migration_agreement.py`) emits an empty diff only while they
    agree — the constraint `name` is byte-identical to the migration's.
    """

    __tablename__ = "cancellation_request"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension (ERD §4.4), mirroring every table. UUIDv7
        # is time-ordered, so the PK also carries creation order (why no `created_at`).
        server_default=text("uuidv7()"),
    )
    leave_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leave_request.id"), nullable=False
    )
    # One of the three PENDING/APPROVED/REJECTED states, stored as TEXT with a CHECK.
    status: Mapped[str] = mapped_column(Text, nullable=False)

    # No requester/decider column, no `created_at`, no index (ERD §2.1, §3, §4.4).

    __table_args__ = (
        # AD-5 backstop — the service is the gate; name byte-identical to the migration.
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED')",
            name="cancellation_request_status_check",
        ),
    )
