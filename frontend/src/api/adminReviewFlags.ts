/**
 * The refusal register, as a typed read hook on `apiFetch` (Story 2.11).
 *
 * Implements: FR-10 (frontend), AC9 — an Admin reads every recalculation the system REFUSED to
 * perform, so that a balance left uncorrected is not a balance quietly believed to be correct.
 *
 * READ-ONLY, and there is nothing else it could be. `FR-10` grants the Admin only a read; NO
 * requirement grants a RESOLVE. So there is no `resolved_at` column, no `PATCH`, no `DELETE` — and
 * the application's database role holds `INSERT` and `SELECT` on `admin_review_flag` and neither
 * `UPDATE` nor `DELETE` (AD-20, migration `0010`), so a "clear this flag" button would be refused by
 * PostgreSQL even if someone wrote one. There is therefore no mutation here, no invalidation and no
 * `onSettled` — the whole `useMutation` apparatus the other api modules carry is simply absent, the
 * same way it is absent from `auditEntries.ts`.
 *
 * The ONE thing that invalidates this list is a holiday change, because that is the only thing that
 * writes a flag — so `holidays.ts` invalidates `ADMIN_REVIEW_FLAGS_QUERY_KEY` on both its mutations.
 *
 * AD-2: every value is rendered AS RECEIVED. `occurred_at` is the server's RFC 3339 timestamp and
 * `cause` is the server's vocabulary string; the client parses and computes NOTHING.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
// `Page<T>` has a single home in `departments.ts`; every later list endpoint reuses that type.
import type { Page } from './departments'

/**
 * One recorded refusal on the wire, mirroring the backend `AdminReviewFlagResponse`.
 *
 * The PAIR the recalculation left unchanged — by name and code, not merely by id, because
 * "employee 3f2a…" is not something an Admin can act on — the LEAVE YEAR it refused, the CAUSE, and
 * WHEN it occurred.
 *
 * No field is nullable, unlike `AuditEntry`'s SYSTEM rows: a flag always names its Employee and its
 * Leave Type (both columns are NOT NULL). And there is no `resolved` or `resolved_at`, because a
 * flag is a permanent record that a recalculation was refused.
 */
export interface AdminReviewFlag {
  id: string
  employee_id: string
  employee_name: string
  leave_type_id: string
  leave_type_code: string
  leave_year: number
  cause: string
  occurred_at: string
}

/**
 * The cache key for the refusal register. Invalidated by the holiday mutations — the only writers
 * of a flag — and by nothing else, because nothing else can write one and nothing at all can clear
 * one.
 */
export const ADMIN_REVIEW_FLAGS_QUERY_KEY = ['admin-review-flags'] as const

/**
 * One page of the recorded refusals, newest first (Admin-only).
 *
 * `enabled` is passed by the caller so a non-Admin — who renders nothing — never issues a request
 * the server would answer with a `403` (the `useAuditEntries`/`useEmployees` idiom). The gate is a
 * usability measure; `require_role(ADMIN)` on the server is the real one.
 */
export function useAdminReviewFlags(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ADMIN_REVIEW_FLAGS_QUERY_KEY,
    queryFn: () => apiFetch<Page<AdminReviewFlag>>('/admin-review-flags'),
    enabled: options?.enabled,
  })
}
