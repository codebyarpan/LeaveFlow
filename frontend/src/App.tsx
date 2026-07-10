/**
 * The application shell.
 *
 * Implements: AC8 (a usable shell at common desktop and tablet widths), NFR-18.
 *
 * This is a SHELL, and deliberately nothing more. Per-role surfaces land in
 * `src/features/` from Story 1.2 onward. The spine explicitly defers the choice of
 * styling approach and component library, and the story's delivery context names AC8 as
 * the acceptance criterion with slack in it — the import-direction check and the
 * no-domain-table guarantee are what the next 26 stories rest on, not this.
 *
 * It does one substantive thing: read `GET /api/v1/health` through the typed client and
 * TanStack Query, which proves the whole client seam works before any feature needs it.
 */
import { useHealth } from './api'

function HealthIndicator() {
  const { data, isPending, isError, error } = useHealth()

  if (isPending) return <span className="badge badge--waiting">checking…</span>
  if (isError) return <span className="badge badge--down">unreachable — {error.message}</span>

  return <span className="badge badge--up">api {data.status}</span>
}

export function App() {
  return (
    <div className="shell">
      <header className="shell__header">
        <h1 className="shell__title">LeaveFlow</h1>
        <HealthIndicator />
      </header>

      <main className="shell__main">
        <section className="panel">
          <h2>Project foundation</h2>
          <p>
            The skeleton is in place: a four-package backend whose import direction is
            enforced by the test suite, a migration that creates no domain table, and a
            seed command that seeds nothing yet.
          </p>
          <p className="muted">
            Sign-in arrives in Story 1.2. Nothing here is behind a role gate, because no
            role exists.
          </p>
        </section>
      </main>

      <footer className="shell__footer">
        <span className="muted">One deployment, one organization.</span>
      </footer>
    </div>
  )
}
