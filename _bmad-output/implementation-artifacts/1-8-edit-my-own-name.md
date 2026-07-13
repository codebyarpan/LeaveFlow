---
baseline_commit: 35a54337a77a5d02fed946f2a3bc5274dac303e2
---

# Story 1.8: Edit My Own Name

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Employee,
I want to correct my own Full Name,
so that I am identified correctly wherever I appear, without being able to grant myself a role or a balance.

This is the **final story of Epic 1**. It adds the one write to the self-service `/me` surface: `PATCH /api/v1/me`, accepting **`full_name` and nothing else**. The read side (`GET /api/v1/me`) already exists from Story 1.3. The entire novelty of this story is a *refusal*: any field other than `full_name` is rejected with `400 FORBIDDEN_FIELD` — the resolution of readiness gap **G5**, and the last remaining unmapped error code in Epic 1.

## Acceptance Criteria

1. **Happy path (FR-17).** Given an authenticated Employee, when they call `PATCH /api/v1/me` with a `full_name`, then the response is `200` and the new name is returned by a subsequent `GET /api/v1/me`.

2. **Forbidden fields refused (FR-17, api-contracts §4.1, G5).** Given an authenticated Employee, when they call `PATCH /api/v1/me` with an `email`, `role`, `department`/`department_id`, `manager`/`manager_id`, `joining_date`, or any Leave Balance quantity, then the response is `400` with code `FORBIDDEN_FIELD`, whose `details` **names the rejected field(s)**, and **nothing is persisted**. `full_name` is the only field the endpoint accepts.

3. **`400`, not `403`, and never a bare `422` (G5, api-contracts §2).** The status is `400` because the actor is permitted both the endpoint and the resource (it is their own profile) and the domain refuses the *content* of the request — not `403` ("may see, may not act"). FastAPI's default `422` **must be suppressed for this endpoint** so every non-2xx body carries the `{ code, message, details }` envelope (NFR-17). A `FORBIDDEN_FIELD` response is the envelope, at status `400`.

4. **Only the caller's own record (FR-17).** Given two Employees, when one calls `PATCH /api/v1/me`, then only the authenticated caller's own record changes, and **no endpoint exists** by which an Employee edits another Employee's profile.

5. **Email is Admin-maintained (FR-04, FR-17).** An Employee whose email must change has it changed by an Admin through `PATCH /api/v1/employees/<id>` — never through `/api/v1/me`. The email address is a credential identity, not a profile field the owner edits.

6. **No self password change (FR-17 Notes, PRD §6).** When the routed API surface is enumerated, no endpoint permits an Employee to change their own password. A password is a credential, not a profile field, so FR-17's editable surface remains Full Name alone. (This is a "no new endpoint" assertion — verified by a routing/enumeration check, not by adding anything.)

7. **React profile screen, read-only except the name (NFR-16).** Given the React application and an authenticated Employee, when they open their profile screen, then `email`, `role`, Department, Manager and joining date are shown **read-only**, and **Full Name alone is editable**. Read-only rendering is a usability measure; the server is the enforcement point (AD-14).

---

## Tasks / Subtasks

- [x] **Task 1 — Declare the `FORBIDDEN_FIELD` vocabulary and wire its status (AC2, AC3)**
  - [x] In [backend/app/domain/vocabulary.py](backend/app/domain/vocabulary.py): add `FORBIDDEN_FIELD = "FORBIDDEN_FIELD"` in a new Story 1.8 comment block, and add it to `__all__`. This is the ONLY place the literal `"FORBIDDEN_FIELD"` may appear (AD-21) — `tests/test_vocabulary_literals.py` fails the build otherwise.
  - [x] In [backend/app/main.py](backend/app/main.py): add `vocabulary.FORBIDDEN_FIELD: 400` to the `CODE_TO_STATUS.update({...})` block, with a one-line comment citing Story 1.8 / G5. Do NOT add the literal or import the vocabulary in `api/v1/errors.py` (contract 2 forbids it).

- [x] **Task 2 — Add the `PATCH /me` service (AC1, AC2, AC3, AC4)**
  - [x] Create [backend/app/services/me.py](backend/app/services/me.py): a `services/` command `rename_me(actor_id: uuid.UUID, submitted: dict[str, object]) -> Employee`. Module docstring must name FR-17 and G5 (SM-6).
  - [x] Compute the forbidden set: `forbidden = sorted(k for k in submitted if k != "full_name")`. If non-empty → `raise DomainError(vocabulary.FORBIDDEN_FIELD, <message>, details={"forbidden_fields": forbidden})`. The check runs **before any write**, so nothing persists (AC2). Declare a module-level `_FORBIDDEN_FIELD_MESSAGE` (mirror `services/employee.py`'s `_..._MESSAGE` constants).
  - [x] Open exactly one `with Session(get_engine(), expire_on_commit=False) as session:` (AD-3). Load the actor's own row by `actor_id` (a plain load — it is the caller's own row, so no `not_found()` scope mechanic is needed; the row is guaranteed to exist because the token resolved to it). Set `full_name`, `session.commit()`, and return the reloaded row with `department` eager-loaded so the route can project `MeResponse` after the block closes. Reuse `employee_repo.load_employee` / `apply_employee_changes` idioms from [backend/app/repositories/employee.py](backend/app/repositories/employee.py).
  - [x] Edge case (not in the ACs, decide gracefully): a body with no `full_name` and no forbidden field (`{}`) is a no-op → return the current row at `200`. A body with `full_name` **and** a forbidden field → `400 FORBIDDEN_FIELD` (the forbidden check wins; nothing persists).

- [x] **Task 3 — Add the `PATCH /me` route (AC1, AC2, AC3)**
  - [x] In [backend/app/api/v1/me.py](backend/app/api/v1/me.py): add `@router.patch("/me", tags=["identity"])` depending on `Actor = Depends(get_current_employee)` — **auth only, no `require_role`** (Role "any", api-contracts §4.1). Return the existing `MeResponse`, status `200`.
  - [x] **Surface unknown fields to the service instead of letting Pydantic emit `422`.** Recommended, codebase-consistent approach: define `class UpdateMeRequest(BaseModel)` with `model_config = ConfigDict(extra="allow")` and `full_name: str | None = None`; pass `request.model_dump(exclude_unset=True)` to `services.me.rename_me`. `extra="allow"` collects unknown keys into the dump so the service sees them; `full_name` optional (not required) keeps Pydantic from raising a `422` for a missing field before the forbidden-field gate runs. (Alternative: accept a raw `dict` body — simpler but loses the OpenAPI schema. Do NOT use `extra="forbid"`: it raises `RequestValidationError` → bare `422` without the envelope, violating AC3, unless you also register a scoped override, which is more code.)
  - [x] Project the returned row into `MeResponse` by hand (same six fields as `read_me`), never `from_attributes` — `api/` may not import the ORM `Employee` (contract 2); the `Actor` Protocol / returned row is read field-by-field.

- [x] **Task 4 — Backend integration tests (AC1, AC2, AC3, AC4, AC5, AC6)**
  - [x] Extend [backend/tests/integration/test_me.py](backend/tests/integration/test_me.py) (reuse its `actor` fixture and `_client`). Update the module docstring to note the `PATCH` side.
  - [x] AC1: `PATCH /me` with `{"full_name": "New Name"}` → `200`; a subsequent `GET /me` returns the new name.
  - [x] AC2/AC3: for EACH forbidden field (`email`, `role`, `department_id`, `manager_id`, `joining_date`, and a balance-shaped key e.g. `allocated`) → `400`, body is exactly `{"code","message","details"}`, `body["code"] == vocabulary.FORBIDDEN_FIELD`, `details["forbidden_fields"]` names the rejected key(s), and a follow-up `GET /me` shows the row **unchanged** (nothing persisted). Reference the code as `vocabulary.FORBIDDEN_FIELD`, never the string literal.
  - [x] AC2: `full_name` + a forbidden field together → `400 FORBIDDEN_FIELD`, name unchanged.
  - [x] AC4: create a second Employee, one caller's `PATCH /me` changes only their own row (assert the other's `full_name` is untouched). Assert no `/me/<id>`-style cross-edit route exists (there is none — this is satisfied by the absence of any such route; a routing assertion over `app.routes` is the clean way to prove AC6 too).
  - [x] AC6: enumerate `app.routes` and assert no path both targets `/me` (or any profile route) and accepts a `password` field — no self password-change endpoint.
  - [x] Follow the fixture's skip-when-DB-absent behaviour (`db_connection`) and per-test uuid suffixing already established in the file.

- [x] **Task 5 — React profile screen (AC7)**
  - [x] In [frontend/src/api/me.ts](frontend/src/api/me.ts): add `useUpdateMe()` — a `useMutation` calling `apiFetch<MeResponse>('/me', { method: 'PATCH', body: JSON.stringify({ full_name }) })`, invalidating `ME_QUERY_KEY` on success (mirror `useUpdateEmployee` in [frontend/src/api/employees.ts](frontend/src/api/employees.ts)).
  - [x] Create `frontend/src/features/profile/ProfilePage.tsx`: read `useMe()`; render `email`, `role`, `department.name`, and joining date as **read-only** text (manager is not on `MeResponse` — display "—" or omit, and note this; `/me` deliberately hides `manager_id`), and `full_name` in an editable input submitting via `useUpdateMe`. Show a success/pending state; on error show `error.message` (the form only ever submits `full_name`, so `FORBIDDEN_FIELD` is unreachable through the UI — no `code` match needed here, keeping it simple).
  - [x] Mount `<ProfilePage />` as a panel in `AppShell` in [frontend/src/App.tsx](frontend/src/App.tsx) (alongside `DepartmentsPage` / `EmployeesPage`). It renders for every authenticated user (no role gate — Role "any").

- [x] **Task 6 — Full verification (all ACs)**
  - [x] Backend: run the meta-tests that guard this change — `tests/test_vocabulary_literals.py`, `tests/test_architecture.py` (import-linter), `tests/test_error_envelope.py`, `tests/integration/test_me.py`. All green.
  - [x] Frontend: typecheck + build (`tsc` / Vite) clean.
  - [x] Confirm no schema/migration change was made (none is needed — `employee.full_name` already exists as a plain mutable `TEXT NOT NULL` column).

---

## Dev Notes

### The one job of this story

`GET /api/v1/me` already exists and is fully tested ([backend/app/api/v1/me.py](backend/app/api/v1/me.py), [backend/tests/integration/test_me.py](backend/tests/integration/test_me.py)). You are **adding a `PATCH`** to the same router and **one refusal path**. Do not touch the read, the `MeResponse` shape, the `DepartmentBrief`, or the `get_current_employee` dependency.

### Existing files you MODIFY (read them first — current state → what changes → what to preserve)

- **[backend/app/api/v1/me.py](backend/app/api/v1/me.py)** — *current:* only `GET /me` (`read_me`) + `MeResponse`/`DepartmentBrief` models. *Change:* add the `PATCH /me` route and an `UpdateMeRequest` model. *Preserve:* `MeResponse`'s exact six fields (`id, full_name, email, role, department, joining_date`) — the `PATCH` returns the SAME shape; never leak `password_hash`, `manager_id`, `is_active`, or a balance. Keep the "no ORM import" discipline (contract 2).
- **[backend/app/domain/vocabulary.py](backend/app/domain/vocabulary.py)** — *current:* codes through Story 1.6, plus `__all__`. *Change:* add `FORBIDDEN_FIELD` + `__all__` entry. *Preserve:* every existing constant and the module's AD-21 discipline (this is the sole home for enumerated strings).
- **[backend/app/main.py](backend/app/main.py)** — *current:* `CODE_TO_STATUS.update({...})` maps codes through Story 1.6. *Change:* add `vocabulary.FORBIDDEN_FIELD: 400`. *Preserve:* the single-handler / single-map design; do not add a second handler.
- **[backend/tests/integration/test_me.py](backend/tests/integration/test_me.py)** — *current:* GET-only tests + the `actor` fixture. *Change:* add PATCH tests; reuse the fixture. *Preserve:* the byte-identical-rejection tests and the AC5 role-from-DB test — do not weaken them.
- **[frontend/src/api/me.ts](frontend/src/api/me.ts)** — add `useUpdateMe`; keep `useMe`, `MeResponse`, `ME_QUERY_KEY` intact.
- **[frontend/src/App.tsx](frontend/src/App.tsx)** — add the `<ProfilePage />` panel; do not disturb the login gate / sign-out flow.

### New files you CREATE

- `backend/app/services/me.py` — the `rename_me` command (there is no `services/me.py` today).
- `backend/tests/integration/test_me.py` — extend (do not create a new file); or a sibling if you prefer, but extending is the established pattern.
- `frontend/src/features/profile/ProfilePage.tsx` — the profile panel.

### The FORBIDDEN_FIELD mechanism — the crux (AC2, AC3, G5)

This codebase's OTHER `PATCH` (`/employees/<id>`) **silently ignores** unknown fields via an allowlist filter — [backend/app/services/employee.py:233](backend/app/services/employee.py#L233) `changes = {k: v for k, v in changes.items() if k in _MUTABLE_FIELDS}`. Its docstring points *directly* at this story ([backend/app/services/employee.py:229-231](backend/app/services/employee.py#L229-L231)):

> "Ignores any field outside `_MUTABLE_FIELDS` (Trap 5: a stray `password` is ignored, not rejected — that `FORBIDDEN_FIELD` behaviour is Story 1.8's `PATCH /me`, a different resource)."

**`PATCH /me` does the OPPOSITE and deliberately so:** it *rejects* any non-`full_name` field with `400 FORBIDDEN_FIELD`. Do not copy the ignore-filter here. The two resources are intentionally asymmetric: the Admin edits many fields and forgives extras; the Employee edits exactly one and refuses the rest.

Because Pydantic in this codebase does **not** reject extras by default, and `extra="forbid"` would emit a bare `422` (breaking the envelope, AC3), the reliable path is: **let unknown keys reach the service, and raise the typed `DomainError` there** (services/ is the only layer allowed to construct a `DomainError` — [Spine "Errors in code"]). See Task 3 for the `extra="allow"` + `exclude_unset` recipe.

The `details` payload must **name the rejected fields** (api-contracts §2, G5). Use `details={"forbidden_fields": ["email", "role", ...]}` (sorted for deterministic tests).

### Error / envelope plumbing (already built — just feed it)

A `DomainError` carries `code`, `message`, `details` and **no status** ([backend/app/domain/errors.py](backend/app/domain/errors.py)). The single handler in [backend/app/api/v1/errors.py:73](backend/app/api/v1/errors.py#L73) maps it to the envelope and looks the status up in `CODE_TO_STATUS`. So your only wiring is: declare the code (Task 1a) + add the `: 400` map entry (Task 1b). Raise `DomainError(vocabulary.FORBIDDEN_FIELD, ...)` from the service and the `400` + envelope happen for free. An **unmapped** code renders `500` (`DEFAULT_ERROR_STATUS`) — so forgetting Task 1b makes the tests fail loudly, which is the intended safety net.

### Auth & scope (AC4)

`PATCH /me` needs **authentication only** — `Depends(get_current_employee)` ([backend/app/api/v1/dependencies.py](backend/app/api/v1/dependencies.py)), the same dependency `GET /me` uses. Role is "any" (api-contracts §4.1). Scope "self" is *intrinsic*: the mutation targets the row keyed by the token's subject, so there is no cross-Employee identifier, no `require_role`, and no 404-scope mechanic. The actor's identity and role come from the DB row (AD-14 / NFR-03), never from token claims — the existing `test_role_is_read_from_the_db_not_the_token` proves this for the read; your write inherits it because it resolves the same actor.

### Data model (no migration)

`EMPLOYEE.full_name` is a plain `TEXT NOT NULL` column ([backend/app/repositories/models.py](backend/app/repositories/models.py), line ~77), with **no UNIQUE and no CHECK** — so there is no DB-level refusal in this story; the only gate is the application-level FORBIDDEN_FIELD check. `UNIQUE (email)` and the role/self-manager CHECKs are never touched (you never write `email`, `role`, or `manager_id` here). No Alembic change, no `erd.md` change, and `tests/integration/test_model_migration_agreement.py` stays green untouched.

### Project structure & layering (AD-1, mechanically enforced)

Imports flow `api → services → {repositories, domain}`; `api/` never imports `repositories/` or `domain/`; `domain/` is pure. `import-linter` contracts in `pyproject.toml` **fail the build** on violation. Placement for this story:
- route → `app/api/v1/me.py`
- command/refusal → `app/services/me.py`
- code constant → `app/domain/vocabulary.py`
- status wiring → `app/main.py` (the composition root, outside all contracts)
Every new module docstring names the FR/DR it implements (SM-6).

### Frontend patterns (AC7)

Mutation via `apiFetch` + `useMutation`, invalidate the query key on success — mirror `useUpdateEmployee` ([frontend/src/api/employees.ts:107-119](frontend/src/api/employees.ts#L107-L119)). `apiFetch` ([frontend/src/api/client.ts](frontend/src/api/client.ts)) sets `Content-Type: application/json`, attaches the Bearer token, and throws a typed `ApiError` on non-2xx. Read-only fields render as plain text; only `full_name` is an `<input>`. NFR-16: this hiding is usability, never the guard — the server enforces (AD-14). Note `MeResponse` has **no `manager_id`** (`/me` hides the reporting line), so the "Manager (read-only)" line has no value to show from `/me` — render a placeholder or omit it, and call this out; do not invent a fetch of the manager here.

### Testing standards

`tests/integration/` runs against real PostgreSQL and skips cleanly when the DB is absent (via `db_connection` in `tests/integration/conftest.py`). Use `TestClient` (synchronous). Per-test uuid-suffixed emails/dept names. Assert refusals as the **exact** envelope (`set(body) == {"code","message","details"}`) and reference codes by symbol (`vocabulary.FORBIDDEN_FIELD`), never by literal — the literal test would fail and, for tests, symbol-reference is the house style.

### Project Structure Notes

- Aligns with the spine source tree: `api/v1/`, `services/`, `domain/`, `tests/integration/`, `frontend/src/api|features`. No new top-level directories.
- One net-new backend module (`services/me.py`) and one net-new frontend feature (`features/profile/`). Both follow existing sibling conventions exactly.
- No variances or conflicts detected. No schema/migration/ERD change.

### References

- [Source: epics.md#Story-1.8] (lines 839-877) — the story, its six BDD ACs, and the `400`-not-`403` rationale note (line 856).
- [Source: epics.md#G5] (lines 378-388) — G5 resolution: `400 FORBIDDEN_FIELD`, `details` names rejected fields, `422` suppressed, "Asserted in Story 1.8."
- [Source: epics.md] line 68 (FR-17), line 111/288 (NFR-16, naming Story 1.8), line 180 (`FORBIDDEN_FIELD` in the 20-code vocabulary), lines 618-621 (`GET /me` from Story 1.3), lines 558-560 (employee table), lines 746-749 (`PATCH /employees/<id>`, the Admin email path).
- [Source: architecture/…/api-contracts.md §1, §2, §4.1] — status semantics; error envelope; `/me` GET+PATCH table and the "accepts exactly one field: `full_name`" rule; `FORBIDDEN_FIELD → 400` row.
- [Source: architecture/…/ARCHITECTURE-SPINE.md] — Stack (pinned versions), Source tree, AD-1 layering, AD-10, AD-14, AD-21, "Errors in code", "Testing".
- [Source: module-4-erd/erd.md §2, §2.1, §4.2, GAP-2] — `employee.full_name` is the sole owner-editable field; `email` is Admin-maintained; no constraint on `full_name`.
- Live code to mirror: [backend/app/api/v1/me.py](backend/app/api/v1/me.py), [backend/app/services/employee.py](backend/app/services/employee.py) (update idiom + the Story-1.8 pointer docstring), [backend/app/domain/errors.py](backend/app/domain/errors.py), [backend/app/api/v1/errors.py](backend/app/api/v1/errors.py), [backend/app/main.py](backend/app/main.py), [frontend/src/api/employees.ts](frontend/src/api/employees.ts), [frontend/src/api/client.ts](frontend/src/api/client.ts), [frontend/src/App.tsx](frontend/src/App.tsx).

### Latest tech / versions (authoritative — do NOT upgrade)

Versions are hard-pinned (`==`, not floors) by the spine and mirrored in `backend/pyproject.toml`; `pyproject.toml` explicitly says "Do not upgrade them." Relevant here: Python 3.13, FastAPI 0.139.0, Pydantic 2.13.4, SQLAlchemy 2.0.51, psycopg 3.3.4, PostgreSQL 18, pytest 9.1.1, httpx 0.28.1; React 19.2.7, Vite 8.1.4, TypeScript 6.0.3, TanStack Query 5.101.2. Pydantic v2 API: use `model_config = ConfigDict(extra="allow")` and `model_dump(exclude_unset=True)` (both are current v2 spellings). No new dependency is needed for this story.

### Previous-story intelligence (Epic 1 conventions that are load-bearing here)

- **Story 1.3** built `GET /me` and the byte-identical `401` rejection discipline you must not disturb.
- **Story 1.4** established `not_found()` (single 404 raise site) and the 403-vs-404 convention — neither is exercised by `PATCH /me` (own-row, content refusal), and G5 is explicit that FORBIDDEN_FIELD is a **400**, a third axis distinct from 403/404.
- **Story 1.5/1.6** established: one `_..._MESSAGE` constant per refusal at module level; each refusal is a **service gate** raising a typed `DomainError` (never a framework side effect); DB constraints are AD-5 backstops, not the surfaced error. Follow all three.
- Git history (`feat(story-1.6)`, `test(story-1.7)`) shows the vocabulary-lands-with-its-raise-site discipline: declare `FORBIDDEN_FIELD` **with** its raise site (this story), which is exactly what you are doing.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Code, Dev Story workflow)

### Debug Log References

- Full backend suite: `python -m pytest -q` → **185 passed** (real PostgreSQL on :5433).
- Guarded meta-tests re-run in isolation: `test_vocabulary_literals.py`, `test_architecture.py`
  (import-linter), `test_error_envelope.py`, `test_me.py`, `test_model_migration_agreement.py`
  → **67 passed**.
- `PATCH /me` integration tests: `tests/integration/test_me.py` → **21 passed** (GET tests
  preserved, 12 new PATCH tests added).
- Frontend: `npm run build` (tsc -b + vite) clean; `npm run lint` (oxlint) clean.
- No `alembic/` or `repositories/models.py` change (`git status --porcelain` empty for both).

**One design note worth flagging for review:** the routing assertions for AC4/AC6 could not
enumerate `/me` via `app.routes` — this FastAPI (0.139.0) nests included routers inside an
`_IncludedRouter` that does not expose a flat `.routes` list. They were written instead over
`app.openapi()`, the stable public enumeration of every registered path and request-body
model. This proves both "`/api/v1/me` is the only `/me`-rooted path (GET+PATCH only)" and
"no `/me` operation declares a `password` field".

### Completion Notes List

Implemented `PATCH /api/v1/me` — the one self-service write of Epic 1 — as a refusal-first
endpoint. All 7 ACs satisfied:

- **AC1** — `PATCH /me {full_name}` → `200`, new name readable via `GET /me` (persisted).
- **AC2/AC3** — any field other than `full_name` → `400 FORBIDDEN_FIELD`, exact
  `{code,message,details}` envelope, `details.forbidden_fields` names the rejected key(s),
  nothing persisted. The `422` FastAPI would emit is suppressed via `extra="allow"` +
  service-raised `DomainError` (never `extra="forbid"`). A `400`, not a `403`/`422`.
- **AC4** — the mutation is keyed by the token's own subject (`actor.id`); a second-Employee
  test proves only the caller's row changes; a routing assertion proves no `/me/<id>`
  cross-edit route exists.
- **AC5** — `email` is refused by `/me` (Admin-maintained via `PATCH /employees/<id>`).
- **AC6** — routing assertion: no `/me` operation accepts a `password` field (no self
  password-change endpoint added — a "no new endpoint" assertion).
- **AC7** — React `ProfilePage`: Full Name editable, email/role/department/manager/joining
  date read-only; server is the enforcement point (AD-14). Manager renders "—" because
  `MeResponse` deliberately hides the reporting line.

Layering held (import-linter green): route → `api/v1/me.py`, refusal → `services/me.py`,
code constant → `domain/vocabulary.py`, status wiring → `main.py`. `FORBIDDEN_FIELD` is the
last unmapped Epic-1 code. No schema/migration change (`full_name` is a plain mutable
`TEXT NOT NULL` column). Refactor: `read_me` and `update_me` now share a `_to_me_response`
projection helper (identical output; keeps the six-field contract in one place).

### File List

**Backend — modified**
- `backend/app/domain/vocabulary.py` — add `FORBIDDEN_FIELD` + `__all__` entry.
- `backend/app/main.py` — map `FORBIDDEN_FIELD → 400` in `CODE_TO_STATUS`.
- `backend/app/api/v1/me.py` — add `UpdateMeRequest`, `PATCH /me` route, `_to_me_response` helper.
- `backend/tests/integration/test_me.py` — add `PATCH` tests + `second_actor` fixture.

**Backend — created**
- `backend/app/services/me.py` — the `rename_me` command and `FORBIDDEN_FIELD` refusal.

**Frontend — modified**
- `frontend/src/api/me.ts` — add `useUpdateMe()`.
- `frontend/src/api/index.ts` — export `useUpdateMe`.
- `frontend/src/App.tsx` — mount `<ProfilePage />` (renders for every authenticated user).

**Frontend — created**
- `frontend/src/features/profile/ProfilePage.tsx` — the profile panel.

**Planning artifacts — modified**
- `_bmad-output/implementation-artifacts/1-8-edit-my-own-name.md` — this story file.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status transitions.

## Change Log

- 2026-07-13 — Story 1.8 implemented: `PATCH /api/v1/me` (accepts `full_name` only, refuses
  every other field with `400 FORBIDDEN_FIELD`, resolving G5) + React profile screen. All 7
  ACs met; 185 backend tests pass, frontend builds and lints clean. Status → review.
- 2026-07-13 — Code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor): all 7 ACs
  confirmed. 1 decision + 4 patches applied, 2 dismissed. Added `INVALID_NAME` (400) domain
  code — `PATCH /me` now validates the `full_name` value (rejects null/non-string/empty,
  trims before write) inside the envelope, closing an unenveloped-500 and a bare-422 gap
  (`full_name` retyped `Any` so bad values reach the service); removed a redundant no-op
  reload; fixed three ProfilePage UX glitches (stale "Saved.", empty-field dead-end,
  refetch clobbering in-progress typing). 193 backend tests pass, frontend build + lint
  clean. Status → done.

## Review Findings

Code review 2026-07-13 (Blind Hunter + Edge Case Hunter + Acceptance Auditor). All 7 ACs
verified satisfied by the Acceptance Auditor. Findings below concern robustness of inputs
the ACs did not enumerate.

- [x] [Review][Patch] Server does not validate the `full_name` **value** itself (only the
  set of keys). Three reachable manifestations, all via a raw HTTP client (the React UI never
  triggers them): (a) `{"full_name": null}` passes `str | None` validation, the forbidden gate
  (only key is `full_name`), and reaches `apply_employee_changes` → `commit`, where the
  `nullable=False` column raises `IntegrityError`; `rename_me` has **no** `try/except`
  (unlike every sibling in `services/employee.py`) and no `IntegrityError`/`RequestValidationError`
  handler is registered, so it escapes as an **unenveloped 500**, contradicting NFR-17/AC3.
  (b) `{"full_name": 123}` (wrong type) → Pydantic `RequestValidationError` → **bare 422**, no
  `{code,message,details}` envelope — the exact hole the `extra="allow"` design defends against,
  reopened via the type axis. (c) `{"full_name": ""}` / `"   "` → empty/whitespace name is
  applied and persisted; the server is stated to be the enforcement point (AD-14) but only the
  React form guards emptiness. Root cause: `UpdateMeRequest.full_name: str | None` +
  `apply_employee_changes` is a bare `setattr` with no content check.
  **RESOLVED 2026-07-13 → DECISION: full server-side validation.** Declare a new domain code
  `INVALID_NAME` (vocabulary.py + `__all__`, AD-21), map it `→ 400` in `main.py`, and have
  `rename_me` reject a `full_name` that is `None`, non-`str`, or empty/whitespace-only with a
  typed `DomainError(INVALID_NAME, …)` — trimming the accepted value server-side before the
  write. Add integration tests for all three manifestations (envelope-exact, nothing persisted).
  [backend/app/api/v1/me.py, backend/app/services/me.py, backend/app/domain/vocabulary.py, backend/app/main.py]

- [x] [Review][Patch] No-op path loads the row twice with no mutation between the two
  `load_employee` calls — an extra query + eager `department` join for a pure read [backend/app/services/me.py:346]
- [x] [Review][Patch] Stale "Saved." confirmation re-appears when the user edits then reverts
  the name back to its saved value (`isSuccess` latches; the banner is gated on value-equality,
  not on the last mutation) — never `updateMe.reset()` [frontend/src/features/profile/ProfilePage.tsx:468]
- [x] [Review][Patch] Cleared-field submit is a silent dead-end: emptying the input leaves the
  Save button enabled (`isUnchanged` false), but `handleSubmit` returns on `trimmed === ''` with
  no message and no mutation [frontend/src/features/profile/ProfilePage.tsx:429]
- [x] [Review][Patch] Re-seed `useEffect([serverName])` overwrites in-progress typing on any
  background refetch (TanStack refetch-on-focus, or a concurrent admin rename) — no dirty guard
  [frontend/src/features/profile/ProfilePage.tsx:398]
