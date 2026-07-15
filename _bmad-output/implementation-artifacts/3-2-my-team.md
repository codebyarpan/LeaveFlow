---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

<!--
  Story context created 2026-07-14 by create-story (ultimate context engine).
  Sources: epics.md §Epic 3 / Story 3.2; ARCHITECTURE-SPINE.md (AD-10, FR-19 map);
  api-contracts.md §1/§2/§4.9; erd.md §2.1/§4.4; prd.md FR-19; deferred-work.md;
  story files 3-1, 2-8, 2-12; live working tree (3.1 in review, UNCOMMITTED, atop 4fc1629).
  ⚠️ The working tree is DIRTY with Story 3.1's changes — build on top of them, do not
  revert or commit them.
-->

# Story 3.2: My Team

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Manager,
I want to see the Employees who report to me,
So that I know whose leave is mine to decide.

## Orientation: what this story actually is

**A small, genuinely new read surface — the first Manager-facing employee read.**
`GET /api/v1/team` does not exist in any form today; no Manager can list employees at all
(`GET /employees` is Admin-only, five endpoints, all `require_role(authz.ROLE_ADMIN)`).
But every part it is assembled from already exists and was left waiting for it, some by name:

| Need | Already exists at |
|---|---|
| The scope predicate | `repositories/scoping.py:73` — `Scope.REPORTS` → `Employee.manager_id == actor.id` |
| The seam, promised by name | `services/employee.py:392-394` docstring: "…leaving Story 1.7's Manager-scoped variant **a change of scope, not signature**"; `repositories/employee.py` `get_employee` already takes `scope: Scope = Scope.ALL` — `list_employees` just never grew the param |
| The index | `employee (manager_id)` — models.py:82's own comment: "my team walks this edge" (erd.md §4.4, NFR-12's "manager" access path) |
| The role gate + 403 | `require_role(authz.ROLE_MANAGER)` → `assert_role` → `DomainError(ACTION_NOT_PERMITTED)`; **already mapped to 403 in `main.py:56`** — no `main.py` change |
| Every display column | `Employee.full_name`, `Employee.is_active`, `department` eager-load — `repositories/employee.py::list_employees` already selects, orders (`full_name, id`) and eager-loads all of it |
| Pagination | `api/v1/pagination.py` — `PageParams` + `Page[T]`, `MAX_PAGE_SIZE=100`, `MAX_PAGE` clamp (3.1's Open Decision #5, already landed) |
| Frontend Manager gate | `ManagerQueuePanel.tsx:46-57` — `useMe()` + `role === 'MANAGER'` + `{ enabled }` + `return null` |
| Frontend "(deactivated)" marker | `EmployeesPage.tsx:402-405` — `.emp-inactive` span; class exists in `index.css:421-425` |
| Frontend pager | `MyLeaveHistoryPanel.tsx:203-222` (Story 3.1, in this working tree) — this story is its **second caller** (Open Decision #2) |

So the whole story is: thread `scope` through the one existing employee list read, mount it
behind a Manager-only route at a new path, project a **minimal** response (Open Decision #1),
and render the app's second pager on a Manager-gated panel. No migration, no model change,
no new vocabulary, no new error code, no `main.py` change, no scope-matrix entry (no path
param), no new repo getter needed (extend the existing one), no new CSS, no new dependency.

**The one contract surprise to internalize now: the Admin gets 403 here.** Nearly every
read in this app grants Admin `ALL`; api-contracts §4.9 grants `/team` to **Manager only**,
and AC4 pins the Admin refusal explicitly. An Admin sees everyone through `GET /employees`;
"my team" is a fact about a reporting edge only a Manager has. `require_role(authz.ROLE_MANAGER)`
gives this for free — do not add Admin, do not special-case it.

## Acceptance Criteria

*(From epics.md:1450-1476, verbatim clauses compressed; FR-19 at prd.md:386-396.)*

1. **Given** an authenticated Manager, **when** they call `GET /api/v1/team`, **then** the
   response contains exactly their Direct Reports and no other Employee (`FR-19`, `AD-10`).
2. **Given** each entry in that list, **when** it is inspected, **then** it identifies the
   Employee by Full Name and names their Department (`FR-19`).
3. **Given** a Direct Report who has been deactivated, **when** the list is returned,
   **then** they are distinguishable from an active one (`FR-19`).
4. **Given** an Employee or an Admin, **when** they call `GET /api/v1/team`, which
   api-contracts §4.9 grants to a Manager, **then** the response is `403` with code
   `ACTION_NOT_PERMITTED`, decided by the role gate before any row is read (`G3`,
   api-contracts §1).
5. **Given** the React application and an authenticated Manager, **when** they open their
   team screen, **then** they see their Direct Reports with Department and active state.

## 🚨 Landmines. Read all seven before writing a line.

### Landmine 1 — Deactivated reports must be IN the list. Do not reach for the "active" helpers.

AC3 says a deactivated Direct Report is *distinguishable* — which means **present**.
`Scope.REPORTS`'s predicate (`Employee.manager_id == actor.id`) has no `is_active` filter,
and that is correct — leave it alone. The trap is nearby, twice over:
`repositories/employee.py::count_active_direct_reports` (:187) filters `is_active` (it
serves the AD-22 deactivation guard, a different question), and `EmployeesPage.tsx:418`
branches on `!employee.is_active` to disable an action. Copy either active-only habit into
this read and AC3 fails silently — a deactivated report just vanishes instead of rendering
"(deactivated)". Pin presence with a test: one
active and one deactivated report, both returned, `is_active` carried on the wire.

### Landmine 2 — `api/` may not import `Scope`. The REPORTS decision lives in the service.

`Scope` lives in `app/repositories/scoping.py`, and import-linter contract 2 ("api/ talks
only to services/ (AD-1)") forbids `api/` importing `app.repositories` (or `app.domain`) —
`allow_indirect_imports` notwithstanding, a direct import fails the build. So the route
must NOT pass a scope; the new service function hardcodes `Scope.REPORTS` (the role gate
guarantees the caller is a Manager). Same reason `api/` names roles as `authz.ROLE_MANAGER`
via `services/authorization.py:36`'s re-export — never `from app.domain import vocabulary`,
and never the literal `"MANAGER"` (tests/test_vocabulary_literals.py AST-scans everything
under `app/` for vocabulary values; the frontend is outside its scan and may keep using
`'MANAGER'` as `ManagerQueuePanel.tsx:26` does).

### Landmine 3 — Extend `list_employees`; do not write a new repo getter.

`tests/test_scoped_getters.py` forces any new `list_*`/`get_*` repository function taking
`session` to also take a param literally named `actor` (`_ACTOR_PARAM_NAMES`, :149) or join
the `EXEMPT` registry with a rationale. `repositories/employee.py::list_employees` already
takes `actor`, already applies `employee_scope_predicate`, already eager-loads `department`
(`joinedload` — without it the route's `department.name` projection raises
`DetachedInstanceError` on the closed session), already orders `full_name, id` for
deterministic pages, and already returns `(rows, total)` from one round-trip. Add a
defaulted `scope: Scope = Scope.ALL` param (the exact shape `get_employee` already has at
:131, three functions down) and replace the hardcoded `Scope.ALL` at :108 with it. Existing
callers (`services/employee.py:397`, Admin list) are untouched by the default. Zero
`EXEMPT` changes, zero new getter, and the Admin path is provably byte-identical.

### Landmine 4 — Registration is two edits in `router.py`, or everything 404s; and NO guard files change.

- A new `app/api/v1/team.py` router does nothing until `app/api/v1/router.py` gains it in
  BOTH the import tuple (:12-26) and an `include_router(team.router)` line (:28-41). The
  `/api/v1` prefix comes from `main.py:37` — write `@router.get("/team")`, not
  `"/api/v1/team"`.
- `GET /team` has **no path parameter → it is OUT of the SM-3 scope matrix by
  construction** (`tests/test_scope_matrix.py:31-35` docstring names this class of route;
  only `{`-bearing paths must register). Do not add it to `_SCOPE_REGISTRY`.
- No new error code, no vocabulary entry, no `CODE_TO_STATUS` change (`ACTION_NOT_PERMITTED`
  mapped since 1.4), no migration (`alembic check` must stay clean), no model change.
  If `main.py`, `vocabulary.py`, `test_scope_matrix.py`, `test_scoped_getters.py`, or any
  `alembic/` file appears in your diff, you have taken a wrong turn.

### Landmine 5 — The 403 must be the gate's, with the envelope, for BOTH wrong roles.

AC4's "decided by the role gate before any row is read" is satisfied by construction —
`require_role` runs as a dependency before the route body — but the test must still pin the
observable contract: for an Admin token AND an Employee token, `GET /api/v1/team` → 403,
body exactly `{"code", "message", "details"}` with `code == vocabulary.ACTION_NOT_PERMITTED`
and `details == {}`. The template is `tests/integration/test_role_gate.py:149-169`
(parametrize over `[ROLE_ADMIN, ROLE_EMPLOYEE]` here). Anonymous stays 401 via the auth
dependency — no story work, but a cheap assertion if you're touching the file anyway.

### Landmine 6 — Frontend: `enabled` gating, no day-count tokens, encode every param.

- Gate the panel AND the query: `useTeam(..., { enabled: isManager })` plus
  `if (!isManager) return null` — otherwise every Employee/Admin session fires a guaranteed
  403 against `/team` on mount (`ManagerQueuePanel.tsx:46-57` is the exact idiom).
- `backend/tests/test_frontend_no_client_day_count.py` line-scans `frontend/src` for
  `getDay`/`getUTCDay` tokens **even in comments** (tripped 2.5 and 2.7 first drafts).
  Nothing in this panel needs date math at all — render `full_name`, `department.name`,
  `is_active` verbatim.
- Any query param interpolated into the URL goes through `encodeURIComponent` (the 2.7
  review rule, documented at `leaveRequests.ts:167-169` with the encoding calls just
  below it). For `/team` that is
  `page`/`page_size` only — there are no filters on this endpoint (no AC asks for any; do
  not invent them).
- Features import ONLY from the `api/index.ts` barrel (features/README convention) — export
  the new hook, key and types there with the paired `export {}` / `export type {}` blocks.

### Landmine 7 — You are building on Story 3.1's UNCOMMITTED working tree.

`git status` is dirty: 3.1 (status: review) shipped `MyLeaveHistoryPanel`, the
`LeaveRequestFilters` re-signature of `useLeaveRequests`, and the `MAX_PAGE` clamp — all
uncommitted atop `4fc1629`. Build on this state (the 2.11 precedent: it built on
uncommitted 2.9+2.10). Do not revert, do not commit 3.1's work as yours, and expect the
backend baseline to be **512 passing tests**, not 505. If you adopt Open Decision #2
(shared `Pager`), you will edit `MyLeaveHistoryPanel.tsx` — a file still under review;
keep that edit purely mechanical (lift JSX, change nothing observable).

## Tasks / Subtasks

### Task 1 — Repository: thread `scope` through the existing list read (AC1, AC3)

- [x] `backend/app/repositories/employee.py::list_employees` — add defaulted
      `scope: Scope = Scope.ALL` (the `get_employee` shape); use it in place of the
      hardcoded `Scope.ALL`; update the docstring (the "Story 1.7's Manager-scoped
      variant" sentence has finally come due — in Story 3.2). Everything else — ordering
      (`full_name, id`), `joinedload(department)`, `(rows, total)` — stays byte-identical
      (Landmine 3).

### Task 2 — Service: new read-only `services/team.py` (AC1, AC4)

- [x] New `backend/app/services/team.py` (the `services/balance_reads.py` /
      `services/audit.py` small-read-module precedent; Open Decision #3):
      `list_team(limit: int, offset: int, actor: Employee) -> tuple[list[Employee], int]`
      — opens `Session(get_engine(), expire_on_commit=False)`, delegates to
      `employee_repo.list_employees(session, actor, limit, offset, scope=Scope.REPORTS)`.
      Module docstring names FR-19, AD-10, G3 (SM-6 traceability). The `Scope.REPORTS`
      decision lives HERE, not in `api/` (Landmine 2).

### Task 3 — API: `app/api/v1/team.py` + registration (AC1, AC2, AC4)

- [x] New router file with ONE route:
      `@router.get("/team", tags=["team"])`, params
      `params: PageParams = Depends()` and
      `manager: Actor = Depends(require_role(authz.ROLE_MANAGER))` → 403s Employee AND
      Admin before the body runs (Landmine 5), returns `Page[TeamMemberResponse]`.
- [x] `TeamMemberResponse` — **minimal disclosure** (Open Decision #1):
      `id: uuid.UUID`, `full_name: str`, `department: DepartmentBrief` (import from
      `app.api.v1.employees` — same layer, single home), `is_active: bool`. NO email, NO
      role, NO joining_date, NO manager_id. Hand-project via a `_to_response(row: object)`
      (the Trap-5 `object`-typed projection every route uses).
- [x] Register in `app/api/v1/router.py`: import tuple + `include_router(team.router)`
      (Landmine 4).

### Task 4 — Backend tests: new `tests/integration/test_team.py` (AC1-AC4)

- [x] World fixture in the house style (no shared role fixtures exist — build the world
      per-file as `test_role_gate.py:79-129` / `test_manager_scope.py` do). Top-of-file
      `import app.main` + `TestClient(app.main.app)` exactly as both templates do — their
      own docstrings record that skipping the import leaves routes unregistered (a past
      false-green). World: one Admin, one
      Manager M, direct reports of M including **one deactivated** (`is_active=False`),
      one Employee reporting to a *different* manager (or none), and the second manager.
      Teardown nulls `manager_id` before deleting (self-FK is RESTRICT).
- [x] **AC1 exactness**: M's list contains exactly M's reports — the other manager's
      report absent, M's own row absent (M reports to no one / someone else — assert
      absence either way), no Admin row, and `total` equals the report count.
- [x] **AC2 shape**: each item carries exactly `{id, full_name, department, is_active}`
      with `department == {"id": …, "name": …}` — pin the key set so accidental
      email/role leakage fails the build (Open Decision #1's enforcement).
- [x] **AC3 presence**: the deactivated report IS in the list with `is_active is False`;
      the active one with `True` (Landmine 1).
- [x] **AC4 role gate**: parametrized Admin + Employee → 403, envelope
      `{code,message,details}`, `code == vocabulary.ACTION_NOT_PERMITTED`, `details == {}`
      (Landmine 5). No token → 401.
- [x] **Envelope + clamp**: response carries `items/page/page_size/total`;
      `page_size=200` → clamped to 100 (`MAX_PAGE_SIZE`) — one assertion, the machinery is
      already pinned globally in `test_pagination.py`.
- [x] **Empty team**: a MANAGER-role caller with zero reports → 200, `items == []`,
      `total == 0` (a real state: G8 blocks demotion only while reports exist; a manager
      may simply have none yet).

### Task 5 — Frontend API layer: `src/api/team.ts` (AC5)

- [x] `TEAM_QUERY_KEY = ['team'] as const`; type
      `TeamMember { id, full_name, department: { id, name }, is_active }`;
      `useTeam(params: { page?: number; pageSize?: number } = {}, options?: { enabled?: boolean })`
      → `apiFetch<Page<TeamMember>>('/team…')`, `Page<T>` imported from `./departments`
      (the single home), every param through `encodeURIComponent`, query key
      `[...TEAM_QUERY_KEY, params]` (structural hashing; prefix-invalidation ready — though
      nothing invalidates it yet, read-only surface).
- [x] Re-export hook/key/type through `src/api/index.ts` (paired blocks; Landmine 6).

### Task 6 — Frontend: `src/features/team/MyTeamPanel.tsx` + mount (AC5)

- [x] `<section className="panel">`, Manager-gated exactly as `ManagerQueuePanel.tsx:46-57`
      (`useMe()`, `role === 'MANAGER'`, `{ enabled: isManager }`, `return null`) —
      Landmine 6. New feature dir `features/team/` (one caller → NOT `components/`).
- [x] List rows: the loading/error/empty triad then `<ul className="emp-list">` /
      `<li className="emp-row">` (canonical: `ManagerQueuePanel.tsx:77-130`,
      `MyLeaveHistoryPanel.tsx:173-199`). Each row: `<span className="emp-name">` with
      `full_name` + `{!member.is_active && <span className="emp-inactive"> (deactivated)</span>}`
      (the `EmployeesPage.tsx:402-405` precedent — AC3/AC5), and `department.name` in a
      `.muted` span (AC2/AC5). Server values verbatim; no new CSS.
- [x] Pager: `TEAM_PAGE_SIZE = 10` (the 3.1 rationale — small enough to actually exercise),
      Prev/Next + `Page X of Y` from the server's `total`/`page_size`
      (`Math.max(1, Math.ceil(total / pageSize))`), buttons disabled at the rails and
      while loading — per Open Decision #2, via the shared `Pager` component if adopted,
      else the `MyLeaveHistoryPanel.tsx:203-222` JSX shape inline.
- [x] Mount `<MyTeamPanel />` in `App.tsx`'s `<main>` adjacent to `<ManagerQueuePanel />`
      (the Manager cluster), with the house comment block naming the role gate and the
      server guard.

### Task 7 — Guards and verification (all ACs)

- [x] Backend: full `pytest` — baseline is **512 passed** (3.1's uncommitted tree,
      Landmine 7); expect only additions. `lint-imports` — 7/7 contracts byte-identical.
      `test_scope_matrix.py`, `test_scoped_getters.py`, `test_vocabulary_literals.py`,
      `test_frontend_no_client_day_count.py` all green with **no diff to any guard file**
      (Landmine 4).
- [x] `alembic check` clean — this story ships no migration; drift means you touched a model.
- [x] Frontend: `npm run build` (tsc + vite) + `npm run lint` (oxlint) clean. State plainly
      in the Dev Agent Record that these plus code reading are the ONLY frontend
      verification — there is still no test runner (`package.json`: dev/build/lint/preview).

## Dev Notes

### The one-paragraph mental model

`GET /api/v1/team` is `GET /employees` with two words changed: the role gate says MANAGER
instead of ADMIN, and the scope predicate says REPORTS instead of ALL — plus a deliberately
smaller response. Everything else — the pagination envelope, the eager-loaded department,
the deterministic ordering, the `(rows, total)` single round-trip, the 403-before-the-body
dependency — is the machinery Epic 1 built, reused without modification. The Admin-gets-403
inversion is the only counter-intuitive fact, and it is contract, not accident: an Admin has
`GET /employees`; a team is a reporting edge, and only a Manager stands on one. The frontend
is the third verse of the same song 3.1 sang: Manager-gated panel, list rows, pager.

### What is already true, and must stay true

- REPORTS is evaluated live at request time from `actor.id` (AD-10/AD-14) — a reassignment
  takes effect on the next request; nothing is cached from the token beyond the subject.
- A Manager's own row is never in REPORTS (`manager_id == actor.id` can't match self —
  `CHECK (id <> manager_id)` + the G7 cycle guard), and `test_manager_scope.py` already
  pins reports-with-NULL-manager exclusion semantics for the general predicate.
- The Admin `GET /employees` list is byte-identical after Task 1 (`scope` defaults to
  `Scope.ALL`; the existing service call site passes nothing new).
- The `employee (manager_id)` index serves this exact read (erd.md §4.4; NFR-12 "manager").
- Envelope is exactly `items/page/page_size/total`; `MAX_PAGE_SIZE=100`, `DEFAULT=50`,
  `MAX_PAGE` clamp — all pinned by `test_pagination.py`; touch nothing there.
- `403` bodies carry the full envelope with `details == {}` (`authorization.py:68-81`).

### Reuse map — DO NOT reinvent these

| Need | Already exists at |
|---|---|
| Role gate dependency | `api/v1/dependencies.py:90::require_role` (chains auth first) |
| Roles without literals | `services/authorization.py:36` re-exports `authz.ROLE_*` |
| Scoped employee page read | `repositories/employee.py:94::list_employees` (Task 1 threads `scope`) |
| REPORTS predicate | `repositories/scoping.py:73::employee_scope_predicate` |
| Pagination params/envelope | `api/v1/pagination.py::PageParams` / `Page[T]` |
| `DepartmentBrief` | `api/v1/employees.py` — import, don't redeclare |
| Projection idiom | `api/v1/employees.py:101::_to_response` (object-typed, hand-projected) |
| Small read-only service shape | `services/balance_reads.py`, `services/audit.py` |
| 403 test template | `tests/integration/test_role_gate.py:149-169` |
| REPORTS-exactness test world | `tests/integration/test_manager_scope.py` |
| Frontend fetch + envelope | `api/client.ts::apiFetch`/`ApiError` — branch on `error.code` |
| `Page<T>` TS type | `api/departments.ts:26-31` |
| Manager panel gate | `features/leave/ManagerQueuePanel.tsx:46-57` |
| "(deactivated)" marker | `features/employees/EmployeesPage.tsx:402-405` + `.emp-inactive` |
| Pager (first caller) | `features/leave/MyLeaveHistoryPanel.tsx:203-222` (3.1, uncommitted) |
| List render triad | `MyLeaveHistoryPanel.tsx:173-199` / `ManagerQueuePanel.tsx:77-85` |

### Gotchas this codebase has actually produced (relevant subset)

- Unencoded query params (2.7 review patch — Landmine 6).
- `getDay` token in a comment tripping the day-count guard (2.5, 2.7 first drafts).
- Filter/select or list without loading/empty/error states (2.5 review patch).
- Guard files "routed around" instead of left untouched (2.9's settlement) — this story
  needs ZERO guard changes; treat any red guard as your bug.
- Missing `joinedload` → `DetachedInstanceError` on `department.name` after the session
  closes (documented in the repo's own docstrings) — Task 1 keeps the existing eager load.
- Role-gated panels without `enabled:` firing guaranteed-4xx requests for other roles
  (the reason `useEmployees`/`ManagerQueuePanel` gate their queries).

### Project Structure Notes

- Backend: TWO new files (`api/v1/team.py`, `services/team.py`), TWO edits
  (`repositories/employee.py` — one keyword-only param; `api/v1/router.py` — two lines),
  ONE new test file (`tests/integration/test_team.py`). Nothing else.
- Frontend: TWO new files (`api/team.ts`, `features/team/MyTeamPanel.tsx`), edits to
  `api/index.ts` and `App.tsx`; plus `components/Pager.tsx` + a mechanical
  `MyLeaveHistoryPanel.tsx` edit iff Open Decision #2 is adopted. No router exists (panels
  stack in `AppShell`); no new CSS (reuse `.panel`, `.emp-list`, `.emp-row`, `.emp-name`,
  `.emp-inactive`, `.emp-actions`, `.muted`, `.emp-error`).
- Stack pins frozen by the spine (FastAPI 0.139.0, SQLAlchemy 2.0.51, React 19.2.7,
  TanStack Query 5.101.2, TypeScript 6.0.3) — no upgrades, no new dependency, and no
  external research needed: every library this story touches is already in the tree.

### References

- epics.md:1450-1476 (Story 3.2 ACs); :463-476 (Epic 3 notes — AD-10 governs, AD-18 n/a
  here: no day counts on this surface)
- prd.md:386-396 (FR-19 + its testable consequences); :94 (Full Name glossary)
- api-contracts.md:225-237 (§4.9 — `/team` | Manager | reports), :37-44 (403-vs-404 G3
  ruling + every-403-carries-the-envelope), :50 (pagination convention), :102 (role vocab)
- ARCHITECTURE-SPINE.md:121-125 (AD-10), :402 (FR-19 → `api/v1/team`, governed by AD-10),
  :206 (uuidv7 ids), :213 (NFR-11)
- erd.md:173-186 (employee attributes — `full_name`, `is_active`, `manager_id` provenance),
  :370-382 (§4.4 indexes — `employee (manager_id)`), :424-428 (GAP-2: `full_name` IS what
  FR-19 displays, by decision)
- Story 3-1 file (baseline state, pager precedent, no-test-runner declaration, Landmine
  style); Story 2-8 file (role-gated panel precedent); Story 2-12 file (components/
  promotion rule — `RecalculationSummaryPanel` lift)
- deferred-work.md:62,70,76 (page-1-only app-wide — why the pager, not another page-1 list),
  :75 (AD-6 submit gap — Open Decision #4 below)

## Open Decisions

Four. #1 is the genuinely under-determined one — no artifact fixes the response shape, and
it is a disclosure decision, not a style one.

1. **Response shape — RECOMMENDED: minimal `{id, full_name, department{id,name}, is_active}`.**
   FR-19's consequences name exactly three facts: the Employee (Full Name — erd.md GAP-2
   settled that Full Name IS the identification), their Department, and the active state.
   `EmployeeResponse` is "an Employee as the **Admin** view sees it" (its own docstring) and
   additionally discloses `email`, `role`, `joining_date`, `manager_id` — none of which any
   requirement grants a Manager sight of. Reusing it would widen disclosure silently; AD-10's
   whole posture is that authority is granted per-surface, in the SQL/projection, never by
   convenience. `id` is included (uuidv7, non-enumerable, needed as a React key and for any
   later drill-down); `manager_id` is omitted as tautological (it is the caller). The AC2
   test pins the exact key set so the decision stays made.
2. **Shared `Pager` component — RECOMMENDED: extract to `src/components/Pager.tsx`.**
   This panel is the second caller of 3.1's Prev/Next pager; `components/README.md` states
   the rule ("lives with that feature **until a second caller appears**") and 2.12 executed
   exactly this lift (`RecalculationSummaryPanel` out of `HolidaysPage` when its second
   caller arrived). Props: `page`, `pageCount`, `total`, `noun` (singular label),
   `disabled`, `onPrev/onNext` (or `onPageChange`) — a mechanical lift of
   `MyLeaveHistoryPanel.tsx:203-222`, changing nothing observable. Cost: it edits a file
   Story 3.1 still has in review (Landmine 7). If the reviewer prefers zero contact with
   3.1's files, the sanctioned alternative is duplicating the small JSX block inline in
   `MyTeamPanel` and logging the promotion to deferred-work.md — but the recommendation is
   the lift; page-1-only (no pager) is NOT an option, it would recreate deferred-work's
   oldest open item on a brand-new surface.
3. **Service home — RECOMMENDED: new `services/team.py`, not a function in
   `services/employee.py`.** `services/employee.py`'s docstring scopes it to FR-04 command
   orchestration; a read-only FR-19 module mirrors the established small-read-service shape
   (`balance_reads.py`, `audit.py`) and keeps SM-6's one-docstring-one-FR traceability
   clean. If the dev judges a new module too heavy for one function, adding `list_team` to
   `services/employee.py` with FR-19 added to its docstring is acceptable — but the
   recommendation is the separate module.
4. **Carried forward, NOT this story's to fix: the AD-6 submit gap** (2.11 #8 → 2.12 #11 →
   3.1 #6; deferred-work.md:75 — "it now ships unless Epic 3 picks it up"). This story is
   read-only over `employee` and never touches `submit_leave_request`; adopting the fix
   here would be the silent scope-widening three stories have now declined. Restated so it
   does not lapse: an Epic 3 story that reaches the submit path (3.4's notification hook
   into `services/leave_request` transitions is the likely candidate) must make the call,
   or the epic ends with it shipped.

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) via Claude Code / bmad-dev-story workflow.

### Debug Log References

- Red-green cycle: `tests/integration/test_team.py` written FIRST against the not-yet-existing
  route — all 8 tests failed (404s against the real app; even the no-token case, since an
  unregistered path 404s before auth). Then Tasks 1-3 implemented; all 8 green with no test edit.
- Baseline discrepancy, benign: the story predicted **512** passing tests on 3.1's uncommitted
  tree; the actual pre-existing baseline measured **514** (`pytest --ignore=tests/integration/
  test_team.py`) — 3.1's post-story-creation state carries two more tests than the story file
  recorded. All 514 pass untouched; this story adds exactly 8 (7 functions, one parametrized ×2)
  for a final count of **522 passed, 0 failed, 0 skipped**.
- Guard sweep re-run after the frontend files landed (`test_frontend_no_client_day_count` scans
  `frontend/src`): 118 guard tests green; `git status` confirms ZERO guard files in the diff
  (no `main.py`, no `vocabulary.py`, no `test_scope_matrix.py`, no `test_scoped_getters.py`,
  no `alembic/`).

### Completion Notes List

- **All 5 ACs met, no deviations.** `GET /api/v1/team` returns exactly the caller's Direct
  Reports (AC1), each as the pinned minimal key set `{id, full_name, department{id,name},
  is_active}` (AC2), with a deactivated report PRESENT and carrying `is_active: false` on the
  wire (AC3 — Landmine 1: the REPORTS predicate has no `is_active` filter and grew none).
  Employee AND Admin both get the gate's `403 ACTION_NOT_PERMITTED` with the full envelope and
  empty details, decided before any row is read (AC4 — the §4.9 inversion, pinned by a
  parametrized test). The React `MyTeamPanel` renders name + "(deactivated)" marker +
  department for a Manager (AC5).
- **Task 1 landed as promised — a change of scope, not signature**: `list_employees` gained one
  defaulted `scope: Scope = Scope.ALL` param (the exact `get_employee` shape) replacing the
  hardcoded `Scope.ALL`; the Admin `GET /employees` call site is untouched and provably
  byte-identical (default applies). Zero `EXEMPT` changes, zero new repo getter.
- **Landmine 2 honored**: the `Scope.REPORTS` decision lives in new `services/team.py` —
  `api/v1/team.py` imports only `services/` + api-layer modules; import-linter contract 2
  (and all 7) kept.
- **Open Decisions #1, #2, #3 adopted as recommended; #4 restated, not adopted.**
  - #1 minimal response: `TeamMemberResponse` = `{id, full_name, department, is_active}`;
    NO email/role/joining_date/manager_id. The AC2 test pins the exact key set so accidental
    disclosure fails the build. `DepartmentBrief` imported from `api/v1/employees.py`
    (single home), not redeclared.
  - #2 shared `Pager`: lifted `MyLeaveHistoryPanel`'s pager JSX to `src/components/Pager.tsx`
    (the 2.12 `RecalculationSummaryPanel` precedent — second caller arrived). The
    `MyLeaveHistoryPanel.tsx` edit is purely mechanical (JSX lifted, props threaded, nothing
    observable changed: same rail-disabling, same "· N requests" line). NOTE for reviewer:
    this touches a file Story 3.1 still has in review, as the story authorized.
  - #3 separate `services/team.py` module (FR-19/AD-10/G3 named in its docstring; SM-6
    traceability), mirroring `balance_reads.py`/`audit.py`.
  - #4 AD-6 submit gap: NOT adopted — read-only story, never reaches `submit_leave_request`.
    Restated so it does not lapse: 3.4's transition hook is the likely forcing point, or the
    epic ends with it shipped.
- **Frontend verification stated plainly**: there is STILL no frontend test runner
  (`package.json`: dev/build/lint/preview only). AC5 is verified by `npm run build`
  (tsc + vite) + `npm run lint` (oxlint), the backend day-count guard scan, and code
  reading — and by nothing else.
- Backend: **522 passed** (from 514 measured baseline, 0 skipped); `lint-imports` 7/7 kept;
  `alembic check` clean (no migration, no model change). Frontend: build + lint clean.
- Built atop Story 3.1's UNCOMMITTED working tree (Landmine 7); nothing of 3.1's was
  reverted or committed.

### File List

New:
- backend/app/services/team.py
- backend/app/api/v1/team.py
- backend/tests/integration/test_team.py
- frontend/src/api/team.ts
- frontend/src/components/Pager.tsx
- frontend/src/features/team/MyTeamPanel.tsx

Modified:
- backend/app/repositories/employee.py (one defaulted `scope` param on `list_employees` + docstring)
- backend/app/api/v1/router.py (import tuple + `include_router(team.router)`)
- frontend/src/api/index.ts (barrel re-exports: `TEAM_QUERY_KEY`, `useTeam`, `TeamMember`)
- frontend/src/App.tsx (mount `<MyTeamPanel />` in the Manager cluster + house comment)
- frontend/src/features/leave/MyLeaveHistoryPanel.tsx (mechanical Pager lift only — Story 3.1
  file, edit authorized by Open Decision #2 / Landmine 7)

## Change Log

- 2026-07-14: Story created (create-story workflow). Epic 3 already in-progress; 3-2
  backlog → ready-for-dev.
- 2026-07-14: Story implemented (dev-story workflow). All 5 ACs met; Open Decisions #1-#3
  adopted as recommended, #4 restated without adoption. `GET /api/v1/team` (Manager-only,
  REPORTS scope, minimal disclosure) + `MyTeamPanel` with the shared `Pager` lifted to
  `components/`. Backend pytest 522 passed (514 baseline, 8 added); import-linter 7/7;
  alembic check clean; frontend build+lint clean; zero guard-file changes. Status → review.
