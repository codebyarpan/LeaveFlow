"""The leave history — cross-year, every state, three composable filters (Story 3.1).

Implements the test side of:
- AC1 (FR-20) an Employee's UNFILTERED list is their whole history: every Leave Year, every
  state including CANCELLED and REJECTED, each entry carrying the Leave Type, the date range,
  the frozen Leave Day count and the current state. A DOCUMENTING test — there is no year
  filter to remove (no `leave_year` column exists); this pins that none ever creeps in.
- AC3 (FR-12) `status`, `leave_type_id`, `date_from` and `date_to` COMPOSE: the result is the
  intersection, and `total` obeys the same filters as `items` even when `page_size` truncates
  the page (the count query has no LeaveType join — Landmine 3).
- Open Decision #1: the date window selects by OVERLAP (`end_date >= date_from AND
  start_date <= date_to`), so a request straddling a boundary — exactly the Leave Year edge a
  cross-year history must not drop — is included. Story 4.2's CSV export inherits these
  semantics; they are pinned here.
- AC4 (FR-12/FR-03/AD-10) filters only ever NARROW the scope predicate they sit beside: an
  Employee stays confined to their own rows, a Manager to their Direct Reports' (still never
  their own — the keep-REPORTS ruling), an Admin sees all.
- Open Decisions #2/#3: an inverted window and a nonexistent (valid-UUID) `leave_type_id` are
  well-formed predicates matching nothing → 200 with an empty page, never a 422 or a 404
  (AD-10 reserves 404 for scope misses). Malformed values are framework 422s, exactly like a
  bad `status` (the pinned 2.7 precedent) — no domain error code exists for a filter.

Rows are seeded by DIRECT repository-level inserts (the rollover tests' precedent): submission
refuses past dates, and a HISTORY is precisely rows whose dates have passed — the API cannot
seed its own test data here. Direct inserts also write no audit rows and touch no balance, so
the fixture cleans up only what it created. Real PostgreSQL through the real router.

AC2 (envelope + clamp), AC5 (byte-identical 404) and AC6 (stored `leave_days`) are already
pinned by `test_pagination.py` and `test_leave_request_decide.py` — run, not duplicated, here.
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, delete, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import (
    Department,
    Employee,
    LeaveRequest,
    LeaveType,
    Notification,
)

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 403/404 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
# The current Leave Year and the one before it: a history spans years that have PASSED, which
# is exactly why these rows are seeded at repository level rather than through submission.
_YEAR = datetime.date.today().year
_PRIOR = _YEAR - 1
_client = TestClient(app)


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        type_a_id: uuid.UUID,
        type_b_id: uuid.UUID,
        rep_id: uuid.UUID,
        rep_token: str,
        coworker_id: uuid.UUID,
        coworker_token: str,
        b_report_id: uuid.UUID,
        manager_a_id: uuid.UUID,
        manager_a_token: str,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.type_a_id = type_a_id
        self.type_b_id = type_b_id
        self.rep_id = rep_id
        self.rep_token = rep_token
        self.coworker_id = coworker_id
        self.coworker_token = coworker_token
        self.b_report_id = b_report_id
        self.manager_a_id = manager_a_id
        self.manager_a_token = manager_a_token
        self.admin_token = admin_token


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """Two Managers, two of A's reports, one of B's, an Admin, and TWO Leave Types.

    Two types because the `leave_type_id` filter needs a row it matches and a row it excludes.
    Types are inserted DIRECTLY (not through the service), so no balance rows materialize —
    the read path under test never touches a balance, and the fixture stays minimal.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"hist-dept-{suffix}"
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
            email=f"hist-{label}-{suffix}@example.com",
            full_name=f"Hist {label}",
            role=role,
            joining_date=datetime.date(_PRIOR, 1, 1),
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
        rep_id = _employee(
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

        type_a = LeaveType(
            code=f"HIA-{suffix}",
            name="History type A",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        type_b = LeaveType(
            code=f"HIB-{suffix}",
            name="History type B",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        session.add_all([type_a, type_b])
        session.flush()
        type_a_id, type_b_id = type_a.id, type_b.id
        session.commit()

    rep_token = security.create_token(str(rep_id), vocabulary.ROLE_EMPLOYEE)
    coworker_token = security.create_token(str(coworker_id), vocabulary.ROLE_EMPLOYEE)
    manager_a_token = security.create_token(str(manager_a_id), vocabulary.ROLE_MANAGER)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    try:
        yield _World(
            suffix,
            department_name,
            type_a_id,
            type_b_id,
            rep_id,
            rep_token,
            coworker_id,
            coworker_token,
            b_report_id,
            manager_a_id,
            manager_a_token,
            admin_token,
        )
    finally:
        # Direct inserts wrote no audit rows and no balances — only requests, employees, the
        # two types and the department need removal. The owner engine, the cleanup convention.
        with Session(owner_engine) as session:
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
                delete(LeaveRequest).where(
                    LeaveRequest.leave_type_id.in_([type_a_id, type_b_id])
                )
            )
            session.execute(
                update(Employee)
                .where(Employee.email.like(f"%{suffix}%"))
                .values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(
                delete(LeaveType).where(LeaveType.id.in_([type_a_id, type_b_id]))
            )
            session.execute(
                delete(Department).where(Department.name == department_name)
            )
            session.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _insert_request(
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
    *,
    status: str,
    leave_days: int = 3,
) -> str:
    """Seed one request row at repository level (the rollover tests' precedent).

    Submission refuses past dates (`PAST_DATE_RANGE`), and a history is made of past dates —
    so the API cannot seed this data. `leave_days` is any positive frozen figure; the read
    path returns it verbatim (AD-18), it is never re-derived from the range.
    """
    with Session(get_engine()) as session:
        row = LeaveRequest(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            start_date=start,
            end_date=end,
            leave_days=leave_days,
            status=status,
        )
        session.add(row)
        session.commit()
        return str(row.id)


def _list(token: str, **params: object) -> dict:
    response = _client.get(
        "/api/v1/leave-requests", params=params, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- AC1: the unfiltered list is the whole cross-year, every-state history -------------------


def test_unfiltered_history_is_cross_year_and_every_state(world: _World) -> None:
    """AC1 (FR-20), a DOCUMENTING test: no year predicate exists, and none may creep in.

    Four rows for one Employee — this year and LAST year, including a CANCELLED and a
    REJECTED — all present in one unfiltered list, each entry carrying the Leave Type
    labels, the range, the stored day count and the state.
    """
    seeded = {
        _insert_request(
            world.rep_id, world.type_a_id,
            datetime.date(_PRIOR, 3, 2), datetime.date(_PRIOR, 3, 4),
            status=vocabulary.STATUS_APPROVED,
        ),
        _insert_request(
            world.rep_id, world.type_a_id,
            datetime.date(_PRIOR, 9, 7), datetime.date(_PRIOR, 9, 9),
            status=vocabulary.STATUS_REJECTED,
        ),
        _insert_request(
            world.rep_id, world.type_b_id,
            datetime.date(_YEAR, 2, 2), datetime.date(_YEAR, 2, 4),
            status=vocabulary.STATUS_CANCELLED,
        ),
        _insert_request(
            world.rep_id, world.type_a_id,
            datetime.date(_YEAR, 5, 4), datetime.date(_YEAR, 5, 6),
            status=vocabulary.STATUS_PENDING,
        ),
    }

    body = _list(world.rep_token)
    assert {item["id"] for item in body["items"]} == seeded
    assert body["total"] == 4

    # Both Leave Years and all four states are present — the cross-year, every-state claim.
    years = {int(item["start_date"][:4]) for item in body["items"]}
    assert years == {_PRIOR, _YEAR}
    states = {item["status"] for item in body["items"]}
    assert states == {
        vocabulary.STATUS_APPROVED,
        vocabulary.STATUS_REJECTED,
        vocabulary.STATUS_CANCELLED,
        vocabulary.STATUS_PENDING,
    }

    # Every entry carries the AC1 display fields, values verbatim from the row.
    for item in body["items"]:
        assert item["leave_type_code"] in {f"HIA-{world.suffix}", f"HIB-{world.suffix}"}
        assert item["leave_type_name"] in {"History type A", "History type B"}
        assert item["start_date"] and item["end_date"]
        assert item["leave_days"] == 3
        assert item["status"] in states


# --- AC3: the four filters compose, and `total` obeys them under truncation ------------------


def test_filters_compose_as_an_intersection(world: _World) -> None:
    """AC3 (FR-12): all four filters ANDed = the intersection, and `total` counts the WHOLE
    intersection even when `page_size` truncates `items` (Landmine 3 — the count query joins
    only Employee, so a joined-column filter would silently desynchronize it)."""
    window_from, window_to = datetime.date(_YEAR, 3, 1), datetime.date(_YEAR, 3, 31)

    matching = {
        _insert_request(
            world.rep_id, world.type_a_id,
            datetime.date(_YEAR, 3, 2), datetime.date(_YEAR, 3, 4),
            status=vocabulary.STATUS_APPROVED,
        ),
        _insert_request(
            world.rep_id, world.type_a_id,
            datetime.date(_YEAR, 3, 9), datetime.date(_YEAR, 3, 11),
            status=vocabulary.STATUS_APPROVED,
        ),
        _insert_request(
            world.rep_id, world.type_a_id,
            datetime.date(_YEAR, 3, 16), datetime.date(_YEAR, 3, 18),
            status=vocabulary.STATUS_APPROVED,
        ),
    }
    # Three decoys, each off by exactly ONE dimension — the intersection must drop each.
    _insert_request(  # status differs
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 3, 23), datetime.date(_YEAR, 3, 25),
        status=vocabulary.STATUS_REJECTED,
    )
    _insert_request(  # leave type differs
        world.rep_id, world.type_b_id,
        datetime.date(_YEAR, 3, 23), datetime.date(_YEAR, 3, 25),
        status=vocabulary.STATUS_APPROVED,
    )
    _insert_request(  # dates outside the window
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 5, 4), datetime.date(_YEAR, 5, 6),
        status=vocabulary.STATUS_APPROVED,
    )

    filters = {
        "status": vocabulary.STATUS_APPROVED,
        "leave_type_id": str(world.type_a_id),
        "date_from": window_from.isoformat(),
        "date_to": window_to.isoformat(),
    }

    body = _list(world.rep_token, **filters)
    assert {item["id"] for item in body["items"]} == matching
    assert body["total"] == 3

    # Truncated page: `items` shrinks to the page, `total` still counts the intersection.
    truncated = _list(world.rep_token, **filters, page_size=2)
    assert len(truncated["items"]) == 2
    assert truncated["total"] == 3
    assert {item["id"] for item in truncated["items"]} < matching


# --- Open Decision #1: overlap semantics, pinned ----------------------------------------------


def test_date_range_filter_uses_overlap_semantics(world: _World) -> None:
    """Open Decision #1 (pinned for Story 4.2's CSV export to inherit): the window selects
    requests whose range INTERSECTS it — `end_date >= date_from AND start_date <= date_to` —
    so a straddler at either boundary is included and containment's silent year-edge drop
    cannot happen. Each side works alone."""
    window_from, window_to = datetime.date(_YEAR, 6, 10), datetime.date(_YEAR, 6, 20)

    straddles_from = _insert_request(
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 6, 5), datetime.date(_YEAR, 6, 12),
        status=vocabulary.STATUS_APPROVED,
    )
    ends_before_from = _insert_request(
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 6, 1), datetime.date(_YEAR, 6, 9),
        status=vocabulary.STATUS_APPROVED,
    )
    straddles_to = _insert_request(
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 6, 18), datetime.date(_YEAR, 6, 25),
        status=vocabulary.STATUS_APPROVED,
    )
    starts_after_to = _insert_request(
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 6, 21), datetime.date(_YEAR, 6, 30),
        status=vocabulary.STATUS_APPROVED,
    )

    # Both sides: the two straddlers are in, the two outside rows are out.
    both = _list(
        world.rep_token,
        date_from=window_from.isoformat(),
        date_to=window_to.isoformat(),
    )
    assert {item["id"] for item in both["items"]} == {straddles_from, straddles_to}

    # `date_from` alone: everything still running on or after it — including the straddler.
    from_only = _list(world.rep_token, date_from=window_from.isoformat())
    assert {item["id"] for item in from_only["items"]} == {
        straddles_from,
        straddles_to,
        starts_after_to,
    }

    # `date_to` alone: everything starting on or before it — including the straddler.
    to_only = _list(world.rep_token, date_to=window_to.isoformat())
    assert {item["id"] for item in to_only["items"]} == {
        straddles_from,
        ends_before_from,
        straddles_to,
    }


# --- AC4: filters never widen the scope they sit beside ---------------------------------------


def test_filters_never_widen_scope(world: _World) -> None:
    """AC4 (FR-12/FR-03/AD-10): the broadest possible filters still return only what the
    caller's scope grants — an Employee their own, a Manager their Direct Reports' (and still
    never their own row, the keep-REPORTS ruling), an Admin everyone's."""
    window = (datetime.date(_YEAR, 7, 6), datetime.date(_YEAR, 7, 8))
    rep_row = _insert_request(
        world.rep_id, world.type_a_id, *window, status=vocabulary.STATUS_APPROVED
    )
    cow_row = _insert_request(
        world.coworker_id, world.type_a_id, *window, status=vocabulary.STATUS_APPROVED
    )
    brep_row = _insert_request(
        world.b_report_id, world.type_a_id, *window, status=vocabulary.STATUS_APPROVED
    )
    mgr_own_row = _insert_request(
        world.manager_a_id, world.type_a_id, *window, status=vocabulary.STATUS_APPROVED
    )

    # Filters broad enough to match every row above — precisely the coworker's type/dates.
    broad = {
        "leave_type_id": str(world.type_a_id),
        "date_from": datetime.date(_PRIOR, 1, 1).isoformat(),
        "date_to": datetime.date(_YEAR, 12, 31).isoformat(),
        "status": vocabulary.STATUS_APPROVED,
    }

    # The Employee names a filter matching their coworker's rows — and still sees only their own.
    rep_view = _list(world.rep_token, **broad)
    assert {item["id"] for item in rep_view["items"]} == {rep_row}
    assert rep_view["total"] == 1

    # The Manager filtering broadly: Direct Reports only — no other team, and NOT their own row.
    mgr_view = _list(world.manager_a_token, **broad)
    mgr_ids = {item["id"] for item in mgr_view["items"]}
    assert mgr_ids == {rep_row, cow_row}
    assert brep_row not in mgr_ids
    assert mgr_own_row not in mgr_ids  # :602's invariant, held under the new filters

    # The Admin: all four.
    admin_view = _list(world.admin_token, **broad)
    assert {rep_row, cow_row, brep_row, mgr_own_row} <= {
        item["id"] for item in admin_view["items"]
    }


# --- Open Decisions #2/#3: well-formed empties are 200; malformed input is 422 ----------------


def test_inverted_range_and_unknown_type_are_empty_pages(world: _World) -> None:
    """Open Decisions #2/#3, pinned: `date_from > date_to` is a well-formed predicate whose
    intersection is EMPTY (200, `total == 0`, no error code) — and a nonexistent valid-UUID
    `leave_type_id` matches nothing (200 empty, never a 404: AD-10 reserves 404 for scope
    misses on identified resources; a filter identifies nothing)."""
    _insert_request(
        world.rep_id, world.type_a_id,
        datetime.date(_YEAR, 4, 6), datetime.date(_YEAR, 4, 8),
        status=vocabulary.STATUS_APPROVED,
    )

    inverted = _list(
        world.rep_token,
        date_from=datetime.date(_YEAR, 4, 30).isoformat(),
        date_to=datetime.date(_YEAR, 4, 1).isoformat(),
    )
    assert inverted["items"] == []
    assert inverted["total"] == 0

    unknown_type = _list(world.rep_token, leave_type_id=str(uuid.uuid4()))
    assert unknown_type["items"] == []
    assert unknown_type["total"] == 0


def test_malformed_filter_values_are_framework_422(world: _World) -> None:
    """Landmine 2 / the pinned 2.7 precedent: a non-UUID `leave_type_id` and an unparseable
    date are FRAMEWORK 422s (bare FastAPI `{"detail": ...}`), never a domain envelope — no
    filter error code exists in the vocabulary, and none is wanted."""
    bad_uuid = _client.get(
        "/api/v1/leave-requests",
        params={"leave_type_id": "not-a-uuid"},
        headers=_auth(world.rep_token),
    )
    assert bad_uuid.status_code == 422
    assert "detail" in bad_uuid.json()  # the framework shape, not the domain envelope

    bad_date = _client.get(
        "/api/v1/leave-requests",
        params={"date_from": "not-a-date"},
        headers=_auth(world.rep_token),
    )
    assert bad_date.status_code == 422
    assert "detail" in bad_date.json()
