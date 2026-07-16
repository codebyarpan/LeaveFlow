/**
 * The top bar (design-system foundation): the active surface title left; right-aligned
 * actions — the api status pill, the notification bell with its unread count, the theme
 * toggle, the signed-in identity (avatar + full name · role · department), and the Log out
 * control. A hamburger appears only on narrow viewports to open the nav drawer.
 *
 * The unread bell mirrors the preserved `useUnreadCount` branch points: silent while loading
 * or on error, nothing at zero (an unread count is ambient — a broken pill is worse than
 * none). Identity keeps the "loading your profile…" / "profile unavailable" microcopy.
 */
import { useUnreadCount } from '../api'
import type { MeResponse } from '../api'
import { Button } from '../components/ui/Button'
import { IconButton } from '../components/ui/IconButton'
import { Avatar } from './Avatar'
import { MenuIcon, MoonIcon, NotificationsIcon, SunIcon } from './icons'
import { StatusPill } from './StatusPill'
import { useTheme } from './themeContext'

interface TopBarProps {
  title: string
  me: MeResponse | undefined
  meIsPending: boolean
  onToggleDrawer: () => void
  onOpenNotifications: () => void
  onLogout: () => void
}

/** The unread bell — ambient, so it stays silent while loading or on error. */
function UnreadBell({ onOpen }: { onOpen: () => void }) {
  const { data, isPending, isError } = useUnreadCount()
  const unread = isPending || isError ? 0 : data.unread

  return (
    <IconButton label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'} onClick={onOpen}>
      <NotificationsIcon size={16} />
      {unread > 0 && (
        <span className="absolute -right-1 -top-1 inline-flex min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold leading-4 text-on-accent tabular-nums">
          {unread}
        </span>
      )}
    </IconButton>
  )
}

export function TopBar({
  title,
  me,
  meIsPending,
  onToggleDrawer,
  onOpenNotifications,
  onLogout,
}: TopBarProps) {
  const { theme, toggle } = useTheme()

  const identity = me
    ? `${me.full_name} · ${me.role} · ${me.department.name}`
    : meIsPending
      ? 'loading your profile…'
      : 'profile unavailable'

  return (
    <header
      className="sticky top-0 z-20 flex h-topbar items-center gap-3 border-b border-line px-4"
      style={{ background: 'color-mix(in srgb, var(--bg) 82%, transparent)', backdropFilter: 'blur(8px)' }}
    >
      <IconButton label="Open navigation" onClick={onToggleDrawer} className="md:hidden">
        <MenuIcon size={16} />
      </IconButton>

      <h1 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h1>

      <div className="ml-auto flex items-center gap-2.5">
        <div className="hidden sm:block">
          <StatusPill />
        </div>

        <UnreadBell onOpen={onOpenNotifications} />

        <IconButton
          label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          onClick={toggle}
        >
          {theme === 'dark' ? <SunIcon size={16} /> : <MoonIcon size={16} />}
        </IconButton>

        <div className="flex items-center gap-2 pl-1">
          {me && <Avatar name={me.full_name} />}
          <span className="hidden text-[12.5px] text-ink-muted md:inline">{identity}</span>
        </div>

        <Button variant="secondary" onClick={onLogout} className="!px-3 !py-1.5 !text-[12.5px]">
          Log out
        </Button>
      </div>
    </header>
  )
}
