/**
 * Leave Requests, as typed hooks on `apiFetch`. Story 2.5 ships the preview.
 *
 * Implements: FR-08 (frontend) — the Employee sees the day count, its named excluded dates, and
 * the projected balance BEFORE submitting. AD-2: the count, the excluded dates, each reason and
 * every holiday name arrive from the server; the client renders them and computes NO day count.
 *
 * A preview is a `POST` with a body, run ON DEMAND when the Employee asks — so `useMutation`, NOT
 * `useQuery` (which would auto-fetch with no input). The value is advisory only (AD-3): submission
 * (Story 2.6) re-decides under lock, so nothing here caches or reserves. `usePreviewLeaveRequest`
 * follows the `apiFetch` POST shape `useCreateLeaveType`/`useCreateHoliday` established.
 */
import { useMutation } from '@tanstack/react-query'

import { apiFetch } from './client'

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
