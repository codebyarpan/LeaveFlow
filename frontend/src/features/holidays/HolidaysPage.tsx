/**
 * The Company Holidays screen (Story 2.2, AC4 / AC10).
 *
 * Implements: FR-10 (frontend), AC4 (an Admin adds and deletes holidays for a Leave Year),
 * NFR-16 (the add/delete controls render only for an Admin), NFR-17 (a duplicate-date refusal
 * is shown as a human line).
 *
 * --- The one rule this screen must never break (AC4 / AC6 / AC10) ---
 *
 * Hiding the add form and the delete buttons from a non-Admin is a USABILITY measure, never
 * the guard. The guard is the server's `403` on `POST`/`DELETE /holidays` (Task 6). So this
 * component gates *rendering* of those controls on the role from `useMe`, and never gates the
 * *action* on it. The list itself is shown to every role — the GET is any-role (scope `all`)
 * — exactly the Departments/Leave Types pattern (Pattern A), NOT the Employees pattern that
 * returns `null` for a non-Admin.
 *
 * Branch on `code`, never `message` (`client.ts` guidance): `message` is prose for a human and
 * may be reworded; `code` is the contract. The two wire strings this screen matches on — the
 * Admin role and the duplicate-`holiday_date` refusal — are each restated ONCE here, the
 * frontend's single home for them (AD-21), as the departments screen restates its codes.
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useMe } from '../../api'
import {
  type CreateHolidayInput,
  useCreateHoliday,
  useDeleteHoliday,
  useHolidays,
} from '../../api/holidays'

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

export function HolidaysPage() {
  const me = useMe()
  const holidays = useHolidays()
  const createHoliday = useCreateHoliday()
  const deleteHoliday = useDeleteHoliday()

  const [createForm, setCreateForm] = useState({ ...EMPTY_CREATE })
  // The last delete failure, scoped to the row it happened on — the same per-row shape the
  // Departments screen uses, so a failed delete is never silent (a stale row plus no feedback).
  const [deleteError, setDeleteError] = useState<{ id: string; message: string } | null>(null)

  const isAdmin = me.data?.role === ADMIN_ROLE

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const holidayDate = createForm.holiday_date
    const name = createForm.name.trim()
    // Guard the required fields client-side; the server is still the real validator. A blank
    // date or an empty name both stop here rather than sending a doomed request.
    if (holidayDate === '' || name === '') return

    const input: CreateHolidayInput = { holiday_date: holidayDate, name }
    createHoliday.mutate(input, { onSuccess: () => setCreateForm({ ...EMPTY_CREATE }) })
  }

  function handleDelete(id: string) {
    setDeleteError(null)
    deleteHoliday.mutate(id, {
      onSuccess: () => setDeleteError(null),
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
