/**
 * The Admin's audit-log screen (Story 2.9). OPTIONAL — no AC requires it.
 *
 * Implements: FR-16 (frontend) — an Admin reads the append-only record of every state transition, so
 * that "a disagreement about what was approved is settled by the system rather than by whoever kept
 * better notes". The implementation-readiness report (F-8) is explicit that `GET /audit-entries` has
 * NO frontend criterion and that the endpoint satisfies FR-16 as written; this panel is the endpoint
 * made visible, not a requirement being met.
 *
 * --- The three rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (the `CancellationRequestsPanel` idiom). This mounts
 *    only for an ADMIN, but the real boundary is the server: `GET /audit-entries` is
 *    `require_role(ADMIN)` and a non-Admin gets a `403 ACTION_NOT_PERMITTED`, decided before any row
 *    is read (G3). Hiding the panel is a convenience.
 * 2. The client computes NOTHING (AD-2). `occurred_at` is rendered exactly as received — the
 *    server's RFC 3339 string — and so are the states. No date parsing, no day-of-week primitive, no
 *    reformatting.
 * 3. A SYSTEM row shows the word SYSTEM, never a name and never a blank. `actor_name` is `null` for
 *    the managerless auto-approval because NO PERSON ACTED, and AC6's promise is that no human
 *    approver is fabricated. A blank cell would read as missing data — as though the system had lost
 *    the approver's name rather than truthfully recording that there was none. So the row renders
 *    `actor_type`, which says SYSTEM, and that is the honest answer.
 */
import { useAuditEntries, useMe } from '../../api'
import type { AuditEntry } from '../../api'

/** The role this screen is for — the one string the mount gate matches on (the `EmployeesPage` idiom). */
const ADMIN_ROLE = 'ADMIN'

/** The `actor_type` that means "no person acted" — the managerless auto-approval (FR-09). */
const SYSTEM_ACTOR = 'SYSTEM'

/**
 * Who acted, as a line of text.
 *
 * For a human: their name. For the system: the literal word SYSTEM — NOT `actor_name`, which is
 * `null` by design and would render as an empty cell that looks like a bug. This is the only place
 * a display string is chosen for a SYSTEM row, and it is chosen HERE, in the view, rather than in
 * the service, precisely so that the absence of a name stays a fact about the data all the way down.
 */
function actorLabel(entry: AuditEntry): string {
  return entry.actor_type === SYSTEM_ACTOR ? SYSTEM_ACTOR : (entry.actor_name ?? SYSTEM_ACTOR)
}

/** The transition, as the server recorded it. `from_state` is `null` for a creation — show its arrival. */
function transitionLabel(entry: AuditEntry): string {
  return entry.from_state === null
    ? `created → ${entry.to_state}`
    : `${entry.from_state} → ${entry.to_state}`
}

export function AuditLogPanel() {
  const me = useMe()
  const isAdmin = me.data?.role === ADMIN_ROLE
  // Gate the fetch on the resolved role: a non-Admin, which renders nothing below, never issues the
  // request the server would refuse with a 403.
  const trail = useAuditEntries({ enabled: isAdmin })

  // The mount gate is a usability measure; the server's 403 is the real guard (AC2).
  if (!isAdmin) {
    return null
  }

  const items = trail.data?.items ?? []

  return (
    <section className="panel">
      <h2>Audit trail</h2>
      <p className="muted">
        Every state transition the system has recorded, newest first — who acted, on what, and when.
        The record is append-only: it cannot be edited or deleted, by anyone, including this screen.
      </p>

      {trail.isLoading && <p className="muted">Loading the audit trail…</p>}
      {trail.isError && (
        <p className="emp-error" role="alert">
          Could not load the audit trail. Try again later.
        </p>
      )}
      {!trail.isLoading && !trail.isError && items.length === 0 && (
        <p className="muted">No transitions have been recorded yet.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((entry: AuditEntry) => (
            <li key={entry.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">{actorLabel(entry)}</span>
                <span className="muted">
                  {entry.subject_type} · {transitionLabel(entry)} · {entry.reason} ·{' '}
                  {entry.occurred_at}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
