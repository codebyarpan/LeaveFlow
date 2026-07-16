/**
 * The generic card (design-system foundation) — the surface container: `surface` fill,
 * hairline `line` border, `lg` radius. Depth is carried by the border, never a shadow.
 */
import type { HTMLAttributes, ReactNode } from 'react'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

export function Card({ className = '', children, ...rest }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-line bg-surface ${className}`.trim()}
      {...rest}
    >
      {children}
    </div>
  )
}
