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
 */

/** The single key the token lives under. Exported so a test can assert against it. */
export const TOKEN_STORAGE_KEY = 'leaveflow.token'

/** The stored token, or `null` when no one is signed in. */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

/** Persist the token returned by a successful login. */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

/** Forget the token. Story 1.3 calls this on a 401; this story exposes it, unused. */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}
