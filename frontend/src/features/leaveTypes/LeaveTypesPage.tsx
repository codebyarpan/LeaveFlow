/**
 * The Leave Types screen (Story 2.1 AC5; Story 2.12 AC10, AC11).
 *
 * Implements: FR-06 (frontend) — BOTH halves now. Story 2.1 delivered "define the leave types and
 * their attributes"; Story 2.12 delivers its last clause: AN ADMIN CHANGING POLICY IS FORCED TO SAY
 * WHAT HAPPENS TO THE BALANCES THAT ALREADY EXIST. Also SM-5 (a fourth Leave Type is created — and
 * now EDITED — through the UI with no code change), NFR-16 (the write controls render only for an
 * Admin), NFR-17 (a refusal is shown as a human line).
 *
 * --- AC10, and why the form REFUSES to submit without a disposition ---
 *
 * The server requires a disposition whenever a balance-affecting attribute actually changes, and
 * refuses the whole edit with `400 POLICY_DISPOSITION_REQUIRED` without one — applying NOTHING. So
 * "without this the Admin can create a Leave Type but never successfully edit one" is literally true,
 * and a form that let them try would be a form that only ever fails. The submit button is therefore
 * DISABLED until they choose, and the two options say IN PLAIN LANGUAGE what each does to the
 * balances that already exist. This is not client-side validation standing in for the server's; the
 * server is still the guard. It is the screen making a required decision visible instead of letting
 * the Admin discover it as an error.
 *
 * ⚠️ The honest bit, stated rather than hidden (Landmine 3 / Open Decision #1): for a CAP-ONLY
 * change, PRESERVE and RECALCULATE do the same thing to existing balances. Nothing in the schema
 * freezes a carry-forward cap — `entitlement_basis` freezes only the annual entitlement — so every
 * downstream trigger re-reads the cap live, and "preserve the cap" is a promise the system cannot
 * keep. The copy below says so. Quietly implying otherwise would be the wrong figure that will be
 * believed (PRD §1).
 *
 * --- AC11: a `200` is not a success ---
 *
 * A RECALCULATE may REFUSE a given (Employee, Leave Type) pair, leaving that balance entirely
 * unchanged and knowingly stale, while the rest of the edit commits and the server answers `200`
 * (AD-19). The summary is therefore CAPTURED, never discarded, and rendered by the same
 * `RecalculationSummaryPanel` the Holidays screen uses — the component this story's edit was the
 * second caller of.
 *
 * --- The one rule this screen must never break (AC5 / AC7) ---
 *
 * Hiding the create and edit forms from a non-Admin is a USABILITY measure, never the guard. The
 * guard is the server's `403` on `POST` and `PATCH /leave-types`. So this component gates *rendering*
 * of the forms on the role from `useMe`, and never gates the *action* on it. The list itself is shown
 * to every role — the GET is any-role (scope `all`) — exactly the Departments pattern (Pattern A),
 * NOT the Employees pattern that returns `null` for a non-Admin.
 *
 * Branch on `code`, never `message` (`client.ts` guidance): `message` is prose for a human and may be
 * reworded; `code` is the contract. Every wire string this screen matches on is restated ONCE here,
 * the frontend's single home for them (AD-21).
 *
 * AD-2: every server figure is rendered AS RECEIVED. This screen computes no balance and no day count.
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useMe } from '../../api'
import {
  type CreateLeaveTypeInput,
  type LeaveType,
  type RecalculationSummary,
  type UpdateLeaveTypeInput,
  useCreateLeaveType,
  useLeaveTypes,
  useUpdateLeaveType,
} from '../../api/leaveTypes'
import { RecalculationSummaryPanel } from '../../components/RecalculationSummaryPanel'

/** The role that may create and edit Leave Types — the one string this screen matches on. */
const ADMIN_ROLE = 'ADMIN'

/** The refusal code a duplicate `code` carries. Matched on `code`, never `message` (AD-21). */
const LEAVE_TYPE_CODE_IN_USE_CODE = 'LEAVE_TYPE_CODE_IN_USE'

/** The refusal code a balance-affecting edit with no valid disposition carries (Story 2.12). */
const POLICY_DISPOSITION_REQUIRED_CODE = 'POLICY_DISPOSITION_REQUIRED'

/**
 * The two dispositions, restated ONCE here — the frontend's single home for them (AD-21), exactly as
 * this screen restates the Admin role and its error codes. They are the server's vocabulary strings
 * and travel verbatim on the wire.
 */
const DISPOSITION_RECALCULATE = 'RECALCULATE'
const DISPOSITION_PRESERVE = 'PRESERVE'

/**
 * The three attributes whose change makes the server demand a disposition (FR-06). This mirrors the
 * server's `_BALANCE_AFFECTING`, and it is a USABILITY mirror, never the guard: if this list ever
 * drifts from the server's, the server still refuses the edit with `POLICY_DISPOSITION_REQUIRED` and
 * the screen shows that refusal. What drift would cost is the *prompt*, not the *protection*.
 */
const BALANCE_AFFECTING = [
  'annual_entitlement',
  'carries_forward',
  'carry_forward_cap',
] as const

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
 * Turn an EDIT rejection into a human line (Story 2.12, NFR-17).
 *
 * `POLICY_DISPOSITION_REQUIRED` should be unreachable from this form — AC10's guard is exactly that
 * it cannot be submitted without a choice — but it is translated anyway rather than falling through
 * to the raw server message. The server is the guard; a guard whose refusal the screen cannot explain
 * is a guard the user experiences as a mystery. And "nothing was applied" is the half of the refusal
 * an Admin most needs to hear.
 */
function editErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === POLICY_DISPOSITION_REQUIRED_CODE) {
      return (
        'This change affects leave balances that already exist, so you must choose what happens ' +
        'to them. Nothing was applied.'
      )
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

/**
 * The edit form's state — every attribute as a STRING (or a boolean), plus the chosen disposition.
 *
 * Strings, because that is what an `<input>` holds: an empty number input is `''`, not `0` or `NaN`.
 * The submit handler converts, exactly as the create form does. `disposition` is `''` until the Admin
 * chooses — and `''` is what AC10's submit guard tests.
 */
interface EditForm {
  name: string
  annual_entitlement: string
  carries_forward: boolean
  carry_forward_cap: string
  requires_supporting_document: boolean
  disposition: string
}

/** Open the edit form on a row, seeded with what that row currently holds. */
function toEditForm(leaveType: LeaveType): EditForm {
  return {
    name: leaveType.name,
    annual_entitlement: String(leaveType.annual_entitlement),
    carries_forward: leaveType.carries_forward,
    // A null cap is "no cap" — an EMPTY field, never the string "0", which would be a real cap of
    // zero and a different policy entirely.
    carry_forward_cap:
      leaveType.carry_forward_cap === null ? '' : String(leaveType.carry_forward_cap),
    requires_supporting_document: leaveType.requires_supporting_document,
    disposition: '',
  }
}

/**
 * The attributes this form would actually CHANGE on the row — the sparse `PATCH` body.
 *
 * ⚠️ ONLY changed keys are included, and that is load-bearing on two counts. The server reads the
 * body with `exclude_unset`, so an omitted key means "no change" while an explicit `null` cap means
 * "the cap was REMOVED" (uncapped) — two different edits that a full object would collapse into one.
 * And a resubmitted identical value is NOT a change: including it would make the server demand a
 * disposition for an edit that moves nothing.
 *
 * `disposition` is not an attribute of the Leave Type and is added by the caller, not here.
 */
function changedFields(form: EditForm, original: LeaveType): UpdateLeaveTypeInput {
  const changes: UpdateLeaveTypeInput = {}

  const name = form.name.trim()
  if (name !== original.name) changes.name = name

  const entitlement = Number(form.annual_entitlement)
  if (entitlement !== original.annual_entitlement) {
    changes.annual_entitlement = entitlement
  }

  if (form.carries_forward !== original.carries_forward) {
    changes.carries_forward = form.carries_forward
  }

  // The cap is meaningful only on a carrying type; otherwise it is null. An empty field is also null
  // — never 0, which is a real (and very different) cap.
  const cap =
    form.carries_forward && form.carry_forward_cap.trim() !== ''
      ? Number(form.carry_forward_cap)
      : null
  if (cap !== original.carry_forward_cap) changes.carry_forward_cap = cap

  if (form.requires_supporting_document !== original.requires_supporting_document) {
    changes.requires_supporting_document = form.requires_supporting_document
  }

  return changes
}

/** Does this edit touch a balance-affecting attribute — i.e. will the server demand a disposition? */
function needsDisposition(changes: UpdateLeaveTypeInput): boolean {
  return BALANCE_AFFECTING.some((attribute) => attribute in changes)
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
  const updateLeaveType = useUpdateLeaveType()

  const [createForm, setCreateForm] = useState({ ...EMPTY_CREATE })
  // Which row is open for editing, and its working state. The `editingId` inline-edit idiom is
  // `EmployeesPage`'s; there is no router and no modal in this app.
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm | null>(null)
  // The last edit's recalculation summary (AC11). Cleared when a new edit starts, so the Admin never
  // reads the previous edit's outcome as though it belonged to the one they just made.
  const [lastChange, setLastChange] = useState<RecalculationSummary | null>(null)

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

  function startEdit(leaveType: LeaveType) {
    setEditingId(leaveType.id)
    setEditForm(toEditForm(leaveType))
    setLastChange(null)
  }

  function cancelEdit() {
    setEditingId(null)
    setEditForm(null)
  }

  function handleEdit(event: FormEvent<HTMLFormElement>, original: LeaveType) {
    event.preventDefault()
    if (editForm === null) return

    const changes = changedFields(editForm, original)
    // Nothing moved — a resubmitted identical form. Close it rather than sending an edit the server
    // would treat as a no-op anyway.
    if (Object.keys(changes).length === 0) {
      cancelEdit()
      return
    }

    // AC10's guard, restated in code. The button is already disabled in this state; this is the
    // second half of the same rule, because a form can also be submitted with Enter.
    const mustChoose = needsDisposition(changes)
    if (mustChoose && editForm.disposition === '') return
    if (mustChoose) changes.disposition = editForm.disposition

    setLastChange(null)
    updateLeaveType.mutate(
      { id: original.id, input: changes },
      {
        onSuccess: (result) => {
          cancelEdit()
          // The summary is CAPTURED, never discarded (AC11): a RECALCULATE can refuse a pair, and
          // reporting that 200 as a bare "Saved" is how a stale balance comes to be believed.
          setLastChange(result.recalculation)
        },
      },
    )
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

      {/* AC11. What the edit actually did — including, and especially, what it DECLINED to do. The
          same component the Holidays screen renders: a policy change and a holiday change refuse in
          exactly the same way, per the same (Employee, Leave Type) pair. */}
      {lastChange && (
        <RecalculationSummaryPanel action="Leave type updated" summary={lastChange} />
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

              {isAdmin && editingId !== leaveType.id && (
                <span className="dept-actions">
                  <button type="button" onClick={() => startEdit(leaveType)}>
                    Edit policy
                  </button>
                </span>
              )}

              {isAdmin && editingId === leaveType.id && editForm !== null && (
                <EditPolicyForm
                  form={editForm}
                  original={leaveType}
                  isPending={updateLeaveType.isPending}
                  error={updateLeaveType.isError ? updateLeaveType.error : null}
                  onChange={setEditForm}
                  onSubmit={(event) => handleEdit(event, leaveType)}
                  onCancel={cancelEdit}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

interface EditPolicyFormProps {
  form: EditForm
  original: LeaveType
  isPending: boolean
  error: unknown
  onChange: (form: EditForm) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onCancel: () => void
}

/**
 * The inline policy-edit form (AC10). Extracted from the row for readability, not for reuse — it has
 * exactly one caller and lives with its feature (`src/components/README.md`).
 *
 * THE RULE THIS FORM EXISTS TO ENFORCE: when the edit would affect balances that already exist, it
 * WILL NOT SUBMIT until the Admin chooses what happens to them. The submit button is disabled and the
 * two options state, in plain language, what each does. The server refuses without a disposition
 * anyway (`400 POLICY_DISPOSITION_REQUIRED`, applying nothing) — this is the screen making that
 * required decision visible rather than letting the Admin meet it as an error.
 */
function EditPolicyForm({
  form,
  original,
  isPending,
  error,
  onChange,
  onSubmit,
  onCancel,
}: EditPolicyFormProps) {
  const changes = changedFields(form, original)
  const mustChoose = needsDisposition(changes)
  const nothingChanged = Object.keys(changes).length === 0
  // AC10, in one expression: a balance-affecting edit cannot be submitted without a disposition.
  const blocked = mustChoose && form.disposition === ''

  return (
    <form className="emp-create" onSubmit={onSubmit}>
      <div className="emp-fields">
        <label className="emp-field">
          Name
          <input
            type="text"
            value={form.name}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
            required
          />
        </label>
        <label className="emp-field">
          Annual entitlement (days)
          <input
            type="number"
            min="0"
            value={form.annual_entitlement}
            onChange={(event) =>
              onChange({ ...form, annual_entitlement: event.target.value })
            }
            required
          />
        </label>
        <label className="emp-field leave-check">
          <input
            type="checkbox"
            checked={form.carries_forward}
            onChange={(event) =>
              onChange({
                ...form,
                carries_forward: event.target.checked,
                // Clearing the cap when carry-forward is turned off keeps the form honest: a
                // disabled field must not smuggle a stale value into submit.
                carry_forward_cap: event.target.checked ? form.carry_forward_cap : '',
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
            value={form.carry_forward_cap}
            disabled={!form.carries_forward}
            onChange={(event) =>
              onChange({ ...form, carry_forward_cap: event.target.value })
            }
            placeholder={form.carries_forward ? 'No cap' : 'N/A'}
          />
        </label>
        <label className="emp-field leave-check">
          <input
            type="checkbox"
            checked={form.requires_supporting_document}
            onChange={(event) =>
              onChange({ ...form, requires_supporting_document: event.target.checked })
            }
          />
          Requires supporting document
        </label>
      </div>

      {/* AC10. Shown ONLY when the change actually affects existing balances — asking for a
          disposition on a rename would be a question with no meaning. */}
      {mustChoose && (
        <div className="emp-fields">
          <p className="muted">
            This change affects leave balances that already exist. Choose what happens to them —
            the edit will not save until you do.
          </p>
          <label className="emp-field leave-check">
            <input
              type="radio"
              name={`disposition-${original.id}`}
              value={DISPOSITION_RECALCULATE}
              checked={form.disposition === DISPOSITION_RECALCULATE}
              onChange={() => onChange({ ...form, disposition: DISPOSITION_RECALCULATE })}
            />
            Recalculate — re-derive every existing balance under the new policy. A balance that
            cannot be corrected without going negative is left unchanged and flagged for review.
          </label>
          <label className="emp-field leave-check">
            <input
              type="radio"
              name={`disposition-${original.id}`}
              value={DISPOSITION_PRESERVE}
              checked={form.disposition === DISPOSITION_PRESERVE}
              onChange={() => onChange({ ...form, disposition: DISPOSITION_PRESERVE })}
            />
            Preserve — leave existing balances as they were accrued; only future accruals use the
            new value.
          </label>
          {/* The honest caveat (Landmine 3 / Open Decision #1). Nothing in the schema freezes a
              carry-forward cap the way `entitlement_basis` freezes the annual entitlement, so
              "preserve the cap" is a promise the system cannot keep — every later trigger re-reads
              the cap live. Rather than pretend, the system re-derives carry-forward under BOTH
              dispositions for these two attributes, and says so here. */}
          {('carry_forward_cap' in changes || 'carries_forward' in changes) && (
            <p className="muted">
              Note: you changed the carry-forward rules. Carry-forward is always re-derived from the
              new rules, under either choice — nothing in the system can freeze a cap the way it
              freezes an annual entitlement, so preserving one is not something it can honestly
              offer. Your choice is still recorded.
            </p>
          )}
        </div>
      )}

      <div className="emp-form-actions">
        <button type="submit" disabled={isPending || blocked || nothingChanged}>
          {isPending ? 'Saving…' : 'Save policy'}
        </button>
        <button type="button" onClick={onCancel} disabled={isPending}>
          Cancel
        </button>
        {error !== null && (
          <p className="emp-error" role="alert">
            {editErrorMessage(error)}
          </p>
        )}
      </div>
    </form>
  )
}
