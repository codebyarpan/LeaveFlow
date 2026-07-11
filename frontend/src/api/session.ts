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
 * Every access is wrapped: `localStorage` is not always available or writable. Safari
 * with "Block All Cookies", a private/incognito context, a sandboxed iframe, or a full
 * storage quota all make `getItem`/`setItem` THROW a `SecurityError`/`QuotaExceededError`.
 * An unguarded throw in `getToken()` (called during App's render) would crash the whole
 * tree to a blank page instead of showing the login screen (AC10). So a failed read
 * degrades to "signed out" and a failed write degrades to a session that lives only in
 * React state — lost on reload, but never a crash and never a stranded login.
 */

/** The single key the token lives under. Exported so a test can assert against it. */
export const TOKEN_STORAGE_KEY = 'leaveflow.token'

/** The stored token, or `null` when no one is signed in (or storage is unreadable). */
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    // Storage denied (private mode, blocked cookies, sandboxed frame). Treat as
    // signed out — the login screen renders rather than the app crashing.
    return null
  }
}

/** Persist the token returned by a successful login. Best-effort: a denied write is swallowed. */
export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } catch {
    // Storage denied or quota exceeded. The caller has already flipped React state, so
    // the session works for this page load; it simply will not survive a reload.
  }
}

/** Forget the token. Story 1.3 calls this on a 401; this story exposes it, unused. */
export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // Nothing to do — if the store is unreachable there is nothing persisted to clear.
  }
}
