/**
 * The Department Leave Calendar, as a typed hook on `apiFetch`. `GET /api/v1/calendar` (Story 3.3).
 *
 * Implements: FR-18 (frontend) — a Manager's Direct Reports' PENDING + APPROVED leave overlapping
 * a date range, fetched at the moment of decision (UJ-2). Manager-ONLY server-side (api-contracts
 * §4.9, the same inversion as `/team`): an Employee AND an Admin get a `403`, so the caller gates
 * the fetch with `enabled` and the server's role gate stays the real guard. The status set is
 * fixed SERVER-side — there is no status param to send; Cancelled and Rejected leave is
 * deliberately not on a calendar.
 *
 * The wire shape IS `LeaveRequestResponse` (backend Open Decision #1) — the `LeaveRequest` type
 * from `./leaveRequests` is reused, never redeclared, exactly as `Page<T>` keeps its single home
 * in `departments.ts`. AD-2: every date, day count and status renders as received; nothing here
 * computes anything.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { Page } from './departments'
import type { LeaveRequest } from './leaveRequests'

/**
 * The base cache key for the calendar. Each params combination caches under
 * `[...CALENDAR_QUERY_KEY, params]` (TanStack v5 hashes keys structurally), so the decision
 * mutations' prefix invalidation (`invalidateAfterDecision` in `leaveRequests.ts`) reaches every
 * window at once — a decision flips a PENDING row to APPROVED/REJECTED, exactly the facts a
 * calendar under it is showing.
 */
export const CALENDAR_QUERY_KEY = ['calendar'] as const

/**
 * The calendar's params: the overlap window plus the shared page envelope's controls. All are
 * optional server-side (an absent date applies no predicate), but the decision calendar always
 * passes the request-under-decision's own range. Dates are `YYYY-MM-DD` strings rendered/sent
 * as received (AD-12/AD-2).
 */
export interface CalendarParams {
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}

/** Each param's wire name, in one place so the query string and the backend stay in agreement. */
const PARAM_NAMES = {
  dateFrom: 'date_from',
  dateTo: 'date_to',
  page: 'page',
  pageSize: 'page_size',
} as const

/**
 * The Direct Reports' PENDING+APPROVED leave overlapping the window (FR-18). Every value is
 * `encodeURIComponent`-escaped into the query string (the 2.7 review's rule); the query key
 * carries the whole `params` object so each window caches distinctly while prefix invalidation
 * still fans out. `options.enabled` gates the fetch (the `useTeam` idiom): a non-Manager, which
 * renders nothing, never issues a request that is guaranteed to 403.
 */
export function useCalendar(
  params: CalendarParams = {},
  options?: { enabled?: boolean },
) {
  const pairs = (Object.keys(PARAM_NAMES) as (keyof CalendarParams)[])
    .filter((key) => params[key] !== undefined)
    .map((key) => `${PARAM_NAMES[key]}=${encodeURIComponent(String(params[key]))}`)
  const path: `/${string}` =
    pairs.length > 0 ? `/calendar?${pairs.join('&')}` : '/calendar'
  return useQuery({
    queryKey: [...CALENDAR_QUERY_KEY, params],
    queryFn: () => apiFetch<Page<LeaveRequest>>(path),
    enabled: options?.enabled,
  })
}
