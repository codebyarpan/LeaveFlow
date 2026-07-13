/**
 * The Admin's Cancellation Requests screen (Story 2.8, AC10).
 *
 * Implements: FR-09 (frontend) — an Admin sees every Pending Cancellation Request, each naming its
 * applicant, the targeted Leave Request and its dates, and approves or rejects it. This is the
 * Admin's ONLY route to a Cancellation Request: none is announced by notification or dashboard, so
 * without this screen a Pending Cancellation Request would be undiscoverable. Approving cancels the
 * leave and returns the applicant's days; rejecting changes nothing.
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (the `EmployeesPage` idiom). This mounts only for an
 *    ADMIN (`useMe().role`), but the real boundary is the server: approve/reject are
 *    `require_role(ADMIN)` (a non-Admin is a 403), and the id is located under scope `all`. The
 *    client hiding the panel is a convenience, not enforcement.
 * 2. The client computes NOTHING (AD-2). `leave_days`, the dates, the applicant name and the status
 *    are rendered AS RECEIVED — no day-of-week primitive and no day-count arithmetic here.
 */
import { ApiError, useApproveCancellationRequest, useCancellationRequests, useMe, useRejectCancellationRequest } from '../../api'
import type { CancellationRequest } from '../../api'

/** The role this screen is for — the one string the mount gate matches on (the `EmployeesPage` idiom). */
const ADMIN_ROLE = 'ADMIN'

/** The one status this queue shows: Cancellation Requests awaiting a decision. Sent as received (AD-2). */
const PENDING_STATUS = 'PENDING'

/** Turn a decision rejection into a human line, naming the obstruction (NFR-17); branch on `code`. */
function decisionErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'TRANSITION_NOT_ALLOWED') {
      return 'This cancellation request was already decided, or the leave changed — the queue has been refreshed.'
    }
    if (error.code === 'RESOURCE_NOT_FOUND') {
      return 'This cancellation request is no longer available.'
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

export function CancellationRequestsPanel() {
  const me = useMe()
  const isAdmin = me.data?.role === ADMIN_ROLE
  // Gate the fetch on the resolved role (the `useEmployees` idiom): a non-Admin, which renders
  // nothing below, never issues the request.
  const queue = useCancellationRequests(PENDING_STATUS, { enabled: isAdmin })
  const approve = useApproveCancellationRequest()
  const reject = useRejectCancellationRequest()

  // The mount gate is a usability measure; the server's 403 is the real guard (AC8).
  if (!isAdmin) {
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
      <h2>Cancellation requests</h2>
      <p className="muted">
        Requests from employees to cancel approved leave. Approving cancels the leave and returns the
        days to the applicant; rejecting leaves the approved leave in place. Each figure is the
        server&apos;s — nothing is computed here.
      </p>

      {queue.isLoading && <p className="muted">Loading cancellation requests…</p>}
      {queue.isError && (
        <p className="emp-error" role="alert">
          Could not load cancellation requests. Try again later.
        </p>
      )}
      {!queue.isLoading && !queue.isError && items.length === 0 && (
        <p className="muted">No cancellation requests are awaiting a decision.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((request: CancellationRequest) => (
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
