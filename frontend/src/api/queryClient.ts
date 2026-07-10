/**
 * The TanStack Query client.
 *
 * Implements: AC8 (TanStack Query is wired), NFR-17.
 */
import { QueryClient } from '@tanstack/react-query'

import { ApiError } from './client'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Do not retry a refusal the server has already reasoned about. A 400
      // INSUFFICIENT_BALANCE will be insufficient the second time too, and retrying a
      // 401 TOKEN_INVALID three times only delays the redirect to the login screen.
      //
      // Retry the rest — a 502 while the api container restarts is worth one retry.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false
        return failureCount < 2
      },
      staleTime: 30_000,
    },
  },
})
