/**
 * The reusable button (design-system foundation). Three variants from DESIGN.md:
 * `primary` (solid accent), `secondary` (surface + strong border), `mini` (transparent,
 * table row-action). Styled with token-backed Tailwind utilities.
 */
import type { ButtonHTMLAttributes } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'mini'

const BASE =
  'inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap cursor-pointer ' +
  'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ' +
  'disabled:opacity-60 disabled:cursor-not-allowed'

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'rounded-md px-3.5 py-2 text-[13px] bg-accent text-on-accent border border-accent ' +
    'hover:brightness-110',
  secondary:
    'rounded-md px-3.5 py-2 text-[13px] bg-surface text-ink border border-line-strong ' +
    'hover:border-ink-faint',
  mini:
    'rounded-sm px-2.5 py-1 text-[12px] bg-transparent text-ink border border-line-strong ' +
    'hover:border-ink-faint',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

export function Button({ variant = 'secondary', className = '', type, ...rest }: ButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      className={`${BASE} ${VARIANTS[variant]} ${className}`.trim()}
      {...rest}
    />
  )
}
