/**
 * The app shell (design-system foundation) — the sidebar + top-bar console that shows one
 * surface at a time.
 *
 * A CSS-grid two-column layout (a `sidebar`-wide rail + a fluid main column). Navigation is
 * a single `useState` into `navConfig` — no router, per the spine's "no library" decision.
 * The content region mounts the active surface BARE (every panel owns its own
 * `<section className="panel"><h2>`, so the shell adds no wrapper or heading). Below the `md`
 * breakpoint the rail hides and a top-bar hamburger opens a slide-in drawer with the same
 * tree, closing on selection or backdrop tap.
 *
 * The token/session/logout wiring stays in `App.tsx`; this component receives `onLogout` and
 * reads `useMe` only to filter the nav by role and render the identity. Every panel keeps its
 * own `useMe` self-gate — hiding a nav item is convenience, never the authorization guard.
 */
import { useCallback, useEffect, useState } from 'react'

import { useMe } from '../api'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { CloseIcon } from './icons'
import { IconButton } from '../components/ui/IconButton'
import {
  DEFAULT_NAV_ID,
  NAV_ITEMS,
  isNavItemVisible,
} from './navConfig'
import type { Role } from './navConfig'

export function AppShell({ onLogout }: { onLogout: () => void }) {
  const { data: me, isPending } = useMe()
  const role = me?.role as Role | undefined

  const [activeId, setActiveId] = useState<string>(DEFAULT_NAV_ID)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const fallback = NAV_ITEMS.find((item) => item.id === DEFAULT_NAV_ID) ?? NAV_ITEMS[0]
  // If the active surface is no longer visible for this role (e.g. role resolved after a
  // default pick), fall back to Dashboard rather than mounting a hidden surface.
  const activeItem =
    NAV_ITEMS.find((item) => item.id === activeId && isNavItemVisible(item, role)) ?? fallback

  const select = useCallback((id: string) => {
    setActiveId(id)
    setDrawerOpen(false)
  }, [])

  // Escape closes the nav drawer, matching the spine's overlay convention (Esc closes the
  // topmost). Only bound while the drawer is open.
  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  return (
    <div className="min-h-screen bg-bg text-ink md:grid md:grid-cols-[var(--spacing-sidebar)_1fr]">
      {/* Desktop rail. */}
      <aside className="hidden border-r border-line md:block">
        <div className="sticky top-0 h-screen">
          <Sidebar role={role} activeId={activeItem.id} onSelect={select} />
        </div>
      </aside>

      {/* Narrow-viewport drawer. */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/50"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-[var(--spacing-sidebar)] max-w-[82%] flex-col border-r border-line bg-surface shadow-lg">
            <div className="flex justify-end p-2">
              <IconButton label="Close navigation" onClick={() => setDrawerOpen(false)}>
                <CloseIcon size={16} />
              </IconButton>
            </div>
            <div className="min-h-0 flex-1">
              <Sidebar role={role} activeId={activeItem.id} onSelect={select} />
            </div>
          </div>
        </div>
      )}

      {/* Main column. */}
      <div className="flex min-w-0 flex-col">
        <TopBar
          title={activeItem.label}
          me={me}
          meIsPending={isPending}
          onToggleDrawer={() => setDrawerOpen((open) => !open)}
          onOpenNotifications={() => select('notifications')}
          onLogout={onLogout}
        />
        <main className="flex-1 px-canvas-x py-canvas-y">
          <div className="mx-auto flex max-w-[1100px] flex-col gap-gutter">{activeItem.render()}</div>
        </main>
      </div>
    </div>
  )
}
