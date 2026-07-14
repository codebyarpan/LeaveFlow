/**
 * The audit trail, as a typed read hook on `apiFetch` (Story 2.9).
 *
 * Implements: FR-16 (frontend) — an Admin reads the append-only record of every state transition.
 * READ-ONLY, and there is nothing else it could be: the endpoint is a `GET` and the application's
 * database role holds `INSERT` and `SELECT` on `audit_entry` and neither `UPDATE` nor `DELETE`
 * (AD-9). So there is no mutation here, and therefore no invalidation and no `onSettled` — the
 * whole `useMutation` apparatus the other api modules carry is simply absent.
 *
 * AD-2: every value is rendered AS RECEIVED. `occurred_at` is the server's RFC 3339 timestamp and
 * the states are the server's vocabulary strings; the client parses and computes NOTHING.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
// `Page<T>` has a single home in `departments.ts`; every later list endpoint reuses that type.
import type { Page } from './departments'

/**
 * One recorded state transition on the wire, mirroring the backend `AuditEntryResponse` (§4.9).
 *
 * The subject (`subject_type` + the polymorphic `subject_id`), the transition (`from_state` →
 * `to_state`), the actor and the timestamp — plus the `reason` that says why.
 *
 * `from_state` is `null` for a creation: a newly submitted request had no prior state.
 *
 * `actor_id` and `actor_name` are BOTH `null` when `actor_type` is `SYSTEM` — the managerless
 * auto-approval. That is not missing data: no person acted, and the backend deliberately declines to
 * invent a name for one (AC6). A renderer shows `actor_type` for those rows; it must never show a
 * blank cell that reads like an absent value, and it must never fill in a human's name.
 */
export interface AuditEntry {
  id: string
  subject_type: string
  subject_id: string
  from_state: string | null
  to_state: string
  actor_type: string
  actor_id: string | null
  actor_name: string | null
  reason: string
  occurred_at: string
}

/** The cache key for the audit-trail list. Nothing invalidates it: no client action writes the trail. */
export const AUDIT_ENTRIES_QUERY_KEY = ['audit-entries'] as const

/**
 * One page of the audit trail, newest first (Admin-only).
 *
 * `enabled` is passed by the caller so a non-Admin — who renders nothing — never issues a request
 * that the server would answer with a `403` (the `useEmployees`/`useCancellationRequests` idiom).
 * The gate is a usability measure; `require_role(ADMIN)` on the server is the real one.
 */
export function useAuditEntries(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: AUDIT_ENTRIES_QUERY_KEY,
    queryFn: () => apiFetch<Page<AuditEntry>>('/audit-entries'),
    enabled: options?.enabled,
  })
}
