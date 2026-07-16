/**
 * The application root: the login gate, and the shell it protects.
 *
 * Implements: AC8 (a usable shell), AC10 (an unauthenticated visitor sees the login
 * screen; a successful login stores the token and lands them on the shell), NFR-18, and the
 * design-system foundation (spec-design-system-foundation-shell): the stacked single-scroll
 * shell is replaced by the sidebar/top-bar console (`shell/AppShell`), one surface at a time.
 *
 * The gate is deliberately minimal: the presence of a stored token decides which surface
 * renders. There is no router — the spine defers that choice, and navigation is state-based
 * inside the shell. Story 1.3 makes the token *mean* something on every request (the Bearer
 * header, attached in `api/client.ts`) and signs the visitor out when the server rejects
 * it: `apiFetch` clears the token and dispatches `SESSION_EXPIRED_EVENT`, and the effect
 * below turns that into the state flip that returns them to the login screen.
 *
 * The theme controller wraps BOTH branches so the login screen is themed too, and the
 * initial `data-theme` resolution happens regardless of auth.
 */
import { useCallback, useEffect, useState } from 'react'

import { queryClient } from './api'
import { clearToken, getToken, SESSION_EXPIRED_EVENT, setToken } from './api/session'
import { LoginPage } from './features/auth/LoginPage'
import { AppShell } from './shell/AppShell'
import { ThemeProvider } from './shell/theme'

export function App() {
  // Initialized from storage so a reload keeps the visitor signed in (AC10). The state
  // is what makes the switch reactive: storing the token alone would not re-render.
  const [token, setSessionToken] = useState<string | null>(() => getToken())

  // The one teardown both sign-out paths converge on: flip the token gate to `null` and
  // drop the whole query cache. Shared by the server-driven SESSION_EXPIRED listener and
  // the deliberate logout below, so the two can never drift into different end states.
  //
  // Drop the ENTIRE query cache with the session (code review 2026-07-15). NO cache key in
  // this app carries a per-user identity — every scoped read (`['me']`, `['notifications']`,
  // `['dashboard']`, `['leaveRequests']`, `['team']`, `['calendar']`, `['balances']`, …) would
  // be served to the NEXT user who signs in on this same browser (within `staleTime`) before
  // any refetch: a genuine cross-user disclosure, not cosmetic staleness. `clear()` closes the
  // CLASS: a future story's key is purged on day one, and the only cost is refetching public
  // config (leave types, holidays) the next user needed fresh anyway.
  const signOut = useCallback(() => {
    setSessionToken(null)
    queryClient.clear()
  }, [])

  // Drive the server-side sign-out (Trap 6). `apiFetch` clears the stored token on a 401
  // TOKEN_INVALID and dispatches this event; clearing storage alone does not re-render,
  // because `token` above still holds the value. `signOut` flips it to `null`, returning
  // the visitor to the login screen. The listener is decoupled by design — `client.ts`
  // never imports `App`, so there is no cycle. Cleaned up on unmount. Note the token was
  // ALREADY cleared by `client.ts` here, which is why `signOut` does not clear it itself —
  // the deliberate logout path (`handleLogout`) adds that missing `clearToken` call.
  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, signOut)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, signOut)
  }, [signOut])

  // Deliberate logout (spec-logout): unlike the expiry path, no one has cleared the stored
  // token yet, so this clears it (memory + localStorage, defensively) BEFORE the shared
  // teardown — otherwise a reload would rehydrate `memoryToken` and revive the session.
  const handleLogout = useCallback(() => {
    clearToken()
    signOut()
  }, [signOut])

  return (
    <ThemeProvider>
      {token === null ? (
        <LoginPage
          onAuthenticated={(issued) => {
            // Drop the ENTIRE query cache before the shell mounts (code review 2026-07-15), so a
            // fresh login on a shared browser fetches everything as itself rather than reading a
            // cached predecessor — the same class-closing `clear()` as the session-expiry listener
            // above: no key in this app carries a per-user identity, and the per-key list this
            // replaced went stale twice.
            queryClient.clear()
            setSessionToken(issued) // flip this render to the shell FIRST — so that a
            setToken(issued) // denied/quota-exceeded persist (guarded, best-effort) can
            // never strand a successful login on the form. Reload persistence is the only
            // thing lost if the write fails; the session still works for this page load.
          }}
        />
      ) : (
        <AppShell onLogout={handleLogout} />
      )}
    </ThemeProvider>
  )
}
