"""The supporting document, end to end against real PostgreSQL (Story 4.1, all backend ACs).

Implements the test side of: AC1 (the schema — the exact columns, the NAMED UNIQUE, and the
pinned ABSENCE of `size_bytes`; plus the `SELECT, INSERT, UPDATE`-and-never-`DELETE` grant),
AC2 (wrong type / oversize → 400 with its code, and the volume directory gained NO entry —
validation runs before any byte is written), AC3 (an accepted upload lands at
`{documents_dir}/{storage_name}` under a server-generated UUID; the client's filename —
including a `../` traversal shape — is persisted VERBATIM as data and never touches a path),
AC4 (the submission gate: a document-requiring Leave Type refuses a documentless JSON submit;
a multipart submit WITH a document creates the request, the row and the file in ONE
transaction with the balance moved exactly once; an invalid file rolls the WHOLE submission
back), AC5 (the GET streams to the applicant, their Manager and an Admin; every other miss —
an unrelated Employee, an unrelated Manager, a documentless request, a nonexistent id — is
the ONE byte-identical 404; the stored `content_type` and the RFC 5987 `Content-Disposition`
ride the response), and OD#2 (attach-or-replace while PENDING; a decided request's evidence
is frozen → 409).

Real PostgreSQL: the one-transaction submit, the UNIQUE backstop, the grant and the scope
predicates all run through the live database and the real router. The basename is globally
unique (the 3.3 lesson).

--- Teardown (Landmine 8) ---

`supporting_document` FK-references `leave_request` with NO `ON DELETE`, so document rows die
FIRST — and their FILES are unlinked before that, because files outlive rows. Then the
standard 3.4 order: audit rows, notifications, requests, balances, employees, types,
department — through the OWNER engine (the app role holds no DELETE on the log tables, which
is the guarantee working, not a bug).
"""

import datetime
import uuid
import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.settings import get_settings
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
    SupportingDocument,
)
from app.services import leave_types as leave_types_service

import app.main  # noqa: F401 — wires CODE_TO_STATUS so 400/409 render, not a 500 default

warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_KNOWN_PASSWORD = "correct-horse-battery-staple"
_YEAR = datetime.date.today().year
_ENTITLEMENT = 10
_client = TestClient(app)

# Future weekdays (today is 2026-07-15), so no range trips PAST_DATE_RANGE by accident.
_TUE = datetime.date(2026, 8, 18)  # Tuesday   (weekday()==1) — Working Day
_THU = datetime.date(2026, 8, 20)  # Thursday  (weekday()==3) — Working Day; Tue–Thu = 3 days
_MON2 = datetime.date(2026, 8, 24)  # Monday   (weekday()==0) — a second, disjoint range
_TUE2 = datetime.date(2026, 8, 25)  # Tuesday  (weekday()==1) — Mon–Tue = 2 days

# A tiny valid payload is enough (OD#3: validation is declared-type + size, never content
# sniffing); the oversize body is exactly one byte over the cap.
_PDF_BYTES = b"%PDF-1.4 fake"
_OVERSIZE_BYTES = b"x" * (5_242_880 + 1)


class _World:
    def __init__(
        self,
        suffix: str,
        department_name: str,
        applicant_id: uuid.UUID,
        applicant_token: str,
        manager_token: str,
        outsider_token: str,
        other_manager_token: str,
        admin_token: str,
        doc_type_id: uuid.UUID,
        free_type_id: uuid.UUID,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.applicant_id = applicant_id
        self.applicant_token = applicant_token
        self.manager_token = manager_token
        self.outsider_token = outsider_token
        self.other_manager_token = other_manager_token
        self.admin_token = admin_token
        self.doc_type_id = doc_type_id
        self.free_type_id = free_type_id


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """A manager, their report (the applicant), an unrelated manager + THEIR report (the
    outsider), and an Admin; TWO Leave Types — one requiring a document, one not.

    All full-year joiners, so both types (created THROUGH the service — the 2.4 hook)
    materialize everyone a balance of the full entitlement.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"sd-dept-{suffix}"
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
            email=f"sd-{label}-{suffix}@example.com",
            full_name=f"SD {label}",
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
        applicant_id = _employee(
            session,
            department.id,
            label="emp",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        other_manager_id = _employee(
            session, department.id, label="omgr", role=vocabulary.ROLE_MANAGER, manager_id=None
        )
        outsider_id = _employee(
            session,
            department.id,
            label="out",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=other_manager_id,
        )
        admin_id = _employee(
            session, department.id, label="adm", role=vocabulary.ROLE_ADMIN, manager_id=None
        )
        session.commit()

    applicant_token = security.create_token(str(applicant_id), vocabulary.ROLE_EMPLOYEE)
    manager_token = security.create_token(str(manager_id), vocabulary.ROLE_MANAGER)
    outsider_token = security.create_token(str(outsider_id), vocabulary.ROLE_EMPLOYEE)
    other_manager_token = security.create_token(
        str(other_manager_id), vocabulary.ROLE_MANAGER
    )
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    doc_type_id = leave_types_service.create_leave_type(
        code=f"SD-{suffix}",
        name="Doc-requiring leave",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=True,
    ).id
    free_type_id = leave_types_service.create_leave_type(
        code=f"SF-{suffix}",
        name="Free leave",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=False,
    ).id

    try:
        yield _World(
            suffix,
            department_name,
            applicant_id,
            applicant_token,
            manager_token,
            outsider_token,
            other_manager_token,
            admin_token,
            doc_type_id,
            free_type_id,
        )
    finally:
        type_ids = [doc_type_id, free_type_id]
        request_ids = select(LeaveRequest.id).where(
            LeaveRequest.leave_type_id.in_(type_ids)
        )
        with Session(owner_engine) as session:
            # Landmine 8 — the NEW first step: files outlive rows, so unlink each document's
            # bytes by its `storage_name`, THEN delete the document rows, and only then the
            # `leave_request` parents they FK-reference (no ON DELETE, by decision).
            documents_dir = get_settings().documents_dir
            for storage_name in session.scalars(
                select(SupportingDocument.storage_name).where(
                    SupportingDocument.leave_request_id.in_(request_ids)
                )
            ):
                (documents_dir / str(storage_name)).unlink(missing_ok=True)
            session.execute(
                delete(SupportingDocument).where(
                    SupportingDocument.leave_request_id.in_(request_ids)
                )
            )
            # The standard 3.4 order from here: audit rows and notifications before the
            # requests they reference, children before parents, owner engine throughout.
            session.execute(
                delete(AuditEntry).where(AuditEntry.subject_id.in_(request_ids))
            )
            session.execute(
                delete(Notification).where(
                    Notification.recipient_employee_id.in_(
                        select(Employee.id).where(Employee.email.like(f"%{suffix}%"))
                    )
                )
            )
            session.execute(
                delete(LeaveRequest).where(LeaveRequest.leave_type_id.in_(type_ids))
            )
            session.execute(
                delete(LeaveBalance).where(LeaveBalance.leave_type_id.in_(type_ids))
            )
            session.execute(
                update(Employee)
                .where(Employee.email.like(f"%{suffix}%"))
                .values(manager_id=None)
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id.in_(type_ids)))
            session.execute(
                delete(Department).where(Department.name == department_name)
            )
            session.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _submit_json(
    token: str, leave_type_id: uuid.UUID, start: datetime.date, end: datetime.date
):
    return _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=_auth(token),
    )


def _submit_multipart(
    token: str,
    leave_type_id: uuid.UUID,
    start: datetime.date,
    end: datetime.date,
    *,
    document: tuple[str, bytes, str] | None,
):
    files = {"document": document} if document is not None else None
    return _client.post(
        "/api/v1/leave-requests",
        data={
            "leave_type_id": str(leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        files=files,
        headers=_auth(token),
    )


def _attach(token: str, request_id: str, document: tuple[str, bytes, str]):
    return _client.post(
        f"/api/v1/leave-requests/{request_id}/document",
        files={"document": document},
        headers=_auth(token),
    )


def _get_document(token: str, request_id: str):
    return _client.get(
        f"/api/v1/leave-requests/{request_id}/document", headers=_auth(token)
    )


def _pending_request(world: _World) -> str:
    """A PENDING request on the free type (JSON, documentless — legal), for the attach flow."""
    response = _submit_json(world.applicant_token, world.free_type_id, _TUE, _THU)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _document_row(request_id: str):
    with Session(get_engine()) as session:
        return session.execute(
            select(SupportingDocument).where(
                SupportingDocument.leave_request_id == uuid.UUID(request_id)
            )
        ).scalar_one_or_none()


def _volume_entries() -> set[str]:
    directory = get_settings().documents_dir
    if not directory.exists():
        return set()
    return {entry.name for entry in directory.iterdir()}


def _request_count(session: Session, leave_type_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .where(LeaveRequest.leave_type_id == leave_type_id)
        )
        or 0
    )


def _balance(world: _World, leave_type_id: uuid.UUID) -> tuple[int, int, int]:
    with Session(get_engine()) as session:
        row = session.execute(
            select(
                LeaveBalance.accrued, LeaveBalance.reserved, LeaveBalance.consumed
            ).where(
                LeaveBalance.employee_id == world.applicant_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == _YEAR,
            )
        ).one()
        return row.accrued, row.reserved, row.consumed


# --- AC1: the schema ---------------------------------------------------------------------


def test_schema_exact_columns_named_unique_and_no_size_bytes(
    db_connection: Connection,
) -> None:
    """AC1: the exact column set — WITH the ABSENCE of `size_bytes` pinned — and the named UNIQUE.

    Exact-set equality (the `test_schema_1_2` pattern): a subset check could not pin an
    absence, and the absence is the AC's own clause — size is validated before the bytes are
    written and no requirement reads it afterwards (ERD §2.1). The UNIQUE's NAME is asserted
    because the model mirrors the migration byte-for-byte (`alembic check`).
    """
    columns = {
        row.column_name: row.is_nullable
        for row in db_connection.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'supporting_document'"
            )
        )
    }
    assert columns == {
        "id": "NO",
        "leave_request_id": "NO",
        "storage_name": "NO",
        "original_filename": "NO",
        "content_type": "NO",
    }

    unique_names = {
        row.conname
        for row in db_connection.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'supporting_document'::regclass AND contype = 'u'"
            )
        )
    }
    assert unique_names == {"supporting_document_leave_request_id_key"}


def test_app_role_grant_is_select_insert_update_never_delete(
    db_connection: Connection,
) -> None:
    """AC1/OD#2: the grant matches the mutability — the replace path UPDATEs; nothing DELETEs.

    The `0012` shape, not the append-only one: `UPDATE` is what makes attach-or-replace work
    at runtime, and the withheld `DELETE` is what makes "no requirement deletes a document"
    a database fact rather than a habit (the 2.9 principle, verified LIVE as the app role).
    """
    app_user = get_settings().app_db_user
    grants = {
        privilege: db_connection.execute(
            text(
                "SELECT has_table_privilege(:role, 'supporting_document', :privilege)"
            ),
            {"role": app_user, "privilege": privilege},
        ).scalar()
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
    }
    assert grants == {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False}


# --- AC2: refusals, before any byte reaches the volume ------------------------------------


def test_wrong_type_is_refused_and_writes_nothing(world: _World) -> None:
    """AC2: a declared type outside PDF/JPG/PNG → 400 UNSUPPORTED_FILE_TYPE, volume untouched.

    `details` names the offender and the accepted list (NFR-17). The volume directory gained
    no entry and no row exists — validation ran BEFORE any write (AD-15).
    """
    request_id = _pending_request(world)
    before = _volume_entries()

    response = _attach(
        world.applicant_token, request_id, ("notes.txt", b"plain text", "text/plain")
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.UNSUPPORTED_FILE_TYPE
    assert body["details"]["content_type"] == "text/plain"
    assert body["details"]["accepted"] == list(vocabulary.DOCUMENT_CONTENT_TYPES)
    assert _volume_entries() == before
    assert _document_row(request_id) is None


def test_oversized_file_is_refused_and_writes_nothing(world: _World) -> None:
    """AC2: a valid-typed payload one byte over 5 MB → 400 FILE_TOO_LARGE, volume untouched.

    The size is decided from the bytes actually read under the hard cap — never from a
    client-supplied `Content-Length` — and `details` names the limit (NFR-17).
    """
    request_id = _pending_request(world)
    before = _volume_entries()

    response = _attach(
        world.applicant_token,
        request_id,
        ("scan.pdf", _OVERSIZE_BYTES, "application/pdf"),
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.FILE_TOO_LARGE
    assert body["details"]["max_bytes"] == vocabulary.DOCUMENT_MAX_BYTES
    assert _volume_entries() == before
    assert _document_row(request_id) is None


# --- AC3: the accepted upload ---------------------------------------------------------------


def test_accepted_upload_lands_under_a_server_uuid_and_filename_is_data(
    world: _World,
) -> None:
    """AC3: the file lands at `{documents_dir}/{storage_name}`; the client's filename is DATA.

    `storage_name` is a UUID that shares nothing with the client's filename — even a
    traversal-shaped `../../etc/passwd.pdf` is persisted VERBATIM as a column and never
    becomes a path component (NFR-05, AD-15). The 201's key set is pinned exactly.
    """
    request_id = _pending_request(world)
    traversal_name = "../../etc/passwd.pdf"

    response = _attach(
        world.applicant_token, request_id, (traversal_name, _PDF_BYTES, "application/pdf")
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body.keys()) == {"id", "original_filename", "content_type"}
    assert body["original_filename"] == traversal_name
    assert body["content_type"] == "application/pdf"

    row = _document_row(request_id)
    assert row is not None
    assert row.original_filename == traversal_name  # verbatim, traversal and all
    assert isinstance(row.storage_name, uuid.UUID)
    assert str(row.storage_name) not in traversal_name  # nothing client-derived in the name

    stored_path = get_settings().documents_dir / str(row.storage_name)
    assert stored_path.read_bytes() == _PDF_BYTES
    # The traversal name never became a path: nothing was written outside the volume dir.
    assert stored_path.parent == get_settings().documents_dir


# --- AC4: the submission gate + the one-transaction multipart submit -----------------------


def test_documentless_submit_for_requiring_type_is_refused(world: _World) -> None:
    """AC4: a JSON submit for a flag-true type → 400 SUPPORTING_DOCUMENT_REQUIRED, no row.

    Story 2.6's submission service is the ONE place this is enforced (FR-13); `details`
    names the Leave Type code that forced it (NFR-17). No `leave_request` row exists and the
    balance never moved — the refusal fired before any lock.
    """
    response = _submit_json(world.applicant_token, world.doc_type_id, _TUE, _THU)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.SUPPORTING_DOCUMENT_REQUIRED
    assert body["details"]["leave_type_code"] == f"SD-{world.suffix}"
    with Session(get_engine()) as session:
        assert _request_count(session, world.doc_type_id) == 0
    assert _balance(world, world.doc_type_id) == (_ENTITLEMENT, 0, 0)


def test_multipart_submit_with_document_is_one_transaction(world: _World) -> None:
    """AC4/OD#1: multipart submit WITH a document → 201; request + row + file, balance once.

    The request is `PENDING` (a managed applicant), `reserved` moved by EXACTLY the frozen
    `leave_days` (once, not twice), the document row references the new request, and the
    bytes sit under its `storage_name`. The 201 is the SAME six-key `SubmitResponse` the
    JSON path returns — the multipart branch is additive, not a second shape.
    """
    response = _submit_multipart(
        world.applicant_token,
        world.doc_type_id,
        _TUE,
        _THU,
        document=("certificate.pdf", _PDF_BYTES, "application/pdf"),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "leave_type_id",
        "start_date",
        "end_date",
        "leave_days",
        "status",
    }
    assert body["status"] == vocabulary.STATUS_PENDING
    assert body["leave_days"] == 3  # Tue–Thu, no holidays seeded

    assert _balance(world, world.doc_type_id) == (_ENTITLEMENT, 3, 0)

    row = _document_row(body["id"])
    assert row is not None
    assert row.original_filename == "certificate.pdf"
    stored_path = get_settings().documents_dir / str(row.storage_name)
    assert stored_path.read_bytes() == _PDF_BYTES


def test_multipart_submit_with_invalid_file_leaves_no_request_row(world: _World) -> None:
    """AC4: an invalid file refuses the WHOLE submission — the transaction is one fact.

    400 UNSUPPORTED_FILE_TYPE, and NO `leave_request` row, NO document row, NO file and NO
    balance movement survive: the request insert, the reservation and the document all rode
    one transaction, and the refusal rolled every one of them back.
    """
    before = _volume_entries()

    response = _submit_multipart(
        world.applicant_token,
        world.doc_type_id,
        _TUE,
        _THU,
        document=("notes.txt", b"plain text", "text/plain"),
    )

    assert response.status_code == 400
    assert response.json()["code"] == vocabulary.UNSUPPORTED_FILE_TYPE
    with Session(get_engine()) as session:
        assert _request_count(session, world.doc_type_id) == 0
    assert _balance(world, world.doc_type_id) == (_ENTITLEMENT, 0, 0)
    assert _volume_entries() == before


def test_multipart_document_on_non_requiring_type_is_stored(world: _World) -> None:
    """OD#1: the §4.7 grant carries no flag precondition — optional evidence is accepted.

    A multipart submit on the flag-FALSE type with a document still stores it: the gate
    refuses absence on a requiring type; it never refuses presence on a non-requiring one.
    """
    response = _submit_multipart(
        world.applicant_token,
        world.free_type_id,
        _MON2,
        _TUE2,
        document=("receipt.png", b"\x89PNG fake", "image/png"),
    )

    assert response.status_code == 201, response.text
    row = _document_row(response.json()["id"])
    assert row is not None
    assert row.content_type == "image/png"


# --- AC5: the scoped GET ---------------------------------------------------------------------


def test_document_streams_to_applicant_manager_and_admin(world: _World) -> None:
    """AC5: the applicant, THEIR Manager and an Admin each stream the bytes back — 200.

    The streamed `Content-Type` equals the STORED one for every authorized reader, and the
    body is the uploaded payload byte-for-byte.
    """
    request_id = _pending_request(world)
    assert (
        _attach(
            world.applicant_token, request_id, ("cert.pdf", _PDF_BYTES, "application/pdf")
        ).status_code
        == 201
    )

    for token in (world.applicant_token, world.manager_token, world.admin_token):
        response = _get_document(token, request_id)
        assert response.status_code == 200
        assert response.content == _PDF_BYTES
        assert response.headers["content-type"] == "application/pdf"


def test_every_get_miss_is_the_one_byte_identical_404(world: _World) -> None:
    """AC5/AD-10: unrelated Employee, unrelated Manager, documentless request, nonexistent id
    — four different misses, ONE byte-identical 404.

    A prober cannot tell "not yours" from "no evidence attached" from "no such request".
    The reference bytes are the nonexistent-id response; every other miss must equal them
    exactly (status AND body).
    """
    request_id = _pending_request(world)
    assert (
        _attach(
            world.applicant_token, request_id, ("cert.pdf", _PDF_BYTES, "application/pdf")
        ).status_code
        == 201
    )
    documentless_id = _submit_json(
        world.applicant_token, world.free_type_id, _MON2, _TUE2
    ).json()["id"]

    reference = _get_document(world.applicant_token, str(uuid.uuid4()))
    assert reference.status_code == 404
    assert reference.json()["code"] == vocabulary.RESOURCE_NOT_FOUND

    for token, target in (
        (world.outsider_token, request_id),  # unrelated Employee, real document
        (world.other_manager_token, request_id),  # unrelated Manager, real document
        (world.applicant_token, documentless_id),  # own request, no document
    ):
        miss = _get_document(token, target)
        assert miss.status_code == reference.status_code
        assert miss.content == reference.content  # byte-identical, down to the envelope


def test_content_disposition_is_attachment_with_rfc5987_filename(world: _World) -> None:
    """AC5/OD#5: the filename leaves ONLY inside `Content-Disposition: attachment` (RFC 5987).

    A non-ASCII filename forces the `filename*=utf-8''…` form (Starlette encodes it); the
    disposition is `attachment`, never `inline` — client-supplied bytes are download-only.
    """
    request_id = _pending_request(world)
    assert (
        _attach(
            world.applicant_token,
            request_id,
            ("certificat médical.pdf", _PDF_BYTES, "application/pdf"),
        ).status_code
        == 201
    )

    response = _get_document(world.manager_token, request_id)

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "filename*=utf-8''" in disposition
    assert "m%C3%A9dical" in disposition  # the é, RFC 5987-encoded


def test_attach_to_anothers_request_is_byte_identical_404(world: _World) -> None:
    """§4.7: the POST grant is scope `self` REGARDLESS of role — even an Admin.

    An unrelated Employee AND an Admin attaching to someone else's request each get the
    404 byte-identical to a nonexistent id: attach is the applicant's own act, always.
    """
    request_id = _pending_request(world)
    reference = _attach(
        world.applicant_token,
        str(uuid.uuid4()),
        ("cert.pdf", _PDF_BYTES, "application/pdf"),
    )
    assert reference.status_code == 404

    for token in (world.outsider_token, world.admin_token):
        miss = _attach(token, request_id, ("cert.pdf", _PDF_BYTES, "application/pdf"))
        assert miss.status_code == reference.status_code
        assert miss.content == reference.content


# --- OD#2: attach-or-replace while PENDING; frozen once decided ------------------------------


def test_second_upload_while_pending_replaces_in_place(world: _World) -> None:
    """OD#2: a second upload while PENDING REPLACES — one row, new file, old bytes gone.

    The row's `id` is stable across the replace (an UPDATE, not a delete-insert — the
    UNIQUE never fires), the new content streams back, and the superseded file no longer
    exists on the volume (best-effort unlink after commit; files outlive rows otherwise).
    """
    request_id = _pending_request(world)
    first = _attach(
        world.applicant_token, request_id, ("v1.pdf", _PDF_BYTES, "application/pdf")
    )
    assert first.status_code == 201
    old_storage = _document_row(request_id).storage_name

    second = _attach(
        world.applicant_token,
        request_id,
        ("v2.png", b"\x89PNG replacement", "image/png"),
    )

    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]  # the SAME row, updated in place

    row = _document_row(request_id)
    assert row.storage_name != old_storage
    assert row.original_filename == "v2.png"
    documents_dir = get_settings().documents_dir
    assert not (documents_dir / str(old_storage)).exists()  # the old bytes are gone
    assert (documents_dir / str(row.storage_name)).read_bytes() == b"\x89PNG replacement"

    served = _get_document(world.applicant_token, request_id)
    assert served.content == b"\x89PNG replacement"
    assert served.headers["content-type"] == "image/png"

    with Session(get_engine()) as session:
        count = session.scalar(
            select(func.count())
            .select_from(SupportingDocument)
            .where(SupportingDocument.leave_request_id == uuid.UUID(request_id))
        )
    assert count == 1


def test_upload_to_a_decided_request_is_refused(world: _World) -> None:
    """OD#2: a decided request's evidence is frozen — 409 TRANSITION_NOT_ALLOWED.

    The request exists and is in scope, so this is neither 404 nor 403: it is the
    state-conflict posture every other guarded transition uses, reused rather than a new
    code (no api-contracts §2 deviation). The document that was attached while PENDING is
    untouched and still streams.
    """
    request_id = _pending_request(world)
    assert (
        _attach(
            world.applicant_token, request_id, ("cert.pdf", _PDF_BYTES, "application/pdf")
        ).status_code
        == 201
    )
    approved = _client.post(
        f"/api/v1/leave-requests/{request_id}/approve", headers=_auth(world.manager_token)
    )
    assert approved.status_code == 200, approved.text

    response = _attach(
        world.applicant_token, request_id, ("late.pdf", _PDF_BYTES, "application/pdf")
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == vocabulary.TRANSITION_NOT_ALLOWED
    assert body["details"] == {}
    assert _document_row(request_id).original_filename == "cert.pdf"  # untouched


# --- AD-8 / AD-16: an upload is not a transition ---------------------------------------------


def test_document_calls_write_no_audit_row_and_no_notification(world: _World) -> None:
    """AD-8/SM-4, AD-16: attach and GET write ZERO audit rows and ZERO notifications.

    An upload is not a state transition (SM-4's exact count of 14 stays literally true —
    the scripted scenario itself is pinned in `test_audit_entries.py`), and the three-kind
    notification set is settled twice over — no `DOCUMENT_UPLOADED` kind exists to write.
    """
    request_id = _pending_request(world)
    with Session(get_engine()) as session:
        audit_before = session.scalar(select(func.count()).select_from(AuditEntry))
        notif_before = session.scalar(select(func.count()).select_from(Notification))

    assert (
        _attach(
            world.applicant_token, request_id, ("cert.pdf", _PDF_BYTES, "application/pdf")
        ).status_code
        == 201
    )
    assert _get_document(world.manager_token, request_id).status_code == 200

    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AuditEntry)) == audit_before
        assert (
            session.scalar(select(func.count()).select_from(Notification)) == notif_before
        )


# --- 2026-07-15 code review: the review-found edges ----------------------------------------


def test_zero_byte_file_is_refused_and_writes_nothing(world: _World) -> None:
    """Review 2026-07-15: an EMPTY file must not satisfy the document requirement.

    Zero bytes is no document of any accepted type → `400 UNSUPPORTED_FILE_TYPE` (the pinned
    three-code set stays closed), the message states the actual ground, and nothing was
    written. Pinned on the attach path AND the multipart submit path — the submit refusal
    rolls the WHOLE submission back (no request row, balance untouched).
    """
    request_id = _pending_request(world)
    before = _volume_entries()

    response = _attach(
        world.applicant_token, request_id, ("empty.pdf", b"", "application/pdf")
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == vocabulary.UNSUPPORTED_FILE_TYPE
    assert "empty" in body["message"]
    assert _volume_entries() == before
    assert _document_row(request_id) is None

    submit = _submit_multipart(
        world.applicant_token,
        world.doc_type_id,
        _TUE,
        _THU,
        document=("empty.pdf", b"", "application/pdf"),
    )
    assert submit.status_code == 400
    assert submit.json()["code"] == vocabulary.UNSUPPORTED_FILE_TYPE
    with Session(get_engine()) as session:
        assert _request_count(session, world.doc_type_id) == 0
    assert _balance(world, world.doc_type_id) == (_ENTITLEMENT, 0, 0)


def test_declared_type_is_normalized_per_rfc_2045(world: _World) -> None:
    """Review 2026-07-15: `Application/PDF` and `image/jpeg; charset=binary` are LEGAL names
    for allowlisted types (RFC 2045: type/subtype case-insensitive, parameters permitted).

    Both are accepted, and the STORED `content_type` — what the GET later serves — is the
    canonical lowercase bare form, so response headers never echo the exotic spelling.
    """
    request_id = _pending_request(world)
    response = _attach(
        world.applicant_token, request_id, ("scan.pdf", _PDF_BYTES, "Application/PDF")
    )
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "application/pdf"
    row = _document_row(request_id)
    assert row is not None and row.content_type == "application/pdf"

    second_id = _submit_json(
        world.applicant_token, world.free_type_id, _MON2, _TUE2
    ).json()["id"]
    response = _attach(
        world.applicant_token,
        second_id,
        ("photo.jpg", b"\xff\xd8fake", "image/jpeg; charset=binary"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "image/jpeg"


def test_get_with_row_but_missing_file_is_the_byte_identical_404(world: _World) -> None:
    """Review 2026-07-15: a document ROW whose FILE is gone (volume restored/pruned apart from
    the DB) must be AD-10's byte-identical 404 — never `FileResponse`'s raw 500.

    The reference bytes are the nonexistent-id miss; the row survives untouched (the read
    repairs nothing).
    """
    request_id = _pending_request(world)
    assert (
        _attach(
            world.applicant_token, request_id, ("cert.pdf", _PDF_BYTES, "application/pdf")
        ).status_code
        == 201
    )
    row = _document_row(request_id)
    assert row is not None
    (get_settings().documents_dir / str(row.storage_name)).unlink()

    reference = _get_document(world.applicant_token, str(uuid.uuid4()))
    assert reference.status_code == 404

    miss = _get_document(world.applicant_token, request_id)
    assert miss.status_code == reference.status_code
    assert miss.content == reference.content  # byte-identical, down to the envelope
    assert _document_row(request_id) is not None  # the row is untouched


def test_malformed_multipart_is_a_400_not_a_500(world: _World) -> None:
    """Review 2026-07-15: a multipart submit with NO boundary (or a garbled body) is a 400.

    Starlette converts its `MultiPartException` into an in-app 400 — the framework shape,
    like the JSON path's malformed-body 422 — and never a raw 500. Pinned so a future
    refactor of the manual `request.form()` call cannot regress it.
    """
    response = _client.post(
        "/api/v1/leave-requests",
        content=b"not a multipart body at all",
        headers={
            "Content-Type": "multipart/form-data",  # no boundary parameter
            **_auth(world.applicant_token),
        },
    )
    assert response.status_code == 400, response.text


def test_uppercase_multipart_content_type_branches_as_multipart(world: _World) -> None:
    """Review 2026-07-15: `Multipart/Form-Data` (legal per RFC 2045) takes the MULTIPART branch.

    Starlette's parser is exact-match lowercase and yields an EMPTY form for the uppercase
    spelling, so the request cannot fully succeed — but branching correctly turns the failure
    into the TRUTHFUL missing-fields 422 (what any FastAPI form route does), not the JSON
    path's opaque `model_attributes_type` 422 over raw bytes.
    """
    boundary = "reviewboundary2026"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="leave_type_id"\r\n\r\n'
        f"{world.free_type_id}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    response = _client.post(
        "/api/v1/leave-requests",
        content=body,
        headers={
            "Content-Type": f"Multipart/Form-Data; boundary={boundary}",
            **_auth(world.applicant_token),
        },
    )
    assert response.status_code == 422, response.text
    missing = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "leave_type_id") in missing  # field-level misses, not model_attributes_type
    types = {error["type"] for error in response.json()["detail"]}
    assert "model_attributes_type" not in types
