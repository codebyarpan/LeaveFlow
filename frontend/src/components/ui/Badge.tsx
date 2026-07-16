/**
 * The status badge (design-system foundation) — a pill with a leading status dot.
 * Four tones from DESIGN.md: `approved` (green), `pending` (amber), `rejected` (red),
 * `neutral` (gray, for states outside the leave-status trio). Color-on-soft-tint per token.
 */
import type { ReactNode } from 'react'

export type BadgeTone = 'approved' | 'pending' | 'rejected' | 'neutral'

const TONES: Record<BadgeTone, string> = {
  approved: 'text-up bg-up-soft',
  pending: 'text-wait bg-wait-soft',
  rejected: 'text-down bg-down-soft',
  neutral: 'text-ink-muted bg-surface-2',
}

export interface BadgeProps {
  tone?: BadgeTone
  /** Show the leading status dot (default true). */
  dot?: boolean
  className?: string
  children: ReactNode
}

export function Badge({ tone = 'neutral', dot = true, className = '', children }: BadgeProps) {
  return (
    <span
      className={
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ' +
        'whitespace-nowrap ' +
        TONES[tone] +
        ' ' +
        className
      }
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  )
}
