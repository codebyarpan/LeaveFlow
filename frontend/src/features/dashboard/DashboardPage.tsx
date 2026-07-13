/**
 * The Employee dashboard (Story 2.4, AC7).
 *
 * Implements: FR-07 (frontend) — for each Leave Type, Available is shown PROMINENTLY, with
 * Reserved disclosed alongside (Consumed too). Renders for every authenticated Employee (the
 * balances are the caller's own, scope `self`).
 *
 * --- The one rule this screen must never break (AD-2) ---
 *
 * The client computes NO day count and NO balance figure: `available`, `reserved` and
 * `consumed` arrive from the server as whole-day integers and are rendered AS-IS. `available`
 * is already derived server-side (`accrued − consumed − reserved`); there is no weekday or
 * holiday logic here, nothing to add or subtract. The `test_frontend_no_client_day_count.py`
 * guard (Story 2.3) stays green.
 *
 * This is the Employee's OWN dashboard. The Manager/Admin "view another Employee's balances"
 * screen (`GET /employees/<id>/balances`, "My Team") is a disclosed forward reference (Story
 * 3.2) — not built here, though its endpoint ships and is tested in this story (AC6).
 *
 * Mirrors `LeaveTypesPage`'s `isPending`/`isError`/`data` branches and `.panel`/`.emp-list`/
 * `.emp-row` layout (Pattern A).
 */
import { useBalances } from '../../api'

export function DashboardPage() {
  const balances = useBalances()

  return (
    <section className="panel">
      <h2>My Leave Balances</h2>
      <p className="muted">
        What you can spend right now — Available is what remains after committed and spent leave.
      </p>

      {balances.isPending && <p className="muted">Loading your balances…</p>}

      {balances.isError && (
        <p className="emp-error" role="alert">
          Could not load your balances — {balances.error.message}
        </p>
      )}

      {balances.data && balances.data.length === 0 && (
        <p className="muted">No leave balances yet.</p>
      )}

      {balances.data && balances.data.length > 0 && (
        <ul className="emp-list">
          {balances.data.map((balance) => (
            <li key={balance.leave_type_code} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {balance.leave_type_code} · {balance.leave_type_name}
                </span>
                <span className="muted">
                  Reserved {balance.reserved} · Consumed {balance.consumed}
                </span>
              </div>
              <div className="balance-available">
                <span className="balance-available-value">{balance.available}</span>
                <span className="muted">available</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
