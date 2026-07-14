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
import { invalidateEverythingARecalculationMoves } from './recalculation'
import type { RecalculationSummary } from './recalculation'

// Re-exported so a screen consuming the EDIT can name the summary type it gets back without reaching
// into a second module for it — the same courtesy `holidays.ts` extends its own callers.
export type { RecalculationSummary, RefusedPair } from './recalculation'

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

/**
 * The body an EDIT presents (Story 2.12) — every attribute optional, plus the DISPOSITION.
 *
 * ⚠️ ONLY THE KEYS THE ADMIN ACTUALLY CHANGED ARE SENT. The server reads the body with
 * `exclude_unset`, which is what keeps `{carry_forward_cap: null}` — the cap was REMOVED, meaning
 * UNCAPPED — distinguishable from "the cap was not submitted", i.e. no change at all. Send a full
 * object with `undefined`s and the two collapse into the same request, one of which silently
 * triggers a recalculation nobody asked for. `JSON.stringify` drops `undefined` keys, so building
 * this sparsely is exactly what is needed.
 *
 * `code` is NOT here, and cannot be edited: it is a Leave Type's identity, and renaming it would be a
 * different Leave Type. The server refuses it with `400 FORBIDDEN_FIELD`.
 *
 * `disposition` is REQUIRED by the server whenever a balance-affecting attribute
 * (`annual_entitlement`, `carry_forward_cap`, `carries_forward`) actually changes — otherwise the
 * edit is refused with `400 POLICY_DISPOSITION_REQUIRED` and NOTHING is applied. That is FR-06's
 * whole point, and the screen's job (AC10) is to make the Admin choose before it will submit.
 */
export interface UpdateLeaveTypeInput {
  name?: string
  annual_entitlement?: number
  carries_forward?: boolean
  carry_forward_cap?: number | null
  requires_supporting_document?: boolean
  disposition?: string
}

/** The `200` body the EDIT answers with: the updated row, and the recalculation it triggered. */
export interface LeaveTypeCommandResult {
  leave_type: LeaveType
  recalculation: RecalculationSummary
}

/**
 * Edit a Leave Type's policy (Admin-only server-side), and RECALCULATE what it affects (Story 2.12).
 *
 * Returns the `200` summary, and the caller MUST NOT discard it (AC11): a `RECALCULATE` can REFUSE a
 * given (Employee, Leave Type) pair — leaving that balance entirely unchanged and knowingly stale —
 * while the rest of the operation commits. Reporting that `200` as a bare "Saved" is precisely how a
 * wrong balance comes to be believed (PRD §1).
 *
 * A policy change moves the same things a holiday change moves — balances, and the review-flag
 * register when it refuses — PLUS the Leave Type itself and the policy-change log. So it invalidates
 * through the shared fan-out rather than a hand-maintained list of keys.
 *
 * A missing or invalid disposition surfaces as an `ApiError` with
 * `code === 'POLICY_DISPOSITION_REQUIRED'`, and NOTHING was applied — the screen branches on `code`,
 * never on `message`.
 */
export function useUpdateLeaveType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateLeaveTypeInput }) =>
      apiFetch<LeaveTypeCommandResult>(`/leave-types/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      invalidateEverythingARecalculationMoves(queryClient)
    },
  })
}
