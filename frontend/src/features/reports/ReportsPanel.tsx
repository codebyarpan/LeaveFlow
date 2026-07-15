/**
 * The leave report screen (Story 4.2, FR-15): filters, the on-screen list, and the CSV export.
 *
 * Implements: AC5 (frontend) — a Manager or an Admin applies filters and exports exactly what
 * they see. "What they see" is the FILTER SET, not the page (Open Decision #4 / Landmine 9):
 * the on-screen list below is paged (the existing `GET /leave-requests`, whose Manager scope is
 * reports-only — the same scope the export applies, so screen and export agree there too),
 * while the export carries EVERY row matching those same filters. Both build their query from
 * the one shared `FILTER_PARAM_NAMES` map, so they cannot disagree on a wire name — that IS the
 * AC. No charts, no aggregates (SM-C2): these are exports, not analytics.
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (NFR-16, the house idiom). This mounts only for a
 *    MANAGER or an ADMIN; the real boundary is the server's `require_role` 403 on the export
 *    and the scope predicate on both reads.
 * 2. The client computes NOTHING about days (AD-2, AD-18). Every figure and date is rendered as
 *    received; the CSV bytes are handed to the browser untouched. No day-of-week primitive, no
 *    day-count arithmetic — `test_frontend_no_client_day_count.py` scans this file too.
 */
import { useEffect, useState } from 'react'

import {
  ApiError,
  fetchLeaveReportCsv,
  useLeaveRequests,
  useLeaveTypes,
  useMe,
} from '../../api'
import type { LeaveRequest, LeaveRequestFilters } from '../../api'
import { Pager } from '../../components/Pager'

/** The two roles this screen serves — the strings the mount gate matches on (the house idiom). */
const MANAGER_ROLE = 'MANAGER'
const ADMIN_ROLE = 'ADMIN'

/**
 * The four wire states, offered as filter choices and sent as received (AD-2). The backend's
 * vocabulary guard scans only `app/`; the frontend may state these (MyLeaveHistoryPanel
 * precedent — a known, accepted deferral, deferred-work.md).
 */
const STATUS_OPTIONS = ['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'] as const

/** Rows per on-screen page (the MyLeaveHistoryPanel size; the server clamps regardless). */
const REPORT_PAGE_SIZE = 10

/** The filter form's state: `''` means "no filter" for every field (the empty select/input). */
interface ReportFilterForm {
  leaveTypeId: string
  status: string
  dateFrom: string
  dateTo: string
}

const EMPTY_FILTERS: ReportFilterForm = {
  leaveTypeId: '',
  status: '',
  dateFrom: '',
  dateTo: '',
}

/** An empty form field is an ABSENT wire param — the server applies no predicate for it. */
function toFilters(form: ReportFilterForm): LeaveRequestFilters {
  return {
    status: form.status === '' ? undefined : form.status,
    leaveTypeId: form.leaveTypeId === '' ? undefined : form.leaveTypeId,
    dateFrom: form.dateFrom === '' ? undefined : form.dateFrom,
    dateTo: form.dateTo === '' ? undefined : form.dateTo,
  }
}

export function ReportsPanel() {
  const me = useMe()
  const role = me.data?.role
  const canReport = role === MANAGER_ROLE || role === ADMIN_ROLE

  const [form, setForm] = useState<ReportFilterForm>(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  // Gate both fetches on the resolved role (the house idiom): a non-Manager/-Admin, which
  // renders nothing below, never issues either request.
  const list = useLeaveRequests(
    { ...toFilters(form), page, pageSize: REPORT_PAGE_SIZE },
    { enabled: canReport },
  )
  const leaveTypes = useLeaveTypes({ enabled: canReport })

  // Clamp when the result set shrinks under us (code review 2026-07-15, the MyLeaveHistoryPanel
  // idiom): a background refetch that drops `total` (a decision elsewhere invalidates the shared
  // query; window focus refetches) would strand this panel past the last page — an empty page
  // captioned "Page 2 of 1". Gated on data presence: a still-loading page has no `total`.
  const knownTotal = list.data?.total
  const knownPageSize = list.data?.page_size ?? REPORT_PAGE_SIZE
  useEffect(() => {
    if (knownTotal === undefined) return
    const lastPage = Math.max(1, Math.ceil(knownTotal / knownPageSize))
    setPage((current) => Math.min(current, lastPage))
  }, [knownTotal, knownPageSize])

  // The mount gate is a usability measure (NFR-16); the server's 403 is the real guard.
  if (!canReport) {
    return null
  }

  // Changing any filter starts over at page 1 — page N of the OLD filter combination is
  // meaningless under the new one. The export ignores pages entirely (FR-15 binds filters).
  function updateFilter(field: keyof ReportFilterForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
    setPage(1)
  }

  /**
   * Download the CSV under the CURRENT filter set — every matching row, not the visible page
   * (Landmine 9; the pinned page-boundary reading). Imperative, like 4.1's document view: the
   * blob becomes an object URL handed to an `<a download>`, then revoked on a delay so the
   * browser's handoff is never raced. A failure states its reason inline (NFR-17).
   */
  async function exportCsv() {
    setExporting(true)
    setExportError(null)
    try {
      const blob = await fetchLeaveReportCsv(toFilters(form))
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'leave.csv'
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (error) {
      setExportError(
        error instanceof ApiError
          ? `Could not export: ${error.message}`
          : 'Could not export. Try again later.',
      )
    } finally {
      setExporting(false)
    }
  }

  const items = list.data?.items ?? []
  const total = list.data?.total ?? 0
  const pageSize = list.data?.page_size ?? REPORT_PAGE_SIZE
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  const leaveTypeItems = leaveTypes.data?.items ?? []
  const leaveTypesUnavailable =
    leaveTypes.isLoading || leaveTypes.isError || leaveTypeItems.length === 0

  return (
    <section className="panel">
      <h2>Leave report</h2>
      <p className="muted">
        {role === ADMIN_ROLE
          ? 'Every employee’s leave, filterable and exportable as CSV.'
          : 'Your direct reports’ leave (not your own), filterable and exportable as CSV.'}{' '}
        The export honors the filters below and carries every matching row — the list shows one
        page of the same rows. Each figure is the server&apos;s; nothing is computed here.
      </p>

      <div className="emp-fields">
        <label className="emp-field">
          Leave type
          <select
            value={form.leaveTypeId}
            onChange={(event) => updateFilter('leaveTypeId', event.target.value)}
            disabled={leaveTypesUnavailable}
          >
            <option value="">All types</option>
            {leaveTypeItems.map((leaveType) => (
              <option key={leaveType.id} value={leaveType.id}>
                {leaveType.code} · {leaveType.name}
              </option>
            ))}
          </select>
          {leaveTypesUnavailable && (
            <span className="muted">
              {leaveTypes.isLoading
                ? 'Loading leave types…'
                : leaveTypes.isError
                  ? 'Could not load leave types. Try again later.'
                  : 'No leave types are configured yet.'}
            </span>
          )}
        </label>
        <label className="emp-field">
          State
          <select
            value={form.status}
            onChange={(event) => updateFilter('status', event.target.value)}
          >
            <option value="">All states</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
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

      <div className="emp-fields">
        <button type="button" onClick={() => void exportCsv()} disabled={exporting}>
          {exporting ? 'Exporting…' : 'Export CSV'}
        </button>
        {exportError !== null && (
          <p className="emp-error" role="alert">
            {exportError}
          </p>
        )}
      </div>

      {list.isLoading && <p className="muted">Loading the report…</p>}
      {list.isError && (
        <p className="emp-error" role="alert">
          Could not load the report. Try again later.
        </p>
      )}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <p className="muted">No requests match — adjust the filters, or none exist yet.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((request: LeaveRequest) => (
            <li key={request.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {request.employee_name} · {request.leave_type_code} ·{' '}
                  {request.leave_type_name}
                </span>
                <span className="muted">
                  {request.start_date} → {request.end_date} · {request.leave_days}{' '}
                  {request.leave_days === 1 ? 'day' : 'days'} · {request.status}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Pager
        page={page}
        pageCount={pageCount}
        total={total}
        noun="request"
        disabled={list.isLoading}
        onPrev={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
      />
    </section>
  )
}
