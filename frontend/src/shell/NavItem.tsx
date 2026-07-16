/**
 * A single sidebar nav item (design-system foundation). Default muted text on a `sm`-radius
 * hit area; hover fills `surface-2` and lifts to `ink`; active fills `accent-soft` with
 * `accent-ink` text. Clicking routes to the surface and sets active state. Fully
 * keyboard-reachable (it is a real <button>).
 */
import type { ReactNode } from 'react'

export interface NavItemProps {
  label: string
  icon: ReactNode
  active: boolean
  onSelect: () => void
}

export function NavItem({ label, icon, active, onSelect }: NavItemProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? 'page' : undefined}
      className={
        'flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-left text-[13.5px] ' +
        'transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 ' +
        'focus-visible:ring-accent ' +
        (active
          ? 'bg-accent-soft text-accent-ink font-medium'
          : 'text-ink-muted hover:bg-surface-2 hover:text-ink')
      }
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  )
}
