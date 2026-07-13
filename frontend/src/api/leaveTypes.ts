/**
 * Leave Types, as typed hooks on `apiFetch`. The two `/api/v1/leave-types` endpoints.
 *
 * Implements: FR-06 (frontend), SM-5 (a fourth Leave Type is created through the API alone),
 * AC5. The list is read by any role; create is Admin-only — but that role gate is the
 * SERVER's (a `403`), and this module never pretends otherwise. `NFR-16`'s control-hiding
 * lives in the screen and is never the only guard (AC5/AC7).
 *
 * The success codes match the backend's chosen 2xx (mirroring departments, G6): `201`
 * create, `200` list. A duplicate `code` surfaces as an `ApiError` with
 * `code === 'LEAVE_TYPE_CODE_IN_USE'`, which the screen branches on (never the message).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
// `Page<T>` has a single home in `departments.ts` (the first list endpoint established it);
// every later list endpoint reuses that type rather than re-declaring the envelope.
import type { Page } from './departments'

/**
 * A Leave Type on the wire — all seven fields, mirroring the backend `LeaveTypeResponse`.
 * `carry_forward_cap` is nullable: it is `null` for a type that does not carry forward.
 */
export interface LeaveType {
  id: string
  code: string
  name: string
  annual_entitlement: number
  carries_forward: boolean
  carry_forward_cap: number | null
  requires_supporting_document: boolean
}

/**
 * The body a create presents — the six writable fields (`id` is server-generated). Numbers
 * and booleans are already typed here; the screen builds this from its string form state.
 */
export interface CreateLeaveTypeInput {
  code: string
  name: string
  annual_entitlement: number
  carries_forward: boolean
  carry_forward_cap: number | null
  requires_supporting_document: boolean
}

/**
 * The cache key for the leave-types list. Exported so the create mutation can invalidate it
 * and any screen can read the same entry — one home keeps create and query in agreement.
 */
export const LEAVE_TYPES_QUERY_KEY = ['leaveTypes'] as const

/** The leave-type list, for any authenticated role (AC4). */
export function useLeaveTypes() {
  return useQuery({
    queryKey: LEAVE_TYPES_QUERY_KEY,
    queryFn: () => apiFetch<Page<LeaveType>>('/leave-types'),
  })
}

/** Create a Leave Type (Admin-only server-side). Invalidates the list on success. */
export function useCreateLeaveType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateLeaveTypeInput) =>
      apiFetch<LeaveType>('/leave-types', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LEAVE_TYPES_QUERY_KEY })
    },
  })
}
