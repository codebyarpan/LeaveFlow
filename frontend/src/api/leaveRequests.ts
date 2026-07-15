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
// The decision calendar's key (Story 3.3). `calendar.ts` imports only TYPES from this module,
// so this value import cannot form a runtime cycle.
import { CALENDAR_QUERY_KEY } from './calendar'
// Story 3.4. A value import, and it cannot cycle: `notifications.ts` imports only `client` and the
// `Page` TYPE from `departments`, never this module.
import { NOTIFICATIONS_QUERY_KEY } from './notifications'
// Story 3.5. A value import that cannot cycle either: `dashboard.ts` imports only `client` and the
// `Balance` TYPE from `balances`, never this module.
import { DASHBOARD_QUERY_KEY } from './dashboard'
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
 * The submission body — the preview's shape (the Leave Type and the inclusive range) plus,
 * since Story 4.1, an optional `document` File. The server re-decides validity and the balance
 * under lock; the client just posts the range. A file present switches the wire format to
 * `multipart/form-data` (OD#1 — how a document-requiring Leave Type is submittable in one
 * request); absent, the request is byte-for-byte the JSON it always was.
 */
export interface SubmitLeaveInput {
  leave_type_id: string
  start_date: string
  end_date: string
  document?: File | null
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
    mutationFn: ({ document, ...fields }: SubmitLeaveInput) => {
      // Story 4.1 (OD#1): a file rides the SAME submission as a multipart part — the json
      // fields become form fields, the browser sets the boundary (`apiFetch` never labels a
      // FormData body as JSON). Without a file the request is exactly the JSON it always was.
      if (document instanceof File) {
        const formData = new FormData()
        formData.append('leave_type_id', fields.leave_type_id)
        formData.append('start_date', fields.start_date)
        formData.append('end_date', fields.end_date)
        formData.append('document', document)
        return apiFetch<LeaveRequestSubmission>('/leave-requests', {
          method: 'POST',
          body: formData,
        })
      }
      return apiFetch<LeaveRequestSubmission>('/leave-requests', {
        method: 'POST',
        body: JSON.stringify(fields),
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BALANCES_QUERY_KEY })
      // Story 3.4 — the ONE same-user notification case, and the only reason this key belongs here.
      // A MANAGERLESS applicant's submission is auto-approved (FR-09) and writes a REQUEST_APPROVED
      // addressed to THEMSELVES (AC4) — so the submitter IS the recipient, and without this their
      // own badge would sit stale until `staleTime` expired. (A managed applicant's submission
      // notifies their MANAGER, whose browser this is not; that one cannot be invalidated from here
      // and is not meant to be — see `invalidateAfterDecision` below.)
      void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })
      // Story 3.5: a submission moves the caller's OWN dashboard — the pending count rises
      // (or, managerless, they land on approved leave) and Available falls. Submit does NOT go
      // through `invalidateAfterDecision`, so the dashboard key must be joined here too.
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_QUERY_KEY })
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
 * The base cache key for the leave-requests list. Each filter/page combination caches under
 * `[...LEAVE_REQUESTS_QUERY_KEY, filters]`, so a `PENDING` queue, an `APPROVED` view and every
 * history page are distinct entries; a transition invalidates this BASE key, which TanStack
 * matches by prefix — so every variant refetches at once. One home keeps the queries and the
 * mutations in agreement.
 */
export const LEAVE_REQUESTS_QUERY_KEY = ['leaveRequests'] as const

/**
 * The optional filters and page window for the leave-requests list (Story 3.1, FR-12). Every
 * field is optional; an absent filter applies no predicate server-side, so an empty object is
 * the caller's whole (scoped, cross-Leave-Year) history. `dateFrom`/`dateTo` are `YYYY-MM-DD`
 * strings straight from an `<input type="date">`; the window selects by OVERLAP server-side.
 * `page`/`pageSize` drive the shared envelope; the server clamps both.
 */
export interface LeaveRequestFilters {
  status?: string
  leaveTypeId?: string
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}

/**
 * Each filter's wire name, in one place so the query string and the backend stay in agreement.
 * Exported since Story 4.2: the CSV export builds its query string from THIS map (minus
 * `page`/`pageSize` — the export carries every matching row), so the screen's list and the
 * export cannot disagree on a wire name.
 */
export const FILTER_PARAM_NAMES = {
  status: 'status',
  leaveTypeId: 'leave_type_id',
  dateFrom: 'date_from',
  dateTo: 'date_to',
  page: 'page',
  pageSize: 'page_size',
} as const

/**
 * The scoped leave-requests list (FR-03, FR-12). The server resolves scope from the caller's role
 * — an Employee sees their own, a Manager their Direct Reports', an Admin all — so this one hook
 * serves every role, and the filters compose server-side as an intersection that only ever
 * NARROWS that scope. Every value is `encodeURIComponent`-escaped into the query string (the 2.7
 * review's rule); the query key carries the whole `filters` object (TanStack v5 hashes keys
 * structurally), so each combination caches distinctly while `LEAVE_REQUESTS_QUERY_KEY` prefix
 * invalidation still reaches all of them.
 *
 * `options.enabled` gates the fetch (mirrors `useEmployees`): the Manager queue passes the
 * resolved `isManager` so a non-Manager, which renders nothing, never issues the request at all.
 */
export function useLeaveRequests(
  filters: LeaveRequestFilters = {},
  options?: { enabled?: boolean },
) {
  const pairs = (Object.keys(FILTER_PARAM_NAMES) as (keyof LeaveRequestFilters)[])
    .filter((key) => filters[key] !== undefined)
    .map(
      (key) =>
        `${FILTER_PARAM_NAMES[key]}=${encodeURIComponent(String(filters[key]))}`,
    )
  const path: `/${string}` =
    pairs.length > 0 ? `/leave-requests?${pairs.join('&')}` : '/leave-requests'
  return useQuery({
    queryKey: [...LEAVE_REQUESTS_QUERY_KEY, filters],
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
 *
 * The calendar joins the fan-out (Story 3.3): a decision flips a PENDING row to APPROVED/REJECTED
 * — exactly the facts the inline decision calendar shows — so without this the Manager approves a
 * request and the calendar under it keeps saying the leave is Pending.
 *
 * 🚨 `NOTIFICATIONS_QUERY_KEY` is DELIBERATELY ABSENT here, and it is not an oversight (Story 3.4).
 * A decision notifies the APPLICANT; the actor running this handler is the MANAGER. The decider is
 * never the recipient — a Manager cannot decide her own request, and scope `reports` excludes her
 * own row (pinned since 2.7) — so there is nothing in THIS browser's cache to refresh. Invalidating
 * a key no query on this client holds would be a no-op that reads as intent.
 *
 * Note the one case that looks like a counter-example and is not: this same handler is also
 * `useCancelLeaveRequest`'s, where the actor IS the applicant — but a self-cancel writes ZERO
 * notifications (AC3's implied negative; `cancel_leave_request` passes no `notify_kind`), so there
 * is still nothing to invalidate. Cross-user freshness is `staleTime` + `refetchOnWindowFocus`, not
 * invalidation (Open Decision #4 — the app has no polling precedent and adding one would be a new
 * standing cost, not a bug fix).
 */
function invalidateAfterDecision(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: LEAVE_REQUESTS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: BALANCES_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: CALENDAR_QUERY_KEY })
  // Story 3.5: a decision moves the Manager's own dashboard — the pending-decision count falls,
  // and an approval can put a report onto the on-leave card. One prefix reaches all three roles'
  // dashboards ("invalidating them anyway costs one refetch … correctness over a saved request").
  void queryClient.invalidateQueries({ queryKey: DASHBOARD_QUERY_KEY })
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
