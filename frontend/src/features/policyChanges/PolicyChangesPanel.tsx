/**
 * The Admin's Policy Changes screen (Story 2.12, AC12).
 *
 * Implements: FR-06 (frontend), AC12 — "they see each recorded change, its old and new value, and the
 * disposition applied".
 *
 * --- Why this screen exists ---
 *
 * A leave balance is a number an Employee is asked to trust. When an Admin changes policy, every
 * balance in that Leave Type may move — or may deliberately NOT move, under `PRESERVE`. This log is
 * the record of WHY each balance is the number it is: what changed, from what, to what, under which
 * disposition, and when. Without it, a balance that changed overnight has no explanation anyone can
 * retrieve, and PRD §1's governing sentence applies — "a leave balance that is wrong is worse than a
 * leave balance that is absent, because it will be believed."
 *
 * --- The three rules this screen must never break ---
 *
 * 1. NOTHING HERE EDITS A RECORD, and there is nowhere for such a control to go. A policy change is a
 *    historical fact. The application's database role holds `INSERT, SELECT` on `policy_change` and
 *    neither `UPDATE` nor `DELETE` (AD-9, migration `0011`), so an "amend this" button would be
 *    refused by PostgreSQL even if someone added one. Its absence is a requirement, not an oversight.
 * 2. Role gate is USABILITY, never the guard (the `ReviewFlagsPanel`/`AuditLogPanel` idiom — Pattern
 *    B). This mounts only for an ADMIN, but the real boundary is the server: `GET /policy-changes` is
 *    `require_role(ADMIN)` and a non-Admin gets a `403 ACTION_NOT_PERMITTED`, decided before any row
 *    is read (AC8, G3).
 * 3. The client computes NOTHING (AD-2). `occurred_at` is rendered exactly as received — the server's
 *    RFC 3339 string — and so are `attribute`, `disposition`, and `old_value`/`new_value`. Those last
 *    two are STRINGS on the wire (one column pair carries an int, a nullable int and a bool), and a
 *    REMOVED cap arrives as the literal `"null"` — which is meant to read as "no cap" and is
 *    deliberately different from "there never was one". No parsing, no reformatting, no guessing.
 */
import { useMe, usePolicyChanges } from '../../api'
import type { PolicyChange } from '../../api'

/** The role this screen is for — the one string the mount gate matches on (the `AuditLogPanel` idiom). */
const ADMIN_ROLE = 'ADMIN'

export function PolicyChangesPanel() {
  const me = useMe()
  const isAdmin = me.data?.role === ADMIN_ROLE
  // Gate the fetch on the resolved role: a non-Admin, which renders nothing below, never issues the
  // request the server would refuse with a 403.
  const changes = usePolicyChanges({ enabled: isAdmin })

  // The mount gate is a usability measure; the server's 403 is the real guard (AC8).
  if (!isAdmin) {
    return null
  }

  const items = changes.data?.items ?? []

  return (
    <section className="panel">
      <h2>Policy changes</h2>
      <p className="muted">
        Every change to a leave type&rsquo;s policy, and what was done with the balances that already
        existed. <strong>Recalculate</strong> re-derived them under the new policy;{' '}
        <strong>Preserve</strong> left them as they were accrued, so only future accruals use the new
        value. The record is permanent: nothing here amends a change.
      </p>

      {changes.isLoading && <p className="muted">Loading policy changes…</p>}
      {changes.isError && (
        <p className="emp-error" role="alert">
          Could not load the policy changes. Try again later.
        </p>
      )}
      {!changes.isLoading && !changes.isError && items.length === 0 && (
        <p className="muted">
          No leave policy has been changed. Every balance still reflects the policy its leave type was
          created with.
        </p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((change: PolicyChange) => (
            <li key={change.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {change.leave_type_code} · {change.attribute}
                </span>
                <span className="muted">
                  {change.old_value} → {change.new_value}
                </span>
                <span className="emp-inactive">
                  {change.disposition} · {change.occurred_at}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
