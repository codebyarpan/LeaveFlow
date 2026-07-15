/**
 * The Manager dashboard (Story 3.5, AC2/AC6) — what is waiting for my decision, and who is
 * away.
 *
 * Implements: FR-11 (frontend) — a count of Leave Requests awaiting the caller's decision,
 * and their Direct Reports on approved leave (the server's default window: the next seven
 * days). Summary cards with a date-range filter; no chart, no trend line (PRD §7.4, SM-C2).
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (the MyTeamPanel idiom). This mounts only for a
 *    MANAGER, and the query is `enabled`-gated so a non-Manager never issues a request that
 *    is guaranteed to 403 — `/dashboard/manager` is Manager-ONLY server-side (§4.9): the
 *    ADMIN is refused alongside the Employee. The server's role gate is the real boundary.
 * 2. The client computes NOTHING (AD-2/AD-18). Both figures and the people list arrive from
 *    the server; the window label derives from the ECHOED `leave_window_from`/`leave_window_to`
 *    — never a hard-coded "next 7 days" string (which would lie the moment a range is
 *    supplied) and never client date arithmetic (`today + 7` is a server decision).
 */
import { useState } from 'react'

import { useManagerDashboard, useMe } from '../../api'
import type { DashboardParams } from '../../api'

import { describeWindow } from './describeWindow'

/** The role this panel is for — the one string the mount gate matches on (the 2.7 idiom). */
const MANAGER_ROLE = 'MANAGER'

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

export function ManagerDashboardPanel() {
  const me = useMe()
  const isManager = me.data?.role === MANAGER_ROLE
  const [form, setForm] = useState<DashboardFilterForm>(EMPTY_FILTERS)

  // Gate the fetch on the resolved role (the MyTeamPanel idiom): a non-Manager, which
  // renders nothing below, never issues the request at all.
  const dashboard = useManagerDashboard(toParams(form), { enabled: isManager })

  // The mount gate is a usability measure; the server's 403 (require_role MANAGER) and the
  // REPORTS scope predicate are the real guards.
  if (!isManager) {
    return null
  }

  function updateFilter(field: keyof DashboardFilterForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const reports = dashboard.data?.reports_on_approved_leave ?? []

  return (
    <section className="panel">
      <h2>My team dashboard</h2>
      <p className="muted">
        Requests awaiting your decision, and which of your direct reports are on approved
        leave. Leave a date empty to use the server&apos;s window — the next seven days.
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

      {dashboard.isLoading && <p className="muted">Loading your team dashboard…</p>}

      {dashboard.isError && (
        <p className="emp-error" role="alert">
          Could not load your team dashboard — {dashboard.error.message}
        </p>
      )}

      {dashboard.data && (
        <div className="emp-fields">
          <section className="panel">
            <div className="balance-available">
              <span className="balance-available-value">
                {dashboard.data.pending_decision_count}
              </span>
              <span className="muted">awaiting your decision</span>
            </div>
            <p className="muted">
              {form.dateFrom === '' && form.dateTo === ''
                ? 'All pending requests from your reports.'
                : 'Pending requests touching the selected range.'}
            </p>
          </section>

          <section className="panel">
            <div className="balance-available">
              {/* The SERVER's DISTINCT people-count, never `reports.length` — the list below
                  is server-capped, so its length silently understates past the cap (AD-2). */}
              <span className="balance-available-value">
                {dashboard.data.reports_on_leave_count}
              </span>
              <span className="muted">
                on approved leave,{' '}
                {describeWindow(
                  dashboard.data.leave_window_from,
                  dashboard.data.leave_window_to,
                )}
              </span>
            </div>
            {reports.length === 0 && (
              <p className="muted">None of your reports are on approved leave.</p>
            )}
            {reports.length > 0 && (
              <ul className="emp-list">
                {reports.map((report) => (
                  <li key={report.employee_id}>{report.full_name}</li>
                ))}
                {dashboard.data.reports_on_leave_count > reports.length && (
                  <li className="muted">
                    …and {dashboard.data.reports_on_leave_count - reports.length} more
                  </li>
                )}
              </ul>
            )}
          </section>
        </div>
      )}
    </section>
  )
}
