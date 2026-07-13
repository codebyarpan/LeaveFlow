/**
 * The Leave Types screen (Story 2.1, AC5).
 *
 * Implements: FR-06 (frontend), SM-5 (an Admin creates a fourth Leave Type through the UI,
 * no code change), AC5 (view and create Leave Types and set each attribute), NFR-16 (the
 * create controls render only for an Admin).
 *
 * --- The one rule this screen must never break (AC5 / AC7) ---
 *
 * Hiding the create form from a non-Admin is a USABILITY measure, never the guard. The guard
 * is the server's `403` on `POST /leave-types` (Task 6). So this component gates *rendering*
 * of the form on the role from `useMe`, and never gates the *action* on it. The list itself
 * is shown to every role — the GET is any-role (scope `all`) — exactly the Departments
 * pattern (Pattern A), NOT the Employees pattern that returns `null` for a non-Admin.
 *
 * Branch on `code`, never `message` (`client.ts` guidance): `message` is prose for a human
 * and may be reworded; `code` is the contract. The two wire strings this screen matches on —
 * the Admin role and the duplicate-`code` refusal — are each restated ONCE here, the
 * frontend's single home for them (AD-21), as the departments screen restates its codes.
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useMe } from '../../api'
import {
  type CreateLeaveTypeInput,
  useCreateLeaveType,
  useLeaveTypes,
} from '../../api/leaveTypes'

/** The role that may create Leave Types — the one string this screen matches on. */
const ADMIN_ROLE = 'ADMIN'

/** The refusal code a duplicate `code` carries. Matched on `code`, never `message` (AD-21). */
const LEAVE_TYPE_CODE_IN_USE_CODE = 'LEAVE_TYPE_CODE_IN_USE'

/** Turn a create rejection into a human line — naming the duplicate `code` obstruction. */
function writeErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === LEAVE_TYPE_CODE_IN_USE_CODE) {
      return 'A leave type with that code already exists — choose a different code.'
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

/**
 * The blank create form. Numeric and nullable fields are held as STRINGS (an empty number
 * input is `''`, not `0` or `NaN`); the two flags are real booleans. The submit handler
 * builds the typed `CreateLeaveTypeInput` (numbers / null / booleans) from this — mirroring
 * `EmployeesPage`'s `manager_id === '' ? null : ...` idiom.
 */
const EMPTY_CREATE = {
  code: '',
  name: '',
  annual_entitlement: '',
  carries_forward: false,
  carry_forward_cap: '',
  requires_supporting_document: false,
}

export function LeaveTypesPage() {
  const me = useMe()
  const leaveTypes = useLeaveTypes()
  const createLeaveType = useCreateLeaveType()

  const [createForm, setCreateForm] = useState({ ...EMPTY_CREATE })

  const isAdmin = me.data?.role === ADMIN_ROLE

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const code = createForm.code.trim()
    const name = createForm.name.trim()
    // Guard the required text/number fields client-side; the server is still the real
    // validator. A blank entitlement or a non-carrying type both resolve cleanly below.
    if (code === '' || name === '' || createForm.annual_entitlement.trim() === '') return

    const input: CreateLeaveTypeInput = {
      code,
      name,
      annual_entitlement: Number(createForm.annual_entitlement),
      carries_forward: createForm.carries_forward,
      // The cap is meaningful only when the type carries forward; otherwise it is null. An
      // empty cap field is also null — never 0, which would be a real (wrong) cap of zero.
      carry_forward_cap:
        createForm.carries_forward && createForm.carry_forward_cap.trim() !== ''
          ? Number(createForm.carry_forward_cap)
          : null,
      requires_supporting_document: createForm.requires_supporting_document,
    }
    createLeaveType.mutate(input, { onSuccess: () => setCreateForm({ ...EMPTY_CREATE }) })
  }

  return (
    <section className="panel">
      <h2>Leave Types</h2>

      {isAdmin ? (
        <p className="muted">
          Define the leave types and their attributes — policy is configuration, not code.
        </p>
      ) : (
        <p className="muted">The leave types configured for your organization.</p>
      )}

      {isAdmin && (
        <form className="emp-create" onSubmit={handleCreate}>
          <div className="emp-fields">
            <label className="emp-field">
              Code
              <input
                type="text"
                value={createForm.code}
                onChange={(event) => setCreateForm({ ...createForm, code: event.target.value })}
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
            <label className="emp-field">
              Annual entitlement (days)
              <input
                type="number"
                min="0"
                value={createForm.annual_entitlement}
                onChange={(event) =>
                  setCreateForm({ ...createForm, annual_entitlement: event.target.value })
                }
                required
              />
            </label>
            <label className="emp-field leave-check">
              <input
                type="checkbox"
                checked={createForm.carries_forward}
                onChange={(event) =>
                  setCreateForm({
                    ...createForm,
                    carries_forward: event.target.checked,
                    // Clearing the cap when carry-forward is turned off keeps the form
                    // honest: a disabled field must not smuggle a stale value into submit.
                    carry_forward_cap: event.target.checked ? createForm.carry_forward_cap : '',
                  })
                }
              />
              Carries forward
            </label>
            <label className="emp-field">
              Carry-forward cap (days)
              <input
                type="number"
                min="0"
                value={createForm.carry_forward_cap}
                disabled={!createForm.carries_forward}
                onChange={(event) =>
                  setCreateForm({ ...createForm, carry_forward_cap: event.target.value })
                }
                placeholder={createForm.carries_forward ? 'No cap' : 'N/A'}
              />
            </label>
            <label className="emp-field leave-check">
              <input
                type="checkbox"
                checked={createForm.requires_supporting_document}
                onChange={(event) =>
                  setCreateForm({
                    ...createForm,
                    requires_supporting_document: event.target.checked,
                  })
                }
              />
              Requires supporting document
            </label>
          </div>
          <div className="emp-form-actions">
            <button type="submit" disabled={createLeaveType.isPending}>
              {createLeaveType.isPending ? 'Adding…' : 'Add leave type'}
            </button>
            {createLeaveType.isError && (
              <p className="emp-error" role="alert">
                {writeErrorMessage(createLeaveType.error)}
              </p>
            )}
          </div>
        </form>
      )}

      {leaveTypes.isPending && <p className="muted">Loading leave types…</p>}

      {leaveTypes.isError && (
        <p className="emp-error" role="alert">
          Could not load leave types — {leaveTypes.error.message}
        </p>
      )}

      {leaveTypes.data && leaveTypes.data.items.length === 0 && (
        <p className="muted">No leave types yet.</p>
      )}

      {leaveTypes.data && leaveTypes.data.items.length > 0 && (
        <ul className="emp-list">
          {leaveTypes.data.items.map((leaveType) => (
            <li key={leaveType.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {leaveType.code} · {leaveType.name}
                </span>
                <span className="muted">
                  {leaveType.annual_entitlement} days/year ·{' '}
                  {leaveType.carries_forward
                    ? `carries forward${
                        leaveType.carry_forward_cap === null
                          ? ' (no cap)'
                          : ` (cap ${leaveType.carry_forward_cap})`
                      }`
                    : 'no carry-forward'}
                  {leaveType.requires_supporting_document && ' · document required'}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
