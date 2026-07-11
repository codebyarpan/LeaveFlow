/**
 * Employees, as typed hooks on `apiFetch`. The five `/api/v1/employees` endpoints.
 *
 * Implements: FR-04 (frontend), AC13 (built on the typed client). UNLIKE departments,
 * every `/employees` endpoint — including the reads — is Admin-only on the server: a
 * non-Admin's list query would `403`. So the screen mounts these hooks only for an Admin
 * (EmployeesPage), and the server's `403` remains the real guard (`NFR-16`, never the only
 * one). Refusals surface by `code` — `EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`,
 * `EMPLOYEE_HAS_DIRECT_REPORTS` — matched in the screen, never here.
 *
 * The success codes match the backend's chosen 2xx (Story 1.6 / G6): `201` create, `200`
 * read/update/deactivate. The `Page<T>` envelope is reused from `./departments`, its single
 * home (api-contracts §1).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { Page } from './departments'

/** A department named just enough to identify it — `{id, name}`, the response brief. */
export interface EmployeeDepartment {
  id: string
  name: string
}

/**
 * An Employee on the wire — mirrors the backend `EmployeeResponse`. Carries `manager_id`
 * and `is_active` (the reporting line and the active flag the Admin manages), and NEVER a
 * password or hash.
 */
export interface Employee {
  id: string
  email: string
  full_name: string
  role: string
  department: EmployeeDepartment
  manager_id: string | null
  joining_date: string
  is_active: boolean
}

/** The body a create presents — the initial password is set here, once (never re-issued). */
export interface CreateEmployeeInput {
  email: string
  full_name: string
  role: string
  department_id: string
  joining_date: string
  password: string
  manager_id?: string | null
}

/**
 * A partial update — only the fields present are changed. `manager_id: null` clears the
 * reporting line; an omitted field is left untouched. There is NO `password` field: a
 * `PATCH` never re-issues a credential (FR-17).
 */
export interface UpdateEmployeeInput {
  email?: string
  full_name?: string
  role?: string
  department_id?: string
  manager_id?: string | null
  joining_date?: string
}

/**
 * The cache key for the employees list. Exported so mutations can invalidate it and the
 * screen can read the same entry — one home keeps create/update/deactivate and the query in
 * agreement about what to refresh.
 */
export const EMPLOYEES_QUERY_KEY = ['employees'] as const

/**
 * The employees list (Admin-only server-side). Mounted only for an Admin (see EmployeesPage).
 *
 * `enabled` gates the fetch: because React's rules-of-hooks require this hook to run before
 * the screen's `role !== ADMIN → return null` gate, a non-Admin would otherwise issue a
 * `GET /employees` that the server (correctly) `403`s, plus React Query's default retries.
 * The caller passes `enabled: role === 'ADMIN'` so the request only fires once the role is
 * known to be Admin. Defaults to `true` for any caller that does its own gating.
 */
export function useEmployees(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: EMPLOYEES_QUERY_KEY,
    queryFn: () => apiFetch<Page<Employee>>('/employees'),
    enabled: options?.enabled ?? true,
  })
}

/** Create an Employee (Admin-only server-side). Invalidates the list on success. */
export function useCreateEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateEmployeeInput) =>
      apiFetch<Employee>('/employees', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: EMPLOYEES_QUERY_KEY })
    },
  })
}

/** Update an Employee (Admin-only server-side). Invalidates the list on success. */
export function useUpdateEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: UpdateEmployeeInput }) =>
      apiFetch<Employee>(`/employees/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: EMPLOYEES_QUERY_KEY })
    },
  })
}

/**
 * Deactivate an Employee (Admin-only server-side). Invalidates the list on success.
 *
 * A refused deactivation is an `ApiError` with `code === 'EMPLOYEE_HAS_DIRECT_REPORTS'` —
 * the caller branches on that code (never the message) to name the blocking reports (NFR-17).
 */
export function useDeactivateEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<Employee>(`/employees/${id}/deactivate`, { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: EMPLOYEES_QUERY_KEY })
    },
  })
}
