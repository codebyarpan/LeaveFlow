---
baseline_commit: f4e0b53103956ffe22ae01c58ba0b9e9ff07bc1f
---

# Story 2.1: Leave Types as Configuration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to define Leave Types and their attributes as data,
so that changing leave policy is configuration rather than a code change.

## Acceptance Criteria

1. **(Schema)** Given a database migrated by this story, when the schema is inspected, then `leave_type` carries `code`, `name`, `annual_entitlement`, `carries_forward`, a **nullable** `carry_forward_cap`, and `requires_supporting_document`, with `UNIQUE (code)` — and it is a **table**, never a PostgreSQL `ENUM` and never a Python `Enum` (`FR-06`, `AD-11`, `DR-11`).
2. **(Seed)** Given the seed command, when it runs, then `EL`, `CL` and `FL` exist, each with `requires_supporting_document` set to **false**; and **no Alembic migration inserts a Leave Type row** (`AD-11`, spine *Seeding*).
3. **(Create — SM-5)** Given an authenticated Admin, when they call `POST /api/v1/leave-types` with a fourth type, then it is created and returned by `GET /api/v1/leave-types`; and **no schema migration was required** (`SM-5`).
4. **(Read — any role)** Given any authenticated Employee of any role, when they call `GET /api/v1/leave-types`, then the response is `200` (any role, scope `all`, api-contracts §4.3).
5. **(Frontend — NFR-16)** Given the React application and an authenticated Admin, when they open the Leave Types screen, then they can view and create Leave Types and set each attribute; the create controls are rendered **only for the Admin role** (`NFR-16`).

### Acceptance criteria the ACs above imply (derived, non-negotiable — the story must leave the system correct, not merely satisfy the literal ACs)

6. **(No 500 on duplicate `code`)** A `POST /api/v1/leave-types` whose `code` already exists is refused with a typed **`409`**, not a raw `IntegrityError`/`500`. A constraint violation reaching a client is a defect (`AD-5`, mirrors the `EMAIL_ALREADY_IN_USE` precedent, `api-contracts §2`).
7. **(Non-Admin write → 403)** A non-Admin calling `POST /api/v1/leave-types` receives `403 ACTION_NOT_PERMITTED` **before** any row is written (`AD-14`; role gate at the boundary).
8. **(No token → 401)** Both endpoints, called with no/invalid token, return `401 TOKEN_INVALID`.
9. **(List is page-bounded)** `GET /api/v1/leave-types` returns the `{items, page, page_size, total}` envelope and honours the shared page-size clamp (`NFR-11`, reuse `api/v1/pagination.py`).

## Tasks / Subtasks

- [x] **Task 1 — `LeaveType` ORM model** (AC: 1)
  - [x] Add `class LeaveType(Base)` to `backend/app/repositories/models.py` with `__tablename__ = "leave_type"`.
  - [x] `id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))` — mirror `Department` exactly (PG18 native, no extension).
  - [x] Columns: `code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)`; `name: Mapped[str] = mapped_column(Text, nullable=False)`; `annual_entitlement: Mapped[int] = mapped_column(nullable=False)`; `carries_forward: Mapped[bool] = mapped_column(nullable=False)`; `carry_forward_cap: Mapped[int | None] = mapped_column(nullable=True)`; `requires_supporting_document: Mapped[bool] = mapped_column(nullable=False)`.
  - [x] Integer columns are plain `INTEGER` (SQLAlchemy `int` Mapped) — **never `NUMERIC`, never float** (ERD §4.1).
  - [x] Docstring names the requirements served (SM-6): `FR-06`, `AD-11`, `DR-11`, `SM-5`.
- [x] **Task 2 — Migration `0003_leave_type.py`** (AC: 1, 2)
  - [x] New file `backend/alembic/versions/0003_leave_type.py`, `revision="0003_leave_type"`, `down_revision="0002_department_and_employee"`, `branch_labels=None`, `depends_on=None`.
  - [x] `upgrade()` uses `op.create_table("leave_type", sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False), sa.Column("code", sa.Text(), nullable=False), sa.Column("name", sa.Text(), nullable=False), sa.Column("annual_entitlement", sa.Integer(), nullable=False), sa.Column("carries_forward", sa.Boolean(), nullable=False), sa.Column("carry_forward_cap", sa.Integer(), nullable=True), sa.Column("requires_supporting_document", sa.Boolean(), nullable=False), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("code", name="leave_type_code_key"))`.
  - [x] `downgrade()` drops the table.
  - [x] **INSERTS NOTHING.** No `op.bulk_insert`, no `op.execute("INSERT ...")`. (AC2 / AD-11 — enforced by `test_migrations_insert_nothing.py`.)
  - [x] Byte-for-byte agreement with the model: `alembic check` must emit an empty diff (enforced by `test_model_migration_agreement.py`). Generate/verify by running `alembic check` against the model, not by hand-guessing.
- [x] **Task 3 — Repository** (AC: 3, 4)
  - [x] New file `backend/app/repositories/leave_type.py` (module of plain functions, `session: Session` first — there is **no repository base class**).
  - [x] `list_leave_types(session, limit, offset) -> tuple[list[LeaveType], int]` — `select(...).order_by(LeaveType.code, LeaveType.id).limit(limit).offset(offset)` for the page + `select(func.count()).select_from(LeaveType)` for the total. Deterministic `ORDER BY` is mandatory.
  - [x] `get_leave_type(session, leave_type_id) -> LeaveType | None` — `session.get(LeaveType, id)`.
  - [x] `create_leave_type(session, *, code, name, annual_entitlement, carries_forward, carry_forward_cap, requires_supporting_document) -> LeaveType` — `session.add(...)` then `session.flush()` (assigns the server-default `id`); does **not** commit (the service owns the transaction).
  - [x] `code_exists(session, code) -> bool` (or equivalent) for the pre-write duplicate check (Task 5).
  - [x] Give `list_leave_types` and `get_leave_type` a "why exempt" docstring (scope-`all` reference read; returns no Employee-derived data) — see Task 8.
- [x] **Task 4 — Service** (AC: 3, 4, 6)
  - [x] New file `backend/app/services/leave_types.py` (plural filename, matching `services/departments.py`; the repo file is singular `leave_type.py`).
  - [x] `create_leave_type(...)` opens `with Session(get_engine(), expire_on_commit=False) as session:` (so the route can read `.id`/attrs after commit), pre-checks the duplicate `code`, calls the repo, `session.commit()`, returns the row. Wrap `commit()` with an `IntegrityError` backstop that rolls back and re-raises the typed 409 (mirror `services/employee.py`'s email pattern).
  - [x] `list_leave_types(limit, offset)` — thin read pass-through over a read session.
- [x] **Task 5 — Duplicate-code error wiring** (AC: 6)
  - [x] Add a new code constant `LEAVE_TYPE_CODE_IN_USE = "LEAVE_TYPE_CODE_IN_USE"` to `backend/app/domain/vocabulary.py` **and** to its `__all__` (AD-21: declared once, literal nowhere else).
  - [x] Map it to `409` in `backend/app/main.py`'s `CODE_TO_STATUS.update({...})` block.
  - [x] Service raises `DomainError(code=vocabulary.LEAVE_TYPE_CODE_IN_USE, message=..., details={"code": code})` on a duplicate.
  - [x] **Do NOT add `EL`/`CL`/`FL` to `vocabulary.py`** — those are seeded *data*, not constants (AD-11; see `vocabulary.py` comment block).
- [x] **Task 6 — API router** (AC: 3, 4, 7, 8, 9)
  - [x] New file `backend/app/api/v1/leave_types.py`, `router = APIRouter()`, `tags=["leave-types"]`.
  - [x] Inline Pydantic `LeaveTypeWriteRequest` (fields: `code: str`, `name: str`, `annual_entitlement: int`, `carries_forward: bool`, `carry_forward_cap: int | None = None`, `requires_supporting_document: bool`) and `LeaveTypeResponse` (all seven fields incl. `id: uuid.UUID`). Project the response by hand via a `_to_response(obj: object)` helper (api/ may not import the ORM model).
  - [x] `@router.post("/leave-types", status_code=status.HTTP_201_CREATED)` with `_admin: Actor = Depends(require_role(authz.ROLE_ADMIN))` → returns `LeaveTypeResponse` (201).
  - [x] `@router.get("/leave-types")` with `params: PageParams = Depends()` and `_caller: Actor = Depends(get_current_employee)` (authentication only, **not** `require_role`) → returns `Page[LeaveTypeResponse]`.
  - [x] Register the router in `backend/app/api/v1/router.py` (`from app.api.v1 import ... leave_types` + `api_v1_router.include_router(leave_types.router)`).
- [x] **Task 7 — Seed EL/CL/FL** (AC: 2)
  - [x] Extend `seed()` in `backend/seed/__main__.py`: import `LeaveType` from `app.repositories.models`; for each of `("EL", "Earned Leave"), ("CL", "Casual Leave"), ("FL", "Floater Leave")`, insert idempotently with `pg_insert(LeaveType).values(code=..., name=..., annual_entitlement=..., carries_forward=..., carry_forward_cap=..., requires_supporting_document=False).on_conflict_do_nothing(index_elements=["code"])` (matches the Admin-email idiom already in the file; the seed uses a Core `connection`, not an ORM `Session`).
  - [x] `requires_supporting_document=False` for all three (spine *Seeding*, PRD §7.3).
  - [x] Pick sensible seed values for `annual_entitlement` / `carries_forward` / `carry_forward_cap` — no artifact pins the exact numbers; **document the chosen values** in the Completion Notes so a reviewer can confirm they are project defaults, not invented policy. (`carry_forward_cap` may be `None` where `carries_forward` is false — it is meaningless there, ERD §6.)
  - [x] Update the seed docstring (the "What arrives later → Story 2.1" note) to reflect that this story delivered it.
  - [x] Do not use any `"EL"`/`"CL"`/`"FL"` literal outside the seed module in a way the literal scan would flag — the seed is the one place these data values live (they are data, not vocabulary).
- [x] **Task 8 — Satisfy the armed enforcement tests** (AC: 1, 2, 4)
  - [x] `backend/tests/test_scoped_getters.py`: add `"list_leave_types"` and `"get_leave_type"` to the `EXEMPT` frozenset (lines 68–77), with a comment marking them scope-`all` reference reads — the module docstring already anticipates "leave types and holidays follow in Epic 2, all api-contracts scope `all`".
  - [x] `backend/tests/test_migrations_insert_nothing.py`: extend the ordered-chain assertion (lines 121–124) to append `"0003_leave_type.py"`.
  - [x] Confirm `test_architecture.py` (7 import-linter contracts) and `test_vocabulary_literals.py` still pass — no new dependency, and the only new literal is the error code (in `vocabulary.py`).
- [x] **Task 9 — Backend tests** (AC: 1–4, 6–9)
  - [x] New `backend/tests/integration/test_leave_types.py` (mirror `test_departments.py`; **must `import app.main`** so `CODE_TO_STATUS` is populated). Cover: Admin POST creates & is returned by GET (201; AC3/SM-5); every role GETs the list (200; AC4); non-Admin POST → 403 `ACTION_NOT_PERMITTED`, no row written (AC7); no token → 401 `TOKEN_INVALID` on both (AC8); duplicate `code` → 409 `LEAVE_TYPE_CODE_IN_USE`, no second row (AC6); page-size clamp through the `Page` envelope (AC9); a created type carries `carry_forward_cap = null` when omitted (AC1 nullable).
  - [x] `backend/tests/integration/test_seed.py` (extend existing): after seed, `EL`/`CL`/`FL` exist with `requires_supporting_document = false`; re-running the seed changes nothing (idempotent, AC2).
- [x] **Task 10 — Frontend Leave Types screen** (AC: 5)
  - [x] New `frontend/src/api/leaveTypes.ts` (copy `api/departments.ts` shape): `LeaveType` + `CreateLeaveTypeInput` interfaces; `LEAVE_TYPES_QUERY_KEY = ['leaveTypes'] as const`; `useLeaveTypes()` → `apiFetch<Page<LeaveType>>('/leave-types')`; `useCreateLeaveType()` mutation POSTing `/leave-types` and invalidating the key on success. Reuse the `Page<T>` type from `api/departments.ts` (its single home).
  - [x] Re-export the surface from `frontend/src/api/index.ts`.
  - [x] New `frontend/src/features/leaveTypes/LeaveTypesPage.tsx`. **Gating = Pattern A (Departments):** the list renders for **any** authenticated role (GET is any-role); the create form + submit render only when `me.data?.role === ADMIN_ROLE` (NFR-16 is usability, never the guard — the server 403 is the boundary).
  - [x] Create form fields: `code` (text), `name` (text), `annual_entitlement` (number), `carries_forward` (checkbox → real boolean in state), `carry_forward_cap` (number, `disabled` when `!carries_forward`; `'' → null` at submit), `requires_supporting_document` (checkbox). Keep numeric/nullable fields as **strings** in form state and build the typed `CreateLeaveTypeInput` (numbers/null/booleans) inside the submit handler — mirror `EmployeesPage`'s `manager_id === '' ? null : ...` idiom. Reset via an `EMPTY_CREATE` constant on success.
  - [x] Server error → user message: a `writeErrorMessage(error: unknown)` helper that branches on `error instanceof ApiError` + `error.code` (restate `LEAVE_TYPES_*` codes as module constants), never on `error.message`. Render `<p className="emp-error" role="alert">…</p>`.
  - [x] Mount `<LeaveTypesPage />` in `AppShell`'s `<main>` in `frontend/src/App.tsx` (there is **no router** — pages are stacked panels; import near the other feature imports).
  - [x] Reuse existing CSS classes (`panel`, `emp-create`, `emp-fields`, `emp-field`, `emp-form-actions`, `emp-list`, `emp-row`, `emp-error`). Add a small scoped `leave-*` block in `index.css` only if the checkbox needs styling (no checkbox precedent exists).
- [x] **Task 11 — Prove it** (all ACs)
  - [x] Backend: from `backend/`, with the stack up (`docker compose up -d`), run `.venv/bin/python -m pytest` — all green (integration tests skip with a reason if no DB). `pytest` **is** the build; `lint-imports` runs inside it via `test_architecture.py`.
  - [x] Frontend: from `frontend/`, run `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean. There is **no frontend test runner**; the frontend proof is passing typecheck+lint+build plus a DECLARED manual click-through (Admin sees create form; non-Admin sees list only). State explicitly in Completion Notes whether the click-through was actually performed.

## Dev Notes

### Why this story is (almost) a copy of Story 1.5 (departments)

`leave_type` is an Admin-managed, organization-wide (`scope: all`) CRUD resource — the same shape as `department`. **Read `1-5-manage-departments.md` and the departments files as your template.** Three things differ and are where the work actually is:

1. **`UNIQUE (code)`** — departments has no unique constraint; `leave_type` does. So you need the **duplicate-guard pattern from `services/employee.py`** (pre-check + `IntegrityError` backstop + a typed 409), a new error code, and a `CODE_TO_STATUS` entry. (Departments needed none of this.)
2. **Boolean + nullable-integer columns** — departments is `{id, name}` only. `leave_type` has two booleans and a nullable int, which changes the migration column types, the Pydantic schema, and the frontend form controls (checkboxes, a `disabled`+nullable number).
3. **Seed rows** — departments seeds nothing new; this story seeds EL/CL/FL. Departments' AC set had no seed AC.

Everything else — the router shape, the `require_role(authz.ROLE_ADMIN)` vs `get_current_employee` split, `_to_response` hand-projection, `Page[...]` envelope, `expire_on_commit=False`, success codes (201 POST / 200 GET), the two armed enforcement tests, the frontend list+form+error-mapping — is identical to 1.5. Reuse, do not reinvent.

### Architecture compliance (guardrails — violating any of these fails `pytest`)

- **AD-11 / DR-11 / SM-5 — Leave Type is DATA, never an enum.** `leave_type` is a table row. It is never a Python `Enum`, never a PostgreSQL `ENUM`, and **no branch anywhere tests a Leave Type by name or code**. Attributes (`annual_entitlement`, `carries_forward`, `carry_forward_cap`, `requires_supporting_document`) are read at runtime. The three seed rows enter via the seed command, **never a migration**. Adding a fourth type must require no code change and no schema migration — that is the AC3/SM-5 acceptance. [Source: ARCHITECTURE-SPINE.md#AD-11; prd.md#FR-06; erd.md#1]
- **AD-1 — layering.** Imports flow `api → services → {repositories, domain}` and `repositories → domain`. `api/` never imports `repositories/` or `domain/` (that is why the router types `_to_response(obj: object)` and reaches role constants through `services.authorization as authz`, never `from app.domain.vocabulary`). `domain/` imports no ORM/web and does no I/O. Enforced by import-linter (7 contracts, `test_architecture.py`). [Source: ARCHITECTURE-SPINE.md#AD-1]
- **Transaction boundary.** Only `services/` opens transactions (`with Session(get_engine(), expire_on_commit=False)`). Only `repositories/` issues SQL. The repo `flush()`es (never commits); the service commits. [Source: ARCHITECTURE-SPINE.md#Design Paradigm; services/departments.py]
- **AD-5 — no constraint violation reaches a client as a 500.** A duplicate `code` must be a typed 409, not a raw `IntegrityError`. Pre-check in the service; keep the DB `UNIQUE` as a backstop with a rollback+re-raise around `commit()`. [Source: models.py:57; api-contracts.md#2 `EMAIL_ALREADY_IN_USE`]
- **AD-21 — canonical vocabulary.** Every enumerated string / error `code` is `UPPER_SNAKE_CASE`, declared once in `domain/`, and appears as a literal nowhere else (`test_vocabulary_literals.py` scans `app/` + `seed/`). The only new one here is `LEAVE_TYPE_CODE_IN_USE`. EL/CL/FL are **data**, not vocabulary. [Source: ARCHITECTURE-SPINE.md#AD-21; vocabulary.py]
- **AD-10 / scope.** `GET /leave-types` is scope `all` (organization-wide reference data), so no per-actor row scoping applies — but the scoped-getter guardrail (`test_scoped_getters.py`) will flag `list_leave_types`/`get_leave_type` on name alone. Resolve by adding them to `EXEMPT` **with a rationale docstring** (they return no Employee-derived data), exactly as Story 1.5 did for departments. Do **not** bolt on an unused `actor` param. [Source: test_scoped_getters.py:9-30]
- **AD-14 / NFR-16 — the client renders authority; only the server enforces it.** The frontend hides the create form from non-Admins for usability; the real access control is the server's `403` on `POST /leave-types`. [Source: ARCHITECTURE-SPINE.md#AD-14; prd.md#NFR-16]

### Exact schema (ERD §2, §4)

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT uuidv7()` (PG18 native, no extension) | time-ordered, non-enumerable |
| `code` | `TEXT` | `NOT NULL`, `UNIQUE (code)` | EL/CL/FL seeded as data; a fourth added via API |
| `name` | `TEXT` | `NOT NULL` | e.g. FL = "Floater Leave" |
| `annual_entitlement` | `INTEGER` | `NOT NULL` | Leave Days for a full year; the base Proration reduces (never `NUMERIC`/float) |
| `carries_forward` | `BOOLEAN` | `NOT NULL` | read at runtime; no branch tests a type by name |
| `carry_forward_cap` | `INTEGER` | **NULLABLE** | max carried across the boundary; meaningless (and null) when `carries_forward` is false |
| `requires_supporting_document` | `BOOLEAN` | `NOT NULL` | seeded **false** for EL/CL/FL |

[Source: module-4-erd/erd.md#2 Logical model, §4.1 Keys and types, §4.2 Constraints, §6]

### API contract (api-contracts §4.3)

| Method | Path | Role | Scope | Success | Realizes |
|---|---|---|---|---|---|
| `POST` | `/api/v1/leave-types` | Admin | all | `201` | FR-06, SM-5 |
| `GET` | `/api/v1/leave-types` | any | all | `200` | FR-06 |

- Base path `/api/v1`; paths plural, kebab-case (`leave-types`; table stays `leave_type`).
- **Per-field request/response schemas are NOT pinned in the contract docs** — the FastAPI-generated OpenAPI at `/docs` is the runtime source of truth. Derive the body from the columns above (`id` is server-generated). [Source: api-contracts.md#0, #5]
- Error envelope (every non-2xx): `{ "code", "message", "details" }`. List envelope: `{ items, page, page_size, total }`. Enumerated values transported `UPPER_SNAKE_CASE` verbatim. [Source: api-contracts.md#1, #2]
- Status semantics: `401` no/invalid token (`TOKEN_INVALID`); `403` role-denied (`ACTION_NOT_PERMITTED`); `409` state conflict (use for duplicate `code`). [Source: api-contracts.md#1]
- Out of scope for this story (same resource, later): `PATCH /leave-types/<id>` (requires `RECALCULATE`/`PRESERVE` disposition → `policy_change`) and `GET /policy-changes`. Do not build them here; do not let them influence the create/list schema.

### Library / framework requirements (pinned — do NOT upgrade)

Python `3.13.*`; FastAPI `0.139.0`; Pydantic `2.13.4`; SQLAlchemy `2.0.51`; Alembic `1.18.5`; psycopg `3.3.4`; PostgreSQL `18`; pytest `9.1.1`; import-linter `2.13`. Frontend: React `19.2.7`, Vite `8.1.4`, TypeScript `6.0.3`, TanStack Query `5.101.2`. No new dependency is needed for this story. [Source: pyproject.toml; frontend/package.json; ARCHITECTURE-SPINE.md#Stack]

### File structure (what to create / edit)

**New (backend):** `app/repositories/leave_type.py`, `app/services/leave_types.py`, `app/api/v1/leave_types.py`, `alembic/versions/0003_leave_type.py`, `tests/integration/test_leave_types.py`, plus `LeaveType` added to `app/repositories/models.py`.
**Edit (backend):** `app/domain/vocabulary.py` (new code + `__all__`), `app/main.py` (`CODE_TO_STATUS`: `LEAVE_TYPE_CODE_IN_USE → 409`), `app/api/v1/router.py` (register router), `seed/__main__.py` (EL/CL/FL), `tests/test_scoped_getters.py` (EXEMPT), `tests/test_migrations_insert_nothing.py` (chain list), `tests/integration/test_seed.py` (seed assertions).
**New (frontend):** `src/api/leaveTypes.ts`, `src/features/leaveTypes/LeaveTypesPage.tsx`.
**Edit (frontend):** `src/api/index.ts` (re-export), `src/App.tsx` (mount page), `src/index.css` (only if the checkbox needs a scoped class).

Naming: modules `snake_case`; SQLAlchemy models `PascalCase` (`LeaveType`); table singular (`leave_type`); service file plural (`leave_types.py`), repo file singular (`leave_type.py`) — matching the departments precedent. React components `PascalCase`, hooks `useThing`. [Source: ARCHITECTURE-SPINE.md#Source tree, Consistency Conventions]

### Testing requirements

- `tests/domain/` runs with **no database**; `tests/integration/` runs against **real PostgreSQL** (skips with a reason if the stack is down). This story is all integration (schema + endpoints + seed) — there is no pure-domain logic to add here. [Source: ARCHITECTURE-SPINE.md#Testing]
- Integration tests **must `import app.main`** to populate `CODE_TO_STATUS` (else a domain code falls through to 500). Use the `callers` fixture pattern from `test_departments.py` (one Employee per role, token via `security.create_token(str(id), role)`, committed so the app's connection sees it). [Source: tests/integration/test_departments.py]
- `pytest` is the build (no CI). The import-linter contracts and the AST migration guard run **inside** the suite; a layering break or a migration `insert` fails `pytest`, not a separate step. [Source: README.md#Tests]
- Model↔migration agreement: run `alembic check` (via `test_model_migration_agreement.py`) — an empty diff is required. Do not hand-author the migration and hope it matches; verify.

### Previous story intelligence (Story 1.5 — the direct twin — and 1.6/1.8)

- **`PageParams` gotcha (1.5 Debug Log):** declare query params as `Annotated[int, Query(...)] = 1`, **not** `= Query(default=1, ...)` — the bare-`Query` form leaves the runtime default a `Query` marker and breaks DB-free construction. You are *reusing* `pagination.py` unchanged, so this is already fixed; do not re-introduce it if you touch that file.
- **1.5 Trap 1 (scoped-getter guardrail) is the template** for Task 8's EXEMPT edit — it added `list_departments`/`get_department` and broadened the docstring rather than silencing. Do the same for the two leave-type getters. `code_exists`/`count_`-style helpers returning a `bool`/`int` are not `get_/list_/find_/fetch_`-prefixed, so they are correctly not candidates.
- **1.5 Trap 5 / G6 (success codes):** 201 POST / 200 GET, matched by the React hooks — reuse verbatim.
- **1.6 (employees) is the pattern for the duplicate-`code` 409** — see `services/employee.py`'s `EMAIL_ALREADY_IN_USE`: pre-check conflicts, and wrap `commit()` in a `try/except IntegrityError: rollback(); raise typed 409`.
- **Frontend proof reality (1.5/1.6/1.8):** there is no frontend test runner. The proof is `npm run build` + `npm run lint` clean, plus a **declared** manual click-through. Prior stories flagged when the click-through was not actually performed — do the same honestly.

### Git intelligence

Recent commits (`feat(story-1.5)` … `feat(story-1.8): edit own profile`) established: the departments CRUD stack (1.5) that this story clones; employee create with `EMAIL_ALREADY_IN_USE` (1.6) that models the duplicate-`code` guard; `PATCH /me` with `FORBIDDEN_FIELD`/`INVALID_NAME` validation codes (1.8) showing the current vocabulary+`CODE_TO_STATUS` wiring convention. Head migration is `0002_department_and_employee`; your migration chains off it as `0003`.

### Project structure notes

No structural conflicts. Every path above already exists as a sibling of an equivalent departments/employees file; you are adding one more resource to established `api/`, `services/`, `repositories/`, `alembic/versions/`, `seed/`, `tests/`, and `frontend/src/{api,features}/` locations. The one novelty — a checkbox control — has no precedent, so a small scoped CSS addition is in keeping with the per-screen style if needed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: Leave Types as Configuration]
- [Source: _bmad-output/planning-artifacts/module-4-erd/erd.md#2 Logical model, #4 Physical model, #6]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md#1 Conventions, #2 Error envelope, #4.3]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-1, #AD-10, #AD-11, #AD-14, #AD-21, #Stack, #Source tree, #Seeding]
- [Source: _bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md#FR-06, #DR-11, #SM-5, #NFR-16, #7.3]
- [Source: backend/app/api/v1/departments.py — router/schema/authz/success-code template]
- [Source: backend/app/services/employee.py — duplicate (EMAIL_ALREADY_IN_USE) 409 pattern]
- [Source: backend/seed/__main__.py — idempotent Core-connection seed with on_conflict_do_nothing]
- [Source: backend/tests/test_scoped_getters.py:68-77 — EXEMPT registry; backend/tests/test_migrations_insert_nothing.py:121-124 — chain list]
- [Source: frontend/src/features/departments/DepartmentsPage.tsx, frontend/src/api/departments.ts, frontend/src/api/client.ts — frontend template]
- [Source: _bmad-output/implementation-artifacts/1-5-manage-departments.md — the twin story's Dev Agent Record]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — BMad dev-story workflow.

### Debug Log References

- `alembic current` → `0003_leave_type (head)`; `alembic check` → "No new upgrade operations detected" (model↔migration byte-agreement, Task 2/AC1).
- First full `pytest`: 3 failures, all pre-existing Story 1.2 schema-snapshot guardrails that were **deliberately armed** to fire when `leave_type` shipped —
  `test_schema_1_2.py::test_exactly_department_employee_and_alembic_version_exist` (exact table-set), `test_migration_smoke.py::test_alembic_version_exists_and_is_stamped_at_head` (`HEAD_REVISION` was `0002`), and `test_migration_smoke.py::test_no_leave_type_row_was_inserted_by_a_migration` (asserted the table did not yet exist). Updated to the new head/schema (see Completion Notes). Re-run: **211 passed**.
- Frontend: `npm run build` (`tsc -b && vite build`) clean (78 modules, LeaveTypesPage bundled); `npm run lint` (oxlint) clean.

### Completion Notes List

**What was implemented (all 5 literal ACs + 4 derived ACs):**
- `LeaveType` ORM model + migration `0003_leave_type` (7 columns, `UNIQUE (code)`, native `uuidv7()`, nullable `carry_forward_cap`), model↔migration verified by `alembic check` (AC1). Migration **inserts nothing** (AC2/AD-11).
- Repository (`repositories/leave_type.py`), service (`services/leave_types.py`) with the duplicate-`code` pre-check + `IntegrityError` backstop → typed `409 LEAVE_TYPE_CODE_IN_USE` (AC6/AD-5, mirroring `EMAIL_ALREADY_IN_USE`).
- Router (`api/v1/leave_types.py`): `POST /leave-types` Admin-only `201` (AC3/SM-5), `GET /leave-types` any-role `200`, page-bounded envelope (AC4/AC9); `403` before any write for non-Admin (AC7), `401 TOKEN_INVALID` with no token (AC8). Registered in `api/v1/router.py`.
- Seed EL/CL/FL as data, idempotent `ON CONFLICT (code) DO NOTHING`, all `requires_supporting_document=false` (AC2).
- Frontend: `api/leaveTypes.ts` hooks (reusing `Page<T>`), `LeaveTypesPage.tsx` (Pattern A — list any-role, create form Admin-only via `useMe`), mounted in `App.tsx`; scoped `.leave-check` CSS for the checkbox control (AC5/NFR-16).

**Seed policy values (Task 7 — no artifact pins the numbers; these are project defaults, not invented policy, documented for the reviewer):**
- EL (Earned Leave): `annual_entitlement=12`, `carries_forward=true`, `carry_forward_cap=30`.
- CL (Casual Leave): `annual_entitlement=12`, `carries_forward=false`, `carry_forward_cap=NULL`.
- FL (Floater Leave): `annual_entitlement=2`, `carries_forward=false`, `carry_forward_cap=NULL`.
- All three `requires_supporting_document=false`. `carry_forward_cap` is `NULL` where `carries_forward=false` (meaningless there, ERD §6).

**Armed-guardrail updates (Task 8 + two Story 1.2 snapshots the story list did not enumerate but the DoD requires green):**
- `test_scoped_getters.py`: added `list_leave_types`/`get_leave_type` to `EXEMPT` with rationale (scope-`all` reference reads, not Employee-derived).
- `test_migrations_insert_nothing.py`: appended `0003_leave_type.py` to the ordered revision chain.
- `test_schema_1_2.py`: added `leave_type` to the exact table-set (grows one table per schema story, as the revision chain grows one file per story).
- `test_migration_smoke.py`: bumped `HEAD_REVISION` to `0003_leave_type`; **repointed** the ex-tripwire test (which asserted the table did not exist) to a live-catalog smoke that `leave_type` shipped with its seven columns + `UNIQUE (code)`. AD-11 row-provenance stays enforced statically (`test_migrations_insert_nothing.py`) and at the seed layer (`test_seed.py`), so the change does not weaken the guarantee.
- `test_architecture.py` (7 import-linter contracts) and `test_vocabulary_literals.py` pass unchanged — the only new literal is the error code, declared in `vocabulary.py`.

**Proof (Task 11):**
- Backend — **authoritative**: `pytest` **211 passed** against real PostgreSQL (docker stack up), incl. all AC1–AC9 coverage in `tests/integration/test_leave_types.py` + `test_seed.py`, the import-linter contracts, and the migration AST guard. `pytest` is the build (README).
- Frontend: `tsc -b && vite build` and `oxlint` both clean.
- **Manual browser click-through: NOT performed.** Consistent with the honest declaration prior stories (1.5/1.6/1.8) made — this project has no frontend test runner or browser-automation harness, and the running containers are stale (built ~42h before this work). The frontend behaviour is proven by typecheck+lint+build and by the backend contract the screen consumes being fully integration-tested; a live click-through against a rebuilt stack is left for review/QA.

### File List

**New (backend):**
- `backend/app/repositories/leave_type.py`
- `backend/app/services/leave_types.py`
- `backend/app/api/v1/leave_types.py`
- `backend/alembic/versions/0003_leave_type.py`
- `backend/tests/integration/test_leave_types.py`

**Edit (backend):**
- `backend/app/repositories/models.py` (added `LeaveType`)
- `backend/app/domain/vocabulary.py` (`LEAVE_TYPE_CODE_IN_USE` + `__all__`)
- `backend/app/main.py` (`CODE_TO_STATUS`: `LEAVE_TYPE_CODE_IN_USE → 409`)
- `backend/app/api/v1/router.py` (register `leave_types.router`)
- `backend/seed/__main__.py` (seed EL/CL/FL, `_SEED_LEAVE_TYPES`)
- `backend/tests/test_scoped_getters.py` (`EXEMPT` += two getters)
- `backend/tests/test_migrations_insert_nothing.py` (revision chain += `0003`)
- `backend/tests/integration/test_seed.py` (EL/CL/FL seed assertions)
- `backend/tests/integration/test_schema_1_2.py` (table-set += `leave_type`)
- `backend/tests/integration/test_migration_smoke.py` (`HEAD_REVISION` = `0003`; repointed leave-type smoke)

**New (frontend):**
- `frontend/src/api/leaveTypes.ts`
- `frontend/src/features/leaveTypes/LeaveTypesPage.tsx`

**Edit (frontend):**
- `frontend/src/api/index.ts` (re-export leave-types surface)
- `frontend/src/App.tsx` (mount `<LeaveTypesPage />`)
- `frontend/src/index.css` (scoped `.leave-check` checkbox block)

## Change Log

| Date | Version | Description |
|---|---|---|
| 2026-07-13 | 0.1 | Implemented Story 2.1 (Leave Types as Configuration): `leave_type` table + migration `0003`, repository/service/router, duplicate-`code` 409 wiring, EL/CL/FL seed, frontend screen, and full backend integration tests. Updated four armed schema/guardrail tests to the new head. Backend `pytest` 211 passed; frontend build+lint clean. Status → review. |

## Review Findings

_Code review 2026-07-13 (parallel adversarial: Blind Hunter + Edge Case Hunter + Acceptance Auditor). No AC violations found; all 9 ACs satisfied. Findings below concern correctness/robustness beyond the literal ACs._

- [x] [Review][Patch] **Duplicate-`code` `IntegrityError` backstop is dead code for its stated purpose** [backend/app/services/leave_types.py:86-92] — The `try/except IntegrityError` wraps only `session.commit()`, but the `UNIQUE (code)` violation surfaces at `session.flush()` inside `repositories/leave_type.py:103` (the flush emits the INSERT). In the concurrent TOCTOU case (two Admins POST the same new `code` at once), the second flush raises `IntegrityError` *outside* the try, so the client gets a raw **500** instead of the typed **409 LEAVE_TYPE_CODE_IN_USE** the AD-5 docstring promises. **Resolution (Decision 1 → option 2):** move the repo `create` call inside the `try` here AND apply the identical fix to `services/employee.py:create_employee` (same latent flaw, `EMAIL_ALREADY_IN_USE`) to keep the pattern correct codebase-wide. (`update_employee` and `delete_department` are already correct — their SQL emits at commit, not an early flush.)
- [x] [Review][Patch] **`create_employee` UNIQUE(email) backstop has the same flush-vs-commit gap** [backend/app/services/employee.py:187-207] — `employee_repo.create_employee` flushes (`repositories/employee.py:241`) before the `try/except` that wraps only `commit()`, so a concurrent duplicate email surfaces as a raw 500 instead of `409 EMAIL_ALREADY_IN_USE`. Fixed alongside the leave-types fix (Decision 1 → option 2).
- [x] [Review][Patch] **AC8 test covers only the absent-token path, not an invalid/malformed one** — `test_both_endpoints_are_401_without_a_token` [backend/tests/integration/test_leave_types.py] exercises only a missing token; AC8/the api-contract wording is "no/**invalid** token." Implementation handles both; add a malformed/garbage-token assertion to close the coverage gap.
- [x] [Review][Defer] **No server-side content validation of the write body** [backend/app/api/v1/leave_types.py:45-53] — deferred (Decision 2 → option 1). Consistent with the 1.5/1.6 deferrals; folds into the pending enveloped-validation contract decision (a raw Pydantic 422 bypasses the NFR-17 `{code,message,details}` envelope). Gaps: (a) empty/whitespace `code`/`name` accepted; (b) `annual_entitlement ≤ 0` accepted — a bad day-count for Epic 2 balance math; (c) INT32-overflow → `DataError` → raw 500; (d) `carry_forward_cap` set while `carries_forward=false` (ERD §6 meaningless); (e) case/whitespace-sensitive `code` uniqueness (`el` vs `EL`).
- [x] [Review][Defer] **Frontend leave-types list is not paginated** [frontend/src/api/leaveTypes.ts:54-59] — deferred, pre-existing app-wide pattern. `useLeaveTypes()` fetches page 1 only (page_size 50) with no next/prev control, so a 51st+ leave type is invisible in the UI. Matches the accepted Departments/Employees pattern; leave types are inherently few.

_Dismissed as noise (2): frontend `type="number"` accepts non-integers → Pydantic `int` returns a raw 422 outside the error envelope (cosmetic; server rejects correctly and `min="0"` is already set); `get_leave_type` repo function is unused (spec-mandated by Task 3 and registered in the scoped-getter EXEMPT list — compliant by instruction)._
