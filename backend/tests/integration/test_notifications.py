"""In-app Notifications — the schema, the two write hooks, and the addressee's three reads (3.4).

Implements the test side of:
- AC1 (AD-16, ERD §4.4): `notification` carries the six columns, `read_at` is the ONLY nullable one,
  the `kind` CHECK admits EXACTLY the three FR-14 kinds — and the index is **PARTIAL**. That last
  clause is the one no other guard can see: Alembic 1.18.5 never compares `postgresql_where`, so a
  plain non-partial index passes `alembic check`, passes `test_model_migration_agreement`, and passes
  a name-only `pg_indexes` assertion (the `test_migration_smoke.py:262-271` precedent) while silently
  failing AC1. `test_the_unread_index_is_partial` asserts the PREDICATE, and it is the only thing
  standing between that index and a silent regression.
- AC2 (AD-16): a managed submission writes exactly one `REQUEST_SUBMITTED` addressed to the
  applicant's MANAGER — inside the submission's transaction, so a REFUSED submission
  (`INSUFFICIENT_BALANCE`, raised under the balance lock) leaves ZERO notification rows. AD-16's "one
  exists if and only if the transition committed" is a biconditional, and both halves are pinned.
- AC3 (FR-14): approve → one `REQUEST_APPROVED` to the APPLICANT; reject → one `REQUEST_REJECTED` to
  the APPLICANT. Plus the two negatives AC3 implies and nothing states: a **self-cancel writes ZERO**
  (`_decide` is shared by cancel — Landmine 1), and a **409'd approve writes ZERO** (the transaction
  rolls back).
- AC4 (FR-09, FR-14): a MANAGERLESS applicant's auto-approved submission gives them one
  `REQUEST_APPROVED` addressed to THEMSELVES, and ZERO `REQUEST_SUBMITTED` exists — "because it would
  have no addressee". The naive unconditional `REQUEST_SUBMITTED` insert would violate the NOT NULL
  recipient FK here and raw-500.
- AC5 (AD-16, AD-10, NFR-04): both reads are addressee-scoped — two Employees each see only their
  own; the unread count is `COUNT(*) WHERE read_at IS NULL`, derived. The exact key sets of the item,
  the unread-count body and the page envelope are PINNED, so an accidental widening — a disclosure —
  fails the build (the 3.2/3.3 house rule).
- AC6 (FR-14, AD-16): mark-read is IDEMPOTENT — a second `PATCH` is a **200, not a 409**, and the
  count decrements exactly ONCE. A non-addressee gets **404**, never 403 (Landmine 2: role `any` ⇒ the
  role gate always admits ⇒ the scope predicate is the only refusal ⇒ G3 makes it a 404, byte-
  identical to a nonexistent id — AD-10).
- SM-4 stays EXACTLY 14 (`test_audit_entries.py` is run UNCHANGED): a Notification is a CONSEQUENCE
  of a transition, not a transition. This story adds ZERO `insert_audit_entry` call sites, and
  `test_the_story_added_no_audit_call_sites` pins that mechanically — unlike `rollover.py`/
  `recalculation.py`, which prove it by not importing `audit_entry_repo` at all, this story writes
  INSIDE the two functions that already call it, so absence-of-import is not available as a proof.

Against real PostgreSQL through the REAL app: importing `app.main` registers the v1 routes and the
error handler — skip it and every request 404s against an empty app (the 2.9 false-green trap).

Teardown runs through the OWNER engine: the app role holds `SELECT, INSERT, UPDATE` on `notification`
and NOT `DELETE` (migration `0012`), exactly as it holds no `DELETE` on `audit_entry` — that refusal
is the guarantee working, not an obstacle to route around by granting the app role `DELETE`.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import (
    AuditEntry,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
)

import app.main  # noqa: F401 — constructs the real app; without it every route 404s

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

_client = TestClient(app.main.app)

_KNOWN_PASSWORD = "correct-horse-battery-staple"

# Every seeded range lies NEXT year, so no submission ever brushes the `PAST_DATE_RANGE` rule and no
# clock is ever mocked (the 3.3 discipline).
_NEXT = datetime.date.today().year + 1

# The EXACT wire shapes (Landmine 12, Open Decisions #2/#5). A fifth key on any of these is a
# widening — a disclosure on the item, a contract drift on the envelope — and must fail the build.
_EXPECTED_ITEM_KEYS = {"id", "kind", "leave_request_id", "read_at", "created_at"}
_EXPECTED_UNREAD_KEYS = {"unread"}
_EXPECTED_PAGE_KEYS = {"items", "page", "page_size", "total"}

# The three kinds FR-14 fixes — EXHAUSTIVE. `services/cancellation.py` writes zero notifications
# (readiness F-4, epics.md:473), and the `reviews/` proposal for `CANCELLATION_*` kinds was rejected.
_ALL_KINDS = {
    vocabulary.NOTIFICATION_REQUEST_SUBMITTED,
    vocabulary.NOTIFICATION_REQUEST_APPROVED,
    vocabulary.NOTIFICATION_REQUEST_REJECTED,
}


def _first_monday(year: int, month: int) -> datetime.date:
    """The first Monday of the month — so every seeded range is all Working Days.

    A range of Mondays-to-Fridays costs a nonzero `count_leave_days` without depending on the
    holiday calendar, so `ZERO_LEAVE_DAYS` never fires and the day count is predictable. No date
    arithmetic reaches the client; this is fixture setup (AD-2 governs the application, not the test
    that seeds it).
    """
    day = datetime.date(year, month, 1)
    while day.weekday() != 0:  # 0 == Monday
        day += datetime.timedelta(days=1)
    return day


class _Member:
    """One seeded Employee: their id, and the token a test calls as them with."""

    def __init__(self, employee_id: uuid.UUID, token: str) -> None:
        self.id = employee_id
        self.token = token


class _World:
    """The topology every AC needs.

    - `manager_m` — the Manager; the addressee of every `REQUEST_SUBMITTED` (AC2) and the actor who
      decides (AC3). NOTE she is the PRIMARY notification recipient in this app — the reason the
      frontend badge carries no role gate (Landmine 2).
    - `emp_a`, `emp_b` — two of her Direct Reports. Two, because AC5's isolation claim needs a second
      Employee whose notifications the first must NOT see.
    - `solo` — a MANAGERLESS Employee (`manager_id IS NULL`), the AC4 auto-approval path.
    - `poor` — a report whose balance has 1 day available, so a 2-day submission is refused with
      `INSUFFICIENT_BALANCE` under the lock: AC2's rollback half.
    """

    def __init__(self) -> None:
        self.suffix: str = ""
        self.leave_type_id: uuid.UUID = None  # type: ignore[assignment]
        self.manager_m: _Member = None  # type: ignore[assignment]
        self.emp_a: _Member = None  # type: ignore[assignment]
        self.emp_b: _Member = None  # type: ignore[assignment]
        self.solo: _Member = None  # type: ignore[assignment]
        self.poor: _Member = None  # type: ignore[assignment]


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """Seed the topology and one balance per submitting Employee; tear down as the OWNER.

    Balances are seeded directly (the composition CHECK `accrued = prorated + carried` satisfied) so
    a submission through the REAL endpoint can `reserve`/`consume_direct` under the lock. `poor` gets
    exactly 1 available day — the lever AC2's rollback half pulls.

    🚨 Teardown deletes `notification` rows BEFORE their `leave_request`/`employee` parents. The FKs
    are NOT NULL with no `ON DELETE` clause (by decision — an Employee is deactivated, never deleted;
    a Leave Request has no DELETE endpoint), so deleting a parent first raises `ForeignKeyViolation`
    and errors the fixture. This is Landmine 16, and it is why eight PRE-EXISTING integration
    teardowns had to be repaired by this story (Task 8b) — the moment `notification` exists, every
    test that submits through the API creates rows that reference those parents.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"notif-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)
    built = _World()
    built.suffix = suffix

    def _insert_employee(
        session: Session,
        label: str,
        role: str,
        *,
        manager_id: uuid.UUID | None = None,
        department_id: uuid.UUID,
    ) -> _Member:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"notif-{label}-{suffix}@example.com",
            full_name=f"Notif {label}",
            role=role,
            joining_date=datetime.date(2026, 1, 1),
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        return _Member(employee.id, security.create_token(str(employee.id), role))

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()
        dept_id = department.id

        built.manager_m = _insert_employee(
            session, "manager", vocabulary.ROLE_MANAGER, department_id=dept_id
        )
        for label in ("emp_a", "emp_b", "poor"):
            setattr(
                built,
                label,
                _insert_employee(
                    session,
                    label,
                    vocabulary.ROLE_EMPLOYEE,
                    manager_id=built.manager_m.id,
                    department_id=dept_id,
                ),
            )
        # `manager_id=None` — the AC4 path. FR-09 auto-approves their submission.
        built.solo = _insert_employee(
            session, "solo", vocabulary.ROLE_EMPLOYEE, department_id=dept_id
        )

        leave_type = LeaveType(
            code=f"NTF-{suffix}",
            name="Notification type",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        session.add(leave_type)
        session.flush()
        built.leave_type_id = leave_type.id

        def _balance(employee_id: uuid.UUID, accrued: int) -> LeaveBalance:
            return LeaveBalance(
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                leave_year=_NEXT,
                accrued=accrued,
                prorated_entitlement=accrued,
                carried_forward=0,
                entitlement_basis=20,
                reserved=0,
                consumed=0,
            )

        for member in (built.emp_a, built.emp_b, built.solo):
            session.add(_balance(member.id, 20))
        # 1 day available — a 2-day submission is refused under the lock (AC2's rollback half).
        session.add(_balance(built.poor.id, 1))
        session.commit()

    try:
        yield built
    finally:
        with Session(owner_engine) as session:
            requests_here = select(LeaveRequest.id).where(
                LeaveRequest.leave_type_id == built.leave_type_id
            )
            # 🚨 Notifications FIRST — they FK-reference both `leave_request` and `employee`, and
            # neither FK cascades. `audit_entry` has no FK to `leave_request`, which is why it may
            # sit either side of the request delete; a notification may not.
            session.execute(
                delete(Notification).where(
                    Notification.leave_request_id.in_(requests_here)
                )
            )
            session.execute(
                delete(AuditEntry).where(AuditEntry.subject_id.in_(requests_here))
            )
            session.execute(
                delete(LeaveRequest).where(
                    LeaveRequest.leave_type_id == built.leave_type_id
                )
            )
            session.execute(
                delete(LeaveBalance).where(
                    LeaveBalance.leave_type_id == built.leave_type_id
                )
            )
            session.execute(
                update(Employee)
                .where(Employee.email.like(f"%{suffix}%"))
                .values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(
                delete(LeaveType).where(LeaveType.id == built.leave_type_id)
            )
            session.execute(
                delete(Department).where(Department.name == department_name)
            )
            session.commit()


# --------------------------------------------------------------------------------------------
# HTTP helpers — every call goes through the REAL app, so the routes, the dependencies, the
# error envelope and the transactions are all the production ones.
# --------------------------------------------------------------------------------------------


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _submit(world: _World, member: _Member, start: datetime.date, end: datetime.date):  # type: ignore[no-untyped-def]
    return _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(world.leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=_auth(member.token),
    )


def _submit_ok(world: _World, member: _Member, start: datetime.date, end: datetime.date) -> str:
    response = _submit(world, member, start, end)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _approve(member: _Member, request_id: str):  # type: ignore[no-untyped-def]
    return _client.post(
        f"/api/v1/leave-requests/{request_id}/approve", headers=_auth(member.token)
    )


def _reject(member: _Member, request_id: str):  # type: ignore[no-untyped-def]
    return _client.post(
        f"/api/v1/leave-requests/{request_id}/reject", headers=_auth(member.token)
    )


def _cancel(member: _Member, request_id: str):  # type: ignore[no-untyped-def]
    return _client.post(
        f"/api/v1/leave-requests/{request_id}/cancel", headers=_auth(member.token)
    )


def _list_notifications(member: _Member, **params: object) -> dict:
    response = _client.get(
        "/api/v1/notifications", params=params, headers=_auth(member.token)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _unread_count(member: _Member) -> int:
    response = _client.get(
        "/api/v1/notifications/unread-count", headers=_auth(member.token)
    )
    assert response.status_code == 200, response.text
    return response.json()["unread"]


def _mark_read(member: _Member, notification_id: str):  # type: ignore[no-untyped-def]
    return _client.patch(
        f"/api/v1/notifications/{notification_id}/read", headers=_auth(member.token)
    )


def _rows_for(world: _World, owner_engine: Engine) -> list[Notification]:
    """Every notification row belonging to THIS world, by its Leave Type — read as the owner.

    Scoping by the world's own Leave Type rather than reading the whole table keeps the assertions
    exact under a suite that runs other modules' fixtures around this one.
    """
    with Session(owner_engine) as session:
        return list(
            session.scalars(
                select(Notification)
                .join(LeaveRequest, Notification.leave_request_id == LeaveRequest.id)
                .where(LeaveRequest.leave_type_id == world.leave_type_id)
                .order_by(Notification.created_at, Notification.id)
            ).all()
        )


# --------------------------------------------------------------------------------------------
# AC1 — the schema, and the part `alembic check` CANNOT see
# --------------------------------------------------------------------------------------------


def test_notification_columns_and_nullability(db_connection: Connection) -> None:
    """AC1: the six columns exist, and `read_at` is the ONLY nullable one.

    `read_at`'s nullability is not incidental — it IS the unread state (AD-16: the count is
    `COUNT(*) WHERE read_at IS NULL`). Making it NOT NULL with a sentinel, or adding an `is_read`
    boolean beside it, would be a second source of truth for a fact this column already carries.
    """
    rows = db_connection.execute(
        text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'notification'"
        )
    )
    nullability = {row[0]: row[1] for row in rows}

    assert set(nullability) == {
        "id",
        "recipient_employee_id",
        "leave_request_id",
        "kind",
        "read_at",
        "created_at",
    }
    nullable = {name for name, is_nullable in nullability.items() if is_nullable == "YES"}
    assert nullable == {"read_at"}, (
        "`read_at` must be the only nullable column — its NULL-ness IS the unread state (AD-16)"
    )


def test_the_unread_index_is_partial(db_connection: Connection) -> None:
    """🚨 AC1's partial index — and the ONE assertion no other guard in this repo can make.

    Landmine 7, verified against the installed packages: Alembic 1.18.5 contains NO reference to
    `postgresql_where` (its PostgreSQL `_dialect_options()` compares only `nulls_not_distinct`). So a
    PLAIN, non-partial index on `recipient_employee_id` would:
      - pass `alembic check` (no diff detected),
      - pass `test_model_migration_agreement` (which runs that same check),
      - pass a name-only `pg_indexes` assertion (the `test_migration_smoke.py:262-271` precedent),
    and STILL silently fail AC1, which requires the index to be partial.

    So this asserts the PREDICATE itself, off the live catalog. Delete the `postgresql_where=` from
    the migration and the model and every other guard in the suite stays green; only this fails.
    """
    indexdef = db_connection.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND indexname = 'ix_notification_recipient_unread'"
        )
    ).scalar()

    assert indexdef is not None, "the AD-16 unread index does not exist"
    assert "read_at IS NULL" in indexdef, (
        "the unread index is NOT PARTIAL — AC1 and ERD §4.4 require "
        "`WHERE read_at IS NULL`, and `alembic check` cannot see its absence: "
        f"{indexdef}"
    )
    assert "recipient_employee_id" in indexdef


def test_the_kind_check_admits_exactly_the_three_fr14_kinds(
    world: _World, owner_engine: Engine
) -> None:
    """AC1: `kind` is constrained to the three FR-14 values — a fourth is refused by the DATABASE.

    Exercised rather than merely read off `pg_constraint`: a real INSERT of a fourth kind must raise.
    The set is EXHAUSTIVE and settled twice (readiness F-4; epics.md:473) — `services/cancellation.py`
    writes ZERO notifications, and the `reviews/review-adversarial.md:166` proposal to add
    `CANCELLATION_APPROVED`/`CANCELLATION_REJECTED` was NOT adopted. If a future story adds a kind,
    this test is where it must be a deliberate act.

    The CHECK is an AD-5 BACKSTOP, never a gate — the services write `vocabulary.NOTIFICATION_*`
    constants — so reaching it from application code would itself be a defect.
    """
    start = _first_monday(_NEXT, 4)
    request_id = _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))

    with Session(owner_engine) as session:
        for kind in _ALL_KINDS:  # each of the three is accepted
            session.add(
                Notification(
                    recipient_employee_id=world.emp_a.id,
                    leave_request_id=uuid.UUID(request_id),
                    kind=kind,
                    created_at=datetime.datetime.now(datetime.timezone.utc),
                )
            )
        session.flush()

        session.add(
            Notification(
                recipient_employee_id=world.emp_a.id,
                leave_request_id=uuid.UUID(request_id),
                kind="CANCELLATION_APPROVED",  # the rejected proposal — the DB must refuse it
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


# --------------------------------------------------------------------------------------------
# AC2 — the submission notification, IN the submission's transaction
# --------------------------------------------------------------------------------------------


def test_a_managed_submission_notifies_the_manager(
    world: _World, owner_engine: Engine
) -> None:
    """AC2: exactly ONE `REQUEST_SUBMITTED`, addressed to the applicant's MANAGER.

    The recipient is the whole assertion. `actor.manager_id` is read straight off the authenticated
    actor — no lookup query — and getting it wrong (addressing it to the applicant) would still leave
    a plausible-looking row that an "I see only my own notifications" test would happily pass.
    """
    start = _first_monday(_NEXT, 5)
    request_id = _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=2))

    rows = _rows_for(world, owner_engine)

    assert len(rows) == 1
    assert rows[0].kind == vocabulary.NOTIFICATION_REQUEST_SUBMITTED
    assert rows[0].recipient_employee_id == world.manager_m.id, (
        "AC2: the addressee is the applicant's MANAGER — the person who must now decide"
    )
    assert rows[0].leave_request_id == uuid.UUID(request_id)
    assert rows[0].read_at is None, "a fresh notification is unread (AD-16)"


def test_a_refused_submission_leaves_no_notification(
    world: _World, owner_engine: Engine
) -> None:
    """AC2's other half — the biconditional. A ROLLED-BACK submission writes NO notification.

    AD-16: the notification is written "inside that transition's transaction, so one exists IF AND
    ONLY IF the transition committed". `poor` has 1 day available and asks for 2, so
    `balances.reserve` raises `INSUFFICIENT_BALANCE` under the balance lock — BEFORE the request row,
    the audit row and the notification are committed — and the whole transaction rolls back.

    A notification written after the commit, or in a session of its own, would leave a row here
    claiming a request was filed that does not exist. That is precisely the failure AD-16's "inside
    that transition's transaction" clause exists to prevent, and this is the test that would catch it.
    """
    start = _first_monday(_NEXT, 6)
    response = _submit(world, world.poor, start, start + datetime.timedelta(days=1))

    assert response.status_code == 400, response.text
    assert response.json()["code"] == vocabulary.INSUFFICIENT_BALANCE

    assert _rows_for(world, owner_engine) == [], (
        "a refused submission must leave ZERO notifications — one exists if and only if the "
        "transition committed (AD-16)"
    )
    assert _unread_count(world.manager_m) == 0


# --------------------------------------------------------------------------------------------
# AC3 — the decision notification, and the two negatives it implies
# --------------------------------------------------------------------------------------------


def test_an_approval_notifies_the_applicant(world: _World, owner_engine: Engine) -> None:
    """AC3: approve → one `REQUEST_APPROVED` addressed to the APPLICANT, not the deciding Manager.

    🚨 The recipient is `row.employee_id`, never `actor.id`. This is the assertion that catches the
    inversion: if the notification were addressed to the Manager who approved, an AC5-style "I only
    see my own notifications" test would STILL PASS — the Manager would legitimately see the wrong
    row addressed to them. Only naming the expected recipient catches it.
    """
    start = _first_monday(_NEXT, 7)
    request_id = _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))

    assert _approve(world.manager_m, request_id).status_code == 200

    rows = _rows_for(world, owner_engine)
    kinds = {row.kind: row for row in rows}

    assert len(rows) == 2  # the REQUEST_SUBMITTED from the submit, plus this
    approved = kinds[vocabulary.NOTIFICATION_REQUEST_APPROVED]
    assert approved.recipient_employee_id == world.emp_a.id, (
        "AC3: the decision is addressed to the APPLICANT — the Manager already knows what they did"
    )
    assert approved.leave_request_id == uuid.UUID(request_id)


def test_a_rejection_notifies_the_applicant(world: _World, owner_engine: Engine) -> None:
    """AC3: reject → one `REQUEST_REJECTED`, addressed to the applicant."""
    start = _first_monday(_NEXT, 8)
    request_id = _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))

    assert _reject(world.manager_m, request_id).status_code == 200

    rows = _rows_for(world, owner_engine)
    rejected = [
        row for row in rows if row.kind == vocabulary.NOTIFICATION_REQUEST_REJECTED
    ]

    assert len(rejected) == 1
    assert rejected[0].recipient_employee_id == world.emp_a.id
    assert rejected[0].leave_request_id == uuid.UUID(request_id)


def test_a_self_cancel_notifies_nobody(world: _World, owner_engine: Engine) -> None:
    """🚨 AC3's implied negative, and Landmine 1: `_decide` is SHARED BY CANCEL.

    An unconditional insert inside `_decide` would fire here — on a transition NO AC grants a
    notification for, and for which the `kind` CHECK admits no value at all. It would surface as a
    raw 500 (a CHECK violation) or, worse, silently write a `REQUEST_REJECTED` the applicant never
    earned. The keyword-only `notify_kind: str | None = None` opt-in is what makes "cancel notifies
    nobody" true BY CONSTRUCTION rather than by remembering.

    The applicant is acting on their own request; there is nobody to tell.
    """
    start = _first_monday(_NEXT, 9)
    request_id = _submit_ok(world, world.emp_b, start, start + datetime.timedelta(days=1))

    before = _rows_for(world, owner_engine)
    assert len(before) == 1  # the REQUEST_SUBMITTED to the Manager

    assert _cancel(world.emp_b, request_id).status_code == 200

    after = _rows_for(world, owner_engine)
    assert len(after) == 1, (
        "a self-cancellation must write ZERO notifications — `_decide` is shared by cancel, and no "
        "AC grants one (the `kind` CHECK does not even admit a value for it)"
    )
    assert after[0].kind == vocabulary.NOTIFICATION_REQUEST_SUBMITTED
    assert _unread_count(world.emp_b) == 0


def test_a_lost_race_approve_writes_no_notification(
    world: _World, owner_engine: Engine
) -> None:
    """AC3's other implied negative: a 409'd transition writes NO notification.

    The second approve's guarded UPDATE matches zero rows (the request is no longer PENDING), the
    service raises `409 TRANSITION_NOT_ALLOWED`, and the WHOLE transaction rolls back — so no second
    `REQUEST_APPROVED` is written. The notification rides the transition's transaction, and a
    transition that did not happen notifies nobody (AD-16).
    """
    start = _first_monday(_NEXT, 10)
    request_id = _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))

    assert _approve(world.manager_m, request_id).status_code == 200
    before = [(row.id, row.kind) for row in _rows_for(world, owner_engine)]

    second = _approve(world.manager_m, request_id)
    assert second.status_code == 409, second.text
    assert second.json()["code"] == vocabulary.TRANSITION_NOT_ALLOWED

    after = [(row.id, row.kind) for row in _rows_for(world, owner_engine)]

    assert after == before, (
        "a refused transition must write NO notification — the whole transaction rolls back, and a "
        "transition that did not happen notifies nobody (AD-16)"
    )
    approved = [
        kind for _, kind in after if kind == vocabulary.NOTIFICATION_REQUEST_APPROVED
    ]
    assert len(approved) == 1, "the applicant is told once, not once per attempt"


# --------------------------------------------------------------------------------------------
# AC4 — the managerless applicant
# --------------------------------------------------------------------------------------------


def test_a_managerless_applicant_notifies_themselves_and_no_submitted_exists(
    world: _World, owner_engine: Engine
) -> None:
    """AC4: the managerless applicant holds one `REQUEST_APPROVED`, and NO `REQUEST_SUBMITTED` exists.

    FR-09 auto-approves a managerless submission, so what happened to the request is that it was
    APPROVED — and the only person who could possibly be told is the applicant themselves.

    🚨 The naive implementation — one unconditional `REQUEST_SUBMITTED` insert with
    `recipient=actor.manager_id` — would pass `None` into a NOT NULL FK column here and surface as a
    RAW 500 on this path, while failing AC4 twice over (wrong kind, wrong addressee, and a
    `REQUEST_SUBMITTED` that AC4 says must not exist "because it would have no addressee").
    """
    start = _first_monday(_NEXT, 11)
    request_id = _submit_ok(world, world.solo, start, start + datetime.timedelta(days=1))

    rows = _rows_for(world, owner_engine)

    assert len(rows) == 1
    assert rows[0].kind == vocabulary.NOTIFICATION_REQUEST_APPROVED
    assert rows[0].recipient_employee_id == world.solo.id, (
        "AC4: the managerless applicant is their OWN addressee"
    )
    assert rows[0].leave_request_id == uuid.UUID(request_id)

    assert not [
        row for row in rows if row.kind == vocabulary.NOTIFICATION_REQUEST_SUBMITTED
    ], "AC4: NO REQUEST_SUBMITTED may exist — it would have no addressee"

    assert _unread_count(world.solo) == 1
    assert _unread_count(world.manager_m) == 0


# --------------------------------------------------------------------------------------------
# AC5 — the reads, addressee-scoped
# --------------------------------------------------------------------------------------------


def test_each_employee_sees_only_their_own_notifications(world: _World) -> None:
    """AC5: the list is addressee-scoped — and the item's key set is PINNED.

    `emp_a` is approved, `emp_b` is rejected; each must see exactly their own decision and NOT the
    other's. The Manager sees the two `REQUEST_SUBMITTED` rows and neither decision — she is the
    primary recipient here, which is exactly why the endpoint carries no role gate (Landmine 2).

    The exact key set is asserted so an accidental widening — adding the applicant's name, the
    request's dates — fails the build. That is a disclosure guard, not a style rule (the 3.2/3.3
    house rule); this read's scope is the addressee alone, and its shape is the minimal one Open
    Decision #5 fixes.
    """
    start = _first_monday(_NEXT, 5)
    a_request = _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))
    b_request = _submit_ok(
        world, world.emp_b, start + datetime.timedelta(days=7), start + datetime.timedelta(days=8)
    )
    assert _approve(world.manager_m, a_request).status_code == 200
    assert _reject(world.manager_m, b_request).status_code == 200

    a_page = _list_notifications(world.emp_a)
    b_page = _list_notifications(world.emp_b)
    m_page = _list_notifications(world.manager_m)

    assert set(a_page) == _EXPECTED_PAGE_KEYS, "the page envelope is exactly the four AC3 names"
    assert {item["kind"] for item in a_page["items"]} == {
        vocabulary.NOTIFICATION_REQUEST_APPROVED
    }
    assert {item["kind"] for item in b_page["items"]} == {
        vocabulary.NOTIFICATION_REQUEST_REJECTED
    }
    assert a_page["total"] == 1
    assert b_page["total"] == 1

    # The Manager holds BOTH submissions and NEITHER decision — she is a recipient, not an observer.
    assert m_page["total"] == 2
    assert {item["kind"] for item in m_page["items"]} == {
        vocabulary.NOTIFICATION_REQUEST_SUBMITTED
    }

    for item in a_page["items"]:
        assert set(item) == _EXPECTED_ITEM_KEYS, (
            "the notification item shape is pinned — a new key is a disclosure that must be "
            "deliberate (Open Decision #5)"
        )
        assert item["read_at"] is None


def test_the_unread_count_is_derived_and_scoped(world: _World, owner_engine: Engine) -> None:
    """AC5: `unread` == `COUNT(*) WHERE read_at IS NULL`, per addressee — and its key set is pinned.

    The count is never stored (AD-16). Asserted against the database's own count of the same
    predicate, so a cached or denormalized tally that drifted from the rows would fail here.
    """
    start = _first_monday(_NEXT, 5)
    _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))
    _submit_ok(
        world, world.emp_b, start + datetime.timedelta(days=7), start + datetime.timedelta(days=8)
    )

    response = _client.get(
        "/api/v1/notifications/unread-count", headers=_auth(world.manager_m.token)
    )
    assert response.status_code == 200
    assert set(response.json()) == _EXPECTED_UNREAD_KEYS, (
        "the unread-count body is exactly `{unread}` (Open Decision #2)"
    )

    with Session(owner_engine) as session:
        expected = session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_employee_id == world.manager_m.id,
                Notification.read_at.is_(None),
            )
        )

    assert response.json()["unread"] == expected == 2
    # The applicants hold no unread notification of their own — the submissions went to the Manager.
    assert _unread_count(world.emp_a) == 0
    assert _unread_count(world.emp_b) == 0


def test_the_reads_require_a_token(world: _World) -> None:
    """AC5: all three endpoints are authenticated. Role `any` does NOT mean anonymous.

    `get_current_employee` is the guard — any authenticated ROLE, never an absent token. An absent
    header flows through `resolve_actor` to the one `401 TOKEN_INVALID` envelope (Story 1.3).
    """
    for response in (
        _client.get("/api/v1/notifications"),
        _client.get("/api/v1/notifications/unread-count"),
        _client.patch(f"/api/v1/notifications/{uuid.uuid4()}/read"),
    ):
        assert response.status_code == 401, response.text
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# --------------------------------------------------------------------------------------------
# AC6 — idempotent mark-read, addressee-only
# --------------------------------------------------------------------------------------------


def test_mark_read_is_idempotent_and_the_count_decrements_once(world: _World) -> None:
    """🚨 AC6, and Landmine 3: the SECOND `PATCH` is a 200, NOT a 409.

    Every other guarded UPDATE in this codebase reads a zero rowcount as a lost race and raises `409
    TRANSITION_NOT_ALLOWED` (AD-4). Here it cannot mean that: the service has ALREADY located the row
    under the actor's scope, so "not yours" and "nonexistent" are excluded, and the only remaining
    cause of a zero rowcount is that `read_at` was already set — the notification was ALREADY READ.
    And "already read" is exactly what a second PATCH is supposed to be. A 409 there would make the
    second call an error, which is the opposite of idempotent.

    AC6's own words: "the Notification is marked read and the unread count decrements ONCE."
    """
    start = _first_monday(_NEXT, 5)
    _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))

    assert _unread_count(world.manager_m) == 1
    notification_id = _list_notifications(world.manager_m)["items"][0]["id"]

    first = _mark_read(world.manager_m, notification_id)
    assert first.status_code == 200, first.text
    assert _unread_count(world.manager_m) == 0

    second = _mark_read(world.manager_m, notification_id)
    assert second.status_code == 200, (
        "the second mark-read is a SUCCESS, not a 409 — mark-read is idempotent (AC6). "
        f"got {second.status_code}: {second.text}"
    )
    assert _unread_count(world.manager_m) == 0, "the count decrements exactly once"

    # The row is read, and stays read — `read_at` is set once and not overwritten into a new instant
    # on the second call (the guarded UPDATE's `read_at IS NULL` clause is what prevents it).
    item = _list_notifications(world.manager_m)["items"][0]
    assert item["read_at"] is not None


def test_a_non_addressee_gets_404_never_403(world: _World) -> None:
    """🚨 AC6 + Landmine 2: no Employee other than the addressee may mark it read — and they get 404.

    THIS INVERTS THE APP'S HABIT. api-contracts §4.8 grants all three notification endpoints to Role
    `any`, so the role gate ADMITS EVERY authenticated caller. By the G3 settlement
    (`api-contracts.md:37-44`) — "if the role admits them, the scope predicate runs, and a miss is
    404" — someone else's Notification is a SCOPE MISS, not a role refusal. So it is a 404 with the
    full envelope and `details == {}`, byte-identical to a nonexistent id (AD-10), and NOT the 403
    `ACTION_NOT_PERMITTED` that 3.2's `/team` and 3.3's `/calendar` both correctly return.

    A 403 here would also leak existence: it would confirm the notification is real and belongs to
    someone. The 404 confirms nothing.
    """
    start = _first_monday(_NEXT, 5)
    _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))
    notification_id = _list_notifications(world.manager_m)["items"][0]["id"]

    # `emp_b` is a real, authenticated Employee — just not the addressee.
    refused = _mark_read(world.emp_b, notification_id)

    assert refused.status_code == 404, (
        "a non-addressee gets 404, NOT 403 — the role gate admits every role here, so the only "
        f"possible refusal is the scope predicate (G3, AD-10). got {refused.status_code}"
    )
    body = refused.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.RESOURCE_NOT_FOUND
    assert body["details"] == {}

    # And it really did not mark it read — the addressee's count is untouched.
    assert _unread_count(world.manager_m) == 1

    # A nonexistent (but well-formed) id is BYTE-IDENTICAL — that is what makes probing useless.
    ghost = _mark_read(world.emp_b, str(uuid.uuid4()))
    assert ghost.status_code == 404
    assert ghost.json() == body


def test_a_manager_reads_notifications_without_any_role_gate(world: _World) -> None:
    """Landmine 2, stated positively: a MANAGER is the primary recipient, and no role is refused.

    `REQUEST_SUBMITTED` is addressed to a Manager — telling a Manager that a decision is waiting is
    the first half of FR-14's entire purpose. An `EMPLOYEE`-role gate on these endpoints (the reflex,
    after 3.2 and 3.3 each shipped a Manager-ONLY inversion) would hide exactly the notification the
    feature exists to deliver. This test fails if anyone ever adds `require_role` here.
    """
    start = _first_monday(_NEXT, 5)
    _submit_ok(world, world.emp_a, start, start + datetime.timedelta(days=1))

    page = _list_notifications(world.manager_m)

    assert page["total"] == 1
    assert page["items"][0]["kind"] == vocabulary.NOTIFICATION_REQUEST_SUBMITTED
    assert _unread_count(world.manager_m) == 1


# --------------------------------------------------------------------------------------------
# SM-4 — a notification is not a state transition
# --------------------------------------------------------------------------------------------


def test_the_story_added_no_audit_call_sites() -> None:
    """SM-4 stays EXACTLY 14: this story adds ZERO `insert_audit_entry` call sites (Landmine 4).

    AD-8 reserves `audit_entry` for "exactly one row per state transition of a Leave Request or a
    Cancellation Request, AND NOTHING ELSE" — and that last clause is what keeps SM-4's exact count
    literally true. A Notification is a CONSEQUENCE of a transition, not a transition; there is no
    `SUBJECT_NOTIFICATION` and there must not be one.

    `rollover.py` and `recalculation.py` prove this by not importing `audit_entry_repo` AT ALL. This
    story cannot: it writes INSIDE the two functions that already call `insert_audit_entry`. So the
    discipline is mechanical instead — the NUMBER of call sites must be byte-identical before and
    after (six: `leave_requests.py` ×2, `cancellation.py` ×4). A seventh means someone audited a
    notification.
    """
    import pathlib

    services = pathlib.Path(__file__).resolve().parents[2] / "app" / "services"
    call_sites = sum(
        module.read_text().count("insert_audit_entry(")
        for module in services.glob("*.py")
    )

    assert call_sites == 6, (
        "the number of `insert_audit_entry` call sites moved — a notification is NOT an audit "
        f"row (AD-8, SM-4 pins 14). expected 6, found {call_sites}"
    )
