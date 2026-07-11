---
baseline_commit: a5b26c3cf5ff0ee2c9531f931909fbb0457875d4
---

# Story 1.4: Authorization Primitives — the Role Gate, Scoped Reads, and the 404 Convention

Status: done

Epic: 1 — Secure Access and Organization Administration (Phase 1, correctness core)
Story Key: `1-4-authorization-primitives-the-role-gate-scoped-reads-and-the-404-convention`
Created: 2026-07-11

## Story

As a developer implementing any protected endpoint,
I want the role gate, the scoped-repository contract and the status-code semantics to exist before the first protected resource does,
So that no endpoint invents its own authorization and no later story rewrites the one that came before it.

## Acceptance Criteria

Verbatim from `epics.md#Story 1.4` (lines 654–680). Do not paraphrase; the wording is the contract. AC numbering is added for task traceability.

**AC1 — Every getter that can return another Employee's data takes the actor (`AD-10`, `NFR-04`)**
**Given** the `repositories/` package
**When** an architecture test inspects the signature of every getter that can return another Employee's data
**Then** each takes the acting Employee as a parameter
**And** no getter exists that returns such data without one

**AC2 — Scope is a SQL predicate, never a post-retrieval filter (`NFR-04`, architecture §7)**
**Given** a scoped repository getter
**When** it executes
**Then** the actor's scope is applied as a predicate in the SQL
**And** it is never applied as a filter over rows already retrieved

**AC3 — 403 is reserved for "may see, may not act" (api-contracts §1)**
**Given** a resource the actor is permitted to see but not permitted to act upon
**When** the acting endpoint is called
**Then** the response is `403`, which is reserved for exactly this case

**AC4 — A scope miss is 404, byte-identical to a nonexistent identifier (`AD-10`, `FR-03`)**
**Given** a scoped read whose predicate matches no row
**When** the `api/` layer handles it
**Then** the response is `404`, byte-identical in body and equal in status to the response for an identifier that names nothing at all
**And** it is never `403`, which would disclose that the resource exists

**AC5 — The refusal happens in an `api/` dependency, at the boundary (`NFR-03`, `AD-14`)**
**Given** a restricted operation
**When** it is invoked directly, by a client that never rendered its control
**Then** it is refused in an `api/` dependency, at the API boundary
**And** `NFR-16`'s role-appropriate rendering is never the only thing preventing the action

> *(From epics.md line 680, the scope of this story:)* This story delivers the **mechanism and its unit tests**. Its first scoped **resource** is a Department in Story 1.5; its first genuinely data-scoped resource — where one Employee's row is invisible to another — is a Leave Request in Epic 2. Ordering it here means Stories 1.5 and 1.6 **consume** these primitives rather than each inventing a role check that Story 1.7 would then rewrite.

## Tasks / Subtasks

- [x] **Task 1: `domain/vocabulary.py` (UPDATE) — declare the two new error codes** (AC: 3, 4)
  - [x] Add `ACTION_NOT_PERMITTED = "ACTION_NOT_PERMITTED"` (api-contracts §2 → 403). This is the code every `403` carries.
  - [x] Add the 404-convention code — recommended `RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"` (→ 404). See 🚨 Trap 5 for the open question this settles and why it is added despite not appearing in api-contracts §2's enumerated list.
  - [x] Append both to `__all__`. `tests/test_vocabulary_literals.py` auto-iterates `__all__`, so both values are immediately guarded against appearing as literals anywhere else under `app/`/`seed/`.
  - [x] Extend the module docstring's "What arrives, and where" list with a Story 1.4 line, matching the existing prose style.
- [x] **Task 2: `main.py` (UPDATE) — wire the two codes to their statuses** (AC: 3, 4)
  - [x] Extend the existing `CODE_TO_STATUS.update({...})` call: `vocabulary.ACTION_NOT_PERMITTED: 403` and `vocabulary.RESOURCE_NOT_FOUND: 404`.
  - [x] Do **not** touch `api/v1/errors.py` — the map is populated only from `main.py` (the composition root, outside the contracts). See 🚨 Trap 3.
- [x] **Task 3: `services/authorization.py` (NEW) — the raise sites and the role re-export** (AC: 3, 4, 5)
  - [x] Create `backend/app/services/authorization.py`. Docstring names `FR-03`, `AD-10`, `AD-14`, `NFR-03`, `NFR-04` (SM-6).
  - [x] `assert_role(actor: <structural actor>, allowed: tuple[str, ...]) -> None` — raise `DomainError(code=vocabulary.ACTION_NOT_PERMITTED, message=_ACTION_NOT_PERMITTED_MESSAGE, details={})` when `actor.role not in allowed`; otherwise return. One fixed message string, module-level constant (mirrors `services/auth.py`'s `_AUTH_FAILED_MESSAGE`).
  - [x] `not_found() -> NoReturn` — raise `DomainError(code=vocabulary.RESOURCE_NOT_FOUND, message=_NOT_FOUND_MESSAGE, details={})`. **One** message constant, empty `details`, so every 404 — genuine or scope-miss — is byte-identical (AC4). See 🚨 Trap 2.
  - [x] Re-export the role constants so `api/` can name them without a forbidden direct import of `domain/`: `from app.domain.vocabulary import ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE`. See 🚨 Trap 1 — this indirection is the whole reason this lives in `services/`.
  - [x] This module raises `DomainError` and touches no HTTP (contract 4). It performs no I/O and opens no transaction — it is a pure guard, but it lives in `services/` because only `services/` may construct a `DomainError`, and `api/` needs the role constants through it.
- [x] **Task 4: `api/v1/dependencies.py` (UPDATE) — the role gate dependency** (AC: 3, 5)
  - [x] Add `require_role(*allowed: str) -> Callable[..., Actor]`: a dependency **factory** returning an inner dependency that `Depends(get_current_employee)`, calls `authorization.assert_role(actor, allowed)`, and returns the `actor` on success so a route can chain `Depends(require_role(...))` and still read the caller.
  - [x] Import the role helpers via `from app.services import authorization as authz` (indirect: `api → services`, allowed). Do **not** `from app.domain.vocabulary import ...` here — contract 2 forbids it, even under `TYPE_CHECKING` (🚨 Trap 1).
  - [x] Keep `get_current_employee` authentication-only and unchanged in behaviour. The role gate builds **on top of** it; it does not replace it (Story 1.3 Dev Notes said so explicitly).
  - [x] If the scope predicates you introduce in Task 6 need `manager_id`, add it to the `Actor` Protocol (`manager_id: uuid.UUID | None`). Add only the fields a gate/scope actually reads — do not widen the Protocol speculatively.
- [x] **Task 5: `tests/` (NEW) — the scoped-getter architecture test** (AC: 1, 2)
  - [x] Create a test (recommended `backend/tests/test_scoped_getters.py`, top-level, DB-free) that reflects over every public function in `app/repositories/*.py`, and asserts each getter that can return Employee-derived data either (a) is in an explicit EXEMPT registry or (b) takes an acting-Employee parameter. See 🚨 Trap 4 and the Testing standards section for the exact shape.
  - [x] Seed the EXEMPT registry with the two actor-resolution getters — `get_by_email`, `get_by_id_with_department` — each already carrying the "why exempt" docstring. The test's failure message must tell a future developer to either scope the new getter or justify a new exemption.
  - [x] Today this test passes because the only getters are the two exempt ones. That is intended: it is an **armed guardrail** for Stories 1.5/1.6/1.7 and Epic 2, not a test of existing scoped behaviour (none exists yet).
- [x] **Task 6: `repositories/scoping.py` (NEW) — the scope resolver Story 1.7 consumes** (AC: 2)
  - [x] Create the scope-predicate resolver that `epics.md#Story 1.7` line 817 calls "the scope resolver introduced by Story 1.4": given an actor, produce the SQLAlchemy predicate — `self` (`Model.<owner_id> == actor.id`), `reports` (`Employee.manager_id == actor.id`), `all` (no predicate / always-true). It returns a predicate to be composed into a `select(...).where(...)`, never a Python-side filter (AC2).
  - [x] Unit-test the Manager predicate resolves to `employee.manager_id == :actor_id` (Story 1.7's AC), evaluated from the actor at call time — never cached from the token.
  - [x] Keep it minimal and grounded in the resolver's one guaranteed consumer shape (the Employee reporting edge). Its first **live getter** consumer is Story 1.7 (and Epic 2's Leave Request reads). Do not build scope machinery for resources that do not yet exist — 🚨 Trap 6.
- [x] **Task 7: Tests — role gate, 404 byte-identity, and the layer boundary** (AC: 3, 4, 5)
  - [x] Domain/unit (DB-free, `tests/domain/`): `assert_role` raises `ACTION_NOT_PERMITTED` for a disallowed role and returns for an allowed one; construct a structural fake actor (no DB), assert the raised `DomainError.code` and `.message`.
  - [x] Byte-identity (AC4): drive `authorization.not_found()` through `domain_error_handler` twice — once framed as "nonexistent id", once as "scope miss" — and assert the two `JSONResponse` bodies are **byte-identical** (`response.body`) and both `404`. Since there is no live scoped endpoint yet, prove it at the handler/service seam.
  - [x] Role-gate at the boundary (AC5): mount a throwaway test-only route guarded by `require_role(authz.ROLE_ADMIN)` on a `TestClient` app fixture and assert a MANAGER/EMPLOYEE token gets `403 {code: ACTION_NOT_PERMITTED}` and an ADMIN token passes — proving the refusal is in the dependency, before the route body runs. Do **not** register this route on the real `api_v1_router`.
  - [x] Full suite stays green: `lint-imports` (7 contracts), `test_vocabulary_literals.py`, `test_error_envelope.py` (do not map `TEST_ONLY_CODE`), `alembic check` (`test_model_migration_agreement.py`). **No migration is expected** — this story adds no column (🚨 Trap 7).
- [x] **Task 8: Prove it end-to-end** (AC: 3, 4, 5)
  - [x] Run the full backend suite and record counts in Dev Agent Record. Run `lint-imports` in `backend/` and confirm 0 broken.
  - [x] There is **no frontend and no new user-facing endpoint** in this story (see Project Structure Notes). Declare the interactive click-through gap as Stories 1.1–1.3 did; the proof here is the passing suite plus the armed architecture test.

### Review Findings

Code review 2026-07-11 (parallel adversarial layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor). Acceptance Auditor confirmed all 5 ACs and all 8 traps honored; findings below are correctness/robustness issues, not AC deviations. 5 patch, 0 defer, 3 dismissed.

- [x] [Review][Patch] Domain auth tests are a false-green — 3 tests fail in isolation (import-order coupling on `CODE_TO_STATUS`) [backend/tests/domain/test_authorization.py:87] — `CODE_TO_STATUS` starts `{}` in `errors.py` and is only populated when `app.main` is imported. `test_resource_not_found_maps_to_404`, `test_action_not_permitted_maps_to_403`, and `test_a_nonexistent_id_and_a_scope_miss_are_byte_identical` never import `app.main`, so `pytest tests/domain/` yields **3 failed** (`assert 500 == 404`, KeyError). They pass only in a full run where `test_me.py`/`test_login.py` import `app.main` first and mutate the shared global. Verified by running. AC3/AC4 (the story's sharpest ACs) are not actually verified independently. Fix: add `import app.main  # noqa: F401` to the test module (mirrors `tests/integration/test_role_gate.py:36`). Also add `else: raise AssertionError(...)` to the two mapping tests so a non-raising regression fails cleanly instead of `NameError` on unbound `response`.
- [x] [Review][Patch] Scope dispatch falls through to `true()` for any unhandled `Scope` member [backend/app/repositories/scoping.py:74] — the final `return true()` handles `ALL` implicitly, so a future enum member (`DEPARTMENT`, `TEAM`) added without a branch silently resolves to the unrestricted always-true predicate — the exact AD-10 leak this module exists to prevent. Fix: make `ALL` explicit (`if scope is Scope.ALL: return true()`) and `raise` on an unhandled member so a missing branch fails loud.
- [x] [Review][Patch] Armed guardrail is non-recursive and its docstring over-promises [backend/tests/test_scoped_getters.py:760] — `pkgutil.iter_modules` enumerates only top-level `repositories/*.py`, so a future unscoped getter in a subpackage (e.g. `repositories/leave/reads.py`) escapes the AC1 check entirely, despite the docstring billing it as the check that "fails the build the moment a future story adds `get_leave_request(id)`." Fix: use `pkgutil.walk_packages` for recursion; soften the docstring to state the matcher keys on `get_/list_/find_/fetch_` names + a `session` param + an `actor` param (a getter that breaks those conventions is not caught).
- [x] [Review][Patch] `require_role()` with no arguments locks out every caller [backend/app/api/v1/dependencies.py:90] — `*allowed` collects to `()`, so `assert_role`'s `actor.role not in ()` is always true → a mis-wired `Depends(require_role())` becomes a permanently-closed 403 endpoint with no startup/import failure. Fix: `assert allowed` (or raise `ValueError`) in the factory so the mis-declaration fails loud.
- [x] [Review][Patch] `test_an_absent_token_is_401_not_403` is needlessly skipped without a DB [backend/tests/integration/test_role_gate.py:686] — it exercises the empty-token → 401 path (no DB touched) but depends on the `callers` fixture (→ `db_connection`), so it is skipped when Postgres is absent. Fix: drop the unused `callers` fixture dependency so the 401-before-403 guarantee runs in a DB-less leg too.

**Dismissed (noise / by-design):** `RESOURCE_NOT_FOUND` outside api-contracts §2's enumerated list — documented Trap 5 decision, reconciled toward NFR-17. A `None` actor id rendering `= NULL` (matches zero rows) — no reachable call site; the actor is always a DB-resolved Employee with a real id. Guardrail's all-repository import at collection time coupling to unrelated import failures — inherent to a reflection test; a broken repository module failing the build is acceptable.

## Dev Notes

### What this story is, and what it is not

This story ships **plumbing, not a feature**. It has no user, no screen, and — uniquely so far — **no new HTTP endpoint a client can call**. It delivers four primitives every later authorization decision will reuse:

1. **The role gate** — an `api/` dependency (`require_role`) that refuses by *role* with `403 ACTION_NOT_PERMITTED`, decided at the boundary before any row is read.
2. **The 404 convention** — a single not-found refusal (`RESOURCE_NOT_FOUND` → 404) raised for both a nonexistent id and an out-of-scope one, guaranteeing they are byte-identical (`FR-03`, `AD-10`).
3. **The scoped-getter contract** — an armed architecture test asserting no repository getter returns another Employee's data without taking the actor.
4. **The scope resolver** — the predicate-builder Story 1.7 evaluates for a Manager (`employee.manager_id = :actor_id`).

**It is NOT:**
- **Not** a live 403/404 on a real resource. Departments (scope `all`) arrive in Story 1.5; the first genuinely data-scoped resource (a Leave Request, invisible across Employees) is Epic 2. So AC3/AC4 are proved at the **mechanism** level (unit tests, a throwaway test route, handler byte-identity), not against a shipping endpoint. This is exactly what epics.md line 680 means by "delivers the mechanism and its unit tests."
- **Not** a change to `get_current_employee`, `resolve_actor`, login, `/me`, or `/health`. The role gate is built on top of the authentication dependency; the authentication dependency stays authentication-only.
- **Not** the place to resolve **G4** (a since-deactivated Employee's still-valid token). Story 1.3 left it open deliberately; do not add an `is_active` check to the token path and write no test asserting one. See 🚨 Trap 8.
- **Not** a schema change. Every column scoping needs (`role`, `manager_id`, `department_id`, `is_active`) already exists on `Employee` (migration 0002).

### 🚨 Eight traps, in the order they will bite

**1. `api/` cannot name a role literal, and cannot import `domain/` to get the constant.** The role gate lives in `api/` but must compare against `ROLE_ADMIN`/`ROLE_MANAGER`/`ROLE_EMPLOYEE`. Two walls collide: contract 2 forbids `api → domain` (import-linter flags it even under `TYPE_CHECKING`, `exclude_type_checking_imports` is off — Story 1.3 proved this empirically), and `test_vocabulary_literals.py` forbids the string `"ADMIN"` appearing as a literal in `api/`. The escape is the **indirect re-export**: `services/authorization.py` does `from app.domain.vocabulary import ROLE_ADMIN, ...` and `api/` does `from app.services import authorization as authz` then references `authz.ROLE_ADMIN`. import-linter sees `api → services` (allowed; `allow_indirect_imports=true` on contract 2), never `api → domain`; the literal scan sees a name, not a string. This is the same indirection `errors.py`/`main.py` already use for `DomainError`.

**2. The 404 must be byte-identical, so there is exactly ONE raise site and ONE message.** AC4 is the hard one: a scope miss and a genuine "no such id" must be indistinguishable down to the bytes, or a Manager can probe which resources exist. The architecture guarantees this *structurally* — because there is no unscoped getter (AC1), both cases return `None` from the same scoped getter, and the service calls the same `not_found()`. Enforce it: one `_NOT_FOUND_MESSAGE` constant, `details={}` always, never interpolate an id or a resource name into the message. If two call sites ever pass different messages, byte-identity is gone and `FR-03` is violated silently.

**3. Do not touch `api/v1/errors.py` to add the new statuses.** `CODE_TO_STATUS` is `{}` in `errors.py` *by design* and is populated only from `main.py`, because contract 2 forbids `errors.py` (in `api/`) from importing `domain/vocabulary`. Add `ACTION_NOT_PERMITTED: 403` and `RESOURCE_NOT_FOUND: 404` to the `CODE_TO_STATUS.update({...})` call in `main.py`. Typing a code literal or importing vocabulary in `errors.py` fails the build — "and it will be right to," as the file says.

**4. The scoped-getter test inspects signatures; it cannot read intent — so it needs an explicit exempt registry.** AC1 says "no getter exists that returns such data without" an actor param. A reflection test cannot know that `get_by_id_with_department` is *legitimately* actor-less (it resolves the caller themselves, before scope exists). So the test carries an EXEMPT set `{"get_by_email", "get_by_id_with_department"}` and asserts every other public getter in `repositories/*.py` takes the actor. Both exempt getters already document *why* in their docstrings — the test's job is to make a future unscoped getter (Epic 2's `get_leave_request(id)`, the exact thing `AD-10`/architecture §7 forbid by name) fail the build unless it either scopes or is deliberately added to the registry with justification.

**5. `RESOURCE_NOT_FOUND` is not in api-contracts §2's enumerated list — this is a real gap, resolved toward NFR-17.** api-contracts §2 lists 20 codes and none is a not-found. Yet `NFR-17` (asserted from Story 1.2) requires *every* non-2xx body to carry the `{code, message, details}` envelope, and `test_error_envelope.py` plus the whole story chain established envelope uniformity — a framework-default `{"detail":"Not Found"}` would break it. So the 404 gets an enveloped code like every other refusal. `RESOURCE_NOT_FOUND` is the recommended name (UPPER_SNAKE, `AD-21`). This is flagged as the one open question for the user (see the handoff note); proceed with the recommended default so implementation is not blocked. Byte-identity (Trap 2) is unaffected by the code name.

**6. Do not build scope machinery for resources that do not exist yet.** The scope resolver (Task 6) is real and Story 1.7 depends on it — but its one guaranteed shape today is the Employee reporting edge (`manager_id`). Resist generalising it into a resource-agnostic framework for Leave Requests, Balances, Documents, etc. — those resources have no tables yet, and a speculative abstraction is exactly the "reinventing wheels / vague implementation" the process guards against. Introduce the resolver against the concrete Employee predicate; let Epic 2 extend it when real scoped resources arrive.

**7. No migration — and `alembic check` will tell on you if you accidentally add one.** Scoping reads existing columns; this story creates no table and no column. `test_model_migration_agreement.py` runs `alembic check`; if you change a model, the suite fails. If you find yourself writing a migration, stop — you have drifted out of this story's scope.

**8. Leave G4 exactly as Story 1.3 left it.** A since-deactivated Employee holding a still-valid token is an *open, non-blocking* decision (sprint-status PLANNING CONTEXT; Story 1.3 Dev Notes). `resolve_actor` deliberately does **not** check `is_active`. Do not "fix" it here as a drive-by, do not add an `is_active` clause to any token path, and write no test that asserts a deactivated token is rejected. It is to be settled before deployment as a one-line change with its own decision.

### Architecture compliance

- **`AD-1` (one-way imports).** `api → services → {repositories, domain}`, `repositories → domain`. `api/` never imports `repositories/` or `domain/` directly. This is why the role gate (`api/`) delegates its raise to `services/authorization.py`, exactly as `get_current_employee` delegates to `services/auth.resolve_actor`. Enforced by the 7 import-linter contracts in `test_architecture.py`; if you add a contract, update that file's `expected` dict in the same commit.
- **`AD-10` (authorization is a query predicate; absence is 404).** No repository exposes an unscoped getter; every read that could return another Employee's data takes the actor and applies scope *in the SQL*; out-of-scope is 404 byte-identical to nonexistent; 403 is reserved for "may see, may not act." This story installs the test that enforces the first clause and the raise site that guarantees the third. [Source: ARCHITECTURE-SPINE.md#AD-10; architecture.md §7]
- **`AD-14` (client renders authority; only the server enforces it).** Every restricted operation is checked in an `api/` dependency against the database, independently of anything the client sent beyond the token's subject. `require_role` reads `actor.role` off the DB-resolved actor, never a token claim. `NFR-16` rendering is never the only thing preventing an action (AC5). [Source: ARCHITECTURE-SPINE.md#AD-14]
- **`AD-21` (one canonical vocabulary).** `ACTION_NOT_PERMITTED` and `RESOURCE_NOT_FOUND` are declared once in `domain/vocabulary.py`, `UPPER_SNAKE_CASE`, and appear as literals nowhere else. Role constants likewise — `api/` reaches them only through the `services/` re-export.
- **`AD-5` (schema is the backstop, service is the gate).** A `CHECK`/constraint violation reaching a client is a defect and a 500, never a refusal or an authz mechanism. Authorization is decided in code (role gate, scope predicate), not by letting the database reject.
- **api-contracts §1 (403 vs 404, settled by G3).** The distinguishing test: *does the actor's role admit them to this endpoint at all?* If no → `403 ACTION_NOT_PERMITTED`, decided before any row is read (the role gate). If yes → the scope predicate runs, and a miss is `404`. Fixed decision order; never the reverse, never post-filter. [Source: api-contracts.md §1]
- **Layering of the four concerns:** role gate → `api/` dependency; scope predicate → `repositories/` (issued as SQL), reached through `services/`; 404 translation → `services/` raises the typed `DomainError`, one `api/` handler (already registered) maps it; transaction boundary → `services/` only. [Source: ARCHITECTURE-SPINE.md "Design Paradigm" & "Consistency Conventions"]

### Previous story intelligence — Story 1.3 (read this; it is first-hand)

- **`get_current_employee` is the seam you extend, not replace.** It returns the `Actor` (a structural `Protocol`, not `Employee` — `api/` can't import the ORM). The actor's `id` is the `:actor_id` your scope predicates consume. Its docstring already says "Story 1.4 extends this into role- and scope-gated dependencies." Keep it authentication-only.
- **The `Actor`/`DepartmentShape` Protocol idiom is mandatory, and `TYPE_CHECKING` does not save you.** Story 1.3 *tried* to annotate a return type via a `TYPE_CHECKING` import into `api/` and verified empirically that import-linter 2.13 flags it (it reasons over the AST). The established fix — a structural `Protocol` naming the shape without importing the class — is what `errors.py` (`DomainErrorLike`) and `dependencies.py` (`Actor`) already do. Any new `api/`-layer type that references the ORM uses a Protocol.
- **The error path is fully built; you are adding codes, not machinery.** `DomainError(code, message, details)` is raised in `services/`; `main.py` registers one handler against the base class and populates `CODE_TO_STATUS`; `errors.py` renders the envelope with `mode="json"`. You add two `vocabulary` constants and two `main.py` map entries. Nothing in `errors.py` or the handler changes.
- **"One raise site, one message string."** Story 1.2/1.3 made every rejection reason produce a byte-identical envelope and tested it by comparing raw bytes. The 404 convention (AC4) is the sharpest instance: one message constant, empty details.
- **Repository getters are plain module functions** taking `session: Session` first (`get_by_email(session, email)`, `get_by_id_with_department(session, employee_id)`), no repository class. Text columns are `mapped_column(Text, ...)` (not `Mapped[str]`, which becomes VARCHAR and breaks `alembic check`) — relevant only if you touch a model, which you should not.
- **`expire_on_commit=False`** is the standing `Session` idiom (`AD-3`), and it preserves *loaded* attributes but does not lazy-load a relationship after close — eager-load (`joinedload`) or read inside the block.
- **Test trees:** `tests/domain/` runs with **no** DB (conftest is deliberately fixture-free; pytest resolves fixtures walking up, never sideways). `tests/integration/` runs against **real PostgreSQL** and skips *loudly* on a missing/placeholder `.env`. `test_me.py` is the template for a TestClient auth test — it mints tokens with `security.create_token` and holds an actor+department+token helper. Domain tests monkeypatch (`auth.security.decode_token`, `auth.employee_repo...`, `auth.get_engine`) to drive branches DB-free — the pattern for unit-testing `assert_role`.

### Verified library / framework facts (checked against installed pins)

- **Stack (epics.md line 169 / SPINE Stack table):** Python 3.13 · FastAPI 0.139.0 · Pydantic 2.13.4 · SQLAlchemy 2.0.51 · Alembic 1.18.5 · psycopg 3.3.4 · PostgreSQL 18 · PyJWT 2.13.0 · pwdlib 0.3.0 · bcrypt 5.0.0 · **pytest 9.1.1** · import-linter 2.13.
- **FastAPI dependency factory:** `require_role(*allowed)` returning an inner function that uses `Depends(get_current_employee)` is the standard, supported "parameterized dependency" pattern — the factory captures `allowed` and the inner callable is what FastAPI resolves. No FastAPI feature beyond `Depends` is needed. `HTTPBearer(auto_error=False)` is already in place; do not add a second security scheme.
- **import-linter 2.13** analyses the import AST including `TYPE_CHECKING` blocks (`exclude_type_checking_imports` defaults off). Confirmed by Story 1.3. Plan for it: Protocols, not imports.
- **`typing`/`inspect` for the architecture test:** use `inspect.getmembers(module, inspect.isfunction)` filtered to functions *defined in* that module (`fn.__module__ == module.__name__`) and `inspect.signature(fn)` to read parameter names. Avoid `get_type_hints` on repository functions if it would force importing annotations that pull the ORM into the test's import graph — parameter-name inspection is sufficient and simpler.

### Testing standards

- **`pytest` is the build (`F-14`); there is no CI.** The full suite must stay green. Story 1.3 ran 72 backend tests; expect this story to add unit tests for `assert_role`, the 404 byte-identity, the role-gate boundary, the scope resolver, and the scoped-getter guardrail (auto-parametrized vocabulary/architecture scans will also pick up the two new `app/` modules).
- **Where each test goes:**
  - `tests/domain/test_authorization.py` (DB-free) — `assert_role` raise/return with a structural fake actor; `not_found()` raises the right code/message.
  - `tests/domain/test_scoping.py` (DB-free) — the Manager scope predicate is `employee.manager_id == :actor_id`; assert on the compiled SQLAlchemy expression, no DB.
  - `backend/tests/test_scoped_getters.py` (top-level, DB-free) — the reflection guardrail over `repositories/*.py` with the EXEMPT registry (AC1/AC2).
  - `tests/integration/test_role_gate.py` (real-PG, TestClient) — a throwaway route guarded by `require_role(authz.ROLE_ADMIN)` mounted on a test-only app; ADMIN passes, MANAGER/EMPLOYEE get `403 ACTION_NOT_PERMITTED` before the body runs (AC5). Follow `test_me.py`'s token-minting.
- **Byte-identity test (AC4):** invoke `domain_error_handler` (or the `not_found()`→handler path) for two framings and assert `resp_a.body == resp_b.body` and both status 404. Compare raw bytes, as the envelope tests do.
- **Do not add `TEST_ONLY_CODE`/`TEST_ONLY` to `CODE_TO_STATUS`** — `test_error_envelope.py` relies on an unmapped code defaulting to 500.
- **`SM-6`:** every new module docstrings the FR/DR/AD it implements. **`NFR-15`:** do not chase coverage on plumbing/happy paths; test the guarantees (byte-identity, the boundary refusal, the armed guardrail), not getters that don't exist yet.
- **Governing metric:** `SM-3` (data-scoped authority). Story 1.4 builds the harness and primitives; it does **not** claim to satisfy `SM-3` (no Leave Request exists to scope). Epic 2 does. Story 1.7 registers Epic 1's endpoints in the `SM-3` matrix.

### Project Structure Notes

- **New (backend):**
  - `backend/app/services/authorization.py` — `assert_role`, `not_found`, role re-exports.
  - `backend/app/repositories/scoping.py` — the scope resolver (Manager predicate; `self`/`reports`/`all`).
  - `backend/tests/test_scoped_getters.py` — the AC1/AC2 architecture guardrail.
  - `backend/tests/domain/test_authorization.py`, `backend/tests/domain/test_scoping.py` — DB-free unit tests.
  - `backend/tests/integration/test_role_gate.py` — the boundary-refusal test.
- **Modified (backend):**
  - `backend/app/domain/vocabulary.py` — two new codes + `__all__` + docstring line.
  - `backend/app/main.py` — two new `CODE_TO_STATUS` entries.
  - `backend/app/api/v1/dependencies.py` — `require_role` factory; possibly one field added to `Actor` (`manager_id`) if a scope reads it in the `api/` layer.
- **Untouched (must stay so):** `api/v1/errors.py` (map populated from `main.py`), `api/v1/me.py` / `auth.py` / `health.py` (stay as they are — `/health` and `/auth/login` anonymous, `/me` self-scoped 401-gated), `services/auth.py` `resolve_actor` (authentication-only; G4 untouched), the two exempt getters in `repositories/employee.py`, all models and migrations, `test_architecture.py` (unless you add an import contract — you should not need to).
- **No frontend in this story.** Unlike Stories 1.2/1.3, there is no client surface: no endpoint, no screen. `NFR-16`'s role-appropriate rendering (hiding controls a role cannot use) arrives with the first role-gated UI in Story 1.5's Departments screen, which *consumes* this story's role gate. Do not add frontend code.

### References

- [epics.md#Story 1.4](../planning-artifacts/epics.md) — story statement and all five criteria, verbatim (lines 648–680); the scope note "delivers the mechanism and its unit tests" (line 680).
- [epics.md#Story 1.7](../planning-artifacts/epics.md) — "the scope resolver introduced by Story 1.4" (line 817); the Manager predicate `employee.manager_id = :actor_id` (line 819); the `SM-3` matrix Epic 1 registers (line 832).
- [epics.md#Story 1.5](../planning-artifacts/epics.md) — the first consumer: `403` for a non-Admin write, refused server-side "independently of whether the client rendered the control (`NFR-03`, Story 1.4)" (line 708).
- [epics.md#Story 1.6](../planning-artifacts/epics.md) — `403` role denial "decided by the role gate in the `api/` dependency *before any row is read*" (line 758); the `403`-here/`404`-there reconciliation (line 760, `G3`).
- [ARCHITECTURE-SPINE.md#AD-10](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — no unscoped getter; scope as a SQL predicate; 404 byte-identical to nonexistent; 403 reserved; Manager scope evaluated at request time.
- [ARCHITECTURE-SPINE.md#AD-14](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — every restricted operation checked in an `api/` dependency against the DB; `NFR-16` rendering never the only guard.
- [ARCHITECTURE-SPINE.md#AD-1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — import direction; `api/` never imports `repositories/`/`domain/`; where each layer's responsibility sits.
- [ARCHITECTURE-SPINE.md#AD-21](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — enumerated strings declared once in `domain/`, literals nowhere else.
- [architecture.md §7](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md) — the reporting edge is `manager_id`; "There is no `get_leave_request(id)`"; `NFR-04` "is not a code-review guideline; it is the only available API."
- [api-contracts.md §1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the status table; the `G3` settlement of 403-vs-404; "does the actor's role admit them to this endpoint at all?"
- [api-contracts.md §2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the `{code, message, details}` envelope; `ACTION_NOT_PERMITTED` → 403; the 20-code table (note: no not-found code — see 🚨 Trap 5).
- [api-contracts.md §4](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the endpoint→role/scope grant matrix the later stories gate against (self/reports/all).
- [1-3-carry-the-session-on-every-request.md](1-3-carry-the-session-on-every-request.md) — `get_current_employee`, the `Actor` Protocol, the `TYPE_CHECKING`-breaks-contract-2 finding, the token/error path this story builds on; the G4 open decision.
- [1-2-log-in-and-receive-a-session.md](1-2-log-in-and-receive-a-session.md) — the envelope, `CODE_TO_STATUS`-from-`main.py`, the vocabulary literal guard, the seven import contracts.
- [backend/app/api/v1/dependencies.py](../../backend/app/api/v1/dependencies.py) · [errors.py](../../backend/app/api/v1/errors.py) · [repositories/employee.py](../../backend/app/repositories/employee.py) · [domain/vocabulary.py](../../backend/app/domain/vocabulary.py) · [tests/test_architecture.py](../../backend/tests/test_architecture.py) — current state, read in full during story creation.
- [module-4-erd/erd.md §4.2](../planning-artifacts/module-4-erd/erd.md) — `CHECK (role IN ('EMPLOYEE','MANAGER','ADMIN'))`; roles are code, not data; uuidv7 PKs are non-enumerable, "which keeps `AD-10`'s 404 honest."
- [deferred-work.md](deferred-work.md) — standing deferrals not to fix as drive-bys.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (BMad Dev Story workflow)

### Debug Log References

- `pytest -q` (full backend suite): **92 passed, 0 skipped** (72 baseline + 20 new — 18 in the four new test files, 2 from the auto-parametrized vocabulary/architecture scans picking up the two new `app/` modules). PostgreSQL up, so all integration tests ran.
- `lint-imports` (backend/): **7 kept, 0 broken** — the `api → services → domain` indirection holds; `api/` never imports `domain/`/`repositories/` directly.
- `alembic check` (via `tests/integration/test_model_migration_agreement.py`): passed — **no migration added** (Trap 7), no model changed.
- Guardrail armed-check: `_scoped_getters()` finds exactly `get_by_email` and `get_by_id_with_department` (both EXEMPT); `employee_scope_predicate` and `get_engine` correctly excluded (no `session` param). A future session-taking getter without an `actor` param fails the build.

### Completion Notes List

- **Task 1 (vocabulary):** Added `ACTION_NOT_PERMITTED` (→403) and `RESOURCE_NOT_FOUND` (→404) as constants, appended both to `__all__` (so `test_vocabulary_literals.py` now guards them automatically), and extended the "What arrives, and where" docstring with a Story 1.4 line.
- **Task 2 (main.py):** Added the two `CODE_TO_STATUS.update({...})` entries. `api/v1/errors.py` untouched (Trap 3).
- **Task 3 (services/authorization.py, NEW):** `assert_role(actor, allowed)` raises `ACTION_NOT_PERMITTED` (empty details) or returns; `not_found()` is the single `RESOURCE_NOT_FOUND` raise site (one message constant, empty details → byte-identity, Trap 2). Re-exports `ROLE_ADMIN/ROLE_MANAGER/ROLE_EMPLOYEE` so `api/` reaches the constants indirectly (Trap 1). Pure guard, no I/O, no HTTP.
- **Task 4 (dependencies.py):** `require_role(*allowed)` factory chains `Depends(get_current_employee)`, calls `authz.assert_role`, returns the actor. Imports `app.services.authorization` (allowed `api → services`), never `domain/`. `get_current_employee` unchanged. **Did NOT add `manager_id` to the `Actor` Protocol** — the scope resolver reads only `actor.id`, which is already present; widening would be speculative (Task 4 caveat).
- **Task 5 (test_scoped_getters.py, NEW):** Reflection guardrail over `app/repositories/*.py`; a "getter" = read-verb prefix + a `session` param; each must take `actor` or be in `EXEMPT = {get_by_email, get_by_id_with_department}`. Failure message tells a future dev to scope or justify an exemption.
- **Task 6 (repositories/scoping.py, NEW):** `employee_scope_predicate(scope, actor)` resolves `Scope.SELF`→`employee.id == :actor_id`, `Scope.REPORTS`→`employee.manager_id == :actor_id` (Story 1.7's Manager edge), `Scope.ALL`→`true()`. Grounded concretely in `Employee`; not generalized (Trap 6). Returns a predicate for `select().where()`, never a Python-side filter (AC2).
- **Task 7 (tests):** `tests/domain/test_authorization.py` (role guard raise/return; `not_found` byte-identity proven at the handler seam by rendering two framings and comparing `response.body`); `tests/domain/test_scoping.py` (compiled-SQL assertions, DB-free); `tests/integration/test_role_gate.py` (throwaway ADMIN-gated route on a test-only app: ADMIN passes and reads the actor back, MANAGER/EMPLOYEE get `403 ACTION_NOT_PERMITTED` and never reach the body, absent token is `401 TOKEN_INVALID`). `TEST_ONLY_CODE` left unmapped.
- **Task 8:** No frontend and no new user-facing endpoint in this story (Project Structure Notes) — the interactive click-through gap is declared as Stories 1.1–1.3 did. Proof is the passing suite plus the armed architecture test.
- **Deferrals left untouched:** G4 (deactivated-but-valid token) not addressed — no `is_active` check added to any token path, no test asserting one (Trap 8). No schema/migration change (Trap 7).

### File List

**New (backend):**
- `backend/app/services/authorization.py`
- `backend/app/repositories/scoping.py`
- `backend/tests/test_scoped_getters.py`
- `backend/tests/domain/test_authorization.py`
- `backend/tests/domain/test_scoping.py`
- `backend/tests/integration/test_role_gate.py`

**Modified (backend):**
- `backend/app/domain/vocabulary.py`
- `backend/app/main.py`
- `backend/app/api/v1/dependencies.py`

**Modified (tracking):**
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/1-4-authorization-primitives-the-role-gate-scoped-reads-and-the-404-convention.md`

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-11 | Story created (ultimate context engine analysis: epics §1.4 + cross-story 1.5/1.6/1.7 context, ARCHITECTURE-SPINE AD-1/AD-10/AD-14/AD-21, api-contracts §1/§2/§4, erd §4.2, prior stories 1.2/1.3, and full current-state audit of dependencies/errors/vocabulary/repositories/test_architecture). Status: ready-for-dev. |
| 2026-07-11 | Story 1.4 implemented: two vocabulary codes + status wiring, `services/authorization.py` (role gate raise + byte-identical 404 + role re-export), `require_role` factory, `repositories/scoping.py` scope resolver, and the armed scoped-getter guardrail. 20 new tests; full suite 92 passed / 0 skipped; lint-imports 7 kept / 0 broken; no migration. Status: review. |
