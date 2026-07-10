/**
 * The application root: the login gate, and the shell it protects.
 *
 * Implements: AC8 (a usable shell), AC10 (an unauthenticated visitor sees the login
 * screen; a successful login stores the token and lands them on the shell), NFR-18.
 *
 * The gate is deliberately minimal for Story 1.2: the presence of a stored token decides
 * which surface renders. There is no router — the spine defers that choice, and this
 * story does not force it. Story 1.3 makes the token *mean* something on every request
 * (the Bearer header) and clears it on a 401; here it is only the switch between the
 * login screen and the shell.
 */
import { useState } from 'react'

import { useHealth } from './api'
import { getToken, setToken } from './api/session'
import { LoginPage } from './features/auth/LoginPage'

function HealthIndicator() {
  const { data, isPending, isError, error } = useHealth()

  if (isPending) return <span className="badge badge--waiting">checking…</span>
  if (isError) return <span className="badge badge--down">unreachable — {error.message}</span>

  return <span className="badge badge--up">api {data.status}</span>
}

function AppShell() {
  return (
    <div className="shell">
      <header className="shell__header">
        <h1 className="shell__title">LeaveFlow</h1>
        <HealthIndicator />
      </header>

      <main className="shell__main">
        <section className="panel">
          <h2>Signed in</h2>
          <p>
            You are authenticated. The per-role surfaces — a dashboard, the request
            lifecycle, the team calendar — arrive across Epics 2 and 3; this shell is
            what they render into.
          </p>
          <p className="muted">
            The session is a Bearer token held in the browser. Story 1.3 attaches it to
            every request and signs you out when the server rejects it.
          </p>
        </section>
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

  if (token === null) {
    return (
      <LoginPage
        onAuthenticated={(issued) => {
          setToken(issued) // persist to localStorage (survives reload)
          setSessionToken(issued) // flip this render to the shell
        }}
      />
    )
  }

  return <AppShell />
}
