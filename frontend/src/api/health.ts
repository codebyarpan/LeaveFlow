/**
 * The deployment probe, as a typed hook.
 *
 * Implements: AC1, AC8, api-contracts §4.10 (`GET /health`, anonymous).
 *
 * Exists to prove the client is wired end to end — typed fetch, error envelope,
 * TanStack Query — against the one endpoint Story 1.1 ships. Later stories add the
 * hooks that matter; this one is the seam they will follow.
 */
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'

export interface HealthResponse {
  status: string
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiFetch<HealthResponse>('/health'),
  })
}
