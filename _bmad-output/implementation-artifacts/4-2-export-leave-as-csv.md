---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

<!--
  Story context created 2026-07-15 by create-story (ultimate context engine).
  Sources: epics.md §Epic 4 / Story 4.2 (:1629-1657), Story 3.1 (:1409-1448), FR-15 (:64),
  Epic 4 notes (:478-489); prd.md §4.8 FR-15 (:439-455), FR-12 (:410-417), FR-03 (:148-159),
  §7.4 (:557), SM-C2 (:644), SM-8 (:638), NFR-04/-10/-11/-16/-17/-18 (:572-596);
  ARCHITECTURE-SPINE.md AD-10 (:121-125), AD-18 (:169-173), AD-21 (:187-191), AD-1 (:67-71),
  capability map FR-15 → api/v1/reports (:398), conventions (:207-219); api-contracts.md §4.9
  (:225-237, endpoint row :235), §5 (:249-251), §1 (:19-56), §2 (:69-89); erd.md leave_request
  (:95-103, :219-227); story files 3-1, 4-1; deferred-work.md; live working tree.
  ⚠️ The working tree is DIRTY with ALL of Epic 3, the 2026-07-15 review fixes AND Story 4.1,
  UNCOMMITTED, atop 4fc1629. Build on top of it. Do not revert or commit any of it.
-->

# Story 4.2: Export Leave as CSV

Status: done

## Story

As a Manager,
I want to export my team's leave, and as an Admin the organization's,
So that I can answer a question the dashboard does not.

## Orientation: what this story actually is

**The last story in the plan.** If this lands, SM-8 (full FR coverage) is met; Epic 4 was the
declared budget casualty and 4.1 already landed, so this is the closing move. It is also the
*smallest* backend story in Phase 3: no migration, no new vocabulary, no audit row, no
notification, no new dependency. Every hard part already exists — this story is one new
read-only route, one CSV serializer, and one frontend panel, wired to machinery other stories
built and pinned:

| Need | Current state |
|---|---|
| The filters | ✅ Story 3.1 shipped `status`, `leave_type_id`, `date_from`, `date_to` end-to-end with OVERLAP date semantics, and the repo docstring pre-commits this story to them verbatim: *"Story 4.2's CSV export inherits this"* (`repositories/leave_request.py:189-192`). |
| The scoped query | ✅ `repositories/leave_request.list_leave_requests` (:165-242) applies `employee_scope_predicate(scope, actor)` in SQL, joins Employee + LeaveType, and projects `_READ_COLUMNS` (:117-128) — **every field a CSV row needs, in one round-trip**. |
| Role → scope mapping | ✅ `services/leave_requests._scope_for_role` (:214-227): ADMIN→ALL, MANAGER→REPORTS. Pure, DB-free. |
| The role gate | ✅ `require_role(authz.ROLE_MANAGER, authz.ROLE_ADMIN)` — exact precedent at `api/v1/balances.py:91`. 403 `ACTION_NOT_PERMITTED` before the body runs. |
| The stored day count | ✅ `LeaveRequest.leave_days` (`models.py:310`), frozen at admission per AD-18; already in `_READ_COLUMNS` and `row_to_view`. |
| Non-JSON 200 precedent | ✅ 4.1's document GET: pin `Content-Type` + `Content-Disposition` headers by test instead of a response envelope (4-1 story :356-359, `api/v1/documents.py`). |
| Frontend raw-bytes fetch | ✅ `apiFetchBlob` (`api/client.ts:192-207`), added by 4.1. Error path still decodes the JSON envelope; success returns a `Blob`. Works for CSV unchanged. |
| Frontend download pattern | ✅ `ViewDocumentButton` (`ManagerQueuePanel.tsx:64-77`): blob → `URL.createObjectURL` → open/click → delayed `revokeObjectURL`. |
| Frontend filter UI + wire names | ✅ `MyLeaveHistoryPanel.tsx` filter form; `FILTER_PARAM_NAMES` (`api/leaveRequests.ts:182-224`) maps camelCase → wire names with `encodeURIComponent`. |
| The reports module | ❌ Does not exist. No CSV implementation exists anywhere under `backend/app` or `frontend/src` (the only "CSV" mention is `leave_request.py:192`'s docstring promising this story the filter semantics). Spine capability map fixes the home: `FR-15 → api/v1/reports` (SPINE:398). |

**What this story must NOT contain:** PDF export (declared non-goal, PRD §7.4, pinned by AC4),
charts/aggregates/analytics on the report screen (SM-C2, prd.md:644 — "Charts are the cheapest
way to look finished and the least defensible under questioning"; "They are exports, not
analytics", prd.md:441), emailed or scheduled reports (PRD §6/§7.4; only the rollover is
scheduled and it has no endpoint), any audit row (an export is a read, not a transition — AD-8,
SM-4 stays exactly 14), any notification (three kinds, settled twice over), any migration, any
new error code, any new dependency, any new frontend CSS.

## Acceptance Criteria

1. **Given** an authenticated Manager
   **When** they call `GET /api/v1/reports/leave.csv`
   **Then** the export contains only their Direct Reports
   **And** an Admin's export contains every Employee (`FR-15`, `FR-03`, `AD-10`)

2. **Given** a filter set applied to the view
   **When** the export runs
   **Then** the exported rows are exactly the rows matching those filters — the same filters
   Story 3.1 established (`FR-15`, `FR-12`)

3. **Given** any exported row
   **When** its Leave Day count is read
   **Then** it is the value stored on the request at admission, never recomputed against
   today's holiday calendar (`AD-18`)

4. **Given** the export format
   **When** it is produced
   **Then** it is CSV
   **And** no PDF export exists, which is a declared non-goal (PRD §7.4)

5. **Given** the React application and an authenticated Manager or Admin
   **When** they open the report screen
   **Then** they can apply filters and export exactly what they see

[Source: epics.md:1629-1657]

## 🚨 Landmines. Read all nine before writing a line.

### Landmine 1 — The pagination trap. A naive reuse of 3.1's list silently exports at most 100 rows.

`repositories/leave_request.list_leave_requests` takes **required** `limit`/`offset`
(:165-242); `MAX_PAGE_SIZE = 100` clamps in `api/v1/pagination.py:36` via `PageParams` — an
API-layer clamp, not a repo one. Route the CSV through `PageParams` (or copy the list route's
plumbing) and the export truncates at 100 rows **with every test green**, violating AC2's
"exactly the rows matching those filters". The pagination convention binds *list endpoints* —
the ones returning `items/page/page_size/total` (api-contracts.md:50, SPINE:213). The export
returns CSV, not the envelope; FR-15's own governance row (SPINE:398) names AD-10 and AD-18,
**not** the pagination convention, and every FR-15 statement says the applied entity is the
*filter set*, never `page`/`page_size`. The export carries **all** matching rows. This must be
pinned by a test that seeds **more than 100 matching rows** and counts them all in the body
(see Testing requirements). Resolve the mechanism via Open Decision #1.

### Landmine 2 — CSV text is built in `services/`; the `Response` is built in `api/`. The import-linter draws this line for you.

Contract 4 (`pyproject.toml:129-133`) forbids `app.services` from importing
fastapi/starlette; contract 2 (:100-105) forbids `app.api` from importing `repositories/` or
`domain/`. So: the service composes the CSV **string** (stdlib `csv` + `io.StringIO` — both
uncontracted), the route wraps it in a `Response(content=..., media_type=...,
headers={"Content-Disposition": ...})`. Put the CSV building in the route and you'll be
tempted to reach past the service; put the `Response` in the service and import-linter fails
the build. 7/7 contracts kept, as every story before this one.

### Landmine 3 — `GET /reports/leave.csv` takes NO scope-matrix entry. Adding one FAILS the guard.

`test_scope_matrix.py`'s `_SCOPE_REGISTRY` keys on `(METHOD, path-with-{param})` and covers
path-parameter endpoints only. This endpoint has no path parameter, so it is out of the
matrix **by construction** — and `test_no_registered_entry_names_a_route_the_app_does_not_expose`
(:233-245) fails on any entry naming a route shape the matrix can't exercise. Exactly the
`audit_entries.py:21-27` precedent, which states this in prose. Scope coverage for this
endpoint comes from its own integration tests instead. **Expected scope-matrix delta: 0.**

### Landmine 4 — A Manager's export EXCLUDES the Manager's own requests. Pin it.

The endpoint's scope column is `reports, all` (api-contracts.md:235) — no `self` for the
Manager, unlike 3.1's `GET /leave-requests` (`self, reports, all`). FR-15 says "for their
Direct Reports" (prd.md:452); AD-10's Manager predicate is `employee.manager_id = :actor_id`
(SPINE:125), which excludes the actor's own row; and 3.1's Manager *list* scope is already
REPORTS-only-excluding-self, pinned by test. `_scope_for_role(MANAGER) → Scope.REPORTS` gives
this for free — but a test must seed the Manager's own leave request and assert its absence
from the Manager's export (and its presence in the Admin's), or the invariant is unpinned here.

### Landmine 5 — Filter semantics are inherited, not designed. 3.1 already settled every edge.

The repo docstring at `leave_request.py:189-192` pre-commits this story: date window is
**OVERLAP** (`end_date >= date_from AND start_date <= date_to`), both boundaries and one-sided
forms pinned — containment would drop year-edge straddlers. Inverted range
(`date_from > date_to`) → `200` with **zero rows** (never 422). Nonexistent-but-valid-UUID
`leave_type_id` → `200` with zero rows, never 404 (AD-10 reserves 404 for scope misses). Bad
`status` value → framework `422`. Single-valued `status` only — nothing anywhere permits
multi-status. Do not re-decide any of this; reuse the same repo predicates so screen and
export **cannot** disagree (Open Decision #1), and a zero-row CSV is `200` with the header row
only, not an error.

### Landmine 6 — No status literal in the new files. The vocabulary guard scans every new `.py` under `app/`.

`test_vocabulary_literals.py` adds one parametrized case per new file under `app/` (:108) and
fails on any status/code literal outside `domain/`. The route reuses the `LeaveStatusFilter`
runtime-enum idiom (`api/v1/leave_requests.py:66-69`, built from
`leave_requests_service.LEAVE_STATUS_VALUES`) — copy that import path, don't restate
`'APPROVED'`. The CSV cells transport the constants verbatim uppercase (AD-21; the adversarial
review's Finding 5 names report filtering as the canonical vocabulary-drift victim). Frontend:
a status `<select>` will restate the literals like `MyLeaveHistoryPanel.tsx:36` does — a known,
accepted deferral (deferred-work.md:83), not yours to fix.

### Landmine 7 — AD-18: `leave_days` is read, never recomputed — and the test must prove it non-vacuously.

AD-18 enumerates "export" by name in its read paths (SPINE:173). `_READ_COLUMNS` already
carries the stored value; there is nothing to compute. The trap is a *vacuous* test: assert on
a row whose stored count happens to equal today's recomputation and you've pinned nothing. Use
the house canary (3.1 precedent, AD-18 test): direct-insert a request whose stored
`leave_days` is deliberately absurd against its date range (e.g. 99 over 3 days) and assert
the CSV cell says `99`. Frontend: zero date arithmetic — `test_frontend_no_client_day_count.py`
regex-bans `getDay`/`getUTCDay` in every shipped `frontend/src` file, including your new ones.
(It is ONE test that loops files internally, not parametrized — new frontend files change the
collected count by ZERO.)

### Landmine 8 — An export writes NOTHING. Guard arithmetic is almost all zeros.

No audit row (AD-8: `audit_entry` holds transitions "and nothing else"; SM-4 stays exactly 14;
the repo audit surface is pinned to `{insert_audit_entry, list_audit_entries}` by
`test_leave_request_submit.py:595-606`). No notification (kinds fixed at 3, CHECK-pinned). No
migration (chain list, `HEAD_REVISION` = 0013, schema exact-set: all untouched). No new
vocabulary, no `main.py::CODE_TO_STATUS` edit. **Expected guard deltas: +2 vocabulary-file
cases (new api + service modules), +0 scope-matrix, +0 chain, +0 or +1 scoped-getter (Open
Decision #1: only if a new repo function is added — and it MUST take `actor`; an EXEMPT entry
would be wrong for Employee-derived data), +0 from the frontend getDay guard (one looping
test, not parametrized).** Baseline is **612 collected / 612 passed** on the dirty tree
(4-1's review entry in sprint-status, 4-1 story :513-516).
MEASURE with `pytest --collect-only -q` before writing code; close the delta exactly; never
derive (the 3.2/3.4 lesson).

### Landmine 9 — "Export exactly what they see" spans a page boundary. Declare the resolution; don't fudge it.

The screen shows a *page* (the app is page-1-only everywhere except 3.1's paginated history —
deferred-work.md's standing entry); the export carries *all* matching rows (Landmine 1). These
are consistent — FR-15's exact words are "the **filter set** applied to the view is applied to
the export" (prd.md:451), filters not pages — but only if the screen says so. The panel's
export button exports the full filtered set while the list shows a page; the AC5 test story is
"apply filters → the export honors those same filter params". State this in the Dev Agent
Record as the reading applied; do not silently export only the visible page (violates AC2) and
do not silently drop the on-screen list (then nothing is "seen").

## Tasks / Subtasks

- [x] **Task 1 — Repository: one unpaginated read, same predicates (AC1, AC2)** (Open Decision #1)
  - [x] Extend `repositories/leave_request.py` so the export path can read ALL matching rows
        with the exact same scope + filter predicates as `list_leave_requests` — shared code,
        not a parallel query (OD#1 recommends optional `limit`/`offset`).
  - [x] Keep the `status`/`statuses` mutual-exclusion ValueError intact; keep
        `LeaveRequest.id.desc()` ordering (UUIDv7 → newest first, deterministic CSV).
  - [x] If (and only if) a new `list_*` function is added: it takes `actor`, and
        `test_scoped_getters` gains its +1 case for free — no EXEMPT entry.
- [x] **Task 2 — Service: `services/reports.py` builds the CSV string (AC1-AC4)**
  - [x] `export_leave_csv(actor, *, status=None, leave_type_id=None, date_from=None,
        date_to=None) -> str`: one read transaction (AD-3 via the house session pattern),
        scope from the existing `_scope_for_role`, rows via Task 1's read, rows through the
        existing public `row_to_view` (:230-253).
  - [x] Serialize with stdlib `csv.writer` over `io.StringIO` (RFC 4180 quoting for free —
        `full_name` and `leave_type_name` can contain commas/quotes). Header row + one row per
        request. Dates via `date.isoformat()` (AD-12), `leave_days` as int, `status` verbatim
        uppercase (AD-21). NO fastapi/starlette import (Landmine 2).
  - [x] Re-export `LEAVE_STATUS_VALUES` or import it from `services/leave_requests` for the
        route's filter enum. Docstring names FR-15 (SM-6, SPINE:219).
- [x] **Task 3 — Route: `api/v1/reports.py` (AC1, AC4)**
  - [x] `GET /api/v1/reports/leave.csv`, `Depends(require_role(authz.ROLE_MANAGER,
        authz.ROLE_ADMIN))` (balances.py:91 precedent) + `get_current_employee` for the actor.
  - [x] Query params: `status` via the `LeaveStatusFilter` runtime-enum idiom, `leave_type_id:
        uuid.UUID | None`, `date_from`/`date_to: datetime.date | None` — mirror
        `api/v1/leave_requests.py:541-579` minus `PageParams` (Landmine 1: no `page`, no
        `page_size` on this endpoint).
  - [x] Return `fastapi.Response(content=csv_text, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leave.csv"'})` (OD#2/#3).
        No Pydantic response model; the 200 is pinned by headers + parsed body, the 4.1 way.
  - [x] Wire into `api/v1/router.py`: one import, one `include_router` (flat, no prefix — the
        module declares its full path, house style).
- [x] **Task 4 — Backend integration tests: `tests/integration/test_leave_report_csv.py` (AC1-AC4)**
  - [x] See Testing requirements for the full list. Direct-insert seeding, zero audit/
        notification rows, app-engine teardown (3.5 precedent); parse the CSV body with
        stdlib `csv.reader`, pin the header row's exact column set (the key-set pin, house
        rule); pin `Content-Type` and `Content-Disposition` headers.
  - [x] The >100-rows anti-truncation test (Landmine 1) and the Manager-own-row-absent test
        (Landmine 4) are non-negotiable.
- [x] **Task 5 — Frontend API: `api/reports.ts` (AC5)**
  - [x] `fetchLeaveReportCsv(filters: LeaveRequestFilters) -> Promise<Blob>`: build the query
        string by reusing `FILTER_PARAM_NAMES` from `api/leaveRequests.ts` **minus
        `page`/`pageSize`**, call `apiFetchBlob('/reports/leave.csv?…')`. Shared wire names =
        screen and export cannot disagree (that IS AC5). NOTE: `FILTER_PARAM_NAMES` is
        currently a module-private `const` (`leaveRequests.ts:192`) — add `export` to it
        (one-word edit, declared in the File List).
- [x] **Task 6 — Frontend screen: `features/reports/ReportsPanel.tsx` (AC5)** (Open Decision #4)
  - [x] Self-gates to `role === 'MANAGER' || role === 'ADMIN'` via `useMe`, returns `null`
        otherwise (NFR-16 — usability, never the guard; the server 403 is the guard). Mounts
        as one more panel in `App.tsx`'s stacked `shell__main` (no router exists).
  - [x] Filter form cloned from `MyLeaveHistoryPanel`'s pattern: status `<select>`, leave-type
        `<select>` fed by `useLeaveTypes` (with `{enabled}` gating + loading/error/empty
        messaging), `date_from`/`date_to` inputs, `''` = absent mapped to `undefined`.
  - [x] On-screen list: the same filters through the existing `GET /leave-requests` query
        (Manager scope is reports-only there too) with `Pager` — 3.1's machinery verbatim.
  - [x] "Export CSV" button: imperative `fetchLeaveReportCsv(currentFilters)` →
        `URL.createObjectURL` → `<a download="leave.csv">` click → delayed `revokeObjectURL`
        (ViewDocumentButton pattern). Failure states the reason (NFR-17). Disabled while
        in flight. No TanStack Query key needed for the export itself (imperative, like 4.1's
        document view — and `queryClient.clear()` at both session boundaries already covers
        any keys the list reuses).
  - [x] Zero new CSS (existing `panel`, `emp-fields`, `emp-list`, `muted`, `emp-error`
        classes); usable at desktop and tablet widths (NFR-18); NO charts, NO aggregates
        (SM-C2); no `getDay`/`getUTCDay`.
- [x] **Task 7 — Verification arithmetic and evidence (all ACs)**
  - [x] `pytest --collect-only -q` BEFORE coding: confirm 612. After: explain every unit of
        the delta (new tests + 2 vocab-file cases + 0/1 scoped-getter; the frontend getDay
        guard adds ZERO cases). All pass; import-linter 7/7; `alembic check` clean.
  - [x] Frontend: `tsc`, `vite build`, `oxlint` clean, getDay-scan — and code reading. There
        is STILL no frontend test runner; say so plainly in the record, per house convention.
  - [x] Live check through the proxy (`:8443`): log in as the seeded Manager, apply a filter,
        export, open the file. nginx needs no change (downloads are responses, not uploads;
        `client_max_body_size` is upload-only) — but 4.1's uid-10001 volume lesson says the
        only checks that catch environment defects are live ones. AC4's "no PDF export
        exists" is satisfied by absence of any PDF *generation/export* code — note a bare
        `grep -i pdf` DOES hit 4.1's upload content-type constants (`application/pdf` in
        `vocabulary.py:412`, `RequestPreviewPanel.tsx:35`); those are expected and are not
        export code.

## Open Decisions

### 🚨 #1 — How the export reads ALL rows. RECOMMEND: make `limit`/`offset` optional on the existing repo function.

The blocker: `list_leave_requests` requires `limit`/`offset` (Landmine 1). Options:

- **(a) RECOMMENDED — optional `limit: int | None = None, offset: int | None = None` on the
  existing `repositories/leave_request.list_leave_requests`**, applying `LIMIT/OFFSET` only
  when given. One function, one WHERE clause — filter/scope parity between screen and export
  is guaranteed **by construction**, which is exactly AC2's demand. Zero new scoped-getter
  case, zero signature breaks (existing callers pass both today). The `total` the function
  already returns is simply ignored by the export path.
- **(b) A new `list_leave_requests_for_export(session, actor, *, scope, status, leave_type_id,
  date_from, date_to)`** sharing an extracted predicate-builder helper with the list. Cleaner
  separation, but +1 scoped-getter case, and "shared helper" is a promise where (a) is a fact.
- **(c) Loop pages inside one session in the service.** Correct but gratuitous: two round
  trips minimum, and the loop is one more thing to get wrong. Rejected.

NFR-10's data scale (one small organization) makes an unbounded read safe; the endpoint is
role-gated to Manager/Admin. Whichever lands, the >100-rows test pins the outcome.

### #2 — The CSV column set. RECOMMEND: the `row_to_view` fields minus internal UUIDs, header row pinned.

api-contracts §5 (:249-251) deliberately leaves the exact column set to the code. Recommended
header, in order:

```
employee_full_name,leave_type_code,leave_type_name,start_date,end_date,leave_days,status
```

Rationale: these are exactly the human-answerable fields (FR-20's history entry is the nearest
analogue: "the Leave Type, the date range, the Leave Day count, and the current state" —
prd.md:404, plus the employee name since this is a multi-employee report). All seven are
already in `_READ_COLUMNS`/`row_to_view` — no new query shape. Internal UUIDs (`id`,
`employee_id`, `leave_type_id`) answer no manager's question and leak nothing useful; omit
them. (If the dev disagrees, adding them is a one-line change — the pin is the test's header
assertion either way.) NEVER `password_hash` or email-adjacent columns beyond what the view
already carries. Values: dates `YYYY-MM-DD`, `leave_days` int, `status` verbatim uppercase.

### #3 — Response mechanics. RECOMMEND: buffered `Response`, not `StreamingResponse`; UTF-8, no BOM.

At NFR-10 scale the whole CSV is a few hundred KB at worst; `StreamingResponse` buys nothing
and complicates testing. `media_type="text/csv; charset=utf-8"`,
`Content-Disposition: attachment; filename="leave.csv"` (static filename — the path already
names it), plain UTF-8 without BOM (Excel-BOM pandering is a non-requirement; nothing in the
plan names Excel). stdlib `csv.writer` default dialect (`\r\n` line endings, RFC 4180
quoting). Both headers pinned by test, the 4.1 convention for a non-JSON 200.

### #4 — Report screen shape. RECOMMEND: filters + paged on-screen list + export button; the export carries the full filtered set.

AC5's "export exactly what they see" needs something visible to see. The cheapest honest
screen: the 3.1 filter form + the existing `GET /leave-requests` list under the same filter
state (+ `Pager`), + an Export button that downloads `/reports/leave.csv` with those same
filter params (shared `FILTER_PARAM_NAMES`, minus paging). The list shows a page; the export
carries every matching row — FR-15 binds the *filter set*, not the page (Landmine 9). Declare
this reading in the Dev Agent Record. Alternative (filters + export button, no list) was
rejected: it makes AC5's "what they see" vacuous and gives the Manager no way to sanity-check
before exporting.

Note the Manager nuance: the on-screen list via `GET /leave-requests` is REPORTS-scoped for a
Manager (excludes their own rows — pinned since 3.1), so screen and export agree on scope too.
Do NOT reuse `MyLeaveHistoryPanel` itself (it is the *self* history); clone its form pattern
into the new panel.

## Dev Notes

### Architecture compliance

- **AD-1 / import-linter (7 contracts, `pyproject.toml:74-160`):** `api/v1/reports.py` imports
  `services/` only (contract 2 — no `repositories/`, no `domain/`; role constants via
  `app.services.authorization` as `authz.ROLE_MANAGER`…). `services/reports.py` imports no
  fastapi/starlette (contract 4); stdlib `csv`/`io` are fine.
- **AD-3:** the read gets its session/transaction in the service, house pattern — never in the
  route, never in the repo.
- **AD-10:** scope as a SQL predicate via the existing `employee_scope_predicate`; never
  post-filter rows in Python. No path param → no 404 case; the role miss is 403
  `ACTION_NOT_PERMITTED` (G3: 403 = role-denied, 404 stays reserved for scope misses).
- **AD-12 / AD-21 / quantities:** dates `YYYY-MM-DD`; enums UPPER_SNAKE_CASE verbatim;
  `leave_days` integer (never NUMERIC/float, DR-10).
- **AD-18:** stored `leave_days` only. The CSV path reads `_READ_COLUMNS`; it has no access to
  the day-count function and must not import it.
- **Errors:** 200 is CSV; every non-2xx still carries the JSON envelope (api-contracts:56) —
  which `apiFetchBlob`'s error path already decodes. No new codes; nothing to add to
  `CODE_TO_STATUS`.
- **SM-6:** every new module's docstring names FR-15.

### The response surface (pinned by test, the house rule)

Non-JSON 200 → no Pydantic envelope. Pin instead: `Content-Type` starts `text/csv`;
`Content-Disposition` is `attachment; filename="leave.csv"`; the parsed body's header row
equals the exact recommended column list (OD#2). This is 4.1's document-GET convention
applied to CSV.

### Testing requirements

`tests/integration/test_leave_report_csv.py`, direct-insert seeding (no audit/notification
side-effects), dates relative to `date.today()` where the calendar is irrelevant, app-engine
teardown. Parse bodies with stdlib `csv.reader`. The must-have list:

1. **Manager scope (AC1 + Landmine 4):** Manager with two reports + own request + an unrelated
   employee's request → export contains exactly the two reports' rows; **the Manager's own row
   is absent**; the unrelated row is absent.
2. **Admin scope (AC1):** the same seed → Admin export contains every row, including the
   Manager's own and the unrelated employee's.
3. **Role gate:** Employee → `403 ACTION_NOT_PERMITTED` (JSON envelope); no token → `401`.
4. **Filters compose (AC2):** `status` + `leave_type_id` + date window together → the
   intersection, exactly.
5. **Inherited edges (AC2, Landmine 5):** one OVERLAP boundary case (a request straddling
   `date_from` appears); inverted range → 200, header row only; nonexistent-but-valid-UUID
   `leave_type_id` → 200, header row only; bad `status` → 422.
6. **Anti-truncation (Landmine 1):** seed >100 matching rows (bulk direct-insert, one
   employee, minimal columns) → the CSV body has ALL of them, not 100. THE test of this story.
7. **AD-18 canary (AC3, Landmine 7):** direct-insert `leave_days=99` over a 3-day range → the
   CSV cell reads `99`.
8. **Format pins (AC4):** header row exact; `Content-Type`/`Content-Disposition` exact; a
   `full_name` containing a comma and a quote survives round-trip through `csv.reader`
   (quoting proof, non-vacuous).
9. **Read purity (Landmine 8):** audit_entry and notification row counts are unchanged by an
   export call.

Frontend: no runner exists — tsc + vite build + oxlint + getDay-scan + reading, stated
plainly, per every story since 3.1.

### Project Structure Notes

NEW files:
- `backend/app/api/v1/reports.py` — the route (SPINE:398 fixes the module name)
- `backend/app/services/reports.py` — CSV composition + orchestration
- `backend/tests/integration/test_leave_report_csv.py`
- `frontend/src/api/reports.ts`
- `frontend/src/features/reports/ReportsPanel.tsx`

UPDATE files (touch NOTHING else):
- `backend/app/repositories/leave_request.py` — OD#1(a): optional `limit`/`offset` (or a new
  export getter under OD#1(b), taking `actor`)
- `backend/app/api/v1/router.py` — one import + one `include_router`
- `frontend/src/App.tsx` — mount `<ReportsPanel />` in `shell__main`
- `frontend/src/api/leaveRequests.ts` — `export` keyword on `FILTER_PARAM_NAMES` (Task 5)
- `frontend/src/api/index.ts` — re-export, if the barrel convention is followed there

NO changes to: migrations (head stays 0013), `domain/vocabulary.py`, `main.py`,
`docker-compose.yml`, `proxy/nginx.conf` (downloads are unaffected by `client_max_body_size`),
`Dockerfile`, `pyproject.toml` dependencies (stdlib only). No image rebuild needed — pure
Python/TS changes ride the existing images' bind mounts; if the api image bakes code, rebuild
per 4.1's note.

### Previous Story Intelligence (4.1, in review — read its Dev Agent Record before starting)

- **Baseline is 612 collected / 612 passed** on this dirty tree. Measure first; the 3.2/3.4
  formula-undercount lesson is now house law.
- **Guard edits are declared, never silent.** 4.2's expected guard footprint is nearly zero
  (Landmine 8) — declare the zeros too.
- **The live proxy check earns its keep:** 4.1's only environment defect (root-owned volume →
  500 on every upload) was invisible to 612 green tests and caught only at `:8443`. Do the
  live export.
- **The dev DB bites:** if the suite is slow or red on pickup, check `pg_stat_user_tables`
  row counts and for orphaned pytest processes before blaming code; `docker exec` without
  `-i` silently no-ops psql input.
- **`apiFetchBlob` and `toApiError`** were factored exactly so the next binary endpoint (this
  one) reuses them — do not fork a second blob fetcher.
- **Ten-key `LeaveRequestResponse` pin:** untouched by this story; the report screen's list
  consumes the existing response as-is. Do not widen it.
- 4.1 is in **review** status: its tree is load-bearing but unreviewed. If its review lands
  fixes mid-flight, rebase your mental model — the files above are the interface, not the
  implementation details.

### Git Intelligence

Committed history ends at `4fc1629` (stories 2.9-2.12). Everything since — all of Epic 3, the
2026-07-15 review fixes, and Story 4.1 — is UNCOMMITTED working tree (~48 modified + ~40
untracked files). Build on top. Do not commit, do not revert. The commit-message convention
when the time comes is `feat(story-4.2): …` per the log.

### Latest Technical Information

- Stack pins (`pyproject.toml`, `==` not floors, do not upgrade): FastAPI 0.139.0,
  Python 3.13.*, SQLAlchemy 2.0.51, Pydantic 2.13.4, pytest 9.1.1, import-linter 2.13.
- **This story adds ZERO dependencies.** `csv` and `io` are stdlib; `fastapi.Response` with
  `media_type` + headers has been stable API since long before 0.139. No `python-multipart`
  interaction (that was uploads). No StreamingResponse needed (OD#3).
- Frontend: existing React + TanStack Query + Vite + oxlint toolchain; the download uses
  browser-native `URL.createObjectURL` + anchor `download` attribute — no library.

### References

- epics.md — Story 4.2 (:1629-1657), Story 3.1 (:1409-1448), FR-15 (:64), Epic 4 notes
  (:478-489, :1584-1588), AD-10 (:142), AD-18 (:150), AD-21 (:153)
- prd.md — §4.8/FR-15 (:439-455), FR-12 (:410-417), FR-03 (:148-159), §7.4 (:557), SM-8
  (:638), SM-C1/C2 (:643-644), NFR-04 (:572), NFR-10/-11 (:584-585), NFR-16/-17/-18 (:594-596)
- ARCHITECTURE-SPINE.md — AD-1 (:71), AD-10 (:125), AD-18 (:173), AD-21 (:191), conventions
  (:207-219), capability map (:398), source tree (:356-378)
- api-contracts.md — §4.9 (:225-237; endpoint row :235; filter-parity sentence :237), §1
  conventions (:19-56), §2 codes (:69-89), scope notation (:106), §5 code-owned schemas
  (:249-251)
- erd.md — leave_request (:95-103, :219-227: "Computed once at admission and frozen"),
  employee (:172-185), leave_type (:187-196), indexes (:372-383)
- Code: `repositories/leave_request.py:117-128` (`_READ_COLUMNS`), :165-242 (list + the
  4.2-inheritance docstring :189-192); `services/leave_requests.py:214-227`
  (`_scope_for_role`), :230-253 (`row_to_view`), :872-907 (list service);
  `api/v1/leave_requests.py:60-69` (`LeaveStatusFilter`), :541-579 (list route);
  `api/v1/pagination.py:35-43`; `api/v1/balances.py:91` (multi-role gate);
  `api/v1/audit_entries.py:21-27` (no-path-param scope-matrix prose);
  `frontend/src/api/client.ts:148-207` (`toApiError`, `apiFetchBlob`);
  `frontend/src/api/leaveRequests.ts:182-224` (`FILTER_PARAM_NAMES`);
  `frontend/src/features/leave/MyLeaveHistoryPanel.tsx` (filter-form pattern);
  `frontend/src/features/leave/ManagerQueuePanel.tsx:64-77` (blob download pattern)
- Guards: `tests/test_scope_matrix.py:233-245`, `tests/test_scoped_getters.py`,
  `tests/test_vocabulary_literals.py:108`, `tests/test_frontend_no_client_day_count.py`,
  `tests/integration/test_leave_request_submit.py:595-606`
- deferred-work.md — page-1-only standing entry, frontend status literals (:83)
- Story 4.1 (`4-1-attach-a-supporting-document.md`) — Dev Agent Record :445-576

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) via Claude Code, 2026-07-15.

### Debug Log References

- Baseline MEASURED before any code: `pytest --collect-only -q` → **612 collected** on the dirty
  tree, exactly as declared. Final: **628 collected / 628 passed** (85s). Import-linter 7/7 kept;
  `alembic check` clean (head stays 0013).
- Docker uses `docker-compose` (v1 CLI) on this machine, not `docker compose`. The api image
  BAKES the code (no bind mount), so the live check required `docker-compose build api && up -d
  api` first — 4.1's rebuild note confirmed in practice.
- Login response key is `access_token` (not `token`) — tripped the first live-check attempt.

### Completion Notes List

- **All 6 ACs met, no deviations.** Open Decisions all landed as RECOMMENDED:
  - **OD#1(a):** `limit`/`offset` made OPTIONAL (`int | None = None`) on the EXISTING
    `repositories/leave_request.list_leave_requests` — `LIMIT`/`OFFSET` applied only when given.
    One function, one WHERE clause: filter/scope parity between screen and export is guaranteed
    by construction (AC2). Zero signature breaks (all existing callers pass both); zero new
    scoped-getter case; the `status`/`statuses` mutual-exclusion ValueError and `id.desc()`
    ordering untouched.
  - **OD#2:** 7 human-answerable columns, no internal UUIDs:
    `employee_full_name,leave_type_code,leave_type_name,start_date,end_date,leave_days,status` —
    header pinned as LITERALS in the test (pinning against the constant would be vacuous).
  - **OD#3:** buffered `Response`, `text/csv; charset=utf-8`, UTF-8 no BOM,
    `Content-Disposition: attachment; filename="leave.csv"` — both headers pinned by test
    (the 4.1 non-JSON-200 convention). stdlib `csv.writer` default dialect (RFC 4180).
  - **OD#4 / Landmine 9 — the page-boundary reading, DECLARED:** the panel's on-screen list
    shows a PAGE (existing `GET /leave-requests` + `Pager`); the Export button carries EVERY
    row matching the same filter set. FR-15's exact words bind the FILTER SET applied to the
    view, never the page — the shared `FILTER_PARAM_NAMES` map (minus `page`/`pageSize`) is
    what makes screen and export unable to disagree on a wire name (AC5). The panel's intro
    text states this to the user.
- **Landmine 1 closed and pinned:** the export path passes NO limit — the >100-rows
  anti-truncation test seeds 105 matching rows and counts all 105 in the CSV body.
- **Landmine 4 pinned:** the Manager-scope test seeds the Manager's OWN request and asserts its
  ABSENCE from the Manager's export (and its presence in the Admin's) — scope `reports, all`,
  no `self`.
- **AD-18 pinned non-vacuously:** direct-inserted `leave_days=99` over a 3-day range exports as
  `99` (the house canary).
- **Landmine 8 (read purity) pinned:** audit_entry and notification counts are unchanged by
  Manager and Admin export calls. An export writes NOTHING.
- **Guard arithmetic, closed exactly:** 612 baseline + 14 new integration tests + 2
  vocabulary-file cases (`api/v1/reports.py`, `services/reports.py`) + 0 scope-matrix (no path
  param — the `audit_entries.py` precedent; adding an entry would FAIL the stale-entry guard)
  + 0 chain/HEAD_REVISION (no migration) + 0 scoped-getter (OD#1(a), no new function) + 0 from
  the frontend getDay guard (one looping test) = **628 collected, 628 passed**.
- **Frontend verification:** `tsc --noEmit` silent, `vite build` clean, `oxlint` exit 0,
  `getDay`/`getUTCDay` grep zero hits across `frontend/src` (including the new files). There is
  STILL no frontend test runner — AC5 is verified by tsc + vite build + oxlint + the backend
  getDay-guard scan + code reading, stated plainly per house convention since 3.1.
- **Live proxy check (`:8443`) done, non-vacuously:** rebuilt the api image (it bakes code),
  logged in as the seeded Admin, exported — 200 with both headers byte-exact and the header-row-
  only body on the empty dev DB; then direct-inserted one row, re-exported (row present,
  correctly labelled `EL · Earned Leave`, stored `leave_days` verbatim), exercised the
  status+date-window filter through the proxy, and deleted the dev row after. nginx needed no
  change (downloads are responses; `client_max_body_size` is upload-only).
- **AC4 (no PDF):** `grep -i pdf` hits are exactly the expected 4.1 upload content-type
  constants (`vocabulary.py`, `documents.py`, `main.py` comment, `RequestPreviewPanel.tsx`)
  plus this story's own AC4 prose in `reports.py`. No PDF generation/export code exists.
- No new dependencies (stdlib `csv` + `io`), no migration, no new vocabulary or error code, no
  audit row (SM-4 stays 14), no notification (kinds stay 3), no new CSS, no charts (SM-C2).
- **SM-8 note:** this was the last story in the plan; with it in review, every FR has an
  implementation.

### File List

NEW:
- `backend/app/services/reports.py` — CSV composition + scoped unpaginated read (FR-15)
- `backend/app/api/v1/reports.py` — `GET /api/v1/reports/leave.csv` route
- `backend/tests/integration/test_leave_report_csv.py` — 14 integration tests
- `frontend/src/api/reports.ts` — `fetchLeaveReportCsv` (shared wire names, minus paging)
- `frontend/src/features/reports/ReportsPanel.tsx` — filters + paged list + Export button

UPDATED:
- `backend/app/repositories/leave_request.py` — OD#1(a): `limit`/`offset` now optional on
  `list_leave_requests`; docstring extended
- `backend/app/api/v1/router.py` — one import + one `include_router`
- `frontend/src/api/leaveRequests.ts` — `export` on `FILTER_PARAM_NAMES` (+ doc note)
- `frontend/src/api/index.ts` — re-export `fetchLeaveReportCsv`
- `frontend/src/App.tsx` — mount `<ReportsPanel />` in `shell__main`

### Review Findings

Code review 2026-07-15 (Blind Hunter + Edge Case Hunter + Acceptance Auditor; no AC violations found).

- [x] [Review][Patch] CSV formula injection via unescaped cell values. FIXED: `_sanitize_cell` prefixes a single quote (OWASP literal-text marker) on any text cell leading with `=` `+` `-` `@` TAB CR, applied to the three free-text-adjacent columns; pinned by `test_a_formula_shaped_name_is_neutralized_in_the_cell` (a `=HYPERLINK(...)` `full_name` arrives quote-prefixed). [backend/app/services/reports.py]
- [x] [Review][Patch] Stale page after the row set shrinks under an active filter. FIXED: the MyLeaveHistoryPanel clamp idiom (`useEffect` snapping `page` to the last real page when `total` drops), verbatim. [frontend/src/features/reports/ReportsPanel.tsx]

## Change Log

- 2026-07-15 — Code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) — zero AC
  violations; 2 patches applied (CSV formula-injection neutralization via `_sanitize_cell`,
  pinned by a `=HYPERLINK` canary test; ReportsPanel page clamp, the MyLeaveHistoryPanel idiom),
  0 deferred, several export-adjacent findings dismissed as spec-sanctioned (static filename,
  discarded COUNT, runtime-enum restatement). 634 backend tests passing. Status → done.

- 2026-07-15 — Story context created by create-story (ultimate context engine analysis
  completed — comprehensive developer guide created). Status: ready-for-dev.
- 2026-07-15 — Implementation complete (dev-story). All 6 ACs met; all Open Decisions landed as
  recommended (OD#1(a) optional `limit`/`offset` on the existing repo function; OD#2 seven-column
  header; OD#3 buffered Response, UTF-8 no BOM; OD#4 filters + paged list + full-set export,
  page-boundary reading declared). Backend: `services/reports.py`, `api/v1/reports.py`, 14
  integration tests (>100-rows anti-truncation, Manager-own-row-absent, AD-18 canary, read-purity
  among them). Frontend: `api/reports.ts`, `ReportsPanel.tsx`, shared `FILTER_PARAM_NAMES`.
  612 → 628 collected/passed, delta explained unit-by-unit; import-linter 7/7; alembic check
  clean; tsc/vite/oxlint clean; live proxy export verified at :8443 (api image rebuilt — it bakes
  code). No migration, no new dependency, no new vocabulary, no audit row, no notification.
  Status: review.
