"""Supporting-document commands and the streamed read (Story 4.1, FR-13, NFR-05, AD-15).

Implements: AC2 (validation — declared type against the allowlist, then size against the hard
cap — runs and REFUSES before any byte reaches the volume), AC3 (an accepted upload is written
under a SERVER-generated UUID name to the configured directory outside the web root; the
client's filename is persisted as a data column and never touches a path), AC5 (the GET
re-applies AD-10's scope and every miss — nonexistent id, out-of-scope id, documentless
request — is the ONE byte-identical `404`). Open Decisions #2 (attach-or-replace while
PENDING; a decided request's evidence is frozen → `409 TRANSITION_NOT_ALLOWED`), #3
(declared-type + capped-read validation; no magic-byte sniffing), #4 (row flush → file write →
commit; a crash between file write and commit leaves an ORPHAN FILE — opaque UUID name, no row
points to it, no route can reach it — harmless and accepted; cleaning orphans is deliberately
out of scope, no requirement names it).

--- Contract 1: `UploadFile` never crosses into this module ---

The api layer extracts `(payload, declared_type, original_filename)` from the multipart part
and hands over an `UploadDocument` — a plain frozen dataclass. This module imports no FastAPI
type (import-linter contract 4 forbids the import outright). The api layer reads the spool with
a `DOCUMENT_MAX_BYTES + 1` cap, so at most one byte over the limit is ever buffered here;
`_validate` decides `FILE_TOO_LARGE` from the PAYLOAD LENGTH, never from a client-supplied
`Content-Length` header.

--- AD-3: one transaction per command, opened here ---

`attach_document` locates the request row first (scope `SELF` — the §4.7 POST grant is
self-only regardless of role) and touches NO balance row, so no balance lock order applies.
`store_new_document` is the submission command's hook (Task 7): `submit_leave_request` owns
THAT transaction and calls it after `insert_leave_request` flushes the id — one command, one
commit; a refused submission leaves no row and no file.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import leave_request as leave_request_repo
from app.repositories import supporting_document as supporting_document_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services import authorization as authz

# The size cap, re-exported for the `api/` layer (the `LEAVE_STATUS_VALUES` indirection): the
# route reads the multipart spool with a `DOCUMENT_MAX_BYTES + 1` cap and may import neither
# `domain/` (contract 2) nor type the number twice. One declaration, in `domain/vocabulary.py`;
# this name is how the route reaches it through the allowed `api → services` edge.
DOCUMENT_MAX_BYTES = vocabulary.DOCUMENT_MAX_BYTES


@dataclass(frozen=True)
class UploadDocument:
    """One upload as the api layer hands it over — bytes and metadata, no framework type.

    `payload` is the part's content, read by the route with a `DOCUMENT_MAX_BYTES + 1` cap
    (so an oversized upload arrives exactly one byte over, enough to refuse it and no more).
    `declared_type` is the part's own `Content-Type`; `original_filename` is the client's
    filename, DATA from the moment it arrives (NFR-05) — nothing here treats it as a path.
    """

    payload: bytes
    declared_type: str
    original_filename: str


@dataclass(frozen=True)
class DocumentView:
    """The stored document as the upload command hands it up — the 201 projection's fields."""

    id: uuid.UUID
    original_filename: str
    content_type: str


@dataclass(frozen=True)
class DocumentFileView:
    """What the streaming GET needs: the file's path and the two stored header values.

    `path` is `{documents_dir}/{storage_name}` — settings plus a server-generated UUID,
    nothing client-supplied (AD-15). The route builds the `FileResponse` from these three;
    `original_filename` leaves ONLY inside the RFC 5987-encoded `Content-Disposition`.
    """

    path: Path
    content_type: str
    original_filename: str


# One message per refusal, stated once at module level (the `services/leave_requests` idiom).
# `details` carries the numbers/values a refusal must state (NFR-17).
_UNSUPPORTED_FILE_TYPE_MESSAGE = (
    "The file type is not accepted; upload a PDF, JPG or PNG document."
)
_EMPTY_FILE_MESSAGE = (
    "The file is empty; upload a non-empty PDF, JPG or PNG document."
)
_FILE_TOO_LARGE_MESSAGE = "The file exceeds the maximum accepted size."
_DOCUMENT_LOCKED_MESSAGE = (
    "The request is no longer in a state that allows this action: "
    "a decided request's evidence is frozen."
)


def _unsupported_file_type(declared_type: str) -> DomainError:
    """Build the `400 UNSUPPORTED_FILE_TYPE` refusal, naming the offender and the allowlist."""
    return DomainError(
        code=vocabulary.UNSUPPORTED_FILE_TYPE,
        message=_UNSUPPORTED_FILE_TYPE_MESSAGE,
        details={
            "content_type": declared_type,
            "accepted": list(vocabulary.DOCUMENT_CONTENT_TYPES),
        },
    )


def _empty_file(declared_type: str) -> DomainError:
    """Build the refusal for a ZERO-BYTE upload (2026-07-15 code review).

    Reuses `UNSUPPORTED_FILE_TYPE` — the pinned three-code set stays closed: whatever type the
    part declares, zero bytes IS no document of that type, and letting it through would satisfy
    `SUPPORTING_DOCUMENT_REQUIRED` with evidence nobody can open. The message states the actual
    ground (NFR-17).
    """
    return DomainError(
        code=vocabulary.UNSUPPORTED_FILE_TYPE,
        message=_EMPTY_FILE_MESSAGE,
        details={
            "content_type": declared_type,
            "accepted": list(vocabulary.DOCUMENT_CONTENT_TYPES),
        },
    )


def _normalize_media_type(value: str) -> str:
    """Canonicalize a declared media type for the allowlist check (2026-07-15 code review).

    RFC 2045: type/subtype are case-insensitive and may carry parameters — `Application/PDF`
    and `image/jpeg; charset=binary` both name allowlisted types. Browsers send the lowercase
    bare form; this exists for the legal-but-uncommon client. The NORMALIZED form is what gets
    stored and later served as `Content-Type`, so downstream headers stay canonical.
    """
    return value.split(";", 1)[0].strip().lower()


def unlink_quietly(path: Path) -> None:
    """Best-effort unlink: NO failure escapes (2026-07-15 code review).

    Every caller is on a path where the command's real outcome is already decided (a commit
    that failed and is being re-raised, or a replace that COMMITTED and is discarding the old
    bytes). A `PermissionError` here must not convert a committed success into a 500, nor mask
    the original commit error — a leftover file is an unreachable orphan, accepted (OD#4).
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _file_too_large() -> DomainError:
    """Build the `400 FILE_TOO_LARGE` refusal, naming the limit (NFR-17)."""
    return DomainError(
        code=vocabulary.FILE_TOO_LARGE,
        message=_FILE_TOO_LARGE_MESSAGE,
        details={"max_bytes": vocabulary.DOCUMENT_MAX_BYTES},
    )


def _document_locked() -> DomainError:
    """Build the `409` refusal for an upload against a decided request (Open Decision #2).

    Reuses `TRANSITION_NOT_ALLOWED` — the state-conflict posture, not a new code: the request
    exists and is in scope, but it is no longer in the state (PENDING) the action requires,
    which is exactly the semantics every other raiser of this code carries. The message names
    the frozen-evidence rule so the refusal is actionable (NFR-17); a state conflict names no
    numbers, so `details` is empty.
    """
    return DomainError(
        code=vocabulary.TRANSITION_NOT_ALLOWED,
        message=_DOCUMENT_LOCKED_MESSAGE,
        details={},
    )


def _scope_for_role(role: str) -> Scope:
    """Resolve the GET's read scope from the actor's role (AC5) — 2.7's three-way resolution.

    Mirrors `services/leave_requests._scope_for_role` (re-declared, the `services/
    cancellation.py` precedent — that module re-declared its own two-way variant): an Admin
    reads every request's document (`ALL`), a Manager their Direct Reports' (`REPORTS`),
    everyone else their own (`SELF`). Pure, DB-free-testable. Applies to the GET only — the
    POST locate is `Scope.SELF` always, the §4.7 grant.
    """
    if role == authz.ROLE_ADMIN:
        return Scope.ALL
    if role == authz.ROLE_MANAGER:
        return Scope.REPORTS
    return Scope.SELF


def _validate(upload: UploadDocument) -> tuple[bytes, str]:
    """Validate the upload wholly in memory — type FIRST, then size — before any volume write.

    Order fixed by AC2's test pins: the declared part `Content-Type` — NORMALIZED per RFC 2045
    (case-folded, parameters stripped) — against the allowlist (`UNSUPPORTED_FILE_TYPE` — OD#3:
    declared type, no magic-byte sniffing; browsers send `image/jpeg` for .jpg and .jpeg alike),
    then a ZERO-BYTE payload refused under the same code (2026-07-15 code review: an empty file
    must not satisfy `SUPPORTING_DOCUMENT_REQUIRED`), then the payload length against the hard
    cap (`FILE_TOO_LARGE`). The length is the ACTUAL bytes read under the api layer's
    `DOCUMENT_MAX_BYTES + 1` cap — a client-supplied `Content-Length` is never consulted.
    Returns `(payload, normalized_type)` for the caller to store.
    """
    declared_type = _normalize_media_type(upload.declared_type)
    if declared_type not in vocabulary.DOCUMENT_CONTENT_TYPES:
        raise _unsupported_file_type(upload.declared_type)
    if not upload.payload:
        raise _empty_file(upload.declared_type)
    if len(upload.payload) > vocabulary.DOCUMENT_MAX_BYTES:
        raise _file_too_large()
    return upload.payload, declared_type


def _documents_dir() -> Path:
    """The volume directory, ensure-created on first WRITE (never at import — AD-1).

    From settings plus nothing else: no client string ever joins into this path (AD-15).
    `mkdir(parents=True, exist_ok=True)` makes first use on a fresh volume or dev checkout
    work without an operator step.
    """
    directory = get_settings().documents_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def store_new_document(
    session: Session, *, leave_request_id: uuid.UUID, upload: UploadDocument
) -> tuple[uuid.UUID, Path]:
    """Validate, insert the row, write the file — INSIDE the caller's open transaction.

    The submission command's hook (Task 7) and `attach_document`'s insert branch share this
    one implementation. OD#4's ordering: the row is flushed FIRST, the file written SECOND,
    and the caller commits THIRD — so a validation refusal or a file-write failure rolls the
    row back (no row, no file), and only a crash in the commit gap leaves an unreachable,
    accepted orphan file. Returns `(document_id, path)`: the flushed row's id for the 201
    projection, and the written path so the caller can best-effort unlink it if its commit
    fails.

    `storage_name` is `uuid.uuid4()` — server-generated randomness, nothing derived from the
    upload (AD-15); the filename on disk is `str(uuid)`, no extension.
    """
    payload, content_type = _validate(upload)
    storage_name = uuid.uuid4()
    document = supporting_document_repo.insert_supporting_document(
        session,
        leave_request_id=leave_request_id,
        storage_name=storage_name,
        original_filename=upload.original_filename,
        content_type=content_type,
    )
    path = _documents_dir() / str(storage_name)
    path.write_bytes(payload)
    return document.id, path


def attach_document(
    actor: Employee, request_id: uuid.UUID, upload: UploadDocument
) -> DocumentView:
    """Attach (or replace) the document on one's OWN request — one transaction (AC2, AC3; OD#2).

    Scope `SELF` ALWAYS — the §4.7 POST grant is self-only regardless of role, so even an
    Admin attaches only to their own request; anyone else's request is a byte-identical
    `404` (AD-10). In order:

      1. Locate the request under `Scope.SELF` — `None` (nonexistent OR someone else's) →
         `authz.not_found()`.
      2. OD#2's state gate: only a `PENDING` request accepts evidence. A decided request →
         `409 TRANSITION_NOT_ALLOWED` ("a decided request's evidence is frozen").
      3. Validate wholly in memory (type first, then size) — a refusal here has written
         NOTHING (AC2).
      4. Insert or replace: no existing row → `store_new_document` (row flush → file write);
         an existing row → UPDATE it in place with a fresh `storage_name` and write the new
         file (the row's `id` is stable). The `UNIQUE` never gates — this decision does.
      5. `commit()`. A failed commit best-effort unlinks the file just written. AFTER a
         successful replace-commit, best-effort unlink the OLD file — files outlive rows,
         and the old row no longer names it.

    Writes NO audit row (an upload is not a state transition — AD-8; SM-4 stays exactly 14)
    and NO notification (the three-kind set is settled — AD-16).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        request = leave_request_repo.get_leave_request(
            session, actor, request_id, Scope.SELF
        )
        if request is None:
            authz.not_found()

        if request.status != vocabulary.STATUS_PENDING:
            raise _document_locked()

        existing = supporting_document_repo.get_supporting_document(
            session, actor, leave_request_id=request_id, scope=Scope.SELF
        )

        if existing is None:
            document_id, path = store_new_document(
                session, leave_request_id=request_id, upload=upload
            )
            old_storage_name: uuid.UUID | None = None
        else:
            payload, content_type = _validate(upload)
            storage_name = uuid.uuid4()
            supporting_document_repo.update_supporting_document(
                session,
                leave_request_id=request_id,
                storage_name=storage_name,
                original_filename=upload.original_filename,
                content_type=content_type,
            )
            path = _documents_dir() / str(storage_name)
            path.write_bytes(payload)
            document_id = existing.id
            old_storage_name = existing.storage_name

        view = DocumentView(
            id=document_id,
            original_filename=upload.original_filename,
            # The NORMALIZED type — what the row stores and the GET will serve — never the
            # raw declared spelling (2026-07-15 code review).
            content_type=_normalize_media_type(upload.declared_type),
        )
        try:
            session.commit()
        except Exception:
            # OD#4: the commit failed after the file write — the row rolls back with the
            # transaction, so the file must not linger claiming otherwise.
            unlink_quietly(path)
            raise

    # Only AFTER the commit: the old file's row is gone for good, so the bytes may follow.
    # Best-effort — a leftover is an unreachable orphan (opaque UUID name, no row), accepted.
    if old_storage_name is not None:
        unlink_quietly(_documents_dir() / str(old_storage_name))

    return view


def get_document(actor: Employee, request_id: uuid.UUID) -> DocumentFileView:
    """Locate the document on a request for streaming, SCOPED to the caller (AC5).

    Scope resolves from the caller's role exactly as 2.7's detail read does (`_scope_for_role`:
    Employee → `SELF`, Manager → `REPORTS`, Admin → `ALL`); the scoped getter applies the
    predicate in ITS OWN SQL (belt-and-braces AD-10). A `None` — a nonexistent request id, an
    out-of-scope one, or a request that simply has no document — is the SAME byte-identical
    `404 RESOURCE_NOT_FOUND`: a prober cannot tell "not yours" from "no evidence attached".

    A READ session (no commit). Returns path + stored `content_type` + `original_filename`
    for the route to stream; the path is settings + `storage_name`, never anything the client
    sent (AD-15).
    """
    scope = _scope_for_role(actor.role)
    with Session(get_engine(), expire_on_commit=False) as session:
        row = supporting_document_repo.get_supporting_document(
            session, actor, leave_request_id=request_id, scope=scope
        )
        if row is None:
            authz.not_found()
        path = get_settings().documents_dir / str(row.storage_name)
        # Row-without-file (volume restored/pruned apart from the DB — 2026-07-15 code review):
        # `FileResponse` would raise at send time, a raw 500 outside the envelope. The miss
        # joins AD-10's byte-identical `404` — to the caller it is indistinguishable from a
        # request with no evidence attached, which for reading purposes it now is.
        if not path.is_file():
            authz.not_found()
        return DocumentFileView(
            path=path,
            content_type=row.content_type,
            original_filename=row.original_filename,
        )

