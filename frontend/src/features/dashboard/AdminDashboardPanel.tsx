/**
 * The Admin dashboard (Story 3.5, AC3/AC6) — the organization at a glance.
 *
 * Implements: FR-11 (frontend) — organization-wide totals: Employees on approved leave (the
 * server's default window: today) and the Pending request count. Summary cards with a
 * date-range filter; no chart, no trend line (PRD §7.4, SM-C2).
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (the MyTeamPanel idiom). This mounts only for
 *    an ADMIN, and the query is `enabled`-gated so a non-Admin never issues a request that
 *    is guaranteed to 403. The server's role gate is the real boundary.
 * 2. The client computes NOTHING (AD-2). Both figures arrive from the server — "Employees on
 *    approved leave" is the server's DISTINCT count of PEOPLE, and the pending count is LEAVE
 *    Requests only (a pending Cancellation Request is deliberately not in it; the Admin's CR
 *    queue below is that surface). The window label derives from the ECHOED
 *    `leave_window_from`/`leave_window_to`, never a hard-coded "today" string.
 */
import { useState } from 'react'

import { useAdminDashboard, useMe } from '../../api'
import type { DashboardParams } from '../../api'

import { describeWindow } from './describeWindow'

/** The role this panel is for — the one string the mount gate matches on (the 2.7 idiom). */
const ADMIN_ROLE = 'ADMIN'

/** The filter form's state: `''` means "no filter" for both fields (the empty date input). */
interface DashboardFilterForm {
  dateFrom: string
  dateTo: string
}

const EMPTY_FILTERS: DashboardFilterForm = { dateFrom: '', dateTo: '' }

/** An empty form field is an ABSENT wire param — the server applies no predicate for it. */
function toParams(form: DashboardFilterForm): DashboardParams {
  return {
    dateFrom: form.dateFrom === '' ? undefined : form.dateFrom,
    dateTo: form.dateTo === '' ? undefined : form.dateTo,
  }
}

export function AdminDashboardPanel() {
  const me = useMe()
  const isAdmin = me.data?.role === ADMIN_ROLE
  const [form, setForm] = useState<DashboardFilterForm>(EMPTY_FILTERS)

  // Gate the fetch on the resolved role (the MyTeamPanel idiom): a non-Admin, which renders
  // nothing below, never issues the request at all.
  const dashboard = useAdminDashboard(toParams(form), { enabled: isAdmin })

  // The mount gate is a usability measure; the server's 403 (require_role ADMIN) is the
  // real guard.
  if (!isAdmin) {
    return null
  }

  function updateFilter(field: keyof DashboardFilterForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  return (
    <section className="panel">
      <h2>Organization dashboard</h2>
      <p className="muted">
        Organization-wide totals: who is on approved leave, and how many requests await a
        decision. Leave a date empty to use the server&apos;s window — today.
      </p>

      <div className="emp-fields">
        <label className="emp-field">
          From
          <input
            type="date"
            value={form.dateFrom}
            onChange={(event) => updateFilter('dateFrom', event.target.value)}
          />
        </label>
        <label className="emp-field">
          To
          <input
            type="date"
            value={form.dateTo}
            onChange={(event) => updateFilter('dateTo', event.target.value)}
          />
        </label>
      </div>

      {dashboard.isLoading && <p className="muted">Loading the organization dashboard…</p>}

      {dashboard.isError && (
        <p className="emp-error" role="alert">
          Could not load the organization dashboard — {dashboard.error.message}
        </p>
      )}

      {dashboard.data && (
        <div className="emp-fields">
          <section className="panel">
            <div className="balance-available">
              <span className="balance-available-value">
                {dashboard.data.employees_on_approved_leave}
              </span>
              <span className="muted">
                employees on approved leave,{' '}
                {describeWindow(
                  dashboard.data.leave_window_from,
                  dashboard.data.leave_window_to,
                )}
              </span>
            </div>
          </section>

          <section className="panel">
            <div className="balance-available">
              <span className="balance-available-value">
                {dashboard.data.pending_request_count}
              </span>
              <span className="muted">pending leave requests</span>
            </div>
            <p className="muted">
              {form.dateFrom === '' && form.dateTo === ''
                ? 'All requests awaiting a decision, organization-wide.'
                : 'Pending requests touching the selected range.'}
            </p>
          </section>
        </div>
      )}
    </section>
  )
}
