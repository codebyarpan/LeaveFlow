/**
 * The Leave Types edit form's "why won't Save respond?" behavior (spec-fix-leave-type-edit-save).
 *
 * The bug this pins: an Admin opens "Edit policy", changes a balance-affecting attribute, and Save
 * stays disabled — correctly, because the server demands a Recalculate/Preserve disposition — but the
 * screen never said so next to the button, and the disabled cursor read as "loading". These tests
 * assert the button's enabled/disabled state AND the adjacent reason hint across the I/O matrix.
 *
 * `fetch` is stubbed: `/me` returns an Admin (so the edit controls render), `GET /leave-types` returns
 * one carrying-forward type (so a balance-affecting edit is reachable), and `PATCH /leave-types/{id}`
 * answers a benign command result. The create form is always present for an Admin and repeats the same
 * field labels, so every field/radio query is scoped with `within(editForm)`.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '../../api'
import { LeaveTypesPage } from './LeaveTypesPage'

const ADMIN_ME = {
  id: 'emp-1',
  full_name: 'Admin',
  email: 'admin@example.com',
  role: 'ADMIN',
  department: { id: 'dep-1', name: 'Administration' },
  joining_date: '2020-01-01',
}

// A carrying-forward type, so changing entitlement or the cap is balance-affecting and trips the
// disposition gate.
const EARNED_LEAVE = {
  id: 'lt-el',
  code: 'EL',
  name: 'Earned Leave',
  annual_entitlement: 12,
  carries_forward: true,
  carry_forward_cap: 30,
  requires_supporting_document: false,
}

const LEAVE_TYPES_PAGE = { items: [EARNED_LEAVE], page: 1, page_size: 50, total: 1 }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/v1/me')) return jsonResponse(ADMIN_ME)
    if (url.includes('/api/v1/leave-types')) {
      if (init?.method === 'PATCH') {
        return jsonResponse({
          leave_type: EARNED_LEAVE,
          recalculation: { requests_recalculated: 0, pairs_recalculated: 0, pairs_refused: [] },
        })
      }
      return jsonResponse(LEAVE_TYPES_PAGE)
    }
    return jsonResponse({ code: 'NOT_FOUND', message: 'test', details: {} }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <LeaveTypesPage />
    </QueryClientProvider>,
  )
}

/** Open the inline edit form on the one row and return the Save button + its form for scoping. */
async function openEdit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: /edit policy/i }))
  const save = screen.getByRole('button', { name: /save policy/i })
  const form = save.closest('form') as HTMLElement
  return { save, form }
}

describe('LeaveTypesPage — edit form Save state and reason hint', () => {
  beforeEach(() => {
    localStorage.clear()
    setToken('a-valid-session-token')
    stubFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('on open with no change: Save is disabled and a hint asks for a change', async () => {
    const user = userEvent.setup()
    renderPage()
    const { save } = await openEdit(user)

    expect(save).toBeDisabled()
    expect(screen.getByText('Make a change to save.')).toBeInTheDocument()
  })

  it('name-only edit: Save enables, no disposition prompt, no reason hint', async () => {
    const user = userEvent.setup()
    renderPage()
    const { save, form } = await openEdit(user)

    const name = within(form).getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Earned Leave (renamed)')

    expect(save).toBeEnabled()
    expect(screen.queryByText('Make a change to save.')).toBeNull()
    expect(screen.queryByText('Choose Recalculate or Preserve above to save.')).toBeNull()
    expect(within(form).queryByRole('radio', { name: /recalculate/i })).toBeNull()
  })

  it('balance-affecting edit without a disposition: Save stays disabled with the disposition hint', async () => {
    const user = userEvent.setup()
    renderPage()
    const { save, form } = await openEdit(user)

    const entitlement = within(form).getByLabelText('Annual entitlement (days)')
    await user.clear(entitlement)
    await user.type(entitlement, '20')

    expect(save).toBeDisabled()
    expect(screen.getByText('Choose Recalculate or Preserve above to save.')).toBeInTheDocument()
    expect(within(form).getByRole('radio', { name: /recalculate/i })).toBeInTheDocument()
  })

  it('balance-affecting edit with a disposition chosen: Save enables and the hint clears', async () => {
    const user = userEvent.setup()
    renderPage()
    const { save, form } = await openEdit(user)

    const entitlement = within(form).getByLabelText('Annual entitlement (days)')
    await user.clear(entitlement)
    await user.type(entitlement, '20')
    await user.click(within(form).getByRole('radio', { name: /recalculate/i }))

    expect(save).toBeEnabled()
    expect(screen.queryByText('Choose Recalculate or Preserve above to save.')).toBeNull()
  })

  it('while a save is in flight: the button reads Saving… and no reason hint shows', async () => {
    // Hold the PATCH open so the mutation stays `isPending` and we can assert the in-flight UI.
    // The `!isPending` guard on the hint is the one non-obvious branch in the change.
    let releasePatch!: (value: Response) => void
    const patchInFlight = new Promise<Response>((resolve) => {
      releasePatch = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/api/v1/me')) return jsonResponse(ADMIN_ME)
        if (url.includes('/api/v1/leave-types')) {
          if (init?.method === 'PATCH') return patchInFlight
          return jsonResponse(LEAVE_TYPES_PAGE)
        }
        return jsonResponse({ code: 'NOT_FOUND', message: 'test', details: {} }, 404)
      }),
    )

    const user = userEvent.setup()
    renderPage()
    const { save, form } = await openEdit(user)

    // A name-only change enables Save; submitting it puts the mutation in flight.
    const name = within(form).getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Earned Leave (renamed)')
    await user.click(save)

    // In flight: the label carries the loading signal, and NEITHER reason hint is shown.
    expect(await screen.findByRole('button', { name: /saving/i })).toBeInTheDocument()
    expect(screen.queryByText('Make a change to save.')).toBeNull()
    expect(screen.queryByText('Choose Recalculate or Preserve above to save.')).toBeNull()

    // Let the request complete so the form settles (avoids a dangling pending mutation at teardown).
    releasePatch(
      jsonResponse({
        leave_type: EARNED_LEAVE,
        recalculation: { requests_recalculated: 0, pairs_recalculated: 0, pairs_refused: [] },
      }),
    )
    await screen.findByRole('button', { name: /edit policy/i })
  })
})
