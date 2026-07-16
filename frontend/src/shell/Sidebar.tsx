/**
 * The sidebar rail (design-system foundation): brand mark + grouped, role-filtered nav with
 * active state, and a quiet footer note. The nav tree is shared verbatim between the desktop
 * rail and the narrow-viewport drawer — this component is the single renderer for both.
 *
 * The footer note is the "quiet slot" the relocated microcopy lives in: the role-scope
 * sentence and the Bearer-token session explainer are preserved VERBATIM (EXPERIENCE.md
 * Voice & Tone — restyle the container, keep the words), alongside the "One deployment, one
 * organization." footer copy.
 */
import { NavItem } from './NavItem'
import { NAV_SECTION_ORDER, visibleNavItems } from './navConfig'
import type { NavSection, Role } from './navConfig'

export interface SidebarProps {
  role: Role | undefined
  activeId: string
  onSelect: (id: string) => void
}

export function Sidebar({ role, activeId, onSelect }: SidebarProps) {
  const items = visibleNavItems(role)

  return (
    <nav aria-label="Primary" className="flex h-full flex-col bg-surface">
      {/* Brand mark — accent-gradient square, "L". */}
      <div className="flex items-center gap-2.5 px-4 py-3.5">
        <span
          aria-hidden="true"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[15px] font-bold text-on-accent"
          style={{
            background:
              'linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #000))',
          }}
        >
          L
        </span>
        <span className="text-[15px] font-semibold tracking-tight text-ink">LeaveFlow</span>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 pb-4">
        {NAV_SECTION_ORDER.map((section: NavSection) => {
          const sectionItems = items.filter((item) => item.section === section)
          if (sectionItems.length === 0) return null
          return (
            <div key={section} className="mb-4">
              <div className="px-2.5 pb-1.5 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
                {section}
              </div>
              <div className="flex flex-col gap-0.5">
                {sectionItems.map((item) => (
                  <NavItem
                    key={item.id}
                    label={item.label}
                    icon={<item.icon size={16} />}
                    active={item.id === activeId}
                    onSelect={() => onSelect(item.id)}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>

      <div className="space-y-2 border-t border-line px-4 py-3 text-[11.5px] leading-relaxed text-ink-muted">
        <p>
          The dashboards below are scoped to your role: everyone sees their own balances and
          pending requests; a Manager additionally sees their team&apos;s, and an Admin the
          organization&apos;s (Story 3.5).
        </p>
        <p>
          The session is a Bearer token held in the browser. It is attached to every request,
          and the server signs you out when it rejects one.
        </p>
        <p className="text-ink-faint">One deployment, one organization.</p>
      </div>
    </nav>
  )
}
