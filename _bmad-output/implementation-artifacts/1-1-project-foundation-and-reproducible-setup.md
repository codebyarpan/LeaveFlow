---
baseline_commit: NO_COMMITS
---

# Story 1.1: Project Foundation and Reproducible Setup

Status: done

Epic: 1 — Secure Access and Organization Administration (Phase 1, correctness core)
Story Key: `1-1-project-foundation-and-reproducible-setup`
Created: 2026-07-10

## Story

As a developer joining LeaveFlow,
I want a hand-rolled four-package skeleton that runs from a documented command sequence on a clean machine,
so that every later story lands in a structure where a domain rule cannot be implemented in the wrong layer.

## Acceptance Criteria

**AC1 — Reproducible setup (`NFR-21`, `NFR-20`)**
**Given** a clean machine with Docker installed and no prior LeaveFlow state
**When** I run `docker compose up`, then `alembic upgrade head`, then the seed command
**Then** `GET /api/v1/health` answers `200` and the static React bundle is served
**And** no step required a configuration value absent from `.env.example`

**AC2 — Import-direction enforcement (`AD-1`, `NFR-13`)**
**Given** the backend source tree `app/{api,services,repositories,domain,jobs,core}`
**When** the import-direction check runs as part of the test suite
**Then** `domain/` imports no ORM, no web framework, and performs no I/O; `api/` imports neither `repositories/` nor `domain/`; `repositories/` does not import `services/`
**And** a violation of any of these fails the build rather than merely warning

**AC3 — Error envelope and exception mapping (spine *Errors in code*)**
**Given** a typed domain exception raised in `services/`
**When** it propagates to the `api/` layer
**Then** a single `api/` exception handler maps it to the envelope `{ code, message, details }` and to a status code
**And** `domain/` and `services/` import no HTTP, verified by the same import-direction check

> The endpoint-level assertion — that *every* non-2xx response carries this envelope — belongs to Story 1.2, the first story in which any endpoint can return a non-2xx response. The `AD-21` vocabulary assertion is likewise Story 1.2's, where the first enumerated values come into existence. Asserted here, both would test a codebase that does not yet exist.

**AC4 — Deployment topology and TLS (`NFR-06`; spine *Deployment*, architecture §2)**
**Given** the `docker compose` topology
**When** the deployed environment is inspected
**Then** a `proxy` service terminates TLS in front of the `web` and `api` services, which sit alongside `postgres:18`
**And** credentials and tokens travel over TLS in any deployed environment

**AC5 — No committed secrets (`NFR-20`)**
**Given** the repository
**When** version control is inspected
**Then** `.env` is ignored and `.env.example` is committed
**And** no secret, database credential, or JWT signing key appears in any committed file

**AC6 — This story creates no domain table (`AD-11`)**
**Given** the Alembic directory after `alembic upgrade head`
**When** the database is inspected
**Then** no domain table has been created by this story, and no migration inserts a Leave Type row

**AC7 — Exact dependency pins**
**Given** the installed dependency set
**When** versions are compared against the Architecture Spine's stack table
**Then** every version matches exactly
**And** SQLAlchemy remains on the 2.0 line, TypeScript on 6.0.3, and Python on 3.13 — the three pins deliberately behind latest, which a later story must not upgrade

**AC8 — Frontend shell (`NFR-18`)**
**Given** the frontend
**When** it is built
**Then** it is a Vite + React + TypeScript SPA with TanStack Query and a typed API client
**And** its shell is usable at common desktop and tablet widths

## Tasks / Subtasks

- [x] **Task 1: Repository skeleton and version control hygiene** (AC: 5, 6)
  - [x] Create the source tree exactly as specified in *Source Tree* below. Do **not** run a template generator for the backend.
  - [x] Write `.gitignore` ignoring `.env`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.pytest_cache/`.
  - [x] Write `.env.example` with **placeholder** values for every variable `pydantic-settings` reads. Commit it.
  - [x] Verify `git status` shows no `.env`, and grep the tree for any real credential or signing key before the first commit.

- [x] **Task 2: Backend package skeleton and settings** (AC: 1, 2, 7)
  - [x] Create `backend/app/{api/v1,services,repositories,domain,jobs,core}` with `__init__.py` in each.
  - [x] Pin every backend dependency to the exact version in *Pinned Stack* below.
  - [x] `core/settings.py`: `pydantic-settings` `BaseSettings` reading `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_HOURS`, seed Admin/Department vars. Every field must have a matching entry in `.env.example`.
  - [x] Every module names in its docstring the FR/DR/NFR/AD it implements (`SM-6`). Foundation modules cite `NFR-13`, `NFR-20`, `NFR-21`, `AD-1`.

- [x] **Task 3: FastAPI application and health endpoint** (AC: 1, 3)
  - [x] `app/main.py`: create the FastAPI app, mount the `api/v1` router under base path `/api/v1`.
  - [x] `api/v1/health.py`: `GET /api/v1/health` → `200`. Anonymous, no auth dependency (api-contracts §4.10).
  - [x] Structured JSON logs to stdout (spine *Observability*). Metrics and error monitoring are **deferred** — do not add them.

- [x] **Task 4: Typed domain errors and the single exception handler** (AC: 3)
  - [x] `domain/errors.py`: base `DomainError` carrying `code`, `message`, `details`. Plain Python exception — **no Pydantic, no HTTP, no ORM**.
  - [x] `domain/vocabulary.py`: the module where `UPPER_SNAKE_CASE` constants are declared exactly once (`AD-21`). It may be near-empty in this story; Story 1.2 adds `AUTH_FAILED`, `TOKEN_INVALID`, the role values, and the standing literal check.
  - [x] `api/v1/errors.py`: **one** `@app.exception_handler(DomainError)` mapping the exception to `{ code, message, details }` and to a status code via a single `code → status` map.
  - [x] Test: raise a `DomainError` from a `services/` function reached through a throwaway route registered on a test-only app; assert body shape and status. Do **not** add a permanent route that exists only to raise.

- [x] **Task 5: Import-direction check that fails the build** (AC: 2, 3)
  - [x] Add `import-linter` (2.13) as a dev dependency.
  - [x] Configure contracts in `pyproject.toml` under `[tool.importlinter]` — **read the `layers` trap in Dev Notes before writing this**. A `layers` contract alone does not satisfy AC2.
  - [x] `backend/tests/test_architecture.py`: `assert lint_imports() == 0`. This is the build-failing mechanism (see *Known Gap: F-14*).
  - [x] Verify by deliberately adding `import sqlalchemy` to a `domain/` module and confirming `pytest` fails; then remove it.

- [x] **Task 6: Alembic wiring that creates no domain table** (AC: 1, 6)
  - [x] `alembic init` into `backend/alembic/`. Point `env.py` at `core/settings.py`'s `DATABASE_URL` — do not duplicate the URL in `alembic.ini`.
  - [x] `repositories/base.py`: `class Base(DeclarativeBase)`. Set `target_metadata = Base.metadata`. **No models exist yet** — this is correct.
  - [x] Create **one no-op baseline revision** (`upgrade()`/`downgrade()` both `pass`). See *Alembic* in Dev Notes for why an explicit revision beats zero revisions.
  - [x] Verify: after `alembic upgrade head`, the database contains `alembic_version` (stamped, one row) and **no other table**.

- [x] **Task 7: Seed command entrypoint** (AC: 1, 6)
  - [x] `backend/seed/` with a CLI entrypoint invocable as a single documented command.
  - [x] It **seeds nothing in this story** — `department` and `employee` do not exist until Story 1.2, and `leave_type` until Story 2.1. It must exit `0` so AC1's three-command sequence completes.
  - [x] Make it idempotent from the outset; Story 1.2 and Story 2.1 extend it. `AD-11`: **no migration ever inserts a Leave Type row** — seeding is always this command's job.

- [x] **Task 8: Docker Compose topology** (AC: 1, 4)
  - [x] Services: `proxy` (TLS termination), `web` (static React bundle), `api` (FastAPI + uvicorn), `postgres:18`.
  - [x] **Omit the `version:` key** — obsolete under the Compose Specification and it emits a warning.
  - [x] `postgres` healthcheck via `pg_isready`; `api` uses `depends_on: {postgres: {condition: service_healthy}}`.
  - [x] **Do not add an auto-migrate service.** See the *Compose* note in Dev Notes — it would silently break AC1.
  - [x] `proxy` routes `/api/v1` → `api`, everything else → `web`, and terminates TLS. Self-signed certs are acceptable locally; TLS is a requirement of the **deployed** environment.
  - [x] `scheduler` (cron) and the documents volume are **deferred** — Story 2.10 and Story 4.1 add them. Do not scaffold empty services.

- [x] **Task 9: Frontend SPA shell** (AC: 1, 7, 8)
  - [x] Scaffold with `npm create vite@latest frontend -- --template react-ts`, then **immediately pin `typescript` to `6.0.3`** — the scaffold will otherwise pull TypeScript 7.x (see *The TypeScript 7 trap*).
  - [x] Pin `react`/`react-dom` 19.2.7, `vite` 8.1.4, `@tanstack/react-query` 5.101.2, `@vitejs/plugin-react` ^6.0.3.
  - [x] `src/api/`: typed fetch client + `QueryClientProvider`. `src/features/`, `src/components/` exist per the spine's source tree.
  - [x] `vite.config.ts`: `server.proxy` maps `/api/v1` → the api service, **without** a `rewrite` (the backend already serves under `/api/v1`; keeping the prefix makes dev and prod paths identical).
  - [x] Responsive shell across desktop and tablet widths (`NFR-18`). Styling and component library are explicitly deferred by the spine — do not choose one.
  - [x] `web` container serves the built `dist/` statically with an SPA fallback (`try_files $uri $uri/ /index.html`).

- [x] **Task 10: Prove the three-command sequence** (AC: 1)
  - [x] From a clean state (`docker compose down -v`), run the three commands verbatim as documented.
  - [x] Confirm `GET /api/v1/health` → `200` and the React bundle loads through the proxy.
  - [x] Write the sequence into `README.md`. Any value the sequence needs must already be in `.env.example`.

### Review Findings

Adversarial code review 2026-07-10 (Blind Hunter + Edge Case Hunter + Acceptance Auditor; 55 raw findings, deduplicated to 37, 8 dismissed as noise).

**Resolution 2026-07-10:** both decisions were made (D1 → `docker compose exec`-based commands two and three; D2 → `settings.py` builds the URL from `POSTGRES_*` parts with a quoted password) and all 27 patches applied and verified by execution: 16 backend tests pass (7 import contracts kept, including two new ones; new date-in-details regression test), frontend builds and lints clean, images rebuilt, the exec-based three-command sequence run against the live stack, health 200, SPA fallback 200, and the trailing-slash redirect now answers `https://localhost:8443/...` (scheme fixed by `--forwarded-allow-ips`, port preserved by an `$http_host` follow-on fix in `proxy/nginx.conf`). The two defers remain open in `deferred-work.md`.

- [x] [Review][Decision] AC1's "three commands" require a host Python 3.13 toolchain the AC does not grant (high) — README command two bundles `cd backend`, `python3.13 -m venv .venv && pip install -e ".[dev]"` before `alembic upgrade head`: a fourth and fifth operator step, needing host Python 3.13, where AC1's Given grants only Docker. Options: (a) route commands two and three through `docker compose exec api` so a clean machine truly needs only Docker, or (b) keep the venv flow and declare the deviation in the story record and README. Related doc nits to fix with either choice: README §Tests' two command lines assume different starting directories, and `tests/integration/conftest.py` says `docker compose up -d` where the README's canonical sequence says `docker compose up`.
- [x] [Review][Decision] Postgres password is hand-duplicated and URL-hostile characters break it silently (medium) — the same password lives in `.env` as `POSTGRES_PASSWORD` and embedded in `DATABASE_URL` (and compose interpolates it raw into a third URL at `docker-compose.yml:71`); a password containing `@ : / # %` yields a malformed DSN with a misleading failure. Options: (a) build `DATABASE_URL` from `POSTGRES_*` parts in `core/settings.py` with URL-quoting — single source of truth, removes the second CHANGE_ME, or (b) keep both values and add loud lockstep + character-set warnings to `.env.example`.
- [x] [Review][Patch] Error handler 500s on any non-JSON-primitive in `details` — `model_dump()` leaves `date`/`Decimal` intact and `json.dumps` raises `TypeError`; reproduced. Fix: `model_dump(mode="json")` (high) [backend/app/api/v1/errors.py:84]
- [x] [Review][Patch] `%` in DATABASE_URL crashes alembic; the comment claiming `set_main_option` escapes it is wrong — verified against alembic 1.18.5 docs: caller must escape. Fix: `.replace("%", "%%")` + correct the comment (medium) [backend/alembic/env.py:32-34]
- [x] [Review][Patch] `X-Forwarded-Proto` from the proxy is ignored — uvicorn's `proxy_headers` is on by default but `forwarded_allow_ips` defaults to loopback, and the nginx container connects from the compose network. Redirects (e.g. trailing-slash 307) generate `http://` URLs that dead-end. Fix: set `FORWARDED_ALLOW_IPS` in the api service environment (medium) [backend/Dockerfile:40]
- [x] [Review][Patch] `CODE_TO_STATUS` comment prescribes an import the contracts forbid — "keys must come from `domain/vocabulary.py`" but contract 2 bans `api/` → `domain/`; Story 1.2 cannot satisfy both as written. Fix: prescribe the same wiring pattern as the handler — `main.py` populates the map at startup (medium) [backend/app/api/v1/errors.py:56]
- [x] [Review][Patch] AD-11 migration guard misses bare `insert()` (ast.Name call), quoted/schema-qualified `UPDATE`, `MERGE INTO`, `COPY ... FROM` — canonical SQLAlchemy 2.0 style `op.execute(insert(t).values(...))` passes today. Extend visitor + regex + guard-the-guard cases (medium) [backend/tests/test_migrations_insert_nothing.py:44-71]
- [x] [Review][Patch] Settings accept empty and `CHANGE_ME` secrets silently, and `jwt_expire_hours` accepts ≤ 0 — Story 1.2 would sign JWTs with the committed placeholder. Add a field validator rejecting empty/`CHANGE_ME*` values and `Field(gt=0)` (medium) [backend/app/core/settings.py:49-58]
- [x] [Review][Patch] Compose interpolation has no `:?` guards — running command one without `.env` yields empty credentials, a postgres crash-loop and a never-healthy api instead of a message naming the missing file (medium) [docker-compose.yml:71-105]
- [x] [Review][Patch] `apiFetch` silently drops headers passed as a `Headers` instance — object-spread of `Headers` yields `{}`; Story 1.2's `Authorization` is the first casualty. Merge via the `Headers` API (medium) [frontend/src/api/client.ts:79-82]
- [x] [Review][Patch] `app.core`, `app.jobs`, `app.main` and `seed` sit outside every import-linter contract — e.g. Story 2.10's `jobs/` could import `api/` with a green suite. Add: `core/` imports no app layer; `jobs/` imports no `app.api` (medium) [backend/pyproject.toml:70-124]
- [x] [Review][Patch] `requests` omitted from forbidden lists in contracts 3 and 4 — the story's prescribed config names it; every hole in the proxy list is a hole in the "no I/O" guarantee (low) [backend/pyproject.toml:100-114]
- [x] [Review][Patch] "Every version in `package.json` is an exact pin" is false — five caret ranges in devDependencies contradict `frontend/README.md:22`. Pin them exactly (lockfile-verified) so the claim becomes true (low) [frontend/package.json:18-22]
- [x] [Review][Patch] Contract self-check verifies contract *names*, not content — emptying a `forbidden_modules` list passes both architecture tests. Assert the contract bodies, not just the name set (low) [backend/tests/test_architecture.py:59-67]
- [x] [Review][Patch] Integration fixture skips only on `OperationalError` — a missing `.env` (`ValidationError`) or malformed URL (`ArgumentError`) errors the suite instead of the promised skip-with-reason (low) [backend/tests/integration/conftest.py:31-40]
- [x] [Review][Patch] Seed command: unreachable database yields the raw traceback its docstring promises away, and `engine.dispose()` is skipped on error paths — catch `OperationalError` legibly; use try/finally (low) [backend/seed/__main__.py:42-80]
- [x] [Review][Patch] `pg_isready` probes the unix socket, which the postgres image's init-phase temp server answers — healthcheck can pass before TCP listens on first boot. Add `-h localhost` (low) [docker-compose.yml:105]
- [x] [Review][Patch] Backend Dockerfile's layer-caching comment describes an optimization the layer order doesn't implement — `pip install` runs after all source `COPY`s, so every source edit re-resolves dependencies. Fix the comment or restructure (low) [backend/Dockerfile:21-29]
- [x] [Review][Patch] Proxy entrypoint never checks certificate expiry (825-day cert reused forever) and discards openssl's error output under `set -e`. Add `openssl x509 -checkend 0` to the regenerate condition; drop `2>/dev/null` (low) [proxy/entrypoint.sh:28-38]
- [x] [Review][Patch] `apiFetch` forces `Content-Type: application/json` unconditionally — pre-installed trap for Story 4.1's `FormData` upload (multipart boundary lost). Set it only for JSON bodies (low) [frontend/src/api/client.ts:80]
- [x] [Review][Patch] `isErrorEnvelope` never validates `details` — an array or string flows through typed as `Record<string, unknown>` (low) [frontend/src/api/client.ts:61-66]
- [x] [Review][Patch] Only 204 is exempt from body parsing — a 200/201 with an empty body throws `SyntaxError` from `response.json()` (low) [frontend/src/api/client.ts:107-110]
- [x] [Review][Patch] `apiFetch` path without a leading slash concatenates silently (`/api/v1health`) — guard it, or type the parameter as `` `/${string}` `` for a compile-time fix (low) [frontend/src/api/client.ts:76-77]
- [x] [Review][Patch] `vite.config.ts` reads `process.env.PROXY_HTTPS_PORT`, which nothing populates — Vite does not load the repo-root `.env` into `process.env`; an operator changing the port in `.env` gets a stale dev proxy. Use `loadEnv` or document shell-env-only (low) [frontend/vite.config.ts:18]
- [x] [Review][Patch] `prepend_sys_path = .` resolves against the cwd — `alembic -c backend/alembic.ini` from the repo root dies with `ModuleNotFoundError: app`. Use `%(here)s` (low) [backend/alembic.ini:21]
- [x] [Review][Patch] `JsonFormatter` drops all `extra=` fields — "structured JSON logs" that silently discard structure the moment a later story logs `extra={"employee_id": ...}` (low) [backend/app/core/logging.py:24-35]
- [x] [Review][Patch] AC3 test raises from a stand-in defined in the test file, not a `services/` function — the deviation is well-argued in the docstring but unrecorded in the Dev Agent Record, unlike the `-d` deviation. Declare it (low) [backend/tests/test_error_envelope.py:30]
- [x] [Review][Defer] `configure_logging()` runs as an import side effect of `app.main`, replacing the importer's root log handlers (pytest included — `test_health.py` imports it at collection) [backend/app/main.py:24] — deferred, pre-existing
- [x] [Review][Defer] A top-level pip package literally named `seed` is installed into site-packages, and the image keeps a duplicate source copy at `/srv` on `sys.path` — collision-prone naming, but the story's prescribed source tree fixes `backend/seed/` [backend/pyproject.toml:54] — deferred, pre-existing

## Dev Notes

### What this story is, and what it is emphatically not

This is scaffolding. It creates **no domain table, no business rule, and no user-facing feature**. Its entire value is that it makes the *next* 26 stories land in a structure where `AD-1` cannot be violated by accident. Over-building here — adding an `employee` model "since we'll need it," wiring auth, seeding leave types — actively breaks AC6 and AC2.

**There is no starter template.** `fastapi/full-stack-fastapi-template` was evaluated and **rejected**: it ships **SQLModel**, in which one class is both the Pydantic API schema and the SQLAlchemy table. That fusion is exactly the coupling `AD-1` forbids, and it dissolves the structural guarantee `DR-2` depends on. It also ships email-based password recovery, a PRD §6 non-goal. Its `docker-compose` and Alembic wiring may be consulted **as reference only**. Scaffold the four-package tree by hand.

*(The frontend is different: `npm create vite@latest -- --template react-ts` is the ordinary Vite scaffold, not the rejected template, and is the expected way to start Task 9.)*

### 🚨 Three traps that will silently break this story

**1. The `import-linter` `layers` contract does not do what AC2 needs.**

A `layers` contract forbids *upward* imports only. It does **not** forbid skip-level imports — `layers = [api, services, repositories, domain]` happily permits `api/` importing `domain/` directly, because `domain` is merely "lower." AC2 requires `api/` to import **neither** `repositories/` nor `domain/`. That is strictly stronger than `layers` alone, and needs supplementary `forbidden` contracts. A dev who writes only the `layers` contract gets a green test suite and an unenforced architecture.

Also: **no import-graph tool can verify "performs no I/O."** `import-linter`, `tach` and `pytest-archon` all reason over imports, not syscalls. Enforce "no I/O" *by proxy* — forbid `domain/` from importing the libraries that perform it. Say so in a comment so the next reader does not mistake the proxy for the guarantee.

Working configuration (`pyproject.toml`):

```toml
[tool.importlinter]
root_package = "app"
include_external_packages = true

# 1. Ordering. Forbids all upward imports (domain -> anything, repositories -> services/api, services -> api).
#    Note: repositories and domain must NOT be declared independent with `|` — repositories -> domain is allowed.
[[tool.importlinter.contracts]]
name = "Layered architecture (AD-1)"
type = "layers"
layers = ["app.api", "app.services", "app.repositories", "app.domain"]

# 2. Closes the skip-level gap contract 1 leaves open. AC2 requires this.
[[tool.importlinter.contracts]]
name = "api/ talks only to services/ (AD-1)"
type = "forbidden"
source_modules = ["app.api"]
forbidden_modules = ["app.repositories", "app.domain"]

# 3. domain/ purity: no ORM, no web framework, no I/O library. Proxy for "performs no I/O".
[[tool.importlinter.contracts]]
name = "domain/ is pure (AD-1)"
type = "forbidden"
source_modules = ["app.domain"]
forbidden_modules = ["sqlalchemy", "psycopg", "alembic", "fastapi", "starlette", "httpx", "requests"]

# 4. services/ raises typed domain exceptions and never imports HTTP (AC3, spine "Errors in code").
[[tool.importlinter.contracts]]
name = "services/ imports no HTTP (AC3)"
type = "forbidden"
source_modules = ["app.services"]
forbidden_modules = ["fastapi", "starlette", "httpx", "requests"]
```

Run it inside pytest so a violation **fails the build** rather than warning:

```python
# backend/tests/test_architecture.py
"""Enforces AD-1 and NFR-13: the layered structure is mechanical, not aspirational."""
from importlinter.cli import lint_imports

def test_import_direction_contracts_hold():
    assert lint_imports() == 0, "Architecture contract violated — see import-linter output"
```

`lint_imports()` returns `0` on success, `1` on any broken contract.

**2. The TypeScript 7 trap.** TypeScript **7.0.2 went GA on 2026-07-08 — two days ago.** `npm create vite@latest` and any `npm install typescript` will now resolve to 7.x. The spine pins **6.0.3** deliberately: 7.x is the native Go port, and TS 7 *hard-removes* what TS 6 only deprecated (`target: es5`, AMD/UMD/SystemJS, `moduleResolution: node10`). A three-day budget cannot absorb it. **Pin `"typescript": "6.0.3"` explicitly and verify with `npx tsc --version` after install.** 6.0.3 is the last 6.x release; there is no 6.1.

**3. `docker compose up` must not run the migration.** The obvious Compose idiom is a one-shot `migrate` service gated by `depends_on: {condition: service_completed_successfully}`. **Do not use it here.** `NFR-21` and AC1 fix the setup as *three operator commands*: `docker compose up`, **then** `alembic upgrade head`, **then** the seed command. An auto-migrate service makes command two a no-op, so AC1's test would pass against a topology that no longer matches its own documentation. Give `postgres` a `pg_isready` healthcheck and have `api` wait on `service_healthy`; leave the migration to the operator.

### Architecture compliance — the invariants this story must satisfy

`AD-1` is the whole point of this story. Imports flow `api → services → {repositories, domain}` and `repositories → domain`. `domain/` imports no ORM, no web framework, and performs no I/O. `api/` never imports `repositories/` or `domain/`. `repositories/` never imports `services/`. Any function that computes a leave quantity lives in `domain/`.

Two consequences the spine relies on, which you are building the machinery for: `NFR-08`'s "exactly one implementation of the day count, and a second anywhere is a defect" becomes a **structural fact** rather than something a reviewer must police — weekend-and-holiday logic can only be *expressed* in a package with no way to reach a database. And `SM-2`'s boundary tests need no database fixture.

`AD-11` — `leave_type` seed rows are inserted by a **seed command, never by a migration**. AC6 asserts this before any Leave Type exists, so it holds vacuously today. It stops holding vacuously the moment someone reaches for `op.bulk_insert()` in Story 2.1. The constraint is established here.

`AD-21` — every enumerated string is `UPPER_SNAKE_CASE`, declared exactly once in `domain/`, and appears as a literal nowhere else. Create `domain/vocabulary.py` now. The standing literal check arrives in Story 1.2 with the first enumerated values.

### Where `core/` sits, and the one decision you must not improvise

`AD-1` names four packages; `core/` is a fifth, holding "settings, security, error envelope" (spine *Source tree*). It is not a layer — it is a leaf. Resolve it this way, and do not invent an alternative:

| Concern | Lives in | Why |
| --- | --- | --- |
| Typed domain exceptions (`DomainError`, `code`, `details`) | `domain/errors.py` | `services/` raises them and must not import HTTP. Keep them stdlib-only — no Pydantic. |
| Error code constants | `domain/vocabulary.py` | `AD-21`: declared exactly once, in `domain/`. |
| `code → HTTP status` map + envelope response model | `api/v1/errors.py` | The mapping is an HTTP concern. `domain/` must never learn about status codes. |
| Settings (`pydantic-settings`) | `core/settings.py` | Read by `api/`, `services/`, `jobs/`. Never by `domain/`. |
| Password hashing, JWT encode/decode | `core/security.py` | Story 1.2 fills this in. |
| SQLAlchemy `DeclarativeBase` | `repositories/base.py` | Models are `repositories/`' business (spine *Source tree*). |

`domain/` must import **nothing** from `core/` — that is what keeps it pure and what makes contract 3 above enforceable.

### Source tree (from the spine — build exactly this)

```text
leaveflow/
  backend/
    app/
      api/v1/         # routers, Pydantic request/response schemas, authz dependencies
      services/       # one transaction per command; orchestration; policy
      repositories/   # SQLAlchemy 2.0 models, scoped queries, FOR UPDATE
      domain/         # PURE: calendar, proration, carry_forward, balance, vocabulary
      jobs/           # rollover CLI entrypoint
      core/           # settings, security, error envelope
    alembic/          # schema only; never seeds a Leave Type
    seed/             # inserts EL, CL, FL as data
    tests/
      domain/         # no database fixture
      integration/    # real PostgreSQL; concurrency tests
  frontend/
    src/
      api/            # typed client, TanStack Query hooks
      features/       # per-role surfaces
      components/
  docker-compose.yml
  .env.example
```

Create `tests/domain/` and `tests/integration/` now, even though only `tests/test_architecture.py` has content. `tests/domain/` runs with **no database fixture** (`SM-2`, `NFR-15`); `tests/integration/` runs against real PostgreSQL and will own `SM-1`'s concurrent double-submit test.

Naming conventions in force: DB tables/columns `snake_case`, tables **singular** (`employee`, `leave_request`); Python modules `snake_case`, SQLAlchemy models `PascalCase`, domain functions `verb_noun`; HTTP paths plural and kebab-case under `/api/v1`; React components `PascalCase`, hooks `useThing`.

### Pinned stack — every version verified against PyPI/npm on 2026-07-10

**Do not upgrade any of these.** Verified today: with the sole exception of TypeScript, *every pin below is the current latest release*. This stack is not stale, and a "helpful" upgrade is a regression.

| Name | Version | Note |
| --- | --- | --- |
| Python | 3.13 | Deliberately not 3.14 — library compatibility. |
| FastAPI | 0.139.0 | Current latest. Since 0.137.0, `router.routes` is a tree, not a flat `APIRoute` list. |
| Pydantic | 2.13.4 | Current latest stable. |
| pydantic-settings | 2.14.2 | Not pinned by the spine; requires `pydantic>=2.7`. |
| SQLAlchemy | 2.0.51 | **Hold the 2.0 line.** 2.1 is at `2.1.0b3` — still beta, `--pre` only. |
| Alembic | 1.18.5 | Since 1.18.2, `add_column()` no longer auto-inlines `PRIMARY KEY` unless `inline_primary_key=True`. |
| psycopg | 3.3.4 | psycopg **3**, not psycopg2. URL scheme is `postgresql+psycopg://`. |
| PostgreSQL | 18 | `uuidv7()` is a **native built-in** — no `pgcrypto`, no `uuid-ossp`, no `CREATE EXTENSION`. |
| PyJWT | 2.13.0 | Not `python-jose` (CVE-2024-33663, confirmed). `decode()` requires `algorithms=`. |
| pwdlib | 0.3.0 | Not `passlib` (last release 2020, broken against bcrypt 5 — confirmed). |
| bcrypt | 5.0.0 | See the 72-byte note below. |
| pytest | 9.1.1 | pytest 9.0 **errors** on sync tests consuming async fixtures. |
| React | 19.2.7 | `createRoot` from `react-dom/client` is still correct. |
| Vite | 8.1.4 | Rolldown-based. Requires Node `^20.19.0 \|\| >=22.12.0`. |
| TypeScript | 6.0.3 | **Last of the 6.x line.** 7.0.2 GA'd 2026-07-08 — see the trap above. |
| TanStack Query | 5.101.2 | Current latest. |

Version-specific facts you will need, gathered so you do not have to guess:

- **Vite 8 is Rolldown**, not Rollup+esbuild. `build.rollupOptions` → **`build.rolldownOptions`**; top-level `esbuild` config → **`oxc`**; `optimizeDeps.esbuildOptions` → `optimizeDeps.rolldownOptions`. `@vitejs/plugin-react` **6.0.3** is the matching plugin (peer: `vite ^8.0.0`).
- **TypeScript 6.0 changed defaults:** `strict` now defaults to `true`; `types` now defaults to `[]` (auto-discovery of `@types/*` is gone — list what you need); `module` defaults to `esnext`. Set `moduleResolution: "bundler"` **explicitly** for Vite rather than relying on inference, and prefer `verbatimModuleSyntax: true` so per-file transpilation can elide type-only imports safely.
- **psycopg 3** uses one driver name for sync and async: `create_engine("postgresql+psycopg://…")`. Prefer the non-binary install for a deployed environment — `psycopg[binary]` bundles a libpq that will not track system security updates.
- **pytest 9** errors (no longer warns) when a sync test depends on an `async def` fixture. This story needs no async tests: FastAPI's `TestClient` is synchronous. **Do not add `pytest-asyncio` in this story.** If a later story needs it, it must resolve to `>=1.x` (1.4.0 declares `pytest<10,>=8.4`).
- **Alembic:** with **zero** revision files, `alembic upgrade head` exits `0`, creates `alembic_version`, and leaves it **empty** — "head" resolves to nothing. With **one no-op revision**, it exits `0`, creates `alembic_version`, and **stamps it**. Use the no-op revision: it anchors `down_revision` for Story 1.2's first real migration, makes `alembic current` meaningful, and smoke-tests your `env.py` wiring. An empty `alembic_version` reads to deploy tooling as "never migrated."
- **Docker Compose:** the top-level `version:` key is obsolete and ignored. `condition: service_healthy` **errors** if the referenced service declares no `healthcheck:`. Pin the image (`postgres:18.4-bookworm`) rather than the floating `postgres:18` tag.

Two facts that belong to **Story 1.2** but bind the dependencies you install here, so you do not pin your way into a corner:

- `bcrypt` 5.0.0 **raises `ValueError`** for passwords over 72 bytes (4.x silently truncated). `pwdlib` does not catch it. Story 1.2 must validate length before hashing.
- `pwdlib` 0.3.0's `PasswordHash.recommended()` returns **Argon2**, not bcrypt. `AD-14` permits either. For bcrypt, construct explicitly: `PasswordHash((BcryptHasher(),))`, and install `pwdlib[bcrypt]`. Argument order is `verify(password, hash)`.

### Testing standards

`tests/domain/` runs with **no database fixture**. `tests/integration/` runs against real PostgreSQL. Every module names in its docstring the FR or DR it implements (`SM-6`).

`NFR-15` is explicit that coverage of CRUD scaffolding matters less than coverage of the hard rules. This story's *only* substantive tests are:

1. `test_architecture.py` — the import-direction contracts (AC2, AC3).
2. A `DomainError` raised in `services/` surfaces as `{ code, message, details }` with the right status (AC3).
3. A migration smoke test: after `alembic upgrade head`, `alembic_version` exists and no domain table does (AC6).

Do not chase coverage on `main.py` or the health endpoint. `SM-8` counts a requirement as delivered only when a consequence from its FR is demonstrably exercised by a passing test — and **this story implements no FR**. The readiness report records it as *"1.1 Project Foundation — no FR (expected)."*

### Known gap: F-14 (accepted, not a blocker)

AC2 requires that a violation *"fails the build rather than merely warning,"* and Story 1.2 requires a standing literal check that *"fails the build."* **No story establishes a CI pipeline.** `NFR-21` covers reproducible local setup, not CI, and Module 1 does not require it. The readiness report accepts this for a three-day trainee project.

Consequence for you: **`pytest` is the build.** Putting `lint_imports()` inside the test suite (Task 5) is what makes "fails the build" true today. Do not create a GitHub Actions workflow — no story asks for one, and it is not in the budget.

### Delivery context — read this before you start

The implementation budget is **three days total** (Days 3–5 of a seven-day plan; Days 1, 2, 6, 7 produce artifacts, not code) for **27 stories and 191 acceptance criteria**. The readiness report singles this story out: *"Story 1.1 alone carries 8 criteria spanning Docker, Alembic, TLS proxy, import-direction enforcement, dependency pinning, and a Vite/React/TanStack Query SPA shell."*

Counter-metric `SM-C1` governs: **when coverage and correctness compete, correctness wins, and the shortfall is declared.** For this story that means: the import-direction check (AC2) and the no-domain-table guarantee (AC6) are load-bearing for all 26 later stories and cannot be trimmed. The frontend shell (AC8) is the AC with slack in it — a responsive, TanStack-Query-wired SPA that renders a shell is sufficient; styling and a component library are **explicitly deferred by the spine**. Do not spend the day there.

### Project Structure Notes

- Greenfield repository. **Zero commits, no source code, no previous story.** Nothing to regress against and no established code pattern to follow — the spine's *Source tree* and *Consistency Conventions* are the only precedent, and this story creates it.
- No previous-story Dev Notes exist. Story 1.2 will be the first story able to learn from a predecessor.
- The `_bmad-output/` and `_bmad/` directories are planning artifacts, not application code. Application code goes in `backend/` and `frontend/` at the repository root.
- No `project-context.md` exists in this repository.

### Deliberate deferrals — do not build these

The spine and PRD defer the following. Adding any of them is scope creep against a three-day budget:

CI/CD · metrics and error monitoring · rate limiting · backup and disaster recovery · high availability · horizontal scalability · multi-tenancy (**no organization/tenant column exists on any table, ever**) · internationalization · WCAG conformance · React styling and component library · React state shape below the page level · charts and trend lines (`SM-C2`) · email delivery · PDF export · password reset/change/re-issue of any kind (`PRD §6`).

### References

- [epics.md#Story 1.1](../planning-artifacts/epics.md) — story statement, all 8 acceptance criteria, Epic 1 implementation notes
- [epics.md#Starter template](../planning-artifacts/epics.md) — the 🚨 no-template decision and its reasoning
- [ARCHITECTURE-SPINE.md#AD-1](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — dependency direction and the pure core
- [ARCHITECTURE-SPINE.md#AD-11](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — Leave Type is data; seeded by command, never by migration
- [ARCHITECTURE-SPINE.md#AD-21](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — one canonical vocabulary, declared once
- [ARCHITECTURE-SPINE.md#Stack](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — the pinned version table
- [ARCHITECTURE-SPINE.md#Structural Seed](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md) — deployment topology, source tree, consistency conventions
- [architecture.md#4.2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md) — why the skeleton is hand-rolled
- [architecture.md#3](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md) — layered-around-a-functional-core, and the rejected alternatives
- [architecture.md#10](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md) — operations: config from environment, seeding as data, observability
- [api-contracts.md#4.10](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — `GET /health`, anonymous; the rollover has no endpoint
- [api-contracts.md#2](../planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md) — the `{ code, message, details }` envelope and the twenty error codes
- [prd.md#9](../planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md) — constraints: three days of application code
- [prd.md#10](../planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md) — `SM-6`, `SM-8`, and counter-metric `SM-C1`
- [implementation-readiness-report-2026-07-10.md#F-14](../planning-artifacts/implementation-readiness-report-2026-07-10.md) — build-failing checks have no CI owner
- [implementation-readiness-report-2026-07-10.md#F-13](../planning-artifacts/implementation-readiness-report-2026-07-10.md) — the budget risk sits in Phase 1, not Phase 3

## Dev Agent Record

### Agent Model Used

`claude-opus-4-8[1m]` (Opus 4.8, 1M context)

### Debug Log References

**2026-07-10 — Environment assessment before Task 1. BLOCKED, awaiting user decision.**

`baseline_commit` recorded as `NO_COMMITS`: git is installed and the repository is
initialized, but `git rev-parse HEAD` fails with an unborn HEAD — there are zero commits.
Neither of the workflow's two cases (a SHA, or `NO_VCS` when version control is absent)
applies literally. The story's *Project Structure Notes* independently predicts this
("Greenfield repository. **Zero commits**"). `NO_COMMITS` is used as a self-describing
sentinel that cannot be mistaken for a SHA.

Two prerequisites named directly in the acceptance criteria are **absent from this machine**:

| Prerequisite | AC / Task that needs it | State on this machine |
| --- | --- | --- |
| Docker + `docker compose` | AC1, AC4, AC6; Tasks 6, 8, 10 | Not installed — no `docker`/`podman`/`colima` binary, no Docker.app, no OrbStack, daemon not running |
| Python 3.13 | AC7; Task 2 | Not installed — only Python 3.14.0 (Homebrew `python@3.14` + python.org framework) |

Consequences, stated precisely rather than worked around:

- AC1 (`docker compose up` → `alembic upgrade head` → seed → `GET /api/v1/health` = 200)
  cannot be executed, and Task 10 exists solely to execute it.
- AC4 (proxy terminates TLS in front of `web` and `api`, alongside `postgres:18`) says
  "when the deployed environment is **inspected**". A compose file can be authored blind;
  the topology cannot be inspected without a runtime.
- AC6 (after `alembic upgrade head`, `alembic_version` exists and no domain table does)
  requires a live PostgreSQL 18. The *Testing standards* section names this one of the
  story's only three substantive tests.
- AC7 requires Python 3.13 exactly. The spine pins it "deliberately not 3.14 — library
  compatibility", so running on the installed 3.14 would violate the AC it is written against.

Substituting SQLite for PostgreSQL, or 3.14 for 3.13, would produce a green test suite
against a stack the story explicitly forbids. Per workflow Step 8 ("NEVER mark a task
complete unless ALL conditions are met") and counter-metric `SM-C1` (correctness wins and
the shortfall is declared), the blocker is declared rather than routed around.

**Verified as NOT blocking** (checked 2026-07-10, network reachable):

- Every backend pin the story names is the current PyPI latest: FastAPI `0.139.0`,
  SQLAlchemy `2.0.51`, Alembic `1.18.5`, Pydantic `2.13.4`.
- Every frontend pin resolves on npm: React/React-DOM `19.2.7`, Vite `8.1.4`,
  `@tanstack/react-query` `5.101.2`, `@vitejs/plugin-react` `6.0.3`.
- The TypeScript 7 trap is real and current: `npm view typescript version` → `7.0.2`.
  `6.0.3` exists and is the last of the 6.x line (successor to `6.0.2`), confirming the
  story's instruction to pin it explicitly.
- Node v24.15.0 satisfies Vite 8's `engines.node` of `^20.19.0 || >=22.12.0`.
- Homebrew 6.0.6 offers `python@3.13` (3.13.14), `colima` (0.10.3), `docker` (29.6.1),
  `docker-compose` (5.3.0) — a headless path to a real `docker compose` with no
  Docker Desktop dependency.

No source files were created. No task checkbox was marked.

---

**2026-07-10 — Blocker RESOLVED by user decision. Implementation proceeded.**

Arpan chose `colima` + the Homebrew `docker` CLI (over Docker Desktop, avoiding its
commercial-licensing question) and a Homebrew `python@3.13` alongside the existing 3.14.
Installed: `python@3.13` (3.13.14), `colima` (0.10.3), `docker` (29.6.1),
`docker-compose` (5.3.0). The existing `python@3.14` and `postgresql@16` were left
untouched.

**Findings during implementation, recorded because a later story will hit them.**

1. **`postgres:18` moved its data directory.** A volume at `/var/lib/postgresql/data` —
   the convention through PostgreSQL 17 — is reported by the image as an *"unused
   mount/volume"* and the container refuses to become healthy. PGDATA now lives in a
   major-version subdirectory (`/var/lib/postgresql/18/docker`) so `pg_upgrade --link`
   need not cross a mount boundary. The mount is now `postgres_data:/var/lib/postgresql`.
   This is not in the story's *Pinned stack* notes; it cost one failed `compose up`.

2. **Port 5432 was already occupied** by a Homebrew `postgresql@16` service on this
   machine. Publishing the container there would have pointed host-run
   `alembic upgrade head` at whichever database answered first. `postgres` now publishes
   **5433**, and `DATABASE_URL` follows. The container still listens on 5432 internally.

3. **`api/v1/errors.py` cannot import `DomainError`.** Contract 2 forbids `app.api` from
   importing `app.domain`, and AC2 requires that to fail the build — but AC3 wants the
   handler in `api/`. Resolved by typing the handler structurally against a
   `DomainErrorLike` Protocol and performing the `add_exception_handler(DomainError, …)`
   binding in `app/main.py`, which names no layer and is outside every contract. Both
   criteria hold, and `lint-imports` proves it rather than a comment asserting it.

4. **The `layers` trap is real, and was confirmed empirically.** With a deliberate
   `from app.domain import vocabulary` added to `api/v1/health.py`, `lint-imports`
   reported `Layered architecture (AD-1) KEPT` while
   `api/ talks only to services/ (AD-1) BROKEN`. A developer who wrote only the `layers`
   contract would have had a green suite over an unenforced architecture, exactly as the
   Dev Notes warn.

5. **The first AD-11 guard was a regex, and it failed against its own docstrings.** The
   baseline migration discusses `op.bulk_insert()` in prose precisely in order to forbid
   it. Rewritten to walk the `ast`, where comments do not exist and docstrings are
   skipped explicitly. The test now also asserts that the guard *fires* on a real
   `bulk_insert` / `INSERT INTO` / `.insert()` — a guard that silently matches nothing
   would leave every future migration "passing".

6. **`docker compose` is not registered for Homebrew's `docker` CLI.** Homebrew installs
   the plugin to `/opt/homebrew/lib/docker/cli-plugins`, which the CLI does not search.
   Verification here used a session-scoped `DOCKER_CONFIG`; the persistent one-line fix
   is documented under *Prerequisites* in `README.md`. `~/.docker/config.json` was **not**
   modified — it is outside the project and was not part of what was approved.

**Deviation from AC1's literal command, stated plainly.** `docker compose up` was run as
`docker compose up -d` (detached) so that commands two and three could be issued against
the running stack in a non-interactive session. The detach flag changes when the command
returns, not what it builds or starts. Everything else ran verbatim, from
`docker compose down -v`.

### Completion Notes List

Story 1.1 is scaffolding, and it created **no domain table, no business rule, and no
user-facing feature** — which is the whole of what AC6 asserts. Its value is that the
next 26 stories now land in a structure where AD-1 cannot be violated by accident.

**What was built.** A hand-rolled four-package backend (`api`, `services`,
`repositories`, `domain`, plus the `core` leaf and `jobs`), a FastAPI app serving
`GET /api/v1/health`, one typed-exception hierarchy with a single `api/` handler and one
`code → status` map, an Alembic baseline revision that creates nothing, an idempotent
seed command that seeds nothing and exits `0`, a four-service Compose topology behind a
TLS-terminating proxy, and a Vite + React 19 + TypeScript 6.0.3 SPA shell with TanStack
Query and a typed API client. No starter template was used for the backend.

**How each AC was verified — by execution, not by inspection.**

| AC | Verified by | Result |
| --- | --- | --- |
| AC1 | `docker compose down -v` → `up` → `alembic upgrade head` → `python -m seed`, then HTTP | `GET /api/v1/health` → `200 {"status":"ok"}`; `GET /` → `200`, `<title>LeaveFlow</title>`, hashed JS asset `200`; deep link `/leave-requests/42` → `200` via SPA fallback. `.env` and `.env.example` declare an identical variable set (checked mechanically). |
| AC2 | `pytest` running `lint_imports()` | 5 contracts kept, 0 broken. Violations proven to **fail** the suite: `import sqlalchemy` in `domain/` → 1 failed; `api/ → domain/` → contract 2 BROKEN while `layers` stayed KEPT. |
| AC3 | `tests/test_error_envelope.py` (5 tests) | `DomainError` raised from a service-layer function through a throwaway route on a test-only app yields exactly `{code, message, details}`. Unmapped code → `500`, not `400`. The map is proven to be *consulted*, not merely defaulted. |
| AC4 | `curl -kv` + `docker compose ps` | TLS 1.3, ALPN `h2`, cert `CN=localhost`. `api` and `web` publish no host port and are reachable only through `proxy`, alongside `postgres:18.4-bookworm`. Plain HTTP to the TLS port → `400 The plain HTTP request was sent to HTTPS port`. |
| AC5 | Scan of all 361 git-visible files | `.env` ignored, `.env.example` committed. None of the three live secret values (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `SEED_ADMIN_PASSWORD`) appears in any committable file. No `BEGIN … PRIVATE KEY` anywhere. The proxy's key is generated at container start into a named volume. |
| AC6 | Live PostgreSQL 18.4 after `alembic upgrade head` | `public` schema contains `alembic_version` and **nothing else**; exactly one row, stamped `0001_baseline`. Asserted as set *equality*, so a table nobody thought to name is still caught. `tests/test_migrations_insert_nothing.py` statically forbids DML in every migration, now and forever. |
| AC7 | `importlib.metadata` **inside the api container** | Python `3.13.14`; FastAPI `0.139.0`, Pydantic `2.13.4`, pydantic-settings `2.14.2`, SQLAlchemy `2.0.51`, Alembic `1.18.5`, psycopg `3.3.4`, PyJWT `2.13.0`, pwdlib `0.3.0`, bcrypt `5.0.0`. `psycopg_binary` absent — the image uses system `libpq`, as the story prefers for a deployed environment. Frontend: `npx tsc --version` → `6.0.3`; React/React-DOM `19.2.7`, Vite `8.1.4`, TanStack Query `5.101.2`, all exact pins. |
| AC8 | `npm run build` (`tsc -b && vite build`), `npm run lint`, served bundle | Builds and lints clean. The served bundle contains `/api/v1` and `/health`, so the typed client survived the build. Responsive via a `48rem` breakpoint. |

**One honest gap on AC8.** The shell was verified as *built and served* — bundle returns
`200`, the SPA fallback works, and the JS contains the API path. It was **not** rendered
in a browser: no headless browser is installed, and adding one is a dependency this story
did not authorize. So "the React component tree mounts and `useHealth()` resolves" is
inferred from the passing build and the `200` from the same proxy the app calls, not
observed. The story's own delivery context names AC8 as the criterion with slack in it
and says not to spend the day there, so this is declared rather than closed.

**Deliberate omissions, all of them required.** `CODE_TO_STATUS` is empty and
`domain/vocabulary.py` is near-empty: this story implements no FR and creates no
enumerated value, so it has nothing to map. Story 1.2 fills both. No CI workflow was
created (F-14: `pytest` is the build). No metrics, no error monitoring, no
`pytest-asyncio`, no `scheduler` service, no documents volume, no styling library, no
auto-migrate service. `SM-8` counts this story as delivering no FR — as the readiness
report expects.

**One warning left standing.** starlette 1.3.1 deprecates `httpx` in `TestClient` in
favour of `httpx2`. It is a warning, not a failure, and `httpx` is not spine-governed —
drifting a dependency mid-story to silence it would have been the larger mistake. Worth a
line in Story 1.2.

**Declared deviation (recorded during code review, review P25).** Task 4's test raises
`DomainError` from `_service_that_refuses`, a stand-in defined inside
`tests/test_error_envelope.py`, not from a function in `app/services/` — which contains
only `__init__.py` because this story implements no service. A permanent service module
whose only reason to exist is to raise would be the same defect as the permanent route
Task 4 forbids. The mechanism is proven by the test; that `services/` cannot import HTTP
is proven structurally by contract 4. The subtask's literal condition — the raiser living
in `services/` — is unmet, and is declared here rather than reworded away.

**Post-review setup change (review D1, 2026-07-10).** AC1's commands two and three now
run as `docker compose exec api alembic upgrade head` and
`docker compose exec api python -m seed`. The originally documented flow created a host
venv inside "command two" — a fourth and fifth operator step requiring host Python 3.13,
which AC1's Given clause (a clean machine with Docker) does not grant. The venv remains
documented under *Tests*, where it genuinely is a prerequisite (pytest runs on the host).

**Post-review settings change (review D2, 2026-07-10).** `core/settings.py` now builds
`DATABASE_URL` from `POSTGRES_USER/PASSWORD/DB/HOST/PORT` with a URL-quoted password;
an explicit `DATABASE_URL` remains an optional override. `.env` therefore holds the
database password in exactly one place, and compose hands the api container parts, not a
hand-assembled URL. Placeholder (`CHANGE_ME*`) and empty secrets now fail validation at
startup instead of signing tokens quietly.

### File List

**Repository root**

- `.gitignore` (new)
- `.env.example` (new)
- `docker-compose.yml` (new)
- `README.md` (new)

**Backend**

- `backend/pyproject.toml` (new) — exact pins; the five `[tool.importlinter]` contracts
- `backend/Dockerfile` (new)
- `backend/.dockerignore` (new)
- `backend/alembic.ini` (new; `sqlalchemy.url` deliberately unset)
- `backend/alembic/env.py` (new)
- `backend/alembic/README` (new, from `alembic init`)
- `backend/alembic/script.py.mako` (new, from `alembic init`)
- `backend/alembic/versions/0001_baseline_baseline_no_domain_table_ac6_ad_11.py` (new)
- `backend/app/__init__.py` (new)
- `backend/app/main.py` (new)
- `backend/app/api/__init__.py` (new)
- `backend/app/api/v1/__init__.py` (new)
- `backend/app/api/v1/errors.py` (new)
- `backend/app/api/v1/health.py` (new)
- `backend/app/api/v1/router.py` (new)
- `backend/app/core/__init__.py` (new)
- `backend/app/core/logging.py` (new)
- `backend/app/core/settings.py` (new)
- `backend/app/domain/__init__.py` (new)
- `backend/app/domain/errors.py` (new)
- `backend/app/domain/vocabulary.py` (new)
- `backend/app/jobs/__init__.py` (new)
- `backend/app/repositories/__init__.py` (new)
- `backend/app/repositories/base.py` (new)
- `backend/app/services/__init__.py` (new)
- `backend/seed/__init__.py` (new)
- `backend/seed/__main__.py` (new)
- `backend/tests/test_architecture.py` (new)
- `backend/tests/test_error_envelope.py` (new)
- `backend/tests/test_health.py` (new)
- `backend/tests/test_migrations_insert_nothing.py` (new)
- `backend/tests/domain/conftest.py` (new)
- `backend/tests/integration/conftest.py` (new)
- `backend/tests/integration/test_migration_smoke.py` (new)

**Frontend**

- `frontend/package.json` (new; scaffold rewritten to exact pins)
- `frontend/package-lock.json` (new)
- `frontend/index.html` (new)
- `frontend/vite.config.ts` (new)
- `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json` (new)
- `frontend/.oxlintrc.json`, `frontend/.gitignore` (new, from scaffold)
- `frontend/Dockerfile` (new)
- `frontend/.dockerignore` (new)
- `frontend/nginx.conf` (new)
- `frontend/README.md` (new)
- `frontend/public/favicon.svg` (new, from scaffold)
- `frontend/src/main.tsx` (new)
- `frontend/src/App.tsx` (new)
- `frontend/src/index.css` (new)
- `frontend/src/api/client.ts` (new)
- `frontend/src/api/health.ts` (new)
- `frontend/src/api/queryClient.ts` (new)
- `frontend/src/api/index.ts` (new)
- `frontend/src/features/README.md` (new)
- `frontend/src/components/README.md` (new)

**Proxy**

- `proxy/Dockerfile` (new)
- `proxy/entrypoint.sh` (new)
- `proxy/nginx.conf` (new)

**Deleted (Vite scaffold artifacts, replaced)**

- `frontend/src/App.css`, `frontend/src/assets/` (`hero.png`, `react.svg`, `vite.svg`),
  `frontend/public/icons.svg`

Not committed, and correct: `.env` (gitignored), `backend/.venv/`,
`frontend/node_modules/`, `frontend/dist/`, `*.egg-info/`.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-10 | Story picked up; environment assessment found Docker and Python 3.13 absent. Blocker declared rather than worked around (`SM-C1`). |
| 2026-07-10 | Blocker resolved by user decision: colima + Homebrew `docker` CLI, and `python@3.13` alongside the existing 3.14. |
| 2026-07-10 | Implemented Tasks 1–10. Four-package backend skeleton, health endpoint, typed error envelope with one handler, five import-linter contracts enforced by `pytest`, no-op Alembic baseline, idempotent seed command, TLS Compose topology, Vite/React/TS SPA shell. |
| 2026-07-10 | Fixed: `postgres:18` requires its volume at `/var/lib/postgresql`, not `/var/lib/postgresql/data`. Found by a failing `compose up`, not by inspection. |
| 2026-07-10 | Fixed: published PostgreSQL on host port 5433 — 5432 was occupied by an existing `postgresql@16`, which host-run Alembic would otherwise have migrated. |
| 2026-07-10 | Fixed: the AD-11 migration guard was a regex that tripped over its own docstrings; rewritten as an AST walk that also proves it fires on a real `bulk_insert`. |
| 2026-07-10 | Fixed: `frontend/src/api/client.ts` spread `{details: {}, ...body}`, making the default dead; TypeScript caught it. `isErrorEnvelope` now narrows to a partial envelope and defaults `details`. |
| 2026-07-10 | All 10 tasks and 51 subtasks complete. 15 backend tests pass, 5 import contracts kept, frontend builds and lints clean. Three-command sequence proven from `docker compose down -v`. Status → review. |
| 2026-07-10 | Adversarial code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor): 55 raw findings → 37 after dedup; 8 dismissed, 2 deferred, 2 decisions resolved, 27 patches applied. See *Review Findings*. |
| 2026-07-10 | Review patches verified by execution: 16 backend tests pass (7 import contracts, new date-serialization regression test), frontend builds/lints clean, images rebuilt, exec-based three-command sequence run live, health 200, trailing-slash redirect now `https://…:8443` (uvicorn `--forwarded-allow-ips` + nginx `$http_host`). Status → done. |
