/**
 * The application root: the login gate, and the shell it protects.
 *
 * Implements: AC8 (a usable shell), AC10 (an unauthenticated visitor sees the login
 * screen; a successful login stores the token and lands them on the shell), NFR-18.
 *
 * The gate is deliberately minimal: the presence of a stored token decides which surface
 * renders. There is no router — the spine defers that choice, and this story does not
 * force it. Story 1.3 makes the token *mean* something on every request (the Bearer
 * header, attached in `api/client.ts`) and signs the visitor out when the server rejects
 * it: `apiFetch` clears the token and dispatches `SESSION_EXPIRED_EVENT`, and the effect
 * below turns that into the state flip that returns them to the login screen.
 */
import { useEffect, useState } from 'react'

import { ME_QUERY_KEY, queryClient, useHealth, useMe } from './api'
import { getToken, SESSION_EXPIRED_EVENT, setToken } from './api/session'
import { LoginPage } from './features/auth/LoginPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { DepartmentsPage } from './features/departments/DepartmentsPage'
import { EmployeesPage } from './features/employees/EmployeesPage'
import { HolidaysPage } from './features/holidays/HolidaysPage'
import { RequestPreviewPanel } from './features/leave/RequestPreviewPanel'
import { LeaveTypesPage } from './features/leaveTypes/LeaveTypesPage'
import { ProfilePage } from './features/profile/ProfilePage'

function HealthIndicator() {
  const { data, isPending, isError, error } = useHealth()

  if (isPending) return <span className="badge badge--waiting">checking…</span>
  if (isError) return <span className="badge badge--down">unreachable — {error.message}</span>

  return <span className="badge badge--up">api {data.status}</span>
}

function AppShell() {
  // A `/me`-backed request: it proves the Bearer header is carried (AC6). If the token is
  // rejected, `apiFetch` has already cleared it and dispatched the sign-out event, so this
  // query erroring is the visible edge of the same flow — not something to handle here.
  const { data, isPending } = useMe()

  // Prefer the data whenever we have it: a background refetch that fails (e.g. a 502 while
  // the api restarts) leaves `isError` true while `data` still holds the last-good profile,
  // so checking `data` before `isError` keeps the name on screen instead of blanking it to
  // "profile unavailable". That message is reserved for an error with nothing cached.
  const identity = data
    ? `${data.full_name} · ${data.role} · ${data.department.name}`
    : isPending
      ? 'loading your profile…'
      : 'profile unavailable'

  return (
    <div className="shell">
      <header className="shell__header">
        <h1 className="shell__title">LeaveFlow</h1>
        <HealthIndicator />
      </header>

      <main className="shell__main">
        <section className="panel">
          <h2>Signed in</h2>
          <p className="muted">{identity}</p>
          <p>
            You are authenticated. The per-role surfaces — a dashboard, the request
            lifecycle, the team calendar — arrive across Epics 2 and 3; this shell is
            what they render into.
          </p>
          <p className="muted">
            The session is a Bearer token held in the browser. It is attached to every
            request, and the server signs you out when it rejects one.
          </p>
        </section>

        {/* The Employee dashboard (Story 2.4): the caller's own leave balances, Available
            prominent with Reserved disclosed alongside. Renders for every authenticated user
            (scope `self`); the client renders server figures as-is (AD-2). */}
        <DashboardPage />

        {/* Request preview (Story 2.5): the caller picks a Leave Type and a range and sees the
            day count, the projected balance, and the named excluded dates before submitting. The
            server is the sole day-count authority; the client renders its figures as-is (AD-2). */}
        <RequestPreviewPanel />

        {/* Self-service: renders for every authenticated user (Role "any"). The Full Name
            is editable here; every other field is read-only, and the server is the guard. */}
        <ProfilePage />

        <DepartmentsPage />
        {/* Admin-only: EmployeesPage renders null for a non-Admin (its own useMe gate). The
            real guard is always the server's 403 on every /employees endpoint (AC5). */}
        <EmployeesPage />
        {/* Any-role list, Admin-only create form (Pattern A, like Departments). The GET is
            any-role (scope `all`); the server's 403 on POST is the real guard (Story 2.1). */}
        <LeaveTypesPage />
        {/* Any-role list, Admin-only add/delete controls (Pattern A). The GET is any-role
            (scope `all`); the server's 403 on POST/DELETE is the real guard (Story 2.2). */}
        <HolidaysPage />
      </main>

      <footer className="shell__footer">
        <span className="muted">One deployment, one organization.</span>
      </footer>
    </div>
  )
}

export function App() {
  // Initialized from storage so a reload keeps the visitor signed in (AC10). The state
  // is what makes the switch reactive: storing the token alone would not re-render.
  const [token, setSessionToken] = useState<string | null>(() => getToken())

  // Drive the sign-out (Trap 6). `apiFetch` clears the stored token on a 401 TOKEN_INVALID
  // and dispatches this event; clearing storage alone does not re-render, because `token`
  // above still holds the value. Flipping it to `null` here is what returns the visitor to
  // the login screen. The listener is decoupled by design — `client.ts` never imports
  // `App`, so there is no cycle. Cleaned up on unmount.
  useEffect(() => {
    const onSessionExpired = () => {
      setSessionToken(null)
      // Drop the profile cache with the session. `['me']` carries no per-user identity, so
      // a stale entry left here would be served to the NEXT user who signs in on this same
      // browser (within `staleTime`) before any refetch — the previous user's name, role
      // and department. Clearing it on sign-out closes that window.
      queryClient.removeQueries({ queryKey: ME_QUERY_KEY })
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onSessionExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onSessionExpired)
  }, [])

  if (token === null) {
    return (
      <LoginPage
        onAuthenticated={(issued) => {
          // Drop any prior user's profile before the shell mounts, so a fresh login on a
          // shared browser fetches its own `/me` rather than reading a cached predecessor.
          queryClient.removeQueries({ queryKey: ME_QUERY_KEY })
          setSessionToken(issued) // flip this render to the shell FIRST — so that a
          setToken(issued) // denied/quota-exceeded persist (guarded, best-effort) can
          // never strand a successful login on the form. Reload persistence is the only
          // thing lost if the write fails; the session still works for this page load.
        }}
      />
    )
  }

  return <AppShell />
}
