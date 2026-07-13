/**
 * Leave Requests, as typed hooks on `apiFetch`. The preview (2.5) and the submission (2.6).
 *
 * Implements: FR-08 (frontend) — the Employee sees the day count, its named excluded dates, and
 * the projected balance BEFORE submitting, then SUBMITS the range. AD-2: the count, the excluded
 * dates, each reason, every holiday name AND the submitted request's `leave_days`/`status` arrive
 * from the server; the client renders them and computes NO day count.
 *
 * Both a preview and a submit are a `POST` with a body, run ON DEMAND when the Employee asks — so
 * `useMutation`, NOT `useQuery`. The preview is advisory (AD-3); the submit is the WRITE that
 * reserves the days, so on success it invalidates the balances query — Available falls immediately
 * (AC8). Both follow the `apiFetch` POST shape `useCreateLeaveType`/`useCreateHoliday` established.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import { BALANCES_QUERY_KEY } from './balances'
// `Page<T>` has a single home in `departments.ts` (the first list endpoint established it); every
// later list endpoint reuses that type rather than re-declaring the envelope.
import type { Page } from './departments'

/**
 * The preview request body — the Leave Type and the inclusive range, mirroring the backend
 * `PreviewRequest`. Dates are `YYYY-MM-DD` strings, straight from a `<input type="date">` (AD-12).
 */
export interface PreviewLeaveInput {
  leave_type_id: string
  start_date: string
  end_date: string
}

/**
 * One excluded date on the wire, mirroring the backend `ExcludedDateResponse` (§4.5). `reason` is
 * the server-provided `'WEEKEND'`/`'HOLIDAY'` string; `name` is the holiday's name for a `HOLIDAY`
 * and `null` for a `WEEKEND`. The client matches/displays these as received — it never derives them.
 */
export interface ExcludedDate {
  date: string
  reason: string
  name: string | null
}

/**
 * The preview payload, mirroring the backend `PreviewResponse` (§4.5). `leave_days`,
 * `available_before` and `available_after` are whole-day integers the server already computed —
 * rendered AS-IS (AD-2). `available_after` may be negative (an overspend); the client does not clamp.
 */
export interface LeaveRequestPreview {
  leave_days: number
  excluded_dates: ExcludedDate[]
  available_before: number
  available_after: number
}

/** Preview what a request would cost (FR-08, scope `self`). An on-demand `POST` — `useMutation`. */
export function usePreviewLeaveRequest() {
  return useMutation({
    mutationFn: (input: PreviewLeaveInput) =>
      apiFetch<LeaveRequestPreview>('/leave-requests/preview', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
  })
}

/**
 * The submission body — identical shape to the preview (the Leave Type and the inclusive range).
 * The server re-decides validity and the balance under lock; the client just posts the range.
 */
export interface SubmitLeaveInput {
  leave_type_id: string
  start_date: string
  end_date: string
}

/**
 * The created request on the wire, mirroring the backend `SubmitResponse` (§4.5). `leave_days` is
 * the server's FROZEN count (AD-18) and `status` is `'PENDING'` (a managed applicant) or
 * `'APPROVED'` (managerless auto-approval, FR-09) — both rendered as received (AD-2).
 */
export interface LeaveRequestSubmission {
  id: string
  leave_type_id: string
  start_date: string
  end_date: string
  leave_days: number
  status: string
}

/**
 * Submit a leave request (FR-08, scope `self`). On success invalidates the balances query so the
 * caller's Available falls IMMEDIATELY (AC8): the days are now reserved (or consumed) server-side.
 */
export function useSubmitLeaveRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SubmitLeaveInput) =>
      apiFetch<LeaveRequestSubmission>('/leave-requests', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BALANCES_QUERY_KEY })
    },
  })
}

/**
 * A Leave Request on the wire (Story 2.7), mirroring the backend `LeaveRequestResponse` (§4.5). It
 * carries the applicant (`employee_id`/`employee_name`, so a Manager's queue shows WHOSE request it
 * is) and the Leave Type (`leave_type_code`/`leave_type_name`), plus the range, the server's FROZEN
 * `leave_days` (AD-18, rendered as received — the client computes NO day count) and the `status`.
 */
export interface LeaveRequest {
  id: string
  employee_id: string
  employee_name: string
  leave_type_id: string
  leave_type_code: string
  leave_type_name: string
  start_date: string
  end_date: string
  leave_days: number
  status: string
}

/**
 * The base cache key for the leave-requests list. A per-`status` query caches under
 * `[...LEAVE_REQUESTS_QUERY_KEY, status]`, so a `PENDING` queue and an `APPROVED` view never share
 * an entry; a transition invalidates this BASE key, which TanStack matches by prefix — so every
 * status view refetches at once. One home keeps the queries and the mutations in agreement.
 */
export const LEAVE_REQUESTS_QUERY_KEY = ['leaveRequests'] as const

/**
 * The scoped leave-requests list (FR-03). The server resolves scope from the caller's role — an
 * Employee sees their own, a Manager their Direct Reports', an Admin all — so this one hook serves
 * every role. An optional `status` narrows the page (the single filter this story grants).
 *
 * `options.enabled` gates the fetch (mirrors `useEmployees`): the Manager queue passes the resolved
 * `isManager` so a non-Manager, which renders nothing, never issues the request at all.
 */
export function useLeaveRequests(status?: string, options?: { enabled?: boolean }) {
  const path: `/${string}` =
    status !== undefined
      ? `/leave-requests?status=${encodeURIComponent(status)}`
      : '/leave-requests'
  return useQuery({
    queryKey: [...LEAVE_REQUESTS_QUERY_KEY, status ?? 'ALL'],
    queryFn: () => apiFetch<Page<LeaveRequest>>(path),
    enabled: options?.enabled,
  })
}

/**
 * Invalidate the list AND the balances after a decision. A transition moves the APPLICANT's
 * reserved/consumed server-side; invalidating balances is cheap and correct (the Manager's own
 * balance is unaffected, but a stale cache never lingers). The list refetch is what makes the queue
 * self-heal — a just-decided (or concurrently-changed) row leaves it.
 *
 * Wired on `onSettled`, NOT `onSuccess`: a `409 TRANSITION_NOT_ALLOWED` / `404 RESOURCE_NOT_FOUND`
 * means the row was decided or cancelled UNDER the Manager — exactly the case whose whole point is to
 * self-heal by dropping the now-stale row from the queue. Invalidating only on success would leave
 * that row visible while the inline message claims the queue refreshed (which it must actually do).
 */
function invalidateAfterDecision(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: LEAVE_REQUESTS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: BALANCES_QUERY_KEY })
}

/** Approve a Direct Report's Pending request (AC1). Manager-only server-side; scope `reports`. */
export function useApproveLeaveRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<LeaveRequest>(`/leave-requests/${id}/approve`, { method: 'POST' }),
    onSettled: () => invalidateAfterDecision(queryClient),
  })
}

/** Reject a Direct Report's Pending request (AC1). Manager-only server-side; scope `reports`. */
export function useRejectLeaveRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<LeaveRequest>(`/leave-requests/${id}/reject`, { method: 'POST' }),
    onSettled: () => invalidateAfterDecision(queryClient),
  })
}

/** Cancel one's OWN Pending request (AC3). Any role server-side; scope `self` (the applicant). */
export function useCancelLeaveRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<LeaveRequest>(`/leave-requests/${id}/cancel`, { method: 'POST' }),
    onSettled: () => invalidateAfterDecision(queryClient),
  })
}
