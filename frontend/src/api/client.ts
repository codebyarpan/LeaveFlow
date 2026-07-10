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

/** The base path every LeaveFlow endpoint is served under. */
export const API_BASE_PATH = '/api/v1'

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

    throw new ApiError(response.status, envelope)
  }

  // An empty body is a success with nothing to decode — 204 by contract, but also a
  // 200/201 whose body is empty, which `response.json()` would turn into a
  // SyntaxError masquerading as a failed mutation.
  const text = await response.text()
  if (text === '') return undefined as T

  return JSON.parse(text) as T
}
