/**
 * The Profile screen (Story 1.8, AC7). Renders for every authenticated user — Role "any".
 *
 * Implements: FR-17 (an Employee corrects their own Full Name), AC7 (email, role,
 * department, manager and joining date are shown READ-ONLY; Full Name alone is editable),
 * NFR-16 (read-only rendering is a usability measure — the server is the enforcement point,
 * AD-14, never this component).
 *
 * --- Why only `full_name` is an input, and why `FORBIDDEN_FIELD` never shows here ---
 *
 * The form submits ONLY `full_name` (via `useUpdateMe`), so the server's `400
 * FORBIDDEN_FIELD` refusal — which fires when any other field is sent — is unreachable
 * through this UI. There is therefore no `code` branch here: an error is shown by its
 * `message`. The other fields are plain read-only text; editing them is not offered, and
 * even if it were, the server would refuse it (the hiding is never the guard).
 *
 * `MeResponse` deliberately has NO `manager_id` — `/me` hides the reporting line — so the
 * Manager row has no value to show from `/me`. It renders a placeholder ("—") rather than
 * inventing a separate fetch of the manager; the reporting line is the Admin's surface
 * (`/employees`), not this self-service read.
 */
import { type FormEvent, useEffect, useRef, useState } from 'react'

import { useMe, useUpdateMe } from '../../api'

/** A read-only profile field: a label and its plain-text value (never an input). */
function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="emp-field">
      {label}
      <span className="muted">{value}</span>
    </div>
  )
}

export function ProfilePage() {
  const me = useMe()
  const updateMe = useUpdateMe()

  // The editable Full Name, seeded from the server value. It is re-seeded when the server
  // value CHANGES (a successful save's refetch, or a concurrent admin rename) — but only if
  // the user has not diverged from the value last seen from the server, so a background
  // refetch never clobbers in-progress typing (code review 2026-07-13).
  const [fullName, setFullName] = useState('')
  const serverName = me.data?.full_name
  const lastSeenServerName = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (serverName === undefined) {
      return
    }
    const previous = lastSeenServerName.current
    lastSeenServerName.current = serverName
    // Seed on first load, or overwrite only when the field still matches what the server
    // last gave us (the user has not edited). Otherwise leave the in-progress edit alone.
    setFullName((current) =>
      previous === undefined || current === previous ? serverName : current,
    )
  }, [serverName])

  // Editing clears a latched success/error state so a stale "Saved." (or error) cannot
  // linger or reappear when the name is reverted to a previously-saved value.
  function handleNameChange(value: string) {
    setFullName(value)
    if (updateMe.isSuccess || updateMe.isError) {
      updateMe.reset()
    }
  }

  if (me.isPending) {
    return (
      <section className="panel">
        <h2>Profile</h2>
        <p className="muted">Loading your profile…</p>
      </section>
    )
  }

  if (me.isError || !me.data) {
    return (
      <section className="panel">
        <h2>Profile</h2>
        <p className="emp-error" role="alert">
          Could not load your profile{me.error ? ` — ${me.error.message}` : ''}.
        </p>
      </section>
    )
  }

  const profile = me.data

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = fullName.trim()
    if (trimmed === '') {
      return
    }
    updateMe.mutate(trimmed)
  }

  const trimmedName = fullName.trim()
  const isEmpty = trimmedName === ''
  const isUnchanged = trimmedName === profile.full_name

  return (
    <section className="panel">
      <h2>Profile</h2>
      <p className="muted">
        Your name is the one detail you maintain here. Email, role, department and joining
        date are set by an administrator and shown for reference.
      </p>

      <form className="emp-create" onSubmit={handleSubmit}>
        <div className="emp-fields">
          <label className="emp-field">
            Full name
            <input
              type="text"
              value={fullName}
              onChange={(event) => handleNameChange(event.target.value)}
              required
            />
          </label>
          <ReadOnlyField label="Email" value={profile.email} />
          <ReadOnlyField label="Role" value={profile.role} />
          <ReadOnlyField label="Department" value={profile.department.name} />
          {/* /me hides the reporting line (no manager_id on MeResponse) — a placeholder,
              never a separate fetch of the manager. */}
          <ReadOnlyField label="Manager" value="—" />
          <ReadOnlyField label="Joining date" value={profile.joining_date} />
        </div>
        <div className="emp-form-actions">
          <button type="submit" disabled={updateMe.isPending || isUnchanged || isEmpty}>
            {updateMe.isPending ? 'Saving…' : 'Save name'}
          </button>
          {updateMe.isSuccess && !updateMe.isPending && (
            <p className="muted" role="status">
              Saved.
            </p>
          )}
          {updateMe.isError && (
            <p className="emp-error" role="alert">
              {updateMe.error.message}
            </p>
          )}
        </div>
      </form>
    </section>
  )
}
