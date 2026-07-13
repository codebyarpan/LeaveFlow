/**
 * Leave Balances, as a typed hook on `apiFetch`. `GET /api/v1/balances` (FR-07, AC7).
 *
 * Implements: FR-07 (frontend) — the Employee's own dashboard reads their balances, with
 * `available` prominent and `reserved` disclosed alongside. Like `useMe`, this is a self-fetch:
 * no parameters, the Bearer token identifies the caller (scope `self`). The Manager/Admin
 * "view another Employee's balances" screen (`GET /employees/<id>/balances`, "My Team") is a
 * disclosed forward reference (Story 3.2) — this hook is the self read only.
 *
 * The response is a PLAIN array (one entry per Leave Type), NOT the `Page` envelope: balances
 * are a bounded set, so the backend returns them unpaginated (api-contracts §4.4).
 *
 * `available`, `reserved` and `consumed` arrive from the server as whole-day integers and are
 * rendered AS-IS (AD-2): the client computes no day count and no balance figure — `available`
 * is already derived server-side (`accrued − consumed − reserved`).
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'

/**
 * One Leave Type's balance on the wire, mirroring the backend `BalanceResponse` (§4.4).
 * `available` is the primary figure (derived server-side); `reserved`/`consumed` alongside.
 * There is no `accrued` — the contract surfaces only the three quantities.
 */
export interface Balance {
  leave_type_code: string
  leave_type_name: string
  available: number
  reserved: number
  consumed: number
}

/**
 * The cache key for the caller's balances. Exported so a later mutation (a submission that
 * reserves days, Story 2.6) can invalidate it and any screen can read the same entry.
 */
export const BALANCES_QUERY_KEY = ['balances'] as const

/** The caller's own current-year balances (FR-07, scope `self`). */
export function useBalances() {
  return useQuery({
    queryKey: BALANCES_QUERY_KEY,
    queryFn: () => apiFetch<Balance[]>('/balances'),
  })
}
