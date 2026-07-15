/**
 * The inline decision calendar (Story 3.3, AC2/AC3).
 *
 * Implements: FR-18 (frontend) — who else on the team is already away (or asking to be) across
 * the dates of the request under decision, rendered INSIDE the pending row of the Manager queue:
 * the queue rows ARE the approval screen, so the overlap is visible at the moment of decision,
 * not discovered the following week (UJ-2). BR-06/DR-15: this INFORMS and never blocks — there is
 * no warning, no confirmation, no reach into the approve/reject actions beside it.
 *
 * --- The three rules this component must never break ---
 *
 * 1. The client computes NOTHING (AD-2/AD-18). `start_date`, `end_date`, `leave_days` and the
 *    status word render EXACTLY as the server sent them. There is no date arithmetic of any kind
 *    here — no day-of-week primitive, no range iteration — and the backend guard scan
 *    (`test_frontend_no_client_day_count.py`) forbids those tokens even in comments.
 * 2. The request under decision is excluded by `id` equality (Open Decision #5): it necessarily
 *    matches its own overlap window, and the server correctly returns it — "also away" is the
 *    remainder after dropping it. No backend marker exists; the endpoint stays context-free.
 * 3. The status word IS the visual distinction (Open Decision #6): APPROVED and PENDING render
 *    verbatim per row — a list of overlap rows, no day-grid, no charts (§7.4), zero new CSS.
 */
import { useCalendar } from '../../api'
import type { LeaveRequest } from '../../api'

/**
 * The server's MAX_PAGE_SIZE (code review 2026-07-15). The default page (50) silently truncated
 * the overlap list — and if the request under decision fell past the page, the `id` exclusion
 * below never fired and it listed itself as its own overlap. Ask for the widest page the server
 * grants, and when `total` still exceeds what came back, SAY so (the "…and N more" row): the one
 * screen that exists to prevent overlap surprises must never under-report the overlap silently.
 */
const CALENDAR_PAGE_SIZE = 100

interface DecisionCalendarProps {
  /** The request under decision — excluded from its own calendar by `id` equality. */
  requestId: string
  /** The request's own range, straight off the queue row (`YYYY-MM-DD`, sent as received). */
  dateFrom: string
  dateTo: string
  /** Gates the fetch (the panel's resolved `isManager`) — a non-Manager never issues it. */
  enabled: boolean
}

export function DecisionCalendar({ requestId, dateFrom, dateTo, enabled }: DecisionCalendarProps) {
  // The queue is PENDING-only and paged, so the per-row query count is bounded; each window
  // caches under its own key and the decision mutations' fan-out keeps every one fresh.
  const calendar = useCalendar(
    { dateFrom, dateTo, pageSize: CALENDAR_PAGE_SIZE },
    { enabled },
  )

  // Open Decision #5: drop the request under decision; the remainder is "also away."
  const items = calendar.data?.items ?? []
  const others = items.filter((item: LeaveRequest) => item.id !== requestId)
  // Overlaps the page could not carry — both figures arrive from the server (AD-2); this is a
  // count of rows NOT shown, so the list can never present a truncation as the complete answer.
  const undisplayed = (calendar.data?.total ?? 0) - items.length

  // The mandatory loading/error/empty triad (the 2.5 review rule). A fetch error stays inside
  // THIS row — never attributed to a sibling (the ManagerQueuePanel:61 lesson).
  if (calendar.isLoading) {
    return <p className="muted">Checking who else is away on these dates…</p>
  }
  if (calendar.isError) {
    return (
      <p className="emp-error" role="alert">
        Could not load the team calendar for these dates.
      </p>
    )
  }
  if (others.length === 0 && undisplayed <= 0) {
    return <p className="muted">No other leave overlaps these dates.</p>
  }

  return (
    <ul className="emp-list">
      {others.map((item: LeaveRequest) => (
        <li key={item.id} className="emp-row">
          <div className="emp-summary">
            <span className="emp-name">{item.employee_name}</span>
            <span className="muted">
              {item.start_date} → {item.end_date} · {item.leave_days}{' '}
              {item.leave_days === 1 ? 'day' : 'days'} · {item.status}
            </span>
          </div>
        </li>
      ))}
      {undisplayed > 0 && (
        <li className="muted">…and {undisplayed} more overlap these dates</li>
      )}
    </ul>
  )
}
