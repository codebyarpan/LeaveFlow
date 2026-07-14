/**
 * The policy-change log, as a typed read hook on `apiFetch` (Story 2.12).
 *
 * Implements: FR-06 (frontend), AC12 — an Admin reads every recorded policy change, its old and new
 * value, and the disposition that was applied to the balances that already existed.
 *
 * READ-ONLY, and there is nothing else it could be. A policy change is a HISTORICAL FACT: it
 * happened, at a moment, under a disposition the Admin was FORCED to choose. It is the record of WHY
 * a balance is the number it is — and a balance whose justification can be quietly rewritten is
 * exactly the "wrong figure that will be believed" (PRD §1). So there is no `PATCH`, no `DELETE`, and
 * the application's database role holds `INSERT` and `SELECT` on `policy_change` and neither `UPDATE`
 * nor `DELETE` (AD-9, migration `0011`) — an "edit this record" control would be refused by
 * PostgreSQL even if someone wrote one. There is therefore no mutation here and no invalidation: the
 * whole `useMutation` apparatus the other api modules carry is simply absent, the same way it is
 * absent from `auditEntries.ts` and `adminReviewFlags.ts`.
 *
 * The ONE thing that writes to this log is `PATCH /leave-types/{id}`, which is why
 * `invalidateEverythingARecalculationMoves` (in `recalculation.ts`) invalidates this key.
 *
 * AD-2: every value is rendered AS RECEIVED. `occurred_at` is the server's RFC 3339 timestamp,
 * `disposition` and `attribute` are the server's strings, and `old_value`/`new_value` are the
 * server's already-stringified figures. The client parses and computes NOTHING.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
// `Page<T>` has a single home in `departments.ts`; every later list endpoint reuses that type.
import type { Page } from './departments'

/**
 * One recorded policy change on the wire, mirroring the backend `PolicyChangeResponse`.
 *
 * `old_value` and `new_value` are STRINGS, not numbers — and deliberately. One column pair on
 * `policy_change` carries an `int` (`annual_entitlement`), a nullable `int` (`carry_forward_cap`) and
 * a `bool` (`carries_forward`), so the server types them TEXT and stringifies at its own boundary. A
 * REMOVED cap arrives as the literal string `"null"`, which is meant to be distinguishable from
 * "there never was a cap". The screen renders them as received; typing them `number` here would be a
 * client-side reinterpretation of a server figure, which AD-2 forbids.
 *
 * There is NO actor field, because there is no actor COLUMN, by decision: PRD §1 promises attribution
 * for Leave Request state changes, and a configuration edit is not one (AD-20).
 */
export interface PolicyChange {
  id: string
  leave_type_id: string
  leave_type_code: string
  attribute: string
  old_value: string
  new_value: string
  disposition: string
  occurred_at: string
}

/**
 * The cache key for the policy-change log. Invalidated by the leave-type edit — the only writer of a
 * policy change — and by nothing else, because nothing else can write one and nothing at all can
 * alter one.
 */
export const POLICY_CHANGES_QUERY_KEY = ['policy-changes'] as const

/**
 * One page of the recorded policy changes, newest first (Admin-only).
 *
 * `enabled` is passed by the caller so a non-Admin — who renders nothing — never issues a request the
 * server would answer with a `403` (the `useAdminReviewFlags`/`useAuditEntries` idiom). The gate is a
 * usability measure; `require_role(ADMIN)` on the server is the real one.
 */
export function usePolicyChanges(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: POLICY_CHANGES_QUERY_KEY,
    queryFn: () => apiFetch<Page<PolicyChange>>('/policy-changes'),
    enabled: options?.enabled,
  })
}
