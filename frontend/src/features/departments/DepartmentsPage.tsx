/**
 * The Departments screen.
 *
 * Implements: FR-05 (frontend), AC8 (create/rename/delete controls, and a refused delete
 * that surfaces the obstruction), NFR-16 (the controls render only for an Admin) and
 * NFR-17 (a `DEPARTMENT_NOT_EMPTY` refusal is shown with the number that names it).
 *
 * --- The one rule this screen must never break (AC4 / AC8) ---
 *
 * Hiding the Admin controls for a non-Admin is a USABILITY measure, never the guard. The
 * guard is the server's `403` (Task 6). So this component gates *rendering* on the role
 * from `useMe`, and never gates the *action* on it — a non-Admin who reached a control
 * anyway would still be refused by the backend. The list itself is shown to every role.
 *
 * Branch on `code`, never `message` (`client.ts` guidance): `message` is prose for a human
 * and may be reworded; `code` is the contract. The two wire strings this screen matches on
 * — the Admin role and the not-empty code — are each restated ONCE here, the frontend's
 * single home for them (AD-21, as `client.ts` restates `TOKEN_INVALID`).
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useMe } from '../../api'
import {
  type Department,
  useCreateDepartment,
  useDeleteDepartment,
  useDepartments,
  useRenameDepartment,
} from '../../api/departments'

/** The role that may create, rename and delete — the one string this screen matches on. */
const ADMIN_ROLE = 'ADMIN'

/** The refusal code a non-empty delete carries. Matched on `code`, never `message`. */
const DEPARTMENT_NOT_EMPTY_CODE = 'DEPARTMENT_NOT_EMPTY'

/** Turn a delete rejection into a human line — naming the obstruction with its count. */
function deleteErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === DEPARTMENT_NOT_EMPTY_CODE) {
    const count = error.details.employee_count
    if (typeof count === 'number') {
      const people = count === 1 ? 'employee' : 'employees'
      return `Cannot delete: ${count} ${people} are still assigned to this department.`
    }
    return error.message
  }
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Please try again.'
}

/** A human line for a create/rename failure — the server's message, or a generic fallback. */
function writeErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Please try again.'
}

export function DepartmentsPage() {
  const me = useMe()
  const departments = useDepartments()
  const createDepartment = useCreateDepartment()
  const renameDepartment = useRenameDepartment()
  const deleteDepartment = useDeleteDepartment()

  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  // The id whose delete was refused, and the line to show against it (NFR-17).
  const [deleteError, setDeleteError] = useState<{ id: string; message: string } | null>(null)

  const isAdmin = me.data?.role === ADMIN_ROLE

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = newName.trim()
    if (name === '') return
    setDeleteError(null)
    createDepartment.mutate(name, { onSuccess: () => setNewName('') })
  }

  function startEditing(department: Department) {
    // Clear any stale delete refusal and any prior rename error before opening the form.
    setDeleteError(null)
    renameDepartment.reset()
    setEditingId(department.id)
    setEditingName(department.name)
  }

  function cancelEditing() {
    renameDepartment.reset()
    setEditingId(null)
  }

  function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = editingName.trim()
    if (editingId === null || name === '') return
    // A failed rename leaves the form open (editingId unchanged) with the error shown below,
    // so the Admin can retry or cancel; only a success closes it.
    renameDepartment.mutate(
      { id: editingId, name },
      { onSuccess: () => setEditingId(null) },
    )
  }

  function handleDelete(department: Department) {
    setDeleteError(null)
    deleteDepartment.mutate(department.id, {
      onSuccess: () => setDeleteError(null),
      onError: (error) =>
        setDeleteError({ id: department.id, message: deleteErrorMessage(error) }),
    })
  }

  return (
    <section className="panel">
      <h2>Departments</h2>

      {isAdmin ? (
        <p className="muted">Create, rename or remove the departments employees belong to.</p>
      ) : (
        <p className="muted">The departments in your organization.</p>
      )}

      {isAdmin && (
        <form className="dept-create" onSubmit={handleCreate}>
          <input
            type="text"
            aria-label="New department name"
            placeholder="New department name"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
          <button type="submit" disabled={createDepartment.isPending || newName.trim() === ''}>
            {createDepartment.isPending ? 'Adding…' : 'Add department'}
          </button>
          {createDepartment.isError && (
            <p className="dept-error" role="alert">
              {writeErrorMessage(createDepartment.error)}
            </p>
          )}
        </form>
      )}

      {departments.isPending && <p className="muted">Loading departments…</p>}

      {departments.isError && (
        <p className="dept-error" role="alert">
          Could not load departments — {departments.error.message}
        </p>
      )}

      {departments.data && departments.data.items.length === 0 && (
        <p className="muted">No departments yet.</p>
      )}

      {departments.data && departments.data.items.length > 0 && (
        <ul className="dept-list">
          {departments.data.items.map((department) => (
            <li key={department.id} className="dept-row">
              {isAdmin && editingId === department.id ? (
                <form className="dept-edit" onSubmit={handleRename}>
                  <input
                    type="text"
                    aria-label="Department name"
                    value={editingName}
                    onChange={(event) => setEditingName(event.target.value)}
                    autoFocus
                  />
                  <button
                    type="submit"
                    disabled={renameDepartment.isPending || editingName.trim() === ''}
                  >
                    Save
                  </button>
                  <button type="button" onClick={cancelEditing}>
                    Cancel
                  </button>
                  {renameDepartment.isError && (
                    <p className="dept-error" role="alert">
                      {writeErrorMessage(renameDepartment.error)}
                    </p>
                  )}
                </form>
              ) : (
                <>
                  <span className="dept-name">{department.name}</span>
                  {isAdmin && (
                    <span className="dept-actions">
                      <button type="button" onClick={() => startEditing(department)}>
                        Rename
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(department)}
                        disabled={
                          deleteDepartment.isPending &&
                          deleteDepartment.variables === department.id
                        }
                      >
                        Delete
                      </button>
                    </span>
                  )}
                </>
              )}

              {deleteError?.id === department.id && (
                <p className="dept-error" role="alert">
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
