/**
 * The api module's public surface. Features import from here, never from a file path.
 *
 * Implements: AC8, and the spine's source tree (`src/api/` — typed client, TanStack
 * Query hooks).
 */
export { API_BASE_PATH, ApiError, apiFetch } from './client'
export type { ErrorEnvelope } from './client'
export { useHealth } from './health'
export type { HealthResponse } from './health'
export { queryClient } from './queryClient'
