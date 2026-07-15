---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

<!--
  Story context created 2026-07-14 by create-story (ultimate context engine).
  Sources: epics.md §Epic 3 / Story 3.1; ARCHITECTURE-SPINE.md; api-contracts.md; erd.md;
  prd.md FR-12/FR-20/NFR-11; deferred-work.md; story files 2-7, 2-8, 2-12; live working tree
  at commit 4fc1629 (stories 2.9–2.12 committed).
  baseline_commit: 4fc1629
-->

# Story 3.1: My Leave History, Filtered and Bounded

Status: done

## Story

As an Employee,
I want to see every Leave Request I have ever made, filtered and paged,
So that I can answer what I took, when, and what it cost, without asking anyone.

## Orientation: what this story actually is

**This story extends; it does not introduce.** `GET /api/v1/leave-requests` and
`GET /api/v1/leave-requests/<id>` exist since Story 2.7, and they are further along than the
epic text assumes. Read this before planning, because roughly half of the epic's AC surface is
**already built, committed and pinned by tests**:

| Epic 3.1 clause | Current state at `4fc1629` |
|---|---|
| `items/page/page_size/total` envelope | ✅ Built (Story 1.5's `Page[T]` + `PageParams`, wired into `GET /leave-requests` by 2.7) |
| `page_size` above max → clamped to max | ✅ Built — `MAX_PAGE_SIZE = 100`, clamp pinned by `test_list_is_scoped_filtered_and_paged` |
| Cross-Leave-Year, every state incl. CANCELLED/REJECTED | ✅ Already true — the list has **no year filter to remove** (no `leave_year` column exists; scope predicate + optional `status` only). Your job is a **documenting test**, not code |
| Entry shows Leave Type, date range, day count, state | ✅ `LeaveRequestResponse` already carries `leave_type_code/name`, `start_date/end_date`, `leave_days`, `status` — **no shape change** |
| `status` filter | ✅ Built (2.7), invalid value → 422, pinned |
| Scope: self/reports/all, byte-identical 404 | ✅ Built (2.7), pinned incl. manager-own-request-absent |
| AD-18 stored `leave_days`, never recomputed | ✅ Built, pinned by `test_get_by_id_returns_stored_leave_days` |
| **`leave_type_id`, `date_from`, `date_to` filters** | ❌ **This story** — three predicates through repo → service → api |
| **React history page: filter by type/state/date range, page through results** | ❌ **This story** — and it is the **first pagination UI in the entire app** (grep confirms: no component reads `page`/`total` today; deferred-work.md has carried "page-1-only app-wide" since 1.5) |

So the backend work is deliberately small — three optional predicates and their tests — and the
frontend work is the real substance: a new history panel with a filter bar and the app's first
pager, plus a signature extension to `useLeaveRequests` that two existing panels consume.

**What this story must NOT contain:** no migration, no model change, no new index, no new
vocabulary entry, no new error code, no `main.py` change, no new route (so no scope-matrix
registration), no new repo getter (so no scoped-getter exemption), no CSS additions expected.
If you find yourself writing any of those, stop and re-read the Landmines.

## Acceptance Criteria

*(From epics.md:1409-1448. This story **extends** the `FR-03`-scoped endpoints Story 2.7
delivers; it adds `FR-12`'s composable filters and `FR-20`'s cross-Leave-Year history.)*

1. **Given** an authenticated Employee, **when** they call `GET /api/v1/leave-requests`,
   **then** the response contains every Leave Request they have submitted, **across every Leave
   Year**, in every state, including `CANCELLED` and `REJECTED`, **and** each entry shows the
   Leave Type, the date range, the Leave Day count and the current state (`FR-20`).
2. **Given** any list response, **when** it is inspected, **then** it carries `items`, `page`,
   `page_size` and `total`, and a client requesting a `page_size` above the server maximum
   receives the maximum (`NFR-11`, `FR-12`).
3. **Given** the filters `status`, `leave_type_id`, `date_from` and `date_to`, **when** they are
   applied together, **then** they compose and the result is the intersection. Story 2.7
   delivered `status` alone; `leave_type_id`, `date_from` and `date_to` are added here (`FR-12`).
4. **Given** a Manager filtering across every Department, **when** the results return, **then**
   they contain only that Manager's Direct Reports — filtering never widens authorization —
   **and** an Employee sees only their own, and an Admin sees anyone's (`FR-12`, `FR-03`, `AD-10`).
5. **Given** a Leave Request identifier outside the caller's scope, **when** they call
   `GET /api/v1/leave-requests/<id>`, **then** the response is `404`, byte-identical to a
   nonexistent identifier (`AD-10`, `SM-3`).
6. **Given** any history entry, **when** its Leave Day count is read, **then** it is the value
   stored on the request at admission, never recomputed against today's holiday calendar (`AD-18`).
7. **Given** the React application and an authenticated Employee, **when** they open their
   history, **then** they can filter by type, state and date range, and page through the results.

## 🚨 Landmines. Read all eight before writing a line.

### Landmine 1 — The pagination machinery already exists. Rebuilding any of it breaks pinned tests.

`backend/app/api/v1/pagination.py` is the single home: `MAX_PAGE_SIZE = 100`,
`DEFAULT_PAGE_SIZE = 50`, `PageParams` (clamps in code, **never** `Query(le=…)` — over-max
carries down to 100, never 422s), `Page[T]` (envelope of **exactly** `items`, `page`,
`page_size`, `total`). Two guard tests will fail if you deviate:

- `tests/test_pagination.py::test_page_envelope_carries_exactly_the_four_contract_fields` —
  adding a fifth envelope field (e.g. `total_pages`) fails the build. Compute page count on the
  client from `total` and `page_size`.
- `tests/integration/test_leave_request_decide.py::test_list_is_scoped_filtered_and_paged` —
  pins `items`, `total`, and `clamped["page_size"] == 100` for `page_size=200`.

AC2 is **already satisfied**; do not touch `pagination.py` except for the optional, explicitly
adopted Open Decision #5.

### Landmine 2 — Four existing integration assertions pin the endpoints you are extending.

In `tests/integration/test_leave_request_decide.py`:

- `test_list_status_filter_rejects_bad_value` (:566) — invalid `status` → **framework 422**
  (bare FastAPI `{"detail": …}`, NOT the domain envelope). Your new filters must follow the same
  path for malformed input: a non-UUID `leave_type_id` and an unparseable `date_from`/`date_to`
  already yield 422 **for free** once typed `uuid.UUID | None` / `datetime.date | None`. Do NOT
  invent a 400 code — there is no filter error code in `vocabulary.py`, none is wanted, and
  `main.py::CODE_TO_STATUS` must not change. (Note: `INVALID_DATE_RANGE` at vocabulary.py is a
  *submission* refusal — "end precedes start" on a request being created. Reusing it for a
  filter would be a category error; see Open Decision #2.)
- `test_manager_own_request_is_absent_from_reads` (:602) — REPORTS scope **excludes the
  Manager's own row** (2.7 Open Decision #4, RESOLVED keep-REPORTS 2026-07-13, locked by this
  test). Your filter predicates must be ANDed **inside** the existing
  `employee_scope_predicate(scope, actor)` conditions list, never restructure it.
- `test_get_by_id_returns_stored_leave_days` (:579) — detail body keys pinned; AC5/AC6 are
  already covered here — keep them green, don't duplicate.
- `test_list_is_scoped_filtered_and_paged` (:509) — the whole scoped/filtered/paged baseline.

### Landmine 3 — `total` must obey the same filters as `items`, and the count query has no LeaveType join.

`repositories/leave_request.py::list_leave_requests` (:165-215) builds one `conditions` list and
uses it in BOTH the page query (which joins `Employee` and `LeaveType` for display columns) and
the count query (which joins **only** `Employee`). This works today because the only predicates
are on `LeaveRequest` columns. Keep it that way: filter on `LeaveRequest.leave_type_id`,
`LeaveRequest.start_date`, `LeaveRequest.end_date` — all local columns, no new join needed in
either query. If you filter via `LeaveType.code` or any joined column, the count query silently
diverges from the page query and `total` lies. Filter by **id**, not code.

### Landmine 4 — `test_scoped_getters.py` and import-linter will fail on careless signatures.

- The repo getters MUST keep parameters literally named `session` and `actor`
  (`_ACTOR_PARAM_NAMES = frozenset({"actor"})` in `tests/test_scoped_getters.py:149`). Add the three
  filters as keyword-only params; rename or drop `actor` and the build fails.
- `pyproject.toml [tool.importlinter]` contract `"api/ talks only to services/ (AD-1)"` forbids
  `api/` importing `app.repositories` or `app.domain`. `uuid` and `datetime.date` are stdlib —
  fine. Do not import `Scope` or vocabulary into `api/`; the status filter enum stays
  runtime-built from `leave_requests_service.LEAVE_STATUS_VALUES` (the existing
  `LeaveStatusFilter` pattern at api/v1/leave_requests.py:62-65). All 7 contracts stay
  byte-identical.

### Landmine 5 — Cross-year is already true. Do not "implement" it — and above all do not break it.

There is no `leave_year` column on `leave_request` (the year of `start_date` IS the Leave Year,
erd.md:386) and the list applies no year predicate. The trap is the opposite direction: writes
use `_current_leave_year()` (services/leave_requests.py) and it sits in the same module —
**do not** let any default creep into the read path (e.g. defaulting `date_from` to Jan 1). All
three new filters default to `None` = absent = no predicate. AC1's test is a *documenting* test:
seed requests in two different leave years (submission requires future dates within one year, so
create rows for year Y and Y+1 via the API where possible, or repo-level inserts as the rollover
tests do) and assert both appear unfiltered.

### Landmine 6 — Frontend: the day-count guard scans your code, and every param must be URL-encoded.

- `backend/tests/test_frontend_no_client_day_count.py` line-scans `frontend/src` for
  `getDay`/`getUTCDay` tokens — **even in a comment** (2.5 and 2.7 first drafts both tripped
  this). The pager arithmetic you need (`Math.ceil(total / page_size)`) is fine; weekday/holiday
  math is not. Render `leave_days`, `start_date`, `end_date` exactly as the server sent them
  (AD-2, AD-18).
- Every query param interpolated into the URL goes through `encodeURIComponent` — the 2.7 review
  patched exactly this on `status` (leaveRequests.ts:143-153). Your `leave_type_id`, `date_from`,
  `date_to`, `page`, `page_size` all follow.
- The TanStack Query key must include **every** filter + page param so each combination caches
  distinctly, while keeping the `LEAVE_REQUESTS_QUERY_KEY` prefix so the existing
  `invalidateAfterDecision` fan-out (onSettled, leaveRequests.ts:166-199) still prefix-matches
  and refetches all variants. Pattern: `[...LEAVE_REQUESTS_QUERY_KEY, params]` (a single stable
  object in the key is fine in TanStack v5 — keys are hashed structurally).

### Landmine 7 — `useLeaveRequests` has two existing consumers. Changing its signature ripples.

`ManagerQueuePanel.tsx` (PENDING queue) and `RequestCancellationPanel.tsx` (own APPROVED
requests) both call `useLeaveRequests(status, { enabled })` today. Extend the hook to a params
object (`{ status?, leaveTypeId?, dateFrom?, dateTo?, page?, pageSize? }`) and **update both call
sites in the same change** — `tsc -b` (via `npm run build`) is the only net that catches this;
there is no frontend test runner. Features import hooks ONLY from the `api/index.ts` barrel
(features/README.md), so re-export any new types there with the paired
`export {}` / `export type {}` blocks.

### Landmine 8 — No new route means no guard registrations — verify, don't add.

Adding query params does not change a path template, so `tests/test_scope_matrix.py` needs **no
change** (`GET /leave-requests/{request_id}` is already registered at :99-101 with all three
scopes; the collection route is deliberately OUT, comment at :96-98). You are extending existing
scoped getters, so `test_scoped_getters.py::EXEMPT` needs **no change**. If either file appears
in your diff, you have taken a wrong turn. Run both to confirm green, and run
`tests/test_vocabulary_literals.py` — no status/enumerated literal anywhere under `app/`
(annotations included); the frontend is outside that guard's scan and may state
`'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'` (ManagerQueuePanel already does).

## Tasks / Subtasks

### Task 1 — Repository: three composable predicates (AC1, AC3, AC4)

- [x] `backend/app/repositories/leave_request.py::list_leave_requests` — add keyword-only
      params `leave_type_id: uuid.UUID | None = None`, `date_from: date | None = None`,
      `date_to: date | None = None` (keep `session`, `actor`, `scope`, `status`, `limit`,
      `offset` exactly as they are — Landmine 4).
- [x] Append to the existing `conditions` list, each only when not `None`:
      `LeaveRequest.leave_type_id == leave_type_id`;
      `LeaveRequest.end_date >= date_from`; `LeaveRequest.start_date <= date_to`
      (overlap semantics — Open Decision #1; all predicates on local columns — Landmine 3).
- [x] Ordering stays `LeaveRequest.id.desc()` (UUIDv7, newest-first). No new join in either the
      page or the count query.

### Task 2 — Service: pass-through (AC3)

- [x] `backend/app/services/leave_requests.py::list_leave_requests` — accept and forward the
      three params to the repo. `_scope_for_role` untouched (AC4 is satisfied BY not touching
      it). `LeaveRequestView` untouched — the response already carries every AC1 display field.

### Task 3 — API: three query params (AC3)

- [x] `backend/app/api/v1/leave_requests.py::list_leave_requests` — add
      `leave_type_id: uuid.UUID | None = Query(default=None)`,
      `date_from: datetime.date | None = Query(default=None)`,
      `date_to: datetime.date | None = Query(default=None)`; forward to the service. Malformed
      values 422 for free (Landmine 2). `status` filter, `PageParams`, `Page[LeaveRequestResponse]`,
      `_to_leave_request_response` all unchanged.

### Task 4 — Backend tests: new file `tests/integration/test_leave_request_history.py` (AC1, AC3, AC4)

- [x] **AC1 documenting test**: requests in two different Leave Years, plus one CANCELLED and
      one REJECTED row, all present in an unfiltered employee list; each item carries
      `leave_type_code`/`leave_type_name`, `start_date`, `end_date`, `leave_days`, `status`.
- [x] **AC3 intersection**: seed rows differing in status/type/dates; apply all four filters
      together; assert the result is exactly the intersection, and `total` equals `len` of the
      full intersection even when `page_size` truncates `items` (Landmine 3).
- [x] **Overlap semantics pinned** (Open Decision #1): a request straddling `date_from` is
      included; one ending the day before `date_from` is not; symmetric at `date_to`;
      one-sided filters work alone.
- [x] **AC4 scope-never-widened**: an Employee with filters naming another Employee's leave
      type/dates still sees only their own; a Manager filtering broadly still sees only Direct
      Reports (and still not their own row — keep :602's invariant); an Admin sees all. Reuse the
      three-role fixture pattern from `test_list_is_scoped_filtered_and_paged`.
- [x] **Documenting tests for Open Decisions #2/#3**: `date_from > date_to` → 200 with empty
      `items`, `total == 0`; nonexistent (valid-UUID) `leave_type_id` → 200 empty; malformed
      `leave_type_id`/`date_from` → 422.
- [x] AC2/AC5/AC6 are already pinned in `test_leave_request_decide.py` and `test_pagination.py`
      — run them, do not duplicate them.

### Task 5 — Frontend API layer: extend `useLeaveRequests` (AC7)

- [x] `frontend/src/api/leaveRequests.ts` — new
      `LeaveRequestFilters` params object (`status?`, `leaveTypeId?`, `dateFrom?`, `dateTo?`,
      `page?`, `pageSize?`); build the query string with `encodeURIComponent` on every value
      (Landmine 6); query key `[...LEAVE_REQUESTS_QUERY_KEY, params]` (prefix-invalidation
      preserved). Returns `Page<LeaveRequest>` — type already exists, `Page<T>` imported from
      `./departments` (the established single home).
- [x] Update both existing call sites — `ManagerQueuePanel.tsx`, `RequestCancellationPanel.tsx`
      (Landmine 7). `npm run build` proves it.
- [x] Re-export anything new through `api/index.ts` (paired `export` / `export type` blocks).

### Task 6 — Frontend: `MyLeaveHistoryPanel` (AC7)

- [x] New `frontend/src/features/leave/MyLeaveHistoryPanel.tsx` — a `<section className="panel">`
      like every other panel. Gate to the EMPLOYEE role via `useMe()` exactly as
      `RequestCancellationPanel.tsx:25` does (Open Decision #4 — a Manager/Admin's "history"
      through this endpoint would be reports'/everyone's data, not their own; the 2.7
      own-requests gap, RESOLVED keep-REPORTS).
- [x] Filter bar inside `.emp-fields`/`.emp-field`: leave-type `<select>` reusing the 2.5
      select-with-states pattern verbatim (`RequestPreviewPanel.tsx:113-153` —
      `useLeaveTypes()`, `unavailable = isLoading || isError || items.length === 0`, disabled
      select, `.muted` reason span, `<option value="">All types</option>` as the no-filter
      option); status `<select>` over the four wire strings + an "All" empty option; two
      `<input type="date">` for from/to. Changing any filter resets `page` to 1.
- [x] List rows: the uniform loading/error/empty/`.emp-list` block (canonical:
      `AuditLogPanel.tsx:75-100`), each `<li className="emp-row">` showing
      `leave_type_code · leave_type_name`, `start_date → end_date`, `leave_days` days, `status`
      — server values verbatim (Landmine 6).
- [x] Pager — the app's first: Prev/Next buttons + `Page X of Y` from
      `Math.max(1, Math.ceil(total / page_size))`; Prev disabled on page 1, Next disabled on the
      last page; `.muted` text, plain buttons, no new CSS expected. Keep it in the feature dir —
      promote to `src/components/` only when a second caller exists (the components/README
      convention 2.12 followed).
- [x] Mount in `App.tsx`'s `AppShell` stack, adjacent to `RequestPreviewPanel` (the employee's
      own cluster).

### Task 7 — Guards and verification (all ACs)

- [x] Backend: full `pytest` (505 passing at baseline — expect only additions), `lint-imports`
      (7/7, byte-identical contracts), `tests/test_pagination.py`, `test_scope_matrix.py`,
      `test_scoped_getters.py`, `test_vocabulary_literals.py`, `test_frontend_no_client_day_count.py`
      all green with **no diff** to any guard file (Landmine 8).
- [x] `alembic check` clean — this story ships **no migration**; if it reports drift you have
      touched a model.
- [x] Frontend: `npm run build` (tsc + vite) and `npm run lint` (oxlint) clean. State plainly in
      the Dev Agent Record that these plus code reading are the ONLY frontend verification —
      there is no test runner (`package.json`: dev/build/lint/preview only). Do not imply
      coverage that does not exist.

### Review Findings (code review 2026-07-15)

- [x] [Review][Patch] `useLeaveTypes()` is not role-gated although the adjacent comment claims both fetches are — every Manager/Admin session issues a `GET /leave-types` for a panel that renders `null` [frontend/src/features/leave/MyLeaveHistoryPanel.tsx:81] — FIXED 2026-07-15: `useLeaveTypes` accepts `{enabled}` and the panel passes `isEmployee`
- [x] [Review][Patch] Pager `page` state is never clamped when the result set shrinks — a refetch that drops `total` leaves the panel on "Page 3 of 1" with a misleading "No requests match" empty state [frontend/src/features/leave/MyLeaveHistoryPanel.tsx:211] (same pattern in MyTeamPanel.tsx:102 and NotificationsPanel.tsx:130) — FIXED 2026-07-15: all three panels clamp `page` to the last real page whenever fresh data arrives
- [x] [Review][Defer] The four status literals are re-hardcoded in the frontend filter off any vocabulary guard — a status added server-side is silently absent from the filter [frontend/src/features/leave/MyLeaveHistoryPanel.tsx:36] — deferred, pre-existing acknowledged precedent (frontend literal copies are unguarded across the codebase; extending the guard scan is its own task)

## Dev Notes

### The one-paragraph mental model

The list endpoint is a scope predicate plus a bag of optional ANDed filters over local
`leave_request` columns, paged by machinery that has existed since 1.5 and clamped at 100.
Story 3.1 drops three more optional predicates into that bag — nothing else on the backend moves
— and then builds the screen the envelope has been waiting for since 1.5: the first component in
the app that actually reads `page` and `total`. Everything hard about this story is discipline,
not invention: filters must never widen the scope predicate they sit beside (AC4), malformed
input stays framework-422 (the pinned 2.7 precedent), and the frontend must render server values
verbatim under a guard that greps its source for weekday math.

### Reuse map — DO NOT reinvent these

| Need | Already exists at |
|---|---|
| Pagination params + clamp | `api/v1/pagination.py::PageParams` (MAX 100 / DEFAULT 50) |
| Envelope | `api/v1/pagination.py::Page[T]` — exactly 4 fields, pinned |
| Scope resolution | `services/leave_requests.py::_scope_for_role` (:192-205) |
| Scope predicate | `repositories/scoping.py::employee_scope_predicate` (via existing conditions list) |
| Status filter enum, literal-free | `api/v1/leave_requests.py::LeaveStatusFilter` (:62-65) from `LEAVE_STATUS_VALUES` |
| Row → wire projection | `api/v1/leave_requests.py::_to_leave_request_response` (:298-316) |
| Read columns incl. joined type code/name | `repositories/leave_request.py::_READ_COLUMNS` (:117-128) |
| Frontend fetch + error envelope | `api/client.ts::apiFetch`/`ApiError` — branch on `error.code`, never `message` |
| `Page<T>` TS type | `api/departments.ts:26-31` — import, don't redeclare |
| `LeaveRequest` TS type | `api/leaveRequests.ts:114-125` — already mirrors the response |
| Leave-type dropdown w/ states | `RequestPreviewPanel.tsx:113-153` + `useLeaveTypes()` (`leaveTypes.ts:60-65`) |
| List render block | `AuditLogPanel.tsx:75-100` (loading/error/empty/`.emp-list`) |
| Role gate | `RequestCancellationPanel.tsx:25` (`EMPLOYEE_ROLE` + `enabled` + `return null`) |
| Query invalidation fan-out | `leaveRequests.ts::invalidateAfterDecision` (onSettled) — must keep prefix-matching |

### What is already true, and must stay true

- REPORTS excludes the Manager's own row (2.7 Open Decision #4, resolved keep-REPORTS; pinned).
- Invalid filter input → framework 422, never a domain envelope (pinned).
- The envelope is exactly `items/page/page_size/total` (pinned).
- The read path never touches `_current_leave_year()`; reads are cross-year by construction.
- `GET /leave-types` is role-`any` — the dropdown works for every authenticated user.
- Indexes: `ix_leave_request_employee_status` and `ix_leave_request_start_end` exist;
  `leave_type_id` filtering is unindexed and **stays that way** — the house stance
  (deferred-work.md:45,69,77) is that at NFR-10 scale missing secondary indexes are consciously
  deferred, not blockers. No migration.

### Gotchas this codebase has actually produced (2.5 → 2.12 reviews)

- Unencoded query params (2.7 review patch — the reason Landmine 6 exists).
- `getDay` token in a *comment* tripping the day-count guard (2.5, 2.7 first drafts).
- Invalidating on `onSuccess` instead of `onSettled`, leaving stale rows after a 409 (2.7).
- Stale error state on a shared mutation object shown against the wrong row (2.7) — not directly
  applicable here (read-only panel), but reset patterns matter if you add any mutation.
- Filter select without loading/empty/error states (2.5 review patch — reuse the fixed pattern).
- Guard files "routed around" instead of revised with rationale (2.9's settlement: a surface
  test gets revised with a rationale, never renamed around). This story should need NO guard
  revision at all — treat any red guard as your bug.

### Project Structure Notes

- Backend touches exactly three files: `repositories/leave_request.py`,
  `services/leave_requests.py`, `api/v1/leave_requests.py` — plus one new test file.
- Frontend: one new panel in `features/leave/`, edits to `api/leaveRequests.ts`,
  `api/index.ts`, `App.tsx`, and the two consumer panels. No router exists (panels stack in
  `AppShell`); no CSS file changes expected (reuse `.panel`, `.emp-fields`, `.emp-field`,
  `.emp-list`, `.emp-row`, `.emp-summary`, `.emp-name`, `.muted`, `.emp-error`).
- No new dependency. Stack pins are frozen by the spine (React 19.2.7, TanStack Query 5.101.2,
  TypeScript 6.0.3, FastAPI 0.139.0, SQLAlchemy 2.0.51 — the deliberately-behind pins must not
  be upgraded).

### References

- epics.md:1409-1448 (Story 3.1 ACs); :246, :1124, :1417 (extends-2.7 seam, assigned by name)
- api-contracts.md:50-52 (pagination + filters-compose conventions), :106 (scope notation),
  :164-174 (§4.5 endpoint table), :37-42 (403-vs-404 rule)
- ARCHITECTURE-SPINE.md:121-125 (AD-10), :169-173 (AD-18), :187-191 (AD-21), :213 (NFR-11
  convention), :225-243 (stack pins), :396,403 (FR-12 "lives in repositories/", FR-20 map)
- erd.md:379-386 (indexes; no `leave_year` column — year of `start_date` IS the Leave Year)
- prd.md FR-12, FR-20, NFR-11 (:585)
- Story 2-7 file (endpoints' birth, Open Decision #4 keep-REPORTS, review patches)
- Story 2-8 file :202,:437 (EMPLOYEE-gate precedent, "the 2.7 own-requests gap")
- Story 2-12 file (house conventions: barrel exports, components/ promotion rule, honest
  no-test-runner declaration)
- deferred-work.md:11,15,29,34,58,62 (page-1-only history; unbounded-`page` overflow), :67,:75
  (AD-6 / Open Decision #11 — see Open Decision #6 below)

## Open Decisions

Six. #1 is the genuinely under-determined one — no planning artifact fixes it, and Story 4.2's
CSV export will inherit whatever this story decides.

1. **Date-range filter semantics — RECOMMENDED: overlap (intersection non-empty).** No artifact
   defines whether `date_from`/`date_to` selects requests *contained in* the window or
   *overlapping* it (exhaustive search confirmed; prd.md:366's "falling inside the range" governs
   dashboards, not this list). Recommendation: include a request iff
   `end_date >= date_from AND start_date <= date_to`, each side optional. Rationale: the natural
   question is "which leave touches this window"; a request straddling a boundary IS leave taken
   in that window; containment silently drops straddlers at every year edge, which is exactly
   what a *cross-year history* must not do; and `ix_leave_request_start_end` serves it. Story 4.2
   ("the exported rows are exactly the rows matching those filters", epics.md:1644) inherits this
   — pin it with tests so the export story receives settled semantics.
2. **`date_from > date_to` — RECOMMENDED: 200 with an empty page, pinned by a documenting test.**
   Under overlap semantics an inverted window is a well-formed predicate whose intersection is
   empty — it falls out of the SQL with zero code, zero new vocabulary, zero `CODE_TO_STATUS`
   change, and matches "the result is the intersection" literally. The alternative (422 via the
   2.5 resource-guard `model_validator` precedent) is defensible but adds machinery for no
   protective value on a read. If the reviewer prefers 422, the change is confined to a
   `PageParams`-style dependency — but the recommendation is the empty page.
3. **Nonexistent (valid-UUID) `leave_type_id` — RECOMMENDED: 200 empty, not 404.** It is a
   predicate that matches nothing, exactly like a `status` no request has. A 404 here would also
   sit oddly beside AD-10, which reserves 404 for scope misses on identified resources.
4. **Frontend gate — RECOMMENDED: EMPLOYEE-only panel, per the 2.8 precedent.** AC7 names "an
   authenticated Employee". For a Manager this endpoint returns their *reports'* requests (never
   their own — keep-REPORTS is pinned), and for an Admin everyone's; labeling either "My leave
   history" would be false. Gate exactly as `RequestCancellationPanel` does and note that
   Manager/Admin own-history remains API-absent by the standing 2.7 ruling — a later story's
   filter change if ever wanted, not this one's.
5. **Adopt deferred-work.md:58 (unbounded `page` → bigint `OFFSET` → raw 500) — RECOMMENDED:
   yes, by name.** This story ships the first live pager, NFR-11 is in its ACs, and the fix is a
   one-line downward clamp of `page` in `PageParams` (e.g. cap at 1,000,000) plus a DB-free case
   in `tests/test_pagination.py`. It touches the shared file Landmine 1 protects — that is why it
   is an Open Decision and not a silent task. If declined, the deferred-work entry stands.
6. **Carried forward, NOT this story's to fix: the AD-6 submit gap (2.11 Open Decision #8 /
   2.12 Open Decision #11).** `reserve`/`consume_direct` never re-derive `carried_forward`;
   deferred-work.md:75 closes with "**it now ships unless Epic 3 picks it up**." This story is
   read-only and its ACs do not reach `submit_leave_request`; adopting a balance-mutation fix
   here would be exactly the silent scope-widening 2.11 and 2.12 both declined. Restated here so
   it does not lapse by omission: an Epic 3 story that touches the submit path (or a dedicated
   fix) must make the call, or the epic ends with it shipped. The fix remains one
   `recompute_carry_forward` call in `submit_leave_request`.

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5), 2026-07-14.

### Debug Log References

None — no HALT conditions, no failed iterations. All new tests passed on the first full run
(14/14 in the targeted run, 512/512 in the full suite).

### Implementation Plan

Backend exactly as the story tasks specify: three keyword-only optional params
(`leave_type_id: uuid.UUID | None`, `date_from/date_to: datetime.date | None`) added to
`repositories/leave_request.py::list_leave_requests` and appended to the EXISTING `conditions`
list only when not `None` — all three predicates on local `LeaveRequest` columns
(`leave_type_id ==`, `end_date >= date_from`, `start_date <= date_to` — overlap semantics,
Open Decision #1), so the count query (Employee join only) and the page query stay in agreement
(Landmine 3). `session`/`actor`/`scope`/`status`/`limit`/`offset` untouched (Landmine 4).
Service is a pure pass-through; `_scope_for_role`, `LeaveRequestView`, `_row_to_view` untouched.
API adds three typed `Query(default=None)` params — malformed values 422 for free via typing
(Landmine 2); no vocabulary/`CODE_TO_STATUS`/route change. Frontend: `useLeaveRequests`
re-signatured to a `LeaveRequestFilters` params object with every value through
`encodeURIComponent` and the whole object in the query key (prefix invalidation preserved);
both existing consumers updated in the same change; new EMPLOYEE-gated `MyLeaveHistoryPanel`
with the 2.5 select-with-states pattern, the AuditLogPanel list block, and the app's first
Prev/Next pager computed from the server's `total`/`page_size`.

### Completion Notes List

- **All 7 ACs satisfied, no deviations.** AC2/AC5/AC6 were already pinned at baseline
  (`test_pagination.py`, `test_leave_request_decide.py`) and stay green untouched; AC1/AC3/AC4
  and the Open Decision documenting tests are the new
  `tests/integration/test_leave_request_history.py` (6 tests); AC7 is the new panel.
- **Open Decisions #1–#4 adopted as recommended and PINNED by tests**: #1 overlap semantics
  (`end_date >= date_from AND start_date <= date_to`, each side optional — straddlers included,
  asserted at both boundaries and one-sided; Story 4.2's CSV export inherits settled semantics);
  #2 inverted range → 200 empty page, `total == 0`, zero code; #3 nonexistent valid-UUID
  `leave_type_id` → 200 empty, not 404; #4 EMPLOYEE-only panel gate (the 2.8
  `RequestCancellationPanel` precedent — a Manager/Admin "My history" would be a false label
  under keep-REPORTS).
- **Open Decision #5 ADOPTED by name** (deferred-work.md:58): `MAX_PAGE = 1_000_000` downward
  clamp in `PageParams` (never a 422, matching the house clamp posture) + a DB-free test proving
  `page=10**18` stays inside bigint OFFSET. This is the story's one sanctioned touch to the
  Landmine-1-protected files; the envelope and `MAX_PAGE_SIZE` clamp are byte-identical in
  behavior and all pre-existing pagination assertions pass unchanged.
- **Open Decision #6 (the AD-6 submit gap) NOT adopted, carried forward explicitly**: this story
  is read-only and never reaches `submit_leave_request`; the deferred-work.md:75 entry stands.
  An Epic 3 story that touches the submit path must make the call, or the epic ends with it
  shipped (restated so it does not lapse by omission).
- **History rows are seeded by repo-level inserts** (the rollover tests' precedent), because
  submission refuses past dates (`PAST_DATE_RANGE`) and a cross-year HISTORY is precisely rows
  whose dates have passed — the API cannot seed its own test data here. Direct inserts write no
  audit rows and touch no balance, so SM-4's ledger is undisturbed and fixture cleanup is
  minimal.
- **AC4's keep-REPORTS invariant held under the new filters**: the scope test asserts a Manager
  filtering broadly still gets Direct Reports only, never their own row (:602's invariant) and
  never another team's; an Employee naming a coworker's exact type/dates still sees only their
  own. Filters are ANDed INSIDE the existing conditions list beside `employee_scope_predicate` —
  the predicate structure is untouched.
- **Landmine 8 verified**: no diff to `test_scope_matrix.py`, `test_scoped_getters.py`,
  `test_vocabulary_literals.py`, `test_frontend_no_client_day_count.py`, or any guard file; no
  migration, no model change, no new vocabulary/error code, no `main.py` change, no new route,
  no new repo getter, no CSS additions, no new dependency.
- ⚠️ **Frontend verification is `npm run build` (tsc + vite) + `npm run lint` (oxlint) + code
  reading, and NOTHING ELSE** — there is still no frontend test runner (`package.json`:
  dev/build/lint/preview only). AC7 is verified by types, lint and reading; stated plainly
  rather than implying coverage that does not exist. The `useLeaveRequests` re-signature ripple
  to `ManagerQueuePanel`/`RequestCancellationPanel` is proven by `tsc -b` (the only net).
- **Verification**: backend pytest **512 passed** (baseline 505 + 6 history + 1 pagination,
  0 skipped); `lint-imports` **7/7 contracts kept** byte-identical; `alembic check` clean ("No
  new upgrade operations detected" — no model touched); frontend build + lint clean.
- `HISTORY_PAGE_SIZE = 10` (not the server default 50) so the pager — the reason the panel
  exists — is exercised at realistic data volumes; the page count derives from the server's
  echoed `total`/`page_size`, and changing any filter resets to page 1.

### File List

- `backend/app/repositories/leave_request.py` — modified (three keyword-only filter params,
  local-column predicates appended to the existing conditions list)
- `backend/app/services/leave_requests.py` — modified (pass-through of the three params)
- `backend/app/api/v1/leave_requests.py` — modified (three typed optional query params on
  `GET /leave-requests`)
- `backend/app/api/v1/pagination.py` — modified (Open Decision #5: `MAX_PAGE` downward clamp)
- `backend/tests/test_pagination.py` — modified (Open Decision #5: DB-free unbounded-page test)
- `backend/tests/integration/test_leave_request_history.py` — new (6 tests: AC1 cross-year/
  every-state documenting test, AC3 intersection + truncated-total, Open Decision #1 overlap
  pinning, AC4 scope-never-widened, Open Decisions #2/#3 empty pages, 422 malformed filters)
- `frontend/src/api/leaveRequests.ts` — modified (`LeaveRequestFilters` params object,
  encodeURIComponent on every value, structural query key)
- `frontend/src/api/index.ts` — modified (re-export `LeaveRequestFilters` type)
- `frontend/src/features/leave/MyLeaveHistoryPanel.tsx` — new (EMPLOYEE-gated filter bar +
  the app's first pager)
- `frontend/src/features/leave/ManagerQueuePanel.tsx` — modified (call-site signature update)
- `frontend/src/features/leave/RequestCancellationPanel.tsx` — modified (call-site signature
  update)
- `frontend/src/App.tsx` — modified (mount `MyLeaveHistoryPanel` in the employee cluster)
- `_bmad-output/implementation-artifacts/3-1-my-leave-history-filtered-and-bounded.md` —
  modified (this story file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — modified (status transitions)

## Change Log

- 2026-07-14: Story created (create-story workflow). Epic 3 opened: epic-3 → in-progress.
- 2026-07-14: Implemented (dev-story workflow). Backend: three composable filter predicates
  (repo → service → api), overlap date semantics pinned; Open Decision #5 adopted (`MAX_PAGE`
  clamp). Frontend: `useLeaveRequests` → params object (both consumers updated), new
  `MyLeaveHistoryPanel` with the app's first pagination UI. Open Decisions #1–#5 adopted as
  recommended; #6 carried forward unadopted. Backend pytest 512 passed; lint-imports 7/7;
  alembic check clean; frontend build + lint clean. Status → review.
