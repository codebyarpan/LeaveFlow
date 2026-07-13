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
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import { BALANCES_QUERY_KEY } from './balances'

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
