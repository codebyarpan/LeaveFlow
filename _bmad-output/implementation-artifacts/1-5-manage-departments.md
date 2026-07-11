---
baseline_commit: 4dbf35d9d00760c8cde78a0fc686835414a09b57
---

# Story 1.5: Manage Departments

Status: done

Epic: 1 — Secure Access and Organization Administration (Phase 1, correctness core)
Story Key: `1-5-manage-departments`
Created: 2026-07-11

## Story

As an Admin,
I want to create, view, rename and remove Departments,
So that Employees can be grouped, and a Department that still holds people cannot quietly vanish.

## Acceptance Criteria

Verbatim from `epics.md#Story 1.5` (lines 682–726). Do not paraphrase; the wording is the contract. AC numbering is added for task traceability.

**AC1 — An Admin creates a Department (`FR-05`, api-contracts §4.2)**
**Given** an authenticated Admin
**When** they call `POST /api/v1/departments` with a name
**Then** the Department is created and returned

**AC2 — Any authenticated Employee reads the Department list (any role, scope `all`)**
**Given** any authenticated Employee of any role
**When** they call `GET /api/v1/departments`
**Then** the response is `200` with the list of Departments (any role, all scope, per api-contracts §4.2)

**AC3 — The list is page-bounded, and the body carries the pagination envelope (`NFR-11`; spine *Pagination*; api-contracts §1)**
**Given** a client calling `GET /api/v1/departments` with a `page_size` larger than the server maximum
**When** the response is returned
**Then** it carries the server maximum, not the larger page
**And** the response body carries `items`, `page`, `page_size` and `total`

> *(From epics.md line 703:)* The page **bound** is a spine convention and lands here, with Epic 1's first list endpoint. `FR-12`'s composable filters remain in Epic 3. The two are separate: the bound is `NFR-11`, the filters are `FR-12`.

**AC4 — A non-Admin is refused the write endpoints with `403`, server-side (`NFR-03`, Story 1.4)**
**Given** an authenticated Employee or Manager, who may read Departments under `GET /api/v1/departments`
**When** they call `POST /api/v1/departments`, `PATCH /api/v1/departments/<id>` or `DELETE /api/v1/departments/<id>`
**Then** the response is `403` — a resource the actor may see but may not act upon, which is exactly what api-contracts §1 reserves `403` for
**And** the refusal happens server-side, independently of whether the client rendered the control

**AC5 — A non-empty Department cannot be deleted (`FR-05`)**
**Given** a Department with at least one assigned Employee
**When** an Admin calls `DELETE /api/v1/departments/<id>`
**Then** the response is `409` with code `DEPARTMENT_NOT_EMPTY`
**And** the refusal names the obstruction, and the Department is unchanged

**AC6 — An empty Department is removed**
**Given** a Department with no assigned Employee
**When** an Admin calls `DELETE /api/v1/departments/<id>`
**Then** the Department is removed

**AC7 — No token is `401` on every endpoint (`FR-02`)**
**Given** a request with no valid token
**When** any `/api/v1/departments` endpoint is called
**Then** the response is `401`

**AC8 — The Departments screen renders role-appropriate controls (`NFR-17`, `NFR-16`)**
**Given** the React application
**When** an Admin opens the Departments screen
**Then** create, rename and delete controls are present, and a refused delete surfaces the message naming the obstruction (`NFR-17`)
**And** for an Employee or Manager those controls are not rendered — a usability measure that is never the only thing preventing the action (`NFR-16`)

## Tasks / Subtasks

> **Read the two 🚨 traps below (Trap 1 and Trap 2) BEFORE writing any repository code.** They are the two decisions that will otherwise cost a review cycle: the armed scoped-getter guardrail (Story 1.4) will fail the build the moment you add a department getter, and the pagination bound has no number fixed upstream — you set it here for every future list endpoint.

- [x] **Task 1: `domain/vocabulary.py` (UPDATE) — declare the `DEPARTMENT_NOT_EMPTY` code** (AC: 5)
  - [x] Add `DEPARTMENT_NOT_EMPTY = "DEPARTMENT_NOT_EMPTY"` (api-contracts §2 → 409).
  - [x] Append it to `__all__`. `tests/test_vocabulary_literals.py` auto-iterates `__all__`, so the value is immediately guarded against appearing as a literal anywhere else under `app/`/`seed/`.
  - [x] Extend the module docstring's "What arrives, and where" list with a Story 1.5 line, matching the existing prose style (see the Story 1.4 line for the shape).
- [x] **Task 2: `main.py` (UPDATE) — wire the code to its status** (AC: 5)
  - [x] Extend the existing `CODE_TO_STATUS.update({...})` call with `vocabulary.DEPARTMENT_NOT_EMPTY: 409`, beside a Story 1.5 comment.
  - [x] Do **not** touch `api/v1/errors.py` — the map is populated only from `main.py`, the composition root (contract 2 forbids `errors.py` importing `domain/`). See Story 1.4 Trap 3.
- [x] **Task 3: `api/v1/pagination.py` (NEW) — the reusable page bound and envelope** (AC: 3) 🚨 **See Trap 2**
  - [x] Create the one home for the pagination convention (`NFR-11`; spine *Pagination*). This is Epic 1's first list endpoint and it **establishes** the convention Stories 1.6, 2.7 and 3.1 reuse — build it to be reused, not inlined into the departments route.
  - [x] Declare `DEFAULT_PAGE_SIZE = 50` and `MAX_PAGE_SIZE = 100` (recommended; the architecture fixes no number — see Trap 2). `page` is 1-based; `page_size` is clamped to `MAX_PAGE_SIZE`, never rejected with a 422 (AC3: "carries the server maximum, not the larger page"). `page < 1` and `page_size < 1` coerce to their minimums.
  - [x] Provide a `PageParams` dependency (parses/clamps `page`, `page_size` query params → `limit`/`offset`) and a generic `Page[T]` Pydantic response model with fields `items: list[T]`, `page: int`, `page_size: int`, `total: int` — exactly the four AC3 names, in that shape. Use `typing.Generic`/`TypeVar` so each list endpoint parameterizes it (`Page[DepartmentResponse]`).
  - [x] This module lives in `api/` (query params and the wire envelope are an `api/` concern). It imports `fastapi`/`pydantic` only — nothing lower. The `LIMIT`/`OFFSET` themselves are issued in `repositories/` (Task 4); this module only computes and carries them.
- [x] **Task 4: `repositories/department.py` (NEW) — the department reads, writes, and the emptiness count** (AC: 1, 3, 5, 6) 🚨 **See Trap 1**
  - [x] `list_departments(session, limit, offset) -> tuple[list[Department], int]` — the page of rows **and** the total count, in the same call (one `SELECT ... LIMIT/OFFSET` plus one `SELECT count(*)`). Order deterministically (e.g. `ORDER BY name, id`) so pages are stable. **This name trips the armed guardrail — resolve it via Trap 1 before writing it.**
  - [x] `get_department(session, department_id) -> Department | None` — load one row by id, for PATCH/DELETE to act on and to distinguish a real 404. `None` means no such row; the *service* decides what that means (`not_found()`), exactly as `employee.py`'s getters leave the missing-row meaning to their service. **Also trips the guardrail — Trap 1.**
  - [x] `count_employees_in_department(session, department_id) -> int` — the DELETE guard's input. **Name it with `count_` (not a read-verb prefix) so it is correctly NOT a scoped-getter candidate** (the guardrail governs row-returning getters; this returns an int). It counts **every** Employee with `department_id = :id`, *active or deactivated* — see Trap 3.
  - [x] Write helpers for create/rename/delete rows (`create_department(session, name)`, `rename_department(...)`, `delete_department(...)`), or issue them from the service directly — either is fine, but keep all SQL in `repositories/`. Writes (`create_`/`update_`/`delete_`/`rename_`) are governed by the role gate, not the scope contract, so they are not guardrail candidates.
- [x] **Task 5: `services/departments.py` (NEW) — the command orchestration and the two refusals** (AC: 1, 5, 6) 🚨 **See Trap 3**
  - [x] Docstring names the FRs/ADs it implements (`SM-6`): `FR-05`, `AD-3` (one transaction per command), `AD-5` (the FK is a backstop; the emptiness check is the gate), `AD-10` (the `not_found()` convention on a real resource, first live use).
  - [x] `create_department(name) -> Department` and `rename_department(department_id, name) -> Department` — open one `with Session(get_engine(), expire_on_commit=False) as session:` (AD-3; `expire_on_commit=False` keeps the returned row readable after commit — the idiom `services/auth.py` documents and every writer copies). Rename must load-or-`not_found()` first (a PATCH on a nonexistent id is `404`, Trap 4).
  - [x] `delete_department(department_id) -> None` — in order: **(1)** `get_department`; if `None` → `authorization.not_found()` (`404 RESOURCE_NOT_FOUND`). **(2)** `count_employees_in_department`; if `> 0` → `raise DomainError(code=vocabulary.DEPARTMENT_NOT_EMPTY, message=_DEPARTMENT_NOT_EMPTY_MESSAGE, details={...})`. **(3)** delete the row and commit. Never let the FK RESTRICT violation reach the client — that would be a `500` (AD-5), not the `409` AC5 requires. See Trap 3.
  - [x] `list_departments(limit, offset) -> tuple[list[Department], int]` — a thin pass-through opening a read session and delegating to the repository. (The `api/` route assembles the `Page` envelope.)
  - [x] One message constant per refusal, module-level (mirror `services/auth.py`'s `_AUTH_FAILED_MESSAGE`). `DEPARTMENT_NOT_EMPTY`'s `details` should state the obstruction with a number (e.g. `{"employee_count": n}`) so `NFR-17`'s "names the obstruction" is satisfied with data, not just prose.
- [x] **Task 6: `api/v1/departments.py` (NEW) — the four routes, role-gated** (AC: 1, 2, 3, 4, 6, 7)
  - [x] `POST /departments` → `Depends(require_role(authz.ROLE_ADMIN))`; body `{name}`; returns the created `DepartmentResponse`. Recommended status **201** (see Trap 5/G6).
  - [x] `GET /departments` → `Depends(get_current_employee)` **only** (role "any" — do **not** `require_role` here); takes `PageParams`; returns `Page[DepartmentResponse]`. Any authenticated role reads; no token is `401` via the empty-token path already in `get_current_employee`.
  - [x] `PATCH /departments/<id>` → `Depends(require_role(authz.ROLE_ADMIN))`; body `{name}`; returns the updated `DepartmentResponse`. Status **200**.
  - [x] `DELETE /departments/<id>` → `Depends(require_role(authz.ROLE_ADMIN))`; returns **204** (recommended; no body). `apiFetch` already decodes an empty body.
  - [x] Route module imports `services/` and the `api/`-layer `dependencies`/`pagination` only — never `repositories/` or `domain/` (contract 2). The `DepartmentResponse` model (`{id: uuid, name: str}`) is declared here, projected by hand (as `me.py` does), not `from_attributes` off the ORM.
  - [x] Register the router in `api/v1/router.py`: `from app.api.v1 import auth, departments, health, me` and `api_v1_router.include_router(departments.router)`.
- [x] **Task 7: `repositories/employee.py` — extend EXEMPT rationale IF Trap 1 chooses EXEMPT** (AC: 2, 3)
  - [x] Only if you resolve Trap 1 by adding the two department getters to `tests/test_scoped_getters.py`'s `EXEMPT` set: update that test's `EXEMPT` frozenset AND broaden its explanatory docstring so a future reader understands the second exemption ground (scope-`all` reference reads returning no Employee-derived data), not just actor-resolution. Do not silently widen the set without the rationale — that is the exact "silencing" the guard's sibling `test_there_are_getters_to_inspect` exists to notice.
- [x] **Task 8: Backend tests** (AC: 1–7)
  - [x] `tests/integration/test_departments.py` (real-PG, `TestClient`) — reuse the `callers` fixture shape from `test_role_gate.py` (one active Employee per role in a shared department, a signed token for each; `import app.main` at top so `CODE_TO_STATUS` is populated). Cover: Admin `POST` creates and returns (AC1); each role `GET`s the list `200` (AC2); a non-Admin `POST`/`PATCH`/`DELETE` gets `403 ACTION_NOT_PERMITTED` before any write (AC4); `DELETE` of a department that still has the fixture's employees → `409 DEPARTMENT_NOT_EMPTY` and the row survives (AC5); `DELETE` of an empty department succeeds (AC6); no token → `401` on each endpoint (AC7); `PATCH`/`DELETE` of a **nonexistent** id → `404 RESOURCE_NOT_FOUND` (Trap 4).
  - [x] Pagination (AC3): create N > `MAX_PAGE_SIZE` departments (or assert against a low fixture bound) and confirm a `page_size` above the max returns exactly `MAX_PAGE_SIZE` items and the body carries `items`, `page`, `page_size`, `total`. A DB-free unit test on `PageParams` clamping is cheaper and should carry the clamp assertion; the integration test proves the envelope end-to-end.
  - [x] Keep the full suite green: `test_vocabulary_literals.py` (picks up `DEPARTMENT_NOT_EMPTY` automatically), `test_error_envelope.py`, `test_scoped_getters.py` (Trap 1 — this MUST stay green with the new getters resolved), `test_architecture.py`'s 7 import contracts, and `alembic check` via `test_model_migration_agreement.py`. **No migration is expected** — the `department` table already exists (migration 0002); you add no column (Trap 6).
- [x] **Task 9: Frontend — the Departments screen, role-gated** (AC: 8)
  - [x] `src/api/departments.ts` (NEW) — typed hooks on `apiFetch`: `useDepartments()` (query, `GET /departments`, typed `Page<Department>`), `useCreateDepartment()`, `useRenameDepartment()`, `useDeleteDepartment()` (mutations). On success, invalidate the departments query key so the list refreshes. Export the public surface from `src/api/index.ts` (as `me.ts`/`auth.ts` are exported).
  - [x] `src/features/departments/DepartmentsPage.tsx` (NEW) — lists departments (any role). Create/rename/delete controls render **only** when `useMe().data.role === 'ADMIN'` (`NFR-16`). A refused delete is an `ApiError` with `code === 'DEPARTMENT_NOT_EMPTY'`; surface `error.message` (or a message built from `details.employee_count`) naming the obstruction (`NFR-17`). Branch on `code`, never `message` (see `client.ts` guidance).
  - [x] Wire it into `App.tsx`'s `AppShell` — minimally. The spine defers routing and no router is installed; do not add one. A simple in-shell section or a lightweight view toggle is sufficient. Keep the "Signed in" identity line.
  - [x] `NFR-16` is a usability measure, **never the only guard** (AC4/AC8): hiding the controls is cosmetic; the `403` from Task 6 is the real refusal. Do not gate the *action* on the client role alone.
- [x] **Task 10: Prove it end-to-end** (AC: 1–8)
  - [x] Backend: run the full suite; record counts in Dev Agent Record. Run `lint-imports` in `backend/` and confirm 0 broken. Confirm `test_scoped_getters.py` passes with the new department getters (Trap 1 resolved).
  - [x] Frontend: `npm run build` (`tsc -b && vite build`) typechecks and builds; `npm run lint` (oxlint) is clean. There is **no frontend test runner** in `package.json` (oxlint + `tsc` only) — so, as Stories 1.2/1.3 did, the frontend proof is the passing typecheck/lint plus a **declared manual click-through** of the Admin (controls present, non-empty delete refused with the named obstruction) and non-Admin (controls absent) paths. Record the click-through gap explicitly.

## Dev Notes

### What this story is, and where it sits

This is the **first real feature endpoint** in LeaveFlow, and it is deliberately the simplest resource — a Department is `{id, name}`. It is the first consumer of Story 1.4's `require_role` gate on a live route, the first `404` raised by `not_found()` against a real resource, the **first list endpoint** (so it *establishes* the `NFR-11` pagination convention every later list reuses), and the **first role-gated UI** (`NFR-16`). Getting the shapes right here is worth more than the feature itself: Stories 1.6, 2.7 and 3.1 copy the pagination module, the role-gated route shape, and the service-is-the-gate/FK-is-the-backstop pattern.

Scope of every departments endpoint is **`all`** (api-contracts §4.2): there is no per-row data scoping — `GET` is granted to any role and returns the whole list; the writes are Admin-only by *role*, not by scope. That is why `require_role` (a role gate) is the whole authorization story here, and the scope resolver (`repositories/scoping.py`) is **not** used. The first genuinely data-scoped resource is a Leave Request in Epic 2.

**It is NOT:**
- **Not** a schema change. `department` (and its `employee.department_id` FK) already exist from migration 0002. Add no column, write no migration (Trap 6).
- **Not** a place for filters. `FR-12`'s `status`/`leave_type_id`/`date_from`/`date_to` are Epic 3. This story delivers only the `NFR-11` page **bound** (epics.md line 703).
- **Not** a `UNIQUE (name)` on department. The ERD declares none, and `models.py` documents *why* not — do not invent one. Two departments may share a name; that is intended (the seed's select-then-insert relies on it).
- **Not** a change to `get_current_employee`, `resolve_actor`, or the G4 decision (deactivated-but-valid token). Leave the auth path exactly as it is.

### 🚨 Six traps, in the order they will bite

**1. The armed scoped-getter guardrail (Story 1.4) fails the build the moment you add a department getter — resolve it deliberately.** `tests/test_scoped_getters.py` reflects over every `repositories/*.py` function whose name starts with `get_`/`list_`/`find_`/`fetch_` AND takes a `session` param, and requires each to take an `actor` param or be in the `EXEMPT` set. `list_departments(session, ...)` and `get_department(session, ...)` both match and will **fail** the build. This is the guardrail doing its job — it cannot read intent, so it flags every candidate. The resolution, and the reasoning:

- AC1 (Story 1.4) governs getters that return "**another Employee's data**." A Department row (`{id, name}`) is *not* Employee data, and its scope is `all` (any role reads the whole list). So the department getters genuinely fall **outside** AC1 — they are a convention-bound false positive, exactly the case the guardrail's own docstring ("The reach of the net, stated honestly") anticipates.
- **Recommended resolution:** add `"list_departments"` and `"get_department"` to `EXEMPT`, and **broaden the EXEMPT docstring** to state the second exemption ground: *scope-`all`, organization-wide reference reads that return no Employee-derived data* (departments here; leave types and holidays later, all api-contracts scope `all`). This is a deliberate, reviewer-visible act — which is the whole point of an explicit registry over a silent bypass.
- **Do NOT** "fix" it by giving the getters an unused `actor` param: scope is `all`, so an actor parameter would imply a scoping that does not happen — misleading, and oxlint/ruff may flag the unused arg. EXEMPT-with-rationale is the honest choice.
- The DELETE emptiness input is `count_employees_in_department` — named with `count_`, **not** a read-verb prefix, so it is correctly *not* a candidate. Keep that naming; do not call it `get_employee_count_...`, which would drag it into the guardrail for no reason.

**2. The pagination bound has no number fixed upstream — you set it, for every future list endpoint.** The spine and api-contracts fix the *convention* ("a server-side maximum page size; a client asking for more receives the maximum") and the *envelope* (`items`, `page`, `page_size`, `total`) but **no numeric maximum**. Choose it here, once, in `api/v1/pagination.py`, and every later list endpoint (1.6, 2.7, 3.1) inherits it. Recommended: `DEFAULT_PAGE_SIZE = 50`, `MAX_PAGE_SIZE = 100`, `page` 1-based. The clamp is silent (AC3: "carries the server maximum, not the larger page") — never a `422`. Build `Page[T]` generic so the response model is reused, not re-declared per endpoint.

**3. The FK is the backstop; the emptiness check is the gate (`AD-5`).** `employee.department_id` is a NOT-NULL FK to `department.id` with Postgres's default `RESTRICT`/`NO ACTION`. If you `DELETE` a department that still has employees without pre-checking, Postgres raises an `IntegrityError` → the handler renders a **500**, not the `409 DEPARTMENT_NOT_EMPTY` AC5 requires. So the service **counts first** and raises the typed `DomainError`; the constraint is only there to catch a defect. This is the same "CHECK/constraint is a backstop, never a gate" discipline the balance rules (spine) and login use. **Count ALL employees regardless of `is_active`:** a deactivated Employee's row persists (Story 1.6) and still references the department via the FK, so a delete would still be refused by the database — the count must match what the FK actually blocks, or you ship a `500` on a department that looks "empty" because everyone in it is deactivated.

**4. A PATCH or DELETE of a nonexistent id is `404`, via `not_found()` — this is its first live use.** Story 1.4 built `authorization.not_found()` (`RESOURCE_NOT_FOUND` → 404, one message, empty-or-fixed details, byte-identical) and proved it only at the handler seam. Story 1.5 is the first story to raise it against a real resource: `PATCH`/`DELETE /departments/<id>` where `<id>` names no row must return `404`, not `500` and not a silent success. Load-or-`not_found()` at the top of the rename/delete services. (For departments — scope `all` — there is no scope-miss vs nonexistent distinction to worry about; both are simply "no such row." The byte-identity property still holds for free because there is one `not_found()`.)

**5. The 2xx success codes are yours to choose (G6), but the frontend must match.** api-contracts fixes only non-2xx statuses; the success code for `DELETE /departments/<id>` is the open (cosmetic, non-blocking) gap **G6**. Recommended, and internally consistent: **201** for `POST` (created, with body), **200** for `PATCH` (updated, with body), **204** for `DELETE` (no body). Whatever you choose, the React `departments.ts` hooks must expect the same — `apiFetch` already tolerates an empty 204 body.

**6. No migration — and `alembic check` will tell on you.** `department` and the `employee.department_id` FK already exist (migration 0002). This story adds no column and no table. `test_model_migration_agreement.py` runs `alembic check`; if you touch a model, it fails. If you find yourself writing a migration, stop — you have drifted out of scope.

### Architecture compliance

- **`AD-1` (one-way imports).** `api → services → {repositories, domain}`; `repositories → domain`. The new route (`api/v1/departments.py`) imports `services/departments` and the `api/`-layer `dependencies`/`pagination`, never `repositories/` or `domain/`. The service raises `DomainError`; `main.py`'s single handler renders it. Enforced by the 7 import contracts in `test_architecture.py` — if you somehow need a new contract (you should not), update that file's `expected` dict in the same commit.
- **`AD-10` (authorization is server-side; absence is 404; scope is a SQL predicate).** Departments are scope `all`, so there is no per-row predicate — but the `404` convention still applies to a nonexistent id (Trap 4), and the write endpoints are refused by role at the `api/` boundary before any row is read (the `403`, not a post-filter). [Source: api-contracts.md §1; ARCHITECTURE-SPINE.md#AD-10]
- **`AD-14` (the server enforces; the client only renders).** `require_role` reads `actor.role` off the DB-resolved actor. The React screen hiding controls for a non-Admin (`NFR-16`) is a usability layer that is **never the only guard** — the `403` is (AC4/AC8). [Source: ARCHITECTURE-SPINE.md#AD-14]
- **`AD-5` (schema is the backstop, service is the gate).** The FK RESTRICT is a backstop; the `count_employees_in_department` pre-check is the gate that raises `409 DEPARTMENT_NOT_EMPTY` (Trap 3).
- **`AD-3` (one transaction per command).** Each write command opens one `with Session(get_engine(), expire_on_commit=False)` and commits inside it — the idiom `services/auth.py` documents and the first writer here must copy correctly (the `expire_on_commit=False` comment in `auth.py:58` explains why the default would raise `DetachedInstanceError` on a committed write).
- **`AD-21` (one canonical vocabulary).** `DEPARTMENT_NOT_EMPTY` is declared once in `domain/vocabulary.py`, `UPPER_SNAKE_CASE`, and appears as a literal nowhere else (the frontend restates the *string it matches on* — here `'DEPARTMENT_NOT_EMPTY'` for the refusal message — in exactly one place, as `client.ts` does for `TOKEN_INVALID`). Role constants reach `api/` only through the `services/authorization` re-export (Story 1.4 Trap 1).
- **`NFR-11` (bounded result sets).** The page bound is enforced from this, Epic 1's first list endpoint, in `api/v1/pagination.py` (Trap 2). [Source: ARCHITECTURE-SPINE.md *Pagination*; api-contracts §1]

### Previous story intelligence — Story 1.4 (read this; it is first-hand)

- **`require_role` is ready and returns the actor.** `require_role(authz.ROLE_ADMIN)` is a dependency factory: it chains `Depends(get_current_employee)` (auth first), calls `authz.assert_role`, and returns the actor on success — so a route can write `actor: Actor = Depends(require_role(authz.ROLE_ADMIN))` and still read the caller. It raises `403 ACTION_NOT_PERMITTED` at the boundary, before the body runs. `require_role()` with no args raises `ValueError` — always pass at least one role.
- **`authorization.not_found()` is the 404 raise site.** One message, byte-identical. Story 1.5 is its first real consumer (Trap 4). Reach it via `from app.services import authorization as authz` and `authz.not_found()` — from the *service*, not the route (the route cannot import `domain/`).
- **The role literals come through `services/authorization`.** `api/` must not `from app.domain.vocabulary import ROLE_ADMIN` — contract 2 flags it even under `TYPE_CHECKING`, and the literal scan forbids the bare string. Use `authz.ROLE_ADMIN` (the re-export). Story 1.4 Trap 1.
- **`CODE_TO_STATUS` is populated from `main.py`, not `errors.py`.** Add `DEPARTMENT_NOT_EMPTY: 409` there. `errors.py` stays untouched (Story 1.4 Trap 3).
- **The `Actor`/`DepartmentShape` Protocol idiom is mandatory in `api/`.** A `TYPE_CHECKING` import of the ORM into `api/` still breaks import-linter (proven empirically in 1.3). The route's `DepartmentResponse` is a plain Pydantic model built by hand from the service's returned `Department`, exactly as `me.py` projects `MeResponse` — not `from_attributes`.
- **Repository getters are plain module functions taking `session: Session` first** (`get_by_email(session, email)`), no repository class. Text columns are `mapped_column(Text, ...)` — but you touch no model here.
- **`expire_on_commit=False`** preserves loaded attributes after the session closes but does **not** lazy-load a relationship after close — read what you need inside the block, or project before returning.
- **Test trees:** `tests/integration/` runs against real PostgreSQL and skips *loudly* when it is absent (see `integration/conftest.py`); `import app.main` at the top of an integration test so `CODE_TO_STATUS` is populated. `test_role_gate.py`'s `callers` fixture — one Employee per role in a shared department, a signed token each — is the copy-paste template for this story's role/permission tests (mint tokens with `security.hash_password` + `security.create_token`, commit through `get_engine()` so the app's fresh per-command connection sees them).

### Verified library / framework facts (checked against installed pins)

- **Stack:** Python 3.13 · FastAPI 0.139.0 · Pydantic 2.13.4 · SQLAlchemy 2.0.51 · Alembic 1.18.5 · psycopg 3.3.4 · PostgreSQL 18 · PyJWT 2.13.0 · pwdlib 0.3.0 · pytest 9.1.1 · import-linter 2.13. Frontend: React 19.2 · @tanstack/react-query 5.101 · Vite 8.1 · TypeScript 6.0 · oxlint 1.73 (build = `tsc -b && vite build`; lint = `oxlint`; **no test runner installed**).
- **FastAPI pagination:** parse `page`/`page_size` as query params via a dependency (a `PageParams` class with `Depends`, or `Query(...)` defaults). Clamp in code — do not use `Query(le=MAX)`, which would *reject* an over-max value with `422`; AC3 requires it to be *clamped* to the max, not refused.
- **Pydantic generic response model:** `class Page(BaseModel, Generic[T])` with `items: list[T]` is supported in Pydantic 2; parameterize as `Page[DepartmentResponse]` in the route's return annotation so the OpenAPI schema (the runtime source of truth per api-contracts §5) is precise.
- **SQLAlchemy count + page:** `session.scalars(select(Department).order_by(...).limit(limit).offset(offset)).all()` for the page; `session.scalar(select(func.count()).select_from(Department))` for `total`. Two statements, one session.
- **TanStack Query mutations:** `useMutation` + `queryClient.invalidateQueries({ queryKey: DEPARTMENTS_QUERY_KEY })` in `onSuccess` to refresh the list after create/rename/delete — the pattern `App.tsx` already uses `removeQueries` for.

### Testing standards

- **`pytest` is the build (`F-14`); there is no CI.** The full suite must stay green. Story 1.4 ran 92 backend tests; this story adds department integration tests plus a DB-free `PageParams` clamp unit test. The auto-parametrized vocabulary/literal and scoped-getter scans will pick up the new modules automatically — which is exactly why Trap 1 must be resolved before the suite can pass.
- **Where each test goes:**
  - `tests/integration/test_departments.py` (real-PG, `TestClient`) — the CRUD, role-gate `403`, `409 DEPARTMENT_NOT_EMPTY`, `401`, and `404`-on-nonexistent behaviours (AC1–AC7). Model the fixture on `test_role_gate.py`'s `callers`.
  - a DB-free unit test (e.g. `tests/test_pagination.py`, top-level) — `PageParams` clamps `page_size > MAX` to `MAX`, coerces `page < 1`/`page_size < 1` to minimums, computes `limit`/`offset` correctly. Cheaper than proving the clamp through the DB, and it pins the convention.
- **`NFR-15`:** test the guarantees (the `403` boundary refusal, the `409` gate vs the FK backstop, the page clamp, the `404` convention), not trivial getters. Do not chase coverage on the happy-path projection.
- **Governing FR:** `FR-05` (Departments). This story fully realizes it. `NFR-11`'s bound is realized here and inherited onward; `FR-12`'s filters are Epic 3.
- **Frontend proof** is `tsc -b`/`vite build` + `oxlint` + a **declared manual click-through** (no test runner exists). Record the click-through gap in the Dev Agent Record exactly as Stories 1.2/1.3 did.

### Project Structure Notes

- **New (backend):**
  - `backend/app/api/v1/pagination.py` — the reusable page bound + `Page[T]` envelope (Trap 2).
  - `backend/app/api/v1/departments.py` — the four routes, role-gated.
  - `backend/app/services/departments.py` — create/rename/delete/list orchestration, the two refusals.
  - `backend/app/repositories/department.py` — `list_departments`, `get_department`, `count_employees_in_department`, and the write helpers.
  - `backend/tests/integration/test_departments.py`, `backend/tests/test_pagination.py`.
- **Modified (backend):**
  - `backend/app/domain/vocabulary.py` — `DEPARTMENT_NOT_EMPTY` + `__all__` + docstring line.
  - `backend/app/main.py` — one `CODE_TO_STATUS` entry (`DEPARTMENT_NOT_EMPTY: 409`).
  - `backend/app/api/v1/router.py` — register the departments router.
  - `backend/tests/test_scoped_getters.py` — `EXEMPT` + docstring, **if** Trap 1 is resolved via EXEMPT (recommended).
- **New (frontend):**
  - `frontend/src/api/departments.ts` — typed hooks.
  - `frontend/src/features/departments/DepartmentsPage.tsx` — the role-gated screen.
- **Modified (frontend):**
  - `frontend/src/api/index.ts` — export the departments surface.
  - `frontend/src/App.tsx` — mount the Departments screen in the shell (minimally; no router).
- **Untouched (must stay so):** `api/v1/errors.py` (map populated from `main.py`), `api/v1/me.py`/`auth.py`/`health.py`/`dependencies.py` (the auth path and role gate are consumed, not changed), `services/auth.py`/`authorization.py` (consumed: `not_found`, `assert_role`, role re-exports), `repositories/employee.py`'s two exempt getters, `repositories/scoping.py` (departments are scope `all`; the resolver is not used here), all models and migrations, `test_architecture.py` (no new import contract needed).

### References

- [epics.md#Story 1.5](../planning-artifacts/epics.md) — the story statement and all eight criteria, verbatim (lines 682–726); the `NFR-11`-bound-vs-`FR-12`-filters split (line 703); the `403` "refused server-side independently of whether the client rendered the control" (line 708); the `NFR-16` control-hiding "never the only thing preventing the action" (line 726).
- [epics.md#Story 1.4](../planning-artifacts/epics.md) — "its first scoped **resource** is a Department in Story 1.5" (line 680); Story 1.5 named as the first consumer of the role gate.
- [epics.md#FR Coverage Map](../planning-artifacts/epics.md) — `NFR-11` "delivered in Story 1.5" (line 246); the pagination bound bound to "Epic 1's first list endpoint" (line 283); `NFR-17` "Refusals carrying *numbers* arrive in Epic 2" (line 289 — here the refusal names an obstruction, not yet a leave-day number).
- [api-contracts.md §1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the status table (`403`, `404`, `409` meanings); the `403`-vs-`404` settlement (`G3`); the **Pagination** convention ("carries the maximum, not the larger page"; `items`, `page`, `page_size`, `total`).
- [api-contracts.md §2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — `DEPARTMENT_NOT_EMPTY` → 409 (`FR-05`); the `{code, message, details}` envelope every non-2xx carries.
- [api-contracts.md §4.2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the four `/departments` endpoints with Role (`Admin`/`any`) and Scope (`all`).
- [ARCHITECTURE-SPINE.md *Pagination* / *Consistency Conventions*](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — "Every list endpoint enforces a server-side maximum page size" (line 213); "Only the base path, the error envelope, the vocabulary and the pagination bound are fixed here" (line 424 — the number is not, hence Trap 2).
- [ARCHITECTURE-SPINE.md#AD-5 / #AD-10 / #AD-14](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — constraint-is-a-backstop; absence-is-404; server-enforces-client-renders.
- [epics.md#G6](../planning-artifacts/epics.md) — the open, cosmetic 2xx status code for `DELETE /departments/<id>` (lines 390–398): "The implementer chooses, and the React client must match" (Trap 5).
- [1-4-authorization-primitives…md](1-4-authorization-primitives-the-role-gate-scoped-reads-and-the-404-convention.md) — `require_role`, `not_found()`, the role re-export, the armed scoped-getter guardrail, `CODE_TO_STATUS`-from-`main.py`; the first-hand traps this story consumes.
- [backend/app/api/v1/dependencies.py](../../backend/app/api/v1/dependencies.py) · [services/authorization.py](../../backend/app/services/authorization.py) · [services/auth.py](../../backend/app/services/auth.py) · [api/v1/me.py](../../backend/app/api/v1/me.py) · [api/v1/auth.py](../../backend/app/api/v1/auth.py) · [repositories/employee.py](../../backend/app/repositories/employee.py) · [repositories/models.py](../../backend/app/repositories/models.py) · [tests/test_scoped_getters.py](../../backend/tests/test_scoped_getters.py) · [tests/integration/test_role_gate.py](../../backend/tests/integration/test_role_gate.py) — current state, read in full during story creation.
- [frontend/src/api/client.ts](../../frontend/src/api/client.ts) · [api/index.ts](../../frontend/src/api/index.ts) · [api/me.ts](../../frontend/src/api/me.ts) · [App.tsx](../../frontend/src/App.tsx) · [features/auth/LoginPage.tsx](../../frontend/src/features/auth/LoginPage.tsx) — the frontend patterns the Departments screen copies (typed hooks on `apiFetch`, `ApiError` code branching, role from `useMe`).
- [module-4-erd/erd.md](../planning-artifacts/module-4-erd/erd.md) — `department` has no `UNIQUE (name)`; `employee.department_id` NOT-NULL FK to `department.id` (why the emptiness check counts all employees, Trap 3).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — dev-story workflow.

### Debug Log References

- `PageParams` initially declared its query params as `page: int = Query(default=1, ...)`.
  A bare `= Query(...)` default leaves the runtime default a `Query` marker object, so the
  DB-free unit test's `PageParams()` raised `TypeError: '>' not supported between instances
  of 'int' and 'Query'`. Fixed by switching to the `Annotated[int, Query(...)] = 1` form,
  which keeps the parameter's runtime default a plain `int` (directly constructable in a
  unit test) while FastAPI still reads the `Query` metadata from the annotation. All 7
  pagination unit tests green after the change.

### Completion Notes List

- **All 8 ACs satisfied and proven.** AC1 create → 201; AC2 list for every role → 200; AC3
  page-bound clamp proven both DB-free (`test_pagination.py`) and end-to-end through the
  `Page` envelope (`test_departments.py`); AC4 non-Admin write → 403 `ACTION_NOT_PERMITTED`
  with the row verified unchanged; AC5 non-empty delete → 409 `DEPARTMENT_NOT_EMPTY` naming
  `employee_count` and the row surviving; AC6 empty delete → 204 and gone; AC7 no token →
  401 on all four endpoints; AC8 role-gated React screen (build + lint clean).
- **Trap 1 (armed scoped-getter guardrail) resolved deliberately, not silenced.** Added
  `list_departments`/`get_department` to `test_scoped_getters.py`'s `EXEMPT` set AND broadened
  the module docstring to state the *second* exemption ground — scope-`all`, organization-wide
  reference reads returning no Employee-derived data — so a future reader sees why. Did NOT
  give the getters an unused `actor` param. `count_employees_in_department` is `count_`-prefixed,
  returning an `int`, so it is correctly not a candidate.
- **Trap 2 (pagination bound) chosen once, here.** `DEFAULT_PAGE_SIZE = 50`, `MAX_PAGE_SIZE = 100`,
  1-based `page`, in `api/v1/pagination.py` — the shared module Stories 1.6/2.7/3.1 inherit. Clamp
  is silent (never a 422); `page < 1`/`page_size < 1` coerce to their minimums.
- **Trap 3 (FK backstop vs emptiness gate, AD-5) honoured.** The service counts first and raises
  the typed 409; the count includes deactivated Employees, so a "looks empty" department cannot
  slip past the gate into an FK RESTRICT 500.
- **Trap 4 (`not_found()` first live use)** — PATCH/DELETE of a nonexistent id → 404
  `RESOURCE_NOT_FOUND`, proven for both verbs.
- **Trap 5 / G6 (success codes)** — 201 POST, 200 PATCH, 204 DELETE, matched by the React hooks.
- **Trap 6 (no migration)** — `department` table pre-exists (migration 0002); no model touched;
  `alembic check` clean via `test_model_migration_agreement.py`.
- **Backend suite: 92 → 122 passing** (added 7 `test_pagination.py` + 23 parametrized cases in
  `test_departments.py`). `lint-imports`: 7 contracts kept, 0 broken. Live OpenAPI confirms all
  four routes registered and `DEPARTMENT_NOT_EMPTY → 409` wired.
- **Frontend proof: `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) both
  clean.** There is **no frontend test runner** in `package.json` (oxlint + `tsc` only), so — as
  Stories 1.2/1.3 did — the frontend proof is the passing typecheck/lint plus a **DECLARED
  manual click-through** of: Admin (create/rename/delete controls present; a non-empty delete
  refused with the message naming the obstruction via `details.employee_count`) and non-Admin
  (controls absent, list still visible). **⚠️ Click-through gap: this manual pass was NOT
  performed in this session** — the backend behaviour it would exercise is fully covered by the
  real-PG integration tests; the frontend rendering was verified only by typecheck + lint + build.

### File List

**New (backend):**
- `backend/app/api/v1/pagination.py`
- `backend/app/api/v1/departments.py`
- `backend/app/services/departments.py`
- `backend/app/repositories/department.py`
- `backend/tests/test_pagination.py`
- `backend/tests/integration/test_departments.py`

**Modified (backend):**
- `backend/app/domain/vocabulary.py` — `DEPARTMENT_NOT_EMPTY` constant + `__all__` + docstring line
- `backend/app/main.py` — `CODE_TO_STATUS` entry `DEPARTMENT_NOT_EMPTY: 409`
- `backend/app/api/v1/router.py` — register the departments router
- `backend/tests/test_scoped_getters.py` — `EXEMPT` set + broadened rationale (Trap 1)

**New (frontend):**
- `frontend/src/api/departments.ts`
- `frontend/src/features/departments/DepartmentsPage.tsx`

**Modified (frontend):**
- `frontend/src/api/index.ts` — export the departments surface
- `frontend/src/App.tsx` — mount `DepartmentsPage` in the shell
- `frontend/src/index.css` — Departments screen styles; `shell__main` gap

### Review Findings

_Adversarial code review 2026-07-11 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). All 8 ACs verified satisfied; findings below are robustness/UX gaps, not AC violations._

**Deferred** (were decision-needed; resolved to defer 2026-07-11)

- [x] [Review][Defer] No server-side validation of department `name` — empty/whitespace accepted (`blind+edge`, medium) — `DepartmentWriteRequest.name: str` has no `min_length`/strip; `POST/PATCH {"name": ""}` or `{"name": "   "}` (bypassing the browser's `trim()`) persists a blank-named department. Violates server-as-guard (NFR-03), but the enveloped-validation-error contract is undecided (a raw pydantic 422 bypasses the NFR-17 envelope). **Deferred:** the enveloped-validation-error contract is a cross-cutting architecture decision (new vocabulary code + status convention) that belongs in a dedicated follow-up, not this story. [backend/app/api/v1/departments.py:45-48, backend/app/services/departments.py:34-59]
- [x] [Review][Defer] Frontend department list is capped at one page (50) with no pagination controls (`blind`, medium) — `useDepartments` requests no `page`/`page_size` and renders no next/prev controls; departments beyond the first page (max 100) are unmanageable via the UI. **Deferred:** departments are few in the MVP and the backend bound is already established; UI controls wait for a dedicated story when a real >50-department need appears. [frontend/src/api/departments.ts:41-46, frontend/src/features/departments/DepartmentsPage.tsx:133-184]

**Patch** (all applied 2026-07-11; backend 122/122 tests pass, 7/7 import contracts kept, frontend typecheck/lint/build clean)

- [x] [Review][Patch] Create & Rename failures are silently swallowed — no error surfaced (`blind+edge`, medium) — FIXED: added `writeErrorMessage`; `createDepartment.isError`/`renameDepartment.isError` now render a `.dept-error` line under the create form and inside the edit form. A failed rename keeps the form open with the error; `renameDepartment.reset()` clears stale errors on open/cancel. [frontend/src/features/departments/DepartmentsPage.tsx]
- [x] [Review][Patch] Delete gate is not atomic — concurrent employee assignment surfaces as a 500 instead of 409 (`edge`, low) — FIXED: `delete_department` now wraps the commit in `try/except IntegrityError`, rolls back, recounts, and re-raises `409 DEPARTMENT_NOT_EMPTY` via the shared `_department_not_empty` helper — completing AD-5's "FK is the backstop" design. [backend/app/services/departments.py]
- [x] [Review][Patch] Delete UX: shared mutation disables all rows' Delete buttons; stale refusal lingers (`blind+edge`, low) — FIXED: Delete button now disables only the in-flight row (`deleteDepartment.variables === department.id`); `deleteError` is cleared on delete success, on create, and on opening an edit. [frontend/src/features/departments/DepartmentsPage.tsx]

_Dismissed as noise (1): AC8 "manual frontend click-through not performed" — already recorded as a permitted gap in the Dev Agent Record per the story's own testing standard; not a code defect._

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-11 | Story created (ultimate context engine analysis: epics §1.5 + cross-story 1.4/1.6 context, ARCHITECTURE-SPINE Pagination/AD-5/AD-10/AD-14, api-contracts §1/§2/§4.2, epics G6, ERD department; prior story 1.4 first-hand; full current-state audit of vocabulary/main/router/dependencies/authorization/auth/errors/me/auth-route/models/employee-repo/scoped-getter-guardrail/role-gate-test and the frontend client/api/App/LoginPage). Status: ready-for-dev. |
| 2026-07-11 | Story implemented (all 8 ACs, all 10 tasks). Backend: pagination module (bound chosen: 50/100), department repository + service + 4 role-gated routes, `DEPARTMENT_NOT_EMPTY` vocabulary→409, scoped-getter EXEMPT resolved (Trap 1). Frontend: typed departments hooks + role-gated screen mounted in shell. Tests: 92→122 backend passing (7 pagination unit + real-PG integration); lint-imports 7/7 kept; frontend build + oxlint clean. No migration (Trap 6). Manual frontend click-through declared as a gap. Status: review. |
| 2026-07-11 | Adversarial code review (3 layers). All 8 ACs verified satisfied. 3 patches applied: create/rename error surfacing (frontend), TOCTOU `IntegrityError`→409 backstop in delete (backend, completes AD-5), per-row delete-button disabling + stale-error clearing (frontend). 2 findings deferred (server-side name validation pending an enveloped-validation contract; pagination UI) → deferred-work.md. 1 dismissed. Re-verified: 122/122 backend tests, 7/7 import contracts, frontend typecheck/lint/build clean. Status: done. |
