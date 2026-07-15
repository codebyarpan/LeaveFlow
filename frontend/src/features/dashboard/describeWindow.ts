/**
 * The dashboard cards' window label, derived from the server's ECHO of the window it
 * actually computed over (Story 3.5, Decision #1: a hard-coded "next 7 days" in the JSX
 * becomes a lie the moment a range is supplied).
 *
 * String assembly only — no date is parsed, compared or advanced here (AD-2: the window is
 * a server decision; the client never computes `today + 7`). A null end is a genuinely
 * unbounded side (a one-sided range) and the label says so rather than inventing a date.
 *
 * Its own module (not an export from a panel) so react-refresh's only-export-components
 * rule holds for both consuming panels.
 */
export function describeWindow(from: string | null, to: string | null): string {
  if (from !== null && to !== null) {
    return `${from} to ${to}`
  }
  if (from !== null) {
    return `from ${from} onwards`
  }
  if (to !== null) {
    return `up to ${to}`
  }
  return 'any dates'
}
