/**
 * The avatar (design-system foundation) — full-round. The signed-in user in the top bar
 * gets an accent gradient with their initials; a plain surface-2 fill is the fallback.
 */
export interface AvatarProps {
  name: string
  size?: number
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function Avatar({ name, size = 28 }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex items-center justify-center rounded-full font-semibold text-on-accent select-none"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.4),
        background: 'linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 60%, #000))',
      }}
    >
      {initials(name)}
    </span>
  )
}
