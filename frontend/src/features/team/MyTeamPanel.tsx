/**
 * The Manager's team (Story 3.2, AC5) — who reports to me, so I know whose leave is mine
 * to decide.
 *
 * Implements: FR-19 (frontend) — a Manager sees their Direct Reports, each identified by
 * Full Name and Department, with a deactivated report PRESENT and marked "(deactivated)"
 * (never filtered out — distinguishable means present). The app's second pager consumer:
 * the shared `Pager` was lifted to `components/` for exactly this panel.
 *
 * --- The two rules this screen must never break ---
 *
 * 1. Role gate is USABILITY, never the guard (the ManagerQueuePanel idiom). This mounts only
 *    for a MANAGER (`useMe().role`), and the query is `enabled`-gated so a non-Manager never
 *    issues a request that is guaranteed to 403 — `GET /team` is Manager-ONLY server-side
 *    (api-contracts §4.9): the ADMIN is refused alongside the Employee, the one read in the
 *    app with that inversion. The real boundary is the server's role gate + REPORTS scope.
 * 2. The client computes NOTHING (AD-2). `full_name`, `department.name` and `is_active` are
 *    rendered AS RECEIVED — there is no date math on this surface at all. The only arithmetic
 *    is the pager's page count over the server's `total` and `page_size`, which is
 *    pagination, not calendar math.
 */
import { useEffect, useState } from 'react'

import { useMe, useTeam } from '../../api'
import type { TeamMember } from '../../api'
import { Pager } from '../../components/Pager'

/** The role this panel is for — the one string the mount gate matches on (the 2.7 idiom). */
const MANAGER_ROLE = 'MANAGER'

/**
 * Rows per team page. A deliberate small page (not the server default of 50) so the pager is
 * exercised by realistic team sizes — the 3.1 rationale; the server clamps whatever is asked
 * of it (NFR-11).
 */
const TEAM_PAGE_SIZE = 10

export function MyTeamPanel() {
  const me = useMe()
  const isManager = me.data?.role === MANAGER_ROLE
  const [page, setPage] = useState(1)

  // Gate the fetch on the resolved role (the ManagerQueuePanel idiom): a non-Manager, which
  // renders nothing below, never issues the request at all.
  const team = useTeam({ page, pageSize: TEAM_PAGE_SIZE }, { enabled: isManager })

  // Clamp when the result set shrinks under us (code review 2026-07-15): a refetch that drops
  // `total` (a report reassigned away) would strand this panel past the last page — an empty page
  // captioned "Page 3 of 1" with a misleading empty state, escapable only via Previous. Gated on
  // data presence: while a page is still loading there is no `total` to judge by.
  const knownTotal = team.data?.total
  const knownPageSize = team.data?.page_size ?? TEAM_PAGE_SIZE
  useEffect(() => {
    if (knownTotal === undefined) return
    const lastPage = Math.max(1, Math.ceil(knownTotal / knownPageSize))
    setPage((current) => Math.min(current, lastPage))
  }, [knownTotal, knownPageSize])

  // The mount gate is a usability measure; the server's 403 (require_role MANAGER) and the
  // REPORTS scope predicate are the real guards.
  if (!isManager) {
    return null
  }

  const items = team.data?.items ?? []
  const total = team.data?.total ?? 0
  // The page count comes from the server's OWN echo of total and the (clamped) page_size —
  // `Math.max(1, …)` keeps "Page 1 of 1" on an empty team rather than "Page 1 of 0".
  const pageSize = team.data?.page_size ?? TEAM_PAGE_SIZE
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  return (
    <section className="panel">
      <h2>My team</h2>
      <p className="muted">
        The Employees who report to you — whose leave is yours to decide. A deactivated
        report stays listed, marked as such. Each entry is the server&apos;s; nothing is
        computed here.
      </p>

      {team.isLoading && <p className="muted">Loading your team…</p>}
      {team.isError && (
        <p className="emp-error" role="alert">
          Could not load your team. Try again later.
        </p>
      )}
      {!team.isLoading && !team.isError && items.length === 0 && (
        <p className="muted">No one reports to you yet.</p>
      )}

      {items.length > 0 && (
        <ul className="emp-list">
          {items.map((member: TeamMember) => (
            <li key={member.id} className="emp-row">
              <div className="emp-summary">
                <span className="emp-name">
                  {member.full_name}
                  {!member.is_active && <span className="emp-inactive"> (deactivated)</span>}
                </span>
                <span className="muted">{member.department.name}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Pager
        page={page}
        pageCount={pageCount}
        total={total}
        noun="member"
        disabled={team.isLoading}
        onPrev={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
      />
    </section>
  )
}
