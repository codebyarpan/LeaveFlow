/**
 * Departments, as typed hooks on `apiFetch`. The four `/api/v1/departments` endpoints.
 *
 * Implements: FR-05 (frontend), AC8 (built on the typed client). The list is read by any
 * role; create, rename and delete are Admin-only — but that role gate is the SERVER's
 * (a `403`), and this module never pretends otherwise. `NFR-16`'s control-hiding lives in
 * the screen, and is never the only guard (AC4/AC8).
 *
 * The success codes match the backend's chosen 2xx (Story 1.5 Trap 5 / G6): `201` create,
 * `200` rename, `204` delete. `apiFetch` decodes an empty `204` body to `undefined`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'

/** A Department on the wire — `{id, name}`, mirroring the backend `DepartmentResponse`. */
export interface Department {
  id: string
  name: string
}

/**
 * The paginated list envelope (api-contracts §1). Mirrors the backend `Page[T]`: exactly
 * `items`, `page`, `page_size`, `total`. Generic so later list endpoints reuse the type.
 */
export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

/**
 * The cache key for the departments list. Exported so mutations can invalidate it and any
 * screen can read the same entry. A single home for the key keeps create/rename/delete and
 * the query in agreement about what to refresh.
 */
export const DEPARTMENTS_QUERY_KEY = ['departments'] as const

/** The department list, for any authenticated role (AC2). */
export function useDepartments() {
  return useQuery({
    queryKey: DEPARTMENTS_QUERY_KEY,
    queryFn: () => apiFetch<Page<Department>>('/departments'),
  })
}

/** Create a Department (Admin-only server-side). Invalidates the list on success. */
export function useCreateDepartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<Department>('/departments', {
        method: 'POST',
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DEPARTMENTS_QUERY_KEY })
    },
  })
}

/** Rename a Department (Admin-only server-side). Invalidates the list on success. */
export function useRenameDepartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      apiFetch<Department>(`/departments/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DEPARTMENTS_QUERY_KEY })
    },
  })
}

/**
 * Delete a Department (Admin-only server-side). Invalidates the list on success.
 *
 * A refused delete is an `ApiError` with `code === 'DEPARTMENT_NOT_EMPTY'` — the caller
 * branches on that code (never the message) to surface the obstruction (NFR-17).
 */
export function useDeleteDepartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/departments/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DEPARTMENTS_QUERY_KEY })
    },
  })
}
