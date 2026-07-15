/**
 * The shared Prev/Next pager over the server's `Page` envelope.
 *
 * Born in `MyLeaveHistoryPanel` (Story 3.1, the app's first pagination UI) and LIFTED here
 * when its second caller arrived (`MyTeamPanel`, Story 3.2) — the `components/` promotion
 * rule this directory's README states, executed exactly as 2.12 lifted
 * `RecalculationSummaryPanel` out of `HolidaysPage`. A mechanical lift: the JSX, the
 * rail-disabling and the count line are byte-for-byte the 3.1 shape; nothing observable
 * changed for the history panel.
 *
 * The caller owns the page state and the page count — `pageCount` comes from the server's
 * OWN echo of `total` and the (clamped) `page_size`, computed where the query lives. The
 * only arithmetic here is the rail comparison, which is pagination, not calendar math.
 */
interface PagerProps {
  /** The caller's current 1-based page. */
  page: number
  /** Total pages, from the server's `total`/`page_size` (`Math.max(1, …)` — never 0). */
  pageCount: number
  /** The server's `total` row count, for the "· N things" suffix; 0 hides the suffix. */
  total: number
  /** The singular row noun ("request", "member") — pluralized with a plain `s`. */
  noun: string
  /** Disable both buttons regardless of rail — pass the query's `isLoading`. */
  disabled?: boolean
  onPrev: () => void
  onNext: () => void
}

export function Pager({ page, pageCount, total, noun, disabled = false, onPrev, onNext }: PagerProps) {
  return (
    <div className="emp-actions">
      <button type="button" onClick={onPrev} disabled={page <= 1 || disabled}>
        Previous
      </button>
      <span className="muted">
        Page {page} of {pageCount}
        {total > 0 ? ` · ${total} ${total === 1 ? noun : `${noun}s`}` : ''}
      </span>
      <button type="button" onClick={onNext} disabled={page >= pageCount || disabled}>
        Next
      </button>
    </div>
  )
}
