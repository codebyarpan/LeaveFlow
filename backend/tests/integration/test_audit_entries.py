"""The audit trail: its Admin-only read, its append-only GRANT, and SM-4's one-to-one count (2.9).

Implements the test side of every AC:
- AC1 an Admin reads `GET /api/v1/audit-entries` → 200, and every entry names its subject, the
  transition, the actor and the timestamp — including the SYSTEM rows, which an INNER join would
  have silently dropped;
- AC2 an Employee and a Manager are both refused 403 `ACTION_NOT_PERMITTED` — the full audit-log
  read is the Admin's alone (FR-16, DR-13, G3), decided before any row is read;
- AC3 the DATABASE refuses UPDATE and DELETE on `audit_entry` to the application's role, because
  migration 0008 never made the grant (AD-9, NFR-09). The code-layer half of AC3 — no repository
  exposes an update or delete — is asserted in `test_leave_request_submit.py`, which Story 2.9
  REVISED (to `{insert_audit_entry, list_audit_entries}`) rather than deleted;
- AC4 SM-4: every transition the system can perform is driven through the real API, and the audit
  rows are counted against them ONE-TO-ONE — total AND the per-`subject_type` breakdown, because a
  bare total can pass while the discriminator is wrong;
- AC5 a transition whose transaction rolls back leaves NOTHING — the row was inserted inside that
  transaction (AD-8);
- AC6 the managerless auto-approval's row is `SYSTEM` / NULL / `AUTO_APPROVED_NO_MANAGER`, in the
  database AND on the wire — no human approver is fabricated, not even as a display string.

Real PostgreSQL, and it must be: AC3 is a statement about Postgres privileges, and AC5 is a
statement about transaction rollback. Neither has any meaning against a mock. `conftest` skips
loudly if Postgres is unreachable or if the app role has not been provisioned.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories import audit_entry as audit_entry_repo
from app.repositories import leave_request as leave_request_repo
from app.repositories.engine import get_engine
from app.repositories.models import (
    AuditEntry,
    CancellationRequest,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
)
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 400/403 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
# Roomy: the AC4 ledger drives four submissions for one applicant (3 Working Days each), so no
# refusal in these tests is ever an incidental INSUFFICIENT_BALANCE — every refusal is the one
# under test.
_ENTITLEMENT = 20
_client = TestClient(app)

# Four DISTINCT future Mon–Wed ranges (today is 2026-07-14), each 3 Working Days: no weekend, no
# seeded holiday, all inside one leave year. Distinct so that no two requests of one applicant
# overlap — the ledger below is about transitions, and an overlap refusal would be a different test.
_RANGES: tuple[tuple[datetime.date, datetime.date], ...] = (
    (datetime.date(2026, 8, 3), datetime.date(2026, 8, 5)),
    (datetime.date(2026, 8, 10), datetime.date(2026, 8, 12)),
    (datetime.date(2026, 8, 17), datetime.date(2026, 8, 19)),
    (datetime.date(2026, 8, 24), datetime.date(2026, 8, 26)),
)
_EXPECTED_DAYS = 3

# An overspending range for AC5: six Mon–Fri weeks = 30 Working Days > the 20-day entitlement, and
# inside one leave year (so the refusal is INSUFFICIENT_BALANCE, not SPANS_TWO_LEAVE_YEARS).
_OVERSPEND_START = datetime.date(2026, 9, 7)  # Monday
_OVERSPEND_END = datetime.date(2026, 10, 16)  # Friday, six weeks later


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        leave_type_id: uuid.UUID,
        report_id: uuid.UUID,
        report_token: str,
        solo_id: uuid.UUID,
        solo_token: str,
        manager_id: uuid.UUID,
        manager_token: str,
        admin_id: uuid.UUID,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.leave_type_id = leave_type_id
        self.report_id = report_id
        self.report_token = report_token
        self.solo_id = solo_id
        self.solo_token = solo_token
        self.manager_id = manager_id
        self.manager_token = manager_token
        self.admin_id = admin_id
        self.admin_token = admin_token


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """A Manager, their report, a MANAGERLESS Employee, an Admin, one Leave Type (20 days).

    The managerless `solo` is not decoration: their submission auto-approves through the SYSTEM path
    (FR-09), and it is the only way to get a `SYSTEM`/NULL-actor row into the trail — which is what
    AC6 asserts and what the endpoint's LEFT OUTER JOIN exists to preserve.

    All join 1 January, so a Leave Type created through the service materializes each a full-
    entitlement balance (Story 2.4's hook).
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"au-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    def _employee(
        session: Session,
        department_id: uuid.UUID,
        *,
        label: str,
        role: str,
        manager_id: uuid.UUID | None,
    ) -> uuid.UUID:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"au-{label}-{suffix}@example.com",
            full_name=f"AU {label}",
            role=role,
            joining_date=datetime.date(_YEAR, 1, 1),
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        return employee.id

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()

        manager_id = _employee(
            session, department.id, label="mgr", role=vocabulary.ROLE_MANAGER, manager_id=None
        )
        report_id = _employee(
            session,
            department.id,
            label="rep",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        # No manager → the auto-approval path (FR-09), which writes the SYSTEM row.
        solo_id = _employee(
            session, department.id, label="solo", role=vocabulary.ROLE_EMPLOYEE, manager_id=None
        )
        admin_id = _employee(
            session, department.id, label="adm", role=vocabulary.ROLE_ADMIN, manager_id=None
        )
        session.commit()

    report_token = security.create_token(str(report_id), vocabulary.ROLE_EMPLOYEE)
    solo_token = security.create_token(str(solo_id), vocabulary.ROLE_EMPLOYEE)
    manager_token = security.create_token(str(manager_id), vocabulary.ROLE_MANAGER)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    leave_type_id = leave_types_service.create_leave_type(
        code=f"AU-{suffix}",
        name="Audit type",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=False,
    ).id

    try:
        yield _World(
            suffix,
            department_name,
            leave_type_id,
            report_id,
            report_token,
            solo_id,
            solo_token,
            manager_id,
            manager_token,
            admin_id,
            admin_token,
        )
    finally:
        # The OWNER engine, not `get_engine()` (AD-9): the app role holds INSERT and SELECT on
        # `audit_entry` and NEITHER UPDATE NOR DELETE, so the audit deletes below would be REFUSED
        # through the app engine — which is AC3 working, not a bug. Cleanup is maintenance, and
        # maintenance is the owner's. (This fixture is the AC3 guarantee's first customer.)
        with Session(owner_engine) as session:
            lr_ids = select(LeaveRequest.id).where(
                LeaveRequest.leave_type_id == leave_type_id
            )
            cr_ids = (
                select(CancellationRequest.id)
                .join(
                    LeaveRequest,
                    CancellationRequest.leave_request_id == LeaveRequest.id,
                )
                .where(LeaveRequest.leave_type_id == leave_type_id)
            )
            # Audit rows for both subject types first — they carry no FK (the trail is polymorphic),
            # so nothing cascades and they must go before the rows they name.
            session.execute(
                delete(AuditEntry).where(AuditEntry.subject_id.in_(cr_ids))
            )
            session.execute(
                delete(AuditEntry).where(AuditEntry.subject_id.in_(lr_ids))
            )
            session.execute(
                delete(CancellationRequest).where(
                    CancellationRequest.leave_request_id.in_(lr_ids)
                )
            )
            # Story 3.4 (Landmine 16): notification rows FIRST. Every submission/decision through
            # the API now writes one, and it FK-references BOTH `leave_request` and `employee` with
            # NO `ON DELETE` clause (by decision — an Employee is deactivated, never deleted; a
            # Leave Request has no DELETE endpoint). So deleting either parent first raises
            # `ForeignKeyViolation` and errors this whole module. Deleting them explicitly, ahead of
            # their parents, is the sanctioned fix — NOT granting the app role `DELETE` (this block
            # already runs as the owner) and NOT `ON DELETE CASCADE` (it would signal a deletion
            # path the product forbids). Every recipient is one of this fixture's own Employees.
            session.execute(
                delete(Notification).where(
                    Notification.recipient_employee_id.in_(
                        select(Employee.id).where(Employee.email.like(f"%{suffix}%"))
                    )
                )
            )
            session.execute(
                delete(LeaveRequest).where(LeaveRequest.leave_type_id == leave_type_id)
            )
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id == leave_type_id)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id == leave_type_id))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _submit(
    token: str,
    leave_type_id: uuid.UUID,
    date_range: tuple[datetime.date, datetime.date],
) -> dict:
    """Submit through the real endpoint; return the created request's JSON."""
    start, end = date_range
    response = _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _post(path: str, token: str, *, expect: int) -> dict:
    """POST a transition through the real endpoint and assert its status code."""
    response = _client.post(f"/api/v1/{path}", headers=_auth(token))
    assert response.status_code == expect, response.text
    return response.json()


def _audit_rows_for_world(world: _World) -> list[AuditEntry]:
    """Every audit row whose subject belongs to THIS world — both subject types.

    Scoped to the world's own subjects rather than counting the whole table: the trail is global and
    append-only, so a bare `COUNT(*)` would also tally rows left by the seed or by any other test's
    fixtures. The one-to-one claim SM-4 makes is about transitions and their rows, and the scoping
    is what makes it decidable here without asserting anything weaker.
    """
    with Session(get_engine()) as session:
        lr_ids = select(LeaveRequest.id).where(
            LeaveRequest.leave_type_id == world.leave_type_id
        )
        cr_ids = (
            select(CancellationRequest.id)
            .join(LeaveRequest, CancellationRequest.leave_request_id == LeaveRequest.id)
            .where(LeaveRequest.leave_type_id == world.leave_type_id)
        )
        return list(
            session.scalars(
                select(AuditEntry)
                .where(
                    sa.or_(
                        AuditEntry.subject_id.in_(lr_ids),
                        AuditEntry.subject_id.in_(cr_ids),
                    )
                )
                .order_by(AuditEntry.occurred_at, AuditEntry.id)
            ).all()
        )


# --- AC1 + AC6: the Admin reads the trail, and the SYSTEM rows are IN it ----------------------


def test_admin_reads_the_trail_and_every_entry_names_its_four_things(world: _World) -> None:
    """AC1: 200, the standard envelope, and subject/transition/actor/timestamp on every entry.

    The managerless submission is included deliberately: it is the SYSTEM row, and an INNER JOIN to
    `employee` (instead of the LEFT OUTER JOIN the repository uses) would DROP it from the response
    entirely. This assertion is what catches that — the single most likely way to get this story
    wrong — because the row would simply be absent rather than wrong.
    """
    managed = _submit(world.report_token, world.leave_type_id, _RANGES[0])
    auto = _submit(world.solo_token, world.leave_type_id, _RANGES[1])

    response = _client.get("/api/v1/audit-entries", headers=_auth(world.admin_token))
    assert response.status_code == 200, response.text
    body = response.json()

    # The envelope every list endpoint carries (api-contracts §1, NFR-11).
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page"] == 1
    assert body["total"] >= 2

    by_subject = {item["subject_id"]: item for item in body["items"]}

    # The managed submission: NULL → PENDING, by the applicant.
    entry = by_subject[managed["id"]]
    assert entry["subject_type"] == vocabulary.SUBJECT_LEAVE_REQUEST  # the subject
    assert entry["from_state"] is None and entry["to_state"] == vocabulary.STATUS_PENDING  # the transition
    assert entry["actor_type"] == vocabulary.ACTOR_EMPLOYEE  # the actor
    assert entry["actor_id"] == str(world.report_id)
    assert entry["actor_name"] == "AU rep"
    assert entry["reason"] == vocabulary.REASON_SUBMITTED
    assert entry["occurred_at"]  # the timestamp

    # The managerless submission is PRESENT — the outer-join assertion (AC6 on the wire).
    system_entry = by_subject[auto["id"]]
    assert system_entry["to_state"] == vocabulary.STATUS_APPROVED
    assert system_entry["actor_type"] == vocabulary.ACTOR_SYSTEM
    assert system_entry["actor_id"] is None
    assert system_entry["actor_name"] is None  # NOT "System", NOT "—": no name is invented
    assert system_entry["reason"] == vocabulary.REASON_AUTO_APPROVED_NO_MANAGER


def test_the_system_row_names_no_human_in_the_database_either(world: _World) -> None:
    """AC6: `SYSTEM` / NULL / `AUTO_APPROVED_NO_MANAGER`, asserted at the source, not just on the wire.

    The endpoint could in principle null an actor out on projection; the database could not, because
    the biconditional CHECK `(actor_type = 'SYSTEM') = (actor_id IS NULL)` makes it a schema fact.
    Asserting both is what makes "no human approver is fabricated" a statement about the DATA.
    """
    auto = _submit(world.solo_token, world.leave_type_id, _RANGES[0])

    with Session(get_engine()) as session:
        row = session.scalars(
            select(AuditEntry).where(AuditEntry.subject_id == uuid.UUID(auto["id"]))
        ).one()

    assert row.actor_type == vocabulary.ACTOR_SYSTEM
    assert row.actor_id is None
    assert row.reason == vocabulary.REASON_AUTO_APPROVED_NO_MANAGER
    assert row.to_state == vocabulary.STATUS_APPROVED
    assert row.from_state is None


# --- AC2: nobody but the Admin reads the trail ------------------------------------------------


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_non_admin_cannot_read_the_trail(world: _World, role: str) -> None:
    """AC2: an Employee and a Manager are both 403 `ACTION_NOT_PERMITTED` (FR-16, DR-13, G3).

    403, not 404: the refusal is by ROLE GRANT and is decided BEFORE any row is read, which is
    exactly G3's distinction (404 is reserved for a scope miss — a row the actor may not see).
    """
    token = world.report_token if role == "employee" else world.manager_token

    response = _client.get("/api/v1/audit-entries", headers=_auth(token))

    assert response.status_code == 403, response.text
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED


def test_an_anonymous_caller_cannot_read_the_trail() -> None:
    """AC2, the boundary below it: no token at all is refused before the role gate is reached."""
    response = _client.get("/api/v1/audit-entries")
    assert response.status_code == 401, response.text


# --- AC3: append-only is a GRANT, not a habit -------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_entry SET reason = 'TAMPERED'",
        "DELETE FROM audit_entry",
    ],
    ids=["update", "delete"],
)
def test_the_database_refuses_to_mutate_the_trail(world: _World, statement: str) -> None:
    """AC3: connected AS THE APPLICATION ROLE, Postgres refuses UPDATE and DELETE on `audit_entry`.

    "Then the database refuses, BECAUSE THE GRANT WAS NEVER MADE" — migration 0008 grants the app
    role `INSERT, SELECT` on this table and stops there. Story 2.6 could not assert this: it ran a
    single Postgres role that OWNED the table, and an owner cannot be denied on its own table, so a
    REVOKE was a no-op and only the code-layer surface test held the line.

    The assertion is on the PRIVILEGE error specifically — `psycopg.errors.InsufficientPrivilege`.
    A test that merely asserted "no rows changed" would pass just as happily because the row did not
    exist, or because the SQL was malformed, and would prove nothing at all. A real row is
    guaranteed to exist first (the submission below), so "refused" cannot be confused with "nothing
    to refuse".
    """
    _submit(world.report_token, world.leave_type_id, _RANGES[0])
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuditEntry)) > 0

    with pytest.raises(sa.exc.ProgrammingError) as refused:
        with get_engine().begin() as connection:
            connection.execute(sa.text(statement))

    assert isinstance(refused.value.orig, psycopg.errors.InsufficientPrivilege), (
        "the application role must be REFUSED by Postgres — not merely fail to match a row. "
        f"Got {type(refused.value.orig).__name__}."
    )

    # And the row is still there: a refused mutation changes nothing.
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuditEntry)) > 0


# --- AC4 (SM-4): one audit row per transition, counted one-to-one ------------------------------


def test_sm4_every_transition_the_system_can_perform_writes_exactly_one_row(
    world: _World,
) -> None:
    """AC4 / SM-4: drive EVERY transition through the real API; count the rows one-to-one.

    The ledger, established by Stories 2.6/2.7/2.8 and verified against the source:

        submit (managed)        1   LEAVE_REQUEST        NULL→PENDING     EMPLOYEE  SUBMITTED
        submit (managerless)    1   LEAVE_REQUEST        NULL→APPROVED    SYSTEM    AUTO_APPROVED…
        approve                 1   LEAVE_REQUEST        PENDING→APPROVED EMPLOYEE  APPROVED
        reject                  1   LEAVE_REQUEST        PENDING→REJECTED EMPLOYEE  REJECTED
        cancel own PENDING      1   LEAVE_REQUEST        PENDING→CANCELLED EMPLOYEE CANCELLED
        raise CR                1   CANCELLATION_REQUEST NULL→PENDING     EMPLOYEE  CANCELLATION_…
        approve CR              2   CANCELLATION_REQUEST PENDING→APPROVED  + LEAVE_REQUEST
                                    APPROVED→CANCELLED  — TWO rows, one per subject
        reject CR               1   CANCELLATION_REQUEST PENDING→REJECTED REJECTED
        a REFUSED transition    0   no transition occurred, so no row

    A CR raise IS a transition and writes a row (Story 2.8's Open Decision #3, settled Option A).

    Both the TOTAL and the per-`subject_type` breakdown are asserted: a bare total can pass while
    the discriminator is wrong, which is precisely the bug that would make the trail unreadable.
    """
    # Five submissions: four by the managed report, one by the managerless solo.  -> 5 rows
    lr_approve = _submit(world.report_token, world.leave_type_id, _RANGES[0])
    lr_reject = _submit(world.report_token, world.leave_type_id, _RANGES[1])
    lr_cancel = _submit(world.report_token, world.leave_type_id, _RANGES[2])
    lr_for_cr = _submit(world.report_token, world.leave_type_id, _RANGES[3])
    _submit(world.solo_token, world.leave_type_id, _RANGES[0])  # SYSTEM auto-approve

    # The three Leave Request transitions.                                        -> 3 rows
    _post(f"leave-requests/{lr_approve['id']}/approve", world.manager_token, expect=200)
    _post(f"leave-requests/{lr_reject['id']}/reject", world.manager_token, expect=200)
    _post(f"leave-requests/{lr_cancel['id']}/cancel", world.report_token, expect=200)

    # Approve the fourth so it can carry a Cancellation Request.                   -> 1 row
    _post(f"leave-requests/{lr_for_cr['id']}/approve", world.manager_token, expect=200)

    # Raise a CR and APPROVE it: the two-row case (CR + LR, discriminated).         -> 1 + 2 rows
    cr_approved = _post(
        f"leave-requests/{lr_for_cr['id']}/cancellation-requests",
        world.report_token,
        expect=201,
    )
    _post(
        f"cancellation-requests/{cr_approved['id']}/approve",
        world.admin_token,
        expect=200,
    )

    # Raise a CR against the FIRST approved request and REJECT it.                  -> 1 + 1 rows
    cr_rejected = _post(
        f"leave-requests/{lr_approve['id']}/cancellation-requests",
        world.report_token,
        expect=201,
    )
    _post(
        f"cancellation-requests/{cr_rejected['id']}/reject",
        world.admin_token,
        expect=200,
    )

    # A REFUSED transition: re-approving an already-rejected request is a guarded UPDATE that
    # matches zero rows → 409, the transaction rolls back, and NO audit row is written.  -> 0 rows
    _post(f"leave-requests/{lr_reject['id']}/approve", world.manager_token, expect=409)

    rows = _audit_rows_for_world(world)

    # 5 submits + 3 LR transitions + 1 approve + (1 raise + 2 approve-CR) + (1 raise + 1 reject-CR)
    assert len(rows) == 14, (
        "SM-4 is one audit row per state transition, counted one-to-one. Expected 14 for the "
        f"ledger above; found {len(rows)}: {[(r.subject_type, r.from_state, r.to_state) for r in rows]}"
    )

    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row.subject_type] = by_type.get(row.subject_type, 0) + 1

    assert by_type == {
        # 5 creations + approve + reject + cancel + approve + the CR-approve's LR row.
        vocabulary.SUBJECT_LEAVE_REQUEST: 10,
        # raise + approve + raise + reject.
        vocabulary.SUBJECT_CANCELLATION_REQUEST: 4,
    }, f"the per-subject_type breakdown is wrong: {by_type}"

    # The two rows a CR-approve writes share ONE `occurred_at` (one `_now()`, one transaction) —
    # which is exactly why the endpoint's sort carries an `id` tiebreak (Landmine 3). Assert the
    # tie EXISTS, so that a future refactor which accidentally made the timestamps distinct would
    # not quietly retire the tiebreak's reason for being.
    # Identified by (subject_id, to_state), NOT by to_state alone: `cancel own PENDING` also ends in
    # CANCELLED, and it is a DIFFERENT transaction with its own clock reading. The pair wanted here
    # is the CR's PENDING→APPROVED and its Leave Request's APPROVED→CANCELLED — the two rows written
    # by the single approve-CR command.
    cr_approve_pair = [
        row
        for row in rows
        if (row.subject_id == uuid.UUID(cr_approved["id"])
            and row.to_state == vocabulary.STATUS_APPROVED)
        or (row.subject_id == uuid.UUID(lr_for_cr["id"])
            and row.to_state == vocabulary.STATUS_CANCELLED)
    ]
    assert len(cr_approve_pair) == 2
    assert len({row.occurred_at for row in cr_approve_pair}) == 1, (
        "the CR-approve's two rows must share one occurred_at (one `_now()`, one transaction) — "
        "that tie is the whole premise of the `id` tiebreak in the endpoint's ORDER BY"
    )

    # Every row carries the four things AC1 names, and the SYSTEM biconditional holds throughout.
    for row in rows:
        assert row.subject_type and row.subject_id and row.to_state and row.reason
        assert row.occurred_at is not None
        assert (row.actor_type == vocabulary.ACTOR_SYSTEM) == (row.actor_id is None)


def test_the_endpoints_order_is_total_so_pagination_cannot_repeat_or_skip(
    world: _World,
) -> None:
    """Landmine 3: `occurred_at DESC, id DESC` is a TOTAL order, so paging is stable.

    A CR-approve writes two rows with a byte-identical `occurred_at`. Under `ORDER BY occurred_at
    DESC` alone Postgres may return them in either order between two queries, so page 1 could show a
    row that page 2 shows again while another row is never returned at all. Paging the trail one row
    at a time is the sharpest way to catch that: every id must appear exactly once.
    """
    lr = _submit(world.report_token, world.leave_type_id, _RANGES[0])
    _post(f"leave-requests/{lr['id']}/approve", world.manager_token, expect=200)
    cr = _post(
        f"leave-requests/{lr['id']}/cancellation-requests", world.report_token, expect=201
    )
    _post(f"cancellation-requests/{cr['id']}/approve", world.admin_token, expect=200)

    first = _client.get(
        "/api/v1/audit-entries?page=1&page_size=1", headers=_auth(world.admin_token)
    ).json()
    total = first["total"]

    seen: list[str] = []
    for page in range(1, total + 1):
        body = _client.get(
            f"/api/v1/audit-entries?page={page}&page_size=1",
            headers=_auth(world.admin_token),
        ).json()
        seen.extend(item["id"] for item in body["items"])

    assert len(seen) == total
    assert len(set(seen)) == total, (
        "a row was repeated or skipped across pages — the sort is not a total order. The "
        "`id` tiebreak on `occurred_at` is what makes it one."
    )


# --- AC5: a rolled-back transition leaves nothing ----------------------------------------------


def test_a_rolled_back_transition_leaves_no_audit_row(world: _World) -> None:
    """AC5: the audit row is inserted INSIDE the transition's transaction, so a rollback takes it.

    WHY THIS TEST DRIVES THE TRANSACTION DIRECTLY, AND DOES NOT JUST CALL A REFUSING ENDPOINT.
    Every refusal this system can produce is decided BEFORE the audit row is written — `reserve` and
    `consume_direct` raise `INSUFFICIENT_BALANCE` under the balance lock before `insert_leave_request`
    runs (services/leave_requests.py), and a guarded transition that matches zero rows raises `409`
    before its audit call. So a test that merely refused a submission and then found no audit row
    would pass VACUOUSLY: it would be asserting that a row nobody wrote does not exist, and it would
    keep passing even if `insert_audit_entry` committed on its own. (The refused-409 case is still
    covered — in the SM-4 ledger above, where it belongs, as a transition that writes 0 rows.)

    AC5's "because" clause is a claim about the MECHANISM: the row is inserted inside that
    transaction. So the mechanism is what is exercised. This drives the SAME two repository calls a
    real submission makes, in one transaction, proves the audit row IS written (it is visible inside
    the transaction — otherwise the rollback would prove nothing), then rolls back and proves that
    both the request and its audit row are gone. That is AD-8 exactly: `insert_audit_entry` flushes
    WITHOUT committing, so the row lives or dies with the transition it records.
    """
    now = datetime.datetime.now(datetime.UTC)
    start, end = _RANGES[0]

    with Session(get_engine()) as session:
        request = leave_request_repo.insert_leave_request(
            session,
            employee_id=world.report_id,
            leave_type_id=world.leave_type_id,
            start_date=start,
            end_date=end,
            leave_days=_EXPECTED_DAYS,
            status=vocabulary.STATUS_PENDING,
        )
        audit_entry_repo.insert_audit_entry(
            session,
            subject_type=vocabulary.SUBJECT_LEAVE_REQUEST,
            subject_id=request.id,
            from_state=None,
            to_state=vocabulary.STATUS_PENDING,
            actor_type=vocabulary.ACTOR_EMPLOYEE,
            actor_id=world.report_id,
            reason=vocabulary.REASON_SUBMITTED,
            occurred_at=now,
        )
        request_id = request.id

        # The row really was written — inside the transaction, it is there. Without this the
        # rollback assertion below could pass against a row that was never inserted at all.
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEntry)
                .where(AuditEntry.subject_id == request_id)
            )
            == 1
        )

        # The transition fails. Everything it wrote goes with it.
        session.rollback()

    # A SEPARATE session — a fresh transaction, reading committed state only.
    with Session(get_engine()) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEntry)
                .where(AuditEntry.subject_id == request_id)
            )
            == 0
        ), "AD-8: a rolled-back transition must leave NO audit entry"
        assert (
            session.scalar(
                select(func.count())
                .select_from(LeaveRequest)
                .where(LeaveRequest.id == request_id)
            )
            == 0
        ), "the leave_request itself must be gone too — one transaction, one fate"


def test_a_refused_submission_leaves_neither_a_request_nor_an_audit_row(
    world: _World,
) -> None:
    """AC5, through the real API: an `INSUFFICIENT_BALANCE` submission commits NOTHING.

    30 Working Days against a 20-day entitlement. The refusal is raised under the balance lock, so
    no `leave_request` row and no audit row survive — the whole transaction is gone, and the trail
    records only things that actually happened. (See the test above for why this one, on its own,
    would be too weak to carry AC5: the refusal fires before the audit write.)
    """
    response = _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(world.leave_type_id),
            "start_date": _OVERSPEND_START.isoformat(),
            "end_date": _OVERSPEND_END.isoformat(),
        },
        headers=_auth(world.report_token),
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == vocabulary.INSUFFICIENT_BALANCE

    with Session(get_engine()) as session:
        requests = session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .where(LeaveRequest.employee_id == world.report_id)
        )
    assert requests == 0
    assert _audit_rows_for_world(world) == []
