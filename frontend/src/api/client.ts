/**
 * The typed API client. Every request to LeaveFlow goes through `apiFetch`.
 *
 * Implements: AC8 (a typed API client), NFR-17 (every non-2xx response carries the
 * `{ code, message, details }` envelope), api-contracts §2.
 *
 * AD-2: no module in this directory — or anywhere under `src/` — may reference a
 * weekday or a Company Holiday. Every leave-day count comes from the server, via the
 * preview endpoint. The client is not permitted a second opinion.
 */
import { clearToken, getToken, SESSION_EXPIRED_EVENT } from './session'

/** The base path every LeaveFlow endpoint is served under. */
export const API_BASE_PATH = '/api/v1'

/**
 * The one wire value the frontend matches against the server envelope's `code`.
 *
 * The backend declares it once in `domain/vocabulary.py` (AD-21); there is no shared
 * constants module across the wire, so the frontend restates it — but in exactly one
 * place, so the "clear the session" decision has a single home. Story 1.3 Dev Notes,
 * Trap 5: a login failure is `401 AUTH_FAILED`, NOT this, and must not sign the user out.
 */
const TOKEN_INVALID_CODE = 'TOKEN_INVALID'

/**
 * The body of every non-2xx response (api-contracts §2).
 *
 * `code` is machine-readable and declared once, in the backend's `domain/vocabulary.py`
 * (AD-21). `details` carries the numbers a refusal must state — `INSUFFICIENT_BALANCE`
 * names `days_requested` and `days_available`, because "not enough balance" is not an
 * actionable answer for a user.
 */
export interface ErrorEnvelope {
  code: string
  message: string
  details: Record<string, unknown>
}

/**
 * A refusal the server stated in its own terms.
 *
 * Carries the envelope through to the caller intact. A component that wants to react to
 * one specific refusal switches on `code`, never on `message` — `message` is prose for a
 * human and may be reworded at any time.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, envelope: ErrorEnvelope) {
    super(envelope.message)
    this.name = 'ApiError'
    this.status = status
    this.code = envelope.code
    this.details = envelope.details
  }
}

/**
 * A body carrying at least `code` and `message`.
 *
 * `details` is checked separately and defaulted, rather than being required here: the
 * server always sends it, but a body that omitted it would still be far more useful to
 * a caller than the synthesized `UNKNOWN_ERROR` fallback.
 */
type PartialEnvelope = Pick<ErrorEnvelope, 'code' | 'message'> & {
  details?: unknown
}

function isErrorEnvelope(value: unknown): value is PartialEnvelope {
  if (typeof value !== 'object' || value === null) return false

  const candidate = value as Record<string, unknown>
  return typeof candidate.code === 'string' && typeof candidate.message === 'string'
}

/**
 * `details` is contracted to be an object. An intermediary that fabricates an
 * envelope-shaped body could put an array or string there — which would then flow
 * to consumers typed as `Record<string, unknown>` and break at runtime.
 */
function asDetails(value: unknown): Record<string, unknown> {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

/**
 * Issue a request against the LeaveFlow API and decode the result.
 *
 * Throws `ApiError` on any non-2xx response, so that TanStack Query's `error` is always
 * a typed refusal rather than an untyped `Response` the caller must remember to check.
 *
 * @param path Path relative to `/api/v1` — for example `/health`. The leading slash is
 *   enforced by the type: without it, `'health'` would silently become `/api/v1health`
 *   and surface as an opaque 404.
 */
export async function apiFetch<T>(path: `/${string}`, init?: RequestInit): Promise<T> {
  // Merge through the Headers API, not object spread: spreading a `Headers`
  // instance yields `{}` (its entries are not own-enumerable properties), which
  // would silently drop a caller's Authorization header.
  const headers = new Headers(init?.headers)

  // Carry the session on every request (AC6, AD-14). `!headers.has(...)` so a
  // caller who set their own Authorization header — there is none today — is never
  // clobbered. A `null` token (signed out) attaches nothing; the request goes out
  // bare and the server answers 401 TOKEN_INVALID, which is exactly right.
  const token = getToken()
  if (token !== null && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  // Content-Type is set only when there is a body to describe, and never over a
  // caller's choice. In particular a `FormData` body must NOT be labelled JSON —
  // the browser sets `multipart/form-data` with its boundary, and overriding it
  // makes the upload unparseable (Story 4.1).
  const body = init?.body
  if (body != null && !(body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_PATH}${path}`, { ...init, headers })

  if (!response.ok) {
    // A non-2xx response is *contracted* to carry the envelope (NFR-17). It may still
    // fail to — a proxy can return its own 502 HTML long before the application is
    // reached — so decoding is attempted, not assumed.
    let envelope: ErrorEnvelope = {
      code: 'UNKNOWN_ERROR',
      message: `The server responded ${response.status} without an error envelope.`,
      details: {},
    }

    try {
      const errorBody: unknown = await response.json()
      if (isErrorEnvelope(errorBody)) {
        envelope = {
          code: errorBody.code,
          message: errorBody.message,
          details: asDetails(errorBody.details),
        }
      }
    } catch {
      // Body was absent or not JSON. Keep the synthesized envelope above.
    }

    // The server rejected the stored token (AC6). Clear it and signal `App` to return to
    // the login screen. Gated on the CODE, not just the status (Trap 5): a wrong-password
    // login is `401 AUTH_FAILED` and must NOT clear a session or sign anyone out — there
    // is no session at login anyway. `clearToken` alone would not re-render `App` (its
    // `token` state still holds the value), so the event is what actually drives the
    // sign-out; `App` subscribes to it and flips its state.
    if (response.status === 401 && envelope.code === TOKEN_INVALID_CODE) {
      clearToken()
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT))
    }

    throw new ApiError(response.status, envelope)
  }

  // An empty body is a success with nothing to decode — 204 by contract, but also a
  // 200/201 whose body is empty, which `response.json()` would turn into a
  // SyntaxError masquerading as a failed mutation.
  const text = await response.text()
  if (text === '') return undefined as T

  return JSON.parse(text) as T
}
