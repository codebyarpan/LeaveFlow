/**
 * Cancellation Requests, as typed hooks on `apiFetch` (Story 2.8).
 *
 * Implements: FR-09 (frontend) — an Employee raises a Cancellation Request against their own
 * Approved future-dated leave and tracks its state; an Admin sees every Pending Cancellation Request
 * and approves or rejects it. AD-2: the day count, the dates, the Leave Type labels and the status
 * all arrive from the server; the client renders them and computes NOTHING (no day count).
 *
 * A raise and each decision are a `POST`, run ON DEMAND — so `useMutation`. All three invalidate on
 * `onSettled` (NOT `onSuccess`), so a `409`/`404` still self-heals: they invalidate the
 * cancellation-requests list, the leave-requests list AND the balances (an approval restores the
 * applicant's Available). The list is a `useQuery`, per-status cached and `enabled`-gated — the
 * `leaveRequests.ts` shape exactly.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import { BALANCES_QUERY_KEY } from './balances'
// Story 3.5. A value import that cannot cycle: `dashboard.ts` imports only `client` and a type.
import { DASHBOARD_QUERY_KEY } from './dashboard'
import { LEAVE_REQUESTS_QUERY_KEY } from './leaveRequests'
// `Page<T>` has a single home in `departments.ts`; every later list endpoint reuses that type.
import type { Page } from './departments'

/**
 * A Cancellation Request on the wire, mirroring the backend `CancellationRequestResponse` (§4.6). It
 * carries the CR's own `id`/`leave_request_id`/`status`, the applicant (`employee_id`/`employee_name`,
 * so the Admin screen shows WHOSE filing it is) and the target Leave Request summary (its range, the
 * server's FROZEN `leave_days` — AD-18, rendered as received — and the Leave Type labels).
 */
export interface CancellationRequest {
  id: string
  leave_request_id: string
  status: string
  employee_id: string
  employee_name: string
  start_date: string
  end_date: string
  leave_days: number
  leave_type_code: string
  leave_type_name: string
}

/**
 * The base cache key for the cancellation-requests list. A per-`status` query caches under
 * `[...CANCELLATION_REQUESTS_QUERY_KEY, status]`, so an Admin's PENDING queue and an applicant's
 * full list never share an entry; a raise or a decision invalidates this BASE key, which TanStack
 * matches by prefix — so every status view refetches at once.
 */
export const CANCELLATION_REQUESTS_QUERY_KEY = ['cancellationRequests'] as const

/**
 * The scoped cancellation-requests list (§4.6). The server resolves scope from the caller's role —
 * an Admin sees all, everyone else their own — so this one hook serves both screens. An optional
 * `status` narrows the page. `options.enabled` gates the fetch (the `useLeaveRequests` idiom): the
 * Admin queue passes the resolved `isAdmin` so a non-Admin, which renders nothing, never issues the
 * request at all.
 */
export function useCancellationRequests(
  status?: string,
  options?: { enabled?: boolean },
) {
  const path: `/${string}` =
    status !== undefined
      ? `/cancellation-requests?status=${encodeURIComponent(status)}`
      : '/cancellation-requests'
  return useQuery({
    queryKey: [...CANCELLATION_REQUESTS_QUERY_KEY, status ?? 'ALL'],
    queryFn: () => apiFetch<Page<CancellationRequest>>(path),
    enabled: options?.enabled,
  })
}

/**
 * Invalidate the cancellation-requests list, the leave-requests list AND balances after a raise or a
 * decision. Wired on `onSettled`, NOT `onSuccess`: a `409 TRANSITION_NOT_ALLOWED` / `404
 * RESOURCE_NOT_FOUND` — the row was decided or the leave changed under the caller — is exactly the
 * case whose whole point is to self-heal by refetching. An approval cancels the leave and restores
 * the applicant's Available, so the balances key is invalidated too.
 */
function invalidateAfterCancellation(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: CANCELLATION_REQUESTS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: LEAVE_REQUESTS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: BALANCES_QUERY_KEY })
  // Story 3.5: an approved cancellation takes an Employee OFF approved leave and restores their
  // Available — both dashboard figures. One prefix reaches all three roles' dashboards.
  void queryClient.invalidateQueries({ queryKey: DASHBOARD_QUERY_KEY })
}

/**
 * Raise a Cancellation Request against one's OWN Approved request (AC2). Any role server-side; scope
 * `self` (the applicant). Takes the target Leave Request's id — the route is under its path.
 */
export function useRaiseCancellationRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (leaveRequestId: string) =>
      apiFetch<CancellationRequest>(
        `/leave-requests/${leaveRequestId}/cancellation-requests`,
        { method: 'POST' },
      ),
    onSettled: () => invalidateAfterCancellation(queryClient),
  })
}

/** Approve a Cancellation Request (AC6). Admin-only server-side; scope `all`. */
export function useApproveCancellationRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<CancellationRequest>(`/cancellation-requests/${id}/approve`, { method: 'POST' }),
    onSettled: () => invalidateAfterCancellation(queryClient),
  })
}

/** Reject a Cancellation Request (AC7). Admin-only server-side; scope `all`. */
export function useRejectCancellationRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<CancellationRequest>(`/cancellation-requests/${id}/reject`, { method: 'POST' }),
    onSettled: () => invalidateAfterCancellation(queryClient),
  })
}
