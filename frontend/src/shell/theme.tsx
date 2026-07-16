/**
 * The theme controller (design-system foundation).
 *
 * Dark is the base; light is a fully specified override. The resolved theme is
 * `stored choice → else OS preference`. A manual toggle stamps `data-theme` on
 * `<html>` and persists the choice to `localStorage`; when no explicit choice has been
 * made, the attribute is ABSENT so the `@media (prefers-color-scheme)` fallback in
 * `index.css` governs (system-aware by default). One `data-theme` stamp recolours every
 * token-backed utility and every aliased legacy var.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ThemeContext } from './themeContext'
import type { Theme, ThemeContextValue } from './themeContext'

const STORAGE_KEY = 'leaveflow-theme'

/** The `(prefers-color-scheme: dark)` query, guarded for jsdom (no `matchMedia`). */
function darkQuery(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
  return window.matchMedia('(prefers-color-scheme: dark)')
}

function systemPrefersDark(): boolean {
  // Dark-first: with no signal to the contrary (e.g. jsdom), default to dark.
  return darkQuery()?.matches ?? true
}

function readStored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // `null` means "follow the system" — no explicit choice has been made yet.
  const [explicit, setExplicit] = useState<Theme | null>(() => readStored())
  const [systemDark, setSystemDark] = useState<boolean>(() => systemPrefersDark())

  // Keep the resolved theme reactive to OS changes while in system mode (no-op in jsdom).
  useEffect(() => {
    const mql = darkQuery()
    if (!mql) return
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  const resolved: Theme = explicit ?? (systemDark ? 'dark' : 'light')

  // Stamp the explicit choice on <html>; drop the attribute in system mode so the
  // prefers-color-scheme fallback in index.css takes over.
  useEffect(() => {
    const root = document.documentElement
    if (explicit) root.setAttribute('data-theme', explicit)
    else root.removeAttribute('data-theme')
  }, [explicit])

  const toggle = useCallback(() => {
    // Compute + persist OUTSIDE the state updater — updaters must stay pure (StrictMode
    // double-invokes them). `resolved` is the current on-screen theme, so a toggle from
    // system mode correctly commits the opposite of what the user is actually seeing.
    const next: Theme = resolved === 'dark' ? 'light' : 'dark'
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Persistence is best-effort; the choice still holds for this page load.
    }
    setExplicit(next)
  }, [resolved])

  const value = useMemo<ThemeContextValue>(() => ({ theme: resolved, toggle }), [resolved, toggle])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
