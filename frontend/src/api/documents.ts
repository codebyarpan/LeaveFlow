/**
 * Supporting documents (Story 4.1, FR-13). The attach/replace upload and the blob download.
 *
 * The UPLOAD's primary ride is the submission itself — `useSubmitLeaveRequest` sends
 * `multipart/form-data` when a file is present, so a document-requiring type submits in ONE
 * request (OD#1). `uploadDocument` here is the standalone attach/replace against an EXISTING
 * Pending request (a request whose type's flag flipped afterwards; optional evidence on a
 * non-requiring type). The DOWNLOAD is the Manager's decision-screen "View document" button
 * (OD#6): an on-demand blob fetch — never eager — whose 404 renders as "No document attached."
 * (byte-identical, server-side, to a nonexistent request — AD-10; the client cannot and does
 * not distinguish).
 *
 * A `FormData` body is deliberately NOT labelled JSON by `apiFetch` — the browser sets the
 * multipart boundary (`client.ts` anticipated this story by name).
 */
import { apiFetch, apiFetchBlob } from './client'

/**
 * The stored document on the wire, mirroring the backend `DocumentResponse` — the minimal
 * `{id, original_filename, content_type}` the 201 returns (key set pinned server-side).
 */
export interface DocumentUploadResult {
  id: string
  original_filename: string
  content_type: string
}

/**
 * Attach (or, while the request is still PENDING, replace) the document on one's OWN request.
 *
 * Scope `self` server-side regardless of role; a decided request refuses with
 * `409 TRANSITION_NOT_ALLOWED` ("a decided request's evidence is frozen"), a rejected file
 * with `400 UNSUPPORTED_FILE_TYPE` / `FILE_TOO_LARGE` — the server is the guard, whatever the
 * client pre-checked.
 */
export function uploadDocument(
  requestId: string,
  file: File,
): Promise<DocumentUploadResult> {
  const formData = new FormData()
  formData.append('document', file)
  return apiFetch<DocumentUploadResult>(
    `/leave-requests/${encodeURIComponent(requestId)}/document`,
    { method: 'POST', body: formData },
  )
}

/**
 * Fetch a request's document as a `Blob` — the applicant, their Manager, or an Admin.
 *
 * On-demand only (OD#6): callers fetch when the user asks, never eagerly per row. A 404 —
 * no document, or a request outside the caller's scope, indistinguishable by design —
 * surfaces as a typed `ApiError` with `status === 404` for the caller to render inline.
 */
export function fetchDocumentBlob(requestId: string): Promise<Blob> {
  return apiFetchBlob(`/leave-requests/${encodeURIComponent(requestId)}/document`)
}
