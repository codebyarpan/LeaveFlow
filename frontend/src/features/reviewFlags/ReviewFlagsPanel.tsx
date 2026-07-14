/**
 * The Admin's Review Flags screen (Story 2.11, AC9). NOT optional — this one is an acceptance
 * criterion.
 *
 * Implements: FR-10 (frontend), AC9 — "they see every recorded refusal with its cause, the Employee
 * and Leave Type it left unchanged, and when it occurred; and no control clears a flag".
 *
 * --- Why this screen exists at all, and why cutting it would defeat the story ---
 *
 * PRD §1: "a leave balance that is wrong is worse than a leave balance that is absent, because it
 * will be believed." When a holiday change cannot be applied to somebody's balance, the system
 * leaves that balance ALONE and records a flag (AD-19) — which means there is now a balance in the
 * database that is known to be stale. A refusal recorded where nobody looks is exactly the wrong
 * figure that will be believed. The readiness report (F-7) made this an AC for precisely that
 * reason: "An Admin adds a holiday. The response is 200. Three Employees' balances were silently
 * left unchanged … The Admin is told nothing, and no screen exists to read the flags."
 *
 * So: this screen, and the summary on the Holidays screen (AC8). One is the permanent record, the
 * other is the immediate telling.
 *
 * --- The three rules this screen must never break ---
 *
 * 1. NO CONTROL CLEARS A FLAG, and there is nowhere for one to go. `FR-10` grants the Admin a READ;
 *    no requirement grants a resolve. There is no `resolved_at` column (ERD GAP-4: "The undefined
 *    behavior is gone because the behavior no longer exists"), no `PATCH`/`DELETE` route, and the
 *    application's database role holds `INSERT, SELECT` on `admin_review_flag` and neither `UPDATE`
 *    nor `DELETE` (AD-20) — so a "Resolve" button would be refused by PostgreSQL even if someone
 *    added it. Its absence here is a requirement, not an oversight.
 * 2. Role gate is USABILITY, never the guard (the `AuditLogPanel` idiom). This mounts only for an
 *    ADMIN, but the real boundary is the server: `GET /admin-review-flags` is `require_role(ADMIN)`
 *    and a non-Admin gets a `403 ACTION_NOT_PERMITTED`, decided before any row is read (AC7, G3).
 * 3. The client computes NOTHING (AD-2). `occurred_at` is rendered exactly as received — the
 *    server's RFC 3339 string — and so are `cause`, `leave_year` and the Leave Type code. No date
 *    parsing, no day-of-week primitive, no reformatting.
 */
import { useAdminReviewFlags, useMe } from '../../api'
import type { AdminReviewFlag } from '../../api'

/** The role this screen is for — the one string the mount gate matches on (the `AuditLogPanel` idiom). */
const ADMIN_ROLE = 'ADMIN'

export function ReviewFlagsPanel() {
  const me = useMe()
  const isAdmin = me.data?.role === ADMIN_ROLE
  // Gate the fetch on the resolved role: a non-Admin, which renders nothing below, never issues the
  // request the server would refuse with a 403.
  const flags = useAdminReviewFlags({ enabled: isAdmin })

  // The mount gate is a usability measure; the server's 403 is the real guard (AC7).
  if (!isAdmin) {
    return null
  }

  const items = flags.data?.items ?? []

  return (
    <section className="panel">
      <h2>Review flags</h2>
      <p className="muted">
        Recalculations the system refused to perform. Each one names a balance that was left
        unchanged because correcting it would have driven that Leave Year negative — so the figure
        recorded against it is known to be out of date, and someone has to decide what to do about
        it. The record is permanent: nothing here clears a flag.
      </p>

      {flags.isLoading && <p className="muted">Loading review flags…</p>}
      {flags.isError && (
        <p className="emp-error" role="alert">
          Could not load the review flags. Try again later.
        </p>
      )}
      {!flags.isLoading && !flags.isError && items.length === 0 && (
        <p className="muted">
          No recalculation has been refused. Every holiday change so far has been applied in full.
        </p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((flag: AdminReviewFlag) => (
            <li key={flag.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {flag.employee_name} · {flag.leave_type_code}
                </span>
                <span className="emp-inactive">
                  Left unchanged for {flag.leave_year} · {flag.cause} · {flag.occurred_at}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
