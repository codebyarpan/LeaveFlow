---
baseline_commit: b58546592328126e1beadf3d77dd6b7f85411b76
---

# Story 1.7: Scope Authority to the Reporting Relationship

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Manager,
I want my authority to come from the Employees who actually report to me rather than from my job title,
so that another Manager's people are, to me, indistinguishable from people who do not exist.

## Acceptance Criteria

1. **The Manager scope is the reporting-edge predicate, evaluated at request time.**
   **Given** a Manager and the scope resolver introduced by Story 1.4
   **When** the resolver is evaluated for that Manager
   **Then** the scope is the predicate `employee.manager_id = :actor_id`
   **And** it is evaluated at request time, not cached from the token or from login (`DR-12`, `AD-10`).

2. **Reassignment shifts scope membership with no re-login.**
   **Given** an Employee reporting to Manager A
   **When** an Admin reassigns them to Manager B through `PATCH /api/v1/employees/<id>`
   **Then** the next evaluation of Manager B's scope includes that Employee, and the next evaluation of Manager A's excludes them
   **And** no restart, re-login, or token refresh is required, because authority is evaluated at decision time (`DR-12`, architecture §7).

3. **A managerless Employee falls inside no Manager's scope.**
   **Given** an Employee whose `manager_id` is NULL
   **When** their scope membership is evaluated
   **Then** they fall inside no Manager's scope
   **And** `AD-22`'s deactivation guard (delivered by Story 1.6) is what prevents an Admin from creating this state for an Employee who previously had a Manager (`FR-09`, `AD-22`).

4. **The SM-3 coverage-matrix test registers every identifier endpoint and fails on an unregistered one.**
   **Given** the `SM-3` coverage matrix test
   **When** the test suite runs
   **Then** every endpoint that accepts a resource identifier is registered in the matrix with the scope api-contracts §4 grants it
   **And** an endpoint added by a later story but never registered fails the test.

> **What this story is — read before writing any code.** The Manager predicate `Employee.manager_id == actor.id` **already exists and is unit-tested** — Story 1.4 built it in [`repositories/scoping.py`](../../backend/app/repositories/scoping.py) and [`tests/domain/test_scoping.py`](../../backend/tests/domain/test_scoping.py). This story does **not** re-implement it and does **not** wire a new live Manager-facing endpoint. It is a **verification + test-harness** story with two deliverables: (a) the **SM-3 coverage-matrix test** (AC4 — the unique new artifact), and (b) **DB-backed behavioral proof** that the reporting-edge scope selects exactly a Manager's reports, reflects reassignment at request time, and excludes NULL-manager rows (AC1–AC3). Per epics.md line 837, this story *"builds the harness and registers Epic 1's endpoints; it does not claim to satisfy `SM-3`, which Epic 2 does."*

## Tasks / Subtasks

- [x] **Task 1 — Prove the reporting-edge scope against a real database (AC1, AC2, AC3).** Add a new integration test module (real PostgreSQL), e.g. `backend/tests/integration/test_manager_scope.py`.
  - [x] Reuse the `_World` / `make(role, *, manager_id=..., is_active=..., label=...)` factory pattern from [`tests/integration/test_employees.py`](../../backend/tests/integration/test_employees.py) to build a topology: Manager A, Manager B, Employee R reporting to A, and a control Employee reporting to B. `import app.main  # noqa: F401` at the top.
  - [x] **AC1 (membership):** compose `select(Employee).where(employee_scope_predicate(Scope.REPORTS, manager_a))` against the session and assert it returns exactly R (and not B's report, not A, not B). This proves the predicate is applied *in the SQL* and selects the reporting edge, not a role.
  - [x] **AC2 (request-time reassignment, no re-login):** with Manager B's actor **unchanged** (do not mint a new token or re-resolve from a fresh login), evaluate `Scope.REPORTS` for B → empty of R; then reassign R to B via the repository/service write path used by `PATCH /employees/<id>` (`employee_service.update_employee(R.id, {"manager_id": B.id})`); re-evaluate `Scope.REPORTS` for B → now includes R, and for A → now excludes R. Assert the membership flipped without any token/login step.
  - [x] **AC3 (NULL manager):** create an Employee with `manager_id=None`; assert `Scope.REPORTS` for **every** seeded Manager excludes them (they belong to no Manager's scope).
- [x] **Task 2 — Confirm the DB-free compiled-predicate assertions still hold (AC1).** Do **not** rewrite [`tests/domain/test_scoping.py`](../../backend/tests/domain/test_scoping.py); it already asserts `Scope.REPORTS` compiles to `employee.manager_id = :manager_id_1` with the actor's id bound at call time. If anything, add a one-line assertion that the bound value is read from `actor.id` (already covered at `test_scoping.py:37`). Run it to confirm green.
- [x] **Task 3 — Build the SM-3 coverage-matrix test (AC4).** Add `backend/tests/test_scope_matrix.py` (app-object introspection, **no DB** required for the completeness check). `import app.main` and read `app.main.app`.
  - [x] Enumerate every routed endpoint that accepts a resource identifier: iterate `app.routes`, keep `isinstance(route, fastapi.routing.APIRoute)`, path starts with `/api/v1`, and the path template contains a path parameter (e.g. `{employee_id}`, `{department_id}`). Expand each route's `route.methods` into `(method, path_template)` operations (skip auto-added `HEAD`/`OPTIONS`). *(Implemented via `app.openapi()["paths"]` — under the pinned FastAPI 0.139.0, `include_router(prefix=...)` leaves `app.routes` holding one opaque `_IncludedRouter` that does not expose its nested `APIRoute`s, so the generated OpenAPI is the reliable routed-operation source; it is already prefix-resolved and excludes `HEAD`/`OPTIONS`, and is the same source `test_employees.py`'s AC12 check reads.)*
  - [x] Define an explicit **scope registry**: a dict mapping each `(method, path_template)` to the scope(s) api-contracts §4 grants it. Register Epic 1's five identifier endpoints, all scope `ALL`:
        `GET /api/v1/employees/{employee_id}` → `{Scope.ALL}`;
        `PATCH /api/v1/employees/{employee_id}` → `{Scope.ALL}`;
        `POST /api/v1/employees/{employee_id}/deactivate` → `{Scope.ALL}`;
        `PATCH /api/v1/departments/{department_id}` → `{Scope.ALL}`;
        `DELETE /api/v1/departments/{department_id}` → `{Scope.ALL}`.
  - [x] **Completeness assertion (the AC4 teeth):** every enumerated identifier operation MUST be a key in the registry — a route present in the app but absent from the registry fails the test with a message naming the offending `(method, path)`. This is what makes *"an endpoint added by a later story but never registered fails the test"* true. *(Verified adversarially: injecting an unregistered `GET /api/v1/leave-requests/{request_id}` route makes `test_every_identifier_endpoint_is_registered` fail, naming the offending operation.)*
  - [x] **Vacuity guard** (mirror `test_scoped_getters.py`'s `test_there_are_getters_to_inspect`): assert the enumerated identifier-operation set is non-empty, so a refactor that stops discovering routes cannot silently pass.
  - [x] **Guard-the-guard** (mirror `test_architecture.py`'s content-pinning test): assert the registry is non-empty and that no registered entry names a route the app does not actually expose (a stale registry entry is also a defect). Add a docstring stating Epic 2 extends this registry with the `reports`/`self` Leave-Request endpoints where `SM-3` is actually *satisfied*.
- [x] **Task 4 — Run the full backend suite and import contracts.** From `backend/`, run `pytest` (expect the prior green suite + the new tests, 0 unexpected skips) and `lint-imports` (expect 7 contracts kept, 0 broken). No new migration is expected — this story reads existing schema only. *(pytest: 168 passed, 0 skips; lint-imports: 7 kept, 0 broken; `alembic check`: no new upgrade operations detected.)*

### Review Findings

Adversarial code review 2026-07-11 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Verdict: tests pass and AC1 genuinely proves the reporting-edge data scope; no high/intolerable findings. Surviving items are assertion-strength hardening — appropriate to weigh carefully because this story's entire deliverable is the strength of the harness.

- [x] [Review][Patch] AC3 test is vacuous — no positive control [backend/tests/integration/test_manager_scope.py:189] — `test_a_managerless_employee_is_in_no_managers_scope` seeds two Managers and one managerless Employee but never seeds a real report, then asserts only `managerless not in _reports_of(...)`. If `Scope.REPORTS` regressed to select *nothing*, every assertion still passes. (AC1 at :146 is the only backstop against a globally-empty predicate.) Fix: within this test, also seed a report for `manager_a` and assert it IS selected, so the NULL-exclusion is proven against a non-empty scope rather than an empty one.
- [x] [Review][Patch] AC4 harness has no standing proof that route discovery is live and independent of the registry [backend/tests/test_scope_matrix.py:104] — the completeness gate is `_identifier_operations() - set(_SCOPE_REGISTRY)`. If `_identifier_operations()` ever regressed to mirror the registry (a refactor, an enumeration bug), the vacuity guard, completeness check, and stale-registry check all false-green together. The adversarial-injection proof (spec line 61) was a one-time manual check, not encoded. Fix: add a standing assertion pinning that a specific known route is discovered independent of the registry — e.g. `assert ("GET", "/api/v1/employees/{employee_id}") in _identifier_operations()` — so a discovery mechanism that silently mirrors the registry fails.
- [x] [Review][Patch] `_API_PREFIX` match uses `startswith("/api/v1")` without a segment boundary [backend/tests/test_scope_matrix.py:94] — a future `/api/v10` or `/api/v1beta` path would be pulled into (or a stricter check would exclude) the matrix incorrectly. Fix: guard the boundary — `path == _API_PREFIX or path.startswith(_API_PREFIX + "/")`.
- [x] [Review][Defer] Registered scope *value* is never validated against api-contracts §4 [backend/tests/test_scope_matrix.py:163] — deferred, no machine-readable §4 source. `test_each_registered_operation_grants_at_least_one_scope` only checks non-empty + `isinstance(Scope)`; registering the wrong scope (e.g. `{Scope.REPORTS}` on an Admin-only endpoint) would pass. For Epic 1 all values are correctly `{Scope.ALL}`. No independent source of §4 grants exists in code to cross-check; Epic 2 (which adds multi-scope endpoints) inherits this limitation.
- [x] [Review][Defer] `include_in_schema=False` identifier endpoints escape the completeness gate [backend/tests/test_scope_matrix.py:93] — deferred, Epic 2 concern. Enumeration reads `app.openapi()["paths"]`; a future routed+guarded identifier endpoint declared hidden would be invisible to the gate, weakening AC4's "every such endpoint the app exposes." No such endpoint exists in Epic 1; flag for Epic 2 when the Leave-Request surface lands.

## Dev Notes

### What already exists — do NOT reinvent

- **The scope resolver and the Manager predicate are DONE.** [`app/repositories/scoping.py`](../../backend/app/repositories/scoping.py) defines `class Scope(SELF|REPORTS|ALL)` and `employee_scope_predicate(scope, actor) -> ColumnElement[bool]`. `Scope.REPORTS → Employee.manager_id == actor.id` (`scoping.py:72-73`). The `_Actor` Protocol reads only `id: uuid.UUID`, bound at call time. The dispatch **raises `ValueError` on an unhandled `Scope` member** (`scoping.py:79`) — do not add a member without an explicit branch, or you re-open the exact AD-10 leak this module exists to prevent.
- **The predicate is already unit-tested on compiled SQL.** [`tests/domain/test_scoping.py:23-38`](../../backend/tests/domain/test_scoping.py) asserts `Scope.REPORTS` compiles to `employee.manager_id = :manager_id_1` and binds `actor.id`. Reuse it; do not duplicate it.
- **The scoped-getter contract is armed.** [`tests/test_scoped_getters.py`](../../backend/tests/test_scoped_getters.py) reflects over `repositories/*.py` and requires every `get_/list_/find_/fetch_` getter that takes a `session` to also take an `actor` (or be `EXEMPT`). The Employee getters already comply. This story adds **no new getters**, so `test_scoped_getters.py` must pass **unchanged** — no `EXEMPT` edits.
- **The actor is resolved fresh from the DB on every request.** [`services/auth.py`](../../backend/app/services/auth.py) `resolve_actor(token)` decodes only `sub`, then loads the Employee row from the database; role (and, in future, scope) is read from that row, **never** from a token claim (`auth.py:115-116`, `AD-14`/`NFR-03`). This is *why* AC2's "no re-login/token refresh" already holds structurally — your test proves it, it does not build it.
- **The reporting data exists.** `Employee.manager_id` ([`repositories/models.py:71-92`](../../backend/app/repositories/models.py)) is a nullable self-referential FK, indexed (`employee (manager_id)` serves this predicate), with a `CHECK (id <> manager_id)` backstop. Migration `0002_department_and_employee` created it. The repository helpers `list_employees(session, actor, limit, offset)` and `get_employee(session, actor, employee_id)` already thread the actor and compose `employee_scope_predicate(Scope.ALL, actor)`.

### Scope boundaries — what NOT to build (prevents contradicting the API contract and creating dead code)

- **Do NOT open any `/employees` endpoint to Managers.** api-contracts §4.2 grants all five `/employees` endpoints to the **Admin alone** (scope `all`). Story 1.6's AC and [`api/v1/employees.py`](../../backend/app/api/v1/employees.py) enforce `403 ACTION_NOT_PERMITTED` for any non-Admin via the role gate, *before* any scope predicate runs (`G3`). Granting Managers `REPORTS` scope on `/employees` would directly contradict the contract and Story 1.6.
- **Do NOT add a `require_scope` dependency or a role→scope selection layer now.** There is **no endpoint in Epic 1 that a Manager may call to read Employee data** (`/team` is Epic 3 `FR-19`; `GET /employees/<id>/balances` is Epic 2 `FR-07`, `reports`-scoped). Building scope-selection machinery with no live consumer is speculative dead code — Story 1.4 deliberately avoided exactly this kind of premature widening. Epic 2 wires `Scope.REPORTS` into its first genuinely data-scoped resource (the Leave Request). Leave `services/employee.py` and `repositories/employee.py` scope selections at `Scope.ALL` (correct: an Admin's scope genuinely is everyone).
- **Do NOT change any getter signature.** `list_employees` / `get_employee` keep their `(session, actor, ...)` shape (Story 1.6 Trap 1).
- **No frontend work.** Story 1.7 has **zero** frontend acceptance criteria — unlike Stories 1.5/1.6 (which shipped React screens), this is a backend verification/test-only story. Do not add or modify anything under `frontend/`.
- **Do NOT touch** `resolve_actor` / `get_current_employee` (the `G4` deactivated-token question is deliberately open — see Deferred), `api/v1/errors.py` (the `CODE_TO_STATUS` map is populated only from `main.py`), or `api/v1/pagination.py`.
- **No new vocabulary codes, no new migration.** This story asserts existing behavior; `test_model_migration_agreement.py` (`alembic check`) will fail the build if a stray model change sneaks in.

### The SM-3 coverage matrix — design (AC4, the unique deliverable)

**Intent (`SM-3`, quoted from PRD §8):** *"`SM-3` — Authorization is scoped to data, not to role. Target: for every endpoint accepting a Leave Request identifier, an authenticated Manager who is not the applicant's Manager receives the same response as for a nonexistent request. Zero endpoints authorize on role name alone. Validates `FR-03`, `DR-12`."* No Leave Request exists in Epic 1, so the *satisfaction* of SM-3 (the byte-identical-404 assertions for a non-report's Leave Request) lands in Epic 2. **This story builds the harness** and registers Epic 1's identifier endpoints so that any later identifier endpoint that forgets to declare a scope fails the build.

**Model it on the existing armed guardrails**, not from scratch:
- Registry-plus-completeness shape → copy the spirit of [`tests/test_scoped_getters.py`](../../backend/tests/test_scoped_getters.py) (explicit registry, `@pytest.mark.parametrize` per item, vacuity guard `test_there_are_getters_to_inspect`).
- "Guard the guard" → copy the spirit of [`tests/test_architecture.py`](../../backend/tests/test_architecture.py) `test_every_contract_in_pyproject_is_actually_exercised` (a registry that gets silently emptied must fail).
- Route enumeration precedent → [`tests/integration/test_employees.py:645-655`](../../backend/tests/integration/test_employees.py) already reads `app.openapi()["paths"]`. Either `app.openapi()["paths"]` (path templates + methods, keys already `/api/v1/...`) or iterating `app.main.app.routes` for `APIRoute` with a path parameter works; prefer `app.routes` so you also get `route.methods` cleanly. Filter out `HEAD`/`OPTIONS`.

**"Accepts a resource identifier"** = the path template carries a path parameter (`{...}`). All five Epic 1 identifier endpoints are listed in Task 3. `/me`, `/auth/*`, `/health`, and the collection `GET`/`POST /employees` and `/departments` carry no path parameter and are out of scope for the matrix.

**Registry value = a set of scopes** (`frozenset[Scope]`), because api-contracts §4 grants some endpoints more than one scope by role (e.g. Epic 2's `GET /leave-requests/<id>` is `self, reports, all`). For Epic 1 every value is `{Scope.ALL}`. Keeping it a set now means Epic 2 extends values without reshaping the registry.

### Manager-scope behavioral proof — design (AC1, AC2, AC3)

Because no live Manager read endpoint exists yet, prove the scope at the **repository/predicate level against real PostgreSQL** — this is honest and is exactly what the ACs ("*when the resolver/scope is evaluated*") describe. Compose the predicate into a `select(Employee).where(employee_scope_predicate(Scope.REPORTS, manager))` and assert on the returned rows. The end-to-end HTTP round trip for a Manager waits for Epic 2's `reports`-scoped endpoints; do not fabricate a throwaway Manager route to force one (contrast: Story 1.4 used a throwaway route only to prove the *role gate* mechanism, which had no real endpoint either — acceptable, but here the predicate is directly testable without a route, which is cleaner).

Key correctness points to assert:
- The predicate is applied **in the SQL** — an out-of-scope row is never returned, not returned-then-filtered (`AD-10`/`NFR-04`).
- Reassignment reflects **without re-resolving the Manager's identity** — reuse the same actor object/token; only the *report's* `manager_id` changed (`DR-12` decision-time evaluation).
- A NULL `manager_id` row is excluded because `NULL = :actor_id` is never true in SQL — assert this explicitly rather than assuming it.

### Technical requirements & architecture compliance

- **AD-10 (binding invariant):** *"No repository exposes an unscoped getter... A Manager's scope is `employee.manager_id = :actor_id`, evaluated at request time, so a reassignment takes effect on the next decision."* [Source: ARCHITECTURE-SPINE.md#AD-10, line 125]. Scope is a SQL predicate, never a post-retrieval filter; a scope miss is a **byte-identical 404**, never 403.
- **DR-12:** *"A Manager's authority over a Leave Request derives from the Direct Report relationship to its applicant, not from holding the Manager role. The relationship is evaluated at decision time: if an applicant's Manager changes while their request is Pending, the current Manager decides it. Authorization is data-scoped, and the scope is applied in the query."* [Source: prd.md line 490].
- **G3 (403 vs 404) — do not conflate:** role-denied → `403 ACTION_NOT_PERMITTED`, decided at the boundary before any row is read; in-scope role but the identified row is not the actor's → `404`, byte-identical to a nonexistent id. [Source: api-contracts.md §1]. Story 1.6 delivered the `403` half for `/employees`; this story's tests exercise the `404`/scope-miss reasoning at the predicate level (a Manager's REPORTS predicate simply does not select a non-report — the service would turn the resulting `None` into `not_found()`).
- **Layering (AD-1):** the four-layer discipline holds — `api → services → repositories → domain`, no back-edges, `domain/`/`services/` import no HTTP. Tests live under `backend/tests/`. `lint-imports` is the build gate ([`test_architecture.py`](../../backend/tests/test_architecture.py)).

### Library / framework requirements (already pinned — match, don't add)

- **Python 3.13**, **FastAPI** on uvicorn, **SQLAlchemy 2.0** (`select(...).where(...)`, `session.scalars(...).unique()`), **Alembic** owns schema, **PostgreSQL 18**, **pytest** as the build/test runner. [Source: architecture.md §4]. No new dependency is needed for this story. Route introspection uses `fastapi.routing.APIRoute` and the app's `.routes` / `.openapi()` — both already available.
- Enumerated values (roles, codes) are declared once in `domain/vocabulary.py` and re-exported via `services/authorization.py`; `test_vocabulary_literals.py` forbids the string literals `"ADMIN"`/`"MANAGER"`/`"EMPLOYEE"` outside `domain/`. If your test needs a role, reference `authz.ROLE_MANAGER` etc., not a string literal.

### File structure & files to touch

| File | NEW/UPDATE | Reason |
|------|-----------|--------|
| `backend/tests/test_scope_matrix.py` | **NEW** | The SM-3 coverage-matrix test (AC4): enumerate identifier endpoints from `app.main.app`, register Epic 1's five with their §4 scope, fail on any unregistered identifier endpoint. Vacuity + guard-the-guard checks. No DB. |
| `backend/tests/integration/test_manager_scope.py` | **NEW** | DB-backed proof of AC1/AC2/AC3: reporting-edge membership, request-time reassignment without re-login, NULL-manager exclusion. Reuses the `_World.make(...)` factory pattern from `test_employees.py`. |
| `backend/tests/domain/test_scoping.py` | **NO CHANGE (confirm green)** | Already asserts the `Scope.REPORTS` compiled predicate and its bound actor id. |
| `backend/app/repositories/scoping.py` | **NO CHANGE** | `Scope.REPORTS`/`Employee.manager_id == actor.id` already implemented and tested. |
| `backend/app/{services,repositories}/employee.py` | **NO CHANGE** | Keep `Scope.ALL`; no Manager consumer in Epic 1. Do not add role→scope selection. |
| `backend/tests/test_scoped_getters.py` | **NO CHANGE** | No new getters; contract already satisfied. |
| `frontend/**` | **NO CHANGE** | No frontend ACs in this story. |

### Testing requirements & standards

- **Two test trees, load-bearing boundary.** `tests/domain/` is **DB-free** (its `conftest.py` deliberately defines no DB fixture); `tests/integration/` runs against **real PostgreSQL** and `pytest.skip`s loudly when `.env`/Postgres is absent. Put the matrix test at the top level (`tests/test_scope_matrix.py`) — it introspects the app object only, no DB. Put the behavioral proof under `tests/integration/`.
- **`import app.main  # noqa: F401`** at the top of any module that reads route registration or asserts a `code → HTTP status` mapping — `CODE_TO_STATUS` and the full route set only exist once `app.main` is imported (Story 1.4 review finding: three domain tests were false-green without it).
- **Reuse factories, don't invent:** the `callers` fixture ([`test_role_gate.py`](../../backend/tests/integration/test_role_gate.py)) and the `_World` / `make(role, *, manager_id=..., is_active=..., label=...)` factory ([`test_employees.py`](../../backend/tests/integration/test_employees.py)) already build per-role Employees and manager/report topologies with unique uuid-suffixed emails and teardown. Use `make(manager_id=...)` to wire the reporting edges this story tests.
- **Expected outcome:** full backend `pytest` stays green (prior suite was 156 passed after Story 1.6) plus the new tests, with 0 unexpected skips; `lint-imports` → 7 kept, 0 broken; `alembic check` clean (no schema change).

### Previous story intelligence

- **Story 1.4 (authorization primitives) — the foundation.** Built `scoping.py` *for this story*; its Task 6 unit-tested the Manager predicate "evaluated from the actor at call time — never cached from the token." Its Testing standards explicitly state: *"Story 1.7 registers Epic 1's endpoints in the `SM-3` matrix."* The scope dispatch was hardened during review to **raise on an unhandled `Scope`** rather than fall through to `true()` — respect that. `require_role(*allowed)` raises `ValueError` if called with no roles.
- **Story 1.6 (employees & reporting lines) — the data source.** Built `manager_id`, `list_employees`/`get_employee` (the "first live consumer" of `scoping.py`, at `Scope.ALL`). Its notes predicted 1.7 would "vary the scope (Admin→ALL, Manager→REPORTS) without touching these signatures" — **but** the actual Epic 1 story has no Manager read endpoint to vary it on, so that wiring correctly belongs to Epic 2 (see Scope boundaries). Review lesson carried in: re-reads needing fresh joined relationships used `populate_existing=True`; a role-gated frontend query must gate `enabled` on role (N/A here — no frontend).
- **Story 1.5 (departments) — pattern source.** Established that scope-`all` reference reads are `EXEMPT` from the scoped-getter guardrail (a Department is not Employee data); this story neither exempts nor adds getters. Pagination bound/clamp already reusable.

### Git intelligence

Recent commits (`git log`): `b585465 feat(story-1.6)` → `6b4b75c feat(story-1.5)` → `4dbf35d feat(story-1.4)` → `a5b26c3 fix(story-1.3)`. Story 1.6's commit touched `repositories/employee.py`, `services/employee.py`, `api/v1/employees.py`, `tests/integration/test_employees.py`, `tests/test_reporting_cycle.py` — the pattern for a full slice. **Story 1.7's diff should be almost entirely under `backend/tests/`** (plus, at most, confirming-green edits) — if you find yourself editing `app/repositories/` or `app/api/`, re-read the Scope boundaries above, because that likely means you are building Epic 2's work early.

### Project structure notes

- No `project-context.md` and no UX artifact exist in this project; the binding sources are epics.md, ARCHITECTURE-SPINE.md, architecture.md, api-contracts.md, erd.md, and prd.md.
- Alignment: new files land under `backend/tests/` following the existing `tests/` vs `tests/integration/` vs `tests/domain/` split. No conflict with the unified structure. No `app/` module additions, so no import-linter surface changes.

### References

- [Source: epics.md#Story-1.7 (lines 809-837)] — the four acceptance criteria; the note that this story builds the harness and registers Epic 1's endpoints but does not satisfy SM-3.
- [Source: epics.md#Story-1.6 (lines 728-807, esp. 760)] — the `403`-role-gate half; `G3` split; the reporting-line data model.
- [Source: prd.md line 630] — SM-3 verbatim. [Source: prd.md line 490] — DR-12 verbatim. [Source: prd.md line 148-160] — FR-03 consequences.
- [Source: ARCHITECTURE-SPINE.md#AD-10 (line 121-125)] — authorization is a query predicate; the Manager scope `employee.manager_id = :actor_id` evaluated at request time; absence is a byte-identical 404. [Source: ARCHITECTURE-SPINE.md#AD-14, #AD-22].
- [Source: api-contracts.md §1] — 401/403/404 semantics, the `G3` 403-vs-404 rule, the `{code,message,details}` envelope. [Source: api-contracts.md §4] — per-endpoint role+scope grants; scope notation `self`/`reports`/`all`.
- [Source: erd.md §2.1, §4.2, §4.4] — `Employee.manager_id` nullable self-FK, `CHECK (id <> manager_id)`, the `employee (manager_id)` index serving the scope predicate.
- Code: [`repositories/scoping.py`](../../backend/app/repositories/scoping.py), [`services/authorization.py`](../../backend/app/services/authorization.py), [`services/auth.py`](../../backend/app/services/auth.py), [`repositories/employee.py`](../../backend/app/repositories/employee.py), [`api/v1/employees.py`](../../backend/app/api/v1/employees.py), [`api/v1/dependencies.py`](../../backend/app/api/v1/dependencies.py), [`main.py`](../../backend/app/main.py), [`tests/domain/test_scoping.py`](../../backend/tests/domain/test_scoping.py), [`tests/test_scoped_getters.py`](../../backend/tests/test_scoped_getters.py), [`tests/test_architecture.py`](../../backend/tests/test_architecture.py), [`tests/integration/test_employees.py`](../../backend/tests/integration/test_employees.py).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context)

### Debug Log References

- Initial `test_scope_matrix.py` enumerated routes via `app.routes` + `isinstance(route, fastapi.routing.APIRoute)` as the task text suggested. Under the pinned FastAPI 0.139.0 this discovered **zero** identifier operations — `include_router(prefix=...)` leaves `app.routes` holding a single opaque `_IncludedRouter` whose nested `APIRoute`s are not exposed there (confirmed by dumping route types: only starlette `Route` objects for docs/openapi plus one `fastapi.routing._IncludedRouter` with `path=None`). Pivoted enumeration to `app.openapi()["paths"]` — the equivalent source the task explicitly offered and the one `test_employees.py`'s AC12 check already uses. It yields clean, prefix-resolved `{param}` templates with `HEAD`/`OPTIONS` already excluded. All matrix assertions then passed.

### Completion Notes List

- **Story type:** backend verification + test-harness only. Zero application-code changes, zero frontend changes — the entire diff is under `backend/tests/`, matching the story's Git-intelligence prediction. The Manager predicate (`Employee.manager_id == actor.id`) and the scope resolver were already built and unit-tested by Story 1.4; this story proves and gates them, it does not re-implement them.
- **AC1/AC2/AC3 (behavioral proof) — `tests/integration/test_manager_scope.py` (real PostgreSQL, 3 tests).** AC1: `Scope.REPORTS` composed into a real `select(Employee)` returns exactly Manager A's report R, excluding another Manager's report and the Managers themselves — proving a *data* scope (A and B hold the same MANAGER role, yet A's scope holds only A's report), applied IN the SQL. AC2: reassigning R from A→B through the real `employee_service.update_employee` write path (the one `PATCH /employees/<id>` uses) flips scope membership on the next evaluation, with the A/B actor objects captured **once** and reused unchanged — no token minted, no re-login (DR-12 decision-time evaluation). AC3: a `manager_id = NULL` Employee is excluded from **every** seeded Manager's `Scope.REPORTS`, asserted explicitly because `NULL = :actor_id` is never true in SQL.
- **AC1 (compiled-predicate) — `tests/domain/test_scoping.py` unchanged, confirmed green.** Already asserts `Scope.REPORTS` compiles to `employee.manager_id = :manager_id_1` and binds `actor.id` at call time (line 37). No edit needed or made.
- **AC4 (the unique deliverable) — `tests/test_scope_matrix.py` (DB-free, 9 test cases).** Explicit `frozenset[Scope]` registry over `(METHOD, path)`; Epic 1's five identifier endpoints registered at `{Scope.ALL}`. Completeness assertion (every exposed identifier operation must be registered) is the AC4 teeth; vacuity guard (enumeration non-empty) and two guard-the-guard checks (registry non-empty; no stale entry) mirror `test_scoped_getters.py` and `test_architecture.py`. **Teeth verified adversarially:** injecting an unregistered `GET /api/v1/leave-requests/{request_id}` route makes the completeness test fail, naming the offending operation. Module docstring records that Epic 2 extends the registry with the `reports`/`self` Leave-Request endpoints where SM-3 is actually *satisfied*.
- **Scope boundaries respected:** no `/employees` endpoint opened to Managers, no `require_scope`/role→scope layer added, no getter signature changed, `services/`/`repositories/employee.py` left at `Scope.ALL`, `resolve_actor`/`errors.py`/`pagination.py` untouched, no new vocabulary code, no migration.
- **Validation:** `pytest` → 168 passed (156 prior + 12 new), 0 skips; `lint-imports` → 7 kept, 0 broken; `alembic check` → no new upgrade operations (no schema drift). `test_scoped_getters.py` passes unchanged (no new getters, no `EXEMPT` edits).

### File List

- `backend/tests/integration/test_manager_scope.py` — **NEW** — DB-backed proof of the reporting-edge scope (AC1/AC2/AC3): membership, request-time reassignment without re-login, NULL-manager exclusion.
- `backend/tests/test_scope_matrix.py` — **NEW** — the SM-3 coverage-matrix harness (AC4): enumerate identifier endpoints from the app, register Epic 1's five with their §4 scope, fail on any unregistered identifier endpoint; vacuity + guard-the-guard checks.
- `_bmad-output/implementation-artifacts/1-7-scope-authority-to-the-reporting-relationship.md` — **UPDATE** — frontmatter `baseline_commit`, task checkboxes, Dev Agent Record, File List, Change Log, Status.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — **UPDATE** — story 1-7 status transitions (ready-for-dev → in-progress → review).

## Change Log

| Date | Change |
|------|--------|
| 2026-07-11 | Implemented Story 1.7 (test-harness/verification only). Added `tests/integration/test_manager_scope.py` (AC1–AC3, real PostgreSQL) and `tests/test_scope_matrix.py` (AC4, SM-3 coverage-matrix harness, DB-free). No application-code or frontend changes. Full suite green: pytest 168 passed / 0 skips, lint-imports 7 kept / 0 broken, alembic check clean. Status → review. |
