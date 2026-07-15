/**
 * The Manager's team, as a typed hook on `apiFetch`. `GET /api/v1/team` (Story 3.2).
 *
 * Implements: FR-19 (frontend) — a Manager's Direct Reports, each identified by Full Name
 * and Department, deactivated reports present and distinguishable. Manager-ONLY server-side
 * (api-contracts §4.9): an Employee AND an Admin get a `403` — the one read in the app
 * where the Admin is refused — so the panel gates the fetch with `enabled` and the server's
 * role gate stays the real guard. The response is the minimal disclosure the backend chose
 * (Open Decision #1): no email, no role, no joining date reaches this client.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { Page } from './departments'
import type { DepartmentBrief } from './me'

/**
 * One Direct Report on the wire — EXACTLY `{id, full_name, department, is_active}`,
 * mirroring the backend `TeamMemberResponse`. `department` reuses the `{id, name}` brief
 * (`me.ts` is its single home, as `employees.py` is the backend's).
 */
export interface TeamMember {
  id: string
  full_name: string
  department: DepartmentBrief
  is_active: boolean
}

/**
 * The base cache key for the team list. Each page caches under `[...TEAM_QUERY_KEY, params]`
 * (TanStack v5 hashes keys structurally), so prefix invalidation would reach every page —
 * though nothing invalidates it yet: this is a read-only surface with no mutation.
 */
export const TEAM_QUERY_KEY = ['team'] as const

/**
 * The Manager's Direct Reports, one page at a time (FR-19). `page`/`page_size` are the only
 * params — the endpoint has no filters — and every value is `encodeURIComponent`-escaped
 * into the query string (the 2.7 review's rule). `options.enabled` gates the fetch (the
 * `useLeaveRequests` idiom): a non-Manager, which renders nothing, never issues a request
 * that is guaranteed to 403.
 */
export function useTeam(
  params: { page?: number; pageSize?: number } = {},
  options?: { enabled?: boolean },
) {
  const pairs: string[] = []
  if (params.page !== undefined) {
    pairs.push(`page=${encodeURIComponent(String(params.page))}`)
  }
  if (params.pageSize !== undefined) {
    pairs.push(`page_size=${encodeURIComponent(String(params.pageSize))}`)
  }
  const path: `/${string}` = pairs.length > 0 ? `/team?${pairs.join('&')}` : '/team'
  return useQuery({
    queryKey: [...TEAM_QUERY_KEY, params],
    queryFn: () => apiFetch<Page<TeamMember>>(path),
    enabled: options?.enabled,
  })
}
