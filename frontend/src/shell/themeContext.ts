/**
 * The theme context and its hook (design-system foundation). Kept separate from the
 * provider component so the provider file exports only a component (fast-refresh clean).
 */
import { createContext, useContext } from 'react'

export type Theme = 'light' | 'dark'

export interface ThemeContextValue {
  /** The resolved theme actually in effect (explicit choice, else the OS preference). */
  theme: Theme
  /** Flip dark↔light; the flip becomes an explicit, persisted choice. */
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used within a ThemeProvider')
  return value
}
