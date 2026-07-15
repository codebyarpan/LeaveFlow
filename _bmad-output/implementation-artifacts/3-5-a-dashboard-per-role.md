---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

# Story 3.5: A Dashboard per Role

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user of any role,
I want a dashboard scoped to what I can act on,
So that the first screen I see answers the question my role actually asks.

## Acceptance Criteria

Verbatim from `_bmad-output/planning-artifacts/epics.md:1547-1580`. Numbering is this story's.

**AC1 — the Employee dashboard**
**Given** an authenticated Employee
**When** they call `GET /api/v1/dashboard/employee`
**Then** the response presents, per Leave Type, Available, Reserved and Consumed, plus a count of their Pending requests (`FR-11`)

**AC2 — the Manager dashboard**
**Given** an authenticated Manager
**When** they call `GET /api/v1/dashboard/manager`
**Then** the response presents a count of Leave Requests awaiting their decision, and their Direct Reports on approved leave within the next seven days (`FR-11`, `AD-10`)

**AC3 — the Admin dashboard**
**Given** an authenticated Admin
**When** they call `GET /api/v1/dashboard/admin`
**Then** the response presents organization-wide totals: Employees on approved leave today, and the Pending request count (`FR-11`)

**AC4 — the date-range filter**
**Given** any dashboard endpoint and a `date_from` and `date_to`
**When** the figures are computed
**Then** they are those falling inside the selected range (`FR-11`, api-contracts §4.9)

**AC5 — the mixed gate**
**Given** a Manager calling `GET /api/v1/dashboard/employee`
**When** the response returns
**Then** it carries their own balances, not their reports'
**And** an Employee calling `GET /api/v1/dashboard/manager` receives `403` with code `ACTION_NOT_PERMITTED` (`FR-11`, `FR-03`, `G3`)

**AC6 — the React dashboards**
**Given** the React application
**When** any dashboard renders
**Then** it presents summary cards with a date-range filter
**And** it presents no chart and no trend line, which are out of scope (PRD §7.4, `SM-C2`)
**And** it is usable at desktop and tablet widths (`NFR-18`)

---

## Tasks / Subtasks

### Task 0 — Measure the baseline BEFORE writing a line (Landmine 12)

- [x] `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` — record the **passed** count in the Dev Agent Record.
  - The tree currently **collects 561** (measured 2026-07-14). Story 3.3 recorded 537; 3.4 landed +24 and is **still `in-progress`**, so this number is a moving target and **any figure written in this file is a guess**. 3.2 predicted 512 and measured 514. **Measure. Never assume.**
  - Integration tests `pytest.skip` if PostgreSQL is unreachable — `docker compose up -d` first, then `docker compose exec api alembic upgrade head`.
- [x] Confirm the four build guards are green *before* you start, so a later failure is provably yours: `lint-imports` (7/7), `alembic check` (clean), `npm run build`, `npm run lint`.

### Task 1 — `app/repositories/dashboard.py` — the scoped aggregates (AC1, AC2, AC3; Decisions #3, #4)

- [x] Create the module. Docstring names FR-11 and AD-10 (SM-6), and states why it exists rather than living in `repositories/leave_request.py` — that module's public surface is **hard-pinned by name** at `tests/integration/test_leave_request_submit.py:535-635` and an addition there fails the build. `ARCHITECTURE-SPINE.md:394` sanctions this module by name: *"FR-11 Dashboards | `api/v1/dashboard`, **scoped repository aggregates** | AD-10, AD-16"*.
- [x] `count_leave_requests(session, actor, *, scope, status, date_from, date_to) -> int` — `COUNT(*)` over `leave_request`, joined to `employee` for the scope predicate, filtered by `status` and the overlap window.
- [x] `count_employees_on_leave(session, actor, *, scope, status, date_from, date_to) -> int` — **`COUNT(DISTINCT leave_request.employee_id)`**. See Landmine 1: this is NOT the same number as `count_leave_requests`.
- [x] `list_employees_on_leave(session, actor, *, scope, status, date_from, date_to, limit) -> list[Row]` — **DISTINCT** `(employee_id, full_name)`, ordered by `full_name`, `LIMIT :limit`. Returns plain columns, not the ORM entity. **`limit` is passed IN by the caller** — see Landmine 14.
- [x] Every function takes `actor` and applies `employee_scope_predicate(scope, actor)` **in the SQL** (AD-10, NFR-04). The two `count_*` names sit outside `test_scoped_getters.py`'s `_READ_VERB_PREFIXES` (`tests/test_scoped_getters.py:146`) — they take `actor` **anyway, for correctness rather than to satisfy a guard** (the `repositories/notification.py:161` `count_unread` precedent, quoted). `list_employees_on_leave` **is** a `list_` getter and **must** take `actor` or the guard fails.
- [x] **Do NOT add anything to `tests/test_scoped_getters.py`'s `EXEMPT`.** An untouched `EXEMPT` frozenset is the tell you did it right (3.4's rule).
- [x] 🚨 **Every aggregate here JOINs `Employee` — and the "house COUNT idiom" is the WRONG one to copy.** The scope predicate is a predicate over the **`Employee`** table (`repositories/scoping.py:59-75` — `Employee.manager_id == actor.id`), *not* over `LeaveRequest`. All 14 bare `select(func.count()).select_from(M).where(...)` sites are **single-table** counts whose predicates are on that same table. Copy them here and you emit `SELECT count(*) FROM leave_request, employee WHERE employee.manager_id = …` — an implicit **CARTESIAN PRODUCT**. SQLAlchemy 2.x raises only a `SAWarning`, **not an error**, so a wildly inflated number **ships green**.
  The one **joined**-count precedent in the codebase is `repositories/leave_request.py:228-236` — copy *that*:
  ```python
  total = (
      session.scalar(
          select(func.count())
          .select_from(LeaveRequest)
          .join(Employee, LeaveRequest.employee_id == Employee.id)
          .where(*conditions)
      )
      or 0
  )
  ```
  Join **unconditionally**, for all three scopes: under `Scope.ALL` the predicate is `true()` and the join is a harmless no-op (the FK guarantees no row is dropped), so one code path serves SELF, REPORTS and ALL.
- [x] **The DISTINCT forms — there is NO prior art in `app/` for these** (`grep -rn "distinct" app/` returns only docstring prose; `distinct` is imported and called nowhere). This is the story's one genuinely new query shape, so the form is given here rather than left to invention:
  ```python
  # count_employees_on_leave
  select(func.count(func.distinct(LeaveRequest.employee_id)))
      .select_from(LeaveRequest)
      .join(Employee, LeaveRequest.employee_id == Employee.id)
      .where(*conditions)

  # list_employees_on_leave
  select(LeaveRequest.employee_id, Employee.full_name)
      .select_from(LeaveRequest)
      .join(Employee, LeaveRequest.employee_id == Employee.id)
      .where(*conditions)
      .distinct()
      .order_by(Employee.full_name)
      .limit(limit)
  ```
  `DISTINCT` is over the two selected columns; `full_name` being **in the select list** is what makes the `ORDER BY` legal under `SELECT DISTINCT`. (`Employee.full_name` — `repositories/models.py:85`.)

### Task 2 — `app/services/dashboard.py` — the three read services (AC1–AC5; Decisions #1, #2, #6)

- [x] Create the module. Read-only, the `services/calendar.py` / `services/team.py` shape: **one read session, opened, queried, closed, never committed.** A commit on a read path is how a read quietly becomes a write (the 2.5 precedent).
- [x] `_today() -> datetime.date` — `datetime.date.today()`. The clock lives in the shell, never in `domain/` (AD-1); this mirrors `services/leave_requests.py:240`, `services/cancellation.py:146`, `services/recalculation.py:127`.
- [x] **`DASHBOARD_STATUSES`-style constants**: the leave-presence figures read `vocabulary.STATUS_APPROVED`; the queue figures read `vocabulary.STATUS_PENDING`. Fixed **server-side**, exactly as `CALENDAR_STATUSES` is (`services/calendar.py:46-49`) — no status query param, so no status name ever appears in `api/`.
- [x] `_effective_window(date_from, date_to, *, default_from, default_to)` — implements **Decision #1**: if **both** params are absent, the FR-11 default window applies; if **either** is supplied, the supplied predicates apply verbatim and the default is not used (an absent side applies no predicate — the settled 3.1/3.3 rule).
- [x] `employee_dashboard(actor, date_from, date_to) -> EmployeeDashboardView`
  - Balances: call **`balance_reads.list_own_balances(actor)`** — do not re-read `leave_balance`. **Balances are NOT date-filtered** (Decision #2 / Landmine 3). *(A `services → services` import is legal: contract 1 is a `layers` contract and intra-layer imports are unconstrained. Precedents: `services/calendar.py:42` imports from `services/leave_requests.py`; `services/balance_reads.py:34` imports `services/authorization.py`.)*
  - `leave_year`: **`_today().year`** (DR-8 — the Leave Year *is* the calendar year, `erd.md:209`). 🚨 **`BalanceView` does not carry the year** — it has exactly five fields (`services/balance_reads.py:37-51`), and the year lives only in that module's **private** `_current_leave_year()` (`:53-55`). **Do NOT import the private helper, and do NOT widen `balance_reads.py`** (that would break Task 4's "one existing backend file" invariant). Derive it from this service's own clock helper. Record in the Dev Agent Record that this is a **third** `date.today().year` site — a read-only restatement of DR-8, not a new rule. `deferred-work.md:42` already owns the year-rollover cliff all three share; **do not fix it here.**
  - Pending count: `dashboard_repo.count_leave_requests(scope=Scope.SELF, status=STATUS_PENDING, ...)`.
  - No default window (FR-11 attaches none to the Employee dashboard).
- [x] `manager_dashboard(actor, date_from, date_to, *, limit: int) -> ManagerDashboardView`
  - `Scope.REPORTS` **hardcoded here** (the `services/team.py` / `services/calendar.py` belt-and-braces precedent — `api/` may not import `Scope`, contract 2).
  - 🚨 **`limit` is a PARAMETER, supplied by the route** — not imported. See Landmine 14.
  - `pending_decision_count`: `count_leave_requests(scope=REPORTS, status=PENDING, <supplied range only>)`.
  - `reports_on_approved_leave`: `list_employees_on_leave(scope=REPORTS, status=APPROVED, <effective window>, limit=limit)`, default window `today .. today + 6` (**seven calendar days, inclusive of today**).
  - Echo the effective window back on the view (`leave_window_from` / `leave_window_to`) so the UI's card label is *derived*, never hard-coded (Decision #1). Both are **nullable** — a one-sided range leaves one end unbounded (Decision #1's stated consequence).
- [x] `admin_dashboard(actor, date_from, date_to) -> AdminDashboardView`
  - `Scope.ALL` hardcoded.
  - `employees_on_approved_leave`: `count_employees_on_leave(scope=ALL, status=APPROVED, <effective window>)`, default window `today .. today` (**"today"**).
  - `pending_request_count`: `count_leave_requests(scope=ALL, status=PENDING, <supplied range only>)` — **Leave Requests, NOT Cancellation Requests** (Landmine 5).
- [x] Frozen dataclass views, one per dashboard. **`available` is NOT computed here** — the three stored quantities travel up and `api/` derives it (DR-3, AD-5; the `BalanceView` contract at `services/balance_reads.py:37-51`).

### Task 3 — `app/api/v1/dashboard.py` — three routes, three different gates (AC1–AC5; Landmine 2)

- [x] Create the module with **three literal paths**. 🚨 **`GET /dashboard/{role}` is forbidden** — see Landmine 2.
- [x] `GET /dashboard/employee` → `caller: Actor = Depends(get_current_employee)`. **Role `any`, scope `self`.** **NO `require_role`.** This is the `GET /balances` / `GET /notifications` shape. It can produce **no 403 and no 404**.
- [x] `GET /dashboard/manager` → `manager: Actor = Depends(require_role(authz.ROLE_MANAGER))`. **An ADMIN is refused too** (Landmine 4).
- [x] `GET /dashboard/admin` → `admin: Actor = Depends(require_role(authz.ROLE_ADMIN))`.
- [x] 🚨 **The route supplies the list cap, because `services/` cannot import it.** In `api/v1/dashboard.py`: `from app.api.v1.pagination import MAX_PAGE_SIZE`, then `dashboard_service.manager_dashboard(manager, date_from, date_to, limit=MAX_PAGE_SIZE)`. `pagination.py` lives in **`app.api`** — the top layer — so a `services → api` import breaks import-linter **contract 1** (`layers`) and `lint-imports` drops to 6/7. The bound is the route's to supply, exactly as `api/v1/team.py:83` hands `params.limit` down to `services/team.py:35`. See Landmine 14.
- [x] `date_from: datetime.date | None = Query(default=None)` and `date_to` likewise, on all three — copy `api/v1/calendar.py:50-51` verbatim. A malformed date is a **framework 422** via the `datetime.date` typing; **invent no error code** (the settled 3.1 posture).
- [x] Response models: `EmployeeDashboardResponse`, `ManagerDashboardResponse`, `AdminDashboardResponse` (shapes in Dev Notes → *The response shapes*). **Reuse `BalanceResponse` imported from `api/v1/balances.py`** — an `api → api` import, the `LeaveRequestResponse`-into-`calendar.py` precedent (`api/v1/calendar.py:39`). **Derive `available` at this projection** (`accrued − consumed − reserved`), never below.
- [x] Import roles via `from app.services import authorization as authz` — never `app.domain.vocabulary` (contract 2 + the literal scan).

### Task 4 — Register the router (one existing backend file, two lines)

- [x] `app/api/v1/router.py`: add `dashboard` to the alphabetical import tuple, and `api_v1_router.include_router(dashboard.router)` to the list. **This is the only edit to an existing backend file in the whole story.**

### Task 5 — `backend/tests/integration/test_dashboard.py` (AC1–AC5; red-green)

- [x] **Write the tests first, watch them 404, then implement** (the 3.3 discipline).
- [x] Filename: `test_dashboard.py`. ✅ Verified free — no `tests/domain/test_dashboard.py` exists. (3.3 was forced to rename to `test_department_calendar.py` because a duplicate basename in the packageless test tree is a pytest *"import file mismatch"* that **aborts the whole suite**. Check before you name.)
- [x] Module preamble, **exactly** as `test_team.py` / `test_department_calendar.py` open: `import app.main  # noqa: F401` **before** the `TestClient` import, or every route 404s against an empty app (a recorded false-green).
- [x] Build a per-file `_World` + `_Member`. **There is no top-level `tests/conftest.py`** — no shared client, and no role or token fixtures. **What DOES exist, and what your file inherits automatically, is `tests/integration/conftest.py`**: the session-scoped **`owner_engine`** (`:35-73` — the OWNER-role engine for teardown, AD-9) and **`db_connection`** (`:76-102`). It also owns the `pytest.skip` when PostgreSQL is unreachable, which is what makes Task 0's skip behaviour work. **Do not hand-roll either engine.** Everything else is yours to mint per-file: tokens via `security.create_token(str(employee.id), role)`; `_KNOWN_PASSWORD = "correct-horse-battery-staple"`; isolate with `suffix = uuid.uuid4().hex[:12]`.
- [x] 🚨 **Seed dates relative to `date.today()`, NOT `today.year + 1`** (Landmine 6). Seed rows via direct repository inserts (the `_insert_request` helper at `test_department_calendar.py:150-176`) — read-only rows need no balance and write no audit row, so **SM-4's exact ledger of 14 stays undisturbed**.
- [x] Tests to write, at minimum:
  - AC1: an Employee's per-type Available/Reserved/Consumed + Pending count. Pin the **exact key set** of the response and of each balance item (`assert set(body) == _EXPECTED_KEYS`) — accidental widening is a disclosure and must **fail the build** (the 3.2/3.3/3.4 house rule).
  - AC1: `available` is **derived** — reserve days and watch it drop (the `test_balances_read.py` precedent).
  - AC2: the Manager's `pending_decision_count` equals the number of PENDING requests from their reports, and **no other Manager's**. Name every exclusion one by one (the house convention for proving a scope predicate).
  - AC2: `reports_on_approved_leave` contains exactly the reports with an APPROVED request overlapping `today..today+6`, and a report whose approved leave starts on day 8 is **absent**. Boundary tests on both edges.
  - 🚨 AC2/AC3 **Landmine 1**: a report with **two** APPROVED requests overlapping the window appears **exactly once**, and the Admin's `employees_on_approved_leave` counts them **once**. This test is what proves the `DISTINCT` is real. Without it the story ships a double-count.
  - AC3: org-wide `employees_on_approved_leave` for `today`, and `pending_request_count`. 🚨 Seed a **PENDING Cancellation Request** and assert `pending_request_count` **does not move** (Landmine 5).
  - AC4: supplying `date_from`/`date_to` overrides the default window on all three dashboards; an **inverted range → `200` with zero figures**, not a 422 (the settled 3.1 semantics, zero code).
  - AC5: parametrized — `GET /dashboard/manager` refuses **`admin` AND `employee`**; `GET /dashboard/admin` refuses **`manager` AND `employee`**. Full envelope assert, four lines each:
    ```python
    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == vocabulary.ACTION_NOT_PERMITTED
    assert body["details"] == {}
    ```
  - AC5: a **Manager** calling `GET /dashboard/employee` gets **`200`** carrying **their own** balances — assert their own leave-type codes are present and a report's are absent.
  - `401` on an absent token (not 403) on all three.
  - **AD-18**: seed a request whose stored `leave_days` provably disagrees with any recomputation of its range (the `_STORED_DISAGREES = 99` over a 3-day range trick) and assert the dashboard never recomputes it. AD-18 **names the dashboard by name**.
  - **Write NO 404 test.** These routes have no path param; there is no id to miss on. See Landmine 2.
- [x] Teardown: owner-engine block, FK order `AuditEntry → Notification → LeaveRequest → LeaveBalance → (null manager_id) → Employee → LeaveType → Department`. Take `owner_engine` **iff** you delete audit/notification rows — a read-only story that seeds via direct inserts writes neither, so the simple `test_team.py:161-171` teardown may suffice. Verify, don't assume.

### Task 6 — `frontend/src/api/dashboard.ts` (AC6)

- [x] Three hooks: `useEmployeeDashboard(params)`, `useManagerDashboard(params, options)`, `useAdminDashboard(params, options)`. Query keys `EMPLOYEE_DASHBOARD_QUERY_KEY = ['dashboard','employee']` etc. (or one `DASHBOARD_QUERY_KEY = ['dashboard']` prefix with the role appended — a prefix invalidation then fans out to all three; **recommended**).
- [x] Build the query string with the canonical `FILTER_PARAM_NAMES` + `encodeURIComponent` form — copy `leaveRequests.ts:165-204` (the constant is named `FILTER_PARAM_NAMES`, `:166`).
- [x] `enabled:` gate the manager/admin hooks on role, exactly as `useCalendar`/`useTeam` do.
- [x] Types imported as `import type` — `verbatimModuleSyntax: true` makes a plain type import a **build failure**.
- [x] Export from the `src/api/index.ts` barrel (values, then `export type`). Features import from the barrel, never a file path.

### Task 7 — The invalidation fan-out and the sign-out purge (AC6; Landmine 9)

A dashboard's counts move on submit, on approve/reject/cancel, on an approved cancellation, and on a recalculation. Join **all four** — the house philosophy is stated at `frontend/src/api/recalculation.ts:79-82`: *"invalidating them anyway costs one refetch … and removes an entire class of 'which keys does THIS mutation move again?' bug. **Correctness over a saved request.**"*

- [x] `leaveRequests.ts:234-238` — add the dashboard key to `invalidateAfterDecision` (covers approve/reject/cancel, three mutations, one edit).
- [x] `leaveRequests.ts:108-117` — add it to `useSubmitLeaveRequest`'s `onSuccess`. **🚨 This is the one that gets missed** — submit does not go through `invalidateAfterDecision`; it has its own inline handler.
- [x] `cancellationRequests.ts:79-83` — add it to `invalidateAfterCancellation`.
- [x] `recalculation.ts:84-93` — add it to `invalidateEverythingARecalculationMoves`.
- [x] 🚨 **`App.tsx:222/227` (session-expiry) and `App.tsx:239/242` (fresh login)** — add the dashboard key to the `removeQueries` purge. A `['dashboard']` key carries **no per-user identity**, so on a shared browser the next user would see the **previous user's** counts and balances for up to `staleTime` (30s). That is a **genuine cross-user disclosure**, not cosmetic staleness — it is exactly why 3.4 purged `['notifications']` there (`App.tsx:224-227` says so in as many words).

### Task 8 — The three React dashboards (AC6; Decisions #5, #10)

- [x] **Extend `frontend/src/features/dashboard/DashboardPage.tsx`** — do **not** create a second employee dashboard beside it. It already exists (Story 2.4), is already titled *"My Leave Balances"*, is already mounted at `App.tsx:124`, and already renders per-Leave-Type Available/Reserved/Consumed. **It keeps its no-role-gate** — `/dashboard/employee` is role `any`, and a Manager must see their own balances there (AC5). Add: the Pending-request count card, the date-range filter, and the switch from `useBalances` to `useEmployeeDashboard`.
- [x] ⚠️ **After that switch, `useBalances` has ZERO callers** — `DashboardPage.tsx:26` was its only one. **Leave `src/api/balances.ts` exactly as it is; do not delete it and do not remove its barrel export.** An orphaned *export* is not a lint failure (`noUnusedLocals` governs locals), but `BALANCES_QUERY_KEY` is still invalidated from **three** modules (`leaveRequests.ts:109` and `:236`, `cancellationRequests.ts:82`, `recalculation.ts:88`) and `GET /employees/{id}/balances` still ships. "Tidying up" that file is a build break in three places.
- [x] New `features/dashboard/ManagerDashboardPanel.tsx` — self-gates `MANAGER`. New `features/dashboard/AdminDashboardPanel.tsx` — self-gates `ADMIN`. Both use the app's one gate idiom: `const me = useMe()` → `const isX = me.data?.role === X_ROLE` → **all hooks first** → `if (!isX) { return null }` (`react/rules-of-hooks` is `error` in `.oxlintrc.json`).
- [x] Mount both in `App.tsx`'s `AppShell` stack. **There is no router and 3.5 must not add one** — the spine deliberately defers that choice and every panel self-gates. Replace the "Signed in" placeholder paragraph at `App.tsx:99-111`, whose copy literally says *"a dashboard … arrive across Epics 2 and 3; this shell is what they render into."*
- [x] Date-range filter: copy `MyLeaveHistoryPanel.tsx:45-70, 88-93, 156-171` — the `''`→`undefined` translation (an empty field is an **absent wire param**, never `date_from=`), and `<input type="date">` which emits `YYYY-MM-DD`, the exact wire shape (AD-12).
- [x] 🚨 **The frontend sends NO dates by default.** The "next seven days" and "today" windows are computed **server-side**. The client must never compute `today + 7` — that duplicates a server decision and walks straight into the day-count guard scan (Landmine 8).
- [x] Loading / error / empty triad on every panel (the 2.5 review rule) — use `isLoading`, not `isPending`, on the `enabled`-gated queries.
- [x] **Zero new CSS** (Decision #10). Cards = `<div className="emp-fields">` (already `grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr))` at `index.css:316-320` — an intrinsically responsive card grid, **no media query needed**) containing **`<section className="panel">`** blocks, each holding a `.balance-available-value` for the figure (the big-number treatment, `index.css:453-457`).
  🚨 **Use `.panel`, not `.emp-field`.** `.emp-field` (`index.css:322-328`) is the *form's* label+input wrapper — `display:flex; flex-direction:column`, **no border, no background, no padding** — and renders as unstyled stacked text, not a card. `.panel` (`:80-90`) is the app's bordered card.
  **NFR-18 is already satisfied** by the existing `@media (max-width: 48rem)` at `index.css:119-136` plus `auto-fit` — 3.5 does **not** need the app's first media query.
- [x] **No chart. No trend line. No new dependency.** (PRD §7.4, SM-C2, AC6.)
- [x] Card labels for the leave-presence figures come from the response's echoed window, not a hard-coded "next 7 days" string (Decision #1).

### Task 9 — Verify, and state the frontend truth plainly (AC6)

- [x] `cd backend && .venv/bin/python -m pytest -q` — record passed/skipped. Explain the delta: `measured baseline + your new tests + 3` (one auto-generated `test_vocabulary_literals` case per new `app/**.py` file: `repositories/dashboard.py`, `services/dashboard.py`, `api/v1/dashboard.py`). **No migration → `test_migrations_insert_nothing` gains nothing.** Verify by collecting with and without the story's files, so the arithmetic is **explained, not assumed**.
- [x] `lint-imports` — must stay **7/7 byte-identical**. `alembic check` — must stay clean (drift means you touched a model).
- [x] `npm run build` (tsc + vite) and `npm run lint` (oxlint).
- [x] ⚠️ **State plainly in the Dev Agent Record: there is STILL no frontend test runner** (`package.json` has only `dev`/`build`/`lint`/`preview` — no vitest, no jest, no testing-library, zero `*.test.*` files). **AC6 is verified by tsc + vite build, oxlint, the backend day-count guard scan, and code reading — and by NOTHING ELSE.** Say so rather than implying coverage that does not exist.
- [x] Confirm and record: **zero guard files in the diff** — no `main.py`, no `vocabulary.py`, no `test_scope_matrix.py`, no `test_scoped_getters.py`, no `alembic/`, no `pyproject.toml`, no `index.css`.

### Task 10 — Housekeeping: strike two stale deferred-work entries (Decision #9)

- [x] `deferred-work.md:19` and `:58` both describe the unbounded-`page` → bigint-OFFSET → 500 bug. **Story 3.1 closed it** with `MAX_PAGE = 1_000_000` (`api/v1/pagination.py`). 3.1 said the entries were now stale and 3.4 authorized striking them; nobody has. Strike them, with a one-line note naming 3.1 as the closer.
- [x] Do **not** touch any other deferred-work entry. In particular, see Decision #8.

### Review Findings (code review 2026-07-15)

- [x] [Review][Patch] The Manager dashboard's headline "on approved leave" figure is a client-computed `reports.length` over a server-capped (`MAX_PAGE_SIZE`=100) list — silently wrong past the cap and a violation of the story's own "the client computes NOTHING" rule; `count_employees_on_leave` exists and is wired only to the Admin view. Add a server count field and render that [frontend/src/features/dashboard/ManagerDashboardPanel.tsx:120, backend/app/services/dashboard.py:204-221] — FIXED 2026-07-15: `reports_on_leave_count` (server `COUNT(DISTINCT …)`) added to view/response/wire type, rendered as the headline with an "…and N more" row when the list is capped; `_MANAGER_KEYS` pin updated and the count asserted
- [x] [Review][Patch] The session-expiry and login cache purges remove only ME/NOTIFICATIONS/DASHBOARD — `LEAVE_REQUESTS`, `TEAM`, `CALENDAR`, and `BALANCES` keys carry no per-user identity and survive a session switch on a shared browser: the exact cross-user disclosure the adjacent comments purge the other keys for [frontend/src/App.tsx:239-248, 260-266] — FIXED 2026-07-15: both sites now `queryClient.clear()`, closing the class (the per-key list had gone stale twice)
- [x] [Review][Patch] The dashboard clock is server-local `date.today()` while every other new module uses UTC `_now()`, and `employee_dashboard` reads the year twice across an unsynchronized boundary (`balance_reads.list_own_balances`'s private clock vs this module's `_today().year`) — near-midnight/New-Year responses can label year-N data as year-N+1 [backend/app/services/dashboard.py:114-117, 153-164] — FIXED 2026-07-15: `_today()` derives from UTC, the year is read once and passed into `list_own_balances(leave_year=…)`; `test_dashboard.py`'s `_TODAY` aligned to UTC
- [x] [Review][Patch] `employee_dashboard` assembles its figures from two separate sessions (`balance_reads` opens its own, then a second for the counts) — the response can be a snapshot that never existed; read both from one session [backend/app/services/dashboard.py:153] — FIXED 2026-07-15: `list_own_balances` accepts an optional `session` and the dashboard passes its own, so both figures come from one snapshot

---

## Dev Notes

### 🔴 Read this first: three-quarters of this story already exists

This is the last story of Epic 3 and it is mostly **assembly**. The single largest failure mode is rebuilding what is already shipped and tested.

| 3.5 needs | It already exists at | Do |
| --- | --- | --- |
| Per-Leave-Type Available/Reserved/Consumed | `services/balance_reads.list_own_balances(actor)`; `api/v1/balances.BalanceResponse` | **Call the service. Reuse the response model.** |
| `available` derived, never stored | `api/v1/balances.py:58-72` — derived at the projection | **Copy the derivation; never add a column** |
| The employee React dashboard | **`features/dashboard/DashboardPage.tsx`** — exists, titled "My Leave Balances", mounted at `App.tsx:124` | **Extend it. Do not create a second one.** |
| Date-range overlap semantics | `repositories/leave_request.list_leave_requests:212-215` — `end_date >= date_from AND start_date <= date_to`, each side optional | **Reuse the predicate. Do not re-derive it.** |
| The scope predicate | `repositories/scoping.employee_scope_predicate(scope, actor)` | **Compose it into every dashboard query** |
| The Manager-only role gate + its 403 test | `api/v1/team.py`, `api/v1/calendar.py`; `test_department_calendar.py:595-612` | **Copy verbatim** |
| The role-`any` self-scoped gate | `api/v1/balances.py:75-85`, `api/v1/notifications.py:114-128` | **Copy for `/dashboard/employee`** |
| A scalar-aggregate endpoint | `GET /notifications/unread-count` → `{"unread": int}`; `repositories/notification.count_unread` | **The closest structural precedent for a dashboard tile** |
| The `COUNT(*)` idiom | 14 unanimous sites: `session.scalar(select(func.count()).select_from(M).where(*c)) or 0` | **Use it** |
| A responsive card grid | `.emp-fields` — `index.css:316-320`, `auto-fit`/`minmax` | **Zero new CSS** |
| A big-number card figure | `.balance-available-value` — `index.css:453-457` | **Zero new CSS** |
| Tablet responsiveness (NFR-18) | `@media (max-width: 48rem)` — `index.css:119-136` | **Already satisfied** |
| A date-range filter UI | `MyLeaveHistoryPanel.tsx:45-70, 88-93, 156-171` | **Copy** |
| Pagination, if any list needs it | `components/Pager.tsx`, `api/v1/pagination.py` | Reuse — but see Decision #5 |

**What is genuinely new:** three routes, one service module, one repository module of scoped aggregates, two React panels, and **one number nobody has computed before — a DISTINCT count of Employees on leave.** That last one is the story's real engineering content (Landmine 1).

### The binding contract

`api-contracts.md:225-239`, §4.9, complete for our rows:

```
| Method | Path                  | Role    | Scope   | Realizes |
| GET    | /dashboard/employee   | any     | self    | FR-11    |
| GET    | /dashboard/manager    | Manager | reports | FR-11    |
| GET    | /dashboard/admin      | Admin   | all     | FR-11    |
```
> Every dashboard accepts `date_from` and `date_to` (`FR-11`). … A Manager requesting `/dashboard/employee` receives their own balances, not their reports'. An Employee requesting `/dashboard/manager` is refused (`FR-11`, `FR-03`).

**The response schemas are deliberately NOT fixed by any artifact.** `api-contracts.md:249-251` (§5, *What this document does not fix*): *"Per-endpoint request and response schemas … are owned by the code and published in the generated OpenAPI document at `/docs`. Fixing them twice would guarantee they diverge."* The shapes below are therefore **this story's to decide** — see *The response shapes*.

`FR-11` verbatim (`prd.md:358-371`) — the content list is binding:
> - The **Employee** dashboard presents, per **Leave Type**: **Available**, **Reserved**, and **Consumed**; plus a count of **Pending** requests.
> - The **Manager** dashboard presents a count of **Leave Requests** awaiting their decision, and their **Direct Reports** who are on approved leave within the next seven days.
> - The **Admin** dashboard presents organization-wide totals: **Employees** on approved leave today, and **Pending** request count.
> - Every dashboard supports a **date-range filter**; the figures presented are those falling inside the selected range.
> - A **Manager** requesting the Employee dashboard sees their own balances, not their reports'. An **Employee** requesting the Manager dashboard is refused (`FR-03`).

**SM-8** (`prd.md:638`): *"A requirement is counted as delivered only when a consequence from its FR is demonstrably exercised — **not when its endpoint exists**."* Ship **at least one passing test per FR-11 consequence above**.

---

## 🚨 Landmines

### Landmine 1 — "Employees on approved leave" is a DISTINCT count. A count of requests is the wrong number.

AC3 says *"**Employees** on approved leave today"*. AC2 says *"their **Direct Reports** on approved leave"*. **Both name people, not requests.**

Nothing forbids one Employee holding two APPROVED requests that overlap the same window — `deferred-work.md:50` records that submit has **no duplicate/overlapping-request guard**. So:

- `COUNT(*) FROM leave_request WHERE status='APPROVED' AND <overlap>` → **counts requests. Double-counts the Employee.**
- `COUNT(DISTINCT leave_request.employee_id)` → **counts Employees. This is the requirement.**

**This is also why `repositories/leave_request.list_leave_requests`'s `total` cannot be reused for these two figures.** It returns a count of *requests*, and it is otherwise a perfect fit — which is exactly what makes this trap easy to fall into. `total` **is** the right number for the two **Pending counts** (a queue is a list of requests), and it is the wrong number for the two **leave-presence figures**.

**A test that seeds one report with two overlapping APPROVED requests and asserts they appear exactly once is what proves the DISTINCT is real.** Write it. Without it, the double-count ships green.

### Landmine 2 — Three literal routes. `GET /dashboard/{role}` breaks two things at once.

A dev economizing with one parameterized route destroys the story:

1. **The scope matrix.** `tests/test_scope_matrix.py` registers **every `/api/v1` route whose template contains `{`**. `/dashboard/{role}` creates a path param → the guard demands a registry entry. The three literal paths have **no `{`** → they are **out of the matrix by construction** (the `GET /team`, `GET /calendar`, `GET /notifications` precedent), and registering them would trip `test_no_registered_entry_names_a_route_the_app_does_not_expose` in the *other* direction.
2. **AC5's semantics.** With a literal `/dashboard/manager`, an Employee is refused by `require_role` **before any row is read** → **403 `ACTION_NOT_PERMITTED`**, which is exactly what AC5 demands. With `/dashboard/{role}`, "manager" becomes a *value*, and the natural implementation turns a role mismatch into a scope miss → **404**. That is the wrong code, and the G3 settlement (`api-contracts.md:37-44`) is explicit about which is which: *"does the actor's role admit them to this endpoint at all? If no → **403**, decided before any row is read. If yes → the scope predicate runs, and a miss is **404**."*

**Three routes. Three literal paths. `test_scope_matrix.py` stays untouched — that is the tell you did it right.** 3.1, 3.2 and 3.3 each shipped zero entries there.

### Landmine 3 — A `leave_balance` row has no dates. Do not invent a `leave_year` predicate from the date range.

`leave_balance` is keyed `(employee_id, leave_type_id, **leave_year**)` — an **integer year**, not a date range (`erd.md:209`). A `date_from`/`date_to` of `2026-03-01..2026-05-31` **does not select a balance row**, and a range spanning two Leave Years would select two rows per Leave Type, breaking AC1's "per Leave Type" singular shape.

**Decision #2 rules: balances are the caller's CURRENT Leave Year, always, and are never date-filtered.** The range filters the **Pending count** only.

Story 3.1's **Landmine 5** warned about precisely this creep: *"writes use `_current_leave_year()` … **do not** let any default creep into the read path (e.g. defaulting `date_from` to Jan 1)."* Do not run it in reverse either — do not let `date_from` become a `leave_year`.

Related, and **not 3.5's to fix**: `deferred-work.md:42` records the year-rollover cliff — an Employee with no current-year balance row reads **empty**. `list_own_balances` inherits that. Do not be surprised by it; do not fix it here.

### Landmine 4 — `/dashboard/manager` refuses the ADMIN too. This is the third verse of the same inversion.

api-contracts §4.9 grants `/dashboard/manager` to **Manager**, full stop. AC5 only names the Employee, but the contract binds: **an Admin gets `403 ACTION_NOT_PERMITTED` as well.** `require_role(authz.ROLE_MANAGER)` gives this for free — and 3.2 and 3.3 both **pinned it with a parametrized test** (`test_department_calendar.py:595-612`, `parametrize("denied", ["admin", "employee"])`). Do the same, both ways:

- `/dashboard/manager` → refuses `admin` **and** `employee`.
- `/dashboard/admin` → refuses `manager` **and** `employee`.

An Admin sees organization-wide figures on **their own** dashboard; a *team* is a reporting edge only a Manager stands on.

### Landmine 5 — The Admin's "Pending request count" is LEAVE Requests. Not Cancellation Requests. Settled twice.

`implementation-readiness-report-2026-07-10.md:565`: *"The Admin dashboard (`FR-11`, Story 3.5) presents 'Employees on approved leave today, and the Pending request count' — that count is **Leave Requests**, not Cancellation Requests."* Repeated at `:819` and `epics.md:1176`.

And Story 2.8 built its own premise on it (`2-8-…:27`, `:121`): the Admin queue at `GET /cancellation-requests` is *"the Admin's **only** route to a Cancellation Request, because **none is announced to them by notification or dashboard**."*

**A dev who folds Cancellation Requests into the Admin's pending count breaks a settled decision and 2.8's stated design.** Seed a PENDING Cancellation Request in the AC3 test and assert the count **does not move**.

### Landmine 6 — The test-date convention of every other Epic-3 test file is WRONG for this story.

`test_team.py` and `test_department_calendar.py` both open with `_NEXT = datetime.date.today().year + 1` and seed everything a year out, *"so no submission ever brushes the `PAST_DATE_RANGE` rule and no clock is ever mocked."*

**Copy that here and every leave-presence figure reads zero.** The Manager's default window is `today..today+6`; the Admin's is `today..today`. Rows seeded a year out fall outside both, and the tests pass **vacuously**.

3.5 seeds rows by **direct repository insert** (which bypasses `PAST_DATE_RANGE` entirely — the 3.1/3.3 precedent), so dates near and around `today` are free. Seed relative to `datetime.date.today()`:
- inside the window (starts today; starts day 3; spans the boundary from yesterday into day 2),
- **on both edges** (ends exactly on `today+6` → in; starts exactly on `today+7` → **out**),
- and outside it.

**And never mock the clock.**

### Landmine 7 — `api/` may import neither `Scope` nor a status name. The decisions live in the service.

import-linter **contract 2** (`pyproject.toml`): `source_modules = ["app.api"]`, `forbidden_modules = ["app.repositories", "app.domain"]` — flagged **even under `TYPE_CHECKING`**. And `test_vocabulary_literals.py` makes the bare string `"MANAGER"` / `"PENDING"` unwritable anywhere under `app/`.

Therefore:
- `Scope.SELF` / `Scope.REPORTS` / `Scope.ALL` are **hardcoded in `services/dashboard.py`**, never passed from the route. (`services/calendar.py:13-18` explains exactly this.)
- Status constants come from `app.domain.vocabulary` **in the service**, never in `api/`.
- Role constants reach `api/` through the sanctioned re-export: `from app.services import authorization as authz` → `authz.ROLE_MANAGER`. (`services/authorization.py:11-18` documents why this indirection exists.)

`lint-imports` must stay **7/7 byte-identical**. `pyproject.toml` is untouched.

### Landmine 8 — The day count belongs to the server. (And know exactly what the guard scans — it is narrower than you think.)

`backend/tests/test_frontend_no_client_day_count.py:49` line-scans `frontend/src` for **exactly two tokens**: `_DAY_OF_WEEK_PRIMITIVE = re.compile(r"\b(getDay|getUTCDay)\b")`. It **does** match inside comments and strings (a raw line-scan), but its own docstring (`:10`) is explicit that it does **not** forbid the words "weekday" or "holiday".

**So a card label reading "Next 7 days" is perfectly safe. A `.getDay()` call is not.** Do not let this landmine scare you out of writing honest copy — the real rule is AD-2/AD-18: **the window is computed server-side, the client sends no dates by default, and every server figure is rendered verbatim.** `Math.ceil(total / page_size)` arithmetic is fine; date arithmetic to derive `today + 7` in the browser is not — it duplicates a server decision that the response already echoes back to you (`leave_window_from`/`leave_window_to`).

### Landmine 9 — A `['dashboard']` query key is a cross-user disclosure if it is not purged on sign-out.

The key carries **no per-user identity**. On a shared browser, the next user sees the **previous user's** balances and counts for up to `staleTime` (30 s). `App.tsx:224-227` states the hazard for `['notifications']` in as many words: *"a genuine cross-user disclosure, not cosmetic staleness."*

**Add the dashboard key to the `removeQueries` purge at `App.tsx:222/227` (session expiry) and `App.tsx:239/242` (fresh login).** Task 7.

### Landmine 10 — You cannot add a COUNT to `repositories/leave_request.py`.

`tests/integration/test_leave_request_submit.py:535-635` **hard-pins that module's public surface by name** to exactly seven functions, and `audit_entry.py` to two. A `count_requests_by_status` added there **fails the build by name at import time**. The pin is load-bearing for AD-8/AD-9 append-only and has been widened twice, each time with heavy justification; a dashboard COUNT does not qualify.

The sanctioned home is a **new module** — and the spine names it: `ARCHITECTURE-SPINE.md:394` maps `FR-11 Dashboards` to *"`api/v1/dashboard`, **scoped repository aggregates**"*. `repositories/dashboard.py` **is** that scoped-aggregate module. Declare it as such in its docstring.

### Landmine 11 — No new error code. No new vocabulary. No migration. No new index.

- **`main.py` `CODE_TO_STATUS` is UNTOUCHED.** `ACTION_NOT_PERMITTED → 403` (line 56) and `RESOURCE_NOT_FOUND → 404` (line 57) are already mapped. Every refusal these routes can produce — 403 role gate, 401 no token, a framework 422 on a malformed date — is already covered.
- **`domain/vocabulary.py` is UNTOUCHED.** `STATUS_PENDING`, `STATUS_APPROVED`, `ROLE_*` all exist. A dashboard is a read; it invents no enumerated string.
- **No migration.** `alembic check` must stay clean — drift means you touched a model. `test_migrations_insert_nothing` / `test_migration_smoke` / `test_schema_1_2` are all untouched.
- **No new index.** The two indexes this story's aggregates walk already exist, both shipped in `0006`: `leave_request (employee_id, status)` — which `erd.md:379` tags **for this story by name**, *"**Dashboards**, history, deactivation guard (**FR-11**, FR-20, AD-22)"* — and `leave_request (start_date, end_date)` (`erd.md:380`, tagged FR-18/FR-10, and the one the overlap predicate actually uses). The house stance on missing secondary indexes (`deferred-work.md:45, 69, 77`) is that at **NFR-10** scale they are consciously deferred, not blockers. Name in the Dev Agent Record which indexes your aggregates walk, so the decision is informed rather than accidental.

### Landmine 12 — Measure the test baseline. Do not trust this file's number.

3.4 is **`in-progress`**, its Dev Agent Record is **empty**, and its Task 11 may still land (which would *add* tests and *delete* `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject`). The tree collected **561** on 2026-07-14. 3.2 predicted 512 and measured 514. **Run the suite first and write down what you actually see.**

The delta rule:
```
expected = MEASURED baseline
         + your new test functions (parametrized cases counted individually)
         + 1 per new .py file under backend/app/ or backend/seed/   ← test_vocabulary_literals.py
         + 1 per new file in backend/alembic/versions/               ← test_migrations_insert_nothing.py  (3.5: ZERO)
```
3.5 adds three `app/` modules → **+3** before a single new test is written.

### Landmine 13 — One aggregate query per figure. Never a loop over reports.

The obvious wrong implementation of the Manager dashboard is: fetch the reports, then issue one COUNT per report. That is an N+1 the codebase has nowhere else. Every figure is **one** scoped SQL aggregate, with the scope as a `JOIN employee … WHERE employee.manager_id = :actor` predicate — never a Python-side filter (AD-10, NFR-04, and it is SM-3's subject).

And carry the `total`-lies lesson (3.1's Landmine 3, restated at `repositories/notification.py:137-138`): **if a count joins, the count's predicate must be the same predicate as the page's.** Filter by **id**, never by a joined column's code.

### Landmine 14 — `services/` may NOT import `MAX_PAGE_SIZE`. The bound comes DOWN from the route.

Decision #5 caps the Manager's `reports_on_approved_leave` list at `MAX_PAGE_SIZE` (100). The obvious implementation — `from app.api.v1.pagination import MAX_PAGE_SIZE` inside `services/dashboard.py` — **breaks the build.**

`pagination.py` lives at `app/api/v1/pagination.py:36` — inside **`app.api`**, the *top* layer. import-linter **contract 1** is a `layers` contract (`["app.api", "app.services", "app.repositories", "app.domain"]`), and an upward `services → api` import violates it. `lint-imports` drops to **6/7**, contradicting this story's own requirement that it stay 7/7. **No module under `app/services`, `app/repositories`, `app/domain` or `app/jobs` imports `app.api` today** — there is no precedent to lean on, because there is no legal one.

**The house pattern already answers this: `api/` owns the bound and passes it down.** `api/v1/team.py:83` calls `team_service.list_team(params.limit, params.offset, manager)` against `services/team.py:35`'s `def list_team(limit: int, offset: int, actor: Employee)`. Do exactly that:

- `api/v1/dashboard.py` — `from app.api.v1.pagination import MAX_PAGE_SIZE` (an `api → api` import, legal, the `BalanceResponse` precedent) → `manager_dashboard(..., limit=MAX_PAGE_SIZE)`
- `services/dashboard.py` — `limit: int` is a **keyword parameter**, never an import
- `repositories/dashboard.py` — `limit` arrives as an argument and lands in `.limit(limit)`

---

## Architecture Compliance

| Rule | Source | What it means here |
| --- | --- | --- |
| **AD-10** — authorization is a query predicate; no repository exposes an unscoped getter | `ARCHITECTURE-SPINE.md:121-125` — and it **binds FR-11 by name** | Every dashboard aggregate takes `actor` and applies `employee_scope_predicate` **in the SQL**. A Manager's scope is `employee.manager_id = :actor_id`, bound at request time. |
| **AD-18** — the Leave Day count is frozen | `ARCHITECTURE-SPINE.md:169-173` — *"Every read path — history, **dashboard**, calendar, export — reads the stored value and never recomputes it"* | **The spine names this story.** Never call `count_leave_days`. Pin it with the `_STORED_DISAGREES = 99` test. |
| **DR-3 / AD-5** — `available` is derived, never stored | `prd.md:469`, `erd.md:217`, `api-contracts.md:162` | `available = accrued − consumed − reserved`, derived at the **`api/` projection**, exactly as `api/v1/balances.py:58-72` does. No column, no model, no lower layer. |
| **AD-17** — one module owns every balance mutation, exactly eight callables | `ARCHITECTURE-SPINE.md:163-167`; pinned by `test_balances_module_surface.py` | 3.5 is read-only and touches none of them. **Do not add a ninth public callable to `services/balances.py`** — reads live in `services/balance_reads.py`, which has no pin. |
| **AD-3** — one transaction per command, `FOR UPDATE` on balance writes | `ARCHITECTURE-SPINE.md:79-83` | AD-3 governs **commands**. A dashboard is a query: **no lock, no `FOR UPDATE`, no commit.** |
| **AD-1** — `api → services → {repositories, domain}`; `api/` imports neither `repositories/` nor `domain/` | `pyproject.toml` contracts 1 & 2 | Landmine 7. |
| **AD-21** — enumerated values declared once in `domain/` | `ARCHITECTURE-SPINE.md:191`; `test_vocabulary_literals.py` | `vocabulary.STATUS_PENDING`, never `"PENDING"`. |
| **AD-12** — dates are `YYYY-MM-DD` | `ARCHITECTURE-SPINE.md:137` | `date_from`/`date_to` are `datetime.date`. Instants are never interchanged with dates. |
| **AD-8** — a read is not a transition | | **Zero audit rows. Zero notifications.** SM-4's ledger stays at exactly 14. The proof: `services/dashboard.py` does not import `audit_entry_repo` or `notification_repo` at all (the `services/rollover.py` idiom). |
| **NFR-11** — no endpoint returns an unbounded collection | `non-functional-requirements.md:45` | Decision #5 — the one list this story returns is **server-capped and the cap is declared**. |
| **NFR-04** — scoping where data is fetched, never post-filter | | Landmine 13. |
| **NFR-10** — ~500 ms typical reads | `non-functional-requirements.md:43` | Explicitly *"an order of magnitude, not a contractual figure"*, and **verified by no story** (`epics.md:282`). Do not write a timing test. Do name the indexes your aggregates walk. |
| **SM-6** — every module docstring names the FR/DR it implements | `ARCHITECTURE-SPINE.md:219` | All three new modules cite FR-11. |
| **SM-C2** — dashboard richness is a counter-metric: *do not optimize* | `prd.md:644` | **No charts. No trend lines.** Resist enrichment (see Decision #7). |

---

## The response shapes

No artifact fixes these (api-contracts §5 defers them to the code, by design). This story fixes them. **Pin the exact key sets with tests** — accidental widening is a disclosure and must fail the build.

```jsonc
// GET /api/v1/dashboard/employee   (role any, scope self)
{
  "leave_year": 2026,                    // which year's balances these are (Decision #2 made visible)
  "balances": [                          // BalanceResponse, reused byte-for-byte from api/v1/balances.py
    { "leave_type_code": "EL", "leave_type_name": "Earned Leave",
      "available": 12, "reserved": 3, "consumed": 5 }
  ],
  "pending_request_count": 2             // the caller's own PENDING requests
}

// GET /api/v1/dashboard/manager   (role Manager, scope reports)
{
  "pending_decision_count": 3,           // PENDING requests from the caller's Direct Reports
  "reports_on_approved_leave": [         // DISTINCT Employees, not requests (Landmine 1)
    { "employee_id": "0199…", "full_name": "Rahul Sharma" }
  ],
  "leave_window_from": "2026-07-14",     // the EFFECTIVE window — the UI's card label derives from this
  "leave_window_to": "2026-07-20"        // NULLABLE: a one-sided range leaves one end unbounded
}

// GET /api/v1/dashboard/admin   (role Admin, scope all)
{
  "employees_on_approved_leave": 7,      // COUNT(DISTINCT employee_id) — Landmine 1
  "pending_request_count": 12,           // LEAVE Requests only — Landmine 5
  "leave_window_from": "2026-07-14",
  "leave_window_to": "2026-07-14"        // NULLABLE, as above
}
```

`leave_window_from` and `leave_window_to` are typed **`datetime.date | None`** in Pydantic — a caller supplying only `date_from` leaves the upper end genuinely unbounded, and the wire must say so rather than fabricate an end date (Decision #1's stated consequence).

Whole-day **integers** everywhere (the spine's consistency convention: *"no `NUMERIC`, no float, in schema, domain, or API"*). `accrued` is never surfaced.

---

## Previous Story Intelligence

**3.4 — In-App Notifications (`in-progress`, uncommitted).** 3.5 builds on its tree. Tasks 1–10 are landed (the `notification` table, the repo/service/api trio, the two transition hooks, the scope-matrix entry, the eight repaired teardowns); **Task 11 is not.** Its Dev Agent Record is empty. Two things 3.5 inherits directly: (a) `count_unread` is the **closest structural precedent** for a dashboard aggregate — a scoped `COUNT(*)`, `count_`-prefixed, returning a bare `int`, *"applying the scope predicate anyway, for correctness rather than to satisfy a guard"*; (b) the `['notifications']` sign-out purge in `App.tsx` is the reason Landmine 9 exists.

**3.3 — Department Leave Calendar (`review`).** The nearest read-only precedent, and the source of three things 3.5 copies verbatim: the thin read-only service over `list_leave_requests`; the server-side fixed status set (`CALENDAR_STATUSES`) that keeps every status name out of `api/`; and the parametrized Admin-**and**-Employee 403 test. It also recorded the basename collision that **aborts the whole pytest suite** — check your test filename.

**3.2 — My Team (`review`).** Established: the service owns the `Scope` decision; the minimal-disclosure response with an **exact-key-set pin**; `components/` promotion only on the second caller; and the measured-vs-recorded baseline discrepancy that produced the "MEASURE FIRST" rule.

**3.1 — My Leave History (`review`).** Established the **overlap** date semantics 3.5 reuses (`end_date >= date_from AND start_date <= date_to`, each side optional), the inverted-range → `200`-empty ruling (zero code), the `''`→`undefined` filter-form translation, and the `MAX_PAGE` clamp that closes `deferred-work.md:19`/`:58` (Task 10).

**2.4 — Leave Balances (`done`).** Built `GET /balances`, `services/balance_reads.py`, `BalanceResponse` with its derived `available`, **and `features/dashboard/DashboardPage.tsx`** — the page this story extends. It is also the last story to add CSS (`.balance-available*`), which is why the honest claim is *"zero new CSS since 2.4"*, not *"the app's first CSS"*.

**Git.** HEAD is `4fc1629` (stories 2.9–2.12, squashed). Stories 3.1–3.4 are **uncommitted working-tree state**. The house commit shape is one squashed `feat(story-N.M): …` per story.

---

## Open Decisions

Each carries a recommendation. Adopt or overrule — but **record the choice** in the Dev Agent Record.

### 🚨 #1 — How `date_from`/`date_to` interact with "the next seven days" and "today". THE story's one genuinely under-determined point.

**The contradiction is real and no artifact resolves it.** FR-11 specifies figures over a window fixed **relative to now** ("within the next seven days", "today") *and*, one bullet later, that *"the figures presented are those falling inside the selected range."* If a Manager sets `date_from=2026-01-01&date_to=2026-03-31`, what does the "next seven days" card show? Three readings, all defensible, none written down. I searched every artifact: the readiness report (`:265-267`) and the epics (`:56`, `:1561-1569`) each restate **both halves** without noticing the tension, and no gap (G1–G8) touches it.

Sharpening it: Story 3.1's Open Decision #1 **explicitly carved the dashboard out of its own overlap ruling** (`3-1-…:378`): *"`prd.md:366`'s 'falling inside the range' governs **dashboards**, not this list."* So 3.1 declined to settle it **on purpose**, and left it here.

**RECOMMENDED — the range REPLACES the default window, and FR-11's windows are the DEFAULTS:**

| Figure | Default when **both** params absent | When **either** param is supplied |
| --- | --- | --- |
| Employee: balances | current Leave Year (Decision #2) | **unchanged** — never date-filtered |
| Employee: pending count | **no window** — all their PENDING requests | overlap predicate |
| Manager: pending-decision count | **no window** — all PENDING from reports | overlap predicate |
| Manager: reports on approved leave | **`today .. today+6`** (seven calendar days, inclusive of today) | overlap predicate |
| Admin: employees on approved leave | **`today .. today`** ("today") | overlap predicate |
| Admin: pending request count | **no window** — all PENDING org-wide | overlap predicate |

Rule, stated once: **if both params are absent, the FR-11 default applies; if either is supplied, the supplied predicates apply verbatim and the default is not used** (an absent side applies no predicate — the settled 3.1/3.3 semantics, reused unchanged).

**Why the pending counts default to *no* window** and not to a seven-day one: a Manager's pending queue is **work**, not a report. Windowing it by default would **silently hide requests awaiting decision** — the exact failure UJ-2 exists to prevent. FR-11 attaches a window to the leave-presence figures **only**; read it literally.

**Why the response echoes the effective window** (`leave_window_from`/`leave_window_to`): so the UI's card label is *derived* from what was actually computed. Hard-coding "Next 7 days" in the JSX makes the label a **lie** the moment a range is supplied.

**The one-sided consequence, stated so it is CHOSEN and not stumbled into:** `date_from` alone → `end_date >= date_from` with **no upper bound** — approved leave arbitrarily far into the future. `date_to` alone → **no lower bound** — all past approved leave. This falls straight out of the settled 3.1/3.3 rule that *an absent side applies no predicate*, and it is the right answer (a defaulted end date would be a predicate the caller never asked for). It is why `leave_window_from`/`leave_window_to` are **nullable on the wire**: the UI must render *"from 2026-08-01 onwards"*, never invent an end date the server did not apply.

*Rejected:* **(B) intersect the range with the fixed window** — returns an empty card for almost any range a user would pick; certainly not intended. **(C) leave the windows fixed and filter only the other figures** — directly contradicts *"**the figures** presented are those falling inside the selected range."*

### #2 — What a date range means for the Employee dashboard's balances. **Answer: nothing. They are never date-filtered.**

A `leave_balance` row is keyed by an integer `leave_year`, not by dates (Landmine 3). **RECOMMENDED:** balances are the caller's **current Leave Year**, always — `balance_reads.list_own_balances(actor)` called verbatim — and the response carries `leave_year` so the user can see which year they are looking at. The range filters the **pending count** only.

*Rejected:* deriving `leave_year` from the range. A range spanning two Leave Years yields two balance rows per Leave Type, which breaks AC1's "per Leave Type" singular shape, and no artifact grants the mapping.

### #3 — "Employees on approved leave" is `COUNT(DISTINCT employee_id)`.

**RECOMMENDED:** adopt. This is Landmine 1, restated as a decision because it is the story's one genuinely new query. It is also **why `repositories/dashboard.py` must exist** — `list_leave_requests`'s `total` counts requests and cannot express it.

### #4 — A new `repositories/dashboard.py`, not an addition to `repositories/leave_request.py`.

**RECOMMENDED:** adopt. Two reasons, both hard: (a) `leave_request.py`'s surface is **pinned by name** and an addition fails the build (Landmine 10); (b) `ARCHITECTURE-SPINE.md:394` maps FR-11 to *"`api/v1/dashboard`, **scoped repository aggregates**"* — the module is sanctioned by the spine, by name. Its docstring must say so, so a reviewer reads it as an architectural instruction followed, not as a pin evaded.

### #5 — The Manager's `reports_on_approved_leave` is a bounded list of Employees, not a paged list and not a bare count.

FR-11 says the dashboard *"presents … their **Direct Reports** who are on approved leave"* — it presents the **people**. But NFR-11 binds: *"**No endpoint** returns an unbounded collection."*

**RECOMMENDED:** return a **list of `{employee_id, full_name}`, DISTINCT per Employee, ordered by name, capped at `MAX_PAGE_SIZE` (100)** — reuse that constant rather than inventing a second bound, but reuse it **from the route**, passed down as `limit=`. 🚨 **`services/` and `repositories/` may not import it** — `pagination.py` lives in `app.api` and the upward import breaks import-linter contract 1 (Landmine 14). **Declare the cap in the Dev Agent Record** (the no-silent-caps rule). A Manager's direct reports are inherently few, so the cap is effectively unreachable; it exists so NFR-11 holds by construction rather than by luck.

**No `Page` envelope, no `Pager`.** This is a summary card, not a list screen — and the app already has **six** page-1-only lists (`deferred-work.md:11, 15, 29, 34, 62, 70, 76`); do not ship a seventh. **Dates are deliberately not on the card**: a Manager who wants *when* has `GET /calendar` (Story 3.3), rendered inline on the very approval screen. The dashboard summarizes; the calendar details. Say so.

**Do not fix the six other panels' pagers.** Not this story's surface.

### #6 — Deactivated Employees are INCLUDED.

**RECOMMENDED:** adopt, by inheritance. 3.2 and 3.3 both ruled that the reports predicate carries **no `is_active` filter** — *"a deactivated report's approved absence is still a fact about the team's dates"* (`services/calendar.py:27-29`). FR-11 is silent on `is_active`, and inventing a filter would make the Admin's org-wide count disagree with the calendar's. Note the nearby trap: `count_active_direct_reports` **does** filter — do not reach for it.

### #7 — The dashboard does NOT carry an unread-notification count.

api-contracts §4.8 tags `GET /notifications/unread-count` with **`FR-11`** as well as FR-14, which invites folding it into the dashboard response. **RECOMMENDED: do not.** FR-11's consequence list does not name it; 3.4 already ships the badge; and **SM-C2** — *"dashboard richness … the cheapest way to look finished and the least defensible under questioning"* — counsels against exactly this kind of enrichment. Likewise **do not** surface `GET /employees/{id}/balances` on the Manager dashboard: it still has no UI consumer, but no AC of 3.5 asks for it, and adding it would silently widen disclosure.

### #8 — 🚨 The AD-6 submit gap: 3.5 CANNOT fix it, and must say so loudly.

**The history.** Six stories have now deferred this: 2.11 (#8) → 2.12 (#11) → 3.1 (#6) → 3.2 (#4) → 3.3 (#7) → 3.4 (#1). `deferred-work.md:75`: *"**It now ships unless Epic 3 picks it up.**"* 3.3 named the runway precisely: *"3.4 … is the named forcing point, and **3.5 closes the epic**."*

**The state right now, verified in the tree:** 3.4's Open Decision #1 ruled that the fix should be adopted as its Task 11 — and **Task 11 is not implemented.** `recompute_carry_forward` does not appear in `submit_leave_request`; `CAUSE_SUBMISSION_RECALCULATION` does not exist in `vocabulary.py`; `insert_admin_review_flag` still has exactly two call sites; and 2.12's pinned canary `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject` is **still passing**, which 3.4 said the fix would break. 3.4 is `in-progress` with an empty Dev Agent Record. **The defect is live and unruled-upon.**

**RECOMMENDED: 3.5 declines, explicitly and on the record.** 3.5 is three read-only GETs. It never opens a write transaction, never calls `reserve`/`consume_direct`/`set_accrual`/`recompute_carry_forward`, and never imports the balance mutators. The fix would require editing `services/rollover.recompute_carry_forward`, `services/balances.set_accrual`, `services/leave_requests.submit_leave_request` and `domain/vocabulary.py` — **four functions, none of which is in 3.5's diff**, for reasons no AC of 3.5 grants. That is precisely the silent scope-widening five stories have declined by name.

**🚫 And do NOT "helpfully" add the one-liner.** `deferred-work.md:67`/`:75` prescribes *"one more `recompute_carry_forward` call in `submit_leave_request`"* — **3.4 proved that fix is UNSAFE as written.** The three existing call sites are all where `available(Y)` **rises**; submit **lowers** it, `recompute_carry_forward` has **no forward check**, and `set_accrual`'s guard raises a **bare `ValueError`** with no handler. The one-liner converts a quiet wrong balance into a **raw 500 on the most-trafficked write path in the application.**

**The honest disposition:** **3.4 must close its Task 11 as DONE or NOT-DONE before Epic 3 is declared complete.** If NOT-DONE, `deferred-work.md` gets an Epic-3-close entry saying the defect shipped. This is the PRD's own posture (§7.3): *a missed target is reported as a missed target, never reclassified afterwards as a deferral that was always intended.* **Record this in 3.5's Dev Agent Record so it cannot lapse silently when the epic closes.**

### #9 — Strike `deferred-work.md:19` and `:58` as stale.

Both describe the unbounded-`page` → bigint-OFFSET → 500 bug that **Story 3.1 closed** (`MAX_PAGE = 1_000_000`). 3.1 flagged them as stale; 3.4 authorized striking them; nobody has. **RECOMMENDED:** strike them (Task 10), naming 3.1 as the closer. Touch nothing else in that file.

### #10 — Zero new CSS.

**RECOMMENDED:** adopt. `.emp-fields` is already an `auto-fit`/`minmax` responsive grid; `.balance-available-value` is already a big-number card figure; the `@media (max-width: 48rem)` block already answers NFR-18. Every Epic-3 story has shipped zero CSS. **If a class is genuinely warranted, it must be DECLARED in the Dev Agent Record as the first CSS added since Story 2.4** — and justified against SM-C2.

### #11 — An inverted range (`date_from > date_to`) is `200` with zero figures.

**RECOMMENDED:** adopt, by inheritance from 3.1 Open Decision #2. A well-formed empty intersection, not an error — **zero code**, since the overlap predicates simply match nothing. No `INVALID_DATE_RANGE`, no 422. A **malformed** date (`date_from=banana`) is a framework 422 via the `datetime.date` typing, free, and **no error code is invented** for it (the settled 3.1 posture; `deferred-work.md:10` owns the enveloped-422 question app-wide and is not 3.5's to resolve).

---

## Project Structure Notes

**New files**
```
backend/app/repositories/dashboard.py          # scoped aggregates (spine :394)
backend/app/services/dashboard.py              # the three reads; owns Scope + the status sets + the clock
backend/app/api/v1/dashboard.py                # three literal routes, three different gates
backend/tests/integration/test_dashboard.py    # basename verified free
frontend/src/api/dashboard.ts
frontend/src/features/dashboard/ManagerDashboardPanel.tsx
frontend/src/features/dashboard/AdminDashboardPanel.tsx
```

**Modified**
```
backend/app/api/v1/router.py                   # 2 lines — the ONLY existing backend file changed
frontend/src/api/index.ts                      # barrel exports
frontend/src/api/leaveRequests.ts              # 2 invalidation sites (decision fan-out + submit onSuccess)
frontend/src/api/cancellationRequests.ts       # 1 invalidation site
frontend/src/api/recalculation.ts              # 1 invalidation site
frontend/src/App.tsx                           # mount 2 panels; 2 removeQueries purge sites; replace the placeholder copy
frontend/src/features/dashboard/DashboardPage.tsx   # EXTEND (pending count + date filter) — do not clone
_bmad-output/implementation-artifacts/deferred-work.md   # strike :19 and :58
```

**MUST NOT change** — if one of these appears in your diff, stop and re-read the landmine that names it:
```
backend/app/main.py                    (CODE_TO_STATUS — no new error code)
backend/app/domain/vocabulary.py       (no new enumerated string)
backend/tests/test_scope_matrix.py     (no path params → out by construction; registering FAILS the build)
backend/tests/test_scoped_getters.py   (EXEMPT untouched is the tell you did it right)
backend/alembic/**                     (no migration; `alembic check` stays clean)
backend/pyproject.toml                 ([tool.importlinter] — 7/7 byte-identical)
backend/app/services/balances.py       (the 8-callable pin)
backend/app/repositories/leave_request.py, repositories/audit_entry.py   (surfaces pinned BY NAME)
frontend/src/index.css                 (zero new CSS — Decision #10)
```

---

## References

- Story ACs — `_bmad-output/planning-artifacts/epics.md:1547-1580`; Epic 3 preamble `:1403-1407`
- FR-11 (binding) — `prds/prd-LeaveFlow-2026-07-09/prd.md:358-371`; FR-03 `:148-159`; FR-12 `:410-417`; FR-18 `:373-381`
- api-contracts §4.9 — `architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md:225-239`; §1 conventions + the **G3 settlement** `:17-52`, esp. `:37-44`; §5 (schemas deliberately unfixed) `:249-251`
- AD-10 `ARCHITECTURE-SPINE.md:121-125` · AD-18 `:169-173` · AD-17 `:163-167` · AD-3 `:79-83` · AD-5 `:95` · AD-21 `:191` · AD-1 `:71` · capability map (FR-11 → *scoped repository aggregates*) **`:394`**
- PRD §7.4 (charts out of scope) — `prd.md:554-558`; SM-C2 `:644`; SM-8 `:638`; UJ-1 `:60`; UJ-2 `:69`
- NFR-18 — `module-1-business-analysis/non-functional-requirements.md:63`; NFR-11 `:45`; NFR-10 `:43`; NFR-12 `:47`
- ERD — `leave_balance` `module-4-erd/erd.md:83-94`, CHECKs `:343-348`, `available` absent by rule `:217`; `leave_request` `:95-103`, no `created_at` `:227`; **indexes §4.4 `:370-382`** (two name FR-11 / "Dashboards")
- Readiness report — FR-11 restatement `:263-269`; **"that count is Leave Requests, not Cancellation Requests"** `:565`, `:819`; F-11 resolved (403 + code) `:957`; no UX spec exists `:528-536`
- Code to copy — `api/v1/calendar.py` (Manager gate, optional date Query params) · `api/v1/balances.py:75-85` (role-`any` self read + the `available` derivation) · `api/v1/notifications.py:114-128` (scalar-aggregate endpoint) · `services/calendar.py` (thin read service, hardcoded Scope, server-side status set) · `repositories/notification.py:161-188` (`count_unread` — the aggregate template) · `repositories/leave_request.py:204-215` (the overlap predicate) · `repositories/scoping.py:59-79`
- Tests to copy — `tests/integration/test_department_calendar.py:595-612` (the parametrized 403 envelope), `:150-176` (`_insert_request`), `:360-412` (teardown) · `tests/integration/test_team.py:179-194` (exactness + named exclusions), `:161-171` (simple teardown)
- Guards — `tests/test_scope_matrix.py:142-161` · `tests/test_scoped_getters.py:172-182` · `tests/test_vocabulary_literals.py:108` · `tests/integration/test_leave_request_submit.py:535-635` (the pinned repo surfaces) · `tests/test_balances_module_surface.py:19-57` · `tests/test_frontend_no_client_day_count.py`
- Frontend — `App.tsx:99-196` (the shell + the gate idiom), `:222-242` (the purge) · `MyLeaveHistoryPanel.tsx:45-70, 88-93, 156-171` (the date filter) · `features/dashboard/DashboardPage.tsx` (extend) · `api/leaveRequests.ts:108-117, 165-204, 234-238` · `api/recalculation.ts:79-93` · `components/README.md:5-6` (the second-caller rule) · `index.css:119-136, 316-320, 453-457`
- Prior stories — `3-4-in-app-notifications.md` (OD#1, the AD-6 ruling) · `3-3-…-calendar.md` · `3-2-my-team.md` · `3-1-…-history.md` · `2-4-leave-balances-….md` · `deferred-work.md`

---

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5)

### Debug Log References

- **Task 0 baseline, MEASURED FIRST (Landmine 12):** `563 passed, 0 skipped` — NOT the story's guessed 561. Sprint-status explains the +2: 3.4 closed its Task 11 after this story file was written (2 new AD-6 tests, the 2.12 canary replaced 1:1). All four build guards green pre-story: `lint-imports` 7/7, `alembic check` clean, `npm run build`, `npm run lint`. Dev DB verified clean before the run (seed state: 1 employee / 3 balances; no orphaned pytest processes — the 3.4 trap checked for explicitly).
- **Red-green honored:** `test_dashboard.py` written first — 21 tests, all failed 404 against the routeless app (verified: `GET /api/v1/dashboard/employee → 404`). Implementation then turned them green with two TEST-side corrections, neither weakening an assertion: (1) the one-sided-range expectation had missed the fixture's own day-40/41 row (r4's CR-target) — corrected to expect it, which makes the test STRONGER (it now proves `date_from`-alone reaches leave arbitrarily far out); (2) a `parametrize` value said `"manager"` where the `_World` attribute is `manager_m`.
- **oxlint `react/only-export-components`:** exporting `describeWindow` from `ManagerDashboardPanel.tsx` broke the Fast-Refresh rule — moved to its own `features/dashboard/describeWindow.ts` (see File List deviation note).
- **Final counts:** backend `588 passed, 0 skipped` (the 1 warning is the pre-existing Starlette `testclient` deprecation, not app code); `lint-imports` 7/7 byte-identical; `alembic check` clean; `npm run build` + `npm run lint` clean; `test_frontend_no_client_day_count.py` 3/3.

### Completion Notes List

- **All 6 ACs met.** AC1: `GET /dashboard/employee` — per-type Available/Reserved/Consumed (via `balance_reads.list_own_balances`, `BalanceResponse` reused byte-for-byte, `available` DERIVED at the api projection and proven derived by the move-reserved-watch-it-drop test) + own PENDING count; exact key set pinned at both levels. AC2: `GET /dashboard/manager` — reports' PENDING count + DISTINCT reports on approved leave, default window `today..today+6` pinned on BOTH edges (ends-day-6 IN, starts-day-7 OUT), name-ordered, deactivated report IN. AC3: `GET /dashboard/admin` — org-wide `COUNT(DISTINCT employee_id)` (default "today") + PENDING LEAVE-request count; a seeded PENDING Cancellation Request moves nothing (Landmine 5). AC4: supplied range REPLACES the default on all three; one-sided → null echo end; inverted → 200 with zero figures and balances untouched. AC5: parametrized both ways (`/manager` refuses admin+employee; `/admin` refuses manager+employee, full envelope) and a Manager on `/employee` gets THEIR OWN balances (proved with a second leave type held only by the manager). AC6: three card-based dashboards with date-range filters, zero new CSS, no chart/trend, server-echoed window labels.
- **Landmine 1 (the story's real engineering content) proven non-vacuous:** r1 holds TWO overlapping APPROVED requests; the manager list carries r1 exactly once, and the Admin count over a window both requests overlap answers 4 where a naive `COUNT(*)` would answer 5.
- **Landmine 2 held:** three literal routes; `test_scope_matrix.py` untouched (no `{` in any template). The AC5 refusals are the gate's 403, never a scope-miss 404; **no 404 test written** — no path param exists to miss on.
- **Landmine 14 held:** `MAX_PAGE_SIZE` (100) imported in `api/v1/dashboard.py` only, handed down as `limit=` through `services/dashboard.py` to the repository's `.limit()`. **The cap is hereby DECLARED** (Decision #5, the no-silent-caps rule): the Manager's `reports_on_approved_leave` list is server-capped at 100 DISTINCT people; a Manager's direct reports are inherently few, so the cap exists to make NFR-11 true by construction.
- **Landmine 11 / NFR-10 — the indexes the aggregates walk, named:** the two pending counts walk `leave_request (employee_id, status)` (`erd.md:379` tags it "Dashboards … FR-11" by name); the two leave-presence aggregates walk `leave_request (start_date, end_date)` (`0006`, the overlap predicate's index). No new index (the house stance on secondary indexes at NFR-10 scale stands).
- **Test-count arithmetic, EXPLAINED not assumed:** 588 = 563 (measured baseline) + 21 (new test functions, parametrized cases counted individually) + 3 (`test_vocabulary_literals`, one per new `app/` module) + 1 (`test_scoped_getters` auto-case for `list_employees_on_leave` — which PASSES because the getter takes `actor`; `EXEMPT` untouched, exactly the +1 the story's own Task 9 formula omitted and 3.4's sprint note predicted). Verified by collecting the guard files and grepping the 4 generated `dashboard` cases by name.
- **Open Decisions:** #1–#7, #9–#11 ADOPTED as recommended (#1: supplied range REPLACES defaults, pending counts unwindowed by default, effective window echoed nullable; #2 balances never date-filtered, `leave_year` on the wire; #3 DISTINCT; #4 new `repositories/dashboard.py`, spine :394 cited in its docstring; #5 bounded list, no Pager, no dates on the card; #6 deactivated included; #7 no unread count and no `GET /employees/{id}/balances` on any dashboard — SM-C2; #9 struck `deferred-work.md` :19 and :58 naming 3.1 as closer; #10 zero new CSS — `.emp-fields` grid + nested `.panel` cards + `.balance-available-value`, NFR-18 satisfied by the existing 48rem media query + auto-fit; #11 inverted range 200-empty, malformed date framework-422, zero code).
- **Open Decision #8 (the AD-6 submit gap) — OVERTAKEN BY EVENTS, recorded so nothing lapses:** the story's recommendation ("3.5 declines; 3.4 must close its Task 11 as DONE or NOT-DONE before the epic closes") was written while 3.4's Task 11 was unimplemented. **3.4 has since CLOSED Task 11 as DONE** (sprint-status 2026-07-14: `recompute_carry_forward` is now forward-checked, the submit-side recompute is wired into `submit_leave_request`, 2.12's canary replaced by `test_a_refused_pair_with_a_stale_cap_is_flagged_not_500`, `deferred-work:67/:74/:75` all closed by one root-cause fix). 3.5 verified this in the tree it builds on (the 563 baseline INCLUDES the 2 AD-6 tests) and touched none of it — the epic closes with the defect FIXED, not shipped. `deferred-work.md:75`'s entry is 3.4's to strike, not 3.5's (Task 10 authorized exactly two strikes).
- **DR-8 restated:** `services/dashboard.py:_today().year` is a third `date.today().year` read site (after `balance_reads._current_leave_year` and the write path) — a read-only restatement of DR-8, not a new rule. The year-rollover cliff all three share stays owned by `deferred-work.md:42` and was NOT fixed here.
- **AD-8 held by construction:** `services/dashboard.py` imports neither `audit_entry_repo` nor `notification_repo`; the story is read-only end-to-end (tests seed by direct insert, no API write) — SM-4's ledger stays at exactly 14, undisturbed.
- **Zero guard files in this story's diff** (Task 9 check): no `main.py`, no `vocabulary.py`, no `test_scope_matrix.py`, no `test_scoped_getters.py`, no `alembic/`, no `pyproject.toml`, no `index.css`, no `services/balances.py`, no `repositories/leave_request.py`/`audit_entry.py`. (The wider working tree carries 3.1–3.4's uncommitted review-state edits to some of those files; they are not 3.5's.) The only existing BACKEND file 3.5 edits is `router.py`, two lines.
- **`useBalances` now has ZERO callers** (DashboardPage switched to `useEmployeeDashboard`) — `src/api/balances.ts` deliberately LEFT INTACT per Task 8: `BALANCES_QUERY_KEY` is still invalidated from three modules, the `Balance` type is `dashboard.ts`'s item type, and `GET /employees/{id}/balances` still ships.
- **⚠️ THE FRONTEND TRUTH, stated plainly:** there is STILL no frontend test runner (`package.json`: `dev`/`build`/`lint`/`preview` only; zero `*.test.*` files). **AC6 is verified by tsc + vite build, oxlint, the backend day-count guard scan (3/3), and code reading — and by NOTHING else.**
- **Declared deviations (2):** (1) `DashboardPage`'s heading changed "My Leave Balances" → "My dashboard" — the panel now carries a pending-count card and a date filter beside the balances, so the old title would under-describe it; the balances list itself is unchanged. (2) NEW file `frontend/src/features/dashboard/describeWindow.ts`, not in the story's file list: oxlint's `react/only-export-components` (Fast Refresh) forbids exporting a helper from a panel file, and both panels need the window-label derivation; pure string assembly, no date arithmetic.

### File List

**New**
- `backend/app/repositories/dashboard.py` — the scoped aggregates (spine :394)
- `backend/app/services/dashboard.py` — the three reads; owns Scope, the status sets, the clock, the effective-window rule
- `backend/app/api/v1/dashboard.py` — three literal routes, three gates; derives `available`; supplies the list cap
- `backend/tests/integration/test_dashboard.py` — 21 tests (AC1–AC5, AD-18, Landmines 1/5/6)
- `frontend/src/api/dashboard.ts` — the three hooks + `DASHBOARD_QUERY_KEY`
- `frontend/src/features/dashboard/ManagerDashboardPanel.tsx`
- `frontend/src/features/dashboard/AdminDashboardPanel.tsx`
- `frontend/src/features/dashboard/describeWindow.ts` — window-label helper (declared deviation 2)

**Modified**
- `backend/app/api/v1/router.py` — 2 lines (the ONLY existing backend file changed)
- `frontend/src/api/index.ts` — barrel exports (values, then types)
- `frontend/src/api/leaveRequests.ts` — dashboard key joined to `invalidateAfterDecision` AND `useSubmitLeaveRequest.onSuccess`
- `frontend/src/api/cancellationRequests.ts` — dashboard key joined to `invalidateAfterCancellation`
- `frontend/src/api/recalculation.ts` — dashboard key joined to `invalidateEverythingARecalculationMoves` (+ "Six keys" → "Seven keys" doc fix)
- `frontend/src/App.tsx` — mounted both panels; dashboard key added to BOTH `removeQueries` purge sites (session expiry + fresh login, Landmine 9); replaced the stale "arrive across Epics 2 and 3" placeholder copy
- `frontend/src/features/dashboard/DashboardPage.tsx` — EXTENDED (pending-count card, date filter, `useBalances` → `useEmployeeDashboard`)
- `_bmad-output/implementation-artifacts/deferred-work.md` — struck :19 and :58 (Task 10, naming 3.1 as closer)
- `_bmad-output/implementation-artifacts/3-5-a-dashboard-per-role.md` — this file (frontmatter, checkboxes, record, status)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status transitions

## Change Log

- 2026-07-14 — Story 3.5 implemented complete (all 11 tasks, all 6 ACs): three dashboard endpoints + repository aggregates + service module, three React dashboards, invalidation fan-out and sign-out purge, deferred-work strikes. Backend 588 passed (from measured 563; arithmetic explained), import-linter 7/7, alembic clean, frontend build+lint clean. Status → review.
