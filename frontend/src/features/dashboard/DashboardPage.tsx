/**
 * The Employee dashboard (Story 2.4, AC7 — EXTENDED by Story 3.5, AC1/AC6).
 *
 * Implements: FR-07/FR-11 (frontend) — for each Leave Type, Available is shown PROMINENTLY,
 * with Reserved and Consumed disclosed alongside, plus a count of the caller's own Pending
 * requests and a date-range filter. Renders for EVERY authenticated user, deliberately without
 * a role gate: `/dashboard/employee` is role `any`, scope `self` — a Manager here sees THEIR
 * OWN balances, never a report's (AC5).
 *
 * --- The one rule this screen must never break (AD-2) ---
 *
 * The client computes NO day count and NO balance figure: every number arrives from the server
 * as a whole-day integer and is rendered AS-IS. `available` is already derived server-side
 * (`accrued − consumed − reserved`); `leave_year` is the server's, not `new Date()`'s. The
 * `test_frontend_no_client_day_count.py` guard (Story 2.3) stays green.
 *
 * The date range narrows the PENDING COUNT only — balances are the current Leave Year, always,
 * and are never date-filtered (a balance row has no dates; Story 3.5's Decision #2). The empty
 * field is an ABSENT wire param, never `date_from=` (the MyLeaveHistoryPanel translation).
 */
import { useState } from 'react'

import { useEmployeeDashboard } from '../../api'
import type { DashboardParams } from '../../api'

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

export function DashboardPage() {
  const [form, setForm] = useState<DashboardFilterForm>(EMPTY_FILTERS)
  const dashboard = useEmployeeDashboard(toParams(form))

  function updateFilter(field: keyof DashboardFilterForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const balances = dashboard.data?.balances ?? []

  return (
    <section className="panel">
      <h2>My dashboard</h2>
      <p className="muted">
        Your balances for the current leave year, and your requests still awaiting a decision.
        Available is what remains after committed and spent leave. The date range narrows the
        pending count; balances always show the whole year.
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

      {dashboard.isPending && <p className="muted">Loading your dashboard…</p>}

      {dashboard.isError && (
        <p className="emp-error" role="alert">
          Could not load your dashboard — {dashboard.error.message}
        </p>
      )}

      {dashboard.data && (
        <>
          <div className="emp-fields">
            <section className="panel">
              <div className="balance-available">
                <span className="balance-available-value">
                  {dashboard.data.pending_request_count}
                </span>
                <span className="muted">pending requests</span>
              </div>
              <p className="muted">
                {form.dateFrom === '' && form.dateTo === ''
                  ? 'All of your requests awaiting a decision.'
                  : 'Your pending requests touching the selected range.'}
              </p>
            </section>
          </div>

          <p className="muted">Leave year {dashboard.data.leave_year}</p>

          {balances.length === 0 && <p className="muted">No leave balances yet.</p>}

          {balances.length > 0 && (
            <ul className="emp-list">
              {balances.map((balance) => (
                <li key={balance.leave_type_code} className="emp-row">
                  <div className="emp-summary">
                    <span className="emp-name">
                      {balance.leave_type_code} · {balance.leave_type_name}
                    </span>
                    <span className="muted">
                      Reserved {balance.reserved} · Consumed {balance.consumed}
                    </span>
                  </div>
                  <div className="balance-available">
                    <span className="balance-available-value">{balance.available}</span>
                    <span className="muted">available</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
