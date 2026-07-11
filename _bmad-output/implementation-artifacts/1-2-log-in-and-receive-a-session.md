---
baseline_commit: d317d765eee644632ff0139a29169ad08a3191d3
---

# Story 1.2: Log In and Receive a Session

Status: review

Epic: 1 — Secure Access and Organization Administration (Phase 1, correctness core)
Story Key: `1-2-log-in-and-receive-a-session`
Created: 2026-07-10

## Story

As an Employee,
I want to exchange my email address and password for a session token,
so that I can use LeaveFlow without a failed attempt revealing whether anyone's account exists.

## Acceptance Criteria

**AC1 — The first two domain tables, and only those (`epics.md#Story 1.2`, ERD §2/§4)**
**Given** a database migrated by this story
**When** the schema is inspected
**Then** `department` and `employee` exist and no other domain table does
**And** `employee` carries `UNIQUE (email)`, `CHECK (role IN ('EMPLOYEE','MANAGER','ADMIN'))`, `CHECK (id <> manager_id)`, a NOT NULL `department_id` foreign key, a **nullable** self-referencing `manager_id`, a `joining_date` of type `DATE`, `is_active`, and `password_hash`, with indexes on `manager_id` and `department_id`
**And** `CHECK (id <> manager_id)` is a **backstop** for `AD-23`, never the gate: the transitive cycle refusal lives in the employee service (Story 1.6), and a `CHECK` violation reaching a client is a defect and a `500` (`AD-5`, `AD-23`)

> `employee.department_id` is NOT NULL — every Employee belongs to exactly one Department (PRD §3) — so `department` is created here rather than in Story 1.5, which adds its endpoints.

**AC2 — Seeded Admin (`G1`/`GAP-5`, `AD-11`)**
**Given** the seed command has run
**When** the database is inspected
**Then** exactly one Department and exactly one Admin Employee exist, both taken from the environment
**And** that Admin has `manager_id` NULL and `is_active` true

**AC3 — Login succeeds (`FR-01`, `NFR-02`)**
**Given** an active Employee and their correct password
**When** `POST /api/v1/auth/login` is called
**Then** the response is `200` carrying a JSON Web Token whose claims identify the subject and the role
**And** the token carries an `exp` claim whose lifetime is measured in hours, not days

**AC4 — Failure discloses nothing (`FR-01`)**
**Given** an email address belonging to no Employee
**When** `POST /api/v1/auth/login` is called
**Then** the response is `401` with code `AUTH_FAILED`
**And** the body is byte-identical, and the status code equal, to the response for a known email with a wrong password

**AC5 — The lookup never short-circuits (ERD §4.2, GAP-1)**
**Given** an email address belonging to no Employee
**When** authentication is attempted
**Then** the login path executes exactly one password hash comparison, against a constant fallback hash, before returning `AUTH_FAILED`
**And** a test asserting the verification function was invoked passes identically on the unknown-email path and the wrong-password path, so the lookup never short-circuits on a missing row

> This is a structural assertion, not a wall-clock timing assertion — a timing test would be flaky rather than probative.

**AC6 — Password storage (`NFR-01`, `AD-14`)**
**Given** any Employee row
**When** `password_hash` is inspected
**Then** it is a salted hash produced by bcrypt or Argon2 through `pwdlib`
**And** no stored representation permits recovery of the password, and neither `passlib` nor `python-jose` appears in the dependency set

**AC7 — A deactivated Employee cannot authenticate (`FR-04`, `AD-22`)**
**Given** an Employee whose `is_active` is false
**When** they present their correct credentials
**Then** authentication is refused with the same `AUTH_FAILED` response

**AC8 — The envelope, exercised for real (`NFR-17`, api-contracts §2)**
**Given** the `401` response produced by any failed login
**When** its body is inspected
**Then** it carries exactly the envelope `{ code, message, details }` with `code` equal to `AUTH_FAILED`
**And** `POST /api/v1/auth/login` is the first endpoint capable of a non-2xx response, so the envelope is exercised here rather than in Story 1.1

**AC9 — The vocabulary and its standing guard (`AD-21`)**
**Given** the enumerated values this story introduces — the role values `EMPLOYEE`, `MANAGER`, `ADMIN`, and the error codes `AUTH_FAILED` and `TOKEN_INVALID`
**When** the codebase is checked
**Then** each is `UPPER_SNAKE_CASE` and declared exactly once as a constant in `domain/`
**And** a standing check fails the build if any such value appears as a literal outside that module, for these values and for every enumerated value a later story adds

**AC10 — The login screen (`FR-01` frontend)**
**Given** the React application and an unauthenticated visitor
**When** they open the app
**Then** a login screen is presented; a successful login stores the token and lands them on the application shell
**And** a failed login shows a message that does not disclose whether the account exists

## Tasks / Subtasks

- [x] **Task 1: Migration 0002 — `department` and `employee`** (AC: 1)
  - [x] New revision in `backend/alembic/versions/`, `down_revision = "0001_baseline"` (the exact revision id in `0001_baseline_baseline_no_domain_table_ac6_ad_11.py`).
  - [x] `department`: `id UUID PK DEFAULT uuidv7()`, `name TEXT NOT NULL`. No `UNIQUE(name)` — the ERD does not declare one; do not invent schema.
  - [x] `employee`: `id UUID PK DEFAULT uuidv7()`, `department_id UUID NOT NULL FK → department`, `manager_id UUID NULL FK → employee`, `email TEXT NOT NULL UNIQUE`, `full_name TEXT NOT NULL`, `role TEXT NOT NULL CHECK (role IN ('EMPLOYEE','MANAGER','ADMIN'))`, `joining_date DATE NOT NULL`, `is_active BOOLEAN NOT NULL`, `password_hash TEXT NOT NULL`, `CHECK (id <> manager_id)`.
  - [x] Indexes: `employee(manager_id)`, `employee(department_id)` (`NFR-12`; ERD §4.4).
  - [x] `uuidv7()` is a PostgreSQL 18 **native built-in**: `server_default=sa.text("uuidv7()")`, no extension, no `CREATE EXTENSION`.
  - [x] The migration creates schema and inserts **nothing**. `tests/test_migrations_insert_nothing.py` parametrizes over every migration automatically and will enforce this — including its hardened checks for bare `insert()` calls and quoted/schema-qualified DML (post-review state).

- [x] **Task 2: SQLAlchemy models** (AC: 1)
  - [x] `repositories/models.py` (or one module per entity): `Department`, `Employee` as SQLAlchemy 2.0 `Mapped`/`mapped_column` models on the existing `repositories/base.py` `Base`.
  - [x] Import the models module from `alembic/env.py` (or from something `env.py` already imports) — `env.py`'s own comment warns that `--autogenerate` silently drops tables it cannot see. Verify `alembic check`/autogenerate emits an **empty** diff after the hand-written migration matches the models.
  - [x] Model docstrings cite `FR-01`, `FR-04`, `AD-10`, `AD-14`, `AD-23` (`SM-6`).

- [x] **Task 3: Vocabulary and the standing literal check** (AC: 9)
  - [x] `domain/vocabulary.py`: `ROLE_EMPLOYEE = "EMPLOYEE"`, `ROLE_MANAGER = "MANAGER"`, `ROLE_ADMIN = "ADMIN"`, `AUTH_FAILED = "AUTH_FAILED"`, `TOKEN_INVALID = "TOKEN_INVALID"`, exported via `__all__`. `TOKEN_INVALID` is declared now (it is this story's vocabulary per the epic) even though Story 1.3 raises it first.
  - [x] `backend/tests/test_vocabulary_literals.py` — the standing check: read every string constant exported by `domain/vocabulary.py`, then AST-walk every `.py` under `app/` and `seed/` **except** `domain/vocabulary.py`, and fail if any exported value appears as a string literal (skip docstrings, as `test_migrations_insert_nothing.py` already does — reuse its `visit_Expr` docstring-skip pattern). It must pick up future constants automatically — iterate the module's `__all__`, never a hardcoded list.
  - [x] **Scope decision, made here so no later story relitigates it:** `alembic/versions/` is exempt — the `CHECK (role IN (...))` DDL is the *database's* copy of the vocabulary, prescribed verbatim by ERD §4.2, and a migration is immutable once applied. `tests/` are not scanned by the check, but tests SHOULD import the constants (`vocabulary.AUTH_FAILED`, not `"AUTH_FAILED"`) — byte-identity assertions built from constants survive a rename.
  - [x] Guard-the-guard: assert the check actually fires on a planted literal (in-memory source string, same pattern as `test_the_guard_detects_a_real_bulk_insert`).

- [x] **Task 4: `core/security.py` — hashing and JWT mechanics, and nothing else** (AC: 3, 6)
  - [x] `PasswordHash((BcryptHasher(),))` constructed **explicitly** — see the 🚨 `recommended()` trap below. Expose `hash_password(str) -> str` and `verify_password(password: str, hash: str) -> bool`. Argument order is `verify(password, hash)` — password first.
  - [x] Pre-check the 72-byte bcrypt limit (`len(password.encode("utf-8")) > 72`) in both hash and verify paths — bcrypt 5.0.0 **raises `ValueError`**, it no longer truncates. On the login path an over-long password is an ordinary `AUTH_FAILED`; at seed time it is a clear startup error naming `SEED_ADMIN_PASSWORD`.
  - [x] JWT: `create_token(subject: str, role: str) -> str` using `jwt.encode({"sub": subject, "role": role, "exp": now_utc + timedelta(hours=settings.jwt_expire_hours)}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)`. `sub` must be a **string** (`str(employee.id)`) — PyJWT validates the claim type. Decode (Story 1.3 consumes it, write it now beside encode): `jwt.decode(token, key, algorithms=[settings.jwt_algorithm])` — `algorithms=` is **mandatory** in PyJWT 2.13; omitting it raises `DecodeError` unconditionally.
  - [x] A module-level `FALLBACK_HASH = hash_password("<fixed arbitrary string>")` computed once at import, for AC5's constant comparison.
  - [x] `core/security.py` imports `core/settings.py` and third-party libraries **only**. It must NOT import `app.domain` — post-review contract 6 (`core/ is a leaf`) fails the build if it does. It raises no domain error; it returns booleans and lets PyJWT exceptions propagate to its caller in `services/`.

- [x] **Task 5: The auth service and the login endpoint** (AC: 3, 4, 5, 7, 8)
  - [x] `repositories/employee.py`: `get_by_email(connectionish, email) -> Employee | None`. This getter is exempt from Story 1.4's scoped-getter rule — authentication has no actor yet; note that in its docstring.
  - [x] `services/auth.py`: `authenticate(email, password) -> Employee` — loads by email; if no row, verify against `core.security.FALLBACK_HASH` and **discard the result** (the fallback's preimage is in the source, so a `True` from it must never matter); if row exists, verify against `password_hash`; on any failure — unknown email, wrong password, `is_active` false — raise `DomainError(code=AUTH_FAILED, message=<one fixed sentence>, details={})`. One raise site, one message string: byte-identity by construction, not by discipline. `is_active` is checked **after** the hash comparison so the deactivated path is not distinguishable by timing either.
  - [x] `services/auth.py`: `issue_token(employee) -> str` via `core.security.create_token(str(employee.id), employee.role)`.
  - [x] `api/v1/auth.py`: `POST /auth/login` route, anonymous, Pydantic request `{email, password}`, response `{access_token, token_type: "bearer"}`. The route calls the service and returns; it imports neither `repositories/` nor `domain/` (contract 2 fails the build otherwise). Register in `api/v1/router.py`.
  - [x] `main.py`: populate the status map beside the handler binding, exactly as the `CODE_TO_STATUS` comment prescribes: `CODE_TO_STATUS.update({vocabulary.AUTH_FAILED: 401, vocabulary.TOKEN_INVALID: 401})`. `main.py` sits outside every contract precisely so it can perform this wiring — do NOT put literals or a vocabulary import in `api/v1/errors.py`; either fails the build.
  - [x] The service opens one transaction/connection per command (`AD-3` shape) — a read-only lookup here, but establish the `services/` transaction idiom the next 25 stories copy.

- [x] **Task 6: Seed the Department and the Admin** (AC: 2)
  - [x] Extend `backend/seed/__main__.py`: after the existing `alembic_version` ordering guard, insert the Department named `SEED_DEPARTMENT_NAME` and the Admin (`SEED_ADMIN_EMAIL`, `SEED_ADMIN_FULL_NAME`, hash of `SEED_ADMIN_PASSWORD`, `role=ROLE_ADMIN`, `manager_id=NULL`, `is_active=true`, `joining_date=date.today()`, `department_id=<the seed department>`).
  - [x] Idempotent: Admin via `INSERT ... ON CONFLICT (email) DO NOTHING`; Department via select-by-name-then-insert (no unique constraint exists on `name`; the seed is single-process, so this does not race). Running the seed twice changes nothing — assert that in a test.
  - [x] The seed imports `domain/vocabulary.py` for `ROLE_ADMIN` and `core/security.py` for the hash — both legal (seed/ sits outside the layer contracts). It must NOT hardcode `"ADMIN"` — the literal check scans `seed/`.
  - [x] Settings already validate `SEED_ADMIN_PASSWORD`/`JWT_SECRET_KEY` against empty and `CHANGE_ME*` values (post-review) — the seed can trust them non-placeholder, but must still handle the >72-byte case with a legible error.

- [x] **Task 7: Frontend — login screen and session storage** (AC: 10)
  - [x] **No new dependency.** There is no router in `package.json` and this story does not add one — the spine defers that choice. `App.tsx` renders conditionally: token present → the existing shell; absent → `LoginPage`.
  - [x] `src/api/auth.ts`: `login(email, password)` via the existing `apiFetch` (`POST /auth/login`), plus a TanStack `useMutation` hook. `apiFetch` post-review handles header merging, empty bodies, and envelope-shape validation — use it as-is; do not hand-roll a fetch.
  - [x] `src/api/session.ts` (or similar): store the token in `localStorage` under one exported key, with `getToken/setToken/clearToken`. Story 1.3 attaches it as a Bearer header and clears it on 401 — leave those to 1.3.
  - [x] `src/features/auth/LoginPage.tsx`: email + password form; on failure render the **server envelope's `message`** (already non-disclosing by AC4) — never branch on anything that would distinguish unknown-email from wrong-password.
  - [x] Responsive at the existing `48rem` breakpoint; plain CSS in the established pattern. No component library (spine *Deferred*).

- [x] **Task 8: Tests** (AC: all)
  - [x] `tests/integration/test_schema_1_2.py`: after `alembic upgrade head`, `public` contains exactly `{alembic_version, department, employee}` (set equality, the Story 1.1 pattern); `employee` constraint and index assertions per AC1.
  - [x] `tests/integration/test_login.py`: seed-or-create fixture rows (unique emails per test), then: correct credentials → 200, token decodes with `algorithms=[...]`, claims carry subject id + role, and `exp` lies within `jwt_expire_hours` of now (hours, not days — `NFR-02`); unknown email vs wrong password → status equal AND `response.content` byte-identical; deactivated employee → same body; envelope shape exact `{code, message, details}` with `code == vocabulary.AUTH_FAILED`.
  - [x] AC5 structural test (domain-level, no DB): monkeypatch/spy `verify_password`; call `authenticate` on a stub repository returning `None` and on one returning an employee with a wrong password; assert exactly one verification call on **both** paths.
  - [x] `tests/domain/`: none needed — this story adds no domain rule beyond constants. Do not chase coverage (`NFR-15`).
  - [x] Run the full suite; the architecture, migration-guard, vocabulary and envelope checks must all stay green. `pytest` is the build (F-14).

- [x] **Task 9: Prove it end-to-end** (AC: 2, 3, 10)
  - [x] From clean state: `docker compose down -v` → `docker compose up` → `docker compose exec api alembic upgrade head` → `docker compose exec api python -m seed` (the post-review exec-based sequence in `README.md`).
  - [x] `curl -k` the login endpoint with the seed Admin's credentials → 200 + token; with a wrong password → 401 `AUTH_FAILED`.
  - [x] Rebuild the web image; open the app; log in via the browser flow if a browser is available, otherwise verify the built bundle serves and declare the gap exactly as Story 1.1 did for AC8.

## Dev Notes

### What this story is, and what it is not

This story delivers **login only**: the first two tables, the seeded Admin, credential exchange, and the vocabulary. It does NOT deliver token *verification* on requests (`GET /me`, the Bearer dependency, 401 `TOKEN_INVALID` responses) — that is Story 1.3, and building it early means building it before Story 1.4's authorization primitives exist to consume it. Write `core/security.py`'s decode function now (it belongs beside encode); wire no dependency.

Also NOT here: password change/reset of any kind (PRD §6 — permanent non-goal), password complexity rules (G1 explicitly rejected them), `must_change_password` state (G1 rejected), rate limiting (spine *Deferred*), refresh tokens (`NFR-02`: no refresh mechanism exists), logout endpoint (no source requires one — the client discards its token).

### 🚨 Four traps, in the order they will bite

**1. The layering squeeze on error codes — read this before writing any `raise`.**
`AUTH_FAILED` must be declared in `domain/vocabulary.py` (AD-21), the exception must be `DomainError` (Story 1.1's single handler catches exactly that class), and the `code → 401` mapping must land in `api/v1/errors.py`'s `CODE_TO_STATUS`. But the import contracts (now seven) forbid: `api/` → `domain/` (contract 2), and `core/` → any layer including `domain/` (contract 6, added in review). The one legal wiring:

- `services/auth.py` raises `DomainError(code=vocabulary.AUTH_FAILED, ...)` — `services → domain` is legal.
- `core/security.py` never touches domain code — it returns `bool`/raises library errors; the *service* translates.
- `main.py` populates `CODE_TO_STATUS.update({vocabulary.AUTH_FAILED: 401, vocabulary.TOKEN_INVALID: 401})` — `main.py` is the composition root outside every contract, and the comment above `CODE_TO_STATUS` (post-review) prescribes exactly this. A literal `"AUTH_FAILED"` typed in `api/v1/errors.py` fails the new vocabulary check; an `import app.domain` there fails contract 2. Both failures are correct.

**2. `PasswordHash.recommended()` CRASHES in this project — verified 2026-07-10 on the installed pins.**
The project installs `pwdlib[bcrypt]` (pinned in Story 1.1's `pyproject.toml`); the argon2 extra is absent. `PasswordHash.recommended()` tries to import argon2 first and raises `pwdlib.exceptions.HasherNotAvailable` — it does not fall back. Construct explicitly:

```python
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

password_hash = PasswordHash((BcryptHasher(),))   # produces $2b$12$... hashes
password_hash.verify(password, stored_hash)        # password FIRST, hash second
```

**3. bcrypt 5.0.0 raises `ValueError` above 72 bytes — it no longer truncates.**
Verified: `hash("x" * 73)` → `ValueError: password cannot be longer than 72 bytes, truncate manually if necessary`. 4.x silently truncated; 5.x refuses. An unguarded login with a 100-character password would 500. Pre-check the **encoded byte length** (multibyte UTF-8 characters count per byte, not per character) and route to the ordinary `AUTH_FAILED` on the login path. The length check runs before any hashing on *both* the known-email and unknown-email paths, so it leaks nothing about account existence.

**4. The fallback-hash comparison must run AND its result must be ignored.**
AC5 requires the unknown-email path to run one real bcrypt verification against a constant fallback hash. That fallback is built at import from a string that lives in this repository — so an attacker can send exactly that string as a password. If the code does `if verify(password, fallback): ...` anything differently, the "byte-identical" guarantee dies. The unknown-email path is: `verify(password, FALLBACK_HASH)` → discard → `raise` the same `DomainError` as every other failure. One raise site. The deactivated check (AC7) sits **after** the real hash comparison for the same reason.

### Architecture compliance

- **`AD-14`** binds this story end to end: Bearer JWT with hours-lifetime `exp`; `pwdlib` not `passlib`; `PyJWT` not `python-jose`; failure discloses nothing.
- **`AD-21`** (AC9): constants in `domain/vocabulary.py`, standing build-failing literal check. The check's scope decision is recorded in Task 3 — alembic DDL exempt, `app/` + `seed/` scanned.
- **`AD-22`** (partial): "a deactivated Employee cannot authenticate" — the `FR-01` half lands here (AC7). The deactivation *guards* land in Story 1.6. **`G4` is deliberately open**: whether an outstanding *token* survives deactivation is a Story 1.3-adjacent, pre-deployment decision — do not resolve it here, and do not add an `is_active` check to the (not-yet-existing) token dependency as a drive-by.
- **`AD-23`** (backstop only): `CHECK (id <> manager_id)` ships in this migration because ERD §4.2 puts it on the table; the service-layer cycle gate is Story 1.6's.
- **`AD-3` shape**: one transaction per command, opened in `services/`. Login is a read plus zero writes, but the idiom starts here.
- **`AD-10`** does not apply yet — login is anonymous and no scoped read exists until 1.3/1.4.
- **Naming**: tables singular (`department`, `employee`); paths kebab-case under `/api/v1` (`/auth/login`); models `PascalCase`; domain constants `UPPER_SNAKE_CASE`.

### Previous story intelligence — Story 1.1 and its code review (read this; it is first-hand)

Story 1.1 went through an adversarial review on 2026-07-10; 27 patches were applied and verified. The codebase you inherit differs from what 1.1's original notes describe in these load-bearing ways:

- **Seven import-linter contracts, not five.** New: `core/ is a leaf` (core imports no app layer) and `jobs/ never imports api/`. `tests/test_architecture.py` asserts the contract *contents* — if you change `pyproject.toml` contracts at all, that test must change in the same commit, and the bar for doing so is high.
- **`CODE_TO_STATUS` population from `main.py`** is the prescribed pattern (its comment block spells it out). The map is empty today; this story writes its first two entries.
- **The error handler dumps `mode="json"`** — `details` carrying `date`/`Decimal` serializes correctly. Regression-tested.
- **Settings are built from parts**: `DATABASE_URL` is derived from `POSTGRES_*` env vars with a URL-quoted password; `JWT_SECRET_KEY`, `SEED_ADMIN_PASSWORD`, `POSTGRES_PASSWORD` are validated non-empty and non-`CHANGE_ME` at startup. Your login tests will fail with a `ValidationError` skip if `.env` still carries placeholders — that is by design.
- **Setup commands are exec-based**: `docker compose exec api alembic upgrade head` / `docker compose exec api python -m seed`. The host venv exists solely for `pytest`.
- **`apiFetch` is hardened**: `Headers`-instance merging, `Content-Type` only on non-`FormData` bodies, empty-body 200s, `details` shape validation, and a compile-time leading-slash path type. Build on it; do not work around it.
- **The AD-11 migration guard is strict** (bare `insert()` calls, quoted/schema-qualified `UPDATE`, `MERGE`, `COPY`, `TRUNCATE` all trip it) and parametrizes over every migration file automatically — your migration 0002 is under it from the moment the file exists.
- **`tests/test_error_envelope.py` relies on `TEST_ONLY_CODE` being unmapped** — do not add it to `CODE_TO_STATUS`.
- **One warning left standing from 1.1**: starlette 1.3.1 deprecates `httpx` in `TestClient` in favour of `httpx2`. Still a warning, still not spine-governed, still not worth a mid-story dependency drift. Leave it.
- **Two open defers** (in `deferred-work.md`): `configure_logging()` import side effect; the `seed` package name. Neither blocks this story; do not fix them as drive-bys.

### Verified library facts — checked 2026-07-10 against the *installed* pinned versions, not documentation

- `PasswordHash.verify(password, hash)` — password first. `hash()` returns `$2b$12$...` strings.
- `PasswordHash.recommended()` raises `HasherNotAvailable` here (no argon2 extra). Trap 2 above.
- bcrypt 5.0.0: 73+ bytes → `ValueError`. Trap 3 above.
- PyJWT 2.13.0: `jwt.decode(...)` without `algorithms=` raises `DecodeError` unconditionally — there is no default. Tampered token → `InvalidSignatureError`; expired → `ExpiredSignatureError`; both subclass `jwt.PyJWTError` (catch that in 1.3, not bare `Exception`).
- PyJWT 2.13.0 emits `InsecureKeyLengthWarning` for HMAC keys under 32 bytes. `.env.example`'s documented generator (`secrets.token_urlsafe(32)`) produces 43 chars — fine. A short test-fixture key will warn; use a ≥32-byte key in test fixtures too.
- PostgreSQL 18's `uuidv7()` is native — verified working in Story 1.1's stack (`postgres:18.4-bookworm`).

### Testing standards

`tests/domain/` runs with no database fixture; `tests/integration/` against real PostgreSQL (fixtures now skip loudly on missing/placeholder `.env` or unreachable DB). Every module docstring names its FR/DR/AD (`SM-6`). This story's substantive tests are the ones the ACs name: schema set-equality, the byte-identical failure pair, the AC5 spy test, seed idempotency, the vocabulary literal check. `NFR-15`: do not chase coverage on the login route's happy-path plumbing beyond AC3.

**Byte-identity, mechanically:** compare `response.content` (raw bytes), not parsed JSON — key order or whitespace differences are exactly what "byte-identical" exists to catch. Both failure modes flow through the same single `raise` site and the same handler, so this holds by construction; the test proves it stays that way.

### Project Structure Notes

- New files: `backend/alembic/versions/0002_*.py`, `backend/app/repositories/models.py` (or `department.py`/`employee.py`), `backend/app/repositories/employee.py`, `backend/app/services/auth.py`, `backend/app/core/security.py`, `backend/app/api/v1/auth.py`, `backend/tests/test_vocabulary_literals.py`, `backend/tests/integration/test_schema_1_2.py`, `backend/tests/integration/test_login.py`, frontend `src/features/auth/LoginPage.tsx`, `src/api/auth.ts`, `src/api/session.ts`.
- Modified: `domain/vocabulary.py` (constants), `main.py` (map population), `api/v1/router.py` (auth router), `seed/__main__.py` (department + admin), `alembic/env.py` or `repositories/base.py` (model imports), `App.tsx` (conditional login/shell).
- `core/security.py` was named by Story 1.1's `core/` table ("Story 1.2 fills this in") — fill that file; do not create a parallel `auth_utils.py`.
- No `project-context.md` exists. The repository has its first commit-worthy state but **zero commits** — `baseline_commit` will still be `NO_COMMITS` unless Arpan commits Story 1.1 first (recommended, so this story's diff is reviewable on its own).

### References

- [epics.md#Story 1.2](../planning-artifacts/epics.md) — story statement and all ten criteria, verbatim
- [epics.md#G1](../planning-artifacts/epics.md), [erd.md#GAP-5](../planning-artifacts/module-4-erd/erd.md) — Admin-supplied initial password; no reset/change/complexity policy, by decision
- [erd.md#GAP-1, §4.2](../planning-artifacts/module-4-erd/erd.md) — email is the identifier; never reusable; "the hash comparison must run regardless"
- [api-contracts.md#2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — `AUTH_FAILED` 401, `TOKEN_INVALID` 401, envelope shape
- [api-contracts.md#4.1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — `POST /auth/login`, anonymous
- [ARCHITECTURE-SPINE.md#AD-14, #AD-21, #AD-22, #AD-23](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md)
- [epics.md#Story 1.3, #Story 1.4](../planning-artifacts/epics.md) — the boundary: token verification and authorization primitives are NOT this story
- [1-1-project-foundation-and-reproducible-setup.md](1-1-project-foundation-and-reproducible-setup.md) — Dev Agent Record, Review Findings, and the post-review state this story builds on
- [deferred-work.md](deferred-work.md) — open defers; not this story's work

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — BMad Dev Story workflow.

### Debug Log References

- `alembic check` after Task 1/2: initial run reported `TEXT -> String` type diffs on
  five columns because the models declared `Mapped[str]` (→ VARCHAR) against the
  migration's `sa.Text()`. Fixed by declaring `mapped_column(Text, ...)` on the five
  text columns; `alembic check` then reported "No new upgrade operations detected".
- `lint-imports` after Task 5: contract 2 flagged `app.api -> app.domain` and
  `app.api -> app.repositories` as INDIRECT violations through `app.services`. This is
  the intended layered call chain (a route calls a service that raises a `DomainError`
  and opens a connection), which Story 1.2 is the first story to exercise. Resolved by
  setting `allow_indirect_imports = "true"` on contract 2 ONLY (it forbids *direct*
  skip-level imports, per its name and Trap 1), and pinning that option in
  `test_architecture.py` so it cannot be silently dropped or flipped.

### Completion Notes List

All ten acceptance criteria implemented and verified; all nine tasks complete.

- **AC1** — Migration `0002` creates `department` and `employee` and only those; unique
  email, role CHECK, `id <> manager_id` backstop (AD-23), nullable `manager_id`, NOT NULL
  `department_id` FK, and both indexes. Verified by `test_schema_1_2.py` against the live
  catalog and by `alembic check` (models ≡ migration, empty diff).
- **AC2** — Seed creates exactly one Department and one Admin (`manager_id` NULL,
  `is_active` true, role from `vocabulary.ROLE_ADMIN`), idempotent. `test_seed.py`.
- **AC3** — `POST /api/v1/auth/login` returns 200 + JWT with `sub`/`role` claims and an
  hours-lifetime `exp`. `test_login.py`.
- **AC4/AC5** — One raise site in `services/auth.py`; the unknown-email path runs one
  discarded verification against `core.security.FALLBACK_HASH`. Byte-identity proven by
  comparing `response.content` (`test_login.py`); the single-verification structure
  proven DB-free by the spy tests in `test_authenticate_no_shortcircuit.py`.
- **AC6** — `pwdlib` `BcryptHasher` (explicit, not `recommended()`); `$2b$12$` digests;
  neither `passlib` nor `python-jose` in the dependency set.
- **AC7** — `is_active` checked *after* the hash comparison; deactivated login is
  byte-identical to a wrong password. `test_login.py`.
- **AC8** — `{code, message, details}` envelope with `code == AUTH_FAILED`, exercised on
  the first non-2xx-capable endpoint. `CODE_TO_STATUS` populated from `main.py`.
- **AC9** — `domain/vocabulary.py` holds the role and error constants; the standing
  `test_vocabulary_literals.py` AST-scans `app/` and `seed/`, iterates `__all__`, and
  guards itself with a planted literal.
- **AC10** — `LoginPage` + `session.ts` + conditional `App.tsx`. Verified in a real
  headless Chrome: unauthenticated visitor sees the login screen; a successful login
  stores the token in `localStorage['leaveflow.token']` and lands on the shell.

Boundaries respected (all Story 1.3's, not touched): token *verification* on requests,
the Bearer dependency, `TOKEN_INVALID` raising (declared, not raised), clear-on-401. `G4`
(token survival past deactivation) left deliberately open. `core/security.py`'s
`decode_token` written now, wired later.

Validation: 59 backend tests pass; 7/7 import contracts kept; `alembic check` empty;
frontend lints and builds. Proven end-to-end from a clean `docker-compose down -v` →
`up` → `alembic upgrade head` → `python -m seed` → curl (200 + 401 byte-identical) →
browser login. Note: this environment has the standalone `docker-compose` binary, not the
`docker compose` plugin the README documents — commands are otherwise identical.

### File List

**New — backend**
- `backend/alembic/versions/0002_department_and_employee.py`
- `backend/app/repositories/models.py`
- `backend/app/repositories/engine.py`
- `backend/app/repositories/employee.py`
- `backend/app/services/auth.py`
- `backend/app/core/security.py`
- `backend/app/api/v1/auth.py`
- `backend/tests/test_vocabulary_literals.py`
- `backend/tests/domain/test_authenticate_no_shortcircuit.py`
- `backend/tests/integration/test_schema_1_2.py`
- `backend/tests/integration/test_login.py`
- `backend/tests/integration/test_seed.py`
- `backend/tests/integration/test_model_migration_agreement.py` (added in code-review pass)

**New — frontend**
- `frontend/src/api/auth.ts`
- `frontend/src/api/session.ts`
- `frontend/src/features/auth/LoginPage.tsx`

**Modified — backend**
- `backend/app/domain/vocabulary.py` (role + error-code constants, `__all__`)
- `backend/app/main.py` (`CODE_TO_STATUS` population for the two 401 codes)
- `backend/app/api/v1/router.py` (register the auth router)
- `backend/seed/__main__.py` (seed the Department and Admin)
- `backend/alembic/env.py` (import the models module so autogenerate sees them)
- `backend/pyproject.toml` (contract 2: `allow_indirect_imports = "true"`)
- `backend/tests/test_architecture.py` (pin the new contract-2 option)
- `backend/tests/test_migrations_insert_nothing.py` (expected migration list → two files)
- `backend/tests/integration/test_migration_smoke.py` (head → `0002`; drop the
  Story-1.1-only no-domain-table assertion, now owned by `test_schema_1_2.py`)

**Modified — frontend**
- `frontend/src/api/index.ts` (export auth + session surface)
- `frontend/src/App.tsx` (conditional login/shell on token presence)
- `frontend/src/index.css` (login screen styles, 48rem breakpoint)

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-10 | Story created (ultimate context engine analysis: epics, spine, api-contracts, ERD, PRD, Story 1.1 + its adversarial review, and library APIs verified live against installed pins). Status: ready-for-dev. |
| 2026-07-11 | Implemented all 9 tasks / 10 ACs: migration 0002 (`department`, `employee`), ORM models, `domain/vocabulary.py` + standing literal check, `core/security.py` (bcrypt via pwdlib + PyJWT), the auth service and `POST /auth/login`, the Department+Admin seed, and the React login screen. Contract 2 gained `allow_indirect_imports` to permit the layered api→service→domain chain (first exercised here). 59 backend tests pass; verified end-to-end via curl and a real browser login. Status: review. |
| 2026-07-11 | Code-review fixes (5 findings): guarded all `localStorage` access in `session.ts` against private-mode/quota throws and flipped React state before persisting (blank-screen / stranded-login robustness); added `test_model_migration_agreement.py` running `alembic check` in the suite so the model↔migration agreement is enforced, not just documented; seed department lookup now `.limit(1).first()` (no crash on a duplicate name post-1.5); seed hashes the Admin password only on the insert path (skips ~250ms bcrypt on re-seed); `services/auth.py` opens its Session with `expire_on_commit=False` so the copied transaction idiom is commit-safe for the write commands. 60 backend tests pass; frontend builds; browser login re-verified. |
