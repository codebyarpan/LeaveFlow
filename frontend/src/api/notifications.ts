/**
 * In-app Notifications, as typed hooks on `apiFetch` (Story 3.4). FR-14, AD-16.
 *
 * `GET /api/v1/notifications`, `GET /api/v1/notifications/unread-count` and
 * `PATCH /api/v1/notifications/{id}/read` — api-contracts §4.8 grants all three to Role `any`,
 * Scope `self`.
 *
 * 🚨 ROLE `any` — SO THERE IS NO ROLE GATE ON ANY CONSUMER OF THESE HOOKS. This inverts the app's
 * habit, and the two stories before this one both went the other way (3.2 `/team` and 3.3
 * `/calendar` are Manager-ONLY, and their panels gate on `useMe`). Notifications are different, and
 * the reason matters: a MANAGER is the PRIMARY recipient — `REQUEST_SUBMITTED` is addressed to them
 * — so gating the badge on `role === 'EMPLOYEE'` would hide exactly the notification FR-14 exists to
 * deliver. Every authenticated person has notifications; the server's scope predicate
 * (`recipient_employee_id = :actor`) is the guard, and a non-addressee gets a 404, not a 403.
 *
 * The shape mirrors the backend's minimal `NotificationResponse` (Open Decision #5): the row's own
 * columns and nothing more. `created_at` is rendered VERBATIM by the UI — no `new Date()`, no
 * formatting, no arithmetic (the `auditEntries.ts` precedent; AD-2's spirit).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { Page } from './departments'

/**
 * The base cache key. The list caches per-params at `[...NOTIFICATIONS_QUERY_KEY, params]` and the
 * count at `[...NOTIFICATIONS_QUERY_KEY, 'unread-count']` — both UNDER this prefix, which is what
 * makes one `invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })` refresh the badge and every
 * page of the list together (TanStack v5 hashes keys structurally and matches by prefix).
 */
export const NOTIFICATIONS_QUERY_KEY = ['notifications'] as const

/**
 * One Notification on the wire — the backend's `NotificationResponse`, byte-for-byte.
 *
 * `read_at` is `null` while unread; there is no separate `is_read` boolean, because the nullable
 * timestamp already carries that fact (AD-16) and a second field would be a second source of truth.
 * `kind` is one of the three FR-14 values; the UI renders it as a sentence and computes nothing.
 */
export interface Notification {
  id: string
  kind: string
  leave_request_id: string
  read_at: string | null
  created_at: string
}

/** The unread count's single-key body (backend Open Decision #2). Derived server-side, never stored. */
export interface UnreadCount {
  unread: number
}

/** The list's params — the shared page envelope's controls; the read is addressee-scoped server-side. */
export interface NotificationParams {
  page?: number
  pageSize?: number
}

/** Each param's wire name, in one place so the query string and the backend stay in agreement. */
const PARAM_NAMES = {
  page: 'page',
  pageSize: 'page_size',
} as const

/**
 * The caller's OWN Notifications, newest first (AC5, AC7). Every value is `encodeURIComponent`-escaped
 * into the query string (the 2.7 review's rule); the query key carries the whole `params` object so
 * each page caches distinctly while prefix invalidation still fans out.
 *
 * No `enabled` role gate is offered or wanted — every authenticated role has notifications.
 */
export function useNotifications(params: NotificationParams = {}) {
  const pairs = (Object.keys(PARAM_NAMES) as (keyof NotificationParams)[])
    .filter((key) => params[key] !== undefined)
    .map((key) => `${PARAM_NAMES[key]}=${encodeURIComponent(String(params[key]))}`)
  const path: `/${string}` =
    pairs.length > 0 ? `/notifications?${pairs.join('&')}` : '/notifications'
  return useQuery({
    queryKey: [...NOTIFICATIONS_QUERY_KEY, params],
    queryFn: () => apiFetch<Page<Notification>>(path),
  })
}

/**
 * The caller's unread count (AC5, AC7) — `COUNT(*) WHERE read_at IS NULL`, derived server-side.
 *
 * Keyed UNDER `NOTIFICATIONS_QUERY_KEY` so `useMarkNotificationRead`'s prefix invalidation reaches
 * it: mark one read and the badge must fall. A key outside that prefix would leave the badge stale
 * until `staleTime` expired — the bug this key placement exists to prevent.
 *
 * No `refetchInterval` (Open Decision #4): the app has ZERO polling precedent, and a decision
 * notifies the APPLICANT, whose browser is not the one that acted — so no invalidation on the
 * actor's client could help anyway. The existing defaults answer it well enough: `staleTime` plus
 * TanStack v5's `refetchOnWindowFocus` (on by default) refresh the badge when the user comes back to
 * the tab, which is when they would look at it. No AC requires real-time delivery.
 */
export function useUnreadCount() {
  return useQuery({
    queryKey: [...NOTIFICATIONS_QUERY_KEY, 'unread-count'],
    queryFn: () => apiFetch<UnreadCount>('/notifications/unread-count'),
  })
}

/**
 * Mark one of the caller's own Notifications read (AC6, AC7) — idempotently.
 *
 * A second call on the same id is a 200, not a 409 (the server treats "already read" as success), so
 * a double-click is harmless and needs no client-side guard.
 *
 * `onSettled`, not `onSuccess` (the 2.7 review patch): a 404 means the row is gone or was never the
 * caller's, which is precisely when the cached list is stale and must be refetched. Invalidating only
 * on success would leave a phantom row on screen. The prefix reaches BOTH the badge's count query and
 * every page of the list, because both are keyed under `NOTIFICATIONS_QUERY_KEY`.
 */
export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<null>(`/notifications/${encodeURIComponent(id)}/read`, {
        method: 'PATCH',
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })
    },
  })
}
