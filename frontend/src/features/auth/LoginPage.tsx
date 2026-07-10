/**
 * The login screen.
 *
 * Implements: AC10 (FR-01 frontend) — an unauthenticated visitor sees a login screen; a
 * successful login stores the token and lands them on the shell; a failed login shows a
 * message that does not disclose whether the account exists.
 *
 * --- The one rule this component must never break ---
 *
 * On failure it renders the SERVER's envelope message and nothing else. It never
 * inspects the error to tell an unknown email from a wrong password — the server made
 * them byte-identical on purpose (AC4), and any client-side branch that tried to say
 * more would be re-disclosing exactly what the backend spent AC5 hiding. So: one error
 * path, one message, whatever the server said.
 */
import { type FormEvent, useState } from 'react'

import { ApiError, useLogin } from '../../api'

/** A failure whose cause we could not read at all falls back to this. Still non-disclosing. */
const GENERIC_FAILURE = 'Unable to sign in. Please try again.'

interface LoginPageProps {
  /** Called with the token on a successful login. App stores it and reveals the shell. */
  onAuthenticated: (token: string) => void
}

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useLogin()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    login.mutate(
      { email, password },
      { onSuccess: (response) => onAuthenticated(response.access_token) },
    )
  }

  // The message the server sent, verbatim. `ApiError.message` is the envelope's
  // `message` (AC4 guarantees it discloses nothing); anything else — a network blip —
  // gets the generic line. No branch here distinguishes why the login failed.
  const errorMessage = login.isError
    ? login.error instanceof ApiError
      ? login.error.message
      : GENERIC_FAILURE
    : null

  return (
    <div className="login">
      <main className="login__card">
        <h1 className="login__title">LeaveFlow</h1>
        <p className="muted">Sign in to continue.</p>

        <form className="login__form" onSubmit={handleSubmit} noValidate>
          <label className="login__field">
            <span>Email</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoFocus
            />
          </label>

          <label className="login__field">
            <span>Password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {errorMessage !== null && (
            <p className="login__error" role="alert">
              {errorMessage}
            </p>
          )}

          <button className="login__submit" type="submit" disabled={login.isPending}>
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </main>
    </div>
  )
}
