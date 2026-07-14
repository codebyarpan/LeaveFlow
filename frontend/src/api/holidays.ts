/**
 * Company Holidays, as typed hooks on `apiFetch`. The three `/api/v1/holidays` endpoints.
 *
 * Implements: FR-10 (frontend), AC4/AC10 (Story 2.2) and AC8 (Story 2.11). The list is read by any
 * role; create and delete are Admin-only — but that role gate is the SERVER's (a `403`), and this
 * module never pretends otherwise. `NFR-16`'s control-hiding lives in the screen and is never the
 * only guard.
 *
 * --- ⚠️ The success codes CHANGED in Story 2.11, and so did the bodies ---
 *
 * Story 2.2 shipped `201` create / `204` delete / `200` list, and this comment used to say so. It is
 * now:
 *
 *     POST   /holidays        200 + HolidayCommandResult
 *     DELETE /holidays/{id}   200 + HolidayCommandResult   (was 204, empty body)
 *     GET    /holidays        200 + Page<Holiday>          (unchanged)
 *
 * Because a holiday write is no longer CRUD. It RECALCULATES every Leave Request the change affects
 * — and it may REFUSE a given (Employee, Leave Type) pair, leaving that pair entirely unchanged
 * while the rest of the operation commits (AD-19). So both writes return a summary saying what was
 * recalculated and, crucially, what was NOT. A `204` could not have carried that at all, and neither
 * mutation may discard its result any more: AC8 forbids showing the Admin an unqualified success for
 * an operation that partially refused.
 *
 * A recalculation moves BALANCES, LEAVE REQUESTS and REVIEW FLAGS as well as the holiday list, so
 * every key one touches is invalidated. A duplicate `holiday_date` still surfaces as an `ApiError`
 * with `code === 'HOLIDAY_DATE_IN_USE'`, which the screen branches on (never the message).
 *
 * `holiday_date` is the `YYYY-MM-DD` string the wire uses (AD-12): a `<input type="date">`
 * value is already exactly this shape, so the screen passes it through with no conversion.
 *
 * --- ⚠️ `RefusedPair` / `RecalculationSummary` MOVED in Story 2.12 ---
 *
 * They were declared here, which was right while a holiday was the only thing that could
 * recalculate. `PATCH /leave-types/{id}` recalculates too now, so they live in `api/recalculation.ts`
 * — mirroring the backend, where they live in `services/recalculation.py` and NOT in
 * `services/holidays.py`. They are RE-EXPORTED below, so every existing import from this module keeps
 * working; the invalidation fan-out moved with them, for the same reason.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
// `Page<T>` has a single home in `departments.ts` (the first list endpoint established it);
// every later list endpoint reuses that type rather than re-declaring the envelope.
import type { Page } from './departments'
import { invalidateEverythingARecalculationMoves } from './recalculation'
import type { RecalculationSummary } from './recalculation'

// Re-exported from their new home so this module's existing consumers are undisturbed (Story 2.12).
export type { RecalculationSummary, RefusedPair } from './recalculation'

/** A Company Holiday on the wire — `{id, holiday_date, name}`, mirroring `HolidayResponse`. */
export interface Holiday {
  id: string
  holiday_date: string
  name: string
}

/** The `200` body BOTH holiday writes now answer with: the row, and the recalculation it triggered. */
export interface HolidayCommandResult {
  holiday: Holiday
  recalculation: RecalculationSummary
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

/**
 * Create a Company Holiday (Admin-only server-side), and RECALCULATE what it affects.
 *
 * Returns the `200` summary — the caller must not discard it (AC8): an ADD can refuse a pair, by
 * pricing a request down to zero Working Days or by lowering a stale carry-forward into a Leave Year
 * that is already spent.
 */
export function useCreateHoliday() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateHolidayInput) =>
      apiFetch<HolidayCommandResult>('/holidays', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      invalidateEverythingARecalculationMoves(queryClient)
    },
  })
}

/**
 * Delete a Company Holiday (Admin-only server-side), and RECALCULATE what it affects.
 *
 * Returns the `200` summary; the caller must not discard it (AC8). A DELETE is the likelier refusal:
 * it makes a working day reappear, so more days are charged and a later, already-spent Leave Year can
 * be driven negative.
 *
 * Invalidates on SETTLE — not just on success: the most natural error here is a `404` (the row was
 * already deleted by another Admin), and that is exactly when a refetch reconciles the list by
 * removing the ghost row. Invalidating on error is harmless in the network-failure case (react-query
 * simply retries the fetch), so `onSettled` is strictly the right hook.
 */
export function useDeleteHoliday() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<HolidayCommandResult>(`/holidays/${id}`, { method: 'DELETE' }),
    onSettled: () => {
      invalidateEverythingARecalculationMoves(queryClient)
    },
  })
}
