"""The leave CSV export: scope, filters, the full-set read, and the format pins (Story 4.2).

Implements the test side of every AC:
- AC1 a Manager's export contains ONLY their Direct Reports — their own row is ABSENT (the
  endpoint's contract scope is `reports, all`, no `self`; Landmine 4) — and an Admin's export
  contains every Employee's rows, the Manager's own and the unrelated one's included;
- AC2 the exported rows are exactly the rows matching the applied filter set — Story 3.1's
  filters verbatim (OVERLAP window, inverted range → 200 empty, unknown type → 200 empty, bad
  status → 422), and the export carries ALL matching rows: the >100-rows anti-truncation test is
  THE test of this story (Landmine 1 — `MAX_PAGE_SIZE` clamps list endpoints at 100, and a naive
  reuse of that plumbing would truncate the export with every other test green);
- AC3 the Leave Day count in a CSV cell is the STORED value, pinned NON-VACUOUSLY by the house
  canary — a direct-inserted `leave_days=99` over a 3-day range exports as `99` (AD-18);
- AC4 the format is CSV: the exact header row, the `text/csv` Content-Type and the
  `Content-Disposition` are pinned (the 4.1 non-JSON-200 convention), and RFC 4180 quoting is
  proved by a `full_name` carrying a comma AND a quote surviving the round-trip.

Plus the read-purity pin (Landmine 8): an export is a READ — it writes no audit row and no
notification. Real PostgreSQL via `conftest`; seeding is DIRECT-INSERT (no API submissions), so
the fixture itself creates no audit/notification rows and teardown is four deletes.
"""

import csv
import datetime
import io
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.repositories.engine import get_engine
from app.repositories.models import (
    AuditEntry,
    Department,
    Employee,
    LeaveRequest,
    LeaveType,
    Notification,
)

import app.main  # noqa: F401 — wires CODE_TO_STATUS so the 403 renders, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_YEAR = datetime.date.today().year
_client = TestClient(app)

# The exported column set, pinned as LITERALS (the key-set pin, house rule): asserting against
# the constant in `services/reports.py` would pass vacuously after any accidental change to it.
_EXPECTED_HEADER = [
    "employee_full_name",
    "leave_type_code",
    "leave_type_name",
    "start_date",
    "end_date",
    "leave_days",
    "status",
]


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        type_a_id: uuid.UUID,
        type_b_id: uuid.UUID,
        manager_id: uuid.UUID,
        manager_token: str,
        rep1_id: uuid.UUID,
        rep2_id: uuid.UUID,
        rep1_token: str,
        outsider_id: uuid.UUID,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.type_a_id = type_a_id
        self.type_b_id = type_b_id
        self.manager_id = manager_id
        self.manager_token = manager_token
        self.rep1_id = rep1_id
        self.rep2_id = rep2_id
        self.rep1_token = rep1_token
        self.outsider_id = outsider_id
        self.admin_token = admin_token

    def name(self, label: str) -> str:
        return f"CSV {label} {self.suffix}"


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """A Manager, two reports, an UNRELATED managerless Employee, an Admin, two Leave Types.

    Everything is DIRECT-INSERTED — no API submission, no service call — so the fixture writes
    no audit row, no notification and no balance: the export under test is a pure read over
    `leave_request` joined to `employee`/`leave_type`, and none of that machinery participates.
    The unrelated Employee exists so the Manager-scope test can assert an ABSENCE that would
    otherwise be vacuous; both Leave Types exist so the filter-composition test has something to
    exclude.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"csv-dept-{suffix}"
    hashed = security.hash_password("correct-horse-battery-staple")

    def _employee(
        session: Session,
        department_id: uuid.UUID,
        *,
        label: str,
        role: str,
        manager_id: uuid.UUID | None,
        full_name: str | None = None,
    ) -> uuid.UUID:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"csv-{label}-{suffix}@example.com",
            full_name=full_name if full_name is not None else f"CSV {label} {suffix}",
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
        rep1_id = _employee(
            session,
            department.id,
            label="rep1",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        rep2_id = _employee(
            session,
            department.id,
            label="rep2",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        # No reporting line to the Manager — the absence the scope tests assert.
        outsider_id = _employee(
            session, department.id, label="out", role=vocabulary.ROLE_EMPLOYEE, manager_id=None
        )
        admin_id = _employee(
            session, department.id, label="adm", role=vocabulary.ROLE_ADMIN, manager_id=None
        )

        type_a = LeaveType(
            code=f"CSVA-{suffix}",
            name=f"CSV type A {suffix}",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        type_b = LeaveType(
            code=f"CSVB-{suffix}",
            name=f"CSV type B {suffix}",
            annual_entitlement=20,
            carries_forward=False,
            carry_forward_cap=None,
            requires_supporting_document=False,
        )
        session.add_all([type_a, type_b])
        session.flush()
        type_a_id, type_b_id = type_a.id, type_b.id
        session.commit()

    manager_token = security.create_token(str(manager_id), vocabulary.ROLE_MANAGER)
    rep1_token = security.create_token(str(rep1_id), vocabulary.ROLE_EMPLOYEE)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    try:
        yield _World(
            suffix,
            department_name,
            type_a_id,
            type_b_id,
            manager_id,
            manager_token,
            rep1_id,
            rep2_id,
            rep1_token,
            outsider_id,
            admin_token,
        )
    finally:
        # Direct-insert seeding wrote no audit/notification rows, so teardown is the four
        # parents. The OWNER engine, per house convention for maintenance (AD-9).
        with Session(owner_engine) as session:
            session.execute(
                delete(LeaveRequest).where(
                    LeaveRequest.leave_type_id.in_([type_a_id, type_b_id])
                )
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(
                delete(LeaveType).where(LeaveType.id.in_([type_a_id, type_b_id]))
            )
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _insert_request(
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
    *,
    leave_days: int,
    status: str,
) -> uuid.UUID:
    """Direct-insert one Leave Request — no service, no audit row, no balance movement."""
    with Session(get_engine()) as session:
        request = LeaveRequest(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            start_date=start,
            end_date=end,
            leave_days=leave_days,
            status=status,
        )
        session.add(request)
        session.commit()
        return request.id


def _export(token: str | None, query: str = "") -> "object":
    return _client.get(f"/api/v1/reports/leave.csv{query}", headers=_auth(token))


def _parse(response) -> tuple[list[str], list[dict[str, str]]]:  # type: ignore[no-untyped-def]
    """Parse the CSV body with stdlib `csv.reader`: (header row, data rows as dicts)."""
    rows = list(csv.reader(io.StringIO(response.text)))
    header, data = rows[0], rows[1:]
    return header, [dict(zip(header, row, strict=True)) for row in data]


# --- AC1: scope — the Manager's reports only, the Admin's everything ---------------------------


def test_manager_export_contains_exactly_their_direct_reports(world: _World) -> None:
    """AC1 + Landmine 4: the Manager's own request and the unrelated Employee's are ABSENT.

    The endpoint's contract scope is `reports, all` — no `self` for the Manager, unlike the
    paged list's `self, reports, all`. AD-10's REPORTS predicate (`employee.manager_id =
    :actor_id`) excludes the actor's own row; seeding the Manager's OWN request is what makes
    that absence a pinned fact rather than an accident of the seed.
    """
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_PENDING,
    )
    _insert_request(
        world.rep2_id, world.type_a_id,
        datetime.date(_YEAR, 8, 10), datetime.date(_YEAR, 8, 12),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )
    _insert_request(
        world.manager_id, world.type_a_id,
        datetime.date(_YEAR, 8, 17), datetime.date(_YEAR, 8, 19),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )
    _insert_request(
        world.outsider_id, world.type_a_id,
        datetime.date(_YEAR, 8, 24), datetime.date(_YEAR, 8, 26),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(world.manager_token)
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    names = sorted(row["employee_full_name"] for row in rows)
    assert names == sorted([world.name("rep1"), world.name("rep2")]), (
        "a Manager's export is their Direct Reports' rows, EXACTLY — the Manager's own request "
        f"and the unrelated Employee's must be absent. Got: {names}"
    )


def test_admin_export_contains_every_employees_rows(world: _World) -> None:
    """AC1: the same seed → the Admin's export carries ALL of it, Manager's own row included.

    Filtered to this world's Leave Type so the assertion is exact — the trail of other tests'
    committed data (the export is organization-wide by design) cannot blur it. The filter only
    NARROWS; scope is what puts the four employees' rows in reach, which is the claim under test.
    """
    for employee_id in (world.rep1_id, world.rep2_id, world.manager_id, world.outsider_id):
        _insert_request(
            employee_id, world.type_a_id,
            datetime.date(_YEAR, 9, 7), datetime.date(_YEAR, 9, 9),
            leave_days=3, status=vocabulary.STATUS_APPROVED,
        )

    response = _export(world.admin_token, f"?leave_type_id={world.type_a_id}")
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    names = sorted(row["employee_full_name"] for row in rows)
    assert names == sorted(
        [world.name("rep1"), world.name("rep2"), world.name("mgr"), world.name("out")]
    ), f"an Admin's export contains every Employee's rows. Got: {names}"


# --- The role gate ------------------------------------------------------------------------------


def test_an_employee_is_refused_403(world: _World) -> None:
    """The export is the Manager's and the Admin's alone — an Employee is 403, decided by role
    grant BEFORE any row is read (G3), and the refusal carries the JSON envelope (only the 200
    is CSV)."""
    response = _export(world.rep1_token)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED


def test_an_anonymous_caller_is_refused_401(world: _World) -> None:
    """No token at all is refused before the role gate is reached."""
    response = _export(None)
    assert response.status_code == 401, response.text


# --- AC2: the filter set, inherited from Story 3.1 verbatim -------------------------------------


def test_filters_compose_as_an_intersection(world: _World) -> None:
    """AC2 / FR-12: `status` + `leave_type_id` + the date window together select the
    intersection, exactly — one seeded row survives all three predicates, and each decoy is
    excluded by exactly one of them."""
    match_id = _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )
    # Wrong status.
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_PENDING,
    )
    # Wrong Leave Type.
    _insert_request(
        world.rep1_id, world.type_b_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )
    # Outside the date window.
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 10, 5), datetime.date(_YEAR, 10, 7),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(
        world.manager_token,
        f"?status={vocabulary.STATUS_APPROVED}&leave_type_id={world.type_a_id}"
        f"&date_from={_YEAR}-08-01&date_to={_YEAR}-08-31",
    )
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    assert len(rows) == 1, f"exactly the intersection, no more: {rows}"
    assert rows[0]["start_date"] == f"{_YEAR}-08-03"
    assert rows[0]["end_date"] == f"{_YEAR}-08-05"
    assert rows[0]["status"] == vocabulary.STATUS_APPROVED
    assert match_id is not None


def test_a_straddling_request_is_included_by_overlap(world: _World) -> None:
    """AC2 / Landmine 5: the date window selects by OVERLAP, not containment — a request
    straddling `date_from` (started before the window, ends inside it) IS leave taken in that
    window and appears. Containment semantics would silently drop it (Story 3.1 OD#1)."""
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 7, 28), datetime.date(_YEAR, 8, 1),
        leave_days=4, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(
        world.manager_token, f"?date_from={_YEAR}-08-01&date_to={_YEAR}-08-31"
    )
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    assert [row["start_date"] for row in rows] == [f"{_YEAR}-07-28"], (
        f"a straddler (end_date == date_from) must be included by OVERLAP semantics: {rows}"
    )


def test_an_inverted_range_is_200_with_the_header_row_only(world: _World) -> None:
    """AC2 / Landmine 5: `date_from > date_to` is a well-formed empty intersection — 200 with
    the header row alone, never a 422 and never an error body."""
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(
        world.manager_token, f"?date_from={_YEAR}-12-31&date_to={_YEAR}-01-01"
    )
    assert response.status_code == 200, response.text
    header, rows = _parse(response)
    assert header == _EXPECTED_HEADER
    assert rows == []


def test_a_nonexistent_leave_type_is_200_with_the_header_row_only(world: _World) -> None:
    """AC2 / Landmine 5: a valid-UUID `leave_type_id` matching nothing selects zero rows — 200,
    never 404 (AD-10 reserves 404 for scope misses, and a filter is not a scope)."""
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(world.manager_token, f"?leave_type_id={uuid.uuid4()}")
    assert response.status_code == 200, response.text
    header, rows = _parse(response)
    assert header == _EXPECTED_HEADER
    assert rows == []


def test_a_bad_status_value_is_a_framework_422(world: _World) -> None:
    """AC2 / Landmine 5: an unrecognized `status` is refused by the runtime enum as malformed
    input — the same class as a bad UUID — never a domain error code."""
    response = _export(world.manager_token, "?status=NOT_A_STATUS")
    assert response.status_code == 422, response.text


# --- AC2, Landmine 1: THE test of this story — no silent 100-row truncation ---------------------


def test_the_export_carries_all_matching_rows_beyond_the_page_clamp(world: _World) -> None:
    """AC2 / Landmine 1: seed MORE than `MAX_PAGE_SIZE` (100) matching rows; every one exports.

    The single most likely way to get this story wrong: routing the CSV through the list
    endpoints' `PageParams` plumbing truncates the export at 100 rows with every other test
    green. 105 one-day requests for one report, bulk-inserted; the CSV must carry all 105.
    """
    base = datetime.date(_YEAR, 1, 1)
    with Session(get_engine()) as session:
        session.add_all(
            LeaveRequest(
                employee_id=world.rep1_id,
                leave_type_id=world.type_a_id,
                start_date=base + datetime.timedelta(days=i),
                end_date=base + datetime.timedelta(days=i),
                leave_days=1,
                status=vocabulary.STATUS_APPROVED,
            )
            for i in range(105)
        )
        session.commit()

    response = _export(world.manager_token, f"?leave_type_id={world.type_a_id}")
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    assert len(rows) == 105, (
        f"the export must carry ALL matching rows, not a page: got {len(rows)} of 105. "
        "A 100-row result means the CSV was routed through the API page clamp (Landmine 1)."
    )


# --- AC3: the stored day count, pinned non-vacuously ---------------------------------------------


def test_leave_days_is_the_stored_value_never_recomputed(world: _World) -> None:
    """AC3 / AD-18, the house canary: a stored `leave_days` DELIBERATELY absurd against its
    3-day range (99) exports as `99`. A plausible stored value would pin nothing — the cell
    would match today's recomputation by coincidence and the test would pass vacuously."""
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=99, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(world.manager_token, f"?leave_type_id={world.type_a_id}")
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    assert [row["leave_days"] for row in rows] == ["99"], (
        "the CSV cell must be the STORED count (AD-18) — a value derived from the range "
        f"(3 days) means a read path recomputed it. Got: {rows}"
    )


# --- AC4: the format — header, headers, and quoting ----------------------------------------------


def test_the_header_row_and_response_headers_are_pinned(world: _World) -> None:
    """AC4 / OD#2 / OD#3: the exact column set, the `text/csv` Content-Type and the attachment
    Content-Disposition — the non-JSON-200 surface, pinned the 4.1 way (headers + parsed body,
    no envelope). A zero-row export is the header row alone."""
    response = _export(world.manager_token, f"?leave_type_id={world.type_a_id}")
    assert response.status_code == 200, response.text

    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="leave.csv"'

    header, rows = _parse(response)
    assert header == _EXPECTED_HEADER
    assert rows == []


def test_quoting_survives_a_comma_and_a_quote_in_a_name(world: _World) -> None:
    """AC4: RFC 4180 quoting, proved non-vacuously — a report whose `full_name` contains BOTH a
    comma and a double quote round-trips byte-identically through `csv.reader`."""
    tricky_name = f'Quote", Comma {world.suffix}'
    hashed = security.hash_password("correct-horse-battery-staple")
    with Session(get_engine()) as session:
        department_id = session.scalar(
            select(Department.id).where(Department.name == world.department_name)
        )
        tricky = Employee(
            department_id=department_id,
            manager_id=world.manager_id,
            email=f"csv-tricky-{world.suffix}@example.com",
            full_name=tricky_name,
            role=vocabulary.ROLE_EMPLOYEE,
            joining_date=datetime.date(_YEAR, 1, 1),
            is_active=True,
            password_hash=hashed,
        )
        session.add(tricky)
        session.commit()
        tricky_id = tricky.id

    _insert_request(
        tricky_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(world.manager_token, f"?leave_type_id={world.type_a_id}")
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    assert [row["employee_full_name"] for row in rows] == [tricky_name], (
        f"a comma-and-quote name must survive the CSV round-trip intact: {rows}"
    )


def test_a_formula_shaped_name_is_neutralized_in_the_cell(world: _World) -> None:
    """CSV injection (2026-07-15 code review): a `full_name` leading with `=` is SELF-EDITABLE
    (`PATCH /me`), and RFC 4180 quoting does not stop Excel/Sheets from EXECUTING a cell that
    begins with `=`/`+`/`-`/`@`. The export must ship such a cell prefixed with a single quote
    (OWASP's literal-text marker) so opening the file runs nothing in the Manager's session."""
    formula_name = f'=HYPERLINK("http://evil/{world.suffix}","x")'
    hashed = security.hash_password("correct-horse-battery-staple")
    with Session(get_engine()) as session:
        department_id = session.scalar(
            select(Department.id).where(Department.name == world.department_name)
        )
        hostile = Employee(
            department_id=department_id,
            manager_id=world.manager_id,
            email=f"csv-formula-{world.suffix}@example.com",
            full_name=formula_name,
            role=vocabulary.ROLE_EMPLOYEE,
            joining_date=datetime.date(_YEAR, 1, 1),
            is_active=True,
            password_hash=hashed,
        )
        session.add(hostile)
        session.commit()
        hostile_id = hostile.id

    _insert_request(
        hostile_id, world.type_a_id,
        datetime.date(_YEAR, 9, 7), datetime.date(_YEAR, 9, 9),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    response = _export(world.manager_token, f"?date_from={_YEAR}-09-07&date_to={_YEAR}-09-09")
    assert response.status_code == 200, response.text
    _header, rows = _parse(response)

    assert [row["employee_full_name"] for row in rows] == ["'" + formula_name], (
        f"a formula-leading cell must arrive quote-prefixed, never executable: {rows}"
    )


# --- Landmine 8: an export is a read ------------------------------------------------------------


def test_an_export_writes_no_audit_row_and_no_notification(world: _World) -> None:
    """Landmine 8 / AD-8: an export is a READ, not a transition — the audit trail (SM-4's
    one-to-one ledger) and the notification table are byte-for-byte unchanged by it."""
    _insert_request(
        world.rep1_id, world.type_a_id,
        datetime.date(_YEAR, 8, 3), datetime.date(_YEAR, 8, 5),
        leave_days=3, status=vocabulary.STATUS_APPROVED,
    )

    with Session(get_engine()) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEntry))
        notifications_before = session.scalar(select(func.count()).select_from(Notification))

    assert _export(world.manager_token).status_code == 200
    assert _export(world.admin_token).status_code == 200

    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuditEntry)) == audit_before
        assert (
            session.scalar(select(func.count()).select_from(Notification))
            == notifications_before
        )
