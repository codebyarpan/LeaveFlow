/**
 * What a RECALCULATION is, on the wire — and everything one moves in the cache.
 *
 * Implements: AD-19 (a recalculation may REFUSE a given (Employee, Leave Type) pair, leaving that
 * balance ENTIRELY unchanged, while the rest of the operation commits and the endpoint answers
 * `200`), Story 2.11 AC8 and Story 2.12 AC11 — the Admin is NEVER shown an unqualified success for an
 * operation that partially refused.
 *
 * --- Why this module exists (Story 2.12) ---
 *
 * TWO commands now trigger a recalculation and answer `200` with the same summary:
 *
 *     POST/DELETE /holidays        a HOLIDAY change   (Story 2.11)
 *     PATCH       /leave-types/id  a POLICY change    (Story 2.12)
 *
 * Story 2.11 declared `RefusedPair` / `RecalculationSummary` in `holidays.ts`, which was right when
 * a holiday was the only thing that could recalculate. It is not any more, and a Leave Type edit
 * importing its response types from `holidays.ts` would be a lie about where the concept lives. So
 * the types move HERE — mirroring the backend exactly, where `RefusedPair` and
 * `RecalculationSummary` live in `services/recalculation.py` and NOT in `services/holidays.py`.
 *
 * `holidays.ts` re-exports them, so nothing that already imported them from there breaks.
 */
import { useQueryClient } from '@tanstack/react-query'

import { ADMIN_REVIEW_FLAGS_QUERY_KEY } from './adminReviewFlags'
import { BALANCES_QUERY_KEY } from './balances'
// Story 3.5. A value import that cannot cycle: `dashboard.ts` imports only `client` and a type.
import { DASHBOARD_QUERY_KEY } from './dashboard'
import { HOLIDAYS_QUERY_KEY } from './holidays'
import { LEAVE_REQUESTS_QUERY_KEY } from './leaveRequests'
import { LEAVE_TYPES_QUERY_KEY } from './leaveTypes'
import { POLICY_CHANGES_QUERY_KEY } from './policyChanges'

/**
 * One (Employee, Leave Type) pair the recalculation left ENTIRELY unchanged.
 *
 * NAMES, not bare ids — `employee_name` and `leave_type_code` are what let the screen say WHO was
 * left uncorrected and in WHICH Leave Type, which is the whole point of surfacing this at all.
 *
 * `leave_year` is the year the refusal was DISCOVERED at, which is the year an Admin has to go and
 * look at — not necessarily the year that was edited. `cause` is the server's vocabulary string
 * (`HOLIDAY_RECALCULATION` or `POLICY_RECALCULATION`), rendered as received (AD-2).
 */
export interface RefusedPair {
  employee_id: string
  employee_name: string
  leave_type_id: string
  leave_type_code: string
  leave_year: number
  cause: string
}

/**
 * What a change corrected — and what it DECLINED to correct (AD-19).
 *
 * `pairs_refused` is the half that matters. An empty array is the honest way to say "nothing was
 * refused"; a non-empty one names every pair whose balance was left alone, and the screen must show
 * them rather than report a bare success.
 *
 * `requests_recalculated` is ALWAYS `0` for a POLICY change, and that is not a stub: a policy change
 * touches no Leave Request, because `leave_days` is a function of the calendar and not of
 * entitlement (AD-18). Only a HOLIDAY change moves it.
 */
export interface RecalculationSummary {
  requests_recalculated: number
  pairs_recalculated: number
  pairs_refused: RefusedPair[]
}

/**
 * Everything a recalculation moves. Call this from EVERY mutation that can trigger one.
 *
 * A recalculation is not an edit to one list. It rewrites Leave Requests' day counts (a holiday
 * change), the balances behind them (both), and — when it refuses a pair — the review-flag register.
 * A POLICY change additionally rewrites the Leave Type itself and appends to the policy-change log.
 * Invalidating only the list the Admin was looking at would leave an Employee reading a balance the
 * server has already corrected, which is precisely the "wrong figure that will be believed" (PRD §1)
 * these stories exist to prevent.
 *
 * Seven keys, and the extra ones are why this is a shared function rather than a copy per module.
 * A holiday change cannot move `LEAVE_TYPES_QUERY_KEY` or `POLICY_CHANGES_QUERY_KEY`, but
 * invalidating them anyway costs one refetch of two small lists and removes an entire class of
 * "which keys does THIS mutation move again?" bug. Correctness over a saved request.
 */
export function invalidateEverythingARecalculationMoves(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  void queryClient.invalidateQueries({ queryKey: HOLIDAYS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: BALANCES_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: LEAVE_REQUESTS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: ADMIN_REVIEW_FLAGS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: LEAVE_TYPES_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: POLICY_CHANGES_QUERY_KEY })
  // Story 3.5: a recalculation rewrites the balances a dashboard presents. Same reasoning as the
  // two keys above — one refetch, and one less "which keys does THIS mutation move?" bug.
  void queryClient.invalidateQueries({ queryKey: DASHBOARD_QUERY_KEY })
}
