---
name: LeaveFlow
product: LeaveFlow
status: final
updated: 2026-07-16
description: Leave-management console for one organization. Linear-direction, dark-first, dense and low-chrome. Implemented on Tailwind CSS + hand-built React components; these tokens map to a Tailwind theme extension (CSS variables → theme tokens).
colors:
  # Dark is the base/default theme (dark-first). Light values are the `-light`
  # override set, applied under :root[data-theme="light"] and system light preference.
  # Values are lifted verbatim from the ratified key-screen mock's :root blocks.
  # ---- Base (dark) ----
  bg: '#0b0c0e'            # app canvas
  surface: '#141518'      # cards, sidebar, top bar
  surface-2: '#191b1f'    # hover, nested, tracks, muted fills
  line: '#26282e'         # hairline borders
  line-strong: '#34373f'  # stronger dividers, control borders
  ink: '#e9eaec'          # primary text
  ink-muted: '#9498a3'    # secondary text
  ink-faint: '#6b6f7a'    # tertiary text, eyebrow labels
  accent: '#6e79f0'       # the ONE accent — indigo/violet
  accent-soft: '#6e79f01f'
  accent-ink: '#aeb5ff'   # accent text on soft accent (active nav)
  up: '#3fb27f'           # approved / positive
  up-soft: '#3fb27f1f'
  down: '#e5615a'         # rejected / negative / alert dot
  down-soft: '#e5615a1f'
  wait: '#d9a441'         # pending / waiting
  wait-soft: '#d9a4411f'
  on-accent: '#ffffff'    # text/icon on solid accent fills
  # ---- Light overrides ----
  bg-light: '#f7f8fa'
  surface-light: '#ffffff'
  surface-2-light: '#f2f3f5'
  line-light: '#e7e9ee'
  line-strong-light: '#d6d9e0'
  ink-light: '#14161a'
  ink-muted-light: '#5c6470'
  ink-faint-light: '#878e9a'
  accent-light: '#5b63e0'
  accent-soft-light: '#5b63e014'
  accent-ink-light: '#4b52c9'
  up-light: '#0f7b4f'
  up-soft-light: '#0f7b4f14'
  down-light: '#b3261e'
  down-soft-light: '#b3261e14'
  wait-light: '#8a6400'
  wait-soft-light: '#8a640014'
typography:
  fontFamily:
    sans: "-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif"
    mono: "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace"
  body:
    fontFamily: '{typography.fontFamily.sans}'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: -0.006em
  page-title:
    fontSize: 21px
    fontWeight: '650'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  stat-figure:
    fontSize: 26px
    fontWeight: '650'
    letterSpacing: -0.02em
    # rendered with tabular-nums — see Typography body
  card-title:
    fontSize: 13.5px
    fontWeight: '600'
  nav-item:
    fontSize: 13.5px
    fontWeight: '400'
  eyebrow:
    # nav section label / small caps eyebrows
    fontSize: 10.5px
    fontWeight: '600'
    letterSpacing: 0.07em
  table-header:
    fontSize: 11px
    fontWeight: '600'
    letterSpacing: 0.05em
  badge:
    fontSize: 11.5px
    fontWeight: '550'
  button:
    fontSize: 13px
    fontWeight: '550'
  mono:
    fontFamily: '{typography.fontFamily.mono}'
rounded:
  xs: 5px      # segmented-control inner selection
  sm: 7px      # nav item, segmented outer, table row-action buttons
  md: 8px      # button, input/select, icon button
  lg: 10px     # card, stat card, dialog, panel
  full: 9999px # badge, status pill, count badge, avatar, balance track
spacing:
  '1': 4px
  '2': 6px
  '3': 8px
  '4': 12px
  '5': 14px
  '6': 16px
  '7': 20px
  '8': 24px
  gutter: 14px       # grid gap between cards / stat cells
  canvas-x: 26px     # main content horizontal padding
  canvas-y: 24px     # main content top padding
  sidebar-w: 232px   # expanded rail width
  topbar-h: 52px
elevation:
  shadow: '0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6)'
  shadow-light: '0 1px 2px rgba(20,22,26,.05), 0 8px 24px -14px rgba(20,22,26,.18)'
components:
  app-shell:
    grid: '{spacing.sidebar-w} 1fr'
    background: '{colors.bg}'
  sidebar:
    background: '{colors.surface}'
    border-right: '1px solid {colors.line}'
    width: '{spacing.sidebar-w}'
  nav-item:
    color: '{colors.ink-muted}'
    radius: '{rounded.sm}'
    hover-background: '{colors.surface-2}'
    hover-color: '{colors.ink}'
  nav-item-active:
    background: '{colors.accent-soft}'
    color: '{colors.accent-ink}'
    fontWeight: '500'
  nav-count:
    background: '{colors.surface-2}'
    color: '{colors.ink-muted}'
    radius: '{rounded.full}'
    active-background: '{colors.accent}'
    active-color: '{colors.on-accent}'
  topbar:
    height: '{spacing.topbar-h}'
    border-bottom: '1px solid {colors.line}'
    background: 'color-mix(in srgb, {colors.bg} 82%, transparent)'
  stat-card:
    background: '{colors.surface}'
    border: '1px solid {colors.line}'
    radius: '{rounded.lg}'
    label-color: '{colors.ink-muted}'
    figure: '{typography.stat-figure}'
    delta-color: '{colors.ink-faint}'
  card:
    background: '{colors.surface}'
    border: '1px solid {colors.line}'
    radius: '{rounded.lg}'
    title: '{typography.card-title}'
  table:
    header-color: '{colors.ink-faint}'
    header: '{typography.table-header}'
    row-border-top: '1px solid {colors.line}'
    row-hover-background: '{colors.surface-2}'
  badge-approved:
    color: '{colors.up}'
    background: '{colors.up-soft}'
    radius: '{rounded.full}'
  badge-pending:
    color: '{colors.wait}'
    background: '{colors.wait-soft}'
    radius: '{rounded.full}'
  badge-rejected:
    color: '{colors.down}'
    background: '{colors.down-soft}'
    radius: '{rounded.full}'
  badge-neutral:
    color: '{colors.ink-muted}'
    background: '{colors.surface-2}'
    radius: '{rounded.full}'
  button-primary:
    background: '{colors.accent}'
    border: '1px solid {colors.accent}'
    color: '{colors.on-accent}'
    radius: '{rounded.md}'
    font: '{typography.button}'
  button-secondary:
    background: '{colors.surface}'
    border: '1px solid {colors.line-strong}'
    color: '{colors.ink}'
    radius: '{rounded.md}'
    hover-border: '{colors.ink-faint}'
  button-mini:
    background: 'transparent'
    border: '1px solid {colors.line-strong}'
    color: '{colors.ink}'
    radius: '{rounded.sm}'
    ok-hover-color: '{colors.up}'
    danger-hover-color: '{colors.down}'
  icon-button:
    background: '{colors.surface}'
    border: '1px solid {colors.line}'
    color: '{colors.ink-muted}'
    radius: '{rounded.md}'
  input:
    background: '{colors.surface}'
    border: '1px solid {colors.line-strong}'
    color: '{colors.ink}'
    radius: '{rounded.md}'
    focus-ring: '{colors.accent}'
  status-pill:
    border: '1px solid {colors.line}'
    color: '{colors.ink-muted}'
    radius: '{rounded.full}'
    ok-dot: '{colors.up}'
  avatar:
    radius: '{rounded.full}'
    background: '{colors.surface-2}'
  balance-track:
    background: '{colors.surface-2}'
    radius: '{rounded.full}'
    fill-default: '{colors.accent}'
    fill-up: '{colors.up}'
    fill-wait: '{colors.wait}'
  chart:
    bar-fill: '{colors.accent}'
    bar-muted: '{colors.surface-2}'
    axis-color: '{colors.ink-faint}'
  skeleton:
    base: '{colors.surface-2}'
    highlight: '{colors.line}'
    radius: '{rounded.sm}'
  dialog:
    background: '{colors.surface}'
    border: '1px solid {colors.line}'
    radius: '{rounded.lg}'
    shadow: '{elevation.shadow}'
---

# LeaveFlow — Visual Design Spine

> This DESIGN.md and its peer EXPERIENCE.md are the canonical spine. **The spine wins over any mock on conflict** — the key-screen mock (`.working/key-screen-dashboard.html`) is a ratified illustration of these tokens, not an authority above them.

## Brand & Style

LeaveFlow is the internal leave-management console for a single organization — the place an employee requests time off, a manager clears a queue, and an admin governs policy. The redesign takes its direction from **Linear**: dark-first, dense but breathable, focused, low chrome, one indigo/violet accent, muted grays, and tabular numerals wherever figures line up. Stripe, Vercel, and Notion inform details (the hairline-bordered card, the quiet segmented control, the precise eyebrow label) but Linear governs.

The posture is *instrument, not brochure*. Surfaces are quiet so the data reads loud: hairline borders instead of heavy dividers, flat fills instead of gradients, near-zero elevation except where a surface genuinely floats (dialogs, popovers). Both color modes are first-class — **dark is the default**, light is a fully specified override that follows OS preference with a manual toggle. Every token below ships a dark base value and a `-light` counterpart.

Implementation is **Tailwind CSS** plus a small set of hand-built reusable React components — no headless component library. The token groups in this file are authored to drop into a Tailwind theme extension: each CSS variable becomes a theme token, so `bg-surface`, `text-ink-muted`, `border-line` resolve to the values here.

## Colors

One accent, three status hues, a muted gray spine. That is the whole palette.

- **Canvas & surfaces** — `{colors.bg}` is the app canvas; `{colors.surface}` is every card, the sidebar, and the top bar; `{colors.surface-2}` is the one step up used for hover, nested fills, balance tracks, and muted chart bars. Depth is carried by these three fills and hairline borders, not by shadow.
- **Lines** — `{colors.line}` is the default hairline (card borders, table row rules, sidebar edge). `{colors.line-strong}` is reserved for control borders (secondary buttons, inputs) and stronger dividers.
- **Ink** — `{colors.ink}` primary text, `{colors.ink-muted}` secondary, `{colors.ink-faint}` tertiary and eyebrow labels. Three steps, no more.
- **Accent (`{colors.accent}` dark / `{colors.accent-light}` light)** — the single brand color. Used for the active nav item (as `{colors.accent-soft}` fill with `{colors.accent-ink}` text), the primary button, chart bars, the default balance-track fill, and focus rings. It is *never* used for status. One accent, and stop.
- **Status trio** — `{colors.up}` (approved / positive), `{colors.wait}` (pending / waiting), `{colors.down}` (rejected / negative). Each pairs with its `-soft` tint for badge backgrounds. These three carry all leave-state meaning; they are not used as chrome or decoration.

The light overrides (`-light` tokens) darken the status hues and ink for contrast on white and soften the accent — pulled verbatim from the mock's `:root[data-theme="light"]` block. Do not introduce a fourth hue or a second accent.

## Typography

System sans (`{typography.fontFamily.sans}` — SF/Inter/Segoe stack) for everything; `{typography.fontFamily.mono}` only where digits must not jitter but a proportional face already has tabular figures, so mono is rarely needed. Base is `{typography.body}` — 14px, 1.5 line-height, a faint negative tracking that gives the dense UI its Linear tightness.

Roles:

- **`{typography.page-title}`** — the surface H1 ("Good afternoon, Arpan").
- **`{typography.stat-figure}`** — the big number on a stat card. Always rendered with `font-variant-numeric: tabular-nums`.
- **`{typography.card-title}`** — card and panel headers.
- **`{typography.eyebrow}`** — uppercase nav-section labels and small caps eyebrows.
- **`{typography.table-header}`** — uppercase column headers.
- **`{typography.nav-item}`**, **`{typography.badge}`**, **`{typography.button}`** — as named.

**Tabular numerals are a rule, not a flourish:** every figure that lines up in a column or updates in place — stat values, day counts, balance fractions ("14.5 / 25"), table numeric cells — uses tabular figures so nothing shifts on change.

## Layout & Spacing

Two-column app shell: a `{spacing.sidebar-w}` sidebar rail and a fluid main column; the top bar is `{spacing.topbar-h}` tall. Main content sits in a scroll canvas padded `{spacing.canvas-y}` top and `{spacing.canvas-x}` sides.

The spacing scale is compact (`{spacing.1}`–`{spacing.8}`, 4→24px) — density is a feature. Cards and stat cells are laid out on grids with a `{spacing.gutter}` (14px) gap: stat cards in a 4-up row, the dashboard's chart+balances in a ~1.55/1 two-column split, tables full-bleed inside their card. Breakpoint behavior (rail → icon rail → drawer, and how tables reflow) is owned by EXPERIENCE.md's Responsive & Platform section; the token widths above are the anchors it references.

## Elevation & Depth

Low chrome is the discipline. Depth comes from the three surface fills and hairline borders, **not** from shadow. `{elevation.shadow}` (and its `-light` counterpart) exists for exactly the surfaces that truly float above the canvas — dialogs, popovers, and the segmented-control's active selection chip. Cards, the sidebar, and the top bar carry a border, never a drop shadow. No layered/stacked shadows, no glow, no colored shadow.

## Shapes

A tight radius ramp: `{rounded.xs}` (5px) for the segmented-control selection, `{rounded.sm}` (7px) for nav items and row-action buttons, `{rounded.md}` (8px) for buttons, inputs, and icon buttons, `{rounded.lg}` (10px) for cards, panels, and dialogs, `{rounded.full}` for anything pill-shaped — badges, status pills, count badges, avatars, balance tracks. Corners read "tool," not "consumer app": crisp, never pillowy.

## Components

Visual specs for the reusable set the mock demonstrates. Behavior lives in EXPERIENCE.md; these are the looks.

- **App shell** (`{components.app-shell}`) — `{spacing.sidebar-w}` sidebar + fluid main on `{colors.bg}`. Sidebar (`{components.sidebar}`) is `{colors.surface}` with a `{colors.line}` right edge; brand mark top-left (accent-gradient square, "L"). Top bar (`{components.topbar}`) is `{spacing.topbar-h}` tall with a translucent `color-mix` background and a `{colors.line}` bottom rule; holds breadcrumb/title left, and right-aligned actions: api-status pill, notification bell, theme toggle, avatar.
- **Nav item** (`{components.nav-item}`) — default `{colors.ink-muted}` text, `{rounded.sm}` hit area; hover fills `{colors.surface-2}` and lifts text to `{colors.ink}`. Active (`{components.nav-item-active}`) fills `{colors.accent-soft}` with `{colors.accent-ink}` text at weight 500. Optional trailing **count badge** (`{components.nav-count}`): `{colors.surface-2}`/`{colors.ink-muted}` pill, inverting to `{colors.accent}`/`{colors.on-accent}` when the item is active.
- **Stat card** (`{components.stat-card}`) — `{colors.surface}` card, `{rounded.lg}`. Small `{colors.ink-muted}` label with a leading glyph, big `{typography.stat-figure}` value (tabular), and a `{colors.ink-faint}` descriptor line; an optional trend uses `{colors.up}` (▲) or `{colors.down}`.
- **Card** (`{components.card}`) — the generic container: `{colors.surface}`, `{colors.line}` border, `{rounded.lg}`. Card head is a title (`{typography.card-title}`) with an optional right-side control (segmented toggle, "View all →" link, or button).
- **Table** (`{components.table}`) — uppercase `{typography.table-header}` headers in `{colors.ink-faint}`, no header rule; body rows separated by a `{colors.line}` top border, hover fills `{colors.surface-2}`. Numeric columns are tabular and right-aligned; a trailing actions column is right-aligned and holds mini buttons.
- **Badge** — pill (`{rounded.full}`) with a leading status dot. `{components.badge-approved}` (green), `{components.badge-pending}` (amber), `{components.badge-rejected}` (red), `{components.badge-neutral}` (gray, for states outside the trio). Color-on-soft-tint pairing per token.
- **Button** — **primary** (`{components.button-primary}`): solid `{colors.accent}`, `{colors.on-accent}` text, brightens on hover. **Secondary** (`{components.button-secondary}`): `{colors.surface}` with `{colors.line-strong}` border, border brightens to `{colors.ink-faint}` on hover. **Mini** (`{components.button-mini}`): transparent, `{rounded.sm}`, used in table rows — the "ok" variant borders/text to `{colors.up}` on hover, the "no" variant to `{colors.down}`. **Icon button** (`{components.icon-button}`): 30px square, `{colors.line}` border, `{colors.ink-muted}` glyph.
- **Input / Select / Form field** (`{components.input}`) — `{colors.surface}` fill, `{colors.line-strong}` border, `{rounded.md}`; focus shows a visible `{colors.accent}` ring. Labels use `{colors.ink-muted}`; validation errors use `{colors.down}` text + a `{colors.down}` border.
- **Status pill** (`{components.status-pill}`) — the top-bar api indicator: bordered `{rounded.full}` pill, `{colors.ink-muted}` text, leading `{colors.up}` dot when healthy (down state uses `{colors.down}`).
- **Avatar** (`{components.avatar}`) — `{rounded.full}`; initials on `{colors.surface-2}` in tables, or an accent gradient for the signed-in user in the top bar.
- **Progress / balance track** (`{components.balance-track}`) — 6px `{rounded.full}` track on `{colors.surface-2}`; fill is `{colors.accent}` by default, `{colors.up}` or `{colors.wait}` to signal a healthy or low remaining balance. Fraction label ("14.5 / 25") is tabular.
- **Chart** (`{components.chart}`) — flat bar/line only. Bars fill `{colors.accent}` (a subtle top-down fade to a transparent accent is the *only* permitted gradient), muted/weekend bars use `{colors.surface-2}`, axis labels `{colors.ink-faint}`. No 3D, no heavy gradients, no drop shadow. Charts appear on dashboards only.
- **Skeleton loader** (`{components.skeleton}`) — shimmer sweep between `{colors.surface-2}` and `{colors.line}`, `{rounded.sm}`; shaped to the content it replaces (text bars, track fills, table rows).
- **Dialog / modal** (`{components.dialog}`) — `{colors.surface}`, `{colors.line}` border, `{rounded.lg}`, and the one place `{elevation.shadow}` is used to lift the surface off a dimmed canvas.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Carry depth with the three surface fills + hairline `{colors.line}` borders | Reach for drop shadows; reserve `{elevation.shadow}` for dialogs/popovers only |
| Keep dark as the default; ship the `-light` value for every token | Treat light mode as an afterthought or leave a token half-themed |
| Use `{colors.accent}` for the one accent — active nav, primary action, chart, focus ring | Use the accent for status, or introduce a second accent / fourth hue |
| Reserve `{colors.up}`/`{colors.wait}`/`{colors.down}` for leave state only | Use status hues as chrome or decoration |
| Render every aligned/updating figure with tabular numerals | Let stat values, day counts, or balances shift width on change |
| Stay dense but breathable on the compact `{spacing}` scale | Inflate padding to "modern SaaS" airiness — density is the point |
| Keep charts flat (dashboards only) | Add 3D, heavy gradients, or charts to Reports (tables + CSV stay) |
| Present the existing precise, plain microcopy in cleaner type | Rewrite functional copy or add marketing voice (owned by EXPERIENCE.md) |
