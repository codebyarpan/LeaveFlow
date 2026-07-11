---
baseline_commit: 15743a0250a6918855c4c1de4791ff27d5fac266
---

# Story 1.3: Carry the Session on Every Request

Status: review

Epic: 1 — Secure Access and Organization Administration (Phase 1, correctness core)
Story Key: `1-3-carry-the-session-on-every-request`
Created: 2026-07-11

## Story

As an authenticated Employee,
I want my session verified server-side on every request I make,
so that an absent, expired, or forged token cannot reach protected data.

## Acceptance Criteria

Verbatim from `epics.md#Story 1.3` (lines 610–646). Do not paraphrase these into implementation; satisfy them.

**AC1 — `GET /me` returns the caller's own profile (`FR-17`, `AD-14`)**
**Given** a valid, unexpired token
**When** `GET /api/v1/me` is called with `Authorization: Bearer <token>`
**Then** the response is `200` carrying the caller's own id, full name, email, role, department and joining date
**And** it carries no `password_hash` and no Leave Balance quantity

**AC2 — Absent token is rejected (`FR-02`)**
**Given** a request bearing no `Authorization` header
**When** any protected endpoint is called
**Then** the response is `401` with code `TOKEN_INVALID`

**AC3 — Expired token is rejected (`FR-02`, `NFR-02`)**
**Given** a token whose `exp` claim has passed
**When** any protected endpoint is called
**Then** the response is `401` with code `TOKEN_INVALID`

**AC4 — A tampered token fails signature verification (`FR-02`)**
**Given** a token whose payload was altered to change its subject or its role
**When** any protected endpoint is called
**Then** signature verification fails and the response is `401`
**And** the altered role is never honoured

**AC5 — The actor is resolved from the database, not from the client (`AD-14`, `NFR-03`)**
**Given** any protected endpoint
**When** the `api/` authorization dependency resolves the caller
**Then** it loads the Employee row from the database using the token's subject, and reads the caller's role from that row
**And** it relies on nothing the client sent beyond that subject

> *(What happens when that row is a **since-deactivated** Employee is not fixed by any source, and no criterion is asserted for it here. `AD-14` enumerates exactly three rejection cases — a token absent, expired, or whose signature does not verify — and `AD-22`'s "a deactivated Employee cannot authenticate" governs `FR-01` login, not `FR-02` token presentation. See **G4** in Dev Notes: do not resolve it in this story.)*

**AC6 — The React client carries the token and clears it on rejection**
**Given** the React typed API client
**When** any request is issued
**Then** the token is attached as a Bearer header
**And** a `401` clears the stored session and returns the user to the login screen

## Tasks / Subtasks

- [x] **Task 1: `repositories/employee.py` — add `get_by_id`** (AC: 1, 5)
  - [x] Add `get_by_id(session: Session, employee_id: uuid.UUID) -> Employee | None`. Mirror the existing `get_by_email` shape; use `session.get(Employee, employee_id)` (identity-map lookup by PK) or `select(Employee).where(Employee.id == employee_id)`.
  - [x] AC1 needs the caller's `department` in the response. To avoid a `DetachedInstanceError` after the session closes (see 🚨 Trap 3), **eager-load the department** for the `/me` read: either a dedicated `get_by_id_with_department(...)` using `select(Employee).options(joinedload(Employee.department)).where(Employee.id == employee_id)`, or access `employee.department` inside the open session before returning. Pick one; document it in the docstring.
  - [x] Docstring: cite `FR-17`, `AD-14`. State explicitly that this getter is **exempt from Story 1.4's scoped-getter rule** — like `get_by_email`, it resolves *the actor themself* from the token subject, not another Employee's data, so it precedes scoping. This note stops Story 1.4/1.7 from mistakenly wrapping it.

- [x] **Task 2: `services/auth.py` — resolve a token to its Employee** (AC: 2, 3, 4, 5)
  - [x] Add `resolve_actor(token: str) -> Employee` (name it clearly; Story 1.4 builds its role gate and scope predicates on the actor this returns). This is the **only** legal place for the JWT-error→domain-error translation — see 🚨 Trap 1.
  - [x] Steps, in order: (a) `claims = security.decode_token(token)` wrapped in `try/except jwt.PyJWTError` → on any `PyJWTError` raise `DomainError(code=vocabulary.TOKEN_INVALID, message=<one fixed sentence>, details={})`. Catch `jwt.PyJWTError` (the base), **never** bare `Exception` — Story 1.2 verified `InvalidSignatureError` (tampered) and `ExpiredSignatureError` (expired) both subclass it.
  - [x] (b) Read `sub = claims.get("sub")`; if absent/empty, or not parseable via `uuid.UUID(sub)`, raise the **same** `TOKEN_INVALID` `DomainError`. A malformed `sub` is a rejected token, not a `500`.
  - [x] (c) Load the Employee with `employee_repo.get_by_id(session, subject_uuid)` inside `with Session(get_engine(), expire_on_commit=False) as session:` (copy Story 1.2's idiom exactly — `expire_on_commit=False` keeps the returned row usable after the block; AC1 also needs `department` loaded here, Task 1). If no row, raise the **same** `TOKEN_INVALID` `DomainError`.
  - [x] (d) Return the `Employee`. The caller's role is `employee.role` **from this row** — AC5. Do not trust `claims["role"]` for anything; the token's role claim is never read to make a decision.
  - [x] **One raise site, one message string** for every rejection (absent header, expired, tampered, missing/bad `sub`, no row): all cases produce a byte-identical `TOKEN_INVALID` envelope, disclosing nothing (AD-14). Mirror Story 1.2's single-`raise` discipline.
  - [x] 🚫 **Do NOT check `is_active` here.** See 🚨 Trap 2 / **G4**. This story asserts only what `AD-14` fixes.
  - [x] Legal imports (verified against contract 4): `services/` may import `jwt` to catch `PyJWTError` — contract 4 forbids only `fastapi, starlette, httpx, requests`. It must **not** import `fastapi`.

- [x] **Task 3: `api/v1/dependencies.py` (NEW) — the Bearer dependency** (AC: 1, 2, 5)
  - [x] Create `backend/app/api/v1/dependencies.py`. No `deps`/`dependencies` module exists yet; this is the idiomatic home for the auth dependency. Only `api/` may import `fastapi`.
  - [x] Declare `HTTPBearer(auto_error=False)` — see 🚨 Trap 4. With `auto_error=False`, a missing/malformed `Authorization` header yields `credentials = None` instead of FastAPI's own non-envelope `403`. Do **not** use the default `auto_error=True`.
  - [x] `def get_current_employee(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> Employee:` — if `credentials is None`, call the service with an empty/`""` token (or short-circuit to the same failure) so the **absent-header** case flows through `services.auth.resolve_actor` and raises the one `TOKEN_INVALID` `DomainError` (AC2). Otherwise call `resolve_actor(credentials.credentials)` and return the actor.
  - [x] Imports: `fastapi`, `fastapi.security`, and `app.services.auth` only. It must **not** import `app.repositories`, `app.domain`, or `app.core.security` directly (contract 2 forbids `api/ → repositories`/`domain`; the domain-error translation is the service's job — 🚨 Trap 1). Importing `app.repositories.models.Employee` only for the **type annotation** would trip contract 2 — annotate the return as `Employee` via `TYPE_CHECKING` guard, or return the object without a repositories-typed annotation (e.g. annotate with a `typing.Any`/protocol, or under `if TYPE_CHECKING:`). Prefer the `TYPE_CHECKING` import so the type is visible to editors without a runtime import. **[Resolution: verified empirically that import-linter 2.13 flags even `TYPE_CHECKING` imports here — `exclude_type_checking_imports` is off — so the `TYPE_CHECKING` route broke contract 2. Used the codebase's established structural-`Protocol` idiom instead: an `Actor` Protocol names the actor's shape without importing `Employee`, exactly as `errors.py` names a domain exception with `DomainErrorLike`.]**
  - [x] Naming: `get_current_employee` (the actor/principal). Story 1.4 extends this into role- and scope-gated dependencies; keep this one authentication-only.

- [x] **Task 4: `api/v1/me.py` (NEW) — `GET /me`** (AC: 1)
  - [x] Create `backend/app/api/v1/me.py` with `router = APIRouter()` and `@router.get("/me", tags=["identity"])`. Follow `api/v1/health.py`'s minimal route shape, but declare the auth dependency.
  - [x] Signature: `def read_me(current: Employee = Depends(get_current_employee)) -> MeResponse:`. The dependency does all verification; the route just projects the actor into the response model. Same `TYPE_CHECKING` caution for the `Employee` annotation as Task 3. **[Resolution: annotated `current` with the `Actor` Protocol from `dependencies`, per the Task 3 resolution.]**
  - [x] `MeResponse` (Pydantic response model, declared in this module): fields **exactly** `id`, `full_name`, `email`, `role`, `department`, `joining_date` — the six the AC enumerates, and no more. `department` is a nested `{ id, name }` object (a small `DepartmentBrief` model) sourced from `current.department`. **Never** include `password_hash`, `manager_id`, `is_active`, or any Leave Balance quantity (AC1 explicitly excludes hash and balances; the balance tables do not exist until Epic 2 anyway).
  - [x] The route imports `app.services`… — actually it needs only `get_current_employee` from `.dependencies` and its own Pydantic models. It must not import `repositories`/`domain` (contract 2).
  - [x] Register in `api/v1/router.py`: `from app.api.v1 import auth, health, me` and `api_v1_router.include_router(me.router)`.

- [x] **Task 5: Backend tests** (AC: 1, 2, 3, 4, 5)
  - [x] `tests/integration/test_me.py` (real PostgreSQL, seed-or-create an Employee with a unique email per test, issue a token via `services.auth.issue_token` / `security.create_token`):
    - Valid token → `200`; body carries `id`, `full_name`, `email`, `role`, `department` (`{id, name}`), `joining_date`; assert `"password_hash" not in body` and no balance field (AC1).
    - No `Authorization` header → `401`, `code == vocabulary.TOKEN_INVALID` (AC2). Import the constant; do not hardcode the literal (the `test_vocabulary_literals.py` scan does not cover `tests/`, but byte-identity survives a rename only if built from the constant).
    - Expired token (`create_token` then hand-craft an `exp` in the past via `jwt.encode` with `exp=now-1h` using the real secret) → `401` `TOKEN_INVALID` (AC3).
    - Tampered token (valid token, mutate the payload segment, re-base64 without re-signing) → `401`; the response does not reflect the altered role (AC4).
    - **Role-from-DB proof (AC5):** sign a *validly-signed* token whose `role` claim differs from the DB row (e.g. `create_token(str(emp.id), vocabulary.ROLE_ADMIN)` for an `EMPLOYEE`), call `GET /me`, assert `body["role"] == "EMPLOYEE"` (the DB value), proving nothing beyond `sub` is trusted.
    - Envelope shape exact `{code, message, details}` on a rejection; absent vs expired vs tampered are **byte-identical** (`response.content`) — one raise site guarantees it.
  - [x] `tests/domain/` or a service-level test: a bad-signature token and a well-formed token for a **nonexistent** subject both raise `DomainError(TOKEN_INVALID)` from `resolve_actor` (DB-free where possible with a stub/spy; the nonexistent-subject path needs a repo returning `None`).
  - [x] Do **not** write a test asserting a deactivated Employee's token is rejected — that behaviour is **not** specified (G4). Asserting it would encode a decision this story deliberately leaves open.
  - [x] Run the full suite: the seven import-linter contracts (`tests/test_architecture.py`), `test_vocabulary_literals.py`, `test_migrations_insert_nothing.py`, `test_error_envelope.py`, and `alembic check` (`test_model_migration_agreement.py`) must all stay green. `pytest` is the build (F-14). This story adds **no migration and no new vocabulary** — do not touch `alembic/` or `domain/vocabulary.py`.

- [x] **Task 6: Frontend — attach the Bearer header and clear on 401** (AC: 6)
  - [x] `src/api/client.ts` — in the `new Headers(init?.headers)` merge block (the seam the existing comment flags as where the Authorization header must not be dropped), attach the token: `const token = getToken(); if (token !== null && !headers.has('Authorization')) headers.set('Authorization', \`Bearer ${token}\`)`. Respect `!headers.has(...)` so a caller-supplied header is never clobbered. Import `getToken` from `./session`.
  - [x] On rejection, in the `!response.ok` block, **clear the session only on `TOKEN_INVALID`**: after building `envelope`, `if (response.status === 401 && envelope.code === 'TOKEN_INVALID') { clearToken(); <notify App to sign out> }` before `throw new ApiError(...)`. 🚨 **Gate on the code, not just the 401** — a login failure is `401 AUTH_FAILED` and must not trigger a sign-out/clear (Trap 5). `'TOKEN_INVALID'` here is the wire value from the server envelope; the frontend has no shared constants module, so a string literal is unavoidable — keep it in this one place. **[Kept as a single `TOKEN_INVALID_CODE` const at the top of `client.ts`.]**
  - [x] **Drive the React sign-out (Trap 6):** `clearToken()` alone does not re-render `App` (its `token` state still holds the value). Dispatch a decoupled signal — `window.dispatchEvent(new CustomEvent('leaveflow:session-expired'))` from `client.ts` — and in `App.tsx` add a `useEffect` that subscribes to it and calls `setSessionToken(null)`, then cleans up the listener on unmount. This avoids a circular import between `client.ts` and `App.tsx`. (Alternative: a subscriber callback registered on the `session` module; pick one and keep it centralized.) **[Used the CustomEvent approach; event name centralized as `SESSION_EXPIRED_EVENT` in `session.ts`, imported by both `client.ts` and `App.tsx`.]**
  - [x] `App.tsx` — add the `useEffect` listener described above; preserve the existing "flip state first, then persist" ordering at the `onAuthenticated` callback. Update the stale comment block (lines 7–11 / 44–47) only if it now misdescribes behaviour.
  - [x] Optionally add `src/api/me.ts` with a `useMe()` TanStack query hook (`useQuery({ queryKey: ['me'], queryFn: () => apiFetch<MeResponse>('/me') })`) mirroring `health.ts`, and export from `src/api/index.ts`. Not required by any AC — add only if it makes AC6 demonstrable in the shell; do not build UI beyond what proves the flow. **[Added `me.ts` + a minimal identity line in `AppShell` so a `/me`-backed request demonstrably carries the Bearer header.]**
  - [x] `queryClient.ts` already short-circuits retries on any `< 500` `ApiError` (its comment names the 401 case) — no change needed there.

- [x] **Task 7: Prove it end-to-end** (AC: 1, 2, 6)
  - [x] From a running stack (`docker compose up`; migrate + seed per README's exec-based sequence): `curl` `GET /api/v1/me` with the seed Admin's token → `200` + profile; with no header → `401 TOKEN_INVALID`; with a garbage token → `401 TOKEN_INVALID`. Confirm the `200` body has no `password_hash`. **[Done via the TLS proxy at `https://localhost:8443` (the stack publishes only the proxy's 443, not the api's 8000). Valid → 200 with exactly the six fields and no `password_hash`; absent → 401 `TOKEN_INVALID`; garbage → 401 `TOKEN_INVALID`.]**
  - [x] Rebuild the web image; in a browser (or headless Chrome, as Story 1.2 did): log in, confirm the shell loads and a `/me`-backed request carries the Bearer header (network tab / server log); then simulate an invalid token (edit `localStorage['leaveflow.token']` to garbage and trigger a request, or let one expire) and confirm the app returns to the login screen. If no browser is available, verify the built bundle serves and declare the gap exactly as Stories 1.1/1.2 did. **[No headless browser available in this environment — gap declared as Stories 1.1/1.2 did. Rebuilt the web image; the proxy serves the new bundle (HTTP 200) and the served JS contains the `leaveflow:session-expired` sign-out signal, confirming the new frontend code shipped. `tsc -b` typecheck and `vite build` pass; `oxlint` is clean.]**

## Dev Notes

### What this story is, and what it is not

This story delivers **token verification on every request**: the `api/` Bearer dependency that resolves the caller from a JWT, the `GET /me` endpoint, `TOKEN_INVALID` `401`s, and the frontend attaching the Bearer header and signing out on a `401 TOKEN_INVALID`. Story 1.2 pre-staged almost all of the machinery — `decode_token` is written (unwired), `TOKEN_INVALID` is declared **and already mapped to `401`**, and `clearToken` exists unused. Your job is to wire it, not to invent it.

It does **NOT** deliver: the **role gate**, **scoped reads**, or the **404-for-out-of-scope / 403 convention** — those are Story 1.4's authorization *primitives*, deliberately built after authentication so 1.5/1.6 consume them rather than each inventing a role check (`epics.md#Story 1.4`, line 680). It does not deliver `PATCH /me` (Story 1.8, `400 FORBIDDEN_FIELD`). It adds **no migration**, **no new domain vocabulary**, and **no new dependency** (backend or frontend). The actor `get_current_employee` returns is exactly the `:actor_id` that Story 1.4's `AD-10` scope predicates will consume — name and shape it so 1.4 *extends* it, never *replaces* it.

### 🚨 Six traps, in the order they will bite

**1. The layering squeeze — you cannot catch the JWT error where you decode it, nor where you depend on it.**
`decode_token` lives in `core/security.py`, which **must not import `app.domain`** (contract 6, "core/ is a leaf") — so it cannot raise `DomainError(TOKEN_INVALID)`; it lets `jwt.PyJWTError` propagate (its docstring says so). The FastAPI dependency lives in `api/`, which **must not import `app.domain` or `app.repositories`** (contract 2, `allow_indirect_imports=true`) — so it cannot construct the `DomainError` or load the row either. The **one** legal home for both the `try/except jwt.PyJWTError → raise DomainError(vocabulary.TOKEN_INVALID)` translation and the `get_by_id` lookup is **`services/auth.py`**, which may import `jwt`, `core.security`, `domain`, and `repositories`, but **not `fastapi`** (contract 4). So the flow is strictly: `api/` dependency extracts the raw Bearer string → `services.auth.resolve_actor(token)` decodes, catches, translates, and loads → `DomainError` propagates through `main.py`'s single `add_exception_handler(DomainError, ...)` → the envelope handler maps `TOKEN_INVALID → 401` (already in `CODE_TO_STATUS`). Any shortcut across these layers fails `pytest` (the architecture test).

**2. Do NOT add an `is_active` check to the token path. This is G4, and it is deliberately open.**
It is tempting — you are loading the Employee row anyway, and `AD-22` says "a deactivated Employee cannot authenticate." Resist it. `epics.md`'s Story 1.3 AC5 note (line 641) states plainly that the since-deactivated case "is not fixed by any source, and no criterion is asserted for it here." `AD-14` enumerates **exactly three** rejection cases — absent, expired, signature-invalid — and `AD-22`'s guarantee governs `FR-01` **login** (credential exchange), not `FR-02` **token presentation**. Story 1.2's Dev Notes issued this exact instruction in advance: *"do not add an `is_active` check to the (not-yet-existing) token dependency as a drive-by."* G4 is security-relevant and will be settled **before deployment**, as a one-line change to this dependency if the decision goes that way — but that decision is not yours to make in this story. Assert only what `AD-14` fixes.

**3. `expire_on_commit=False` and the `department` lazy-load — or you get `DetachedInstanceError`.**
AC1 requires `GET /me` to carry the caller's `department`. `department` is a SQLAlchemy relationship. If you return the `Employee` from the service's `with Session(...)` block and *then* touch `employee.department` in the route, the session is closed and SQLAlchemy raises `DetachedInstanceError` even with `expire_on_commit=False` (that flag preserves *already-loaded* attributes; it does not load a lazy relationship after close). Fix: **eager-load** `department` in the `/me` query (`joinedload(Employee.department)`) or read `employee.department` while the session is still open (Task 1). Copy Story 1.2's `Session(get_engine(), expire_on_commit=False)` idiom for everything else.

**4. `HTTPBearer(auto_error=False)` — the default would leak a non-envelope `403`.**
FastAPI's `HTTPBearer` with the default `auto_error=True` raises its *own* `HTTPException(403, "Not authenticated")` on a missing header — a bare body, wrong status, bypassing the `{code, message, details}` envelope (`NFR-17`) and the `TOKEN_INVALID`/`401` contract. Construct it `HTTPBearer(auto_error=False)`, receive `credentials: HTTPAuthorizationCredentials | None`, and when it is `None` route the **absent-header** case through the same `resolve_actor` failure so it becomes a `401 TOKEN_INVALID` envelope like every other rejection (AC2).

**5. Clear the session on `TOKEN_INVALID`, never on any `401`.**
The login endpoint returns `401 AUTH_FAILED` on bad credentials. If the frontend clears the session / redirects on *any* `401`, a wrong-password attempt would behave like a session expiry (and there is no session to clear at login anyway). Gate the clear on `response.status === 401 && envelope.code === 'TOKEN_INVALID'`.

**6. `clearToken()` does not re-render React — you must drive `App`'s state.**
`App.tsx` holds `token` in `useState` (line 61); clearing `localStorage` inside `apiFetch` does not touch that state, so the shell keeps rendering. Dispatch a `window` `CustomEvent('leaveflow:session-expired')` from `client.ts` and have `App` subscribe via `useEffect` and call `setSessionToken(null)`. This keeps `client.ts` free of an import on `App` (no cycle) and is trivially testable. Preserve the existing "flip state first, then persist" ordering pattern in `onAuthenticated`.

### Architecture compliance

- **`AD-14`** governs this story end to end: Bearer JWT with hours-lifetime `exp`; the check happens **in an `api/` dependency against the database, independently of anything the client sent beyond the token's subject**; absent/expired/bad-signature are the three (and only three) rejection cases; failure discloses nothing (one message, empty `details`, byte-identical across rejection reasons). `PyJWT` (not `python-jose`).
- **`AD-10`** binds `FR-17`: `/me`'s scope is **self** (api-contracts §4.1, Role "any", Scope "self"). The read is keyed by the token's own subject, so there is no cross-Employee identifier to guess and the 404-scope-miss mechanic does not bite here — the `401` gate does. The full scoped-read/404 convention is **Story 1.4**, not this story.
- **`AD-21`**: `TOKEN_INVALID` is already declared once in `domain/vocabulary.py` (Story 1.2, line 43) and is in `__all__`. Reference `vocabulary.TOKEN_INVALID`; never type the literal in `app/` or `seed/` (the standing `test_vocabulary_literals.py` fails the build). Tests should import the constant too.
- **`AD-1` / the seven contracts**: the api → service → domain/repositories chain (Trap 1) is exactly the layering the contracts encode. `allow_indirect_imports=true` on contract 2 (added in Story 1.2) permits the route→service→domain call chain but still forbids a *direct* `api/ → domain`/`repositories` import. If you find yourself importing `DomainError`, `vocabulary`, or a repository from `api/`, you have taken a wrong turn — move that logic into the service.
- **`AD-3` shape**: one transaction/connection per command, opened in `services/`. `resolve_actor` is a single read; copy the `with Session(get_engine(), expire_on_commit=False)` idiom Story 1.2 established.
- **Naming**: paths kebab-case under `/api/v1` (`/me`); models `PascalCase` (`MeResponse`, `DepartmentBrief`); dependency `get_current_employee`; React hooks `useThing`.

### Previous story intelligence — Story 1.2 (read this; it is first-hand and load-bearing)

Story 1.2 (`review` status; commit `15743a0` is your baseline) deliberately built the ramp for this story. Inherit exactly this state:

- **`core/security.py::decode_token(token: str) -> dict`** exists and is verified. It passes `algorithms=[settings.jwt_algorithm]` (mandatory in PyJWT 2.13), verifies `exp` by default, and lets `jwt.PyJWTError` subclasses propagate uncaught — `InvalidSignatureError` (tampered) and `ExpiredSignatureError` (expired). **Catch `jwt.PyJWTError`, not bare `Exception`.** Do not modify this function.
- **`TOKEN_INVALID` is already mapped to `401`** in `main.py` (`CODE_TO_STATUS.update({vocabulary.AUTH_FAILED: 401, vocabulary.TOKEN_INVALID: 401})`). **Do not touch `main.py`** — the status and the `DomainError` handler binding already cover your new raise site. `errors.py` needs no change either (the handler is registered against the `DomainError` base class).
- **`services/auth.py`** shows the idiom to copy: `with Session(get_engine(), expire_on_commit=False) as session:` then a repo call. Its imports (`from app.core import security`, `from app.domain import vocabulary`, `from app.domain.errors import DomainError`, `from app.repositories import employee as employee_repo`, `from app.repositories.engine import get_engine`, `from app.repositories.models import Employee`) are the palette for `resolve_actor`.
- **`repositories/employee.py`** has only `get_by_email(session, email)`. `get_by_id` does **not** exist — create it (Task 1). The subject arrives as a **string** (`str(employee.id)` was signed in); parse to `uuid.UUID` and treat a parse failure as `TOKEN_INVALID` (not a `500`).
- **`api/v1/auth.py`** is the route pattern: `router = APIRouter()`, a route decorated with `tags=[...]`, importing only `app.services`. **`health.py`** shows the minimal anonymous-route shape; `/me` follows it but *declares* the auth dependency.
- **`repositories/models.py::Employee`** fields: `id`, `department_id`, `manager_id` (nullable), `email` (unique), `full_name`, `role`, `joining_date` (`date`), `is_active`, `password_hash`, plus `department` and `manager` relationships. `MeResponse` exposes only `id, full_name, email, role, department{id,name}, joining_date`.
- **Frontend `apiFetch<T>(path: \`/${string}\`, init?): Promise<T>`** (client.ts:90) merges headers via `new Headers(init?.headers)` (client.ts:94) — the exact seam for the Bearer attach; on `!response.ok` it decodes the envelope and throws `ApiError(status, envelope)` (client.ts:107–131). `session.ts` exposes `getToken/setToken/clearToken` (all guarded against storage throws; `clearToken` currently unused, "Story 1.3 calls this on a 401"). `App.tsx` gates login/shell on `token` state (line 61). `queryClient.ts` already declines to retry a `< 500` `ApiError`.
- **The `docker compose` gotcha**: this environment has the standalone `docker-compose` binary, not the `docker compose` plugin the README documents; commands are otherwise identical. Settings reject placeholder/`CHANGE_ME` `.env` values — integration tests skip loudly on a bad `.env`.
- **Two open defers** (`deferred-work.md`): `configure_logging()` import side effect and the `seed` package name. Neither is this story's work — do not fix as drive-bys.

### Verified library / framework facts (checked against installed pins in `pyproject.toml`)

- `PyJWT 2.13.0`: `jwt.decode(token, key, algorithms=[...])` verifies the signature and `exp` by default. Missing `algorithms=` → `DecodeError` unconditionally (already handled in `decode_token`). Tampered → `InvalidSignatureError`; expired → `ExpiredSignatureError`; both subclass `jwt.PyJWTError`. To *forge a validly-signed* token for a test (AC5 role-from-DB proof, or a past-`exp` token for AC3), use `jwt.encode(...)` with `settings.jwt_secret_key` and `HS256`.
- `FastAPI 0.139.0`: `from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials`. `HTTPBearer(auto_error=False)` returns `None` on a missing/malformed header instead of raising its own `403` (Trap 4). `credentials.credentials` is the raw token string.
- The `TestClient` is synchronous (no `pytest-asyncio`; not installed). Starlette's `httpx`-deprecation warning stands from Story 1.1 — leave it.
- Frontend pins (no change): React 19, TanStack Query 5.101.2, Vite 8. No router exists and this story does not add one — the token-presence switch in `App.tsx` remains the gate.

### Testing standards

`tests/domain/` runs DB-free; `tests/integration/` against real PostgreSQL (fixtures skip loudly on a missing/placeholder `.env`). Every module docstring names its FR/DR/AD (`SM-6`). This story's substantive tests are the ones the ACs name: the `/me` happy path with the exclusion assertions, the three rejection cases (`TOKEN_INVALID`, byte-identical), the tampered-token case, and the **role-from-DB** proof (AC5) — the single most important test, since it proves the dependency trusts nothing beyond `sub`. `NFR-15`: do not chase coverage on plumbing. **Do not** write a deactivated-token test (G4, Trap 2).

### Project Structure Notes

- **New files**: `backend/app/api/v1/dependencies.py` (the `HTTPBearer` scheme + `get_current_employee`), `backend/app/api/v1/me.py` (`GET /me` + `MeResponse`/`DepartmentBrief`), `backend/tests/integration/test_me.py`, and optionally a service-level rejection test under `tests/domain/`. Optional frontend `frontend/src/api/me.ts`.
- **Modified**: `backend/app/repositories/employee.py` (`get_by_id`), `backend/app/services/auth.py` (`resolve_actor`), `backend/app/api/v1/router.py` (register `me.router`), `frontend/src/api/client.ts` (Bearer attach + clear-on-`TOKEN_INVALID`), `frontend/src/App.tsx` (session-expired `useEffect`), and — if the optional hook is added — `frontend/src/api/index.ts`.
- **Untouched by design**: `main.py`, `api/v1/errors.py`, `core/security.py`, `domain/vocabulary.py`, `alembic/` (no migration), `settings.py`. Touching any of these is a signal you have gone off-plan (except an unavoidable one-line `router.py` import).

### References

- [epics.md#Story 1.3](../planning-artifacts/epics.md) — story statement and all seven criteria, verbatim; the since-deactivated note (line 641)
- [epics.md#Story 1.4](../planning-artifacts/epics.md) — the boundary: role gate, scoped reads, 404 convention are NOT this story (line 680)
- [epics.md#G4](../planning-artifacts/epics.md) — the deliberately-open deactivated-token decision; settle before deployment, not here
- [ARCHITECTURE-SPINE.md#AD-14](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — Bearer JWT, three rejection cases, DB check independent of the client, PyJWT
- [ARCHITECTURE-SPINE.md#AD-10, #AD-1, #AD-21, #AD-22](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — scope predicate, layering, vocabulary, deactivation
- [api-contracts.md §1, §2, §4.1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — Bearer convention, `TOKEN_INVALID`/`401` + envelope, `GET /me` (any, self, FR-17)
- [1-2-log-in-and-receive-a-session.md](1-2-log-in-and-receive-a-session.md) — the ramp: `decode_token`, `TOKEN_INVALID` mapping, the service idiom, `apiFetch`/`session.ts`/`App.tsx`, the "no `is_active` drive-by" instruction
- [pyproject.toml](../../backend/pyproject.toml) — the seven import-linter contracts and the version pins
- [deferred-work.md](deferred-work.md) — open defers; not this story's work

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — BMad dev-story workflow

### Debug Log References

- `pytest` (backend): 60 passed at baseline → **72 passed** after this story (10 new test functions + 2 auto-parametrized vocabulary-literal scans over the two new `app/` files). Integration suite ran against real PostgreSQL (docker stack up).
- `lint-imports` (import-linter 2.13): **7 kept, 0 broken** — the api → service → domain/repositories layering (Trap 1) holds, including the `Actor`-Protocol resolution that keeps `api/` free of a `repositories` import.
- Frontend: `oxlint` clean; `tsc -b` typecheck passes; `vite build` succeeds (dist emitted).
- Live-stack `curl` via TLS proxy `https://localhost:8443`: `GET /me` valid → 200 (six fields, no `password_hash`); absent → 401 `TOKEN_INVALID`; garbage → 401 `TOKEN_INVALID`.

### Completion Notes List

- **Trap 1 (layering squeeze)** resolved as specified: the JWT-error→`DomainError(TOKEN_INVALID)` translation and the DB load both live in `services.auth.resolve_actor`. The `api/` dependency only lifts the raw Bearer string off the request. `core/security.decode_token` was left untouched and still lets `jwt.PyJWTError` propagate.
- **Type-annotation resolution (Task 3/4):** the story's preferred `TYPE_CHECKING` import of `Employee` into `api/` was **verified empirically to break contract 2** — import-linter 2.13 analyses the AST and flags `TYPE_CHECKING` imports (`exclude_type_checking_imports` defaults off). Adopted the codebase's own established idiom instead: a structural `Actor` `Protocol` in `dependencies.py` names the actor's shape without importing the ORM model, exactly as `api/v1/errors.py` uses `DomainErrorLike`. This keeps full editor typing with zero forbidden imports.
- **Trap 2 (G4):** no `is_active` check was added to the token path — the three AD-14 rejection cases only. The deactivated-token decision stays open, and no test asserts it.
- **Trap 3:** `department` is eager-loaded via `joinedload` in `get_by_id_with_department`, so `/me`'s projection reads it after the session closes without `DetachedInstanceError`.
- **Trap 4:** `HTTPBearer(auto_error=False)`; the absent-header case (`credentials is None`) is routed through `resolve_actor("")` so it yields the same `401 TOKEN_INVALID` envelope as every other rejection.
- **Byte-identity (AD-14):** every rejection in `resolve_actor` leaves through one nested `reject()` → one `raise` → one message string. An integration test asserts absent/expired/tampered/garbage responses are byte-identical.
- **Trap 5 (frontend):** the session clear is gated on `status === 401 && code === TOKEN_INVALID`, never on any 401 — a `401 AUTH_FAILED` login failure does not sign anyone out.
- **Trap 6 (frontend):** sign-out is driven by a decoupled `window` `CustomEvent` (`SESSION_EXPIRED_EVENT`, centralized in `session.ts`); `App`'s `useEffect` flips `token` state to `null`. No `client.ts → App` import cycle.
- Added the optional `useMe()` hook and a one-line identity display in `AppShell` so AC6's Bearer-carrying request is demonstrable; no UI beyond that.
- **Constraints honoured:** no migration, no new `domain/vocabulary.py` entry, no new dependency; `main.py`, `errors.py`, `core/security.py`, `vocabulary.py`, `alembic/`, `settings.py` untouched. Only `router.py` got the one-line `me` import/registration.
- **Declared gap:** no headless browser in this environment, so the interactive click-through (log in, inspect network tab, expire the token) was not run. Mitigated by the full HTTP-layer proof (integration tests + live curl), a passing typecheck/build, and confirming the served bundle ships the sign-out signal — the same gap-declaration posture Stories 1.1/1.2 took.

### File List

**Backend — modified**
- `backend/app/repositories/employee.py` — added `get_by_id_with_department` (PK lookup, `joinedload(department)`; exempt from scoped-getter rule).
- `backend/app/services/auth.py` — added `resolve_actor(token)` (decode→translate→load, one `reject()` raise site) and `_TOKEN_INVALID_MESSAGE`.
- `backend/app/api/v1/router.py` — register `me.router`.

**Backend — new**
- `backend/app/api/v1/dependencies.py` — `HTTPBearer(auto_error=False)`, `get_current_employee`, and the `Actor`/`DepartmentShape` Protocols.
- `backend/app/api/v1/me.py` — `GET /me`, `MeResponse`, `DepartmentBrief`.
- `backend/tests/integration/test_me.py` — AC1–AC5 end-to-end against real PostgreSQL.
- `backend/tests/domain/test_resolve_actor_rejections.py` — DB-free service-level rejection tests.

**Frontend — modified**
- `frontend/src/api/session.ts` — added `SESSION_EXPIRED_EVENT` constant.
- `frontend/src/api/client.ts` — attach Bearer header; clear session + dispatch event on `401 TOKEN_INVALID`.
- `frontend/src/api/index.ts` — export `useMe`/`MeResponse`/`DepartmentBrief`/`SESSION_EXPIRED_EVENT`.
- `frontend/src/App.tsx` — `useEffect` session-expired listener; `useMe`-backed identity line in `AppShell`.

**Frontend — new**
- `frontend/src/api/me.ts` — `useMe()` TanStack hook + `MeResponse`/`DepartmentBrief` types.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-11 | Story created (ultimate context engine analysis: epics.md Story 1.3/1.4/G4, ARCHITECTURE-SPINE AD-14/AD-10/AD-1/AD-21/AD-22, api-contracts §1/§2/§4.1, Story 1.2 + its review, and the live backend/frontend code verified against installed pins). Status: ready-for-dev. |
| 2026-07-11 | Implemented all 7 tasks: `resolve_actor` + Bearer dependency + `GET /me`, `get_by_id_with_department`, frontend Bearer-attach and sign-out-on-`TOKEN_INVALID`. 72 backend tests pass; 7 import-linter contracts kept; frontend typecheck/build/lint clean; live-stack curl verified. Task 3/4 type annotation uses an `Actor` Protocol (not `TYPE_CHECKING` import) because import-linter flags TYPE_CHECKING imports. Status: review. |
