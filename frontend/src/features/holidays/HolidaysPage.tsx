/**
 * The Company Holidays screen (Story 2.2 AC4/AC10; Story 2.11 AC8).
 *
 * Implements: FR-10 (frontend), AC4 (an Admin adds and deletes holidays for a Leave Year),
 * NFR-16 (the add/delete controls render only for an Admin), NFR-17 (a duplicate-date refusal
 * is shown as a human line), and — since Story 2.11 — AC8: THE ADMIN IS NEVER SHOWN AN
 * UNQUALIFIED SUCCESS FOR AN OPERATION THAT PARTIALLY REFUSED.
 *
 * --- AC8, and why it is the point of the story rather than a nicety ---
 *
 * A holiday change is no longer CRUD. It recalculates every Leave Request it affects, and it may
 * REFUSE a given (Employee, Leave Type) pair — leaving that balance ENTIRELY unchanged — while the
 * rest of the operation commits and the endpoint answers `200` (AD-19). So a `200` here does NOT
 * mean "it worked". It can mean "it worked for eleven pairs and I declined to touch three, whose
 * balances are now knowingly stale".
 *
 * PRD §1: "a leave balance that is wrong is worse than a leave balance that is absent, because it
 * will be believed." Reporting that `200` as a bare "Holiday added" is precisely how a wrong balance
 * comes to be believed. So this screen reports BOTH numbers — recalculated AND left unchanged — and
 * NAMES every refused pair. The permanent record lives on the Review Flags screen (AC9); this is the
 * immediate telling, at the moment the Admin acts.
 *
 * --- The one rule this screen must never break (AC4 / AC6 / AC10) ---
 *
 * Hiding the add form and the delete buttons from a non-Admin is a USABILITY measure, never
 * the guard. The guard is the server's `403` on `POST`/`DELETE /holidays`. So this
 * component gates *rendering* of those controls on the role from `useMe`, and never gates the
 * *action* on it. The list itself is shown to every role — the GET is any-role (scope `all`)
 * — exactly the Departments/Leave Types pattern (Pattern A), NOT the Employees pattern that
 * returns `null` for a non-Admin.
 *
 * Branch on `code`, never `message` (`client.ts` guidance): `message` is prose for a human and
 * may be reworded; `code` is the contract. The two wire strings this screen matches on — the
 * Admin role and the duplicate-`holiday_date` refusal — are each restated ONCE here, the
 * frontend's single home for them (AD-21), as the departments screen restates its codes.
 *
 * AD-2: every server figure is rendered AS RECEIVED. The counts, the Leave Year and the Leave Type
 * codes are the server's; this screen computes no day count and parses no date.
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useMe } from '../../api'
import {
  type CreateHolidayInput,
  type RecalculationSummary,
  useCreateHoliday,
  useDeleteHoliday,
  useHolidays,
} from '../../api/holidays'
import { RecalculationSummaryPanel } from '../../components/RecalculationSummaryPanel'

/** The role that may add and delete holidays — the one string this screen matches on. */
const ADMIN_ROLE = 'ADMIN'

/** The refusal code a duplicate date carries. Matched on `code`, never `message` (AD-21). */
const HOLIDAY_DATE_IN_USE_CODE = 'HOLIDAY_DATE_IN_USE'

/** Turn a create rejection into a human line — naming the duplicate-date obstruction. */
function writeErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === HOLIDAY_DATE_IN_USE_CODE) {
      return 'A holiday already exists on that date.'
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

/**
 * A human line for a delete failure — the server's message, or a generic fallback. A holiday
 * has no FK dependents (ERD §3), so there is no "still in use" refusal to translate; the paths
 * that reach here are a `404` (the row was already deleted, e.g. by another Admin) or a network
 * error. Mirrors the Departments screen's per-row delete-error line (Pattern A).
 */
function deleteErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Please try again.'
}

/**
 * The blank create form. Both fields are held as STRINGS: `holiday_date` is already the
 * `YYYY-MM-DD` a `<input type="date">` emits — exactly the wire shape — and `name` is text.
 * The submit handler builds the typed `CreateHolidayInput` from this.
 */
const EMPTY_CREATE = {
  holiday_date: '',
  name: '',
}

/**
 * The outcome of the last holiday change — what it corrected, and what it refused to correct.
 *
 * Held in state rather than read off `mutation.data` because ONE panel reports BOTH mutations: an
 * add and a delete each produce a summary, and the Admin needs to see the one they just caused,
 * whichever it was.
 */
interface LastChange {
  /** The word the heading uses. The server does not send it; which mutation ran is the client's own fact. */
  action: 'added' | 'deleted'
  summary: RecalculationSummary
}

export function HolidaysPage() {
  const me = useMe()
  const holidays = useHolidays()
  const createHoliday = useCreateHoliday()
  const deleteHoliday = useDeleteHoliday()

  const [createForm, setCreateForm] = useState({ ...EMPTY_CREATE })
  // The last delete failure, scoped to the row it happened on — the same per-row shape the
  // Departments screen uses, so a failed delete is never silent (a stale row plus no feedback).
  const [deleteError, setDeleteError] = useState<{ id: string; message: string } | null>(null)
  // The last recalculation summary (AC8). Cleared when a new change starts, so the Admin never reads
  // the previous edit's outcome as though it belonged to the one they just made.
  const [lastChange, setLastChange] = useState<LastChange | null>(null)

  const isAdmin = me.data?.role === ADMIN_ROLE

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const holidayDate = createForm.holiday_date
    const name = createForm.name.trim()
    // Guard the required fields client-side; the server is still the real validator. A blank
    // date or an empty name both stop here rather than sending a doomed request.
    if (holidayDate === '' || name === '') return

    setLastChange(null)
    const input: CreateHolidayInput = { holiday_date: holidayDate, name }
    createHoliday.mutate(input, {
      onSuccess: (result) => {
        setCreateForm({ ...EMPTY_CREATE })
        // The summary is CAPTURED, never discarded (AC8). An add can refuse a pair too.
        setLastChange({ action: 'added', summary: result.recalculation })
      },
    })
  }

  function handleDelete(id: string) {
    setDeleteError(null)
    setLastChange(null)
    deleteHoliday.mutate(id, {
      onSuccess: (result) => {
        setDeleteError(null)
        // Story 2.2 discarded this result. It cannot be discarded any more: a delete is the likeliest
        // refusal there is, and dropping the summary is how a partial refusal becomes an unqualified
        // success on the screen (AC8).
        setLastChange({ action: 'deleted', summary: result.recalculation })
      },
      onError: (error) => setDeleteError({ id, message: deleteErrorMessage(error) }),
    })
  }

  return (
    <section className="panel">
      <h2>Holidays</h2>

      {isAdmin ? (
        <p className="muted">
          Maintain the calendar of days the organization does not work — no one spends leave
          on a day nobody was working.
        </p>
      ) : (
        <p className="muted">The company holidays configured for your organization.</p>
      )}

      {isAdmin && (
        <form className="emp-create" onSubmit={handleCreate}>
          <div className="emp-fields">
            <label className="emp-field">
              Date
              <input
                type="date"
                value={createForm.holiday_date}
                onChange={(event) =>
                  setCreateForm({ ...createForm, holiday_date: event.target.value })
                }
                required
              />
            </label>
            <label className="emp-field">
              Name
              <input
                type="text"
                value={createForm.name}
                onChange={(event) => setCreateForm({ ...createForm, name: event.target.value })}
                required
              />
            </label>
          </div>
          <div className="emp-form-actions">
            <button
              type="submit"
              disabled={
                createHoliday.isPending ||
                createForm.holiday_date === '' ||
                createForm.name.trim() === ''
              }
            >
              {createHoliday.isPending ? 'Adding…' : 'Add holiday'}
            </button>
            {createHoliday.isError && (
              <p className="emp-error" role="alert">
                {writeErrorMessage(createHoliday.error)}
              </p>
            )}
          </div>
        </form>
      )}

      {/* AC8. The Admin is told what the change actually did — including, and especially, what it
          DECLINED to do. The markup itself now lives in `components/RecalculationSummaryPanel`:
          Story 2.12's Leave Type edit refuses in exactly the same way, per the same pair, and is the
          second caller this component was waiting for. */}
      {lastChange && (
        <RecalculationSummaryPanel
          action={`Holiday ${lastChange.action}`}
          summary={lastChange.summary}
        />
      )}

      {holidays.isPending && <p className="muted">Loading holidays…</p>}

      {holidays.isError && (
        <p className="emp-error" role="alert">
          Could not load holidays — {holidays.error.message}
        </p>
      )}

      {holidays.data && holidays.data.items.length === 0 && (
        <p className="muted">No holidays yet.</p>
      )}

      {holidays.data && holidays.data.items.length > 0 && (
        <ul className="emp-list">
          {holidays.data.items.map((holiday) => (
            <li key={holiday.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">{holiday.name}</span>
                <span className="muted">{holiday.holiday_date}</span>
              </div>
              {isAdmin && (
                <span className="dept-actions">
                  <button
                    type="button"
                    onClick={() => handleDelete(holiday.id)}
                    disabled={
                      deleteHoliday.isPending && deleteHoliday.variables === holiday.id
                    }
                  >
                    Delete
                  </button>
                </span>
              )}
              {deleteError?.id === holiday.id && (
                <p className="emp-error" role="alert">
                  {deleteError.message}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
