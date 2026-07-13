/**
 * Company Holidays, as typed hooks on `apiFetch`. The three `/api/v1/holidays` endpoints.
 *
 * Implements: FR-10 (frontend), AC4/AC10. The list is read by any role; create and delete
 * are Admin-only — but that role gate is the SERVER's (a `403`), and this module never
 * pretends otherwise. `NFR-16`'s control-hiding lives in the screen and is never the only
 * guard (AC4/AC6/AC10).
 *
 * The success codes match the backend's chosen 2xx (mirroring departments/leave-types, G6):
 * `201` create, `204` delete, `200` list. `apiFetch` decodes an empty `204` body to
 * `undefined`. A duplicate `holiday_date` surfaces as an `ApiError` with
 * `code === 'HOLIDAY_DATE_IN_USE'`, which the screen branches on (never the message).
 *
 * `holiday_date` is the `YYYY-MM-DD` string the wire uses (AD-12): a `<input type="date">`
 * value is already exactly this shape, so the screen passes it through with no conversion.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
// `Page<T>` has a single home in `departments.ts` (the first list endpoint established it);
// every later list endpoint reuses that type rather than re-declaring the envelope.
import type { Page } from './departments'

/** A Company Holiday on the wire — `{id, holiday_date, name}`, mirroring `HolidayResponse`. */
export interface Holiday {
  id: string
  holiday_date: string
  name: string
}

/**
 * The body a create presents — `{holiday_date, name}` (`id` is server-generated).
 * `holiday_date` is the `YYYY-MM-DD` string, straight from a date input.
 */
export interface CreateHolidayInput {
  holiday_date: string
  name: string
}

/**
 * The cache key for the holidays list. Exported so the create/delete mutations can invalidate
 * it and any screen can read the same entry — one home keeps mutations and query in agreement.
 */
export const HOLIDAYS_QUERY_KEY = ['holidays'] as const

/** The holiday list, for any authenticated role (AC3). */
export function useHolidays() {
  return useQuery({
    queryKey: HOLIDAYS_QUERY_KEY,
    queryFn: () => apiFetch<Page<Holiday>>('/holidays'),
  })
}

/** Create a Company Holiday (Admin-only server-side). Invalidates the list on success. */
export function useCreateHoliday() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateHolidayInput) =>
      apiFetch<Holiday>('/holidays', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: HOLIDAYS_QUERY_KEY })
    },
  })
}

/**
 * Delete a Company Holiday (Admin-only server-side). Invalidates the list on SETTLE — not
 * just on success: the most natural error here is a `404` (the row was already deleted by
 * another Admin), and that is exactly when a refetch reconciles the list by removing the
 * ghost row. Invalidating on error is harmless in the network-failure case (react-query
 * simply retries the fetch), so `onSettled` is strictly the right hook.
 */
export function useDeleteHoliday() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/holidays/${id}`, { method: 'DELETE' }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: HOLIDAYS_QUERY_KEY })
    },
  })
}
