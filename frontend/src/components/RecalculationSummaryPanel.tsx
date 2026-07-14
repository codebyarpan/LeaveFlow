/**
 * What a recalculation did — and, above all, what it DECLINED to do.
 *
 * Implements: Story 2.11 AC8 and Story 2.12 AC11 — "the Admin is NEVER shown an unqualified success
 * for an operation that partially refused", and "the screen NAMES every Employee-and-Leave-Type pair
 * the forward check refused and left unchanged".
 *
 * --- Why this is the first thing in `src/components/` ---
 *
 * `src/components/README.md`: "a component used by exactly one feature lives with that feature until
 * a second caller appears." Story 2.11 put this markup inline in `HolidaysPage`, correctly — a
 * holiday was the only thing that could recalculate. Story 2.12 IS the second caller: a Leave Type
 * policy edit runs the same forward check, refuses the same way, per the same (Employee, Leave Type)
 * pair, and returns the same `200` + summary. So it is lifted here rather than cloned, and
 * `HolidaysPage` consumes it. A second copy would be two screens that must be kept honest by hand,
 * with nothing to notice when one of them stops being.
 *
 * --- Why it matters more than it looks ---
 *
 * A `200` from either command does NOT mean "it worked". It can mean "it worked for eleven pairs and
 * I declined to touch three, whose balances are now knowingly stale". PRD §1: "a leave balance that
 * is wrong is worse than a leave balance that is absent, because it will be believed." Reporting that
 * `200` as a bare "Saved" is exactly how a wrong balance comes to be believed. So this reports BOTH
 * numbers and NAMES every refused pair. The permanent record lives on the Review Flags screen; this
 * is the immediate telling, at the moment the Admin acts.
 *
 * AD-2: every figure is rendered AS RECEIVED. The counts, the Leave Year, the Leave Type codes and
 * the cause are the server's; this component computes nothing and parses no date.
 */
import type { RecalculationSummary } from '../api'

interface RecalculationSummaryPanelProps {
  /**
   * The verb, as the heading should read it — "Holiday added", "Leave type updated". The SERVER does
   * not send this and should not: which command ran is the client's own fact, and the summary is
   * identical either way.
   */
  action: string
  summary: RecalculationSummary
}

export function RecalculationSummaryPanel({
  action,
  summary,
}: RecalculationSummaryPanelProps) {
  const refused = summary.pairs_refused.length
  const recalculated = summary.pairs_recalculated

  return (
    <div className="emp-summary" role="status">
      {refused === 0 ? (
        <span className="muted">
          {action}. {recalculated} {recalculated === 1 ? 'balance' : 'balances'} recalculated
          {summary.requests_recalculated > 0 && (
            <>
              {' '}
              ({summary.requests_recalculated} leave{' '}
              {summary.requests_recalculated === 1 ? 'request' : 'requests'})
            </>
          )}
          . Nothing was left unchanged.
        </span>
      ) : (
        <>
          <span className="emp-error" role="alert">
            {action}, but {refused} {refused === 1 ? 'balance was' : 'balances were'} LEFT
            UNCHANGED — correcting {refused === 1 ? 'it' : 'them'} would have driven that Leave
            Year negative. {recalculated} {recalculated === 1 ? 'balance' : 'balances'} were
            recalculated normally.
          </span>
          <ul className="emp-list">
            {summary.pairs_refused.map((pair) => (
              <li
                key={`${pair.employee_id}-${pair.leave_type_id}-${pair.leave_year}`}
                className="emp-row"
              >
                <div className="emp-summary">
                  <span className="emp-name">
                    {pair.employee_name} · {pair.leave_type_code}
                  </span>
                  <span className="emp-inactive">
                    Left unchanged for {pair.leave_year} · {pair.cause}
                  </span>
                </div>
              </li>
            ))}
          </ul>
          <span className="muted">
            These refusals are recorded permanently on the Review flags screen.
          </span>
        </>
      )}
    </div>
  )
}
