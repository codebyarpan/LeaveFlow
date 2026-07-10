/**
 * Login, as a typed call and a TanStack mutation.
 *
 * Implements: AC10 (FR-01 frontend), AC8 (built on the typed client), api-contracts §4.1.
 *
 * Built on `apiFetch`, never a hand-rolled `fetch`: the client already merges headers,
 * sets `Content-Type` only for a JSON body, decodes an empty body, and turns a non-2xx
 * response into a typed `ApiError` carrying the server envelope. A failed login is
 * therefore an `ApiError` whose `message` is the server's non-disclosing sentence
 * (AC4) — the form renders that message verbatim and branches on nothing else.
 */
import { useMutation } from '@tanstack/react-query'

import { apiFetch } from './client'

/** The success body of `POST /auth/login` (api-contracts §4.1). */
export interface LoginResponse {
  access_token: string
  token_type: string
}

/** The credentials a login submits. */
export interface Credentials {
  email: string
  password: string
}

/** Exchange credentials for a token. Throws `ApiError` on any non-2xx (AC4). */
export function login(credentials: Credentials): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

/**
 * The login mutation. The caller wires `onSuccess` to store the token and reveal the
 * shell (App owns that transition); this hook owns only the request and its state —
 * `isPending` disables the button, `error` (an `ApiError`) renders the message.
 */
export function useLogin() {
  return useMutation({
    mutationFn: login,
  })
}
