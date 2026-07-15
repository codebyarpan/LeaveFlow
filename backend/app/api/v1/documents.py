"""The `/api/v1/leave-requests/{id}/document` routes: the upload and the streamed download.

Implements: FR-13 (`POST` attaches — or, while the request is still PENDING, replaces — the
document an existing Leave Request carries; `GET` streams it back to the applicant, their
Manager, or an Admin), NFR-05 / AD-15 (the file lives OUTSIDE the web root under a
server-generated UUID name; no static route maps to the volume — THESE two authorized
endpoints are the only path to the bytes; the client's filename is DATA, returned only inside
an RFC 5987-encoded `Content-Disposition` header), AC2, AC3, AC5 (Story 4.1).

--- What this module may import, and what it may not ---

The route imports `services/` and the `api/`-layer `dependencies` only — never
`repositories/` or `domain/` (contract 2). The vocabulary codes reach the client through the
service's `DomainError` and the one handler; the size cap arrives by NAME through the
service's re-export (`documents_service.DOCUMENT_MAX_BYTES` — the `LEAVE_STATUS_VALUES`
indirection). Both endpoints are `get_current_employee`, NOT `require_role` (api-contracts
§4.7: role `any` for both): the POST's scope is `self` — intrinsic to the token subject —
and the GET's scope (`self`/`reports`/`all`) resolves from the caller's role in the service.

--- Why the routes are sync `def` ---

Starlette's `UploadFile.file` is a synchronous `SpooledTemporaryFile`; a sync route reads it
without the async drift the rest of the codebase avoids. Only OD#1's dual-mode submit route
(in `leave_requests.py`) needs `async def`, for `await request.form()`.

--- The 2xx shapes ---

`POST` → `201` with the minimal `{id, original_filename, content_type}` (key set pinned by
test). `GET` → `200` raw bytes — the FIRST non-JSON 200 in the app: there is no envelope to
pin, so the tests pin the two headers instead (`Content-Type` equals the STORED type;
`Content-Disposition: attachment` carries the RFC 5987 filename, which Starlette encodes).
"""

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.v1.dependencies import Actor, get_current_employee
from app.services import documents as documents_service

router = APIRouter()


class DocumentResponse(BaseModel):
    """The stored document on the wire (Story 4.1) — the minimal 201 projection.

    `original_filename` is echoed VERBATIM (it is data, NFR-05); `content_type` is the
    declared type the upload was validated against. No `storage_name` — the server-side
    name is an implementation detail no client needs, and disclosing it would only invite
    path guessing against a directory no route serves anyway.
    """

    id: uuid.UUID
    original_filename: str
    content_type: str


def _to_document_response(view: object) -> DocumentResponse:
    """Project a `DocumentView` into the response, BY HAND (the `balances.py` precedent).

    Typed `object` because `api/` does not import the service dataclass (contract 2's house
    reading); the service guarantees the fields are present.
    """
    return DocumentResponse(
        id=view.id,
        original_filename=view.original_filename,
        content_type=view.content_type,
    )


@router.post(
    "/leave-requests/{request_id}/document",
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def attach_document(
    request_id: uuid.UUID,
    document: UploadFile = File(...),
    caller: Actor = Depends(get_current_employee),
) -> DocumentResponse:
    """Attach (or replace) the document on one's OWN Pending request (AC2, AC3; OD#2).

    `get_current_employee`, role any; scope `self` ALWAYS (§4.7) — even an Admin attaches
    only to their own request, and anyone else's is a byte-identical `404`. The multipart
    part is read HERE, off the sync spool, with a `DOCUMENT_MAX_BYTES + 1` cap — at most one
    byte over the limit is ever buffered, and a client-supplied `Content-Length` is never
    consulted — then handed to the service as plain bytes + metadata (`UploadFile` does not
    cross the layer boundary, contract 1). Refusals: wrong declared type → `400
    UNSUPPORTED_FILE_TYPE`; over 5 MB → `400 FILE_TOO_LARGE` (both BEFORE any volume write,
    AC2); a decided request → `409 TRANSITION_NOT_ALLOWED` (evidence is frozen, OD#2).
    """
    payload = document.file.read(documents_service.DOCUMENT_MAX_BYTES + 1)
    upload = documents_service.UploadDocument(
        payload=payload,
        declared_type=document.content_type or "",
        original_filename=document.filename or "",
    )
    view = documents_service.attach_document(caller, request_id, upload)
    return _to_document_response(view)


@router.get("/leave-requests/{request_id}/document", tags=["documents"])
def get_document(
    request_id: uuid.UUID,
    caller: Actor = Depends(get_current_employee),
) -> FileResponse:
    """Stream the document on a request, scoped to the caller (AC5). Any role.

    Scope resolves from the caller's role in the service (Employee `self`, Manager
    `reports`, Admin `all` — §4.7); every miss — a nonexistent id, an out-of-scope one, a
    request with no document — is the ONE byte-identical `404` (AD-10). The file is opened
    by its server-generated `storage_name` joined to the configured directory — nothing
    client-supplied touches the path (AD-15). `attachment`, not `inline` (OD#5): serving
    client-supplied bytes inline on the app's origin is a stored-XSS-adjacent risk for a
    mislabelled file; download-only closes it. Starlette RFC 5987-encodes `filename*`.
    """
    view = documents_service.get_document(caller, request_id)
    return FileResponse(
        view.path,
        media_type=view.content_type,
        filename=view.original_filename,
        content_disposition_type="attachment",
    )
