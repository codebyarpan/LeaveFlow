/**
 * The top-bar api status pill (design-system foundation) — bordered full pill, muted text,
 * a leading `up` dot when healthy / `down` when unreachable. Mirrors the preserved
 * `useHealth` branch points; "api ok" microcopy is kept verbatim (EXPERIENCE.md Voice).
 * Ambient: it never crashes and stays quiet while checking.
 */
import { useHealth } from '../api'

export function StatusPill() {
  const { data, isPending, isError } = useHealth()

  const dot = isPending ? 'bg-ink-faint' : isError ? 'bg-down' : 'bg-up'
  const text = isPending ? 'checking…' : isError ? 'unreachable' : `api ${data.status}`

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[11.5px] text-ink-muted whitespace-nowrap"
      title={isError ? 'the api is unreachable' : undefined}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {text}
    </span>
  )
}
