/**
 * The three role dashboards, as typed hooks on `apiFetch`. `GET /api/v1/dashboard/*` (Story 3.5).
 *
 * Implements: FR-11 (frontend) — a dashboard scoped to what the caller can act on. Three
 * endpoints, three gates server-side: `/dashboard/employee` is role `any` (a Manager there sees
 * their OWN balances — AC5), `/dashboard/manager` is Manager-ONLY (an Admin gets a `403` too, the
 * §4.9 inversion), `/dashboard/admin` is Admin-only. The manager/admin hooks therefore take the
 * `enabled` gate (the `useCalendar`/`useTeam` idiom) so a panel that renders nothing never issues
 * a request that is guaranteed to 403.
 *
 * AD-2: every figure arrives from the server and renders AS-IS. The DEFAULT windows ("today",
 * "the next seven days") are computed SERVER-side and echoed back as `leave_window_from`/
 * `leave_window_to` — the client sends NO dates by default and never computes `today + 7`; the
 * card label derives from the echo, so it can never lie about what was actually computed. The
 * echoed ends are nullable: a one-sided range genuinely leaves one end unbounded.
 *
 * One `DASHBOARD_QUERY_KEY` prefix with the role appended: a single prefix invalidation from any
 * mutation that moves a count (submit, decide, cancellation, recalculation) fans out to all three
 * dashboards at once.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
// The wire shape of one balance is `BalanceResponse`, reused byte-for-byte server-side — so the
// `Balance` type keeps its single home in `balances.ts` (the `Page<T>`-in-`departments.ts` rule).
import type { Balance } from './balances'

/**
 * The base cache key for every dashboard. Each role's dashboard caches under
 * `[...DASHBOARD_QUERY_KEY, role, params]` (TanStack v5 hashes keys structurally), so prefix
 * invalidation reaches all three roles' dashboards — and every date-range variant — at once.
 */
export const DASHBOARD_QUERY_KEY = ['dashboard'] as const

/**
 * The dashboards' params: an optional overlap window. An absent side applies no predicate
 * server-side; both absent means the server's FR-11 default window applies. Dates are
 * `YYYY-MM-DD` strings straight from an `<input type="date">` (AD-12), sent as received.
 */
export interface DashboardParams {
  dateFrom?: string
  dateTo?: string
}

/** Each param's wire name, in one place so the query string and the backend stay in agreement. */
const FILTER_PARAM_NAMES = {
  dateFrom: 'date_from',
  dateTo: 'date_to',
} as const

/** Build `role`'s dashboard path with every supplied param `encodeURIComponent`-escaped. */
function dashboardPath(role: string, params: DashboardParams): `/${string}` {
  const pairs = (Object.keys(FILTER_PARAM_NAMES) as (keyof DashboardParams)[])
    .filter((key) => params[key] !== undefined)
    .map(
      (key) =>
        `${FILTER_PARAM_NAMES[key]}=${encodeURIComponent(String(params[key]))}`,
    )
  return pairs.length > 0
    ? `/dashboard/${role}?${pairs.join('&')}`
    : `/dashboard/${role}`
}

/**
 * The Employee dashboard on the wire, mirroring the backend `EmployeeDashboardResponse`.
 * `balances` is the caller's CURRENT Leave Year (`leave_year` says which) and is never
 * date-filtered — a balance row has no dates; the range narrows `pending_request_count` only.
 */
export interface EmployeeDashboard {
  leave_year: number
  balances: Balance[]
  pending_request_count: number
}

/** One Direct Report on approved leave — a person, not a request (the server de-duplicates). */
export interface ReportOnLeave {
  employee_id: string
  full_name: string
}

/**
 * The Manager dashboard on the wire, mirroring the backend `ManagerDashboardResponse`.
 * `leave_window_from`/`leave_window_to` echo the window the list was ACTUALLY computed over
 * (the server's default "next seven days" when no range was sent) — the card label derives
 * from these, never from a hard-coded string. Either end may be null (a one-sided range).
 * `reports_on_leave_count` is the server's DISTINCT people-count and is the headline figure:
 * the list beside it is server-capped, so its `.length` is NOT the count (AD-2).
 */
export interface ManagerDashboard {
  pending_decision_count: number
  reports_on_leave_count: number
  reports_on_approved_leave: ReportOnLeave[]
  leave_window_from: string | null
  leave_window_to: string | null
}

/**
 * The Admin dashboard on the wire, mirroring the backend `AdminDashboardResponse`.
 * `employees_on_approved_leave` counts PEOPLE (server-side DISTINCT); `pending_request_count`
 * counts LEAVE Requests only — a pending Cancellation Request is deliberately not in it.
 */
export interface AdminDashboard {
  employees_on_approved_leave: number
  pending_request_count: number
  leave_window_from: string | null
  leave_window_to: string | null
}

/** The caller's own dashboard (role `any`, scope `self`) — balances + own pending count. */
export function useEmployeeDashboard(params: DashboardParams = {}) {
  return useQuery({
    queryKey: [...DASHBOARD_QUERY_KEY, 'employee', params],
    queryFn: () => apiFetch<EmployeeDashboard>(dashboardPath('employee', params)),
  })
}

/**
 * The Manager dashboard (Manager-ONLY server-side; an Admin is refused too). Gate with
 * `enabled` from the resolved role so a non-Manager never issues the request.
 */
export function useManagerDashboard(
  params: DashboardParams = {},
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: [...DASHBOARD_QUERY_KEY, 'manager', params],
    queryFn: () => apiFetch<ManagerDashboard>(dashboardPath('manager', params)),
    enabled: options?.enabled,
  })
}

/** The Admin dashboard (Admin-only server-side). Gate with `enabled` from the resolved role. */
export function useAdminDashboard(
  params: DashboardParams = {},
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: [...DASHBOARD_QUERY_KEY, 'admin', params],
    queryFn: () => apiFetch<AdminDashboard>(dashboardPath('admin', params)),
    enabled: options?.enabled,
  })
}
