/**
 * Hand-built inline SVG icons (design-system foundation — no icon dependency, per the
 * spec's Never/Ask-First boundary). Each is a 16px stroke glyph that inherits
 * `currentColor`, so a nav item recolours it for free.
 */
import type { ReactNode, SVGProps } from 'react'

type IconProps = { size?: number } & Omit<SVGProps<SVGSVGElement>, 'width' | 'height'>

function Icon({ size = 16, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  )
}

export function DashboardIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Icon>
  )
}

export function RequestLeaveIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </Icon>
  )
}

export function MyLeaveIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 6h11M8 12h11M8 18h11" />
      <path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
    </Icon>
  )
}

export function CancellationIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9l6 6M15 9l-6 6" />
    </Icon>
  )
}

export function ApprovalsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8.5 12.5l2.5 2.5 4.5-5" />
    </Icon>
  )
}

export function TeamIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <path d="M16 6.5a3 3 0 0 1 0 5.5M17 14.5a5.5 5.5 0 0 1 3.5 4.5" />
    </Icon>
  )
}

export function ReportsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 20V4M4 20h16" />
      <rect x="7" y="12" width="3" height="5" />
      <rect x="12" y="8" width="3" height="9" />
      <rect x="17" y="14" width="3" height="3" />
    </Icon>
  )
}

export function CancellationRequestsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 5h16v11H8l-4 3z" />
      <path d="M10 10l4 4M14 10l-4 4" />
    </Icon>
  )
}

export function EmployeesIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </Icon>
  )
}

export function DepartmentsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="4" y="8" width="16" height="12" rx="1.5" />
      <path d="M9 8V4h6v4M9 12h.01M15 12h.01M9 16h.01M15 16h.01" />
    </Icon>
  )
}

export function LeaveTypesIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20 12l-8 8-8-8V5a1 1 0 0 1 1-1h7z" />
      <circle cx="8.5" cy="8.5" r="1.2" />
    </Icon>
  )
}

export function HolidaysIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="4" y="5" width="16" height="16" rx="2" />
      <path d="M4 9h16M8 3v4M16 3v4" />
    </Icon>
  )
}

export function PolicyChangesIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 3h7l4 4v14H7z" />
      <path d="M13 3v5h5M9.5 13h5M9.5 16.5h5" />
    </Icon>
  )
}

export function ReviewFlagsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 21V4M6 4h11l-2 3.5 2 3.5H6" />
    </Icon>
  )
}

export function AuditLogIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M9 8h6M9 12h6M9 16h3" />
    </Icon>
  )
}

export function NotificationsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </Icon>
  )
}

export function ProfileIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </Icon>
  )
}

export function SunIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" />
    </Icon>
  )
}

export function MoonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />
    </Icon>
  )
}

export function MenuIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Icon>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
  )
}
