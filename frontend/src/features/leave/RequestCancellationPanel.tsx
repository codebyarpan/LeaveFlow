/**
 * The Employee's "cancel my approved leave" panel (Story 2.8, AC10).
 *
 * Implements: FR-09 (frontend) — a plain Employee sees their own APPROVED requests, raises a
 * Cancellation Request against one whose dates are still ahead, and tracks its state (Pending /
 * Rejected) while an Admin decides it. An approved Cancellation Request cancels the leave, so that
 * request leaves the APPROVED list entirely (the list refetches) and the caller's Available rises.
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard. This mounts only for a plain EMPLOYEE — Open Decision
 *    #6: a Manager's `GET /leave-requests` returns their REPORTS' requests, not their own (the 2.7
 *    own-requests gap), so a `useLeaveRequests('APPROVED')`-driven panel would show the wrong list
 *    for a Manager, and the SELF-scoped raise would 404 on a report's request. A Manager/Admin
 *    self-cancelling Approved leave is API-only until that gap is closed. The real boundary is
 *    always the server: the raise is `self`-scoped (a non-owner target is a byte-identical 404).
 * 2. The client computes NOTHING (AD-2). `leave_days`, the dates and the status are rendered AS
 *    RECEIVED — no day-of-week primitive, no day-count arithmetic (`test_frontend_no_client_day_
 *    count.py` stays green; those tokens must never appear, not even in a comment).
 */
import { ApiError, useCancellationRequests, useLeaveRequests, useMe, useRaiseCancellationRequest } from '../../api'
import type { CancellationRequest, LeaveRequest } from '../../api'

/** The role this panel is for — the one string the mount gate matches on (Open Decision #6). */
const EMPLOYEE_ROLE = 'EMPLOYEE'

/** The one Leave Request status this panel acts on: an Approved request may be cancelled. */
const APPROVED_STATUS = 'APPROVED'

/** The Cancellation Request states this panel narrates, matched on the wire `status` string. */
const CANCELLATION_PENDING = 'PENDING'
const CANCELLATION_REJECTED = 'REJECTED'

/** Turn a raise rejection into a human line, naming the obstruction (NFR-17); branch on `code`. */
function raiseErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'LEAVE_ALREADY_TAKEN') {
      return 'This leave has already been taken and can no longer be cancelled.'
    }
    if (error.code === 'TRANSITION_NOT_ALLOWED') {
      return 'This request is no longer in a state that can be cancelled — the list has been refreshed.'
    }
    if (error.code === 'RESOURCE_NOT_FOUND') {
      return 'This request is no longer available to you.'
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

/** The most recent open cancellation state for a Leave Request, or null if none is on file. */
function cancellationStateFor(
  leaveRequestId: string,
  cancellations: CancellationRequest[],
): string | null {
  const mine = cancellations.filter((c) => c.leave_request_id === leaveRequestId)
  if (mine.some((c) => c.status === CANCELLATION_PENDING)) {
    return CANCELLATION_PENDING
  }
  if (mine.some((c) => c.status === CANCELLATION_REJECTED)) {
    return CANCELLATION_REJECTED
  }
  return null
}

export function RequestCancellationPanel() {
  const me = useMe()
  const isEmployee = me.data?.role === EMPLOYEE_ROLE
  // Gate both fetches on the resolved role (the `useLeaveRequests` idiom): a non-Employee, which
  // renders nothing below, never issues either request.
  const approved = useLeaveRequests(APPROVED_STATUS, { enabled: isEmployee })
  const cancellations = useCancellationRequests(undefined, { enabled: isEmployee })
  const raise = useRaiseCancellationRequest()

  // The mount gate is a usability measure; the server's self-scoped 404 is the real guard.
  if (!isEmployee) {
    return null
  }

  const items = approved.data?.items ?? []
  const mine = cancellations.data?.items ?? []
  const failedId = raise.isError ? (raise.variables ?? null) : null
  const busyId = raise.isPending ? raise.variables : null

  return (
    <section className="panel">
      <h2>Cancel approved leave</h2>
      <p className="muted">
        Your approved requests. If your plans change, request a cancellation — an administrator
        decides it, and if approved the days return to your balance. Each figure is the
        server&apos;s; nothing is computed here.
      </p>

      {approved.isLoading && <p className="muted">Loading your approved leave…</p>}
      {approved.isError && (
        <p className="emp-error" role="alert">
          Could not load your approved leave. Try again later.
        </p>
      )}
      {!approved.isLoading && !approved.isError && items.length === 0 && (
        <p className="muted">You have no approved leave to cancel.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((request: LeaveRequest) => {
            const state = cancellationStateFor(request.id, mine)
            return (
              <li key={request.id} className="emp-row">
                <div className="emp-summary">
                  <span className="emp-name">{request.leave_type_code}</span>
                  <span className="muted">
                    {request.start_date} → {request.end_date} · {request.leave_days}{' '}
                    {request.leave_days === 1 ? 'day' : 'days'} · {request.status}
                  </span>
                  {state === CANCELLATION_PENDING && (
                    <span className="muted">Cancellation requested — awaiting a decision.</span>
                  )}
                  {state === CANCELLATION_REJECTED && (
                    <span className="muted">A previous cancellation request was rejected.</span>
                  )}
                </div>
                <div className="emp-actions">
                  <button
                    type="button"
                    onClick={() => raise.mutate(request.id)}
                    disabled={busyId !== null || state === CANCELLATION_PENDING}
                  >
                    {raise.isPending && busyId === request.id
                      ? 'Requesting…'
                      : 'Request cancellation'}
                  </button>
                </div>
                {failedId === request.id && (
                  <p className="emp-error" role="alert">
                    {raiseErrorMessage(raise.error)}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
