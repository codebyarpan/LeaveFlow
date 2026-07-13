"""Deciding a Leave Request — approve/reject/cancel + the scoped reads, end to end (Story 2.7).

Implements the test side of every AC:
- AC1 approve moves `reserved → consumed`, reject releases the reservation, each writing exactly ONE
  audit row naming the Manager;
- AC2 a guarded transition whose `UPDATE … WHERE status = :from` matches zero rows is a clean 409,
  the balance byte-unchanged and no audit row (the transaction rolled back);
- AC3 an applicant cancels their OWN Pending request; a non-owner gets 404; a settled request 409;
- AC4 `GET /leave-requests` is scoped (Employee own / Manager reports' / Admin all), paged and
  status-filterable, the scope a SQL predicate (a foreign team's request never appears);
- AC5 `GET /leave-requests/<id>` returns the STORED (frozen) `leave_days`; out-of-scope → 404;
- AC6 an Admin approving/rejecting → 403 ACTION_NOT_PERMITTED (role denial, before any row is read);
- AC7 / AC10 (SM-3 SATISFIED) a non-report Manager and a non-owner Employee get a 404 BYTE-IDENTICAL
  to a nonexistent id on every identifier endpoint;
- AC8 authority is evaluated at DECISION time (a reassigned applicant is decided by the new Manager);
- SM-4 the audit-row count equals the transition count, one-to-one.

Real PostgreSQL: the guarded UPDATE, the `SELECT … FOR UPDATE` balance moves and the scope predicates
all run through the live database and the real router. `conftest` skips loudly if Postgres is absent.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, delete, func, select, update
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
)
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 403/404/409 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
# Roomy entitlement: several small requests inside one test never exhaust it, so a refusal in these
# tests is always the transition guard under test, never an incidental INSUFFICIENT_BALANCE.
_ENTITLEMENT = 20
_client = TestClient(app)

# A future 3-Working-Day range (today is 2026-07-13), no weekend, no seeded holiday: Mon–Wed.
_MON = datetime.date(2026, 8, 3)  # Monday    (weekday()==0)
_WED = datetime.date(2026, 8, 5)  # Wednesday (weekday()==2)
_EXPECTED_DAYS = 3  # Mon, Tue, Wed


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        leave_type_id: uuid.UUID,
        report_id: uuid.UUID,
        report_token: str,
        coworker_id: uuid.UUID,
        coworker_token: str,
        b_report_id: uuid.UUID,
        b_report_token: str,
        manager_a_id: uuid.UUID,
        manager_a_token: str,
        manager_b_id: uuid.UUID,
        manager_b_token: str,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.leave_type_id = leave_type_id
        self.report_id = report_id
        self.report_token = report_token
        self.coworker_id = coworker_id
        self.coworker_token = coworker_token
        self.b_report_id = b_report_id
        self.b_report_token = b_report_token
        self.manager_a_id = manager_a_id
        self.manager_a_token = manager_a_token
        self.manager_b_id = manager_b_id
        self.manager_b_token = manager_b_token
        self.admin_token = admin_token


@pytest.fixture
def world(db_connection: Connection) -> Iterator[_World]:
    """Two Managers (A, B), two of A's reports, one of B's, an Admin, one Leave Type (20 days).

    All join 1 January, so a Leave Type created through the service materializes each a full-
    entitlement balance (Story 2.4's hook). `report`/`coworker` report to Manager A; `b_report`
    reports to Manager B — the cross-team pair AC4's predicate isolation and AC7's non-report 404
    both need.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"dc-dept-{suffix}"
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
            email=f"dc-{label}-{suffix}@example.com",
            full_name=f"DC {label}",
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

        manager_a_id = _employee(
            session, department.id, label="mgra", role=vocabulary.ROLE_MANAGER, manager_id=None
        )
        manager_b_id = _employee(
            session, department.id, label="mgrb", role=vocabulary.ROLE_MANAGER, manager_id=None
        )
        report_id = _employee(
            session, department.id, label="rep", role=vocabulary.ROLE_EMPLOYEE, manager_id=manager_a_id
        )
        coworker_id = _employee(
            session, department.id, label="cow", role=vocabulary.ROLE_EMPLOYEE, manager_id=manager_a_id
        )
        b_report_id = _employee(
            session, department.id, label="brep", role=vocabulary.ROLE_EMPLOYEE, manager_id=manager_b_id
        )
        admin_id = _employee(
            session, department.id, label="adm", role=vocabulary.ROLE_ADMIN, manager_id=None
        )
        session.commit()

    report_token = security.create_token(str(report_id), vocabulary.ROLE_EMPLOYEE)
    coworker_token = security.create_token(str(coworker_id), vocabulary.ROLE_EMPLOYEE)
    b_report_token = security.create_token(str(b_report_id), vocabulary.ROLE_EMPLOYEE)
    manager_a_token = security.create_token(str(manager_a_id), vocabulary.ROLE_MANAGER)
    manager_b_token = security.create_token(str(manager_b_id), vocabulary.ROLE_MANAGER)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    leave_type_id = leave_types_service.create_leave_type(
        code=f"DC-{suffix}",
        name="Decide type",
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
            coworker_id,
            coworker_token,
            b_report_id,
            b_report_token,
            manager_a_id,
            manager_a_token,
            manager_b_id,
            manager_b_token,
            admin_token,
        )
    finally:
        with Session(get_engine()) as session:
            session.execute(
                delete(AuditEntry).where(
                    AuditEntry.subject_id.in_(
                        select(LeaveRequest.id).where(
                            LeaveRequest.leave_type_id == leave_type_id
                        )
                    )
                )
            )
            session.execute(
                delete(LeaveRequest).where(LeaveRequest.leave_type_id == leave_type_id)
            )
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id == leave_type_id)
            )
            session.execute(
                update(Employee)
                .where(Employee.email.like(f"%{suffix}%"))
                .values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id == leave_type_id))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _balance_row(
    employee_id: uuid.UUID, leave_type_id: uuid.UUID
) -> tuple[int, int, int]:
    with Session(get_engine()) as session:
        row = session.execute(
            select(LeaveBalance.accrued, LeaveBalance.reserved, LeaveBalance.consumed).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == _YEAR,
            )
        ).one()
        return (row.accrued, row.reserved, row.consumed)


def _audit_count(subject_id: uuid.UUID) -> int:
    with Session(get_engine()) as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(AuditEntry)
                .where(AuditEntry.subject_id == subject_id)
            )
            or 0
        )


def _audit_rows(subject_id: uuid.UUID) -> list[AuditEntry]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditEntry).where(AuditEntry.subject_id == subject_id)
            ).all()
        )


def _submit(
    token: str,
    leave_type_id: uuid.UUID,
    start: datetime.date = _MON,
    end: datetime.date = _WED,
) -> dict:
    """Submit a request through the real endpoint and return its JSON body (a PENDING row)."""
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


# --- AC1: approve moves reserved→consumed, one audit row ------------------------------------


def test_manager_approves_report_request(world: _World) -> None:
    """AC1: Manager A approves a report's PENDING request → 200 APPROVED, `reserved → consumed` by
    exactly `leave_days`, Available unchanged, and exactly ONE EMPLOYEE/APPROVED audit row."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])
    after_submit = _balance_row(world.report_id, world.leave_type_id)
    assert after_submit[1] == _EXPECTED_DAYS  # reserved == leave_days
    assert _audit_count(request_id) == 1  # the submission row

    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_a_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == vocabulary.STATUS_APPROVED
    assert body["leave_days"] == _EXPECTED_DAYS
    assert body["employee_id"] == str(world.report_id)
    assert body["employee_name"] == "DC rep"

    accrued, reserved, consumed = _balance_row(world.report_id, world.leave_type_id)
    assert reserved == 0
    assert consumed == _EXPECTED_DAYS
    assert accrued - consumed - reserved == after_submit[0] - _EXPECTED_DAYS  # available unchanged

    rows = _audit_rows(request_id)
    assert len(rows) == 2  # submission + approval
    approval = [r for r in rows if r.to_state == vocabulary.STATUS_APPROVED][0]
    assert approval.from_state == vocabulary.STATUS_PENDING
    assert approval.actor_type == vocabulary.ACTOR_EMPLOYEE
    assert approval.actor_id == world.manager_a_id
    assert approval.reason == vocabulary.REASON_APPROVED


# --- AC1: reject releases the reservation, one audit row ------------------------------------


def test_manager_rejects_report_request(world: _World) -> None:
    """AC1: Manager A rejects a report's PENDING request → 200 REJECTED, the reservation released
    (reserved down, Available back up), one EMPLOYEE/REJECTED audit row."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])
    before = _balance_row(world.report_id, world.leave_type_id)  # reserved == 3

    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/reject",
        headers=_auth(world.manager_a_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == vocabulary.STATUS_REJECTED

    accrued, reserved, consumed = _balance_row(world.report_id, world.leave_type_id)
    assert reserved == 0
    assert consumed == 0
    assert accrued == before[0]  # available fully restored

    rows = _audit_rows(request_id)
    assert len(rows) == 2
    rejection = [r for r in rows if r.to_state == vocabulary.STATUS_REJECTED][0]
    assert rejection.reason == vocabulary.REASON_REJECTED
    assert rejection.actor_id == world.manager_a_id


# --- AC2: the guarded transition — a lost race is a clean 409, nothing written --------------


def test_approve_after_cancel_is_409_and_writes_nothing(world: _World) -> None:
    """AC2: approving a request the applicant already CANCELLED → 409 TRANSITION_NOT_ALLOWED, the
    balance byte-unchanged and NO new audit row (the whole transaction rolled back)."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])

    cancel = _client.post(
        f"/api/v1/leave-requests/{request_id}/cancel", headers=_auth(world.report_token)
    )
    assert cancel.status_code == 200, cancel.text
    balance_after_cancel = _balance_row(world.report_id, world.leave_type_id)
    audit_after_cancel = _audit_count(request_id)  # submission + cancel == 2

    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_a_token),
    )
    assert response.status_code == 409
    assert response.json()["code"] == vocabulary.TRANSITION_NOT_ALLOWED

    # Rolled back: balance and audit unchanged by the failed approve.
    assert _balance_row(world.report_id, world.leave_type_id) == balance_after_cancel
    assert _audit_count(request_id) == audit_after_cancel


# --- AC3: the applicant cancels their own request; non-owner 404; settled 409 ----------------


def test_applicant_cancels_own_request(world: _World) -> None:
    """AC3: the applicant cancels their OWN Pending request → 200 CANCELLED, the reservation
    released, one EMPLOYEE/CANCELLED audit row naming the applicant."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])

    response = _client.post(
        f"/api/v1/leave-requests/{request_id}/cancel", headers=_auth(world.report_token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == vocabulary.STATUS_CANCELLED

    _, reserved, consumed = _balance_row(world.report_id, world.leave_type_id)
    assert reserved == 0 and consumed == 0

    cancellation = [
        r for r in _audit_rows(request_id) if r.to_state == vocabulary.STATUS_CANCELLED
    ][0]
    assert cancellation.actor_type == vocabulary.ACTOR_EMPLOYEE
    assert cancellation.actor_id == world.report_id
    assert cancellation.reason == vocabulary.REASON_CANCELLED


def test_non_owner_cannot_cancel_and_settled_cannot_cancel(world: _World) -> None:
    """AC3: a NON-OWNER cancelling → 404 (out of scope); cancelling a SETTLED request → 409."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])

    # A coworker (also a report of A) is not the owner → byte-identical 404.
    non_owner = _client.post(
        f"/api/v1/leave-requests/{request_id}/cancel", headers=_auth(world.coworker_token)
    )
    assert non_owner.status_code == 404
    assert non_owner.json()["code"] == vocabulary.RESOURCE_NOT_FOUND

    # Settle it (approve), then the applicant cancelling a non-PENDING request → 409.
    _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_a_token),
    )
    settled = _client.post(
        f"/api/v1/leave-requests/{request_id}/cancel", headers=_auth(world.report_token)
    )
    assert settled.status_code == 409
    assert settled.json()["code"] == vocabulary.TRANSITION_NOT_ALLOWED


# --- AC6: an Admin may read every request and decide none ------------------------------------


def test_admin_cannot_approve_or_reject(world: _World) -> None:
    """AC6: an Admin approving/rejecting → 403 ACTION_NOT_PERMITTED (a role denial, decided by the
    require_role gate BEFORE any row is read — DR-13, G3)."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])

    for verb in ("approve", "reject"):
        response = _client.post(
            f"/api/v1/leave-requests/{request_id}/{verb}", headers=_auth(world.admin_token)
        )
        assert response.status_code == 403, verb
        assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED


def test_role_gate_denies_employee_and_precedes_any_row_read(world: _World) -> None:
    """AC6/DR-13/G3: the `require_role(MANAGER)` gate denies BEFORE any row is read.

    Two things the Admin-only test above cannot show:
    - An EMPLOYEE (not just an Admin) approving/rejecting is also a 403 by the same gate — only a
      MANAGER role passes; the `reports` scope then decides ownership.
    - The gate runs BEFORE the scope/existence check: an Admin approving a NONEXISTENT id gets a
      `403` (a role denial), never a `404`. If the gate ran after the row lookup this would be a
      404 — so the 403 here is the proof that role is decided first (G3).
    """
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = uuid.UUID(submitted["id"])

    # An Employee (the applicant themselves) hitting approve/reject → 403, not a scope 404.
    for verb in ("approve", "reject"):
        denied = _client.post(
            f"/api/v1/leave-requests/{request_id}/{verb}", headers=_auth(world.report_token)
        )
        assert denied.status_code == 403, verb
        assert denied.json()["code"] == vocabulary.ACTION_NOT_PERMITTED

    # An Admin approving a NONEXISTENT id → still 403 (role denied before the row is ever read),
    # never 404 — the G3 ordering guarantee made observable.
    ghost = _client.post(
        f"/api/v1/leave-requests/{uuid.uuid4()}/approve", headers=_auth(world.admin_token)
    )
    assert ghost.status_code == 403
    assert ghost.json()["code"] == vocabulary.ACTION_NOT_PERMITTED


# --- AC7 / AC10: SM-3 satisfied — the byte-identical 404 -------------------------------------


def test_non_report_manager_and_non_owner_get_byte_identical_404(world: _World) -> None:
    """AC7/AC10 (SM-3 SATISFIED): a non-report Manager on GET/approve/reject, and a non-owner
    Employee on cancel, get a 404 BYTE-IDENTICAL to the 404 for a nonexistent UUID. This is the
    FR-03/DR-12 guarantee the whole scope machinery exists for — assert byte-equality explicitly."""
    submitted = _submit(world.report_token, world.leave_type_id)
    real_id = submitted["id"]  # A's report's request
    ghost_id = str(uuid.uuid4())  # never existed

    # Manager B is not the applicant's Manager: an existing-but-out-of-scope id must be
    # indistinguishable from a nonexistent one, method by method.
    for method, path_suffix, token in (
        ("get", "", world.manager_b_token),
        ("post", "/approve", world.manager_b_token),
        ("post", "/reject", world.manager_b_token),
        ("post", "/cancel", world.coworker_token),  # a non-owner Employee
    ):
        caller = getattr(_client, method)
        out_of_scope = caller(
            f"/api/v1/leave-requests/{real_id}{path_suffix}", headers=_auth(token)
        )
        nonexistent = caller(
            f"/api/v1/leave-requests/{ghost_id}{path_suffix}", headers=_auth(token)
        )
        assert out_of_scope.status_code == 404, (method, path_suffix)
        assert nonexistent.status_code == 404, (method, path_suffix)
        # Byte-identical: same status AND same body bytes (the one not_found envelope).
        assert out_of_scope.content == nonexistent.content, (method, path_suffix)


# --- AC4: list scoping, status filter, page clamp -------------------------------------------


def test_list_is_scoped_filtered_and_paged(world: _World) -> None:
    """AC4: an Employee's list is their own; a Manager's is their reports' (not other teams');
    an Admin's is all. The scope is a predicate — B's report never appears in A's list. The
    `status` filter narrows, and `page_size` is clamped to the server maximum."""
    rep = _submit(world.report_token, world.leave_type_id)
    cow = _submit(world.coworker_token, world.leave_type_id)
    brep = _submit(world.b_report_token, world.leave_type_id)
    rep_id, cow_id, brep_id = rep["id"], cow["id"], brep["id"]

    # Employee: only their own.
    own = _client.get("/api/v1/leave-requests", headers=_auth(world.report_token)).json()
    assert {item["id"] for item in own["items"]} == {rep_id}
    assert own["total"] == 1

    # Manager A: their reports' (rep + cow), never their own, never B's report.
    a_list = _client.get(
        "/api/v1/leave-requests", headers=_auth(world.manager_a_token)
    ).json()
    a_ids = {item["id"] for item in a_list["items"]}
    assert a_ids == {rep_id, cow_id}
    assert brep_id not in a_ids  # the predicate isolates B's team

    # Admin: all three appear.
    admin_ids = {
        item["id"]
        for item in _client.get(
            "/api/v1/leave-requests", headers=_auth(world.admin_token)
        ).json()["items"]
    }
    assert {rep_id, cow_id, brep_id} <= admin_ids

    # Status filter: approve rep's request, then PENDING excludes it and APPROVED includes it.
    _client.post(
        f"/api/v1/leave-requests/{rep_id}/approve", headers=_auth(world.manager_a_token)
    )
    pending = _client.get(
        "/api/v1/leave-requests",
        params={"status": vocabulary.STATUS_PENDING},
        headers=_auth(world.manager_a_token),
    ).json()
    assert {item["id"] for item in pending["items"]} == {cow_id}
    approved = _client.get(
        "/api/v1/leave-requests",
        params={"status": vocabulary.STATUS_APPROVED},
        headers=_auth(world.manager_a_token),
    ).json()
    assert {item["id"] for item in approved["items"]} == {rep_id}

    # page_size is clamped to the server maximum (100), never rejected.
    clamped = _client.get(
        "/api/v1/leave-requests",
        params={"page_size": 200},
        headers=_auth(world.admin_token),
    ).json()
    assert clamped["page_size"] == 100


def test_list_status_filter_rejects_bad_value(world: _World) -> None:
    """AC4: an unrecognized `status` is a framework 422 (input validation), not a domain error."""
    response = _client.get(
        "/api/v1/leave-requests",
        params={"status": "NOT_A_STATUS"},
        headers=_auth(world.report_token),
    )
    assert response.status_code == 422


# --- AC5: by-id read returns the stored (frozen) leave_days ----------------------------------


def test_get_by_id_returns_stored_leave_days(world: _World) -> None:
    """AC5: `GET /leave-requests/<id>` returns the STORED `leave_days` (never recomputed), with its
    Leave Type; an out-of-scope id → 404."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = submitted["id"]

    read = _client.get(
        f"/api/v1/leave-requests/{request_id}", headers=_auth(world.report_token)
    )
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["leave_days"] == submitted["leave_days"]  # the frozen admitted count
    assert body["leave_type_id"] == str(world.leave_type_id)
    assert body["leave_type_code"] == f"DC-{world.suffix}"
    assert body["status"] == vocabulary.STATUS_PENDING

    # An out-of-scope caller (Manager B) → 404.
    out = _client.get(
        f"/api/v1/leave-requests/{request_id}", headers=_auth(world.manager_b_token)
    )
    assert out.status_code == 404


def test_manager_own_request_is_absent_from_reads(world: _World) -> None:
    """AC4/AC5 decision (Open Question #4, resolved 2026-07-13): a Manager's OWN submitted request is
    INTENTIONALLY not returned by these reads. A Manager's scope is `REPORTS`
    (`Employee.manager_id == actor.id`), which excludes the Manager's own row — so the request is
    absent from `GET /leave-requests` and yields a byte-identical 404 from `GET /leave-requests/<id>`
    (they may still cancel it via the `self`-scoped cancel). This locks in the "reports-only" reading
    of the AC; widening to "my team AND me" is a later filter change, not this story.
    """
    # A Manager submits their own request (submit is `get_current_employee`, any role; the fixture
    # materializes a balance for every employee, Managers included, since all join 1 January).
    own = _submit(world.manager_a_token, world.leave_type_id)
    own_id = own["id"]

    # It is NOT in the Manager's own list (their list is their reports', not their own).
    listing = _client.get(
        "/api/v1/leave-requests", headers=_auth(world.manager_a_token)
    ).json()
    assert own_id not in {item["id"] for item in listing["items"]}

    # And the by-id read of their own request is a 404 byte-identical to a nonexistent id.
    mine = _client.get(
        f"/api/v1/leave-requests/{own_id}", headers=_auth(world.manager_a_token)
    )
    ghost = _client.get(
        f"/api/v1/leave-requests/{uuid.uuid4()}", headers=_auth(world.manager_a_token)
    )
    assert mine.status_code == 404
    assert mine.content == ghost.content


# --- AC8: authority is evaluated at decision time (reassignment) -----------------------------


def test_authority_is_evaluated_at_decision_time(world: _World) -> None:
    """AC8/DR-12: a Pending request's applicant is reassigned to Manager B. B now decides it
    successfully; A — no longer the applicant's Manager — gets a 404. Authority binds at decision
    time (the scope predicate `Employee.manager_id == :actor_id` at request time), not submission."""
    submitted = _submit(world.report_token, world.leave_type_id)
    request_id = submitted["id"]

    # Reassign the applicant from Manager A to Manager B (Admin PATCH /employees/<id>).
    reassign = _client.patch(
        f"/api/v1/employees/{world.report_id}",
        json={"manager_id": str(world.manager_b_id)},
        headers=_auth(world.admin_token),
    )
    assert reassign.status_code == 200, reassign.text

    # Manager A is no longer authorized over this applicant → 404 (a scope miss, decided now).
    a_attempt = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_a_token),
    )
    assert a_attempt.status_code == 404

    # Manager B, the new Manager, decides it successfully.
    b_attempt = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_b_token),
    )
    assert b_attempt.status_code == 200, b_attempt.text
    assert b_attempt.json()["status"] == vocabulary.STATUS_APPROVED


# --- SM-4: one audit row per transition, one-to-one ------------------------------------------


def test_audit_count_equals_transition_count(world: _World) -> None:
    """SM-4: the count of audit rows equals the count of state transitions performed, one-to-one —
    a submission plus each decision, and no more."""
    submitted = _submit(world.report_token, world.leave_type_id)  # transition 1 (NULL → PENDING)
    request_id = uuid.UUID(submitted["id"])
    assert _audit_count(request_id) == 1

    _client.post(
        f"/api/v1/leave-requests/{request_id}/reject", headers=_auth(world.manager_a_token)
    )  # transition 2 (PENDING → REJECTED)
    assert _audit_count(request_id) == 2

    # A refused transition (rejecting an already-settled request) adds NO audit row.
    refused = _client.post(
        f"/api/v1/leave-requests/{request_id}/reject", headers=_auth(world.manager_a_token)
    )
    assert refused.status_code == 409
    assert _audit_count(request_id) == 2


# --- Auth: no token is 401 ------------------------------------------------------------------


def test_transition_without_token_is_401(world: _World) -> None:
    """A transition with no Bearer token is a 401 TOKEN_INVALID, like every other endpoint."""
    response = _client.post(f"/api/v1/leave-requests/{uuid.uuid4()}/cancel")
    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID
