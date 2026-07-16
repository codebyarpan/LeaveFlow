---
name: LeaveFlow
product: LeaveFlow
status: final
updated: 2026-07-16
sources:
  - ./DESIGN.md
  - ./.memlog.md
---

# LeaveFlow — Experience Spine

> This EXPERIENCE.md and its peer `DESIGN.md` are the canonical spine. **The spine wins over any mock on conflict** — the key-screen mock (`.working/key-screen-dashboard.html`) is a ratified illustration, not an authority above it. Visual values and component looks are owned by `DESIGN.md` and referenced here by `{path.to.token}`; this file owns behavior.

## Foundation

LeaveFlow is a responsive **web app** — the internal leave-management console for a single organization ("one deployment, one organization"). The redesign restyles the existing surfaces into a Linear-direction shell (sidebar + top bar, dark-first with a light override). `DESIGN.md` is the visual reference; this spine is how it behaves.

**Styling system: Tailwind CSS** plus a small set of hand-built reusable React components (Card, Table, Badge, Button, Input, Dialog, and the shell primitives). No headless component library. `DESIGN.md`'s tokens map into a Tailwind theme extension.

**HARD CONSTRAINT — frontend-only.** This redesign changes layout, visuals, component extraction, and client routing **only**. It does **not** touch the backend, API contracts, business logic, authentication, authorization, or the database. All ~18 existing role-gated panels and every TanStack Query hook they use (`useEmployeeDashboard`, `useManagerDashboard`, `useAdminDashboard`, `useLeaveRequests`, `usePreviewLeaveRequest`, `useSubmitLeaveRequest`, `useTeam`, `useCancellationRequests`, `usePolicyChanges`, `useAdminReviewFlags`, `useAuditEntries`, `useNotifications`, …) are preserved as-is. Stack: React 19 + TanStack Query + Vite.

**Role model.** Three roles — EMPLOYEE, MANAGER, ADMIN. Each panel already self-gates via `useMe` and renders `null` when the signed-in role can't use it; the redesign additionally hides the nav item that would lead there. **The client is not the authorization boundary** — the server's `403`/`404` (role checks and scope predicates) remains the real guard. Hiding a nav item is a convenience, never a security control; every panel still calls its own gated endpoint.

## Information Architecture

Group-by-function sidebar. Items are hidden unless the signed-in role can reach them; the per-panel `useMe` self-gate stays the source of truth, and the server remains the authz guard.

| Section · Item | Role visibility | App.tsx surface | Primary hooks |
|---|---|---|---|
| **Overview** · Dashboard | All (adaptive by role) | `DashboardPage` + `ManagerDashboardPanel` + `AdminDashboardPanel` | `useEmployeeDashboard`, `useBalances`, `useManagerDashboard`, `useAdminDashboard` |
| **Leave** · Request Leave | All (role `any`, scope self) | `RequestPreviewPanel` | `useLeaveTypes`, `useBalances`, `usePreviewLeaveRequest`, `useSubmitLeaveRequest` |
| **Leave** · My Leave | Employee only | `MyLeaveHistoryPanel` | `useLeaveRequests` |
| **Leave** · Cancellations | Employee only | `RequestCancellationPanel` | `useLeaveRequests` (approved), `useRaiseCancellationRequest` |
| **Team** · Approvals *(dept leave calendar embedded at decision)* | Manager only | `ManagerQueuePanel` | `useLeaveRequests` (reports), `useCalendar`, `useApproveLeaveRequest`, `useRejectLeaveRequest` |
| **Team** · My Team | Manager only | `MyTeamPanel` | `useTeam` |
| **Reports** · Leave Report + CSV | Manager & Admin | `ReportsPanel` | `useLeaveRequests` (report scope) + CSV export |
| **Administration** · Cancellation Requests | Admin only | `CancellationRequestsPanel` | `useCancellationRequests`, `useApproveCancellationRequest`, `useRejectCancellationRequest` |
| **Administration** · Employees | Admin only | `EmployeesPage` | `useEmployees`, `useCreateEmployee`, `useUpdateEmployee`, `useDeactivateEmployee` |
| **Administration** · Departments | Admin section *(list endpoint is any-role; create/rename/delete Admin-only)* | `DepartmentsPage` | `useDepartments`, `useCreateDepartment`, `useRenameDepartment`, `useDeleteDepartment` |
| **Administration** · Leave Types | Admin section *(list any-role; create/edit Admin-only)* | `LeaveTypesPage` | `useLeaveTypes`, `useCreateLeaveType`, `useUpdateLeaveType` |
| **Administration** · Holidays | Admin section *(list any-role; add/delete Admin-only)* | `HolidaysPage` | `useHolidays`, `useCreateHoliday`, `useDeleteHoliday` |
| **Administration** · Policy Changes | Admin only | `PolicyChangesPanel` | `usePolicyChanges` |
| **Administration** · Review Flags | Admin only | `ReviewFlagsPanel` | `useAdminReviewFlags` |
| **Administration** · Audit Log | Admin only `[ASSUMPTION]` — self-gates like its section peers | `AuditLogPanel` | `useAuditEntries` |
| **Account** · Notifications | All (no role gate — server addressee scope is the guard) | `NotificationsPanel` | `useNotifications`, `useUnreadCount`, `useMarkNotificationRead` |
| **Account** · Profile | All (role `any`) | `ProfilePage` | `useMe`, `useUpdateMe` |

**Adaptive Dashboard.** Dashboard is ONE surface, the post-login landing page, composed of role panels: Employee balances + pending-request count always; a Manager's queue-summary added for managers; an Admin's org-wide totals added for admins. It hosts the **net-new charts** (balance usage, pending counts, employees-on-leave). Each sub-panel keeps its own `useMe` self-gate and renders `null` when the role can't use it — the composition is additive, never a fork.

**Department leave calendar** (Story 3.3) is embedded inside Approvals at decision time (via `useCalendar`), **not** a standalone nav item.

→ Composition reference: `.working/key-screen-dashboard.html` (Admin Dashboard). Spine wins on conflict.

## Voice and Tone

**Preserve the existing precise, plain, no-marketing voice.** The current microcopy is functional and exact; the redesign presents it in cleaner type, it does not rewrite it. Implementation-detail asides may move to a less prominent placement, but their wording is preserved verbatim.

| Keep (existing voice) | Never |
|---|---|
| "One deployment, one organization." | "Streamline your team's time off! ✨" |
| "The session is a Bearer token held in the browser. It is attached to every request, and the server signs you out when it rejects one." *(may relocate to a quieter spot; wording unchanged)* | Deleting or paraphrasing the explainer to "tidy up" |
| "profile unavailable" / "loading your profile…" | "Oops! Something went wrong 😬" |
| "api ok" | "All systems operational! 🎉" |
| Counts and verbs: "12 pending", "Approve", "Reject", "View all 12 →" | Padded status prose: "You currently have 12 items awaiting review." |

Rule: do not touch functional copy. Restyle the container, keep the words.

## Component Patterns

Behavioral only. Visual specs live in `DESIGN.md`; each row references the owning component by name.

| Pattern | DESIGN.md component | Behavior |
|---|---|---|
| Nav item | `{components.nav-item}` / `{components.nav-item-active}` | Click routes to the surface and sets active state. Trailing `{components.nav-count}` shows a live count (pending approvals, pending cancellations, unread) sourced from the same hook the target surface uses; it inverts to accent when active. Hidden entirely when the role can't reach it. |
| Approvals row | `{components.table}` + `{components.button-mini}` | Approve/Reject mini buttons act inline; on success the queue and affected balances refresh via the existing TanStack Query invalidation (optimistic where the current code already is). The row's `{components.badge-pending}` flips to approved/rejected. Opening a row surfaces the embedded department calendar at decision time. |
| Cancellation-request row | `{components.table}` + `{components.button-mini}` | Admin approve/reject; on success the list refetches (`useCancellationRequests` invalidated). No client-side day count — server figures render as-is. |
| Request Leave form | `{components.input}` + `{components.button-primary}` | Pick Leave Type + range → `usePreviewLeaveRequest` returns the day count, projected balance, and named excluded dates. Submit calls `useSubmitLeaveRequest`; on success the balances query invalidates so **Available falls immediately**. |
| Stat card | `{components.stat-card}` | Read-only figure from a dashboard hook; tabular value never shifts width on refetch. |
| Balance track | `{components.balance-track}` | Fill width = remaining/entitlement from `useBalances`; fraction label is tabular. Skeleton track while pending. |
| Chart | `{components.chart}` | Dashboards only, read-only. Renders from dashboard-hook data; flat bar/line, no interaction beyond a segmented range toggle (7d/14d/30d) that re-reads the same data. Charts library `[ASSUMPTION]` Recharts (per memlog, pending build-time confirm). |
| Badge / status pill | `{components.badge-*}` / `{components.status-pill}` | Leave state → approved/pending/rejected/neutral. Top-bar api pill reflects `useHealth` (ok / unreachable). |
| Dialog | `{components.dialog}` | Used for confirm/edit flows (e.g. employee edit); Esc and backdrop close; one level deep, never stacked. |
| List + Pager | `{components.table}` | My Leave, Reports, and other paged lists reuse the existing `Pager` control (see Interaction Primitives). |

## State Patterns

Mapped to the preserved TanStack Query branch points — `isPending`, `isError`, `data`.

| State | Branch | Treatment |
|---|---|---|
| Loading | `isPending` | `{components.skeleton}` shimmer shaped to the content — stat cards, balance tracks, table rows — replacing today's text "loading…". |
| Loaded | `data` | Render figures as-is (client renders server numbers verbatim, AD-2). Prefer cached `data` over a failed background refetch so a name/figure never blanks. |
| Empty | `data` length 0 | Icon + one-line message + a single primary action (e.g. empty approvals queue → "Nothing awaiting your decision." + Request Leave / relevant primary). |
| Error | `isError` | Inline retry affordance at the panel scope (message + a retry button that refetches), not a full-screen error. Ambient indicators (unread badge, api pill) stay silent on error rather than showing a broken pill. |

## Interaction Primitives

- **Navigation** — one nav model across breakpoints (see Responsive & Platform). Click to route; active item reflects the current surface. Fully keyboard-reachable.
- **Theme toggle** — top-bar `{components.icon-button}`. System-aware by default (follows OS light/dark); the toggle is a manual override that stamps `data-theme` on the root and persists the choice.
- **Pagination** — the existing `Pager` component (My Leave was the app's first pagination UI; Reports reuses it). Pagination only — no infinite scroll.
- **Form submit / validation** — inline validation on `{components.input}`; the server is the sole authority for day counts and balances (client never computes them). Submit disabled while pending; success invalidates the relevant queries.
- **Dialogs** — Esc closes the topmost; backdrop click closes; focus is trapped while open; one level deep.
- **Command palette (⌘K)** — **out of scope** for this redesign; logged as a future enhancement, not a spine feature.

## Accessibility Floor

The stated floor — honestly, **no formal WCAG AA commitment** (WCAG was a declared project non-goal; this redesign does not add one).

- Legible contrast in **both** themes — the `-light` and dark token sets are tuned for readable text on their surfaces.
- **Full keyboard navigation** — every surface, nav item, control, and dialog is operable without a mouse. Tab order matches reading order; Esc closes modals/popovers.
- **Visible focus rings** — the accent focus ring is now more important because dark mode exists; focus is never suppressed.
- **Semantic tables and forms** — real `<table>`/`<th>`/`<td>`, labeled form controls, so assistive tech reads structure.

This is a floor, not an AA conformance claim. Do not imply certification.

## Responsive & Platform

One nav model, three tiers of the same collapsible sidebar:

| Breakpoint | Sidebar | Content |
|---|---|---|
| Desktop (wide) | Full labeled rail (`{spacing.sidebar-w}`) | Multi-column grids (4-up stat cards, chart + balances split). |
| Medium | Icon-only rail (labels hidden, icons + counts remain; tooltip on hover) | Grids reflow to fewer columns. |
| Narrow | Hidden; hamburger in the top bar opens a slide-in drawer (same tree) | Single column; the drawer closes on selection or backdrop tap. |

**Responsive tables** — wide tables scroll horizontally inside their card (`overflow-x`) rather than breaking layout; numeric columns stay tabular and aligned. LeaveFlow is responsive web (works on phones for read + simple actions), primary surface is desktop.

`[ASSUMPTION]` The concrete icon set is unspecified — the mock uses placeholder glyphs. Any consistent line-icon library (or hand-built SVGs) satisfies the rail; icons must remain visible in the icon-only tier.

## Key Flows

### Flow 1 — Mary, a manager, clears her Thursday approvals queue

1. Mary lands on **Dashboard**; her queue-summary panel shows "12 pending", and the sidebar **Approvals** item carries a `{components.nav-count}` of 4 for her reports.
2. She opens **Team · Approvals**. The `{components.table}` lists her Direct Reports' pending requests, each a `{components.badge-pending}` row with Approve/Reject mini buttons.
3. She opens Mary Chen's row; the **embedded department leave calendar** surfaces at decision time — she sees no clash that week.
4. She clicks **Approve**.
5. **Climax:** the row's badge flips to approved, the queue count drops to 3, the Dashboard "pending" figure and the nav count refresh together — all from the existing query invalidation, no reload. She clears the rest and the queue shows the empty state: "Nothing awaiting your decision."

Failure: an approve call errors → inline retry on that row; the badge stays pending until it succeeds.

### Flow 2 — Arpan, an admin, changes a leave-type policy and sees the disposition

1. Arpan opens **Administration · Leave Types**, edits an entitlement on a type, and saves (`useUpdateLeaveType`).
2. The list refetches with the new value; the edit dialog closes.
3. He opens **Administration · Policy Changes**.
4. **Climax:** the new entry sits at the top of the `{components.table}` — old value, new value, and the **disposition applied to balances that already existed** — the record of *why* a balance is the number it is. Nothing here lets him amend it; it is append-only by design. He confirms the disposition matches intent and moves on.

Failure: the update errors → inline retry in the form; no Policy Changes entry appears, because nothing was committed.

### Flow 3 — James, an employee, requests leave and watches Available fall

1. James opens **Leave · Request Leave** (`RequestPreviewPanel`).
2. He picks Annual Leave and a range; `usePreviewLeaveRequest` returns the day count, the **projected balance**, and the named excluded dates (holidays/weekends).
3. He submits (`useSubmitLeaveRequest`).
4. **Climax:** on success the balances query invalidates — his **Available annual-leave figure falls immediately** on the same surface (and on the Dashboard balance track), tabular digits stepping down without a reload. The server computed every number; the client only rendered it.
5. He opens **Leave · My Leave** and sees the new request at the top, `{components.badge-pending}`, awaiting his manager — closing the loop with Flow 1.

Failure: submit errors → inline retry; Available is unchanged because nothing was committed.
