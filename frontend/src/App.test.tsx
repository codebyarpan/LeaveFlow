/**
 * The logout flow, end to end in the DOM (spec-logout).
 *
 * Renders the real `App` over the real `queryClient` with a token in place, so the token
 * gate mounts the shell. Clicking "Log out" must: return the visitor to the login screen
 * (the shell and its panels unmount — the app's only "protected route" is inaccessible
 * once the token is gone), forget the token, and clear the query cache so a shared browser
 * cannot serve this user's cached data to the next.
 *
 * `fetch` is stubbed: `/me` and `/health` succeed so the shell renders cleanly; every other
 * endpoint answers a benign 404 so the role's panels fall to their empty/error states
 * rather than crashing on an unexpected success shape. None of that is what the test
 * asserts — it only needs the shell mounted and the "Log out" button reachable.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getToken, queryClient, SESSION_EXPIRED_EVENT, setToken } from './api'
import { App } from './App'

const ME_BODY = {
  id: 'emp-1',
  full_name: 'Ada Lovelace',
  email: 'ada@example.com',
  role: 'EMPLOYEE',
  department: { id: 'dep-1', name: 'Engineering' },
  joining_date: '2020-01-01',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// A profile for a DIFFERENT user, used to prove the first user's data does not survive
// into a subsequent session on the same browser.
const OTHER_ME_BODY = { ...ME_BODY, id: 'emp-2', full_name: 'Grace Hopper' }

function stubFetch(meBody: typeof ME_BODY = ME_BODY) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/me')) return jsonResponse(meBody)
    if (url.endsWith('/api/v1/health')) return jsonResponse({ status: 'ok' })
    if (url.endsWith('/unread-count')) return jsonResponse({ unread: 0 })
    // A refusal that is NOT 401 TOKEN_INVALID (which would itself sign the user out) and
    // not 5xx (which the client would retry): panels render their empty/error branch.
    return jsonResponse({ code: 'NOT_FOUND', message: 'test', details: {} }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
}

function renderApp() {
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

/** The queries currently held in the shared client's cache. */
function cachedQueryCount() {
  return queryClient.getQueryCache().getAll().length
}

describe('logout flow', () => {
  beforeEach(() => {
    localStorage.clear()
    queryClient.clear()
    stubFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
    queryClient.clear()
  })

  it('signs the user out: returns to login, forgets the token, empties the cache', async () => {
    setToken('a-valid-session-token')

    renderApp()

    // The shell is mounted (the protected surface) and the control is reachable.
    const logoutButton = await screen.findByRole('button', { name: /log out/i })
    expect(await screen.findByText(/Ada Lovelace/)).toBeInTheDocument()
    // The user's profile really is in the cache before logout — otherwise "cache emptied"
    // below would be vacuously true.
    expect(cachedQueryCount()).toBeGreaterThan(0)

    await userEvent.setup().click(logoutButton)

    // Back on the login screen: the shell and its panels are gone.
    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    expect(screen.queryByText('Signed in')).toBeNull()
    expect(screen.queryByRole('button', { name: /log out/i })).toBeNull()

    // The token is forgotten and the whole query cache is actually empty — asserting the
    // EFFECT, not merely that clear() was called (a partial teardown must fail here).
    expect(getToken()).toBeNull()
    expect(cachedQueryCount()).toBe(0)
  })

  it('does not serve the previous user cached data to the next login on the same browser', async () => {
    setToken('user-one-token')
    const { unmount } = renderApp()
    expect(await screen.findByText(/Ada Lovelace/)).toBeInTheDocument()

    await userEvent.setup().click(await screen.findByRole('button', { name: /log out/i }))
    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    unmount()

    // A different user signs in on the same browser: point the stub at their profile, seat
    // their token as a successful login would, and mount a fresh app. Because logout emptied
    // the cache, this fetches everything as the new user rather than replaying the old one.
    stubFetch(OTHER_ME_BODY)
    setToken('user-two-token')
    renderApp()

    expect(await screen.findByText(/Grace Hopper/)).toBeInTheDocument()
    expect(screen.queryByText(/Ada Lovelace/)).toBeNull()
  })

  it('the SESSION_EXPIRED path (server-driven sign-out) also returns to login and empties the cache', async () => {
    setToken('a-valid-session-token')
    renderApp()
    expect(await screen.findByText(/Ada Lovelace/)).toBeInTheDocument()
    expect(cachedQueryCount()).toBeGreaterThan(0)

    // client.ts dispatches this after a 401 TOKEN_INVALID (having already cleared the
    // token). App's listener must flip to the login screen and drop the cache.
    await act(async () => {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT))
    })

    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    expect(screen.queryByText('Signed in')).toBeNull()
    expect(cachedQueryCount()).toBe(0)
  })
})
