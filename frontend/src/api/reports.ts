/**
 * The leave CSV export (Story 4.2, FR-15): fetch `/reports/leave.csv` as a `Blob`.
 *
 * Implements: AC5 (frontend) — the filter set applied to the report screen is applied to the
 * export, and it is the FILTER SET that is shared, never a page: the query string is built from
 * the SAME `FILTER_PARAM_NAMES` map the on-screen list uses, minus `page`/`pageSize` (the export
 * carries every matching row; FR-15 binds filters, not pages). Screen and export cannot disagree
 * on a wire name, because there is only one map.
 *
 * An IMPERATIVE fetch, not a TanStack Query hook (the 4.1 document-view precedent): a download
 * is a one-shot action with nothing to cache. `apiFetchBlob` supplies the Authorization header
 * and decodes any non-2xx into the typed `ApiError` (the refusal envelope is still JSON — only
 * the success body is CSV). Nothing is computed from the bytes (AD-2); the caller hands the
 * `Blob` to `URL.createObjectURL`.
 */
import { apiFetchBlob } from './client'
import { FILTER_PARAM_NAMES } from './leaveRequests'
import type { LeaveRequestFilters } from './leaveRequests'

/** The filter keys the export sends — the shared map MINUS the paging keys, by construction. */
const EXPORT_FILTER_KEYS = (
  Object.keys(FILTER_PARAM_NAMES) as (keyof LeaveRequestFilters)[]
).filter((key) => key !== 'page' && key !== 'pageSize')

/** Fetch the CSV export under `filters` — every matching row, no page bound (FR-15). */
export function fetchLeaveReportCsv(filters: LeaveRequestFilters): Promise<Blob> {
  const pairs = EXPORT_FILTER_KEYS.filter((key) => filters[key] !== undefined).map(
    (key) => `${FILTER_PARAM_NAMES[key]}=${encodeURIComponent(String(filters[key]))}`,
  )
  const path: `/${string}` =
    pairs.length > 0 ? `/reports/leave.csv?${pairs.join('&')}` : '/reports/leave.csv'
  return apiFetchBlob(path)
}
