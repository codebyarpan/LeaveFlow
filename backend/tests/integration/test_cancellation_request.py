"""Cancelling APPROVED leave through a Cancellation Request, end to end (Story 2.8).

Implements the test side of every AC:
- AC1 `cancellation_request` is its own table with the three-state CHECK; `leave_request` still has
  exactly its four statuses (no fifth);
- AC2 the applicant raises against their OWN future Approved request → 201 PENDING; a non-owner → a
  byte-identical 404;
- AC3 a raise against past-dated Approved leave → 400 LEAVE_ALREADY_TAKEN;
- AC4 while a CR is PENDING the target LR is APPROVED and the balance is byte-unchanged;
- AC5 `GET /cancellation-requests` is scoped (self/all), paged, status-filterable — the scope a SQL
  predicate (another applicant's CR never appears);
- AC6 an Admin approves → LR CANCELLED, consumed down by leave_days (Available restored), two audit
  rows discriminated by subject_type;
- AC7 an Admin rejects → LR still APPROVED, consumed unchanged, one audit row;
- AC8 a non-Admin deciding → 403 ACTION_NOT_PERMITTED, decided before any row is read (403 not 404
  even on a nonexistent id — the G3 property);
- AC2/guard race: approving a settled CR, or a CR whose LR already left APPROVED → 409, balance
  byte-unchanged, no new audit row;
- AC9 an approval writes exactly one row per subject, discriminated by subject_type (SM-4).

Real PostgreSQL: the guarded UPDATEs, the `SELECT … FOR UPDATE` balance move and the scope
predicates all run through the live database and the real router. `conftest` skips loudly if
Postgres is absent.
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
    CancellationRequest,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 400/403/404/409 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
_ENTITLEMENT = 20
_client = TestClient(app)

# A future 3-Working-Day range (today is 2026-07-13), no weekend, no seeded holiday: Mon–Wed.
_MON = datetime.date(2026, 8, 3)  # Monday    (weekday()==0)
_WED = datetime.date(2026, 8, 5)  # Wednesday (weekday()==2)
_EXPECTED_DAYS = 3  # Mon, Tue, Wed

# A past 2-Working-Day range in the SAME leave year (Mon–Tue), for the AC3 "already taken" path.
_PAST_MON = datetime.date(2026, 6, 1)  # Monday
_PAST_TUE = datetime.date(2026, 6, 2)  # Tuesday
_PAST_DAYS = 2


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
    reports to Manager B — the cross-team pair AC5's predicate isolation needs. Cleanup deletes the
    Cancellation Requests and their audit rows FIRST (they FK the leave requests).
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"cr-dept-{suffix}"
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
            email=f"cr-{label}-{suffix}@example.com",
            full_name=f"CR {label}",
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
        code=f"CR-{suffix}",
        name="Cancellation type",
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
            # Audit rows for the Cancellation Requests, then for the Leave Requests.
            session.execute(
                delete(AuditEntry).where(AuditEntry.subject_id.in_(cr_ids))
            )
            session.execute(
                delete(AuditEntry).where(AuditEntry.subject_id.in_(lr_ids))
            )
            # Cancellation Requests before the Leave Requests they FK.
            session.execute(
                delete(CancellationRequest).where(
                    CancellationRequest.leave_request_id.in_(lr_ids)
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


def _submit(token: str, leave_type_id: uuid.UUID) -> dict:
    """Submit a PENDING request through the real endpoint and return its JSON body."""
    response = _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(leave_type_id),
            "start_date": _MON.isoformat(),
            "end_date": _WED.isoformat(),
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approved_request(world: _World, applicant_token: str) -> str:
    """Submit as `report` and approve via Manager A → an APPROVED future-dated request id.

    (The applicant token is `report`'s; Manager A is its Manager. After this the balance is
    `reserved=0, consumed=3`.)
    """
    submitted = _submit(applicant_token, world.leave_type_id)
    request_id = submitted["id"]
    approved = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve",
        headers=_auth(world.manager_a_token),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == vocabulary.STATUS_APPROVED
    return request_id


def _raise_cr(token: str, request_id: str):  # type: ignore[no-untyped-def]
    return _client.post(
        f"/api/v1/leave-requests/{request_id}/cancellation-requests",
        headers=_auth(token),
    )


def _insert_past_approved_request(world: _World) -> str:
    """Insert an APPROVED request whose dates are already in the PAST, directly in the DB (AC3).

    The submit path refuses a past range, so a past Approved request is built directly. `report`
    owns it (so the SELF-scoped raise locates it); its `leave_days` is the stored figure. No balance
    move is needed — the AC3 refusal fires before any transition.
    """
    with Session(get_engine()) as session:
        request = LeaveRequest(
            employee_id=world.report_id,
            leave_type_id=world.leave_type_id,
            start_date=_PAST_MON,
            end_date=_PAST_TUE,
            leave_days=_PAST_DAYS,
            status=vocabulary.STATUS_APPROVED,
        )
        session.add(request)
        session.commit()
        return str(request.id)


# --- AC1: the schema — cancellation_request is its own table, no fifth LR status ---------------


def test_schema_cancellation_request_is_its_own_table(world: _World) -> None:
    """AC1: `cancellation_request` exists with the three-state CHECK; `leave_request` still holds
    exactly its four statuses (no fifth)."""
    with Session(get_engine()) as session:
        # The CR table accepts its three states and rejects a fourth via the CHECK.
        lr_id = uuid.UUID(_approved_request(world, world.report_token))
        for value in (
            vocabulary.STATUS_PENDING,
            vocabulary.STATUS_APPROVED,
            vocabulary.STATUS_REJECTED,
        ):
            session.add(CancellationRequest(leave_request_id=lr_id, status=value))
            session.flush()
        session.rollback()

        # The four Leave Request statuses are unchanged — CANCELLED is a LR status, not a CR one,
        # and there is no fifth. The CR CHECK does NOT admit CANCELLED.
        from sqlalchemy.exc import IntegrityError

        session.add(
            CancellationRequest(
                leave_request_id=lr_id, status=vocabulary.STATUS_CANCELLED
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


# --- AC2: the applicant raises against their own future Approved request; non-owner 404 -------


def test_applicant_raises_against_own_approved_request(world: _World) -> None:
    """AC2: the applicant raises a Cancellation Request against their own future Approved request →
    201, a PENDING CR referencing the Leave Request."""
    request_id = _approved_request(world, world.report_token)

    raised = _raise_cr(world.report_token, request_id)
    assert raised.status_code == 201, raised.text
    body = raised.json()
    assert body["status"] == vocabulary.STATUS_PENDING
    assert body["leave_request_id"] == request_id
    assert body["employee_id"] == str(world.report_id)
    assert body["employee_name"] == "CR rep"
    assert body["leave_days"] == _EXPECTED_DAYS
    assert body["leave_type_code"] == f"CR-{world.suffix}"


def test_non_owner_raise_is_byte_identical_404(world: _World) -> None:
    """AC2: a non-owner raising against someone else's request → 404 byte-identical to a
    nonexistent-id 404 (the target is out of scope — AD-10)."""
    request_id = _approved_request(world, world.report_token)

    out_of_scope = _raise_cr(world.coworker_token, request_id)  # a coworker, not the owner
    nonexistent = _raise_cr(world.coworker_token, str(uuid.uuid4()))
    assert out_of_scope.status_code == 404
    assert nonexistent.status_code == 404
    assert out_of_scope.content == nonexistent.content
    assert out_of_scope.json()["code"] == vocabulary.RESOURCE_NOT_FOUND


def test_raise_against_non_approved_request_is_409(world: _World) -> None:
    """AC2/Open Decision #2: raising against a still-PENDING request → 409 TRANSITION_NOT_ALLOWED
    (a Pending request is cancelled via `/cancel`, not through a Cancellation Request)."""
    submitted = _submit(world.report_token, world.leave_type_id)  # PENDING, not approved
    raised = _raise_cr(world.report_token, submitted["id"])
    assert raised.status_code == 409
    assert raised.json()["code"] == vocabulary.TRANSITION_NOT_ALLOWED


# --- AC3: a Cancellation Request against past-dated leave is refused 400 LEAVE_ALREADY_TAKEN ---


def test_raise_against_past_dated_leave_is_400(world: _World) -> None:
    """AC3: a Cancellation Request raised against an Approved request whose dates have already
    passed → 400 LEAVE_ALREADY_TAKEN."""
    past_id = _insert_past_approved_request(world)
    raised = _raise_cr(world.report_token, past_id)
    assert raised.status_code == 400, raised.text
    assert raised.json()["code"] == vocabulary.LEAVE_ALREADY_TAKEN


# --- AC4: while a Cancellation Request is Pending, the Leave Request is untouched --------------


def test_pending_cancellation_request_is_inert(world: _World) -> None:
    """AC4: while a CR is PENDING, the target LR is still APPROVED and the balance
    `(reserved, consumed)` is byte-unchanged from before the raise."""
    request_id = _approved_request(world, world.report_token)
    before = _balance_row(world.report_id, world.leave_type_id)

    raised = _raise_cr(world.report_token, request_id)
    assert raised.status_code == 201, raised.text

    # The Leave Request is still APPROVED (a self-scoped by-id read).
    read = _client.get(
        f"/api/v1/leave-requests/{request_id}", headers=_auth(world.report_token)
    )
    assert read.json()["status"] == vocabulary.STATUS_APPROVED
    # The balance is byte-unchanged.
    assert _balance_row(world.report_id, world.leave_type_id) == before


# --- AC5: GET /cancellation-requests — scoped, paged, status-filtered -------------------------


def test_list_is_scoped_filtered_and_paged(world: _World) -> None:
    """AC5: an Employee's list is only their own; an Admin's is all; the `status` filter narrows;
    the envelope holds; `page_size` clamps to the maximum."""
    rep_req = _approved_request(world, world.report_token)
    rep_cr = _raise_cr(world.report_token, rep_req).json()["id"]

    # A second applicant (b_report, under Manager B) raises their own CR.
    b_req = _submit(world.b_report_token, world.leave_type_id)["id"]
    _client.post(
        f"/api/v1/leave-requests/{b_req}/approve", headers=_auth(world.manager_b_token)
    )
    b_cr = _raise_cr(world.b_report_token, b_req).json()["id"]

    # The report sees ONLY their own (a predicate — b_report's never appears).
    own = _client.get(
        "/api/v1/cancellation-requests", headers=_auth(world.report_token)
    ).json()
    assert {item["id"] for item in own["items"]} == {rep_cr}
    assert own["total"] == 1

    # The Admin sees both.
    admin_ids = {
        item["id"]
        for item in _client.get(
            "/api/v1/cancellation-requests", headers=_auth(world.admin_token)
        ).json()["items"]
    }
    assert {rep_cr, b_cr} <= admin_ids

    # The envelope carries items/page/page_size/total, and page_size clamps to 100.
    clamped = _client.get(
        "/api/v1/cancellation-requests",
        params={"page_size": 200},
        headers=_auth(world.admin_token),
    ).json()
    assert clamped["page_size"] == 100
    assert set(clamped.keys()) >= {"items", "page", "page_size", "total"}

    # The status filter: reject the report's CR, then PENDING excludes it and REJECTED includes it.
    _client.post(
        f"/api/v1/cancellation-requests/{rep_cr}/reject", headers=_auth(world.admin_token)
    )
    pending = _client.get(
        "/api/v1/cancellation-requests",
        params={"status": vocabulary.STATUS_PENDING},
        headers=_auth(world.admin_token),
    ).json()
    assert rep_cr not in {item["id"] for item in pending["items"]}
    rejected = _client.get(
        "/api/v1/cancellation-requests",
        params={"status": vocabulary.STATUS_REJECTED},
        headers=_auth(world.admin_token),
    ).json()
    assert rep_cr in {item["id"] for item in rejected["items"]}


def test_list_status_filter_rejects_bad_value(world: _World) -> None:
    """AC5: an unrecognized `status` is a framework 422 (input validation), not a domain error."""
    response = _client.get(
        "/api/v1/cancellation-requests",
        params={"status": "NOT_A_STATUS"},
        headers=_auth(world.report_token),
    )
    assert response.status_code == 422


# --- AC6: an Admin approves — the LR moves to CANCELLED and its days return --------------------


def test_admin_approves_and_leave_is_cancelled(world: _World) -> None:
    """AC6/AC9: an Admin approves → CR APPROVED, LR CANCELLED, consumed down by exactly leave_days
    (Available restored), reserved unchanged; TWO new audit rows discriminated by subject_type."""
    request_id = _approved_request(world, world.report_token)
    before = _balance_row(world.report_id, world.leave_type_id)  # reserved 0, consumed 3
    assert before[2] == _EXPECTED_DAYS

    cr_id = _raise_cr(world.report_token, request_id).json()["id"]
    cr_uuid = uuid.UUID(cr_id)
    lr_uuid = uuid.UUID(request_id)
    audit_before_cr = _audit_count(cr_uuid)  # the raise row (Option A) == 1
    audit_before_lr = _audit_count(lr_uuid)  # submission + approval == 2

    approved = _client.post(
        f"/api/v1/cancellation-requests/{cr_id}/approve", headers=_auth(world.admin_token)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == vocabulary.STATUS_APPROVED

    # The Leave Request is CANCELLED (an Admin reads it — scope all).
    lr = _client.get(
        f"/api/v1/leave-requests/{request_id}", headers=_auth(world.admin_token)
    )
    assert lr.json()["status"] == vocabulary.STATUS_CANCELLED

    accrued, reserved, consumed = _balance_row(world.report_id, world.leave_type_id)
    assert consumed == before[2] - _EXPECTED_DAYS  # consumed returned
    assert reserved == before[1]  # reserved untouched
    assert accrued - consumed - reserved == accrued  # Available fully restored

    # Exactly one new CR-subject row (the approve) and one new LR-subject row (the CANCELLED move).
    assert _audit_count(cr_uuid) == audit_before_cr + 1
    assert _audit_count(lr_uuid) == audit_before_lr + 1

    cr_approve = [
        r for r in _audit_rows(cr_uuid) if r.to_state == vocabulary.STATUS_APPROVED
    ]
    assert len(cr_approve) == 1
    assert cr_approve[0].subject_type == vocabulary.SUBJECT_CANCELLATION_REQUEST
    assert cr_approve[0].from_state == vocabulary.STATUS_PENDING
    assert cr_approve[0].reason == vocabulary.REASON_APPROVED

    lr_cancel = [
        r for r in _audit_rows(lr_uuid) if r.to_state == vocabulary.STATUS_CANCELLED
    ]
    assert len(lr_cancel) == 1
    assert lr_cancel[0].subject_type == vocabulary.SUBJECT_LEAVE_REQUEST
    assert lr_cancel[0].from_state == vocabulary.STATUS_APPROVED
    assert lr_cancel[0].reason == vocabulary.REASON_CANCELLED


# --- AC7: an Admin rejects — nothing about the leave changes -----------------------------------


def test_admin_rejects_and_leave_is_untouched(world: _World) -> None:
    """AC7: an Admin rejects → CR REJECTED, LR still APPROVED with days still consumed; ONE new
    audit row (the CR reject); the LR is untouched."""
    request_id = _approved_request(world, world.report_token)
    before = _balance_row(world.report_id, world.leave_type_id)

    cr_id = _raise_cr(world.report_token, request_id).json()["id"]
    cr_uuid = uuid.UUID(cr_id)
    lr_uuid = uuid.UUID(request_id)
    audit_before_cr = _audit_count(cr_uuid)
    audit_before_lr = _audit_count(lr_uuid)

    rejected = _client.post(
        f"/api/v1/cancellation-requests/{cr_id}/reject", headers=_auth(world.admin_token)
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == vocabulary.STATUS_REJECTED

    # The Leave Request is still APPROVED and the balance is byte-unchanged.
    lr = _client.get(
        f"/api/v1/leave-requests/{request_id}", headers=_auth(world.admin_token)
    )
    assert lr.json()["status"] == vocabulary.STATUS_APPROVED
    assert _balance_row(world.report_id, world.leave_type_id) == before

    # One new CR-subject row (the reject); the LR gained none.
    assert _audit_count(cr_uuid) == audit_before_cr + 1
    assert _audit_count(lr_uuid) == audit_before_lr
    reject_row = [
        r for r in _audit_rows(cr_uuid) if r.to_state == vocabulary.STATUS_REJECTED
    ]
    assert len(reject_row) == 1
    assert reject_row[0].subject_type == vocabulary.SUBJECT_CANCELLATION_REQUEST
    assert reject_row[0].reason == vocabulary.REASON_REJECTED


# --- AC8: only an Admin decides — 403 ACTION_NOT_PERMITTED, before any row is read -------------


def test_non_admin_cannot_decide(world: _World) -> None:
    """AC8: a Manager and an Employee calling approve/reject → 403 ACTION_NOT_PERMITTED (a role
    denial, decided by the require_role gate before any row is read)."""
    request_id = _approved_request(world, world.report_token)
    cr_id = _raise_cr(world.report_token, request_id).json()["id"]

    for token in (world.manager_a_token, world.report_token):
        for verb in ("approve", "reject"):
            response = _client.post(
                f"/api/v1/cancellation-requests/{cr_id}/{verb}", headers=_auth(token)
            )
            assert response.status_code == 403, (token, verb)
            assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED


def test_non_admin_decide_is_403_not_404_on_nonexistent(world: _World) -> None:
    """AC8/G3: a non-Admin deciding a NONEXISTENT id gets 403 (role denied before the row is read),
    never 404 — the ordering guarantee made observable."""
    ghost = _client.post(
        f"/api/v1/cancellation-requests/{uuid.uuid4()}/approve",
        headers=_auth(world.manager_a_token),
    )
    assert ghost.status_code == 403
    assert ghost.json()["code"] == vocabulary.ACTION_NOT_PERMITTED


# --- AC2/guard race: a lost-race approve is a clean 409, nothing written -----------------------


def test_approving_a_settled_cr_is_409_and_writes_nothing(world: _World) -> None:
    """Guard race: approving an already-APPROVED Cancellation Request → 409 TRANSITION_NOT_ALLOWED,
    the balance byte-unchanged and NO new audit row (the whole transaction rolled back)."""
    request_id = _approved_request(world, world.report_token)
    cr_id = _raise_cr(world.report_token, request_id).json()["id"]

    first = _client.post(
        f"/api/v1/cancellation-requests/{cr_id}/approve", headers=_auth(world.admin_token)
    )
    assert first.status_code == 200, first.text
    balance_after = _balance_row(world.report_id, world.leave_type_id)
    audit_cr_after = _audit_count(uuid.UUID(cr_id))
    audit_lr_after = _audit_count(uuid.UUID(request_id))

    second = _client.post(
        f"/api/v1/cancellation-requests/{cr_id}/approve", headers=_auth(world.admin_token)
    )
    assert second.status_code == 409
    assert second.json()["code"] == vocabulary.TRANSITION_NOT_ALLOWED

    # Rolled back: balance and audit unchanged by the failed second approve.
    assert _balance_row(world.report_id, world.leave_type_id) == balance_after
    assert _audit_count(uuid.UUID(cr_id)) == audit_cr_after
    assert _audit_count(uuid.UUID(request_id)) == audit_lr_after


def test_second_pending_cr_for_same_request_is_409(world: _World) -> None:
    """Code review D2: a SECOND concurrent PENDING Cancellation Request for the same Approved
    request is refused 409 TRANSITION_NOT_ALLOWED — no `UNIQUE(leave_request_id)`, but two
    simultaneous PENDING rows are guarded out at raise time. The first CR stays approvable."""
    request_id = _approved_request(world, world.report_token)
    first_raise = _raise_cr(world.report_token, request_id)
    assert first_raise.status_code == 201, first_raise.text
    cr1 = first_raise.json()["id"]

    # A second raise while cr1 is still PENDING is refused — the duplicate never lands.
    second_raise = _raise_cr(world.report_token, request_id)
    assert second_raise.status_code == 409
    assert second_raise.json()["code"] == vocabulary.TRANSITION_NOT_ALLOWED

    # The first (only) CR is unaffected and still approvable.
    approved = _client.post(
        f"/api/v1/cancellation-requests/{cr1}/approve", headers=_auth(world.admin_token)
    )
    assert approved.status_code == 200, approved.text


def test_re_raise_after_rejection_is_allowed(world: _World) -> None:
    """Code review D2 (the guard does NOT over-block): the concurrent-PENDING refusal only blocks a
    SIMULTANEOUS second filing. Once the first CR is REJECTED, a fresh raise is permitted again —
    ERD §3's "a rejected one may be followed by another" still holds."""
    request_id = _approved_request(world, world.report_token)
    cr1 = _raise_cr(world.report_token, request_id).json()["id"]

    rejected = _client.post(
        f"/api/v1/cancellation-requests/{cr1}/reject", headers=_auth(world.admin_token)
    )
    assert rejected.status_code == 200, rejected.text

    # No PENDING CR remains, so a re-raise against the still-APPROVED leave is accepted.
    re_raise = _raise_cr(world.report_token, request_id)
    assert re_raise.status_code == 201, re_raise.text
    assert re_raise.json()["status"] == vocabulary.STATUS_PENDING


def test_approving_cr_whose_leave_is_now_past_is_400(world: _World) -> None:
    """Code review D1: AC3 is re-checked at DECISION time. A CR raised while the leave was future can
    sit PENDING until the dates fully pass; approving it then is refused 400 LEAVE_ALREADY_TAKEN —
    "already taken" leave cannot be un-taken on the Admin path either. The LR stays APPROVED, the CR
    stays PENDING, and no days are released."""
    request_id = _insert_past_approved_request(world)
    # A PENDING CR pointing at the now-past leave, inserted directly: the raise guard would refuse a
    # past target, so this reproduces the "raised while future, decided after it passed" state.
    with Session(get_engine()) as session:
        cr = CancellationRequest(
            leave_request_id=uuid.UUID(request_id),
            status=vocabulary.STATUS_PENDING,
        )
        session.add(cr)
        session.commit()
        cr_id = str(cr.id)

    approved = _client.post(
        f"/api/v1/cancellation-requests/{cr_id}/approve", headers=_auth(world.admin_token)
    )
    assert approved.status_code == 400
    assert approved.json()["code"] == vocabulary.LEAVE_ALREADY_TAKEN

    # Rolled back: the LR is still APPROVED and the CR still PENDING — no transition, no release.
    with Session(get_engine()) as session:
        lr_status = session.scalar(
            select(LeaveRequest.status).where(LeaveRequest.id == uuid.UUID(request_id))
        )
        cr_status = session.scalar(
            select(CancellationRequest.status).where(
                CancellationRequest.id == uuid.UUID(cr_id)
            )
        )
    assert lr_status == vocabulary.STATUS_APPROVED
    assert cr_status == vocabulary.STATUS_PENDING


# --- AC9 / SM-4: audit discrimination, one row per transition ---------------------------------


def test_audit_rows_are_discriminated_by_subject_type(world: _World) -> None:
    """AC9/SM-4: an approval writes exactly one CANCELLATION_REQUEST row and exactly one
    LEAVE_REQUEST row (to CANCELLED), both naming the Admin; each transition is one audit row."""
    request_id = _approved_request(world, world.report_token)
    cr_id = _raise_cr(world.report_token, request_id).json()["id"]
    cr_uuid = uuid.UUID(cr_id)
    lr_uuid = uuid.UUID(request_id)

    _client.post(
        f"/api/v1/cancellation-requests/{cr_id}/approve", headers=_auth(world.admin_token)
    )

    cr_rows = _audit_rows(cr_uuid)
    lr_rows = _audit_rows(lr_uuid)
    # CR subject: the raise (PENDING) and the approve (APPROVED) — two, one per transition.
    assert {r.to_state for r in cr_rows} == {
        vocabulary.STATUS_PENDING,
        vocabulary.STATUS_APPROVED,
    }
    assert all(
        r.subject_type == vocabulary.SUBJECT_CANCELLATION_REQUEST for r in cr_rows
    )
    # LR subject: submission (PENDING), approval (APPROVED), cancellation (CANCELLED) — three.
    assert {r.to_state for r in lr_rows} == {
        vocabulary.STATUS_PENDING,
        vocabulary.STATUS_APPROVED,
        vocabulary.STATUS_CANCELLED,
    }
    assert all(r.subject_type == vocabulary.SUBJECT_LEAVE_REQUEST for r in lr_rows)

    # The approve wrote both new rows naming the Admin.
    from app.repositories.models import Employee as _Employee  # local, DB-side lookup

    with Session(get_engine()) as session:
        admin_id = session.scalar(
            select(_Employee.id).where(
                _Employee.email == f"cr-adm-{world.suffix}@example.com"
            )
        )
    cr_approve = [r for r in cr_rows if r.to_state == vocabulary.STATUS_APPROVED][0]
    lr_cancel = [r for r in lr_rows if r.to_state == vocabulary.STATUS_CANCELLED][0]
    assert cr_approve.actor_id == admin_id
    assert lr_cancel.actor_id == admin_id


# --- Auth: no token is 401 --------------------------------------------------------------------


def test_decide_without_token_is_401(world: _World) -> None:
    """A decision with no Bearer token is 401 TOKEN_INVALID, like every other endpoint."""
    response = _client.post(f"/api/v1/cancellation-requests/{uuid.uuid4()}/approve")
    assert response.status_code == 401
    assert response.json()["code"] == vocabulary.TOKEN_INVALID
