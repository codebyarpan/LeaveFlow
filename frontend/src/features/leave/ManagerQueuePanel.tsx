/**
 * The Manager decision queue (Story 2.7, AC9).
 *
 * Implements: FR-09 (frontend) — a Manager sees the requests awaiting their decision (their Direct
 * Reports' PENDING requests) and approves or rejects each; afterwards the queue and any affected
 * balances refresh (the mutations invalidate both query keys). A `409 TRANSITION_NOT_ALLOWED` — the
 * request was cancelled or decided under the Manager between load and click — is shown inline and
 * the queue self-heals, because the mutation still invalidates the list on settling.
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (AC6, the `EmployeesPage` idiom). This mounts only for
 *    a MANAGER (`useMe().role`), but the real boundary is the server: approve/reject are
 *    `require_role(MANAGER)` (a non-Manager is a 403), and the `reports` scope is what decides
 *    whether THIS Manager owns THIS applicant (a non-report is a byte-identical 404). The client
 *    hiding the panel is a convenience, not enforcement.
 * 2. The client computes NOTHING (AD-2). `leave_days`, the dates, the applicant name and the status
 *    are rendered AS RECEIVED. There is no day-of-week primitive and no day-count arithmetic here —
 *    `test_frontend_no_client_day_count.py` (which line-scans `frontend/src` for the JS
 *    day-of-week primitives) stays green; those tokens must never appear, not even in a comment.
 */
import { ApiError, useApproveLeaveRequest, useLeaveRequests, useMe, useRejectLeaveRequest } from '../../api'
import type { LeaveRequest } from '../../api'

/** The role this queue is for — the one string the mount gate matches on (the `EmployeesPage` idiom). */
const MANAGER_ROLE = 'MANAGER'

/** The one status this queue shows: requests awaiting a decision. Rendered/sent as received (AD-2). */
const PENDING_STATUS = 'PENDING'

/** Turn a decision rejection into a human line, naming the obstruction (NFR-17); branch on `code`. */
function decisionErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'TRANSITION_NOT_ALLOWED') {
      return 'This request was already decided or cancelled — the queue has been refreshed.'
    }
    if (error.code === 'RESOURCE_NOT_FOUND') {
      return 'This request is no longer available to you.'
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

export function ManagerQueuePanel() {
  const me = useMe()
  const isManager = me.data?.role === MANAGER_ROLE
  // Gate the fetch on the resolved role (the `useEmployees` idiom): a non-Manager, which renders
  // nothing below, never issues the request.
  const queue = useLeaveRequests(PENDING_STATUS, { enabled: isManager })
  const approve = useApproveLeaveRequest()
  const reject = useRejectLeaveRequest()

  // The mount gate is a usability measure; the server's 403/404 is the real guard (AC6/AC7).
  if (!isManager) {
    return null
  }

  const items = queue.data?.items ?? []
  // The id whose decision was refused, and which action failed, so the inline line sits on its row.
  const failed = approve.isError ? approve : reject.isError ? reject : null
  const failedId = failed?.variables ?? null
  const busyId = approve.isPending
    ? approve.variables
    : reject.isPending
      ? reject.variables
      : null

  return (
    <section className="panel">
      <h2>Approvals</h2>
      <p className="muted">
        Requests from your direct reports awaiting a decision. Approving moves the days to consumed;
        rejecting returns them. Each figure is the server&apos;s — nothing is computed here.
      </p>

      {queue.isLoading && <p className="muted">Loading your queue…</p>}
      {queue.isError && (
        <p className="emp-error" role="alert">
          Could not load the approval queue. Try again later.
        </p>
      )}
      {!queue.isLoading && !queue.isError && items.length === 0 && (
        <p className="muted">No requests are awaiting your decision.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((request: LeaveRequest) => (
            <li key={request.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">{request.employee_name}</span>
                <span className="muted">
                  {request.leave_type_code} · {request.start_date} → {request.end_date} ·{' '}
                  {request.leave_days} {request.leave_days === 1 ? 'day' : 'days'} · {request.status}
                </span>
              </div>
              <div className="emp-actions">
                <button
                  type="button"
                  onClick={() => {
                    // Clear the sibling's prior error so a stale line can never linger on—or be
                    // mis-attributed to—another row: only the action just taken shows a result.
                    reject.reset()
                    approve.mutate(request.id)
                  }}
                  disabled={busyId !== null}
                >
                  {approve.isPending && busyId === request.id ? 'Approving…' : 'Approve'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    approve.reset()
                    reject.mutate(request.id)
                  }}
                  disabled={busyId !== null}
                >
                  {reject.isPending && busyId === request.id ? 'Rejecting…' : 'Reject'}
                </button>
              </div>
              {failed !== null && failedId === request.id && (
                <p className="emp-error" role="alert">
                  {decisionErrorMessage(failed.error)}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
