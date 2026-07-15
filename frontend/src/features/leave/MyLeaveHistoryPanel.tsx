/**
 * The Employee's leave history (Story 3.1, AC7) — and the app's FIRST pagination UI.
 *
 * Implements: FR-12/FR-20 (frontend) — a plain Employee sees every Leave Request they have ever
 * made, across every Leave Year and in every state (CANCELLED and REJECTED included), filters it
 * by type, state and date range, and pages through the results. The filters compose SERVER-side
 * as an intersection; this screen only chooses them. The envelope (`items`/`page`/`page_size`/
 * `total`) has carried a page count since Story 1.5 — this is the first component to read it.
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (Open Decision #4, the 2.8 precedent). This mounts
 *    only for a plain EMPLOYEE: a Manager's `GET /leave-requests` returns their REPORTS' requests
 *    — never their own (the keep-REPORTS ruling) — and an Admin's returns everyone's, so "My
 *    leave history" would be a false label for either. Manager/Admin own-history stays API-absent
 *    by the standing 2.7 ruling. The real boundary is the server's scope predicate.
 * 2. The client computes NOTHING about days (AD-2, AD-18). `leave_days`, the dates and the status
 *    are rendered AS RECEIVED — no day-of-week primitive, no day-count arithmetic
 *    (`test_frontend_no_client_day_count.py` stays green; those tokens must never appear, not
 *    even in a comment). The only arithmetic here is the pager's page count over the server's
 *    `total` and `page_size`, which is pagination, not calendar math.
 */
import { useEffect, useState } from 'react'

import { ApiError, uploadDocument, useLeaveRequests, useLeaveTypes, useMe } from '../../api'
import type { LeaveRequest, LeaveRequestFilters } from '../../api'
import { Pager } from '../../components/Pager'
import {
  DOCUMENT_ACCEPTED_TYPES,
  DOCUMENT_MAX_BYTES,
} from './documentPolicy'

/** The role this panel is for — the one string the mount gate matches on (the 2.8 precedent). */
const EMPLOYEE_ROLE = 'EMPLOYEE'

/** The one state whose evidence is still writable (OD#2: a decided request's is frozen). */
const PENDING_STATUS = 'PENDING'

/**
 * The four wire states, offered as filter choices and sent as received (AD-2). The backend's
 * vocabulary guard scans only `app/`; the frontend may state these (ManagerQueuePanel precedent).
 */
const STATUS_OPTIONS = ['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'] as const

/**
 * Rows per history page. A deliberate small page (not the server default of 50) so the pager —
 * the reason this panel exists — is exercised by realistic data volumes; the server clamps
 * whatever is asked of it (NFR-11).
 */
const HISTORY_PAGE_SIZE = 10

/** The filter form's state: `''` means "no filter" for every field (the empty select/input). */
interface HistoryFilterForm {
  leaveTypeId: string
  status: string
  dateFrom: string
  dateTo: string
}

const EMPTY_FILTERS: HistoryFilterForm = {
  leaveTypeId: '',
  status: '',
  dateFrom: '',
  dateTo: '',
}

/**
 * Per-PENDING-row attach/replace (Story 4.1 OD#2; wired by the 2026-07-15 code review — the
 * standalone `POST /leave-requests/{id}/document` shipped with no caller, leaving the Employee
 * whose request predates a type's flag flip, or who picked the wrong file, with no way to attach
 * evidence). Imperative like the Manager's ViewDocumentButton: pick a file, it uploads. The
 * pre-check only STATES REASONS early (NFR-17); the server stays the guard — a request decided
 * in the meantime refuses with `409 TRANSITION_NOT_ALLOWED` (its evidence is frozen), a rejected
 * file with its 400 code. The native input remounts after every outcome so its filename display
 * never claims a file this control no longer holds. Zero new CSS (`emp-field`/`muted`/`emp-error`).
 */
function AttachDocumentControl({ requestId }: { requestId: string }) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [inputEpoch, setInputEpoch] = useState(0)

  async function attach(file: File | null) {
    if (file === null) return
    setInputEpoch((current) => current + 1)
    if (!DOCUMENT_ACCEPTED_TYPES.includes(file.type)) {
      setFailed(true)
      setNote('That file type is not accepted — upload a PDF, JPG or PNG.')
      return
    }
    if (file.size > DOCUMENT_MAX_BYTES) {
      setFailed(true)
      setNote('That file is larger than the 5 MB limit.')
      return
    }
    setBusy(true)
    setNote(null)
    setFailed(false)
    try {
      const result = await uploadDocument(requestId, file)
      setNote(`Document attached: ${result.original_filename}`)
    } catch (error) {
      setFailed(true)
      if (error instanceof ApiError && error.code === 'TRANSITION_NOT_ALLOWED') {
        setNote('This request was decided in the meantime — its evidence is frozen.')
      } else if (error instanceof ApiError && error.status === 404) {
        setNote('This request is no longer available to you.')
      } else if (error instanceof ApiError) {
        setNote(error.message)
      } else {
        setNote('Could not upload the document. Try again later.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <label className="emp-field">
      <span className="muted">
        {busy ? 'Uploading…' : 'Attach or replace document (PDF, JPG or PNG, up to 5 MB)'}
      </span>
      <input
        key={inputEpoch}
        type="file"
        accept={DOCUMENT_ACCEPTED_TYPES.join(',')}
        disabled={busy}
        onChange={(event) => void attach(event.target.files?.[0] ?? null)}
      />
      {note !== null && (
        <span className={failed ? 'emp-error' : 'muted'} role={failed ? 'alert' : undefined}>
          {note}
        </span>
      )}
    </label>
  )
}

/** An empty form field is an ABSENT wire param — the server applies no predicate for it. */
function toRequestFilters(form: HistoryFilterForm, page: number): LeaveRequestFilters {
  return {
    status: form.status === '' ? undefined : form.status,
    leaveTypeId: form.leaveTypeId === '' ? undefined : form.leaveTypeId,
    dateFrom: form.dateFrom === '' ? undefined : form.dateFrom,
    dateTo: form.dateTo === '' ? undefined : form.dateTo,
    page,
    pageSize: HISTORY_PAGE_SIZE,
  }
}

export function MyLeaveHistoryPanel() {
  const me = useMe()
  const isEmployee = me.data?.role === EMPLOYEE_ROLE
  const [form, setForm] = useState<HistoryFilterForm>(EMPTY_FILTERS)
  const [page, setPage] = useState(1)

  // Gate both fetches on the resolved role (the RequestCancellationPanel idiom): a non-Employee,
  // which renders nothing below, never issues either request.
  const history = useLeaveRequests(toRequestFilters(form, page), { enabled: isEmployee })
  const leaveTypes = useLeaveTypes({ enabled: isEmployee })

  // Clamp when the result set shrinks under us (code review 2026-07-15): a refetch that drops
  // `total` (a self-cancel shrinking a filtered history) would strand this panel past the last
  // page — an empty page captioned "Page 3 of 1" whose "no requests match" line would be a lie.
  // Gated on data presence: a still-loading page has no `total` to judge by.
  const knownTotal = history.data?.total
  const knownPageSize = history.data?.page_size ?? HISTORY_PAGE_SIZE
  useEffect(() => {
    if (knownTotal === undefined) return
    const lastPage = Math.max(1, Math.ceil(knownTotal / knownPageSize))
    setPage((current) => Math.min(current, lastPage))
  }, [knownTotal, knownPageSize])

  // The mount gate is a usability measure (Open Decision #4); the server's scope is the guard.
  if (!isEmployee) {
    return null
  }

  // Changing any filter starts over at page 1 — page N of the OLD filter combination is
  // meaningless under the new one.
  function updateFilter(field: keyof HistoryFilterForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
    setPage(1)
  }

  const items = history.data?.items ?? []
  const total = history.data?.total ?? 0
  // The page count comes from the server's OWN echo of total and the (clamped) page_size —
  // `Math.max(1, …)` keeps "Page 1 of 1" on an empty result rather than "Page 1 of 0".
  const pageSize = history.data?.page_size ?? HISTORY_PAGE_SIZE
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  const leaveTypeItems = leaveTypes.data?.items ?? []
  // The select cannot offer a usable choice while leave types are loading, errored, or empty —
  // surface why rather than a dead control (the RequestPreviewPanel pattern, code review 2026-07-13).
  const leaveTypesUnavailable =
    leaveTypes.isLoading || leaveTypes.isError || leaveTypeItems.length === 0

  return (
    <section className="panel">
      <h2>My leave history</h2>
      <p className="muted">
        Every request you have ever made — across every leave year, in every state. Filter by
        type, state or date range; a date range matches any request that touches it. Each figure
        is the server&apos;s; nothing is computed here.
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

      {history.isLoading && <p className="muted">Loading your leave history…</p>}
      {history.isError && (
        <p className="emp-error" role="alert">
          Could not load your leave history. Try again later.
        </p>
      )}
      {!history.isLoading && !history.isError && items.length === 0 && (
        <p className="muted">No requests match — adjust the filters, or none exist yet.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((request: LeaveRequest) => (
            <li key={request.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {request.leave_type_code} · {request.leave_type_name}
                </span>
                <span className="muted">
                  {request.start_date} → {request.end_date} · {request.leave_days}{' '}
                  {request.leave_days === 1 ? 'day' : 'days'} · {request.status}
                </span>
              </div>
              {request.status === PENDING_STATUS && (
                <AttachDocumentControl requestId={request.id} />
              )}
            </li>
          ))}
        </ul>
      )}

      {/* The app's first pager — lifted to components/Pager.tsx when its second caller
          (MyTeamPanel, Story 3.2) arrived, per the components/ promotion rule. */}
      <Pager
        page={page}
        pageCount={pageCount}
        total={total}
        noun="request"
        disabled={history.isLoading}
        onPrev={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
      />
    </section>
  )
}
