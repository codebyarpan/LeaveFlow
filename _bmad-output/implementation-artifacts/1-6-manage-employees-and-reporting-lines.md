---
baseline_commit: 4dbf35d9d00760c8cde78a0fc686835414a09b57
---

# Story 1.6: Manage Employees and Reporting Lines

Status: done

Epic: 1 — Secure Access and Organization Administration (Phase 1, correctness core)
Story Key: `1-6-manage-employees-and-reporting-lines`
Created: 2026-07-11

## Story

As an Admin,
I want to create, view, update and deactivate Employees — including each one's Department, role, joining date and Manager —
So that the reporting relationship every authorization decision depends on is data I control, and a departing Employee never takes their history with them.

## Acceptance Criteria

Verbatim from `epics.md#Story 1.6` (lines 728–807). Do not paraphrase; the wording is the contract. AC numbering is added for task traceability. The parenthetical notes below each criterion are lifted from the epic and are binding context, not commentary.

**AC1 — An Admin creates an active Employee with an initial password (`FR-04`, api-contracts §4.2)**
**Given** an authenticated Admin
**When** they call `POST /api/v1/employees` with an email, full name, role, department, joining date and **initial password**, and an optional manager
**Then** the Employee is created and active, and can immediately authenticate with that email and password
**And** assigning a manager establishes the Direct Report relationship that `FR-03` enforces

**AC2 — The password is hashed once, and no response ever discloses it (`FR-04`, `NFR-01`, `AD-14`)**
**Given** an Employee created by an Admin
**When** the stored row is inspected
**Then** `password_hash` holds a salted hash produced through `pwdlib`, written once from the supplied initial password
**And** no response body from any `/api/v1/employees` endpoint carries a password or a password hash

**AC3 — An Admin reads and updates every Employee; PATCH accepts no password (`FR-04`, `FR-17`, api-contracts §4.2, PRD §6)**
**Given** an authenticated Admin
**When** they call `GET /api/v1/employees`, `GET /api/v1/employees/<id>` or `PATCH /api/v1/employees/<id>`
**Then** they may read every Employee, and may change the email address, full name, role, Department, Manager and joining date of any of them
**And** `PATCH /api/v1/employees/<id>` accepts **no** password — there is no re-issue path

**AC4 — The list is page-bounded, and the body carries the pagination envelope (`NFR-11`; spine *Pagination*)**
**Given** a client calling `GET /api/v1/employees` with a `page_size` larger than the server maximum
**When** the response is returned
**Then** it carries the server maximum, and the body carries `items`, `page`, `page_size` and `total`

**AC5 — A non-Admin is refused every `/employees` endpoint with `403`, before any row is read (`G3`, api-contracts §1)**
**Given** an authenticated Employee or Manager
**When** they call any `/api/v1/employees` endpoint, all of which api-contracts §4.2 grants to the Admin alone
**Then** the response is `403` with code `ACTION_NOT_PERMITTED`, and nothing is read or written
**And** the refusal is decided by the role gate in the `api/` dependency *before any row is read*, so it never reaches the scope predicate

> *(From epics.md line 760:)* `403` here, `404` in Story 1.7, and the two do not conflict. The test is whether the actor's **role** admits them to the endpoint at all: if no, `403`, decided before any row is read; if yes, the scope predicate runs and a miss is `404`. `AD-10`'s `404` still means exactly one thing — outside your scope. Settled by `G3`.

**AC6 — A duplicate email is refused `409 EMAIL_ALREADY_IN_USE`, raised by the service before the write (`G2`, `AD-5`, `NFR-17`)**
**Given** an email address already belonging to an Employee, whether active or deactivated
**When** an Admin calls `POST /api/v1/employees` or `PATCH /api/v1/employees/<id>` with it
**Then** the response is `409` with code `EMAIL_ALREADY_IN_USE`, raised by the service before the write
**And** it is never surfaced from the `UNIQUE (email)` violation, which is a backstop and would be a `500`; and the refusal does not disclose whether the holder is active

**AC7 — A manager assignment that would close a cycle is refused `400 REPORTING_CYCLE` (`AD-23`, `G7`)**
**Given** an Admin assigning a Manager to an Employee
**When** the assignment would make that Employee their own Manager, or would close a cycle A → B → A
**Then** the response is `400` with code `REPORTING_CYCLE`, and nothing is persisted
**And** `employee` carries `CHECK (id <> manager_id)` as a backstop, while the transitive cycle walk is the gate, in the service, inside the assignment transaction

> *(From epics.md line 772:)* Without this, an Employee who is their own Manager approves their own Leave Requests: `FR-09` grants approval to "the Manager of the applicant" and `DR-12` derives that authority from the relationship rather than the role, so the check passes — and `SM-3` still reports green, because self-approval genuinely **is** data-scoped.

**AC8 — Deactivation is refused while an active Employee reports to them (`409 EMPLOYEE_HAS_DIRECT_REPORTS`, `AD-22`)**
**Given** an Employee whom at least one **active** Employee names as their Manager
**When** an Admin calls `POST /api/v1/employees/<id>/deactivate`
**Then** the response is `409` with code `EMPLOYEE_HAS_DIRECT_REPORTS`
**And** the Employee remains active, because deactivating them would orphan their Direct Reports and cause `FR-09` to auto-approve those reports' requests with no human approver

**AC9 — Demotion below `MANAGER` is refused while an active Employee reports to them (`409 EMPLOYEE_HAS_DIRECT_REPORTS`, `AD-22` as amended, `G8`)**
**Given** an Employee whom at least one **active** Employee names as their Manager
**When** an Admin calls `PATCH /api/v1/employees/<id>` lowering their `role` below `MANAGER`
**Then** the response is `409` with code `EMPLOYEE_HAS_DIRECT_REPORTS`, and the role is unchanged
**And** deactivation and demotion are the two doors to the same orphaning, and both are closed

> *(From epics.md line 784:)* A demoted Manager who still holds Direct Reports is the worst of both worlds: `DR-12` says the relationship grants them authority to decide, the role gate says it does not, and their reports' Pending requests have no approver and receive no auto-approval, because `manager_id` is not NULL.

**AC10 — Deactivation is refused while the Employee holds any Pending Leave Request (`409 EMPLOYEE_HAS_PENDING_REQUESTS`, `FR-04`, `AD-22`) — VACUOUS IN THIS EPIC**
**Given** an Employee holding any Pending Leave Request
**When** an Admin calls `POST /api/v1/employees/<id>/deactivate`
**Then** the response is `409` with code `EMPLOYEE_HAS_PENDING_REQUESTS`

> *(From epics.md line 790 — binding:)* Vacuously satisfied in this epic: no `leave_request` table exists yet, so no Employee can hold a Pending request. Epic 2's Leave Request submission story creates that table and makes this guard executable. It is asserted here because it is `FR-04`'s consequence, and re-asserted there as a running test. **See Trap 6 — do NOT implement a `leave_request` query in this story.**

**AC11 — An Employee with no active report and no Pending request deactivates; the row persists (`FR-04`, `AD-22`)**
**Given** an Employee with no active Direct Report and no Pending Leave Request
**When** an Admin deactivates them
**Then** `is_active` becomes false and the row persists
**And** the Employee can no longer authenticate, and their history is preserved rather than deleted

**AC12 — No endpoint deletes an Employee; a deactivated email is never reusable (`FR-04`, ERD §4.2)**
**Given** the API surface
**When** it is enumerated
**Then** no endpoint deletes an Employee — an Employee is never physically deleted
**And** because a deactivated Employee's row persists under `UNIQUE (email)`, their email address is never reusable

**AC13 — The Employees screen (Admin) creates, edits, deactivates, assigns a Manager, sets an initial password, and surfaces every refusal (`NFR-17`, `NFR-16`, `G2`, `G7`, `G8`, `FR-14`, PRD §6)**
**Given** the React application and an authenticated Admin
**When** they open the Employees screen
**Then** they can create, edit and deactivate Employees, assign a Manager, and set an initial password on the create form
**And** a refused deactivation surfaces the reason, naming the blocking Direct Reports or Pending requests (`NFR-17`)
**And** a refused demotion, a duplicate email address, and a refused manager assignment each surface their reason — `EMPLOYEE_HAS_DIRECT_REPORTS`, `EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE` (`NFR-17`, `G2`, `G7`, `G8`)
**And** the Admin communicates the initial password outside LeaveFlow, which sends no email (`FR-14`, PRD §6)

## Tasks / Subtasks

> **Read the seven 🚨 traps in Dev Notes BEFORE writing any repository or service code.** Story 1.6 is the most complex story in Epic 1: it adds five new refusal paths (`EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`, `EMPLOYEE_HAS_DIRECT_REPORTS`, and — deferred — `EMPLOYEE_HAS_PENDING_REQUESTS`) on top of the department CRUD pattern Story 1.5 established. The single biggest decision is **Trap 1** (the scoped-getter guardrail on Employee reads), and it resolves *differently* from Story 1.5 because Employees **are** Employee-derived data. **No migration is expected** — the `employee` table, its `UNIQUE (email)`, its `role` CHECK and its `CHECK (id <> manager_id)` all already exist (migration `0002`); you add no column (Trap 7).

- [x] **Task 1: `domain/vocabulary.py` (UPDATE) — declare the three codes this story raises** (AC: 6, 7, 8, 9)
  - [x] Add `EMAIL_ALREADY_IN_USE = "EMAIL_ALREADY_IN_USE"` (api-contracts §2 → 409), `REPORTING_CYCLE = "REPORTING_CYCLE"` (→ 400), `EMPLOYEE_HAS_DIRECT_REPORTS = "EMPLOYEE_HAS_DIRECT_REPORTS"` (→ 409).
  - [x] Append all three to `__all__`. `tests/test_vocabulary_literals.py` auto-iterates `__all__`, so each value is immediately guarded against appearing as a literal anywhere else under `app/`/`seed/` (the frontend restates the *strings it matches on* once each, exactly as the departments screen does — see Task 9).
  - [x] Extend the module docstring's "What arrives, and where" list with a Story 1.6 line, matching the existing prose style (see the Story 1.5 line for the shape). Name why `EMPLOYEE_HAS_PENDING_REQUESTS` is **not** declared here (Trap 6): it is Epic 2's, declared and raised together when the `leave_request` table exists.
  - [x] **Do NOT declare `EMPLOYEE_HAS_PENDING_REQUESTS`** — see Trap 6. It has no raise site in Epic 1 (no `leave_request` table), and the codebase's dominant discipline is declare-a-code-with-its-raise-site.
- [x] **Task 2: `main.py` (UPDATE) — wire the three codes to their statuses** (AC: 6, 7, 8, 9)
  - [x] Extend the existing `CODE_TO_STATUS.update({...})` call with `vocabulary.EMAIL_ALREADY_IN_USE: 409`, `vocabulary.REPORTING_CYCLE: 400`, `vocabulary.EMPLOYEE_HAS_DIRECT_REPORTS: 409`, beside a Story 1.6 comment.
  - [x] Do **not** touch `api/v1/errors.py` — the map is populated only from `main.py`, the composition root (contract 2 forbids `errors.py` importing `domain/`). See Story 1.5 Task 2 / Story 1.4 Trap 3.
- [x] **Task 3: `repositories/employee.py` (UPDATE) — the admin reads, the guard counts, and the cycle-walk helper** (AC: 1, 3, 4, 7, 8, 9) 🚨 **See Trap 1**
  - [x] `list_employees(session, actor, limit, offset) -> tuple[list[Employee], int]` — one page of Employees (with `department` eager-loaded via `joinedload`, so the route can project it after the session closes) **and** the full count, ordered deterministically (e.g. `ORDER BY full_name, id`). **Takes `actor` and applies `scoping.employee_scope_predicate(Scope.ALL, actor)` in the `WHERE`** — Trap 1. Do NOT add to EXEMPT.
  - [x] `get_employee(session, actor, employee_id) -> Employee | None` — one row by id, `department` eager-loaded, `None` if no such row (or out of scope). **Takes `actor` and composes `employee_scope_predicate(Scope.ALL, actor)` alongside `Employee.id == employee_id`** — Trap 1. The service decides what `None` means (`not_found()` → 404).
  - [x] `count_active_direct_reports(session, manager_id) -> int` — the deactivation/demotion guard's input (AC8, AC9). Counts Employees where `manager_id = :id` **AND `is_active` is true** — only *active* reports orphan (`AD-22`). Named with `count_` (returns an `int`), so it is correctly **not** a scoped-getter candidate.
  - [x] `manager_id_of(session, employee_id) -> uuid.UUID | None` — returns just the `manager_id` column for one Employee (the cycle walk's single step, Trap 2). Named with `_of`, **not** a read-verb prefix, so it is not a scoped-getter candidate (it returns a scalar, not rows). Alternatively fold the walk into a dedicated `would_close_reporting_cycle(...)` repo helper — but keep all SQL in `repositories/`.
  - [x] Write helpers for the row mutations (`create_employee(session, ...) -> Employee`, `update_employee(...)`, `deactivate_employee(...)`), or issue them from the service — either is fine, but keep all SQL in `repositories/`. Writes are governed by the role gate, not the scope contract, so they are not guardrail candidates. `create_employee` must `flush()` to assign the server-default `id` before the route projects it (mirror `create_department`).
  - [x] **Reuse the existing `get_by_email(session, email)`** for the uniqueness pre-check (Trap 3) — do not add a second email getter. It is already EXEMPT (actor-resolution ground) and stays so; using it inside an Admin service for an existence probe discloses nothing.
  - [x] **Do NOT reuse `get_by_id_with_department`** for the admin reads — it is the EXEMPT `/me` actor-resolution getter (it resolves the *caller themselves*, no scope). The admin reads are a different concern (another Employee's data, scope `all`) and take the actor + predicate.
- [x] **Task 4: `services/employee.py` (NEW) — command orchestration and the four refusals** (AC: 1, 2, 3, 6, 7, 8, 9, 11) 🚨 **See Traps 2, 3, 4, 5, 6**
  - [x] Docstring names the FRs/ADs it implements (`SM-6`): `FR-04`, `FR-17` (the no-password-on-update rule), `AD-3` (one transaction per command), `AD-5` (the `UNIQUE (email)` and `CHECK (id <> manager_id)` constraints are backstops; the service is the gate), `AD-10`/`AD-14` (`not_found()`; role-gated at the boundary), `AD-22`/`AD-23` (the orphaning and cycle guards). One module-level message constant per refusal (mirror `services/departments.py`).
  - [x] `create_employee(email, full_name, role, department_id, joining_date, initial_password, manager_id=None) -> Employee` — in one transaction (`AD-3`): **(1)** email uniqueness pre-check via `get_by_email`; if a row exists (active or deactivated) → `raise EMAIL_ALREADY_IN_USE` (Trap 3); **(2)** if `manager_id` given, verify it names a real Employee (Trap 2 — else the FK 500s) and run the cycle walk (vacuous on create — the new row has no id yet — but harmless; Trap 2); **(3)** hash the password with `security.hash_password` (Trap 5); **(4)** insert `is_active=True`, `flush` for the id; **(5)** wrap the commit in `try/except IntegrityError` → re-raise `EMAIL_ALREADY_IN_USE` (the `UNIQUE (email)` backstop, `AD-5`, mirrors `delete_department`'s TOCTOU guard). Return the row for projection.
  - [x] `update_employee(employee_id, **changes) -> Employee` — load-or-`not_found()` first (Trap 4 pattern). Partial update (only provided fields change): `email`, `full_name`, `role`, `department_id`, `manager_id`, `joining_date`. **Accepts no password** (Trap 5). Order of guards: **(a)** if `email` changes and now belongs to a *different* Employee → `EMAIL_ALREADY_IN_USE` (Trap 3); **(b)** if `manager_id` changes → verify the manager exists and run the transitive cycle walk → `REPORTING_CYCLE` on a self- or A→B→A cycle (Trap 2); **(c)** if `role` is lowered **below `MANAGER`** (i.e. to `EMPLOYEE`) **and** `count_active_direct_reports > 0` → `EMPLOYEE_HAS_DIRECT_REPORTS`, role unchanged (Trap 4 / AC9); apply, `try/except IntegrityError` on commit → `EMAIL_ALREADY_IN_USE`.
  - [x] `deactivate_employee(employee_id) -> Employee` — load-or-`not_found()`. Guard: if `count_active_direct_reports > 0` → `EMPLOYEE_HAS_DIRECT_REPORTS` (AC8), row unchanged. **Do NOT query pending requests** (Trap 6 — no `leave_request` table; AC10 is vacuous). Set `is_active=False`, commit, return the row (so the client sees the new state).
  - [x] `list_employees(limit, offset, actor) -> tuple[list[Employee], int]` and `get_employee(employee_id, actor) -> Employee` (raising `not_found()` on `None`) — thin pass-throughs opening a read session and delegating with the actor threaded through (Trap 1). The `api/` route assembles the `Page` envelope and the single-row response.
  - [x] Every write command opens exactly one `with Session(get_engine(), expire_on_commit=False) as session:` and commits inside it (`AD-3`; `expire_on_commit=False` keeps the returned row projectable — the idiom `services/auth.py` documents and `services/departments.py` copies).
- [x] **Task 5: `api/v1/employees.py` (NEW) — the five routes, all Admin-gated** (AC: 1, 2, 3, 4, 5, 8, 11, 12)
  - [x] `POST /employees` → `Depends(require_role(authz.ROLE_ADMIN))`; request body model with `email`, `full_name`, `role`, `department_id`, `joining_date`, `password`, optional `manager_id`; returns the created `EmployeeResponse` (Trap 5 — **never** echo the password). Recommended status **201**.
  - [x] `GET /employees` → `Depends(require_role(authz.ROLE_ADMIN))` (Admin-only — **unlike departments**, whose GET was `any`); takes `PageParams`; passes the actor into the service; returns `Page[EmployeeResponse]`.
  - [x] `GET /employees/<id>` → `require_role(authz.ROLE_ADMIN)`; returns one `EmployeeResponse`, or `404` (service `not_found()`).
  - [x] `PATCH /employees/<id>` → `require_role(authz.ROLE_ADMIN)`; partial-update body model — the mutable six fields, each optional, **and no `password` field** (Trap 5); returns the updated `EmployeeResponse`. Status **200**. Use `model.model_dump(exclude_unset=True)` so an omitted field is left unchanged and a `null` is distinguishable from absent (relevant for `manager_id`, which may be set to `null`).
  - [x] `POST /employees/<id>/deactivate` → `require_role(authz.ROLE_ADMIN)`; no body; returns the updated `EmployeeResponse` (`is_active=false`). Status **200**.
  - [x] **Do NOT add a `DELETE /employees/<id>` route** (AC12) — an Employee is never physically deleted.
  - [x] `EmployeeResponse` (declared here, projected by hand like `me.py`/`departments.py`): `id`, `email`, `full_name`, `role`, `department` (`{id, name}` brief), `manager_id` (`uuid | None`), `joining_date`, `is_active`. **Never `password_hash`** (Trap 5). The Admin view *does* expose `manager_id` and `is_active` (unlike `MeResponse`, which hides them) — the Admin manages exactly these.
  - [x] Route module imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never `repositories/` or `domain/` (contract 2). Role literals come through `authz.ROLE_ADMIN`. Register in `api/v1/router.py`: add `employees` to the import and `api_v1_router.include_router(employees.router)`.
- [x] **Task 6: `tests/test_scoped_getters.py` — leave EXEMPT UNCHANGED; the new getters take the actor** (AC: 3, 4) 🚨 **See Trap 1**
  - [x] The new `list_employees`/`get_employee` take an `actor` parameter and apply `employee_scope_predicate`, so they **pass the guardrail without an EXEMPT entry**. Do **not** add them to EXEMPT — Employees *are* Employee-derived data, so the honest resolution is to take the actor (Story 1.5's departments were exempt precisely because they are *not* Employee data; that ground does not transfer). Confirm `test_scoped_getters.py` stays green with no edit.
  - [x] Verify `manager_id_of` and `count_active_direct_reports` are correctly **not** flagged (the former by its `_of` name, the latter by `count_`).
- [x] **Task 7: Backend tests** (AC: 1–12)
  - [x] `tests/integration/test_employees.py` (real-PG, `TestClient`) — model the fixture on `test_departments.py`'s `callers` (one active Employee per role in a shared department, a signed token each; `import app.main` at top so `CODE_TO_STATUS` is populated). Cover:
    - AC1: Admin `POST` creates an active Employee; the created Employee can then `POST /auth/login` and receive a token (prove the initial password works end-to-end).
    - AC2: no create/read/update/deactivate response body contains `password` or `password_hash`; the stored `password_hash` verifies against the supplied password.
    - AC3: Admin reads all (`GET` list + by-id), updates the mutable fields; a `PATCH` carrying a `password` field does not change the hash (it is ignored / not a re-issue path).
    - AC4: pagination clamp end-to-end (seed `> MAX_PAGE_SIZE` employees, assert `page_size == MAX_PAGE_SIZE` and the four-key envelope) — mirror `test_departments.py`'s clamp test.
    - AC5: every `/employees` endpoint (POST, GET list, GET by-id, PATCH, deactivate) returns `403 ACTION_NOT_PERMITTED` for a Manager and an Employee, with nothing read or written.
    - AC6: create and PATCH with an email already held by an **active** Employee → `409 EMAIL_ALREADY_IN_USE`; **and** by a **deactivated** Employee → also `409` (proves it counts deactivated rows and does not leak active-ness).
    - AC7: PATCH assigning self as manager → `400 REPORTING_CYCLE`; PATCH closing A→B→A → `400 REPORTING_CYCLE`; nothing persisted (verify the row is unchanged).
    - AC8: deactivate a Manager who has an **active** report → `409 EMPLOYEE_HAS_DIRECT_REPORTS`, still active; deactivate one whose only report is **already deactivated** → succeeds (proves *active* is the qualifier).
    - AC9: PATCH lowering role to `EMPLOYEE` while holding an active report → `409 EMPLOYEE_HAS_DIRECT_REPORTS`, role unchanged; the same PATCH after the report is deactivated → succeeds.
    - AC11: deactivate an Employee with no active report → `is_active` false, row persists, and a subsequent `POST /auth/login` with their credentials fails `401` (cannot authenticate).
    - AC12: assert the generated OpenAPI (`app.openapi()`) exposes **no** `delete` operation under `/api/v1/employees/{...}`.
    - `401` on every endpoint with no token; `404 RESOURCE_NOT_FOUND` on GET/PATCH/deactivate of a nonexistent id.
  - [x] Optionally a DB-free unit test for the cycle-detection logic if you extract it as a pure function over a `parent_of` callable (cheaper than proving every cycle shape through PG). The integration test still proves the two canonical shapes (self, A→B→A).
  - [x] Keep the full suite green: `test_vocabulary_literals.py` (picks up the three new codes automatically), `test_error_envelope.py`, `test_scoped_getters.py` (Trap 1 — MUST stay green, **unchanged**), `test_architecture.py`'s 7 import contracts, and `alembic check` via `test_model_migration_agreement.py`. **No migration is expected** (Trap 7).
- [x] **Task 8: Frontend — the Employees screen, Admin-only** (AC: 13)
  - [x] `src/api/employees.ts` (NEW) — typed hooks on `apiFetch`: `useEmployees()` (query, `GET /employees`, typed `Page<Employee>`), `useCreateEmployee()`, `useUpdateEmployee()`, `useDeactivateEmployee()` (mutations). Reuse the `Page<T>` type from `./departments` (or re-export it). On success, invalidate the employees query key. Export the surface from `src/api/index.ts`. **Unlike departments, `GET /employees` is Admin-only** — a non-Admin's query would `403`, so the screen is only mounted/enabled for an Admin (below).
  - [x] `src/features/employees/EmployeesPage.tsx` (NEW) — the Admin management screen. **Reuse `useDepartments()`** to populate the Department `<select>`, and `useEmployees()` (the same list) to populate the optional Manager `<select>`. The create form carries email, full name, role (`EMPLOYEE`/`MANAGER`/`ADMIN`), department, joining date, **initial password**, and optional manager. The list renders edit (email/name/role/department/manager/joining-date) and Deactivate controls. Surface each refusal by **`code`, never `message`** (as `client.ts` guides): `EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`, `EMPLOYEE_HAS_DIRECT_REPORTS`. The three wire strings are each restated **once** here (the frontend's single home for them, `AD-21`, as the departments screen restates `DEPARTMENT_NOT_EMPTY`). Copy the departments screen's error-surfacing shape (`writeErrorMessage`/`deleteErrorMessage`, per-row error state, `mutation.reset()` on form open/cancel).
  - [x] `NFR-16` control-hiding is **never the only guard** (AC5): render the whole screen only for `useMe().data.role === 'ADMIN'`, but the real refusal is always the server's `403`.
  - [x] Wire into `App.tsx`'s `AppShell` beside `DepartmentsPage` — minimally, no router (the spine defers routing; do not add one). Render `EmployeesPage` only for an Admin. `src/index.css` — add the screen's styles (reuse the `dept-*` patterns or add `emp-*` equivalents).
- [x] **Task 9: Prove it end-to-end** (AC: 1–13)
  - [x] Backend: run the full suite; record counts in Dev Agent Record. Run `lint-imports` in `backend/` and confirm 0 broken. Confirm `test_scoped_getters.py` passes **unchanged** (Trap 1) with the two new actor-taking getters.
  - [x] Frontend: `npm run build` (`tsc -b && vite build`) typechecks and builds; `npm run lint` (oxlint) is clean. There is **no frontend test runner** — so, as Stories 1.2/1.3/1.5 did, the frontend proof is the passing typecheck/lint/build plus a **declared manual click-through** of: create an Employee (with password) → log in as them; assign a manager; trigger each refusal (duplicate email, self-manager cycle, deactivate-with-active-report). Record the click-through gap explicitly.

## Dev Notes

### What this story is, and where it sits

Story 1.6 is the **most complex story in Epic 1** and the second consumer of the Story 1.4 primitives (after 1.5). It manages the `employee` table — the row every authorization decision in the entire product keys on. Where Story 1.5's Department was `{id, name}` with one refusal (`DEPARTMENT_NOT_EMPTY`), an Employee carries a reporting edge, a role, an active flag and a credential, and this story adds **four** refusal paths: `EMAIL_ALREADY_IN_USE` (409), `REPORTING_CYCLE` (400), `EMPLOYEE_HAS_DIRECT_REPORTS` (409), and — deferred to Epic 2 — `EMPLOYEE_HAS_PENDING_REQUESTS` (409).

You are **copying the Story 1.5 pattern wholesale** for the CRUD/pagination/role-gate/404 machinery (read `1-5-manage-departments.md` and the four files it produced — they are the template), and **layering four new guards** on top. The department implementation (`repositories/department.py`, `services/departments.py`, `api/v1/departments.py`, `tests/integration/test_departments.py`) is the shape; this story is that shape plus the reporting-line invariants.

**Scope of every `/employees` endpoint is Admin-only, scope `all`** (api-contracts §4.2). That is the one structural difference from departments to hold onto: departments' `GET` was `any` role; here **every** `/employees` endpoint — including the reads — is `require_role(ROLE_ADMIN)`. There is no per-row *data* scoping in this story (an Admin sees everyone). The Manager-scoped Employee reads — `/team` (`FR-19`), `GET /employees/<id>/balances` (`FR-07`, reports) — are **later stories** and different getters; do not build them here.

**It is NOT:**
- **Not** a schema change. `employee`, `UNIQUE (email)`, `CHECK (role IN (...))` and `CHECK (id <> manager_id)` all exist from migration `0002`. Add no column, write no migration (Trap 7).
- **Not** the pending-request guard. AC10 is **vacuous** — no `leave_request` table exists. Do not write a query against a table that is not there (Trap 6).
- **Not** a `PATCH /me`-style `FORBIDDEN_FIELD` rejection. That is Story 1.8, a different resource with its own `G5` decision. Here, PATCH simply has no password field; an unknown field is ignored (Trap 5).
- **Not** the reports-scope resolver's live wiring. Story 1.7 wires `Scope.REPORTS` to Manager reads. This story uses only `Scope.ALL` (Trap 1).
- **Not** a change to `get_current_employee`, `resolve_actor`, the login path, or the `G4` decision. Leave the auth path exactly as it is.

### 🚨 Seven traps, in the order they will bite

**1. The scoped-getter guardrail resolves DIFFERENTLY here than in Story 1.5 — take the actor, do NOT go EXEMPT.** `tests/test_scoped_getters.py` flags every `repositories/*.py` function whose name starts with `get_`/`list_`/`find_`/`fetch_` AND takes a `session`, and requires each to take an `actor` param or be EXEMPT. Your new `list_employees(session, ...)` and `get_employee(session, ...)` both match. In Story 1.5, `list_departments`/`get_department` went EXEMPT on the ground that *a Department is not Employee data*. **That ground does not transfer: an Employee row IS Employee-derived data — exactly what `AD-10` governs.** So the honest resolution is the one the rule prescribes: **give both getters an `actor` parameter and apply `scoping.employee_scope_predicate(Scope.ALL, actor)` in the `WHERE`.** The predicate resolves to `true()` for an Admin (scope `all`), so the query is unrestricted — *which is correct*, an Admin's scope genuinely is everyone — but the getter now takes the actor and applies a scope predicate, keeping the guardrail's invariant literally true. This is `repositories/scoping.py`'s **first live consumer** (it was built in Story 1.4 for exactly this). Story 1.7 later extends the *selection* of the scope (Admin→`ALL`, Manager→`REPORTS`) without touching these signatures. **Do NOT add these to EXEMPT** — widening EXEMPT to cover Employee data would gut the guardrail's entire purpose. `count_active_direct_reports` (`count_`, returns `int`) and `manager_id_of` (`_of`, returns a scalar) are correctly not candidates.

**2. The reporting-cycle walk is the gate; `CHECK (id <> manager_id)` is only the backstop (`AD-23`, `G7`).** Assigning manager `M` to Employee `E` must be refused `400 REPORTING_CYCLE` when `M == E` (self) or when `E` is an ancestor of `M` (walking `M`'s `manager_id` chain upward reaches `E`). Algorithm, **inside the assignment transaction**: `cur = M; visited = set()`; loop — if `cur is None`: no cycle, stop; if `cur == E.id`: **cycle** → raise `REPORTING_CYCLE`; if `cur in visited`: a *pre-existing* cycle in the data — stop defensively (do not loop forever); `visited.add(cur); cur = manager_id_of(cur)`. The DB's `CHECK (id <> manager_id)` catches only the one-node self-loop and, if it ever fires, is a **500** — so the self case must be caught by the walk *before* the write, not left to the constraint. On **create**, the walk is vacuous (the new row has no id, so nothing can reach it) — but you must still verify a supplied `manager_id` **names a real Employee** or the NOT-checked FK insert 500s (see Trap below). On **PATCH**, the walk is the real work.
   - *Manager existence (a sub-trap of Trap 2):* if `manager_id` is supplied (create or patch) and names no Employee, the `ForeignKey` insert/update raises `IntegrityError` → 500. Pre-check by loading the proposed manager; if absent, raise `authz.not_found()` (`404`) — the manager they named is, to them, a resource that does not exist. (api-contracts fixes no dedicated code for this; `404` is the consistent choice and is flagged as a minor decision in "Open questions".)

**3. Email uniqueness is a service gate; `UNIQUE (email)` is the backstop (`G2`, `AD-5`).** Before any create/patch write, call `get_by_email(new_email)`. On **create**: if any row exists (active *or* deactivated) → `409 EMAIL_ALREADY_IN_USE`. On **PATCH**: if a row exists **and its id differs from the Employee being edited** → `409` (a no-op re-set of the same Employee's own email is fine). The refusal message and `details` must **not disclose whether the holder is active** (`G2`). And, exactly as `delete_department` guards the FK RESTRICT, wrap the commit in `try/except IntegrityError` and re-raise `EMAIL_ALREADY_IN_USE` — the `UNIQUE (email)` constraint is the TOCTOU backstop, never the surfaced 500.

**4. Deactivation and demotion are two doors to the same orphaning — both count ACTIVE reports (`AD-22`, `G8`).** `count_active_direct_reports(manager_id)` counts Employees with `manager_id = :id` **AND `is_active` true**. Deactivation (AC8) and a demotion to `EMPLOYEE` (AC9) are each refused `409 EMPLOYEE_HAS_DIRECT_REPORTS` when that count is `> 0`. "Below `MANAGER`" means the new role is `ROLE_EMPLOYEE` — `MANAGER` and `ADMIN` are not below it, so a `MANAGER→ADMIN` change is *not* guarded by this rule. The `is_active` qualifier is load-bearing: a Manager whose only report is *already deactivated* may be deactivated or demoted — a deactivated report is not orphaned (they cannot submit requests). The refusal's `details` should name the count (`NFR-17` — "names the obstruction with a number"), e.g. `{"active_direct_reports": n}`.

**5. The password: hashed once on create, never echoed, never re-issued (`FR-04`, `NFR-01`, `AD-14`, PRD §6).** Create hashes the supplied `password` with `security.hash_password` (produces a `$2b$12$...` bcrypt digest) and stores it once. **No `/employees` response — not create, not read, not update, not deactivate — carries `password` or `password_hash`**; the `EmployeeResponse` projection simply omits it (like `MeResponse`). PATCH has **no** `password` field: there is no re-issue path (a client that sends one has it ignored, not rejected — that `FORBIDDEN_FIELD` behaviour is Story 1.8's `PATCH /me`, not this resource). *Known rough edge:* `hash_password` raises `ValueError` on a password over 72 UTF-8 bytes (bcrypt's limit) — with no vocabulary code for "password too long", that would surface as a 500. This matches Story 1.5's deferred server-side-name-validation gap and is left to the same future enveloped-validation contract; note it, do not block on it (see "Open questions").

**6. AC10 (pending-request guard) is VACUOUS — write no `leave_request` query, declare no code for it.** No `leave_request` table exists in Epic 1, so no Employee can hold a Pending request and the guard cannot execute. Do **not** implement a query against a non-existent table, and do **not** declare `EMPLOYEE_HAS_PENDING_REQUESTS` in `vocabulary.py` — the codebase's discipline is to declare a code *with* its raise site, and this code's raise site is Epic 2's Leave Request submission story (which creates the table and adds the guard as a running test). Document the seam in `deactivate_employee`'s docstring ("the Pending-request guard AD-22 also requires lands in Epic 2, when `leave_request` exists"). This is the epic's explicit instruction (epics.md line 790).

**7. No migration — and `alembic check` will tell on you.** `employee`, its `UNIQUE (email)`, its `role` CHECK and its `CHECK (id <> manager_id)` all exist (migration `0002`). This story adds no column and no table. `test_model_migration_agreement.py` runs `alembic check`; if you touch a model, it fails. If you find yourself writing a migration, stop — you have drifted out of scope.

### Architecture compliance

- **`AD-1` (one-way imports).** `api → services → {repositories, domain}`; `repositories → domain`; `services → core` (for `security`). The new route (`api/v1/employees.py`) imports `services/employee` and the `api/`-layer `dependencies`/`pagination`, never `repositories/` or `domain/`. `services/employee` imports `repositories/employee`, `repositories/scoping`, `repositories/engine`, `domain/vocabulary`, `domain/errors`, `services/authorization`, and `core/security`. Enforced by the 7 import contracts in `test_architecture.py` — no new contract should be needed. [Source: ARCHITECTURE-SPINE.md#AD-1]
- **`AD-10` / `AD-14` (authorization is server-side; the read is scoped in SQL; the role gate is at the boundary).** Every `/employees` endpoint is `require_role(ROLE_ADMIN)` — the role gate refuses a non-Admin `403` in the `api/` dependency *before any row is read* (`G3`, AC5). The reads take the actor and apply `employee_scope_predicate(Scope.ALL, actor)` (Trap 1). A nonexistent id is `404` via `not_found()`. [Source: api-contracts.md §1, §4.2; ARCHITECTURE-SPINE.md#AD-10]
- **`AD-5` (schema is the backstop, service is the gate).** Applied **twice**: the `UNIQUE (email)` constraint backstops the `EMAIL_ALREADY_IN_USE` service gate (Trap 3), and the `CHECK (id <> manager_id)` backstops the `REPORTING_CYCLE` cycle-walk gate (Trap 2). Both wrap the commit in `try/except IntegrityError` and re-raise the typed refusal, exactly as `delete_department` does for the FK RESTRICT. [Source: ARCHITECTURE-SPINE.md#AD-5; erd.md §4.2]
- **`AD-22` (deactivation guards protect the auto-approval path).** `count_active_direct_reports > 0` blocks both deactivation (AC8) and demotion-below-`MANAGER` (AC9, `AD-22` as amended by `G8`). The Pending-request door (AC10) is Epic 2's (Trap 6). [Source: ARCHITECTURE-SPINE.md#AD-22]
- **`AD-23` (the reporting graph is acyclic).** The service walks the reporting chain inside the assignment transaction and refuses a cycle `400 REPORTING_CYCLE`; the `CHECK` is the backstop (Trap 2). [Source: ARCHITECTURE-SPINE.md line 155; erd.md §4.2]
- **`AD-3` (one transaction per command).** Each write command opens one `with Session(get_engine(), expire_on_commit=False)` and commits inside it — copy `services/departments.py`. All guard reads (email lookup, cycle walk, report count) run **inside** the same transaction as the write, so the check and the write are atomic up to the `IntegrityError` backstop.
- **`AD-21` (one canonical vocabulary).** `EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`, `EMPLOYEE_HAS_DIRECT_REPORTS` declared once in `domain/vocabulary.py`; the frontend restates each *matched string* once (as the departments screen does for `DEPARTMENT_NOT_EMPTY`). Role constants reach `api/` only through `services/authorization`.
- **`NFR-11` (bounded result sets).** `GET /employees` reuses the `api/v1/pagination.py` module Story 1.5 built — `Page[EmployeeResponse]`, `PageParams`, the `50`/`100` bound. Do not re-declare it. [Source: ARCHITECTURE-SPINE.md *Pagination*]

### Previous story intelligence — Story 1.5 (read `1-5-manage-departments.md`; it is the template)

- **The whole CRUD/route/pagination/404 machinery is already written for departments — copy it.** `api/v1/pagination.py` (the `Page[T]` generic, `PageParams`, `DEFAULT_PAGE_SIZE=50`/`MAX_PAGE_SIZE=100`) is done and reused as-is. `services/departments.py` shows the one-transaction-per-command idiom, the load-or-`not_found()` on PATCH/DELETE, the module-level message constants, and — critically — the `try/except IntegrityError` → typed-409 backstop you will replicate for `UNIQUE (email)`.
- **`require_role(authz.ROLE_ADMIN)` returns the actor.** `actor: Actor = Depends(require_role(authz.ROLE_ADMIN))` both gates and hands you the caller — you *need* the actor here (unlike departments) to thread into the scoped reads (Trap 1). It raises `403 ACTION_NOT_PERMITTED` at the boundary before the body runs.
- **`authz.not_found()` is the one 404 raise site**, reached from the *service* (`from app.services import authorization as authz`). Byte-identical, empty details.
- **`CODE_TO_STATUS` is populated from `main.py`, not `errors.py`.** Add the three new entries there; leave `errors.py` untouched.
- **`api/` projects responses by hand** (never `from_attributes`) — `me.py` and `departments.py` both do. `EmployeeResponse` is built field-by-field so the omission of `password_hash` is by construction, not by luck. A `TYPE_CHECKING` import of the ORM into `api/` still breaks import-linter (proven in 1.3) — type the projected input as `object`/a Protocol.
- **`expire_on_commit=False`** preserves loaded attributes after the session closes but does **not** lazy-load a relationship — so `joinedload(Employee.department)` in the reads is mandatory for the response to carry `department.name` (exactly why `get_by_id_with_department` eager-loads for `/me`).
- **Integration test shape:** `tests/integration/` runs against real PostgreSQL and skips loudly when absent; `import app.main` at the top populates `CODE_TO_STATUS`. `test_departments.py`'s `callers` fixture (one Employee per role in a shared department, a signed token each, `security.hash_password` + `security.create_token`, commit through `get_engine()`) is the copy-paste template. For AC1's "can immediately authenticate", drive `POST /api/v1/auth/login` with the created Employee's email + the plaintext password.
- **Story 1.5's deferred findings are relevant precedent:** server-side field validation (empty/whitespace names) was deferred pending an enveloped-validation contract. The analogous gaps here (whitespace name/email, >72-byte password, email format) follow the same deferral — note them, don't invent a new validation-error contract in this story.

### Verified library / framework facts (checked against installed pins)

- **Stack:** Python 3.13 · FastAPI 0.139.0 · Pydantic 2.13.4 · SQLAlchemy 2.0.51 · Alembic 1.18.5 · psycopg 3.3.4 · PostgreSQL 18 · PyJWT 2.13.0 · pwdlib 0.3.0 · bcrypt 5.0.0 · pytest 9.1.1 · import-linter 2.13. Frontend: React 19.2 · @tanstack/react-query 5.101 · Vite 8.1 · TypeScript 6.0 · oxlint 1.73 (build = `tsc -b && vite build`; lint = `oxlint`; **no test runner installed**).
- **`security.hash_password(password)`** returns a salted bcrypt digest and **raises `ValueError` on a password > 72 UTF-8 bytes** (bcrypt 5.0.0 no longer truncates). It is already the seed's hasher and `test_departments.py`'s fixture hasher. `security.create_token(str(id), role)` mints the JWT for the login-after-create assertion.
- **`scoping.employee_scope_predicate(Scope.ALL, actor)`** returns SQLAlchemy `true()` — compose it into `select(Employee).where(Employee.id == id, employee_scope_predicate(Scope.ALL, actor))`; the `true()` adds no restriction but keeps the getter honest (Trap 1). `Scope` and `employee_scope_predicate` live in `repositories/scoping.py`.
- **SQLAlchemy count + page:** `session.scalars(select(Employee).options(joinedload(Employee.department)).order_by(...).limit(limit).offset(offset)).unique().all()` for the page (`.unique()` is required when `joinedload` is present on a collection-free path only if duplicates appear — safe to include); `session.scalar(select(func.count()).select_from(Employee).where(predicate))` for `total`.
- **Pydantic partial update:** the PATCH body uses `Optional` fields; read changes with `body.model_dump(exclude_unset=True)` so an omitted field is untouched and an explicit `null` (e.g. clearing `manager_id`) is distinguishable from absent.
- **FastAPI pagination:** reuse `PageParams` (the `Annotated[int, Query(...)] = 1` form — a bare `= Query(...)` default breaks a DB-free `PageParams()` construction; see Story 1.5's Debug Log). Parameterize the response as `Page[EmployeeResponse]`.
- **TanStack Query mutations:** `useMutation` + `queryClient.invalidateQueries({ queryKey: EMPLOYEES_QUERY_KEY })` in `onSuccess`, mirroring `departments.ts`.

### Testing standards

- **`pytest` is the build (`F-14`); there is no CI.** The full suite must stay green. Story 1.5 left the suite at **122 passing**; this story adds `test_employees.py` (the AC1–AC12 integration cases) and optionally a cycle-detection unit test. The auto-parametrized vocabulary/literal and scoped-getter scans pick up the new modules automatically — and `test_scoped_getters.py` must stay green **without an EXEMPT edit** (Trap 1), which is the proof the getters were scoped correctly rather than exempted.
- **Where each test goes:** `tests/integration/test_employees.py` (real-PG, `TestClient`) for every AC (the CRUD, the four refusal paths, the role gate, the pagination clamp, the 404/401, the login-after-create, the no-DELETE-operation assertion). A DB-free unit test only for the cycle-detection function if you extract it purely.
- **`NFR-15`:** test the guarantees (the four refusals, the role-gate boundary, the scope predicate, the page clamp, the login-after-create, the non-disclosure of the password), not trivial getters.
- **Governing FRs:** `FR-04` (Employee management — fully realized here) and the `FR-17`/PRD §6 no-re-issue rule; `AD-22`/`AD-23` guards. `NFR-11`'s bound is inherited from Story 1.5.
- **Frontend proof** is `tsc -b`/`vite build` + `oxlint` + a **declared manual click-through** (no test runner exists). Record the click-through gap in the Dev Agent Record exactly as Stories 1.2/1.3/1.5 did.

### Project Structure Notes

- **New (backend):**
  - `backend/app/services/employee.py` — create/update/deactivate/list/get orchestration and the four refusals.
  - `backend/app/api/v1/employees.py` — the five routes, all Admin-gated; `EmployeeResponse`.
  - `backend/tests/integration/test_employees.py`.
- **Modified (backend):**
  - `backend/app/repositories/employee.py` — `list_employees`, `get_employee` (both actor-scoped), `count_active_direct_reports`, `manager_id_of`, and the write helpers. **Existing `get_by_email`/`get_by_id_with_department` unchanged.**
  - `backend/app/domain/vocabulary.py` — three new codes + `__all__` + docstring line.
  - `backend/app/main.py` — three `CODE_TO_STATUS` entries.
  - `backend/app/api/v1/router.py` — register the employees router.
- **New (frontend):**
  - `frontend/src/api/employees.ts` — typed hooks.
  - `frontend/src/features/employees/EmployeesPage.tsx` — the Admin-only screen.
- **Modified (frontend):**
  - `frontend/src/api/index.ts` — export the employees surface.
  - `frontend/src/App.tsx` — mount `EmployeesPage` (Admin-only) in the shell.
  - `frontend/src/index.css` — Employees screen styles.
- **Untouched (must stay so):** `api/v1/pagination.py` (reused as-is — do NOT edit), `tests/test_scoped_getters.py` (Trap 1 — the getters take the actor, so **no EXEMPT edit**), `api/v1/errors.py` (map populated from `main.py`), `api/v1/me.py`/`auth.py`/`health.py`/`departments.py`/`dependencies.py` (consumed, not changed), `services/auth.py`/`authorization.py`/`departments.py` (consumed), `repositories/department.py`/`scoping.py`/`models.py` (consumed; `scoping.py` gets its first live consumer but is not edited), all migrations, `test_architecture.py` (no new import contract needed).

### References

- [epics.md#Story 1.6](../planning-artifacts/epics.md) — the story statement and all thirteen criteria, verbatim (lines 728–807); the `403`-here / `404`-in-1.7 settlement (line 760); the `EMAIL_ALREADY_IN_USE`-before-the-write / never-from-`UNIQUE` rule (lines 762–765); the `REPORTING_CYCLE` self-approval consequence (line 772); the `EMPLOYEE_HAS_DIRECT_REPORTS` deactivation (lines 774–777) and demotion (lines 779–784) doors; the **vacuous** Pending-request guard (lines 786–790); the no-delete / email-never-reusable rule (lines 797–800); the Admin screen and password-communicated-out-of-band (lines 802–807).
- [epics.md#Story 1.5](../planning-artifacts/epics.md) — the pattern this story copies; "Stories 1.5 and 1.6 consume these primitives rather than each inventing a role check" (line 680).
- [epics.md#FR-04](../planning-artifacts/epics.md) — Employee management, initial password, no re-issue, deactivation-not-deletion, manager establishes the Direct Report edge (line 42).
- [epics.md#G7 / #G8 / #G2 / #G3](../planning-artifacts/epics.md) — the reporting-cycle refusal (lines 400–412), the demotion door (lines 414–424), the duplicate-email code (lines 338–348), the `403`-vs-`404` role/scope split (lines 350–366).
- [api-contracts.md §1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the status table; the `403`-decided-before-any-row-is-read rule (`G3`); the Pagination envelope.
- [api-contracts.md §2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — `EMAIL_ALREADY_IN_USE`→409, `REPORTING_CYCLE`→400, `EMPLOYEE_HAS_DIRECT_REPORTS`→409, `EMPLOYEE_HAS_PENDING_REQUESTS`→409 (the last deferred, Trap 6); the `{code, message, details}` envelope.
- [api-contracts.md §4.2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the five `/employees` endpoints, Role `Admin`, Scope `all`; the initial-password / no-password-on-update / non-disclosure rules; "An Employee is never deleted."
- [ARCHITECTURE-SPINE.md#AD-22 / #AD-23 / #AD-5 / #AD-10 / #AD-3](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — the deactivation guards (line 193); the acyclic reporting graph (line 155); constraint-is-backstop; absence-is-404; one-transaction-per-command.
- [erd.md#EMPLOYEE](../planning-artifacts/module-4-erd/erd.md) — the `employee` columns (lines 172–183); `UNIQUE (email)` and the never-reusable email (line 354); `CHECK (id <> manager_id)` the backstop (line 358); `CHECK (role IN (...))` (line 357); the initial-password GAP-1 provenance (lines 448–452); the `employee → employee` self-edge (line 309).
- [1-5-manage-departments.md](1-5-manage-departments.md) — the CRUD/route/pagination/404/`IntegrityError`-backstop template, first-hand; its deferred server-side-validation finding (the precedent for this story's password/name/email validation gaps).
- Current state, read in full during story creation: [backend/app/repositories/employee.py](../../backend/app/repositories/employee.py) · [repositories/models.py](../../backend/app/repositories/models.py) · [repositories/scoping.py](../../backend/app/repositories/scoping.py) · [repositories/department.py](../../backend/app/repositories/department.py) · [services/departments.py](../../backend/app/services/departments.py) · [services/authorization.py](../../backend/app/services/authorization.py) · [core/security.py](../../backend/app/core/security.py) · [api/v1/departments.py](../../backend/app/api/v1/departments.py) · [api/v1/pagination.py](../../backend/app/api/v1/pagination.py) · [api/v1/me.py](../../backend/app/api/v1/me.py) · [api/v1/dependencies.py](../../backend/app/api/v1/dependencies.py) · [domain/vocabulary.py](../../backend/app/domain/vocabulary.py) · [main.py](../../backend/app/main.py) · [tests/test_scoped_getters.py](../../backend/tests/test_scoped_getters.py) · [tests/integration/test_departments.py](../../backend/tests/integration/test_departments.py) · [tests/integration/test_role_gate.py](../../backend/tests/integration/test_role_gate.py).
- Frontend patterns copied: [frontend/src/api/departments.ts](../../frontend/src/api/departments.ts) · [features/departments/DepartmentsPage.tsx](../../frontend/src/features/departments/DepartmentsPage.tsx) · [api/index.ts](../../frontend/src/api/index.ts) · [App.tsx](../../frontend/src/App.tsx) · [api/client.ts](../../frontend/src/api/client.ts).

### Open questions (for the dev agent — resolve during implementation, do not block story creation)

1. **Nonexistent `manager_id` on create/patch (Trap 2 sub-trap).** api-contracts fixes no dedicated code. Recommended: pre-check and raise `not_found()` (`404`) — the named manager does not exist within the actor's scope. Confirm this reads sensibly on the frontend (a manager `<select>` populated from live employees makes it near-unreachable anyway).
2. **>72-byte password / whitespace-only name or email / malformed email (Trap 5).** No enveloped validation-error contract exists yet (Story 1.5 deferred the equivalent for department names). Recommended: leave to that future contract; a >72-byte password will 500 via `hash_password`'s `ValueError` — acceptable, matching 1.5's precedent. Do not invent a new code here.
3. **Assigning a *deactivated* Employee as a Manager.** `AD-22` prevents deactivating someone who *has* active reports, but nothing prevents naming a deactivated Employee as a *new* manager (their reports would then have an approver who cannot authenticate). No AC covers it; recommend allowing it (matching AC silence) and noting it as a possible future guard — do not expand scope.
4. **Deactivate success status/body.** api-contracts fixes only non-2xx (as with `G6`). Recommended: `200` with the updated `EmployeeResponse` so the client sees `is_active=false`. Confirm the React hook expects the same.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — dev-story workflow.

### Debug Log References

- **Stale `department` relationship on a `department_id` PATCH.** The first run of
  `test_admin_updates_every_mutable_field` failed: after a PATCH changed `department_id`,
  the response projected the OLD department. Cause — SQLAlchemy's identity map keeps the
  already-loaded `.department` relationship; the reloaded row (same identity) is not
  refreshed by a plain `joinedload` because it is already present. Fix — `load_employee`
  reloads with `.execution_options(populate_existing=True)`, overwriting the mapped
  instance with the DB row and freshly-joined department. All 25 integration cases green
  after. (create passed before the fix only because its `.department` was never loaded.)

### Completion Notes List

Story 1.6 implemented in full — all 13 ACs satisfied, all 9 tasks complete.

**Backend (Tasks 1–7):**
- Three vocabulary codes declared with their raise sites (`EMAIL_ALREADY_IN_USE`→409,
  `REPORTING_CYCLE`→400, `EMPLOYEE_HAS_DIRECT_REPORTS`→409); `EMPLOYEE_HAS_PENDING_REQUESTS`
  deliberately NOT declared (Trap 6 — vacuous in Epic 1, no `leave_request` table). Wired in
  `main.py`'s `CODE_TO_STATUS`; `errors.py` untouched.
- **Trap 1 resolved by scoping, not exemption:** `list_employees`/`get_employee` take the
  `actor` and apply `employee_scope_predicate(Scope.ALL, actor)` — `repositories/scoping.py`'s
  first live consumer. `test_scoped_getters.py` passes UNCHANGED (no EXEMPT edit).
  `count_active_direct_reports` (`count_`) and `manager_id_of` (`_of`) are correctly not
  candidates; `load_employee` (write-path loader) uses `load_`, not a read-verb prefix.
- Four refusals in `services/employee.py`, each a service gate before the write with the DB
  constraint as the AD-5 backstop (`IntegrityError` → typed 409 for `UNIQUE (email)`). Cycle
  detection extracted as a pure `_would_close_cycle(target, start, parent_of)` — unit-tested
  DB-free (5 cases) plus the two canonical shapes end-to-end. Manager-existence pre-check
  raises `not_found()` (404) before the FK can 500 (Trap 2 sub-trap, per Open Question 1).
- Five Admin-gated routes in `api/v1/employees.py`; `EmployeeResponse` projected by hand,
  never carries `password`/`password_hash` (Trap 5), exposes `manager_id`/`is_active`. No
  DELETE route (AC12). Registered in `router.py`.
- **No migration** (Trap 7): `alembic check` via `test_model_migration_agreement.py` stays
  green — no model touched.
- **Tests:** `tests/integration/test_employees.py` (25 cases, real PG) covers AC1–AC12
  including login-after-create, the deactivated-email 409, both cycle shapes, the
  active-vs-deactivated report qualifier for deactivation AND demotion, the MANAGER→ADMIN
  boundary, deactivation-persists + can-no-longer-authenticate, and the no-DELETE-operation
  OpenAPI assertion. Plus `tests/test_reporting_cycle.py` (5 DB-free cases).
- **Full suite: 156 passed** (was 122; +25 integration, +5 cycle unit, +auto-parametrized
  vocabulary/scoped-getter picking up the new modules). `lint-imports`: 7 contracts kept, 0
  broken.

**Frontend (Task 8):**
- `src/api/employees.ts` — typed hooks (`useEmployees`/`useCreateEmployee`/
  `useUpdateEmployee`/`useDeactivateEmployee`), reusing `Page<T>` from `./departments`,
  invalidating `EMPLOYEES_QUERY_KEY` on success. Exported from `src/api/index.ts`.
- `src/features/employees/EmployeesPage.tsx` — Admin-only screen (mount gated on
  `useMe().role === 'ADMIN'`, the server's 403 is the real guard). Create form with initial
  password + optional manager; inline edit of the six mutable fields; deactivate. Refusals
  surfaced by `code` (`EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`,
  `EMPLOYEE_HAS_DIRECT_REPORTS`), each wire string restated once. Reuses `useDepartments()`
  and `useEmployees()` for the selects. Mounted in `App.tsx`'s shell; `emp-*` styles added.

**Frontend proof / declared gap (Task 9):** `npm run build` (`tsc -b && vite build`)
typechecks and builds clean; `npm run lint` (oxlint) is clean. As with Stories 1.2/1.3/1.5,
there is **no frontend test runner**, and the api/web containers run baked images (no bind
mount), so a live click-through would require a rebuild. The click-through of create → login
as the new hire; assign a manager; trigger each refusal (duplicate email, self-manager
cycle, deactivate-with-active-report) is therefore **declared, not executed in-session** —
recorded here as a gap. The equivalent backend flows are each proven end-to-end by the 25
integration cases against real PostgreSQL.

**Open questions resolved:** (1) nonexistent `manager_id` → `not_found()` (404), as
recommended. (2) >72-byte password / whitespace / malformed email left to the future
enveloped-validation contract (matches Story 1.5's deferral) — not blocked. (3) a
deactivated Employee may still be named a new manager (AC silence, no new guard added). (4)
deactivate returns `200` with the updated `EmployeeResponse` (`is_active=false`).

### File List

**New (backend):**
- `backend/app/services/employee.py`
- `backend/app/api/v1/employees.py`
- `backend/tests/integration/test_employees.py`
- `backend/tests/test_reporting_cycle.py`

**Modified (backend):**
- `backend/app/domain/vocabulary.py`
- `backend/app/main.py`
- `backend/app/repositories/employee.py`
- `backend/app/api/v1/router.py`

**New (frontend):**
- `frontend/src/api/employees.ts`
- `frontend/src/features/employees/EmployeesPage.tsx`

**Modified (frontend):**
- `frontend/src/api/index.ts`
- `frontend/src/App.tsx`
- `frontend/src/index.css`

### Change Log

- 2026-07-11 — Story 1.6 implemented. Employee management (`FR-04`): five Admin-gated
  `/employees` endpoints with the four refusal paths (`EMAIL_ALREADY_IN_USE`,
  `REPORTING_CYCLE`, `EMPLOYEE_HAS_DIRECT_REPORTS`; `EMPLOYEE_HAS_PENDING_REQUESTS` deferred
  to Epic 2 per Trap 6). First live consumer of `repositories/scoping.py` (Trap 1 — reads
  take the actor, `test_scoped_getters.py` unchanged). No migration (Trap 7). Admin-only
  Employees screen on the frontend. Full backend suite 156 passing; 7 import contracts kept;
  frontend build/lint clean. Status: ready-for-dev → in-progress → review.

### Review Findings

Code review 2026-07-11 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Acceptance
Auditor found **no AC/trap violations** — all 13 ACs and 7 traps satisfied. Findings below
are correctness/robustness issues surrounding the (correct) core.

**Patch (actionable now):**

- [x] [Review][Patch] Blanket `except IntegrityError → EMAIL_ALREADY_IN_USE` mislabels non-email constraint violations [backend/app/services/employee.py:175] — **FIXED 2026-07-11.** Added a department existence pre-check → `authz.not_found()` (404) in both `create_employee` and `update_employee`, mirroring the manager pre-check (removes the realistic deleted-department vector). Made the `IntegrityError` backstop precise via `_email_conflicts(...)`: it now re-raises `EMAIL_ALREADY_IN_USE` only for a genuine email TOCTOU collision; any other constraint (invalid `role`, explicit `null` on a required field) is re-raised untouched (honest 500) rather than mislabeled. The clean-4xx treatment of an invalid `role`/blank field remains the deferred enveloped-validation contract (Open Q2). 156 backend tests pass.
- [x] [Review][Patch] Admin-only employees query fires for every authenticated non-Admin [frontend/src/features/employees/EmployeesPage.tsx:112] — **FIXED 2026-07-11.** `useEmployees` now accepts `{ enabled }`; `EmployeesPage` passes `enabled: me.data?.role === 'ADMIN'`, so a non-Admin never issues the `GET /employees` the server 403s. Mount gate reuses the same `isAdmin`. Typecheck/lint/build clean.

**Deferred (checked off, tracked in deferred-work.md):**

- [x] [Review][Defer] Employees list + Manager dropdown capped at the first 50 rows, no pagination UI [frontend/src/features/employees/EmployeesPage.tsx:130] — deferred, needs pagination UI (same gap as departments)
- [x] [Review][Defer] AD-22 no-orphan invariant incomplete: an active report can be placed under a deactivated manager (Open Q3, allowed by design) and the report-count guard is non-atomic with no DB backstop (concurrent create-under-M + deactivate-M can orphan) [backend/app/services/employee.py:272] — deferred, consequence (auto-approval) vacuous until Epic 2
- [x] [Review][Defer] Email uniqueness is case/whitespace-sensitive; `email: str` (not `EmailStr`), no normalization — `Foo@x` and `foo@x` are distinct accounts [backend/app/services/employee.py:154] — deferred, pre-existing (login shares `get_by_email`); pending the enveloped-validation contract (Open Q2)
- [x] [Review][Defer] A password over 72 UTF-8 bytes raises `ValueError` in `hash_password` → 500 [backend/app/services/employee.py:162] — deferred, explicitly sanctioned by Trap 5 / Open Q2
- [x] [Review][Defer] Unbounded `page` query param → `offset` can overflow bigint → 500 [backend/app/api/v1/pagination.py:82] — deferred, pre-existing in the shared `PageParams` from Story 1.5 (affects departments too)

**Dismissed as noise (4):** no-op `PATCH {"role":"EMPLOYEE"}` on an already-EMPLOYEE row with reports returning 409 (anomalous pre-state, harmless); deactivating an already-deactivated Employee returning 200 (acceptable idempotency); create-form submit guard omitting `joining_date`/`full_name` (HTML `required` covers real users); empty `PATCH {}` no-op (harmless).
