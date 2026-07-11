/**
 * The session token's one home in the browser.
 *
 * Implements: AC10 (a successful login stores the token; the app then shows the shell).
 *
 * One key, one module. Every read and write of the stored token goes through here, so
 * that Story 1.3 — which attaches it as an `Authorization: Bearer` header on every
 * request and clears it on a 401 `TOKEN_INVALID` — has a single seam to build on rather
 * than a scatter of `localStorage` calls to find. This story stores and reads; it does
 * not attach and does not expire. Those are 1.3's, deliberately left out here.
 *
 * `localStorage`, not a cookie: the token is a Bearer credential the client sends
 * explicitly (1.3), not something the browser should attach automatically to every
 * request to the origin. It survives a reload, which is what AC10's "lands them on the
 * shell" needs across a refresh.
 *
 * `localStorage` is not always available or writable. Safari with "Block All Cookies", a
 * private/incognito context, a sandboxed iframe, or a full storage quota all make
 * `getItem`/`setItem` THROW a `SecurityError`/`QuotaExceededError`. So the token has an
 * in-memory home too: `memoryToken` below is the authoritative source `getToken` returns,
 * and `localStorage` is only its best-effort persistence across reloads.
 *
 * This matters because `apiFetch` reads the Bearer header from `getToken()`, NOT from
 * App's React state. If `getToken` had to touch `localStorage` on every call, a denied
 * write (private mode) would leave nothing to read back, and every request would go out
 * bare — a valid login would 401 and bounce straight to the login screen. Sourcing from
 * memory instead: a failed `setItem` still updates `memoryToken`, so the session works
 * for this page load; only reload persistence is lost. A failed `getItem` (at import, or
 * mid-session) degrades to "signed out" at worst, and never crashes App's render (AC10).
 */

/** The single key the token lives under. Exported so a test can assert against it. */
export const TOKEN_STORAGE_KEY = 'leaveflow.token'

/**
 * The `window` event `apiFetch` dispatches when the server rejects the stored token
 * (a 401 `TOKEN_INVALID`). `App` subscribes and flips its `token` state to `null`.
 *
 * A decoupled `CustomEvent` — not a direct call into `App` — is what lets `client.ts`
 * drive the sign-out without importing `App` (which would be a cycle: `App -> api -> App`).
 * Declared here, the one module both the dispatcher and the subscriber already import, so
 * the name is one constant rather than a string literal duplicated across two files.
 */
export const SESSION_EXPIRED_EVENT = 'leaveflow:session-expired'

/**
 * The authoritative session token for this page load. Hydrated once from `localStorage`
 * at module load — a throw there (storage denied) simply leaves it `null` ("signed out").
 * Every later `getToken` reads this, so a mid-session `getItem` failure can never drop the
 * Bearer header and force-sign-out an otherwise-valid session.
 */
let memoryToken: string | null = readStoredToken()

/** Read the persisted token, degrading a denied/unavailable store to `null`. */
function readStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    // Storage denied (private mode, blocked cookies, sandboxed frame). Treat as signed out.
    return null
  }
}

/** The current token, or `null` when no one is signed in. Sourced from memory, not storage. */
export function getToken(): string | null {
  return memoryToken
}

/** Set the token for this page load and best-effort persist it across reloads. */
export function setToken(token: string): void {
  // Memory first: this is what `apiFetch` reads, so the session works even if the persist
  // below throws. The `localStorage` write is best-effort — a denied/quota-exceeded write
  // only costs reload persistence, never the live session.
  memoryToken = token
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } catch {
    // Storage denied or quota exceeded. `memoryToken` still holds the value, so the
    // session works for this page load; it simply will not survive a reload.
  }
}

/** Forget the token — both the live session (memory) and its persisted copy. */
export function clearToken(): void {
  // Memory first, so a 401 signs the session out for this page load even when the
  // `removeItem` below throws (a store that can be read but not written).
  memoryToken = null
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // Nothing more to do — the live session is already cleared; the persisted copy is
    // unreachable to remove. On a reload it may revive, get a 401, and clear again — a
    // single bounce to the login screen, not a loop (App renders the form, not `/me`).
  }
}
