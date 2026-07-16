/**
 * The single source of truth for navigation (design-system foundation).
 *
 * An ordered, grouped list of nav items the sidebar renders and the content region reads.
 * `roles` MIRRORS each panel's own `useMe` self-gate — it never replaces it. Hiding an item
 * is convenience only; the server's 403/404 stays the real authorization guard, and every
 * panel still self-gates and calls its own gated endpoint. Panels mount BARE: all 19 already
 * render their own `<section className="panel"><h2>`, so the shell adds no wrapper or heading.
 */
import type { ReactNode } from 'react'

import { AuditLogPanel } from '../features/audit/AuditLogPanel'
import { AdminDashboardPanel } from '../features/dashboard/AdminDashboardPanel'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { ManagerDashboardPanel } from '../features/dashboard/ManagerDashboardPanel'
import { DepartmentsPage } from '../features/departments/DepartmentsPage'
import { EmployeesPage } from '../features/employees/EmployeesPage'
import { HolidaysPage } from '../features/holidays/HolidaysPage'
import { CancellationRequestsPanel } from '../features/leave/CancellationRequestsPanel'
import { ManagerQueuePanel } from '../features/leave/ManagerQueuePanel'
import { MyLeaveHistoryPanel } from '../features/leave/MyLeaveHistoryPanel'
import { RequestCancellationPanel } from '../features/leave/RequestCancellationPanel'
import { RequestPreviewPanel } from '../features/leave/RequestPreviewPanel'
import { LeaveTypesPage } from '../features/leaveTypes/LeaveTypesPage'
import { NotificationsPanel } from '../features/notifications/NotificationsPanel'
import { PolicyChangesPanel } from '../features/policyChanges/PolicyChangesPanel'
import { ProfilePage } from '../features/profile/ProfilePage'
import { ReportsPanel } from '../features/reports/ReportsPanel'
import { ReviewFlagsPanel } from '../features/reviewFlags/ReviewFlagsPanel'
import { MyTeamPanel } from '../features/team/MyTeamPanel'

import {
  ApprovalsIcon,
  AuditLogIcon,
  CancellationIcon,
  CancellationRequestsIcon,
  DashboardIcon,
  DepartmentsIcon,
  EmployeesIcon,
  HolidaysIcon,
  LeaveTypesIcon,
  MyLeaveIcon,
  NotificationsIcon,
  PolicyChangesIcon,
  ProfileIcon,
  ReportsIcon,
  RequestLeaveIcon,
  ReviewFlagsIcon,
  TeamIcon,
} from './icons'

export type Role = 'EMPLOYEE' | 'MANAGER' | 'ADMIN'

/** Sidebar section labels, in IA order (EXPERIENCE.md). */
export type NavSection = 'Overview' | 'Leave' | 'Team' | 'Reports' | 'Administration' | 'Account'

export const NAV_SECTION_ORDER: NavSection[] = [
  'Overview',
  'Leave',
  'Team',
  'Reports',
  'Administration',
  'Account',
]

export interface NavItemModel {
  id: string
  label: string
  section: NavSection
  /** Which roles may see the item. `'all'` = every authenticated role. Mirrors the self-gate. */
  roles: 'all' | Role[]
  icon: (props: { size?: number }) => ReactNode
  /** The surface mounted (bare) in the content region when this item is active. */
  render: () => ReactNode
}

export const NAV_ITEMS: NavItemModel[] = [
  // Overview — the adaptive dashboard: one surface composed of the three role panels, each
  // keeping its own self-gate (additive, never a fork).
  {
    id: 'dashboard',
    label: 'Dashboard',
    section: 'Overview',
    roles: 'all',
    icon: DashboardIcon,
    render: () => (
      <>
        <DashboardPage />
        <ManagerDashboardPanel />
        <AdminDashboardPanel />
      </>
    ),
  },

  // Leave
  {
    id: 'request-leave',
    label: 'Request Leave',
    section: 'Leave',
    roles: 'all',
    icon: RequestLeaveIcon,
    render: () => <RequestPreviewPanel />,
  },
  {
    id: 'my-leave',
    label: 'My Leave',
    section: 'Leave',
    roles: ['EMPLOYEE'],
    icon: MyLeaveIcon,
    render: () => <MyLeaveHistoryPanel />,
  },
  {
    id: 'cancellations',
    label: 'Cancellations',
    section: 'Leave',
    roles: ['EMPLOYEE'],
    icon: CancellationIcon,
    render: () => <RequestCancellationPanel />,
  },

  // Team
  {
    id: 'approvals',
    label: 'Approvals',
    section: 'Team',
    roles: ['MANAGER'],
    icon: ApprovalsIcon,
    render: () => <ManagerQueuePanel />,
  },
  {
    id: 'my-team',
    label: 'My Team',
    section: 'Team',
    roles: ['MANAGER'],
    icon: TeamIcon,
    render: () => <MyTeamPanel />,
  },

  // Reports
  {
    id: 'reports',
    label: 'Leave Report',
    section: 'Reports',
    roles: ['MANAGER', 'ADMIN'],
    icon: ReportsIcon,
    render: () => <ReportsPanel />,
  },

  // Administration
  {
    id: 'cancellation-requests',
    label: 'Cancellation Requests',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: CancellationRequestsIcon,
    render: () => <CancellationRequestsPanel />,
  },
  {
    id: 'employees',
    label: 'Employees',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: EmployeesIcon,
    render: () => <EmployeesPage />,
  },
  {
    id: 'departments',
    label: 'Departments',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: DepartmentsIcon,
    render: () => <DepartmentsPage />,
  },
  {
    id: 'leave-types',
    label: 'Leave Types',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: LeaveTypesIcon,
    render: () => <LeaveTypesPage />,
  },
  {
    id: 'holidays',
    label: 'Holidays',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: HolidaysIcon,
    render: () => <HolidaysPage />,
  },
  {
    id: 'policy-changes',
    label: 'Policy Changes',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: PolicyChangesIcon,
    render: () => <PolicyChangesPanel />,
  },
  {
    id: 'review-flags',
    label: 'Review Flags',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: ReviewFlagsIcon,
    render: () => <ReviewFlagsPanel />,
  },
  {
    id: 'audit-log',
    label: 'Audit Log',
    section: 'Administration',
    roles: ['ADMIN'],
    icon: AuditLogIcon,
    render: () => <AuditLogPanel />,
  },

  // Account
  {
    id: 'notifications',
    label: 'Notifications',
    section: 'Account',
    roles: 'all',
    icon: NotificationsIcon,
    render: () => <NotificationsPanel />,
  },
  {
    id: 'profile',
    label: 'Profile',
    section: 'Account',
    roles: 'all',
    icon: ProfileIcon,
    render: () => <ProfilePage />,
  },
]

/** The default surface after sign-in. */
export const DEFAULT_NAV_ID = 'dashboard'

/** Whether a role may see an item (undefined role — still loading — sees only `'all'`). */
export function isNavItemVisible(item: NavItemModel, role: Role | undefined): boolean {
  if (item.roles === 'all') return true
  if (!role) return false
  return item.roles.includes(role)
}

/** The items a role may see, in IA order. */
export function visibleNavItems(role: Role | undefined): NavItemModel[] {
  return NAV_ITEMS.filter((item) => isNavItemVisible(item, role))
}
