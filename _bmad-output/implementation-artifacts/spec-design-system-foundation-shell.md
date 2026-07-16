---
title: 'Design-system foundation & app shell — Tailwind token theme, dark-first, and the sidebar/top-bar nav shell'
type: 'feature'
created: '2026-07-16'
status: 'done'
review_loop_iteration: 0
baseline_commit: '592ad5185d9949436ea2e75696693470befef793'
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-LeaveFlow-2026-07-16/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-LeaveFlow-2026-07-16/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** LeaveFlow's frontend has no design system and no shell: styling is one hand-written `index.css` (light-only, 7 ad-hoc CSS vars) and `App.tsx` stacks all ~19 role-gated panels in a single vertical scroll with no navigation. The ratified spine (DESIGN.md + EXPERIENCE.md) calls for a Linear-direction, dark-first, Tailwind-based console — a sidebar + top-bar shell that shows one surface at a time — which nothing in the codebase currently supports. Until that foundation exists, no surface can be restyled "onto the design system."

**Approach:** Build the enabling layer only — introduce Tailwind CSS v4 with the DESIGN.md tokens wired as a runtime-switchable `@theme` (dark base + light override), a theme controller (system-aware + manual toggle, persisted), and a new sidebar/top-bar app shell with a **state-based** nav (no router) that mounts the existing panels **bare**, one at a time, with role-visible nav items. The ~18 per-surface restyles are split to `deferred-work.md`; this run does not touch any panel body, any hook, or the backend.

## Boundaries & Constraints

**Always:** Frontend-only (EXPERIENCE.md HARD CONSTRAINT) — no backend, API contract, business logic, auth, or DB change. Every panel keeps its `useMe` self-gate and its TanStack Query hooks **verbatim**; the server's 403/404 stays the real authz guard and hiding a nav item is convenience only. Dark is the default; every token ships a dark value and a `-light` counterpart (values lifted verbatim from DESIGN.md). The one accent and the status trio (`up`/`wait`/`down`) are reserved as DESIGN.md specifies. Panels render **bare** in the content region — all 19 already own their `<section className="panel"><h2>`, so the shell must not double-wrap or double-head. Preserve existing microcopy verbatim; the Bearer-token session explainer in today's shell relocates to a quieter spot, wording unchanged (EXPERIENCE.md Voice & Tone). Legacy `index.css` rules stay untouched, and the legacy color vars (`--surface`, `--ink`, `--ink-muted`, `--line`, `--up`, `--down`, `--waiting`) are aliased to the new theme tokens so un-migrated panels flip dark/light with the shell.

**Ask First:** Adding any dependency beyond `tailwindcss` + `@tailwindcss/vite` (e.g. an icon library, Recharts). Rewriting any functional copy — in particular the existing "The dashboards below are scoped to your role…" sentence, which describes the now-removed stacked layout: preserve it verbatim or escalate, do not paraphrase. Deleting or rewriting any existing `index.css` rule rather than adding alongside it.

**Never:** No backend/API/DB/auth changes. No routing dependency (react-router) — navigation is state-based per decision. No restyling of any panel body this run (Dashboard, Reports, Employees, Leave Types, Login, … are deferred and tracked in `deferred-work.md`). Do not build the deferred surface primitives (Table, Input, Dialog, Skeleton, StatCard, BalanceTrack, Chart) or add Recharts — they land with their first consuming surface. No headless component library, no second accent, no fourth hue. Never remove a panel's self-gate; nav visibility mirrors it, never replaces it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First load, no stored theme, OS dark | app mounts, `localStorage` theme unset | `data-theme` resolves to system (dark); shell renders dark tokens | N/A |
| Toggle theme | click the top-bar theme toggle | `data-theme` on `<html>` flips dark↔light, persists to `localStorage`, shell recolors; a reload keeps the choice | N/A |
| Nav select | click a sidebar item the role can see | content region swaps to that surface, mounted bare (no extra panel wrapper/heading); active state moves to the clicked item | N/A |
| Role visibility | signed in as EMPLOYEE | Manager/Admin-only nav items are hidden; Dashboard/Request Leave/My Leave/Cancellations/Notifications/Profile show; each shown panel still self-gates | N/A |
| Unread notifications | `useUnreadCount` data | bell shows the count when `unread > 0`; nothing at 0 (ambient) | error/pending → silent, no broken pill (unchanged from today) |
| Api health | `useHealth` ok / unreachable | top-bar status pill green "api ok" with `up` dot / red unreachable | error → down-state pill, never a crash |
| Narrow viewport | width below the narrow breakpoint | sidebar hides; a top-bar hamburger opens a slide-in drawer with the same tree; selecting an item or tapping the backdrop closes it | N/A |
| Log out | click Log out in the shell | identical to spec-logout: token + query cache cleared, returns to login screen | N/A |

</frozen-after-approval>

## Code Map

- `frontend/package.json` -- add devDeps `tailwindcss` + `@tailwindcss/vite` (v4, compatible with Vite 8 Rolldown). No PostCSS/config file needed in v4.
- `frontend/vite.config.ts` -- register `tailwindcss()` in `plugins` alongside `react()` (line ~35). Leave the vitest `test` block and proxy untouched.
- `frontend/src/index.css` -- prepend `@import "tailwindcss";`; add an `@theme inline` layer mapping Tailwind color/spacing/radius/typography tokens to runtime CSS vars, define dark-base values on `:root`, light overrides under `:root[data-theme="light"]` and `@media (prefers-color-scheme: light)` for unset theme; alias the 7 legacy vars to the new tokens. Keep every existing rule (shell/panel/emp/dept/login/badge) in place.
- `frontend/src/App.tsx` -- replace `AppShell`'s single-scroll `<main>` with the new shell; preserve the token/session/logout wiring (`signOut`, `handleLogout`, `SESSION_EXPIRED` listener, `useMe`) exactly; relocate the Bearer-token explainer verbatim into a quiet shell slot.
- `frontend/src/shell/` (new) -- `AppShell.tsx` (grid `[var(--spacing-sidebar)_1fr]`, `useState` active surface, Dashboard fallback, `<md` hamburger→drawer closing on select/backdrop), `Sidebar.tsx` (shared rail+drawer tree, hosts relocated microcopy), `TopBar.tsx` (title, StatusPill, unread bell, theme toggle, identity, Log out), `theme.tsx` (ThemeProvider) + `themeContext.ts` (`ThemeContext`/`useTheme`, split for fast-refresh), `navConfig.tsx` (`NAV_ITEMS` + `visibleNavItems`/`isNavItemVisible`/`DEFAULT_NAV_ID`), `NavItem.tsx`, `StatusPill.tsx`, `Avatar.tsx`, `icons.tsx` (hand-built inline SVGs, no icon dep).
- `frontend/src/components/ui/` (new) -- `Button.tsx` (primary/secondary/mini), `IconButton.tsx`, `Badge.tsx`, `Card.tsx` — the four generic token-styled primitives the shell consumes. Deferred surface primitives (Table/Input/Dialog/Skeleton/StatCard/BalanceTrack/Chart) intentionally not built.
- `frontend/src/api/{me,health,notifications}.ts` -- READ-ONLY consumers: `useMe` (`role` ∈ EMPLOYEE/MANAGER/ADMIN, `full_name`, `department.name`), `useHealth` (`{status}`), `useUnreadCount` (`{unread}`).
- `frontend/src/App.test.tsx` -- keep green; re-anchor if structure shifts (the logout button + user name must stay reachable).
- `frontend/src/features/**` -- unchanged this run; mounted bare by the shell.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/package.json` -- add `tailwindcss` and `@tailwindcss/vite` to `devDependencies` (Tailwind v4, Vite-8 compatible). No other dep. **Done:** both at `4.3.3`.
- [x] `frontend/vite.config.ts` -- add `tailwindcss()` to the `plugins` array next to `react()`; import it at top. Do not alter `test`/`server`. **Done:** `test`/`server` untouched.
- [x] `frontend/src/index.css` -- add `@import "tailwindcss";` first; add the `@theme inline` token layer + dark-base `:root` vars + light overrides (`:root[data-theme="light"]` and `@media (prefers-color-scheme: light) :root:not([data-theme])`), all values verbatim from DESIGN.md; alias legacy vars to the new tokens so un-migrated panels theme for free. Keep all existing rules; do not delete or rewrite any. (Leave the two hardcoded `#fbfcfd`/`#ffffff` values as a known transitional artifact of the deferred Employees/Login surfaces.) **Done:** `@theme inline` maps `--color-* → var(--<design-name>)`; the 6 overlapping legacy vars are the runtime source and flip for free, only `--waiting` explicitly aliased to `var(--wait)`; edit-save `cursor: not-allowed` (now L523) and the two hardcoded colors preserved.
- [x] `frontend/src/shell/theme.tsx` -- theme controller: resolve the initial theme (stored choice → else system `prefers-color-scheme`), expose current + toggle, persist the manual choice to `localStorage`, and stamp `data-theme` on `document.documentElement`. System-aware when the user has made no explicit choice. **Done:** `useTheme`/context split into `shell/themeContext.ts` for fast-refresh/oxlint cleanliness; `data-theme` stamped only for explicit choices so the CSS `prefers-color-scheme` fallback governs system mode; `matchMedia` jsdom-guarded.
- [x] `frontend/src/shell/navConfig.tsx` -- one source of truth: an ordered list of nav items `{ id, label, section, roles, render }` grouped per EXPERIENCE.md's IA (Overview / Leave / Team / Reports / Administration / Account); `roles` mirrors each panel's self-gate (Dashboard/Request Leave/Notifications/Profile = all; My Leave/Cancellations = EMPLOYEE; Approvals/My Team = MANAGER; Reports = MANAGER+ADMIN; Cancellation Requests/Employees/Departments/Leave Types/Holidays/Policy Changes/Review Flags/Audit Log = ADMIN). Default active = Dashboard, whose `render` mounts `DashboardPage` + `ManagerDashboardPanel` + `AdminDashboardPanel` together (the adaptive dashboard). **Done:** exports `NAV_ITEMS`, `visibleNavItems(role)`, `isNavItemVisible`, `DEFAULT_NAV_ID='dashboard'`; panels mounted bare (no added wrapper/heading).
- [x] `frontend/src/components/ui/{Button,IconButton,Badge,Card}.tsx` -- the reusable primitives the shell consumes and every later surface will compose, styled with the token utilities per DESIGN.md (button primary/secondary/mini, icon button, status badge, generic card). Build only these four generic primitives plus the shell atoms below; do not build the deferred surface primitives. **Done.**
- [x] `frontend/src/shell/{Sidebar,TopBar,AppShell}.tsx` (+ `NavItem`/`StatusPill`/`Avatar` atoms + `icons.tsx`) -- the shell chrome: brand mark + grouped, role-filtered nav with active state (Sidebar); title/breadcrumb, api `StatusPill` (from `useHealth`), notification bell with unread count (from `useUnreadCount`), theme toggle, avatar + identity (`full_name · role · department`), and the Log out control (TopBar); the app-shell grid + content region + narrow-viewport hamburger drawer (AppShell). Content region holds the active surface, mounted bare. **Done:** hand-built inline SVG icons (no icon dep); per-item nav-count badges NOT built (not an AC — only the top-bar unread bell is required); AppShell falls back to Dashboard when the active role can't see the current item.
- [x] `frontend/src/App.tsx` -- swap `AppShell`'s stacked `<main>` for the new shell driven by a `useState` active-surface value; keep `signOut`/`handleLogout`/`SESSION_EXPIRED` wiring and the login-gate identical; wrap in the theme controller; relocate the Bearer-token explainer verbatim to a quiet slot (footer or an inline note). **Done:** `ThemeProvider` wraps BOTH branches (login screen themed too); session wiring unchanged; explainer + "scoped to your role" + "One deployment…" relocated VERBATIM to the sidebar footer.
- [x] `frontend/src/shell/AppShell.test.tsx` (new) -- mirror `App.test.tsx`'s fetch stub (stub `/me`, `/health`, `/unread-count`; 404 the rest). Cover the I/O matrix: nav role-visibility (EMPLOYEE hides Manager/Admin items), surface switching (clicking a nav item swaps the mounted panel, no duplicate heading), theme toggle flips `data-theme` and persists across a remount, and the unread count surfaces in the top bar. **Done.**
- [x] `frontend/src/App.test.tsx` -- keep passing; update only the anchors that move (user name now in the top bar, Log out control still reachable by role name). Do not weaken the cache/token assertions. **Done:** required NO change — stayed green unmodified (name + Log out still reachable).

**Acceptance Criteria:**
- Given a signed-in user of any role, when the app loads, then the sidebar + top-bar shell renders with Dashboard active and only the dashboard panels visible (never the whole stack at once).
- Given a signed-in EMPLOYEE, when the sidebar renders, then Manager/Admin-only items are hidden while each visible panel still self-gates internally (the server remains the guard).
- Given the OS is dark and no theme has been chosen, when the app loads, then `data-theme` resolves to dark; when the user toggles, then it flips to light, persists to `localStorage`, and survives a reload.
- Given a role-visible nav item, when it is clicked, then the content region swaps to that surface mounted bare (no duplicate `.panel` wrapper or heading) and the active nav indicator moves to it.
- Given `unread > 0`, when the top bar renders, then the bell shows the count; at 0 or on error it shows none and never a broken pill — unchanged ambient behavior.
- Given the user clicks Log out, when the shell tears down, then behavior is identical to spec-logout (token + full query cache cleared, back to the login screen) and `App.test.tsx` stays green.
- Given a narrow viewport, when the sidebar collapses, then a top-bar hamburger opens a drawer with the same nav tree that closes on selection or backdrop tap.

## Spec Change Log

- **2026-07-16 (review — patches, no loopback).** Blind Hunter + Edge Case Hunter both confirmed build/lint/test green, session/logout preserved verbatim, theme resolution robust (empty/garbage localStorage + jsdom guarded), and role-visibility correct with no authz leak. No `intent_gap`/`bad_spec` → no loopback (iteration stays 0). **Patched (part of the diff):** (1) theme FOUC — added a pre-paint inline script in `index.html` mirroring `shell/theme.tsx` so a reload stamps the stored choice before first paint; (2) identity + preserved "profile unavailable"/"loading" microcopy were hidden below `lg` — lowered to `md:inline` for NFR-18 tablet usability; (3) nav drawer had no Escape-to-close (spine overlay convention) — added a keydown handler; (4) `localStorage.setItem` ran inside a state updater — moved out (StrictMode purity). **Deferred (see deferred-work.md):** full drawer focus-trap/scroll-lock/inert (Esc-to-close shipped; rest to an a11y pass); reset drawer open-state on narrow→wide→narrow resize. **Confirm-worthy (intended, not a bug):** Departments/Leave Types/Holidays are ADMIN-only in the nav though their panels render any-role read lists — matches the FROZEN I/O matrix EMPLOYEE row; logged so it can be flipped later if desired.

## Design Notes

Dark-first with runtime switching is done with Tailwind v4's `@theme inline`: utilities (`bg-surface`, `text-ink-muted`, `border-line`) compile to `var(--color-*)`, and the real values live on `:root` (dark) with `:root[data-theme="light"]` + a `prefers-color-scheme` fallback overriding them — so one `data-theme` stamp recolors everything without rebuilding. Aliasing the seven legacy vars to the new tokens is the high-leverage move: every un-migrated panel keeps its old layout but flips dark/light with the shell, so the transitional state is coherent (old spacing, new colors) rather than half-themed, and each surface migration later is a pure restyle.

The shell mounts panels bare because all 19 already render their own `<section className="panel"><h2>`; wrapping again would double the heading. `LoginPage` stays outside the shell (it owns a full-screen layout and takes `onAuthenticated`) and is deferred as its own surface. Navigation is a single `useState` index into `navConfig`, not a router — no URLs, matching the "no library" decision; the nav config is the one source both the sidebar and the content region read.

## Verification

**Commands:**
- `cd frontend && npm install` -- expected: Tailwind v4 + plugin resolve cleanly.
- `cd frontend && npm run build` -- expected: `tsc -b && vite build` succeed; Tailwind utilities compile; no type errors.
- `cd frontend && npm run lint` -- expected: oxlint clean.
- `cd frontend && npm run test` -- expected: the new `AppShell.test.tsx` passes and `App.test.tsx` stays green with the rest of the suite.

**Manual checks (if no CLI):**
- Run the app (proxy on https://localhost:8443). Sign in as admin@example.com: the sidebar shows all sections, Dashboard is active, one surface renders at a time. Toggle the theme — the whole shell flips dark↔light and the choice survives a reload. Sign in as a plain employee — Manager/Admin nav items are absent. Narrow the window — the rail collapses to a hamburger drawer. Log out — back to login.

## Suggested Review Order

**The design substrate — how DESIGN.md tokens become runtime-switchable utilities**

- Entry point: `@theme inline` maps every Tailwind color/spacing/radius utility to a live `var(--*)`, so one attribute recolours everything.
  [`index.css:26`](../../frontend/src/index.css#L26)
- Light override + system-preference fallback for the unset (system) mode — dark stays the base.
  [`index.css:123`](../../frontend/src/index.css#L123)
- Theme resolution `stored → else system`, dark-first, jsdom-guarded `matchMedia`.
  [`theme.tsx:53`](../../frontend/src/shell/theme.tsx#L53)
- Toggle computes + persists OUTSIDE the state updater (StrictMode purity — review patch).
  [`theme.tsx:63`](../../frontend/src/shell/theme.tsx#L63)
- Pre-paint inline script stamps the stored choice before first paint (no FOUC — review patch).
  [`index.html:14`](../../frontend/index.html#L14)

**The shell & state-based navigation**

- Single source of truth: the ordered, section-grouped nav model each surface routes from.
  [`navConfig.tsx:77`](../../frontend/src/shell/navConfig.tsx#L77)
- Role-visibility predicate — mirrors each panel's self-gate; convenience only, never the authz guard.
  [`navConfig.tsx:238`](../../frontend/src/shell/navConfig.tsx#L238)
- Active-surface `useState` + Dashboard fallback when a role can't see the current item; panel mounted BARE.
  [`AppShell.tsx:40`](../../frontend/src/shell/AppShell.tsx#L40)
- The narrow-viewport drawer with Escape-to-close (review patch) and close-on-select/backdrop.
  [`AppShell.tsx:69`](../../frontend/src/shell/AppShell.tsx#L69)
- Sidebar renders the role-filtered tree and hosts the relocated microcopy — verbatim, restyled container.
  [`Sidebar.tsx:68`](../../frontend/src/shell/Sidebar.tsx#L68)
- Top bar: identity + preserved "profile unavailable"/"loading" microcopy, ambient unread bell, theme toggle, Log out.
  [`TopBar.tsx:56`](../../frontend/src/shell/TopBar.tsx#L56)

**Integration & preservation (the highest-risk stop)**

- App.tsx keeps the entire session/logout/SESSION_EXPIRED wiring identical; only the shell region changed, both branches themed.
  [`App.tsx:69`](../../frontend/src/App.tsx#L69)
- Tailwind v4 plugged into Vite beside `react()`; `test`/`server` blocks untouched.
  [`vite.config.ts:36`](../../frontend/vite.config.ts#L36)

**Peripherals — primitives & tests**

- The four generic token-styled primitives the shell consumes (Button/IconButton/Badge/Card).
  [`Button.tsx:1`](../../frontend/src/components/ui/Button.tsx#L1)
- Shell test: nav role-visibility, surface switching, theme toggle + persistence, unread in the top bar.
  [`AppShell.test.tsx:1`](../../frontend/src/shell/AppShell.test.tsx#L1)
