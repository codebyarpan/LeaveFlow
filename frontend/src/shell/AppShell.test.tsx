/**
 * The app shell (design-system foundation), exercised through the real `App`.
 *
 * Mirrors `App.test.tsx`'s fetch stub: `/me`, `/health`, `/unread-count` succeed and every
 * other endpoint answers a benign 404, so each role's panels fall to their empty/error
 * states rather than crashing. A token is seated so the token gate mounts the shell.
 *
 * Covers the I/O matrix: role-based nav visibility (an EMPLOYEE never sees Manager/Admin
 * items), surface switching (a nav click swaps the mounted surface, no duplicate heading),
 * the theme toggle (flips `data-theme` on <html> and persists), and the unread count in the
 * top bar.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { queryClient, setToken } from './../api'
import { App } from './../App'

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

function stubFetch(meBody: typeof ME_BODY = ME_BODY, unread = 0) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/me')) return jsonResponse(meBody)
    if (url.endsWith('/api/v1/health')) return jsonResponse({ status: 'ok' })
    if (url.endsWith('/unread-count')) return jsonResponse({ unread })
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

describe('app shell', () => {
  beforeEach(() => {
    localStorage.clear()
    queryClient.clear()
    document.documentElement.removeAttribute('data-theme')
    stubFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
    queryClient.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('hides Manager/Admin nav items from an EMPLOYEE, keeps the all-role items', async () => {
    setToken('a-valid-session-token')
    renderApp()

    // Wait for the shell to settle on the signed-in EMPLOYEE.
    expect(await screen.findByRole('button', { name: 'Dashboard' })).toBeInTheDocument()

    // All-role nav items are present…
    expect(screen.getByRole('button', { name: 'Profile' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request Leave' })).toBeInTheDocument()

    // …while Manager/Admin-only items are hidden entirely.
    expect(screen.queryByRole('button', { name: 'Approvals' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Employees' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Leave Report' })).toBeNull()
  })

  it('swaps the mounted surface when a nav item is clicked', async () => {
    setToken('a-valid-session-token')
    renderApp()

    // Dashboard is the default active surface.
    expect(await screen.findByRole('heading', { name: 'My dashboard' })).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Profile' }))

    // The content region now holds the Profile surface (mounted bare — the panel's own <h2>,
    // distinct from the top-bar <h1> title) and the dashboard heading is gone: one surface at
    // a time, never the whole stack.
    expect(await screen.findByRole('heading', { name: 'Profile', level: 2 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'My dashboard' })).toBeNull()
  })

  it('flips data-theme on <html> and persists the choice when the theme toggle is used', async () => {
    setToken('a-valid-session-token')
    renderApp()

    const toggle = await screen.findByRole('button', { name: /switch to .* theme/i })

    // No explicit choice yet — the attribute is absent and the OS preference governs.
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()

    const user = userEvent.setup()
    await user.click(toggle)

    const firstChoice = document.documentElement.getAttribute('data-theme')
    expect(firstChoice === 'light' || firstChoice === 'dark').toBe(true)
    expect(localStorage.getItem('leaveflow-theme')).toBe(firstChoice)

    // Toggling again flips to the other theme and re-persists.
    await user.click(await screen.findByRole('button', { name: /switch to .* theme/i }))
    const secondChoice = document.documentElement.getAttribute('data-theme')
    expect(secondChoice).not.toBe(firstChoice)
    expect(localStorage.getItem('leaveflow-theme')).toBe(secondChoice)
  })

  it('shows the unread count in the top bar when unread > 0', async () => {
    stubFetch(ME_BODY, 3)
    setToken('a-valid-session-token')
    renderApp()

    // The bell surfaces the count (and names it for assistive tech).
    expect(await screen.findByRole('button', { name: /3 unread/i })).toBeInTheDocument()
  })
})
