---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

<!--
  Story context created 2026-07-14 by create-story (ultimate context engine).
  Sources: epics.md §Epic 3 / Story 3.3 (:1478-1505); prd.md FR-18 (:377-381), UJ-2, DR-15,
  §7.4; api-contracts.md §1/§4.9 (:233, :237); ARCHITECTURE-SPINE.md (AD-10, AD-18 :169-173,
  FR-18 map :401); erd.md §4.4 (:380); deferred-work.md; story files 3-1, 3-2, 2-7;
  live working tree (3.1 AND 3.2 in review, UNCOMMITTED, atop 4fc1629).
  ⚠️ The working tree is DIRTY with Stories 3.1 + 3.2 — build on top of them, do not
  revert or commit them.
-->

# Story 3.3: The Department Leave Calendar, at the Moment of Decision

Status: done

## Story

As a Manager,
I want to see who else on my team is already away on the dates I am deciding,
So that I authorize an overlap knowingly rather than discover it the following week.

## Orientation: what this story actually is

**`GET /leave-requests` with the scope pinned, the status set fixed, and the door marked
Manager-only — mounted at the path §4.9 grants, then rendered where the decision happens.**
`GET /api/v1/calendar` returns a Manager's Direct Reports' **PENDING + APPROVED** leave
requests that **overlap** a date range. Every part of that sentence already exists and is
pinned by tests:

| Need | Already exists at |
|---|---|
| The overlap predicate, settled + pinned | `repositories/leave_request.py:207-209` (Story 3.1, Open Decision #1: `end_date >= date_from AND start_date <= date_to`, each side optional) — pinned by `tests/integration/test_leave_request_history.py` boundary tests |
| The scope predicate | `repositories/scoping.py:73` — `Scope.REPORTS` → `Employee.manager_id == actor.id`, live at request time (AD-10/AD-14); a Manager's own row can never match |
| The index, named for THIS story | `ix_leave_request_start_end` — erd.md:380: "`leave_request (start_date, end_date)` \| Department Leave Calendar… (`FR-18`…)". It shipped in 0006. **No migration.** |
| The role gate + 403 | `require_role(authz.ROLE_MANAGER)` → `ACTION_NOT_PERMITTED`, mapped 403 in `main.py:56` since 1.4 — no `main.py` change |
| The read columns + view + response | `repositories/leave_request.py:117-128` `_READ_COLUMNS`; `services/leave_requests.py` `LeaveRequestView` (:101-123) + row mapper (:208-227); `api/v1/leave_requests.py` `LeaveRequestResponse` (:275-296) + projection (:298-316) |
| The service shape for a Manager-only read | `services/team.py` (Story 3.2) — service hardcodes `Scope.REPORTS`; `api/` never sees `Scope` |
| Pagination | `api/v1/pagination.py` — `PageParams` + `Page[T]`, `MAX_PAGE_SIZE=100`, `MAX_PAGE` clamp |
| Frontend Manager gate + decision screen | `ManagerQueuePanel.tsx:46-57` gate idiom; the queue rows (:90-121) ARE the approval screen the calendar mounts on |
| Frontend hook idiom + invalidation fan-out | `api/leaveRequests.ts` (`useLeaveRequests` :174-191, `invalidateAfterDecision` :204-236, onSettled) |

**What is genuinely new — three things:**

1. **A status-SET predicate.** Story 2.7 built only single-value `status ==` equality
   (`leave_request.py:203`). The calendar needs `status IN (PENDING, APPROVED)` — one
   keyword-only param threaded onto the existing getter (Landmine 1).
2. **The inline calendar on the decision screen** — the point of the story (UJ-2: "the
   overlap is visible at the moment of decision, not discovered the following week"), plus
   its invalidation: a decision changes the calendar's picture, so `CALENDAR_QUERY_KEY`
   must join the decision's onSettled fan-out (Landmine 6).
3. **AC4 is a zero-diff assertion about the decide path.** Overlap must produce no warning,
   no block, no acknowledgement (BR-06, DR-15). The strongest proof is that
   `services/leave_requests._decide` is byte-untouched — plus a test approving into a
   two-report overlap and getting a plain 200 (Landmine 7).

**The contract inversion, second verse (internalize again): the Admin gets 403.**
api-contracts §4.9:233 grants `/calendar` to `Manager / reports` — exactly like `/team`,
whose router docstring already explains it: a team is a reporting edge only a Manager
stands on. An Admin reads any request via `GET /leave-requests` (scope ALL). Employee AND
Admin both get `403 ACTION_NOT_PERMITTED` from the gate, before any row is read (G3).
`require_role(authz.ROLE_MANAGER)` gives it for free — do not add Admin.

No migration, no model change, no new vocabulary, no new error code, no `main.py` change,
no scope-matrix entry (no path param), no new repo getter (extend the existing one), no new
dependency (no date-picker library — the calendar renders server rows as-is). Stack pins
frozen (FastAPI 0.139.0, SQLAlchemy 2.0.51, React 19.2.7, TanStack Query 5.101.2) — nothing
to research, nothing to upgrade.

## Acceptance Criteria

*(From epics.md:1478-1505 verbatim, clauses compressed; FR-18 at prd.md:377-381.)*

1. **Given** an authenticated Manager and a date range, **when** they call
   `GET /api/v1/calendar`, **then** the response contains the leave of their Direct
   Reports across that range, and of no other Employee (`FR-18`, `AD-10`).
2. **Given** the calendar, **when** it is rendered, **then** Approved and Pending leave
   are both shown, visually distinguished from one another (`FR-18`).
3. **Given** a Manager opening a Pending Leave Request to decide it, **when** the approval
   screen renders, **then** the calendar for that request's dates is presented inline on
   the same screen (`FR-18`, `UJ-2`).
4. **Given** two Direct Reports already approved as away on a requested date, **when** the
   Manager approves the request under decision, **then** the approval succeeds, **and**
   the overlap produced no warning, no block, and no required acknowledgement — the system
   informs, and never blocks (`BR-06`, `DR-15`).
5. **Given** any leave shown on the calendar, **when** its day count is read, **then** it
   is the value stored on the request, never recomputed (`AD-18`).

*(Not a written AC but binding contract, tested under AC1: §4.9 grants `/calendar` to
Manager ONLY — an Employee and an Admin both receive `403 ACTION_NOT_PERMITTED` from the
role gate, before any row is read. G3, api-contracts §1:39-42, the 3.2 AC4 precedent.)*

## 🚨 Landmines. Read all eight before writing a line.

### Landmine 1 — The status set is ONE keyword-only param on the EXISTING getter. No second getter, no `list_requests_covering`.

`repositories/leave_request.py::list_leave_requests` (:165-231) supports only
`status == <one value>`. Add `statuses: tuple[str, ...] | None = None` (keyword-only);
when not None append `LeaveRequest.status.in_(statuses)` to the SAME `conditions` list
both queries share. `status` is a LOCAL `leave_request` column, so page and count stay in
agreement (3.1 Landmine 3: filter on local columns or `total` lies).

Do NOT write a new repo getter — a new `list_*(session, ...)` without an `actor` param
trips `test_scoped_getters.py` (`_ACTOR_PARAM_NAMES` at :149), and one WITH `actor` is a
duplicate of what exists (3.2 Landmine 3's rule: extend, don't clone). And do NOT reach
for `list_requests_covering` (:234-295): it is single-date not range, SCOPE-LESS
(system-wide, `EXEMPT` at `test_scoped_getters.py:111` as the recalculation sweep), and it
filters APPROVED to future-only — three ways wrong for a calendar.

### Landmine 2 — `api/` may not import `Scope` OR `vocabulary`. The route names NO status at all.

Import-linter contract 2 (`pyproject.toml:96-100`) forbids `api/` → `app.repositories` /
`app.domain`. The `Scope.REPORTS` decision AND the `(STATUS_PENDING, STATUS_APPROVED)`
tuple both live in the new `services/calendar.py` (services may import both — see
`services/team.py:32` and `services/leave_requests.py`). The calendar route takes **no
status query param** (Open Decision #4): FR-18 defines the calendar as Approved+Pending;
the client cannot widen or narrow it, so no status name ever appears in `api/`. Bare
literals `"PENDING"`/`"APPROVED"`/`"MANAGER"` anywhere under `app/` fail
`test_vocabulary_literals.py` (AST scan, annotations included). The frontend is exempt
from that guard and may write `'MANAGER'` (`ManagerQueuePanel.tsx:26` precedent).

### Landmine 3 — Registration is two edits in `router.py`, or everything 404s; and ZERO guard files change.

`app/api/v1/calendar.py` does nothing until `app/api/v1/router.py` gains BOTH the import
(:12-27) and an `include_router` line (:28-43). Write `@router.get("/calendar")` — the
`/api/v1` prefix comes from `main.py:37`.

`GET /calendar` has **no path parameter → OUT of the scope matrix by construction**
(`test_scope_matrix.py:143-146` registers only `{`-bearing paths). Do NOT add it to
`_SCOPE_REGISTRY`. If `main.py`, `domain/vocabulary.py`, `alembic/`, `test_scope_matrix.py`,
`test_scoped_getters.py`, or `pyproject.toml [tool.importlinter]` appear in your diff, you
took a wrong turn (2.9 settlement: guards are revised-with-rationale only when a story
genuinely owns the change — this story owns none).

### Landmine 4 — The 403 must be the gate's, with the envelope, for BOTH wrong roles.

Parametrize Employee AND Admin → `403`, envelope exactly `{code, message, details}`,
`code == vocabulary.ACTION_NOT_PERMITTED`, `details == {}` — the
`test_role_gate.py:149-169` template, executed for `/team` at
`tests/integration/test_team.py:226-242`. 2.7's review dinged a test that proved only one
wrong role; 3.2 pinned both. Do the same.

### Landmine 5 — Overlap semantics are SETTLED. Reuse them; do not re-derive, do not default the dates.

Include a request iff `end_date >= date_from AND start_date <= date_to`, each side
optional (3.1 Open Decision #1, pinned by `test_leave_request_history.py`; Story 4.2's CSV
export inherits the same semantics). Inverted range (`date_from > date_to`) → 200 with
empty `items`, `total == 0` — it falls out of the SQL, zero code (3.1 Open Decision #2).
Malformed dates → framework 422 via `datetime.date | None = Query(default=None)` typing —
no domain error code exists for a read filter and none is invented. Both params default
`None` (= no predicate): never default `date_from` to Jan 1, never let
`_current_leave_year()` near a read path (3.1 Landmine 5) — a calendar range straddling
Dec 31 must work by construction (no `leave_year` column exists to get in the way).

### Landmine 6 — The inline calendar goes stale the instant a decision lands under it, unless you extend the fan-out.

`ManagerQueuePanel`'s approve/reject mutations invalidate via
`invalidateAfterDecision` (`api/leaveRequests.ts:204-207`), wired **onSettled** in all
three decision mutations (:215, :225, :235 — NOT onSuccess; 2.7 review patch: a 409/404
must still refetch to self-heal). A decision
flips a PENDING row to APPROVED/REJECTED — exactly the facts the calendar shows. Add
`CALENDAR_QUERY_KEY` to that same fan-out, or the Manager approves a request and the
calendar under it keeps saying the leave is Pending.

### Landmine 7 — AC4 is satisfied by code you DON'T write.

"No warning, no block, no required acknowledgement" means the decide path
(`services/leave_requests.py::_decide`) gains no overlap awareness whatsoever: no new
response field, no confirmation round-trip, no 4xx. The proof is (a) `_decide` and the
decision endpoints are byte-untouched in the diff, and (b) a test that seeds two reports
already APPROVED across a date, then approves a third report's overlapping PENDING request
— asserting plain 200 and the same response keys the decide endpoint returned before this
story. Do not "improve" the decision response with overlap info; the calendar informs,
the decision endpoint decides (BR-06, DR-15).

### Landmine 8 — You are building on Stories 3.1 AND 3.2's UNCOMMITTED working tree.

HEAD is `4fc1629` (Epic 2 squash); everything Epic 3 is uncommitted (3.1 modified
`leave_requests.py`/repo/service/pagination; 3.2 added `team.py`×2, `Pager.tsx`,
`MyTeamPanel.tsx`, tests). Both stories are in review. Build on top; do not revert, do not
commit their work, do not "clean up" their files beyond what your tasks name. The
documented baseline is **522 passed, 0 skipped** — but 3.2 learned the recorded baseline
can undercount (predicted 512, measured 514): **run the full suite FIRST and record the
real number before adding anything.**

## Tasks / Subtasks

### Task 1 — Repository: keyword-only `statuses` on the existing list read (AC1, AC2)

- [x] In `repositories/leave_request.py::list_leave_requests`, add keyword-only
      `statuses: tuple[str, ...] | None = None`; when not None, append
      `LeaveRequest.status.in_(statuses)` to the shared `conditions` list (local column —
      page and count queries stay in agreement).
- [x] Leave the existing single-value `status` param untouched (2.7's filter; the getter's
      one caller, `services/leave_requests.py:673`, passes named args). Document in the
      docstring that `status` and `statuses` compose by AND like every other filter
      (callers pass one or the other).
- [x] No new getter, no `EXEMPT` change, no index change (`ix_leave_request_start_end`
      already serves this read by name — erd.md:380).

### Task 2 — Service: new read-only `services/calendar.py` (AC1, AC2, AC5)

- [x] Module docstring names FR-18, AD-10, AD-18, BR-06/DR-15 (SM-6 traceability), and
      states the two decisions it embodies: scope is hardcoded `Scope.REPORTS` (Open
      Decision #2) and the status set is fixed `(STATUS_PENDING, STATUS_APPROVED)` (Open
      Decision #4).
- [x] `CALENDAR_STATUSES: tuple[str, str] = (vocabulary.STATUS_PENDING, vocabulary.STATUS_APPROVED)`.
- [x] `list_calendar(*, date_from, date_to, limit, offset, actor) -> tuple[list[LeaveRequestView], int]`:
      open `Session(get_engine(), expire_on_commit=False)` (the `services/team.py:44-47`
      pattern — read-only, never commits), call
      `leave_request_repo.list_leave_requests(session, actor, scope=Scope.REPORTS,
      status=None, statuses=CALENDAR_STATUSES, date_from=..., date_to=..., limit=..., offset=...)`.
- [x] Reuse the existing row→view mapping from `services/leave_requests.py` (:208-227):
      promote `_row_to_view` to public `row_to_view` (rename its ~3 same-module call
      sites; the file is already in this epic's diff). Do NOT copy the mapping — AD-18's
      guarantee (stored `leave_days`, never recomputed) lives in that one mapper reading
      `_READ_COLUMNS` verbatim.

### Task 3 — API: `app/api/v1/calendar.py` + registration (AC1, AC2)

- [x] `router = APIRouter()`;
      `@router.get("/calendar", tags=["calendar"])` →
      `def list_calendar(params: PageParams = Depends(), date_from: datetime.date | None = Query(default=None), date_to: datetime.date | None = Query(default=None), manager: Actor = Depends(require_role(authz.ROLE_MANAGER))) -> Page[LeaveRequestResponse]`.
      Malformed dates are framework 422; inverted range is 200-empty (Landmine 5). No
      status param exists (Landmine 2, Open Decision #4).
- [x] Reuse `LeaveRequestResponse` and its projection from `api/v1/leave_requests.py`
      (Open Decision #1): import the response model; promote `_to_leave_request_response`
      to public `to_leave_request_response` (same single-home precedent as
      `DepartmentBrief` imported from `employees.py` — never redeclare a response shape).
- [x] Assemble `Page[LeaveRequestResponse](items=..., page=params.page,
      page_size=params.page_size, total=total)` — the `team.py:70-89` shape.
- [x] Register in `app/api/v1/router.py`: import tuple + `include_router` (Landmine 3).

### Task 4 — Backend tests: new `tests/integration/test_calendar.py`, red-green (AC1, AC2, AC4, AC5)

- [x] **Write this file FIRST and watch every test fail 404** (an unregistered path 404s
      before auth — the 3.2 red-green precedent), then implement Tasks 1-3, then green
      with no test edit. Top-of-file `import app.main` + `TestClient(app.main.app)`
      (documented false-green trap).
- [x] World fixture in the `test_team.py:63-171` house style (build-your-own-world; seed
      via direct inserts; teardown nulls `manager_id` before deleting — self-FK RESTRICT):
      `manager_m` with reports `r1`, `r2`, `r3` and a deactivated report `r4`;
      `other_manager` with `other_report`; an `admin` and a scope-less `employee`.
      **Seed leave rows by repo-level INSERT** (the 3.1 rollover precedent: submission
      refuses past dates and writes audit rows; direct inserts do neither, leaving SM-4's
      ledger undisturbed). Rows: `r1` APPROVED and `r2` APPROVED overlapping a target
      date; `r3` PENDING overlapping; `r1` REJECTED and `r2` CANCELLED in-range (to prove
      exclusion); `other_report` APPROVED in-range (to prove scope); `r4` (deactivated)
      APPROVED in-range; one APPROVED row straddling Dec 31 (cross-year); one row ending
      the day before `date_from` (boundary exclusion).
      **⚠️ For `r3`'s PENDING request ONLY — the one AC4 approves through the real
      endpoint — the direct-INSERT shortcut is NOT enough:** `_decide` calls
      `balances.consume_reserved`, which locks the balance row (`balances.py:62-74` —
      a missing row is `LookupError` → raw 500) and requires `reserved >= leave_days`
      (`balances.py:138-145` — else `ValueError` → raw 500). Either seed a
      `leave_balance` row for (`r3`, leave_type, `start_date.year`) with
      `reserved == leave_days` and sufficient `accrued`, or create `r3`'s request via
      the real `POST /leave-requests` after materializing its balance (the
      `test_leave_request_decide.py:263-281` `_submit` precedent). The read-only
      calendar rows need no balances (the 3.1 precedent is read-only). Hitting the 500
      and "fixing" it in `_decide` would violate Landmine 7.
- [x] **AC1 exactness:** in-range call returns ONLY `manager_m`'s reports' PENDING+APPROVED
      rows — REJECTED/CANCELLED absent, `other_report` absent, the Manager's own leave
      absent (REPORTS excludes self — pinned by
      `tests/integration/test_leave_request_decide.py:602`, re-held by
      `test_leave_request_history.py:469`), `total` exact.
- [x] **Overlap boundaries:** straddlers at both edges included; the ends-day-before row
      excluded; one-sided `date_from` alone and `date_to` alone work; inverted range →
      200, `items == []`, `total == 0`; cross-year straddler returned for a range spanning
      Dec 31.
- [x] **Deactivated report's leave is IN** (Open Decision #3) — `r4`'s row present.
- [x] **Role gate (Landmine 4):** parametrized `admin` + `employee` → 403, envelope
      `{code, message, details}`, `code == vocabulary.ACTION_NOT_PERMITTED`,
      `details == {}`.
- [x] **Exact key-set pin:** `set(item) ==` the ten `LeaveRequestResponse` keys
      (`id, employee_id, employee_name, leave_type_id, leave_type_code, leave_type_name,
      start_date, end_date, leave_days, status`) — accidental widening fails the build.
- [x] **AC5 / AD-18 non-vacuous:** seed a row whose stored `leave_days` (e.g. `99`)
      provably disagrees with any recomputation of its short range; assert the response
      carries `99` verbatim.
- [x] **AC4 (Landmine 7):** with `r1`+`r2` APPROVED across a date, POST the decide
      endpoint approving `r3`'s overlapping PENDING request → plain 200, request
      APPROVED, response keys identical to the pre-story decide response (no warning
      field, no acknowledgement round-trip).
- [x] **Envelope + clamp:** `items/page/page_size/total`; `?page_size=200` → `page_size == 100`.

### Task 5 — Frontend API layer: `src/api/calendar.ts` (AC2, AC3)

- [x] `CALENDAR_QUERY_KEY = ['calendar'] as const`;
      `useCalendar({ dateFrom, dateTo, page?, pageSize? }, options?: { enabled? })` —
      wire names `date_from`/`date_to`/`page`/`page_size`, EVERY value through
      `encodeURIComponent` (2.7 review rule), `queryKey: [...CALENDAR_QUERY_KEY, params]`,
      `queryFn: () => apiFetch<Page<LeaveRequest>>(path)`. Reuse the `LeaveRequest` type
      from `./leaveRequests` and `Page` from `./departments` — the wire shape IS
      `LeaveRequestResponse` (Open Decision #1); do not redeclare either.
- [x] Add `CALENDAR_QUERY_KEY` to `invalidateAfterDecision`'s fan-out in
      `api/leaveRequests.ts` (onSettled — Landmine 6).
- [x] Export hook/key/types through the `api/index.ts` barrel (paired `export {}` /
      `export type {}` blocks — features import only from the barrel).

### Task 6 — Frontend: the inline decision calendar (AC2, AC3, AC4)

- [x] New `src/features/leave/DecisionCalendar.tsx` — same feature dir as
      `ManagerQueuePanel` (its only caller; `components/` promotion waits for a second
      caller — the Pager/RecalculationSummaryPanel rule). Props:
      `{ requestId, dateFrom, dateTo, enabled }`.
- [x] Render it inside each pending row of `ManagerQueuePanel` (:90-121), below
      `emp-summary` — the queue rows ARE the approval screen, so the calendar for the
      request's dates is "presented inline on the same screen" with no extra click (AC3,
      UJ-2). It fetches `useCalendar({ dateFrom: request.start_date, dateTo:
      request.end_date }, { enabled: isManager })` — the queue is PENDING-only and paged,
      so the per-row query count is bounded.
- [x] **Exclude the request under decision by `id` equality** (Open Decision #5) — it
      necessarily matches its own overlap window; the remaining entries are "also away."
      Empty remainder renders an explicit "No other leave overlaps these dates." state
      (the loading/error/empty triad is mandatory — 2.5 review patch; template
      `MyLeaveHistoryPanel.tsx:173-199`).
- [x] Each entry: `employee_name`, `start_date`–`end_date`, `leave_days`, and the status
      word rendered verbatim — the APPROVED/PENDING text label IS the visual distinction
      (Open Decision #6; reuse `emp-*` classes + `.muted`; adding CSS is sanctioned but
      declared — see the decision).
- [x] **No date arithmetic of any kind.** Render `start_date`/`end_date`/`leave_days`
      exactly as the server sent them (AD-2, AD-18). `getDay`/`getUTCDay` anywhere in
      `frontend/src` — **including comments** — fails
      `test_frontend_no_client_day_count.py` (tripped 2.5 AND 2.7 first drafts; a
      calendar story is this trap's natural habitat). Filtering by `id ===` and
      `Math.ceil` pager arithmetic are fine; weekday/holiday math is not.
- [x] No new dependency, no date-picker, no grid library.

### Task 7 — Guards and verification (all ACs)

- [x] Measure the real baseline first (Landmine 8), then full backend `pytest` — baseline
      + this story's tests, 0 skipped.
- [x] `alembic check` clean (no model change); import-linter **7/7 byte-identical**
      (`pyproject.toml` untouched); `git status` shows ZERO guard files in the diff.
- [x] Frontend `npm run build` (tsc + vite) + `npm run lint` (oxlint) clean. State
      plainly in the Dev Agent Record: there is STILL no frontend test runner
      (`package.json`: dev/build/lint/preview only) — AC2/AC3's rendering and AC4's
      no-warning UI are verified by build + lint + the backend day-count guard scan + code
      reading, and by nothing else.

### Review Findings (code review 2026-07-15)

- [x] [Review][Patch] `DecisionCalendar` fetches `/calendar` with no `page`/`page_size` and ignores `total` — the server default (50 rows) silently truncates the overlap list, and if the request-under-decision falls past page 1 the `id !== requestId` exclusion never fires, so it lists itself as its own overlap. Request the max page size and surface "and N more" from `total` [frontend/src/features/leave/DecisionCalendar.tsx:38-43] — FIXED 2026-07-15: requests `page_size=100` (the server MAX) and renders "…and N more overlap these dates" from `total`
- [x] [Review][Patch] The repository accepts `status` and `statuses` together and silently ANDs them into a contradiction — the docstring's "callers pass one or the other" contract is unenforced; raise on both [backend/app/repositories/leave_request.py:206-209] — FIXED 2026-07-15: raises `ValueError` when both are passed
- [x] [Review][Defer] One `DecisionCalendar` per queue row is a 1+N request fan-out (51 GETs on a full page) and `invalidateAfterDecision` refetches every window on each decision [frontend/src/features/leave/ManagerQueuePanel.tsx] — deferred, spec-conformant design (AC2 orders the calendar inline per pending row); revisit only with a measured problem

## Dev Notes

### The one-paragraph mental model

A calendar here is not a new data shape — it is the leave-request list read, already
scoped, already overlap-filtered, already AD-18-safe, restricted to the two statuses that
mean "away or maybe away" and mounted behind the one role that owns a reporting edge. The
backend is Task 1's one predicate plus two thin files that pin decisions the artifacts
already made. The substance — and the reason this story exists — is frontend: putting that
read INSIDE the decision moment (UJ-2), keeping it fresh across decisions (Landmine 6),
and adding precisely nothing to the decision itself (Landmine 7).

### What is already true, and must stay true

- **Overlap semantics** are pinned and inherited downstream (4.2's CSV export): reuse,
  never re-derive (Landmine 5).
- **REPORTS excludes the Manager's own row** — `manager_id == actor.id` cannot match self;
  3.1 pinned it (:602 invariant). FR-18 says Direct Reports; the Manager's own leave does
  NOT appear. Do not "fix" this.
- **No is_active filter on the REPORTS predicate** — 3.2 Landmine 1's decision, inherited
  here (Open Decision #3).
- **`leave_days` is read from `_READ_COLUMNS` verbatim** — the AD-18 chain (spine :169-173
  names the calendar explicitly: "Every read path — history, dashboard, **calendar**,
  export — reads the stored value and never recomputes it").
- **`MAX_PAGE`/`MAX_PAGE_SIZE` clamps** (3.1 Open Decision #5) protect this endpoint for
  free through `PageParams` — touch nothing in `pagination.py`.
- **403 is already mapped; 404 stays reserved for scope misses on identifier endpoints** —
  this endpoint has no identifier, so AD-10's 404 never arises here.

### Reuse map — DO NOT reinvent these

| Instead of writing… | Reuse |
|---|---|
| A calendar repo query | `list_leave_requests` + Task 1's `statuses` param |
| A view/mapper | `LeaveRequestView` + `row_to_view` (promoted from `_row_to_view`) |
| A response model | `LeaveRequestResponse` + `to_leave_request_response` (promoted) |
| A Manager-only route skeleton | `api/v1/team.py:70-89` |
| A read-only service skeleton | `services/team.py:35-47` |
| A world fixture + teardown | `tests/integration/test_team.py:63-171` |
| A 403 both-roles test | `test_team.py:226-242` / `test_role_gate.py:149-169` |
| A frontend hook | `api/team.ts:43-60` + `api/leaveRequests.ts:174-191` |
| A gated panel + triad | `ManagerQueuePanel.tsx:46-57`, `MyLeaveHistoryPanel.tsx:173-199` |

### Gotchas this codebase has actually produced (relevant subset)

- Unregistered router → every test 404s and even the no-token case "fails red" (3.2).
- `import app.main` missing from a test file → routes unregistered → false green (2.9).
- `getDay` token in a COMMENT tripping the day-count scan (2.5, 2.7).
- Query params unencoded (2.7 review patch) — encode dates too.
- onSuccess instead of onSettled → failed decision never refetches (2.7 review patch).
- Filtering on a JOINED column → count/page divergence, `total` lies (3.1).
- Shared mutation object's error attributed to the wrong row
  (`ManagerQueuePanel.tsx:61` patch) — if DecisionCalendar surfaces per-row fetch errors,
  keep them per-row.

### Project Structure Notes

- New: `backend/app/api/v1/calendar.py`, `backend/app/services/calendar.py`,
  `backend/tests/integration/test_calendar.py`, `frontend/src/api/calendar.ts`,
  `frontend/src/features/leave/DecisionCalendar.tsx`.
- Modified: `backend/app/repositories/leave_request.py` (Task 1),
  `backend/app/services/leave_requests.py` (mapper promotion only),
  `backend/app/api/v1/leave_requests.py` (projection promotion only),
  `backend/app/api/v1/router.py` (two lines),
  `frontend/src/api/leaveRequests.ts` (fan-out + reused type export),
  `frontend/src/api/index.ts` (barrel), `frontend/src/features/leave/ManagerQueuePanel.tsx`
  (mount DecisionCalendar).
- NOT modified: `main.py`, `domain/vocabulary.py`, `alembic/` anything, `pagination.py`,
  any guard test, `pyproject.toml`, `App.tsx` (the calendar mounts inside the existing
  queue panel; no new top-level panel — AC3 puts it on the approval screen, not beside it).
- Naming: plural/kebab paths, `verb_noun` functions, module docstrings name their FR (SM-6).

### References

- epics.md:1478-1505 (Story 3.3 ACs); :1403-1407 (Epic 3 preamble — FR-18 exists so BR-06
  is an informed choice); :463-476 (Epic 3 notes — AD-18/AD-10 govern every read here)
- prd.md:377-381 (FR-18 + consequences: Approved+Pending distinguished, reports only,
  inline on approval screen, never prevents approval); :68-71 (UJ-2 — "the overlap is
  visible at the moment of decision, not discovered the following week"); :493 (DR-15 —
  "The system informs; it never blocks."); :554-558 (§7.4 — no charts/trend lines); :585
  (NFR-11); :596 (NFR-18)
- api-contracts.md:233 (§4.9 — `GET /calendar | Manager | reports | FR-18`); :237
  ("`/calendar` distinguishes Approved from Pending leave visually and never blocks an
  approval"); :39-44 (G3 403-vs-404 + envelope); :50 (pagination convention); :106 (scope
  vocabulary)
- ARCHITECTURE-SPINE.md:401 (FR-18 → `api/v1/calendar`, governed by AD-10 + AD-18);
  :169-173 (AD-18 names the calendar read path); :211-213 (layering + pagination binds
  every list endpoint)
- erd.md:380 (§4.4 — `leave_request (start_date, end_date)` index exists FOR the
  Department Leave Calendar); :225 (the four statuses)
- Story 3-1 file (overlap decision + boundary tests, MAX_PAGE, repo-insert seeding,
  no-year-predicate rule); Story 3-2 file (Manager-only inversion, service-owns-Scope,
  world fixture, red-green, exact-key-set pin); Story 2-7 file (decide path, queue panel,
  onSettled)
- deferred-work.md:75 (AD-6 submit gap — Open Decision #7 below); :58-76 (page-1-only
  history — why the calendar still paginates properly)

## Open Decisions

Seven. #1 and #6 are the genuinely under-determined ones — no artifact fixes the wire
shape or the visual form; everything else is inherited and cited.

1. **Response shape — RECOMMENDED: reuse `LeaveRequestResponse`, byte-for-byte, pinned by
   the exact-key-set test.** api-contracts §5 defers response schemas to the code, so this
   is ours to fix. The disclosure analysis that drove 3.2's minimal shape cuts the OTHER
   way here: a Manager already reads every one of these ten fields for these exact rows
   via `GET /leave-requests` (scope REPORTS) — a narrower calendar shape would be a second
   projection to maintain with zero disclosure gained, and `employee_name` is the field
   that answers "who else is away." Nothing wider (no email, no role, no is_active — the
   ten keys only), pinned in the test so the decision stays made.
2. **Scope — RECOMMENDED: hardcode `Scope.REPORTS` in `services/calendar.py`** (the 3.2
   precedent), not delegation through `_scope_for_role`. FR-18 grants exactly one scope;
   route-gate + hardcoded scope means a future change to either cannot silently widen the
   read. The route gate alone would make role-resolution equivalent today — the hardcode
   is the belt-and-braces the spine's per-surface-authority posture asks for.
3. **A deactivated Direct Report's leave — RECOMMENDED: IN the calendar.** The REPORTS
   predicate carries no `is_active` filter (3.2 Landmine 1's settled decision), FR-18
   states no exclusion, and excluding would add a predicate no requirement grants. Their
   approved absence is still a fact about the team's dates. Pinned by the `r4` test.
   (`LeaveRequestResponse` carries no `is_active`, and FR-18 does not ask the calendar to
   flag it — FR-19's flagging lives on `/team`.)
4. **No `status` query param on `/calendar` — RECOMMENDED: the PENDING+APPROVED set is
   fixed server-side.** FR-18 defines the calendar as "Approved and Pending"; Cancelled
   and Rejected leave is deliberately NOT on it (contrast FR-20's history, which includes
   them). A client wanting other slices has `GET /leave-requests`. This also keeps every
   status name out of `api/` entirely (Landmine 2).
5. **The request under decision appears in its own calendar — RECOMMENDED: no backend
   marker; the frontend excludes it by `id`.** The pending request necessarily satisfies
   its own overlap window, and that is correct data (AC1's "leave of their Direct Reports
   across that range" includes it). A backend "this is the one you're deciding" flag would
   be per-caller state in a cacheable read. `id === request.id` in DecisionCalendar is
   zero-risk (no date math) and keeps the endpoint context-free.
6. **Visual form — RECOMMENDED: a list of overlap rows, not a day-grid; the status word is
   the distinction; new CSS only if declared.** FR-18 fixes the facts (Approved+Pending,
   distinguished, reports only) and the place (inline on the approval screen), not the
   form; §7.4 forbids charts. A 7-column day-grid means net-new CSS (the app has none for
   it), client-side date iteration flirting with the day-count guard, and responsive risk
   (NFR-18) — for zero additional information over "who, which dates, how many days,
   which status." Rendering the server's status string per row distinguishes Approved
   from Pending textually — and every prior story shipped zero new CSS. If the dev judges
   a stronger visual cue warranted, a minimal status-badge class is sanctioned but must be
   declared in the Dev Agent Record as the app's FIRST story-added CSS.
7. **Carried forward, NOT this story's to fix: the AD-6 submit gap** (2.11 #8 → 2.12 #11 →
   3.1 #6 → 3.2 #4; deferred-work.md:75 — "it now ships unless Epic 3 picks it up").
   This story is read-only over `leave_request` plus a frontend surface; it never reaches
   `submit_leave_request`. Adopting the fix here would be the silent scope-widening four
   stories have now declined. Restated so it does not lapse — and note the runway: **3.4
   (notifications, which hooks the very transitions in `services/leave_requests`) is the
   named forcing point, and 3.5 closes the epic.** An Epic 3 story that reaches the
   submit path must make the call, or the epic ends with it shipped.

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) via Claude Code dev-story workflow, 2026-07-14.

### Debug Log References

- Baseline measured FIRST (Landmine 8): full backend pytest on the 3.1+3.2 uncommitted tree
  atop `4fc1629` = **522 passed, 0 skipped** — the story's stated baseline held exactly this
  time (3.2's undercount did not recur).
- Red-green honored: the test file was written first and all 13 tests failed **404** against
  the unregistered path (verified: `{"detail":"Not Found"}` on `/api/v1/calendar`), then
  Tasks 1–3 were implemented and all 13 went green **with zero test edits**.
- ⚠️ ONE DEVIATION, declared: the story names the test file `tests/integration/test_calendar.py`,
  but `tests/domain/test_calendar.py` (Story 2.3's pure day-count tests) already owns that
  basename, and the test tree has no `__init__.py` packages — the duplicate basename is a
  pytest "import file mismatch" collection error that aborts the WHOLE suite (it surfaced on
  the first full-suite run; the file passed standalone). Renamed to
  `tests/integration/test_department_calendar.py`; the file's module docstring records the
  same rationale. Renaming 2.3's pinned file was not an option.

### Completion Notes List

- **All 5 ACs met, plus the binding §4.9 inversion.** Backend delta is exactly what the story
  mapped: ONE keyword-only `statuses` param on the existing `list_leave_requests` (the app's
  first status-SET predicate, a local column so page and count agree), a thin read-only
  `services/calendar.py` (hardcoded `Scope.REPORTS` per Open Decision #2; `CALENDAR_STATUSES =
  (PENDING, APPROVED)` fixed server-side per Open Decision #4 — no status name anywhere in
  `api/`), and `api/v1/calendar.py` reusing `LeaveRequestResponse` byte-for-byte (Open
  Decision #1, pinned by the exact-ten-key test) + two-line router registration.
- **AC4 (Landmine 7) held as a zero-diff assertion**: `services/leave_requests.py::_decide`
  and every decision endpoint are byte-untouched (the only `services/leave_requests.py` change
  is the `_row_to_view` → `row_to_view` promotion the story itself ordered); the AC4 test
  approves a third report's PENDING request into a two-report APPROVED overlap through the
  REAL endpoint → plain 200, response keys exactly the pre-story ten, request APPROVED, and
  the calendar reads back the new status.
- **The AC4 fixture trap was avoided as instructed**: `r3`'s PENDING request (the one approved
  through the real endpoint) got a seeded `leave_balance` row with `reserved == leave_days`
  and the composition CHECK satisfied — all other calendar rows are read-only repo-level
  inserts needing no balance and writing no audit rows (SM-4 undisturbed; the one audit row
  AC4's approve writes is cleaned up via `owner_engine`, the 2.9 convention).
- Open Decisions #1–#6 adopted as recommended: #1 reuse `LeaveRequestResponse` (exact-key-set
  pinned); #2 hardcoded `Scope.REPORTS` in the service; #3 deactivated report's leave IN
  (pinned by the `r4` test); #4 no status query param; #5 frontend excludes the request under
  decision by `id ===` (no backend marker); #6 list rows with the status word as the visual
  distinction — **zero new CSS added** (reused `emp-*`/`.muted`), no day-grid, no charts, no
  new dependency. #7 (the AD-6 submit gap) NOT adopted, restated: this story is read-only over
  `leave_request` and never reaches `submit_leave_request`; **3.4's transition hook remains
  the named forcing point, and 3.5 closes the epic** — an Epic 3 story that reaches the submit
  path must make the call, or the epic ends with it shipped.
- Frontend: `api/calendar.ts` (`useCalendar` — wire names `date_from`/`date_to`/`page`/
  `page_size`, every value `encodeURIComponent`-escaped, whole params object in the query key;
  reuses the `LeaveRequest` type and `Page<T>` — type-only imports, so no runtime cycle with
  `leaveRequests.ts`'s value import of `CALENDAR_QUERY_KEY`); `CALENDAR_QUERY_KEY` joined
  `invalidateAfterDecision`'s fan-out (onSettled in all three decision mutations — Landmine 6);
  `DecisionCalendar.tsx` mounted inside EACH pending `ManagerQueuePanel` row below
  `emp-summary` (AC3/UJ-2 — the queue rows ARE the approval screen), with the mandatory
  loading/error/empty triad ("No other leave overlaps these dates."), per-row error containment,
  and NO date arithmetic of any kind (the day-count guard scan is clean, comments included).
- **Verification**: backend pytest **537 passed, 0 skipped** — 522 baseline + 13 new tests
  + 2 cases `test_vocabulary_literals.py` auto-generates per new `app/` module (it
  parametrizes its AST scan over every module; `app/services/calendar.py` and
  `app/api/v1/calendar.py` each added one, both passing — verified by collecting with and
  without this story's files, so the arithmetic is explained, not hand-waved);
  import-linter **7/7 KEPT** (`pyproject.toml` untouched); `alembic check` clean (no model
  change, no migration); frontend `npm run build` (tsc + vite) and `npm run lint` (oxlint)
  clean; ZERO guard files in this story's diff (`main.py`, `domain/vocabulary.py`, `alembic/`,
  `pagination.py`, `test_scope_matrix.py`, `test_scoped_getters.py`, `pyproject.toml`,
  `App.tsx` all untouched by 3.3 — the pre-existing working-tree modifications are 3.1/3.2's
  review-state work, built on top, not reverted, not committed).
- ⚠️ Stated plainly (Task 7): there is STILL no frontend test runner (`package.json`:
  dev/build/lint/preview only) — AC2/AC3's rendering and AC4's no-warning UI are verified by
  build + lint + the backend day-count guard scan + code reading, and by nothing else.

### File List

New:
- `backend/app/services/calendar.py`
- `backend/app/api/v1/calendar.py`
- `backend/tests/integration/test_department_calendar.py` (deviation from the story's
  `test_calendar.py` name — basename collision with `tests/domain/test_calendar.py`; declared
  above and in the file's docstring)
- `frontend/src/api/calendar.ts`
- `frontend/src/features/leave/DecisionCalendar.tsx`

Modified:
- `backend/app/repositories/leave_request.py` (Task 1: keyword-only `statuses` param +
  docstring)
- `backend/app/services/leave_requests.py` (mapper promotion only: `_row_to_view` →
  `row_to_view`, 3 same-module call sites renamed, docstring notes the second caller)
- `backend/app/api/v1/leave_requests.py` (projection promotion only:
  `_to_leave_request_response` → `to_leave_request_response`, 5 same-module call sites
  renamed, docstring notes the reuse)
- `backend/app/api/v1/router.py` (two lines: import + `include_router`)
- `frontend/src/api/leaveRequests.ts` (CALENDAR_QUERY_KEY added to
  `invalidateAfterDecision`'s fan-out)
- `frontend/src/api/index.ts` (barrel: `CALENDAR_QUERY_KEY`, `useCalendar`,
  `CalendarParams`)
- `frontend/src/features/leave/ManagerQueuePanel.tsx` (mount `DecisionCalendar` inside each
  pending row)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status transitions)
- `_bmad-output/implementation-artifacts/3-3-the-department-leave-calendar-at-the-moment-of-decision.md`
  (this file: checkboxes, Dev Agent Record, File List, Change Log, Status)

## Change Log

- 2026-07-14: Story created by create-story workflow (ultimate context engine). Status: ready-for-dev.
- 2026-07-14: Implemented by dev-story (Claude Fable 5). All 7 tasks complete, all 5 ACs +
  the §4.9 Manager-only contract verified by 13 new integration tests (red-first, green with
  no test edits). One declared deviation: test file named `test_department_calendar.py`
  (pytest basename collision with 2.3's `tests/domain/test_calendar.py`). Backend 537 passed,
  0 skipped (522 baseline + 13 new + 2 auto-generated vocabulary-scan cases over the two new
  modules), import-linter 7/7, alembic check clean, frontend build+lint clean, zero guard
  files touched. Status: review.
