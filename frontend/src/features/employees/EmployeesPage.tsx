/**
 * The Employees screen (Story 1.6, AC13). Admin-only.
 *
 * Implements: FR-04 (frontend), AC13 (create/edit/deactivate, assign a Manager, set an
 * initial password, and surface every refusal), NFR-16 (the screen renders only for an
 * Admin) and NFR-17 (a refused deactivation, demotion, duplicate email or manager
 * assignment is shown with the reason that names it).
 *
 * --- The one rule this screen must never break (AC5 / AC13) ---
 *
 * Rendering this screen only for an Admin is a USABILITY measure, never the guard. The
 * guard is the server's `403` — every `/employees` endpoint is Admin-only, so even the
 * list query would be refused for a non-Admin. This component therefore gates *mounting*
 * on the role from `useMe`, and never treats that hiding as the security boundary.
 *
 * Branch on `code`, never `message` (`client.ts` guidance): `message` is prose and may be
 * reworded; `code` is the contract. The three refusal codes this screen matches on are each
 * restated ONCE here — the frontend's single home for them (AD-21), as the departments
 * screen restates `DEPARTMENT_NOT_EMPTY`. The Admin communicates the initial password out
 * of band; LeaveFlow sends no email (FR-14, PRD §6).
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useDepartments, useMe } from '../../api'
import {
  type Employee,
  type UpdateEmployeeInput,
  useCreateEmployee,
  useDeactivateEmployee,
  useEmployees,
  useUpdateEmployee,
} from '../../api/employees'

/** The role that may manage Employees — the one string the mount gate matches on. */
const ADMIN_ROLE = 'ADMIN'

/** The three roles an Employee may hold — the create/edit select options. */
const ROLES = ['EMPLOYEE', 'MANAGER', 'ADMIN'] as const

/** The refusal codes this screen surfaces, matched on `code`, never `message` (AD-21). */
const EMAIL_ALREADY_IN_USE_CODE = 'EMAIL_ALREADY_IN_USE'
const REPORTING_CYCLE_CODE = 'REPORTING_CYCLE'
const EMPLOYEE_HAS_DIRECT_REPORTS_CODE = 'EMPLOYEE_HAS_DIRECT_REPORTS'

/** Turn any write/deactivate rejection into a human line, naming the obstruction. */
function refusalMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === EMAIL_ALREADY_IN_USE_CODE) {
      return 'That email address is already in use.'
    }
    if (error.code === REPORTING_CYCLE_CODE) {
      return 'That manager assignment would create a reporting cycle.'
    }
    if (error.code === EMPLOYEE_HAS_DIRECT_REPORTS_CODE) {
      const count = error.details.active_direct_reports
      if (typeof count === 'number') {
        const reports = count === 1 ? 'report' : 'reports'
        return `Cannot deactivate or demote: ${count} active direct ${reports} still report to this employee.`
      }
      return error.message
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

/** The blank create form. Role defaults to EMPLOYEE; manager is "none" until chosen. */
const EMPTY_CREATE = {
  email: '',
  full_name: '',
  role: 'EMPLOYEE',
  department_id: '',
  joining_date: '',
  password: '',
  manager_id: '',
}

/** The shape of the inline edit form — the six mutable fields, `manager_id` '' = none. */
interface EditForm {
  email: string
  full_name: string
  role: string
  department_id: string
  manager_id: string
  joining_date: string
}

/** A blank edit form, used only as the initial state before a row is opened for editing. */
const EMPTY_EDIT: EditForm = {
  email: '',
  full_name: '',
  role: 'EMPLOYEE',
  department_id: '',
  manager_id: '',
  joining_date: '',
}

/** The edit form for one Employee, seeded from its current values (manager '' = none). */
function editFormFrom(employee: Employee): EditForm {
  return {
    email: employee.email,
    full_name: employee.full_name,
    role: employee.role,
    department_id: employee.department.id,
    manager_id: employee.manager_id ?? '',
    joining_date: employee.joining_date,
  }
}

export function EmployeesPage() {
  const me = useMe()
  // Gate the Admin-only employees fetch on the resolved role: a non-Admin must not issue a
  // GET /employees the server would 403 (this hook runs before the return-null gate below).
  const isAdmin = me.data?.role === ADMIN_ROLE
  const employees = useEmployees({ enabled: isAdmin })
  const departments = useDepartments()
  const createEmployee = useCreateEmployee()
  const updateEmployee = useUpdateEmployee()
  const deactivateEmployee = useDeactivateEmployee()

  const [createForm, setCreateForm] = useState({ ...EMPTY_CREATE })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ ...EMPTY_EDIT })
  // The id whose row-level action was refused, and the line to show against it (NFR-17).
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)

  // The mount gate is a usability measure; the server's 403 is the real guard (AC5).
  if (!isAdmin) {
    return null
  }

  const departmentOptions = departments.data?.items ?? []
  const employeeOptions = employees.data?.items ?? []

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (createForm.email.trim() === '' || createForm.department_id === '' || createForm.password === '') {
      return
    }
    setRowError(null)
    createEmployee.mutate(
      {
        email: createForm.email.trim(),
        full_name: createForm.full_name.trim(),
        role: createForm.role,
        department_id: createForm.department_id,
        joining_date: createForm.joining_date,
        password: createForm.password,
        manager_id: createForm.manager_id === '' ? null : createForm.manager_id,
      },
      { onSuccess: () => setCreateForm({ ...EMPTY_CREATE }) },
    )
  }

  function startEditing(employee: Employee) {
    setRowError(null)
    updateEmployee.reset()
    setEditingId(employee.id)
    setEditForm(editFormFrom(employee))
  }

  function cancelEditing() {
    updateEmployee.reset()
    setEditingId(null)
  }

  function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (editingId === null) return
    const changes: UpdateEmployeeInput = {
      email: editForm.email.trim(),
      full_name: editForm.full_name.trim(),
      role: editForm.role,
      department_id: editForm.department_id,
      manager_id: editForm.manager_id === '' ? null : editForm.manager_id,
      joining_date: editForm.joining_date,
    }
    // A failed update leaves the form open with the reason shown; only success closes it.
    updateEmployee.mutate(
      { id: editingId, changes },
      { onSuccess: () => setEditingId(null) },
    )
  }

  function handleDeactivate(employee: Employee) {
    setRowError(null)
    deactivateEmployee.mutate(employee.id, {
      onError: (error) => setRowError({ id: employee.id, message: refusalMessage(error) }),
    })
  }

  return (
    <section className="panel">
      <h2>Employees</h2>
      <p className="muted">
        Create, edit and deactivate employees, set their reporting line, and give a new hire
        an initial password (communicate it to them directly — LeaveFlow sends no email).
      </p>

      <form className="emp-create" onSubmit={handleCreate}>
        <div className="emp-fields">
          <label className="emp-field">
            Email
            <input
              type="email"
              value={createForm.email}
              onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })}
              required
            />
          </label>
          <label className="emp-field">
            Full name
            <input
              type="text"
              value={createForm.full_name}
              onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })}
              required
            />
          </label>
          <label className="emp-field">
            Role
            <select
              value={createForm.role}
              onChange={(event) => setCreateForm({ ...createForm, role: event.target.value })}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="emp-field">
            Department
            <select
              value={createForm.department_id}
              onChange={(event) => setCreateForm({ ...createForm, department_id: event.target.value })}
              required
            >
              <option value="" disabled>
                Select a department…
              </option>
              {departmentOptions.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </select>
          </label>
          <label className="emp-field">
            Manager (optional)
            <select
              value={createForm.manager_id}
              onChange={(event) => setCreateForm({ ...createForm, manager_id: event.target.value })}
            >
              <option value="">— None —</option>
              {employeeOptions.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.full_name} ({employee.email})
                </option>
              ))}
            </select>
          </label>
          <label className="emp-field">
            Joining date
            <input
              type="date"
              value={createForm.joining_date}
              onChange={(event) => setCreateForm({ ...createForm, joining_date: event.target.value })}
              required
            />
          </label>
          <label className="emp-field">
            Initial password
            <input
              type="password"
              value={createForm.password}
              onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })}
              required
            />
          </label>
        </div>
        <div className="emp-form-actions">
          <button type="submit" disabled={createEmployee.isPending}>
            {createEmployee.isPending ? 'Adding…' : 'Add employee'}
          </button>
          {createEmployee.isError && (
            <p className="emp-error" role="alert">
              {refusalMessage(createEmployee.error)}
            </p>
          )}
        </div>
      </form>

      {employees.isPending && <p className="muted">Loading employees…</p>}

      {employees.isError && (
        <p className="emp-error" role="alert">
          Could not load employees — {employees.error.message}
        </p>
      )}

      {employees.data && employees.data.items.length === 0 && (
        <p className="muted">No employees yet.</p>
      )}

      {employees.data && employees.data.items.length > 0 && (
        <ul className="emp-list">
          {employees.data.items.map((employee) => (
            <li key={employee.id} className="emp-row">
              {editingId === employee.id ? (
                <form className="emp-edit" onSubmit={handleUpdate}>
                  <div className="emp-fields">
                    <label className="emp-field">
                      Email
                      <input
                        type="email"
                        value={editForm.email}
                        onChange={(event) => setEditForm({ ...editForm, email: event.target.value })}
                        required
                      />
                    </label>
                    <label className="emp-field">
                      Full name
                      <input
                        type="text"
                        value={editForm.full_name}
                        onChange={(event) => setEditForm({ ...editForm, full_name: event.target.value })}
                        required
                      />
                    </label>
                    <label className="emp-field">
                      Role
                      <select
                        value={editForm.role}
                        onChange={(event) => setEditForm({ ...editForm, role: event.target.value })}
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="emp-field">
                      Department
                      <select
                        value={editForm.department_id}
                        onChange={(event) => setEditForm({ ...editForm, department_id: event.target.value })}
                        required
                      >
                        {departmentOptions.map((department) => (
                          <option key={department.id} value={department.id}>
                            {department.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="emp-field">
                      Manager
                      <select
                        value={editForm.manager_id}
                        onChange={(event) => setEditForm({ ...editForm, manager_id: event.target.value })}
                      >
                        <option value="">— None —</option>
                        {employeeOptions
                          .filter((candidate) => candidate.id !== employee.id)
                          .map((candidate) => (
                            <option key={candidate.id} value={candidate.id}>
                              {candidate.full_name} ({candidate.email})
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className="emp-field">
                      Joining date
                      <input
                        type="date"
                        value={editForm.joining_date}
                        onChange={(event) => setEditForm({ ...editForm, joining_date: event.target.value })}
                        required
                      />
                    </label>
                  </div>
                  <div className="emp-form-actions">
                    <button type="submit" disabled={updateEmployee.isPending}>
                      Save
                    </button>
                    <button type="button" onClick={cancelEditing}>
                      Cancel
                    </button>
                    {updateEmployee.isError && (
                      <p className="emp-error" role="alert">
                        {refusalMessage(updateEmployee.error)}
                      </p>
                    )}
                  </div>
                </form>
              ) : (
                <>
                  <div className="emp-summary">
                    <span className="emp-name">
                      {employee.full_name}
                      {!employee.is_active && <span className="emp-inactive"> (deactivated)</span>}
                    </span>
                    <span className="muted">
                      {employee.email} · {employee.role} · {employee.department.name}
                    </span>
                  </div>
                  <span className="emp-actions">
                    <button type="button" onClick={() => startEditing(employee)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeactivate(employee)}
                      disabled={
                        !employee.is_active ||
                        (deactivateEmployee.isPending &&
                          deactivateEmployee.variables === employee.id)
                      }
                    >
                      Deactivate
                    </button>
                  </span>
                </>
              )}

              {rowError?.id === employee.id && (
                <p className="emp-error" role="alert">
                  {rowError.message}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
