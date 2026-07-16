/**
 * The icon button (design-system foundation) — a ~30px square control used in the top bar
 * (theme toggle, notification bell, hamburger). Surface fill, hairline border, muted glyph
 * that lifts to `ink` on hover. Requires an accessible label since it carries only a glyph.
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required — the button shows only an icon, so screen readers need this name. */
  label: string
  children: ReactNode
}

export function IconButton({ label, className = '', type, children, ...rest }: IconButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      aria-label={label}
      title={label}
      className={
        'relative inline-flex h-[30px] w-[30px] items-center justify-center rounded-md ' +
        'bg-surface text-ink-muted border border-line cursor-pointer transition-colors ' +
        'hover:text-ink hover:border-ink-faint ' +
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ' +
        className
      }
      {...rest}
    >
      {children}
    </button>
  )
}
