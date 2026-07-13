/**
 * The caller's own profile, as a typed hook. `GET /api/v1/me` (FR-17, AC1).
 *
 * Implements: AC6 — a request that carries the Bearer header and, on a `401 TOKEN_INVALID`,
 * lets `apiFetch` clear the session and sign the user out. Rendering this in the shell is
 * what makes the whole Story 1.3 flow observable: a signed-in user sees their name; an
 * invalidated token returns them to the login screen.
 *
 * The shape mirrors the backend `MeResponse` (`api/v1/me.py`): exactly the six fields the
 * profile exposes — never the password hash or a balance quantity.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'

export interface DepartmentBrief {
  id: string
  name: string
}

export interface MeResponse {
  id: string
  full_name: string
  email: string
  role: string
  department: DepartmentBrief
  joining_date: string
}

/**
 * The cache key for the caller's profile. Exported so the auth boundary can drop it:
 * `['me']` carries no per-user identity, so on a sign-out or a fresh login `App` clears
 * this entry to stop a shared browser from serving the previous user's profile to the
 * next one.
 */
export const ME_QUERY_KEY = ['me'] as const

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => apiFetch<MeResponse>('/me'),
  })
}

/**
 * Update the caller's own Full Name — `PATCH /api/v1/me` (FR-17, AC7). Invalidates the
 * profile cache on success so the shell and this screen re-render with the new name.
 *
 * The body carries ONLY `full_name` — the one field `/me` accepts. Every other field is
 * refused server-side with `400 FORBIDDEN_FIELD`; because this hook (and the profile form)
 * only ever submit `full_name`, that refusal is unreachable through the UI. The read-only
 * rendering of the other fields is a usability measure — the server is the enforcement
 * point (AD-14), never this hook. Mirrors `useUpdateEmployee` in `./employees`.
 */
export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (full_name: string) =>
      apiFetch<MeResponse>('/me', {
        method: 'PATCH',
        body: JSON.stringify({ full_name }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
    },
  })
}
