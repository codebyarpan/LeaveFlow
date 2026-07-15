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
import { useCallback, useEffect, useState } from 'react'

import { queryClient, useHealth, useMe, useUnreadCount } from './api'
import { clearToken, getToken, SESSION_EXPIRED_EVENT, setToken } from './api/session'
import { LoginPage } from './features/auth/LoginPage'
import { AdminDashboardPanel } from './features/dashboard/AdminDashboardPanel'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { ManagerDashboardPanel } from './features/dashboard/ManagerDashboardPanel'
import { DepartmentsPage } from './features/departments/DepartmentsPage'
import { EmployeesPage } from './features/employees/EmployeesPage'
import { HolidaysPage } from './features/holidays/HolidaysPage'
import { CancellationRequestsPanel } from './features/leave/CancellationRequestsPanel'
import { AuditLogPanel } from './features/audit/AuditLogPanel'
import { ReviewFlagsPanel } from './features/reviewFlags/ReviewFlagsPanel'
import { ManagerQueuePanel } from './features/leave/ManagerQueuePanel'
import { MyLeaveHistoryPanel } from './features/leave/MyLeaveHistoryPanel'
import { MyTeamPanel } from './features/team/MyTeamPanel'
import { RequestCancellationPanel } from './features/leave/RequestCancellationPanel'
import { RequestPreviewPanel } from './features/leave/RequestPreviewPanel'
import { LeaveTypesPage } from './features/leaveTypes/LeaveTypesPage'
import { PolicyChangesPanel } from './features/policyChanges/PolicyChangesPanel'
import { NotificationsPanel } from './features/notifications/NotificationsPanel'
import { ProfilePage } from './features/profile/ProfilePage'
import { ReportsPanel } from './features/reports/ReportsPanel'

function HealthIndicator() {
  const { data, isPending, isError, error } = useHealth()

  if (isPending) return <span className="badge badge--waiting">checking…</span>
  if (isError) return <span className="badge badge--down">unreachable — {error.message}</span>

  return <span className="badge badge--up">api {data.status}</span>
}

/**
 * The unread-notification badge (Story 3.4, AC7) — modelled on `HealthIndicator` above, and slotted
 * into `.shell__header` as a third flex child. ZERO new CSS: the header is already
 * `display:flex; justify-content:space-between; flex-wrap:wrap`, and `.badge`/`.badge--waiting` are
 * the existing pill.
 *
 * 🚨 NO ROLE GATE — AC7's "an Employee is authenticated" means an authenticated PERSON, not the
 * `EMPLOYEE` role. All three notification endpoints are role `any` (api-contracts §4.8), and a
 * MANAGER is the primary recipient (`REQUEST_SUBMITTED` is addressed to her). Gating this on a role
 * would hide the very notification FR-14 exists to deliver.
 *
 * Silent while loading or on error: an unread count is ambient information, and a broken pill in the
 * header is worse than no pill. It renders nothing at zero, too — "0 unread" is noise.
 */
function UnreadBadge() {
  const { data, isPending, isError } = useUnreadCount()

  if (isPending || isError || data.unread === 0) return null

  return <span className="badge badge--waiting">{data.unread} unread</span>
}

function AppShell({ onLogout }: { onLogout: () => void }) {
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
        <UnreadBadge />
        <HealthIndicator />
        {/* Sign out (spec-logout): clears the token and the query cache, then App's token
            gate flips back to the login screen. A deliberate teardown — the counterpart to
            the server-driven SESSION_EXPIRED sign-out. */}
        <button type="button" className="shell__logout" onClick={onLogout}>
          Log out
        </button>
      </header>

      <main className="shell__main">
        <section className="panel">
          <h2>Signed in</h2>
          <p className="muted">{identity}</p>
          <p>
            The dashboards below are scoped to your role: everyone sees their own
            balances and pending requests; a Manager additionally sees their team&apos;s,
            and an Admin the organization&apos;s (Story 3.5).
          </p>
          <p className="muted">
            The session is a Bearer token held in the browser. It is attached to every
            request, and the server signs you out when it rejects one.
          </p>
        </section>

        {/* In-app notifications (Story 3.4, FR-14): what happened to my leave, and — if I am a
            Manager — what is waiting for my decision. Opening one marks it read (idempotently).
            🚨 The ONE panel in the app with NO role gate, deliberately: all three endpoints are role
            `any` (api-contracts §4.8) and a MANAGER is the primary recipient, so gating on a role
            would hide the notification FR-14 exists to deliver. The server's addressee scope
            predicate is the guard; a non-addressee gets a 404, never a 403. */}
        <NotificationsPanel />

        {/* The Employee dashboard (Story 2.4, extended by 3.5): the caller's own leave
            balances plus their pending-request count, with a date-range filter. Renders for
            every authenticated user (role `any`, scope `self` — a Manager sees their OWN
            balances here, AC5); the client renders server figures as-is (AD-2). */}
        <DashboardPage />

        {/* The Manager dashboard (Story 3.5): the pending-decision count and the reports on
            approved leave in the server's window (default: the next seven days, echoed back).
            Renders null for a non-Manager (its own useMe gate); the server's 403
            (require_role MANAGER — the Admin is refused too, §4.9) is the real guard. */}
        <ManagerDashboardPanel />

        {/* The Admin dashboard (Story 3.5): organization-wide totals — employees on approved
            leave (default window: today) and the pending LEAVE-request count (Cancellation
            Requests deliberately excluded; their queue is below). Renders null for a
            non-Admin (its own useMe gate); the server's 403 (require_role ADMIN) is the real
            guard. */}
        <AdminDashboardPanel />

        {/* Request Leave (Story 2.5 preview → 2.6 submit): the caller picks a Leave Type and a
            range, sees the day count, the projected balance and the named excluded dates, then
            SUBMITS — after which Available falls immediately (the balances query is invalidated).
            The server is the sole day-count authority; the client renders its figures as-is (AD-2). */}
        <RequestPreviewPanel />

        {/* My leave history (Story 3.1): a plain Employee's every request, cross-year and
            every-state, filterable by type/state/date range — and the app's first pagination UI.
            Renders null for a non-Employee (its own useMe gate, Open Decision #4 — a Manager's
            list is their reports', an Admin's everyone's; "my history" would be a false label).
            The server's scope predicate is the real guard; server figures render as-is (AD-2). */}
        <MyLeaveHistoryPanel />

        {/* The Manager decision queue (Story 2.7): a Manager's Direct Reports' PENDING requests,
            each approvable/rejectable. Renders null for a non-Manager (its own useMe gate); the
            server's 403 (require_role) and byte-identical 404 (reports scope) are the real guards.
            After a decision the queue and balances refresh; the server's leave_days is rendered
            as-is (AD-2). */}
        <ManagerQueuePanel />

        {/* My team (Story 3.2): a Manager's Direct Reports, each named with Department and
            active state — a deactivated report stays listed, marked "(deactivated)". Renders
            null for a non-Manager (its own useMe gate); the server's 403 (require_role
            MANAGER — the Admin is refused too, api-contracts §4.9) and the REPORTS scope
            predicate are the real guards. Server values render as-is (AD-2). */}
        <MyTeamPanel />

        {/* Cancel approved leave (Story 2.8): a plain Employee's own APPROVED requests, each
            offering a cancellation request an Admin then decides. Renders null for a non-Employee
            (its own useMe gate, Open Decision #6 — a Manager's list is their reports', not their
            own); the server's self-scoped 404 is the real guard. No client day count (AD-2). */}
        <RequestCancellationPanel />

        {/* The Admin's Cancellation Requests screen (Story 2.8): every PENDING cancellation
            request, each approvable/rejectable — the Admin's only route to one (none is announced
            by notification or dashboard). Renders null for a non-Admin (its own useMe gate); the
            server's 403 (require_role ADMIN) is the real guard. No client day count (AD-2). */}
        <CancellationRequestsPanel />
        <AuditLogPanel />

        {/* The Admin's Review Flags screen (Story 2.11, AC9): every recalculation the system
            REFUSED, each naming the balance it left unchanged. Not optional — a refusal recorded
            where nobody looks is exactly the wrong figure that will be believed (PRD §1). No control
            clears a flag: FR-10 grants a read and no requirement grants a resolve (AD-20). Renders
            null for a non-Admin (its own useMe gate); the server's 403 (require_role ADMIN) is the
            real guard. */}
        <ReviewFlagsPanel />

        {/* The Admin's Policy Changes screen (Story 2.12, AC12): every change to a leave type's
            policy, its old and new value, and the disposition applied to the balances that already
            existed. It is the record of WHY a balance is the number it is — and nothing here amends a
            change (AD-9: the app role holds INSERT and SELECT on `policy_change`, and neither UPDATE
            nor DELETE). Renders null for a non-Admin (its own useMe gate); the server's 403
            (require_role ADMIN) is the real guard. */}
        <PolicyChangesPanel />

        {/* The leave report (Story 4.2, FR-15): a Manager exports their Direct Reports' leave,
            an Admin the organization's — filters + a paged on-screen list + a CSV export that
            carries EVERY row matching those same filters (never just the visible page). Renders
            null for a plain Employee (its own useMe gate); the server's 403 (require_role
            MANAGER/ADMIN) and scope predicate are the real guards. No charts (SM-C2). */}
        <ReportsPanel />

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

  if (token === null) {
    return (
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
    )
  }

  return <AppShell onLogout={handleLogout} />
}
