/**
 * The Request panel (Story 2.5 preview → Story 2.6 submission).
 *
 * Implements: FR-08 (frontend), UJ-1 (a range containing a Company Holiday resolves to a day count
 * SMALLER than the picked span, and the excluded holiday is NAMED on screen — never silently netted
 * out). The Employee picks a Leave Type and a range, sees what the request would cost (preview),
 * and then SUBMITS it — after which their Available balance falls immediately (AC8) and the returned
 * status/day-count is shown. A refusal STATES ITS NUMBERS (AC8): the server's `details` figures are
 * rendered, because "not enough balance" is not an actionable answer on its own.
 *
 * --- The one rule this screen must never break (AD-2 / AC12) ---
 *
 * The client computes NOTHING. `leave_days`, `available_before`, `available_after` and the
 * submitted `status`/`leave_days` are rendered AS-IS; the excluded dates, their reasons and each
 * holiday name are displayed as received. There is no day-of-week primitive, no weekday arithmetic,
 * no holiday-set logic — `test_frontend_no_client_day_count.py` stays green. Matching
 * `reason === 'HOLIDAY'` is a display branch on a server-provided string, restated ONCE here as
 * `LeaveTypesPage` restates its codes (the vocabulary guard scans `app/`/`seed/`, not `frontend/`).
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useLeaveTypes, usePreviewLeaveRequest, useSubmitLeaveRequest } from '../../api'

/** The one reason string this screen matches on to name a holiday. Displayed, never computed. */
const HOLIDAY_REASON = 'HOLIDAY'

const EMPTY_FORM = {
  leave_type_id: '',
  start_date: '',
  end_date: '',
}

/** Render a refusal's numbers (AC8). `ApiError.details` carries the actionable figures the prose
 *  message omits — `days_requested`/`days_available`, the crossed `boundary`, etc. Displayed as
 *  received; the client never derives them. */
function RefusalDetails({ error }: { error: Error }) {
  if (!(error instanceof ApiError)) {
    return (
      <p className="emp-error" role="alert">
        {error.message}
      </p>
    )
  }
  const entries = Object.entries(error.details)
  return (
    <div className="emp-error" role="alert">
      <p>{error.message}</p>
      {entries.length > 0 && (
        <ul className="request-refusal-details">
          {entries.map(([key, value]) => (
            <li key={key}>
              {key.replace(/_/g, ' ')}: <strong>{String(value)}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function RequestPreviewPanel() {
  const leaveTypes = useLeaveTypes()
  const preview = usePreviewLeaveRequest()
  const submit = useSubmitLeaveRequest()

  const [form, setForm] = useState({ ...EMPTY_FORM })

  function updateField(field: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
    // Editing any input invalidates the last preview AND the last submission result: clear them so
    // the shown cost/outcome never describes inputs the user has since changed (code review
    // 2026-07-13). The whole point of this screen is to show the state OF THE CURRENT REQUEST.
    if (preview.data !== undefined || preview.isError) preview.reset()
    if (submit.data !== undefined || submit.isError) submit.reset()
  }

  const requiredFilled =
    form.leave_type_id !== '' && form.start_date !== '' && form.end_date !== ''

  function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // The server is the validator; guard only that the required fields are present before the call.
    if (!requiredFilled) return
    preview.mutate({
      leave_type_id: form.leave_type_id,
      start_date: form.start_date,
      end_date: form.end_date,
    })
  }

  function handleSubmit() {
    if (!requiredFilled) return
    submit.mutate(
      {
        leave_type_id: form.leave_type_id,
        start_date: form.start_date,
        end_date: form.end_date,
      },
      {
        // Once the request is reserved, the previewed `available_after` is stale — it predates the
        // reservation and now understates it. Clear the preview so the screen shows only the
        // submitted outcome, never a cost figure the submission has already overtaken (code review
        // 2026-07-13).
        onSuccess: () => {
          if (preview.data !== undefined || preview.isError) preview.reset()
        },
      },
    )
  }

  const result = preview.data
  const submitted = submit.data
  const leaveTypeItems = leaveTypes.data?.items ?? []
  // The select cannot offer a usable choice while leave types are loading, errored, or empty —
  // surface why rather than presenting a form that can never be submitted (code review 2026-07-13).
  const leaveTypesUnavailable =
    leaveTypes.isLoading || leaveTypes.isError || leaveTypeItems.length === 0

  return (
    <section className="panel">
      <h2>Request Leave</h2>
      <p className="muted">
        See what a request will cost — the day count, the projected balance, and which picked days
        are excluded — then submit it. Your balance updates the moment it is reserved.
      </p>

      <form className="emp-create" onSubmit={handlePreview}>
        <div className="emp-fields">
          <label className="emp-field">
            Leave type
            <select
              value={form.leave_type_id}
              onChange={(event) => updateField('leave_type_id', event.target.value)}
              disabled={leaveTypesUnavailable}
              required
            >
              <option value="">Select a leave type…</option>
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
            Start date
            <input
              type="date"
              value={form.start_date}
              onChange={(event) => updateField('start_date', event.target.value)}
              required
            />
          </label>
          <label className="emp-field">
            End date
            <input
              type="date"
              value={form.end_date}
              onChange={(event) => updateField('end_date', event.target.value)}
              required
            />
          </label>
        </div>
        <div className="emp-form-actions">
          <button type="submit" disabled={preview.isPending || leaveTypesUnavailable}>
            {preview.isPending ? 'Previewing…' : 'Preview'}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submit.isPending || leaveTypesUnavailable || !requiredFilled}
          >
            {submit.isPending ? 'Submitting…' : 'Submit request'}
          </button>
          {preview.isError && (
            <p className="emp-error" role="alert">
              {preview.error.message}
            </p>
          )}
        </div>
      </form>

      {submit.isError && <RefusalDetails error={submit.error} />}

      {submitted && (
        <div className="request-submitted" role="status">
          <p>
            Request submitted for <strong>{submitted.leave_days}</strong> leave{' '}
            {submitted.leave_days === 1 ? 'day' : 'days'} — status{' '}
            <strong>{submitted.status}</strong>.
          </p>
        </div>
      )}

      {result && (
        <div className="preview-result">
          <div className="preview-days">
            <span className="preview-days-value">{result.leave_days}</span>
            <span className="muted">leave days</span>
          </div>
          <p className="preview-balance">
            Balance: <strong>{result.available_before}</strong> →{' '}
            <strong>{result.available_after}</strong> after this request
          </p>

          {result.excluded_dates.length > 0 && (
            <>
              <p className="muted">
                These picked days cost no leave and are excluded from the count:
              </p>
              <ul className="preview-excluded">
                {result.excluded_dates.map((excluded) => (
                  <li key={excluded.date}>
                    <span className="preview-excluded-date">{excluded.date}</span>
                    <span className="muted">
                      {excluded.reason === HOLIDAY_REASON ? excluded.name : 'Weekend'}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}
