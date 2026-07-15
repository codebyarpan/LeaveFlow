/**
 * In-app Notifications (Story 3.4, AC7) — what happened, and opening one marks it read.
 *
 * Implements: FR-14 (frontend) — a Manager learns a decision is waiting for them; an applicant
 * learns theirs was made. AD-16 (mark-read is idempotent and permitted only to the addressee).
 *
 * --- 🚨 THERE IS NO ROLE GATE ON THIS PANEL, AND THAT IS THE POINT ---
 *
 * Every other feature panel in this app opens with a `useMe()` role gate (`if (!isManager) return
 * null`), and the two stories immediately before this one both shipped Manager-ONLY surfaces. This
 * one has none, deliberately: api-contracts §4.8 grants all three notification endpoints to Role
 * `any`, and a MANAGER is the PRIMARY recipient — `REQUEST_SUBMITTED` is addressed to her. Gating
 * on `role === 'EMPLOYEE'` would hide precisely the notification FR-14 exists to deliver, and
 * gating on MANAGER would hide every applicant's decision. Notifications belong to PEOPLE, not to
 * roles. The server's scope predicate (`recipient_employee_id = :actor`) is the guard, and it needs
 * no help from a mount gate.
 *
 * --- The client computes NOTHING (AD-2) ---
 *
 * `created_at` is rendered VERBATIM, exactly as received — no `new Date()`, no locale formatting,
 * no relative "2 hours ago" arithmetic (the `auditEntries` precedent). The `kind` is mapped to a
 * sentence for legibility; that is a label lookup, not a computation over server data.
 */
import { useEffect, useState } from 'react'

import { useMarkNotificationRead, useNotifications } from '../../api'
import type { Notification } from '../../api'
import { Pager } from '../../components/Pager'

/**
 * Rows per page — a deliberate small page (not the server default of 50) so the pager is actually
 * exercised (the 3.1/3.2 rationale). The server clamps whatever is asked of it (NFR-11).
 */
const NOTIFICATIONS_PAGE_SIZE = 10

/**
 * The three FR-14 kinds, as sentences. A LOOKUP, not a computation — and exhaustive: the backend's
 * `kind` CHECK admits exactly these three, and a cancellation notifies nobody (readiness F-4). The
 * fallback renders the raw value rather than inventing a sentence for a kind that should not exist.
 */
const KIND_SENTENCE: Record<string, string> = {
  REQUEST_SUBMITTED: 'A leave request is waiting for your decision.',
  REQUEST_APPROVED: 'Your leave request was approved.',
  REQUEST_REJECTED: 'Your leave request was rejected.',
}

export function NotificationsPanel() {
  const [page, setPage] = useState(1)
  const notifications = useNotifications({ page, pageSize: NOTIFICATIONS_PAGE_SIZE })
  const markRead = useMarkNotificationRead()

  // Clamp when the result set shrinks under us (code review 2026-07-15): a refetch that drops
  // `total` would strand this panel past the last page — an empty page captioned "Page 3 of 1"
  // with a misleading empty state. Gated on data presence: a still-loading page has no `total`.
  const knownTotal = notifications.data?.total
  const knownPageSize = notifications.data?.page_size ?? NOTIFICATIONS_PAGE_SIZE
  useEffect(() => {
    if (knownTotal === undefined) return
    const lastPage = Math.max(1, Math.ceil(knownTotal / knownPageSize))
    setPage((current) => Math.min(current, lastPage))
  }, [knownTotal, knownPageSize])

  const items = notifications.data?.items ?? []
  const total = notifications.data?.total ?? 0
  const pageSize = notifications.data?.page_size ?? NOTIFICATIONS_PAGE_SIZE
  // From the server's OWN echo of `total` and the (clamped) `page_size` — `Math.max(1, …)` keeps
  // "Page 1 of 1" on an empty list rather than "Page 1 of 0". Pagination, not calendar math.
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  // The per-row mutation idiom (ManagerQueuePanel): `variables` IS the in-flight/failed id, so the
  // busy state and the inline error both sit on the row that caused them.
  const busyId = markRead.isPending ? markRead.variables : null
  const failedId = markRead.isError ? markRead.variables : null

  return (
    <section className="panel">
      <h2>Notifications</h2>
      <p className="muted">
        What happened to your leave — and, if you are a Manager, what is waiting for your
        decision. Opening a notification marks it read. Every value is the server&apos;s;
        nothing is computed here.
      </p>

      {notifications.isLoading && <p className="muted">Loading your notifications…</p>}
      {notifications.isError && (
        <p className="emp-error" role="alert">
          Could not load your notifications. Try again later.
        </p>
      )}
      {!notifications.isLoading && !notifications.isError && items.length === 0 && (
        <p className="muted">You have no notifications.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((notification: Notification) => (
            <li key={notification.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {KIND_SENTENCE[notification.kind] ?? notification.kind}
                  {notification.read_at === null && (
                    <span className="badge badge--waiting"> unread</span>
                  )}
                </span>
                {/* Rendered VERBATIM — no date arithmetic on the client (AD-2). */}
                <span className="muted">{notification.created_at}</span>
              </div>

              {/* "Opening a Notification marks it read" (AC7). Idempotent server-side: a second
                  call is a 200, not a 409, so a double-click needs no client-side guard. Already-read
                  rows offer no control — there is nothing left to do to them. */}
              {notification.read_at === null && (
                <div className="emp-actions">
                  <button
                    type="button"
                    onClick={() => markRead.mutate(notification.id)}
                    disabled={busyId !== null}
                  >
                    {busyId === notification.id ? 'Opening…' : 'Open'}
                  </button>
                </div>
              )}

              {failedId === notification.id && (
                <p className="emp-error" role="alert">
                  Could not mark this notification read. Try again.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <Pager
        page={page}
        pageCount={pageCount}
        total={total}
        noun="notification"
        disabled={notifications.isLoading}
        onPrev={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
      />
    </section>
  )
}
