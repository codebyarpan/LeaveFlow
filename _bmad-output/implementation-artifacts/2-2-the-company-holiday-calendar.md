---
baseline_commit: f4e0b53103956ffe22ae01c58ba0b9e9ff07bc1f
---

# Story 2.2: The Company Holiday Calendar

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want to maintain the calendar of days the organization does not work,
so that no Employee spends leave on a day nobody was working anyway.

## Acceptance Criteria

**Literal ACs (from epics.md#Story 2.2):**

1. **(Schema)** Given a database migrated by this story, when the schema is inspected, then `company_holiday` carries `holiday_date` of type `DATE` and `name`, with `UNIQUE (holiday_date)`; and **no column scopes a holiday to a Department or a location** — the calendar is global (`FR-10`, ERD §3).
2. **(DATE, not timestamp)** Given a Company Holiday, when it is stored, compared or transported, then it is a calendar `DATE` and never a `TIMESTAMPTZ`, and the API transports it as `YYYY-MM-DD` (`AD-12`, `DR-2a`).
3. **(Endpoints)** Given an authenticated Admin, when they call `POST /api/v1/holidays` or `DELETE /api/v1/holidays/<id>`, then the holiday is added or removed; **and any authenticated role may call `GET /api/v1/holidays`** (api-contracts §4.3).
4. **(Frontend — NFR-16)** Given the React application and an authenticated Admin, when they open the Holidays screen, then they can add and delete holidays for a Leave Year; the add/delete controls render **only for the Admin role**.

**Derived ACs (implied, non-negotiable — the story must leave the system correct, not merely satisfy the literal ACs):**

5. **(No 500 on duplicate date)** A `POST /api/v1/holidays` whose `holiday_date` already exists is refused with a typed **`409 HOLIDAY_DATE_IN_USE`**, not a raw `IntegrityError`/`500`. A constraint violation reaching a client is a defect (`AD-5`, mirrors the `LEAVE_TYPE_CODE_IN_USE` precedent, api-contracts §2).
6. **(Non-Admin write → 403)** A non-Admin calling `POST /api/v1/holidays` **or** `DELETE /api/v1/holidays/<id>` receives `403 ACTION_NOT_PERMITTED` **before** any row is written or deleted (`AD-14`; role gate at the boundary).
7. **(No token → 401)** All three endpoints, called with no/invalid token, return `401 TOKEN_INVALID`.
8. **(Delete of a nonexistent id → 404)** `DELETE /api/v1/holidays/<id>` for an id that names no row is `404 RESOURCE_NOT_FOUND` — the byte-identical not-found the scope convention raises (`AD-10`), never a silent success or a 500.
9. **(List is page-bounded)** `GET /api/v1/holidays` returns the `{items, page, page_size, total}` envelope and honours the shared page-size clamp (`NFR-11`, reuse `api/v1/pagination.py`).
10. **(Frontend controls are Admin-only, list is any-role)** The Holidays list renders for **any** authenticated role; the add form and the per-row delete controls render only when the caller is Admin (`NFR-16` — Pattern A, exactly like Departments/Leave Types). NFR-16 is usability; the server `403` is the boundary (AC6).

## Tasks / Subtasks

- [x] **Task 1 — `CompanyHoliday` ORM model** (AC: 1, 2)
  - [x] Add `class CompanyHoliday(Base)` to `backend/app/repositories/models.py` with `__tablename__ = "company_holiday"`.
  - [x] `id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))` — mirror `Department`/`LeaveType` exactly (PG18 native `uuidv7()`, no extension).
  - [x] `holiday_date: Mapped[datetime.date] = mapped_column(nullable=False, unique=True)` — **`datetime.date`, never `datetime.datetime`**. SQLAlchemy maps `date → DATE` (the exact precedent is `Employee.joining_date` in this same file); `datetime` would map to `TIMESTAMP` and violate AC2/AD-12. `datetime` is already imported at the top of `models.py`.
  - [x] `name: Mapped[str] = mapped_column(Text, nullable=False)`.
  - [x] **No `department_id`, no `location`, no scope column of any kind** — the calendar is global (AC1, ERD §3: "COMPANY_HOLIDAY stands alone by design … scoped to no Department or location"). Do not add a relationship.
  - [x] Docstring names the requirements served (SM-6): `FR-10`, `AD-12`, `DR-2a`, `DR-1`. Note that `UNIQUE (holiday_date)` is the AD-5 backstop behind the duplicate-date 409, mirroring `LeaveType`'s `UNIQUE (code)` docstring.
- [x] **Task 2 — Migration `0004_company_holiday.py`** (AC: 1, 2)
  - [x] New file `backend/alembic/versions/0004_company_holiday.py`, `revision="0004_company_holiday"`, `down_revision="0003_leave_type"`, `branch_labels=None`, `depends_on=None`.
  - [x] `upgrade()` uses `op.create_table("company_holiday", sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False), sa.Column("holiday_date", sa.Date(), nullable=False), sa.Column("name", sa.Text(), nullable=False), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("holiday_date", name="company_holiday_holiday_date_key"))` — `sa.Date()`, NOT `sa.DateTime()` (AC2).
  - [x] `downgrade()` drops the table.
  - [x] **INSERTS NOTHING.** No `op.bulk_insert`, no `op.execute("INSERT ...")` — the calendar starts empty and the Admin populates it via the API (enforced by `test_migrations_insert_nothing.py`, which parses this file's AST).
  - [x] Byte-for-byte agreement with the model: `alembic check` must emit an empty diff (enforced by `test_model_migration_agreement.py`). **Verify by running `alembic check` against the model, not by hand-guessing** — the `UNIQUE` constraint name in particular must match what SQLAlchemy derives from `unique=True` (the `_key` suffix, exactly as `0003` did for `leave_type_code_key`).
- [x] **Task 3 — Repository** (AC: 3, 5, 8, 9)
  - [x] New file `backend/app/repositories/holiday.py` (module of plain functions, `session: Session` first — there is **no repository base class**). Mirror `repositories/leave_type.py`.
  - [x] `list_holidays(session, limit, offset) -> tuple[list[CompanyHoliday], int]` — `select(...).order_by(CompanyHoliday.holiday_date, CompanyHoliday.id).limit(limit).offset(offset)` for the page + `select(func.count()).select_from(CompanyHoliday)` for the total. Order by `holiday_date` (a calendar reads chronologically); `id` is the deterministic tiebreaker. Deterministic `ORDER BY` is mandatory.
  - [x] `get_holiday(session, holiday_id) -> CompanyHoliday | None` — `session.get(CompanyHoliday, id)` (the DELETE's load-or-404 input, AC8).
  - [x] `create_holiday(session, *, holiday_date, name) -> CompanyHoliday` — `session.add(...)` then `session.flush()` (assigns the server-default `id`); does **not** commit (the service owns the transaction).
  - [x] `holiday_date_exists(session, holiday_date) -> bool` for the pre-write duplicate check (Task 5). Named with neither a read-verb prefix nor a row return (answers a `bool`) so it is correctly NOT a scoped-getter candidate.
  - [x] `delete_holiday(session, holiday) -> None` — `session.delete(holiday)` on an already-loaded row (the service loads-or-404s first). **No emptiness guard** — `company_holiday` stands alone with no FK dependents in this epic (ERD §3), so a delete is unconditional beyond the 404. (Recalculation of existing requests on a holiday change lands in Story 2.11, not here.)
  - [x] Give `list_holidays` and `get_holiday` a "why exempt" docstring (scope-`all` reference read; returns no Employee-derived data) — see Task 8.
- [x] **Task 4 — Service** (AC: 3, 5, 8)
  - [x] New file `backend/app/services/holidays.py` (plural filename, matching `services/leave_types.py`/`services/departments.py`; the repo file is singular `holiday.py`). Mirror `services/leave_types.py` for create and `services/departments.py` for the load-or-`not_found()` delete.
  - [x] `create_holiday(*, holiday_date, name) -> CompanyHoliday`: open `with Session(get_engine(), expire_on_commit=False) as session:`, pre-check the duplicate `holiday_date` (→ `409 HOLIDAY_DATE_IN_USE`), then **inside a `try`** call the repo `create` (which flushes) **and** `session.commit()`, with an `IntegrityError` backstop that rolls back and — only for a genuine `holiday_date` collision — re-raises the typed 409; any other `IntegrityError` re-raises untouched. **Put the repo `create` call INSIDE the `try`, not just `commit()`** — the `UNIQUE` violation surfaces at the repo's `flush()`, so wrapping only `commit()` lets a concurrent duplicate escape as a raw 500 (this is the exact bug the 2.1 code review fixed; `services/leave_types.py` now shows the corrected shape — copy it).
  - [x] `delete_holiday(holiday_id) -> None`: open a write session, `get_holiday`-or-`authz.not_found()` (→ `404 RESOURCE_NOT_FOUND`, AC8), then `delete_holiday` + `commit`, returning `None`. No `IntegrityError` backstop needed (no FK RESTRICT points at `company_holiday`). Reach `not_found()` through `services/authorization` — the route cannot import `domain/`.
  - [x] `list_holidays(limit, offset)` — thin read pass-through over a read session (mirror `list_leave_types`).
- [x] **Task 5 — Duplicate-date error wiring** (AC: 5)
  - [x] Add a new code constant `HOLIDAY_DATE_IN_USE = "HOLIDAY_DATE_IN_USE"` to `backend/app/domain/vocabulary.py` **and** to its `__all__` (AD-21: declared once, literal nowhere else). Add a comment block modelled on the `LEAVE_TYPE_CODE_IN_USE` block, attributing it to Story 2.2.
  - [x] Map it to `409` in `backend/app/main.py`'s `CODE_TO_STATUS.update({...})` block, with a Story 2.2 comment beside the `LEAVE_TYPE_CODE_IN_USE` entry.
  - [x] Service raises `DomainError(code=vocabulary.HOLIDAY_DATE_IN_USE, message=..., details={"holiday_date": holiday_date.isoformat()})` on a duplicate — a date is not sensitive, so naming it in `details` satisfies NFR-17 (use `.isoformat()` so the `details` value is the same `YYYY-MM-DD` string the wire uses; a raw `date` is not JSON-serialisable in the envelope).
- [x] **Task 6 — API router** (AC: 2, 3, 6, 7, 8, 9)
  - [x] New file `backend/app/api/v1/holidays.py`, `router = APIRouter()`. Mirror `api/v1/leave_types.py` and (for the DELETE) `api/v1/departments.py`.
  - [x] Inline Pydantic `HolidayWriteRequest` (`holiday_date: datetime.date`, `name: str`) and `HolidayResponse` (`id: uuid.UUID`, `holiday_date: datetime.date`, `name: str`). Pydantic parses/serialises `date` as `YYYY-MM-DD` automatically — this is what delivers AC2 on the wire. Project the response by hand via a `_to_response(obj: object)` helper (api/ may not import the ORM model).
  - [x] `@router.post("/holidays", status_code=status.HTTP_201_CREATED)` with `_admin: Actor = Depends(require_role(authz.ROLE_ADMIN))` → returns `HolidayResponse` (201).
  - [x] `@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)` with `holiday_id: uuid.UUID` and `_admin: Actor = Depends(require_role(authz.ROLE_ADMIN))` → returns `None` (204). Calls `holidays_service.delete_holiday(holiday_id)`.
  - [x] `@router.get("/holidays")` with `params: PageParams = Depends()` and `_caller: Actor = Depends(get_current_employee)` (authentication only, **not** `require_role`) → returns `Page[HolidayResponse]`.
  - [x] Register the router in `backend/app/api/v1/router.py` (`from app.api.v1 import ... holidays` + `api_v1_router.include_router(holidays.router)`).
  - [x] **Success codes (G6 — this story's to choose):** `201` POST / `204` DELETE / `200` GET, matching the React hooks — identical to departments/leave-types. See Dev Notes "The success-code decision (AD-19 / Story 2.11)" for why this is NOT the api-contracts §4.3 "200 with a summary" form yet.
- [x] **Task 7 — Satisfy the armed enforcement tests** (AC: 1, 8, 9)
  - [x] `backend/tests/test_scoped_getters.py`: add `"list_holidays"` and `"get_holiday"` to the `EXEMPT` frozenset (after the `list_leave_types`/`get_leave_type` block, ~lines 82–83), with a comment marking them scope-`all` reference reads — the module docstring already anticipates "leave types **and holidays** follow in Epic 2, all api-contracts scope `all`".
  - [x] `backend/tests/test_migrations_insert_nothing.py`: extend the ordered-chain assertion (`test_the_migration_history_is_the_expected_ordered_chain`, ~lines 121–125) to append `"0004_company_holiday.py"`.
  - [x] `backend/tests/integration/test_schema_1_2.py`: add `"company_holiday"` to the exact table-set in `test_exactly_the_expected_tables_exist` (~line 34). The set grows one table per schema story.
  - [x] `backend/tests/integration/test_migration_smoke.py`: bump `HEAD_REVISION` to `"0004_company_holiday"` (~line 19); add a new `test_company_holiday_table_shipped_with_its_columns_and_unique_date` mirroring the `leave_type` smoke — assert columns `{id, holiday_date, name}`, that `holiday_date`'s `data_type` is `date` (via `information_schema.columns`, closing AC2 at the catalog), and that `UNIQUE (holiday_date)` shipped.
  - [x] Confirm `test_architecture.py` (import-linter contracts) and `test_vocabulary_literals.py` still pass — no new dependency, and the only new literal is the error code (declared in `vocabulary.py`).
- [x] **Task 8 — Backend tests** (AC: 1–3, 5–9)
  - [x] New `backend/tests/integration/test_holidays.py` (mirror `test_leave_types.py`; **must `import app.main`** so `CODE_TO_STATUS` is populated). Use the `callers` fixture pattern from `test_leave_types.py`/`test_departments.py` (one Employee per role, token via `security.create_token(str(id), role)`, committed). Cover:
    - Admin POST creates a holiday and it is returned by GET, with `holiday_date` serialised as `"YYYY-MM-DD"` (201; AC3, AC2).
    - every role GETs the list (200; AC3).
    - Admin DELETE removes it (204), and a subsequent GET no longer lists it (AC3).
    - DELETE of a random/nonexistent UUID → 404 `RESOURCE_NOT_FOUND` (AC8).
    - non-Admin POST → 403 `ACTION_NOT_PERMITTED`, **no row written**; non-Admin DELETE → 403, **row still present** (AC6).
    - no token **and** a malformed/garbage token → 401 `TOKEN_INVALID` on all three endpoints (AC7 — cover both the absent and invalid paths, per the 2.1 code-review lesson).
    - duplicate `holiday_date` → 409 `HOLIDAY_DATE_IN_USE`, `details.holiday_date` names the date, **no second row** (AC5).
    - page-size clamp through the `Page` envelope (AC9).
  - [x] **No `test_seed.py` change** — this story seeds nothing (see Task note below); do not add holiday assertions there.
- [x] **Task 9 — Frontend Holidays screen** (AC: 4, 10)
  - [x] New `frontend/src/api/holidays.ts` (copy `api/leaveTypes.ts` + the delete hook from `api/departments.ts`): `Holiday` (`{id, holiday_date, name}`) + `CreateHolidayInput` (`{holiday_date, name}`) interfaces; `HOLIDAYS_QUERY_KEY = ['holidays'] as const`; `useHolidays()` → `apiFetch<Page<Holiday>>('/holidays')`; `useCreateHoliday()` mutation POSTing `/holidays`; `useDeleteHoliday()` mutation `DELETE /holidays/${id}` (`apiFetch<void>`). All mutations invalidate `HOLIDAYS_QUERY_KEY` on success. Reuse the `Page<T>` type from `api/departments.ts` (its single home).
  - [x] Re-export the surface from `frontend/src/api/index.ts` (values `HOLIDAYS_QUERY_KEY`, `useCreateHoliday`, `useDeleteHoliday`, `useHolidays`; types `CreateHolidayInput`, `Holiday`).
  - [x] New `frontend/src/features/holidays/HolidaysPage.tsx`. **Gating = Pattern A (Departments/Leave Types):** the list renders for **any** authenticated role (GET is any-role); the add form and per-row delete buttons render only when `me.data?.role === ADMIN_ROLE` (AC10; NFR-16 is usability, never the guard — the server 403 is the boundary).
  - [x] Create form fields: `holiday_date` (**`<input type="date">`** — its value is already a `YYYY-MM-DD` string, exactly the wire shape; no conversion) and `name` (text). Hold both as strings in form state; guard `holiday_date !== '' && name.trim() !== ''` before submit; reset to an `EMPTY_CREATE` constant on success. Mirror `LeaveTypesPage`'s form idiom.
  - [x] Per-row Delete button (Admin only), disabled while its own delete is pending (mirror `DepartmentsPage`'s `deleteHoliday.variables === holiday.id` guard). Render the list ordered as the server returns it (by date).
  - [x] Server error → user message: a `writeErrorMessage(error: unknown)` helper branching on `error instanceof ApiError` + `error.code` (restate `HOLIDAY_DATE_IN_USE` as a module constant, matched on `code` never `message`). Render `<p className="emp-error" role="alert">…</p>`. The duplicate-date message should be human ("A holiday already exists on that date.").
  - [x] Mount `<HolidaysPage />` in `AppShell`'s `<main>` in `frontend/src/App.tsx`, after `<LeaveTypesPage />` (there is **no router** — pages are stacked panels; import near the other feature imports).
  - [x] Reuse existing CSS classes (`panel`, `emp-create`, `emp-fields`, `emp-field`, `emp-form-actions`, `emp-list`, `emp-row`, `emp-error`, `dept-actions`). No new CSS is expected (a date input and a text input need none).
- [x] **Task 10 — Prove it** (all ACs)
  - [x] Backend: from `backend/`, with the stack up (`docker compose up -d`), run `.venv/bin/python -m pytest` — all green (integration tests skip with a reason if no DB). `pytest` **is** the build; `lint-imports` runs inside it via `test_architecture.py`; the migration AST guard and `alembic check` run inside it too.
  - [x] Frontend: from `frontend/`, run `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean. There is **no frontend test runner**; the frontend proof is passing typecheck+lint+build plus a DECLARED manual click-through (Admin sees add form + delete; non-Admin sees list only). State explicitly in Completion Notes whether the click-through was actually performed (prior stories declared it honestly when it was not).

## Dev Notes

### Why this story is (almost) a copy of Story 2.1 (leave types)

`company_holiday` is an Admin-managed, organization-wide (`scope: all`) CRUD resource with a `UNIQUE` constraint — the same shape as `leave_type`. **Read `2-1-leave-types-as-configuration.md` and the leave-type files (`repositories/leave_type.py`, `services/leave_types.py`, `api/v1/leave_types.py`, `alembic/versions/0003_leave_type.py`) as your primary template.** Four things differ and are where the work actually is:

1. **A `DATE` column, and the DATE discipline (AC2).** `holiday_date` is `datetime.date` / `sa.Date()` — never `datetime.datetime` / `TIMESTAMPTZ`. The precedent already in the codebase is `Employee.joining_date`. Pydantic carries the round-trip: `date ↔ "YYYY-MM-DD"` on the wire, for free.
2. **A `DELETE` endpoint (AC3, AC8).** Leave types had no delete; holidays do. The delete is the *departments* delete shape (`services/departments.py`: load-or-`not_found()` → delete → commit → 204) **minus** the emptiness guard (`company_holiday` has no FK dependents, ERD §3). So it is *simpler* than departments' delete.
3. **A new duplicate constraint on `holiday_date`** → a new error code `HOLIDAY_DATE_IN_USE` (409), a `CODE_TO_STATUS` entry, and the pre-check + flush-inside-`try` `IntegrityError` backstop. Directly analogous to `LEAVE_TYPE_CODE_IN_USE`.
4. **No seed.** Leave types seeded EL/CL/FL; the holiday calendar starts **empty** — no artifact seeds holidays, and the Admin populates it via the API. So there is no `seed/__main__.py` change and no `test_seed.py` change.

Everything else — the router shape, the `require_role(authz.ROLE_ADMIN)` vs `get_current_employee` split, `_to_response` hand-projection, `Page[...]` envelope, `expire_on_commit=False`, the two armed enforcement tests plus the two schema snapshots, the frontend list+form+error-mapping — is identical to 2.1. Reuse, do not reinvent.

### The success-code decision (AD-19 / Story 2.11) — READ THIS

api-contracts §4.3 says the holiday `POST`/`DELETE` "return `200` with a summary rather than failing wholesale." **That is the end-state, and it is NOT what this story builds.** That `200`-with-summary shape is a *consequence of `AD-19`'s forward-checked recalculation*: adding/deleting a holiday recalculates existing Leave Requests and Balances, and where a balance would go negative the affected Employee/Leave-Type pair is left unchanged and a row appears in `/admin-review-flags` — so the endpoint reports a partial-success summary instead of a hard failure.

**In Story 2.2 there is nothing to recalculate:** `leave_request` and `leave_balance` do not exist yet (they arrive in Stories 2.4/2.6), and epics.md#Story 2.2 states this explicitly — *"Adding or deleting a holiday also recalculates existing Leave Requests. That behavior needs `leave_request` and `leave_balance`, so it lands in Story 2.11. Until then no request exists to recalculate."*

So this story ships the plain CRUD success codes — **`201` create / `204` delete**, matching leave-types/departments — and **Story 2.11 ("A holiday change recalculates and may be refused") revises `POST`/`DELETE /holidays` to the api-contracts §4.3 `200`-with-summary form** when the recalculation and the summary payload actually exist. This is a *disclosed forward reference* (the same way Story 2.1 disclosed that `PATCH /leave-types` is a later story's work): do **not** invent a summary envelope now, and do not return `200` for an operation that has no summary to report. Story 2.11's author owns the change to these two endpoints and the React hooks that consume them.

### Architecture compliance (guardrails — violating any of these fails `pytest`)

- **AD-12 / DR-2a — a leave date is a `DATE`, transported `YYYY-MM-DD`.** `holiday_date` is PostgreSQL `DATE` and Python `datetime.date`, never `TIMESTAMPTZ`/`datetime`. The API transports it as `YYYY-MM-DD` (Pydantic's default `date` serialisation). No holiday date is ever stored, compared, or transported as a timestamp. [Source: ARCHITECTURE-SPINE.md#AD-12; erd.md#COMPANY_HOLIDAY]
- **AD-11-adjacent — the calendar is DATA, entered through the API/seed path, never a migration.** `0004` creates the *shape* and inserts nothing; the Admin adds holidays through `POST /holidays`. Enforced by `test_migrations_insert_nothing.py` (AST over every migration). [Source: ARCHITECTURE-SPINE.md#Seeding; test_migrations_insert_nothing.py]
- **AD-1 — layering.** Imports flow `api → services → {repositories, domain}` and `repositories → domain`. `api/` never imports `repositories/` or `domain/` (that is why the router types `_to_response(obj: object)` and reaches role constants through `services.authorization as authz`, never `from app.domain.vocabulary`). `domain/` imports no ORM/web and does no I/O. Enforced by import-linter (`test_architecture.py`). [Source: ARCHITECTURE-SPINE.md#AD-1]
- **Transaction boundary (AD-3).** Only `services/` opens transactions (`with Session(get_engine(), expire_on_commit=False)`). Only `repositories/` issues SQL. The repo `flush()`es (never commits); the service commits. [Source: ARCHITECTURE-SPINE.md#Design Paradigm; services/leave_types.py]
- **AD-5 — no constraint violation reaches a client as a 500.** A duplicate `holiday_date` must be a typed `409 HOLIDAY_DATE_IN_USE`, not a raw `IntegrityError`. Pre-check in the service; keep the DB `UNIQUE` as a backstop with a rollback+re-raise around the **flush-and-commit** (the `create` call must be inside the `try` — the 2.1 code-review fix). [Source: api-contracts.md#2; services/leave_types.py:76-96]
- **AD-10 — the 404 convention.** `DELETE /holidays/<id>` for an unknown id is `404 RESOURCE_NOT_FOUND`, raised by the service's load-or-`not_found()` — byte-identical to every other not-found. There is no scope predicate here (scope `all`), so the only 404 source is a genuinely absent id. [Source: ARCHITECTURE-SPINE.md#AD-10; services/departments.py:76-101]
- **AD-21 — canonical vocabulary.** Every error `code` is `UPPER_SNAKE_CASE`, declared once in `domain/vocabulary.py`, and appears as a literal nowhere else (`test_vocabulary_literals.py` scans `app/` + `seed/`). The only new one here is `HOLIDAY_DATE_IN_USE`. [Source: ARCHITECTURE-SPINE.md#AD-21; vocabulary.py]
- **Scoped-getter guardrail.** `GET /holidays` is scope `all` (organization-wide reference data), so no per-actor scoping applies — but `test_scoped_getters.py` flags `list_holidays`/`get_holiday` on name alone. Resolve by adding them to `EXEMPT` **with a rationale docstring** (they return no Employee-derived data), exactly as 2.1 did for leave types and 1.5 for departments. Do **not** bolt on an unused `actor` param. [Source: test_scoped_getters.py:68-85]
- **AD-14 / NFR-16 — the client renders authority; only the server enforces it.** The frontend hides the add/delete controls from non-Admins for usability; the real access control is the server's `403` on `POST`/`DELETE /holidays`. [Source: ARCHITECTURE-SPINE.md#AD-14]

### Exact schema (ERD §3, §4, §6)

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT uuidv7()` (PG18 native, no extension) | time-ordered, non-enumerable |
| `holiday_date` | `DATE` | `NOT NULL`, `UNIQUE (holiday_date)` | a single non-working day; not a Working Day, therefore not a Leave Day (`DR-1`). **Never `TIMESTAMPTZ`.** |
| `name` | `TEXT` | `NOT NULL` | the holiday's name — shown at preview time (`UJ-1`, `AD-2`) |

- **No column scopes a holiday to a Department or a location** — the calendar is global (ERD §3.2: "`company_holiday` … Global to the organization; scoped to no Department or location", `FR-10`, `A-03`).
- `company_holiday` stands alone: no foreign key into it, and none out of it. [Source: erd.md#COMPANY_HOLIDAY, §3, §4.2, §6]

### API contract (api-contracts §4.3)

| Method | Path | Role | Scope | Success (this story) | Realizes |
|---|---|---|---|---|---|
| `GET` | `/api/v1/holidays` | any | all | `200` | FR-10 |
| `POST` | `/api/v1/holidays` | Admin | all | `201` | FR-10 |
| `DELETE` | `/api/v1/holidays/<id>` | Admin | all | `204` | FR-10 |

- Base path `/api/v1`; paths plural, kebab-case (`holidays`; table stays singular `company_holiday`).
- **Per-field request/response schemas are NOT pinned in the contract docs** — the FastAPI-generated OpenAPI at `/api/v1/docs` is the runtime source of truth. Derive the body from the columns above (`id` is server-generated). [Source: api-contracts.md#0, #5]
- Error envelope (every non-2xx): `{ "code", "message", "details" }`. List envelope: `{ items, page, page_size, total }`. Enumerated values transported `UPPER_SNAKE_CASE` verbatim. [Source: api-contracts.md#1, #2]
- Status semantics: `401` no/invalid token (`TOKEN_INVALID`); `403` role-denied (`ACTION_NOT_PERMITTED`); `404` unknown id (`RESOURCE_NOT_FOUND`); `409` state conflict (use for duplicate `holiday_date`). [Source: api-contracts.md#1]
- **The `200`-with-summary clause in §4.3 is Story 2.11's** (see "The success-code decision" above). Out of scope here: `AD-19` recalculation, `/admin-review-flags`, and any recalculation summary payload.

### Library / framework requirements (pinned — do NOT upgrade)

Python `3.13.*`; FastAPI `0.139.0`; Pydantic `2.13.4`; SQLAlchemy `2.0.51`; Alembic `1.18.5`; psycopg `3.3.4`; PostgreSQL `18`; pytest `9.1.1`; import-linter `2.13`. Frontend: React `19.2.7`, Vite `8.1.4`, TypeScript `6.0.3`, TanStack Query `5.101.2`. **No new dependency is needed for this story.** [Source: pyproject.toml; frontend/package.json; ARCHITECTURE-SPINE.md#Stack]

### File structure (what to create / edit)

**New (backend):** `app/repositories/holiday.py`, `app/services/holidays.py`, `app/api/v1/holidays.py`, `alembic/versions/0004_company_holiday.py`, `tests/integration/test_holidays.py`, plus `CompanyHoliday` added to `app/repositories/models.py`.
**Edit (backend):** `app/domain/vocabulary.py` (new code + `__all__`), `app/main.py` (`CODE_TO_STATUS`: `HOLIDAY_DATE_IN_USE → 409`), `app/api/v1/router.py` (register router), `tests/test_scoped_getters.py` (EXEMPT += two getters), `tests/test_migrations_insert_nothing.py` (chain += `0004`), `tests/integration/test_schema_1_2.py` (table-set += `company_holiday`), `tests/integration/test_migration_smoke.py` (`HEAD_REVISION` = `0004`; new company_holiday smoke).
**New (frontend):** `src/api/holidays.ts`, `src/features/holidays/HolidaysPage.tsx`.
**Edit (frontend):** `src/api/index.ts` (re-export), `src/App.tsx` (mount page).

Naming: modules `snake_case`; SQLAlchemy models `PascalCase` (`CompanyHoliday`); table singular (`company_holiday`); service file plural (`holidays.py`), repo file singular (`holiday.py`) — matching the departments/leave-types precedent. React components `PascalCase`, hooks `useThing`. [Source: ARCHITECTURE-SPINE.md#Source tree, Consistency Conventions]

### Testing requirements

- `tests/domain/` runs with **no database**; `tests/integration/` runs against **real PostgreSQL** (skips with a reason if the stack is down). This story is all integration (schema + endpoints) — there is no pure-domain logic to add here. [Source: ARCHITECTURE-SPINE.md#Testing]
- Integration tests **must `import app.main`** to populate `CODE_TO_STATUS` (else a domain code falls through to 500). Use the `callers` fixture pattern from `test_leave_types.py` (one Employee per role, token via `security.create_token(str(id), role)`, committed so the app's connection sees it). [Source: tests/integration/test_leave_types.py]
- `pytest` is the build (no CI). The import-linter contracts and the migration AST guard run **inside** the suite; a layering break or a migration `insert` fails `pytest`, not a separate step. [Source: README.md#Tests]
- Model↔migration agreement: run `alembic check` (via `test_model_migration_agreement.py`) — an empty diff is required. Do not hand-author the migration and hope it matches; verify.
- **The two schema snapshots are armed and will fire when `company_holiday` ships** (exactly as they did for `leave_type` in 2.1): `test_schema_1_2.py::test_exactly_the_expected_tables_exist` (exact table-set) and `test_migration_smoke.py::test_alembic_version_exists_and_is_stamped_at_head` (`HEAD_REVISION`). Update both in Task 7 — this is expected, not a regression.

### Previous story intelligence (Story 2.1 — the direct twin — and 1.5)

- **The flush-vs-commit `IntegrityError` trap (2.1 code review, PATCH applied).** Wrapping only `session.commit()` in the `try` is a bug: the `UNIQUE` violation surfaces at the repo's `flush()` (which emits the INSERT), so a concurrent duplicate escapes the `except` as a raw 500. Put the repo `create` call **inside** the `try`. `services/leave_types.py:76-96` now shows the corrected pattern — copy its structure exactly.
- **AC7 must cover BOTH the absent AND the invalid/malformed token (2.1 code review).** The 2.1 test initially covered only the absent-token path; the review added a garbage-token assertion. Cover both here from the start, on all three endpoints.
- **Scope-`all` getters → EXEMPT with rationale (1.5 Trap 1 / 2.1 Task 8), never an unused `actor` param.** `holiday_date_exists` returns a `bool`, so it is correctly not a scoped-getter candidate.
- **Success codes are the story's to choose (1.5 Trap 5 / G6):** 201 POST / 204 DELETE / 200 GET, matched by the React hooks — reuse verbatim (and see the AD-19/2.11 note above for why 200-with-summary is deferred).
- **Deferred, consistent with 2.1 (do the same, declare it):** enveloped server-side *content* validation of the write body is a known, deferred gap pending the NFR-17 enveloping decision — for holidays, a malformed `holiday_date` yields a raw Pydantic `422` outside the `{code,message,details}` envelope, and an empty/whitespace `name` is accepted. This matches the 2.1/1.5/1.6 deferrals; do not solve it here, and note it in Completion Notes. (`holiday_date`'s *type* is still enforced — a non-date is rejected, just not enveloped.)
- **Frontend proof reality (1.5/1.6/1.8/2.1):** there is no frontend test runner. The proof is `npm run build` + `npm run lint` clean, plus a **declared** manual click-through. Declare honestly whether it was actually performed.

### Git intelligence

Head is `f4e0b53 feat(story-1.8): edit own profile`. **Story 2.1's work is implemented and marked `done` in sprint-status but is NOT yet committed** (its files show as untracked/modified in `git status`). This story's migration chains off `0003_leave_type` and its code imports `LeaveType`-adjacent patterns, so 2.1's files must be present in the tree (they are). If the dev workflow expects a clean baseline, **commit Story 2.1 first** (`feat(story-2.1): leave types as configuration`) so 2.2's baseline is unambiguous — see the open question below. Recent commits established: the departments CRUD+DELETE stack (1.5) that models the holiday delete; the leave-type CRUD+duplicate-`code`-409 stack (2.1) that this story clones; the `datetime.date` column precedent (`Employee.joining_date`, 1.2/1.6).

### Project structure notes

No structural conflicts. Every path above already exists as a sibling of an equivalent leave-types/departments file; you are adding one more resource to established `api/`, `services/`, `repositories/`, `alembic/versions/`, `tests/`, and `frontend/src/{api,features}/` locations. There is no new CSS and no new dependency. The one novelty — a `<input type="date">` — needs no styling and no conversion (its value is already the `YYYY-MM-DD` the API expects).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: The Company Holiday Calendar]
- [Source: _bmad-output/planning-artifacts/epics.md#FR-10] (Holiday Management; the recalculation clause is Story 2.11's)
- [Source: _bmad-output/planning-artifacts/module-4-erd/erd.md#COMPANY_HOLIDAY, §3 Relationships, §4 Physical model, §6 Constraints]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md#1 Conventions, #2 Error envelope, #4.3 Leave policy and holidays]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-1, #AD-3, #AD-5, #AD-10, #AD-12, #AD-14, #AD-21, #Stack, #Source tree, #Seeding]
- [Source: _bmad-output/implementation-artifacts/2-1-leave-types-as-configuration.md — the twin story; its Dev Agent Record and Review Findings (flush-vs-commit fix, AC8 both-token fix)]
- [Source: backend/app/repositories/leave_type.py, backend/app/services/leave_types.py, backend/app/api/v1/leave_types.py, backend/alembic/versions/0003_leave_type.py — the create/list template]
- [Source: backend/app/services/departments.py:76-101, backend/app/api/v1/departments.py:119-135 — the load-or-404 DELETE template]
- [Source: backend/app/repositories/models.py — `Employee.joining_date` is the `datetime.date` column precedent; `LeaveType` is the UNIQUE + uuidv7 precedent]
- [Source: backend/tests/test_scoped_getters.py:68-85 — EXEMPT registry; backend/tests/test_migrations_insert_nothing.py:121-125 — chain list; backend/tests/integration/test_schema_1_2.py:34 — table-set; backend/tests/integration/test_migration_smoke.py:19 — HEAD_REVISION]
- [Source: frontend/src/api/leaveTypes.ts, frontend/src/features/leaveTypes/LeaveTypesPage.tsx, frontend/src/api/departments.ts (useDeleteDepartment), frontend/src/features/departments/DepartmentsPage.tsx (delete UI) — frontend template]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8[1m]) — BMAD dev-story workflow.

### Debug Log References

- `alembic upgrade head` (host venv) advanced the dev DB `0003_leave_type → 0004_company_holiday`. The running `api` container image predates Story 2.1, so its bundled migration files stop at `0002`; migrations were therefore applied from the host venv (which carries `0001`–`0004`) against the published port `localhost:5433`, not via `docker compose exec api`.
- One armed enforcement test fired that the story tasks did not enumerate: `tests/test_scope_matrix.py::test_every_identifier_endpoint_is_registered` flagged `DELETE /api/v1/holidays/{holiday_id}` as an identifier endpoint with no SM-3 scope. Resolved by registering it in `_SCOPE_REGISTRY` with `frozenset({Scope.ALL})` — the holiday calendar is organization-wide (scope `all`), identical to the `/departments/{id}` writes. (`POST`/`GET /holidays` carry no path parameter, so they are out of the matrix.)

### Completion Notes List

Story 2.2 implemented as a faithful clone of Story 2.1 (leave types) with the four documented differences: a `DATE` column, a `DELETE` endpoint, a new `HOLIDAY_DATE_IN_USE` (409) code, and no seed. All 10 ACs satisfied.

- **AC1 (Schema):** `company_holiday` carries `holiday_date DATE` + `name TEXT`, `UNIQUE (holiday_date)`, and no scope column (no `department_id`/`location`). Model + migration agree (`alembic check` empty diff, enforced in-suite).
- **AC2 (DATE not timestamp):** `holiday_date` is `datetime.date` / `sa.Date()`; Pydantic transports it as `YYYY-MM-DD`. The new `test_migration_smoke.py::test_company_holiday_table_shipped_with_its_columns_and_unique_date` asserts `information_schema` `data_type == 'date'` at the live catalog.
- **AC3 (Endpoints):** `POST`/`DELETE /api/v1/holidays[/<id>]` (Admin) and `GET /api/v1/holidays` (any role) all live and tested end-to-end.
- **AC4 / AC10 (Frontend):** `HolidaysPage` renders the list for any role; the add form + per-row Delete render only for Admin (Pattern A, `me.data?.role === 'ADMIN'`). Server 403 is the real guard.
- **AC5 (409 duplicate):** typed `409 HOLIDAY_DATE_IN_USE` with `details.holiday_date` (ISO string), pre-check + flush-inside-`try` `IntegrityError` backstop — the corrected 2.1 shape. No raw 500.
- **AC6 (non-Admin 403):** `require_role(ROLE_ADMIN)` gates POST and DELETE at the boundary; tested that no row is written/removed.
- **AC7 (401):** all three endpoints answer `401 TOKEN_INVALID` to both the absent AND the invalid/garbage token (both paths covered, per the 2.1 review lesson).
- **AC8 (404 on unknown delete):** load-or-`not_found()` → `404 RESOURCE_NOT_FOUND`.
- **AC9 (page-bounded):** `Page` envelope + shared clamp, tested through the real envelope.

**Proof performed:**
- Backend: `.venv/bin/python -m pytest` — **232 passed, 1 warning** (starlette httpx deprecation, not spine-governed). This runs the import-linter contracts (`test_architecture.py`), the migration AST guard, `alembic check`, `test_vocabulary_literals.py`, `test_scoped_getters.py` and `test_scope_matrix.py` in-suite — all green.
- Frontend: `npm run build` (`tsc -b && vite build`) — clean; `npm run lint` (oxlint) — clean (exit 0).
- **Manual click-through: NOT performed.** There is no frontend test runner, and the running `web` container image predates this work. The frontend proof is the passing typecheck + lint + build only; the Admin-vs-non-Admin control gating is asserted structurally in code (Pattern A), not exercised in a browser. Declared honestly, consistent with Stories 1.5/1.6/1.8/2.1.

**Deferred (consistent with 2.1/1.5/1.6, declared not solved here):** enveloped server-side *content* validation of the write body pends the NFR-17 enveloping decision. A malformed `holiday_date` yields a raw Pydantic `422` outside the `{code,message,details}` envelope (its *type* is still enforced — a non-date is rejected), and an empty/whitespace `name` is accepted. The api-contracts §4.3 `200`-with-summary form for POST/DELETE is Story 2.11's (AD-19 recalculation), not this story's — plain `201`/`204` ship here.

### File List

**New (backend):**
- `backend/app/repositories/holiday.py`
- `backend/app/services/holidays.py`
- `backend/app/api/v1/holidays.py`
- `backend/alembic/versions/0004_company_holiday.py`
- `backend/tests/integration/test_holidays.py`

**Modified (backend):**
- `backend/app/repositories/models.py` (added `CompanyHoliday`)
- `backend/app/domain/vocabulary.py` (added `HOLIDAY_DATE_IN_USE` + `__all__`)
- `backend/app/main.py` (`CODE_TO_STATUS`: `HOLIDAY_DATE_IN_USE → 409`)
- `backend/app/api/v1/router.py` (registered `holidays.router`)
- `backend/tests/test_scoped_getters.py` (EXEMPT += `list_holidays`, `get_holiday`)
- `backend/tests/test_scope_matrix.py` (registry += `DELETE /holidays/{holiday_id}` → `{Scope.ALL}`)
- `backend/tests/test_migrations_insert_nothing.py` (chain += `0004_company_holiday.py`)
- `backend/tests/integration/test_schema_1_2.py` (table-set += `company_holiday`)
- `backend/tests/integration/test_migration_smoke.py` (`HEAD_REVISION` = `0004_company_holiday`; new company_holiday smoke)

**New (frontend):**
- `frontend/src/api/holidays.ts`
- `frontend/src/features/holidays/HolidaysPage.tsx`

**Modified (frontend):**
- `frontend/src/api/index.ts` (re-export the holidays surface)
- `frontend/src/App.tsx` (mount `<HolidaysPage />` after `<LeaveTypesPage />`)

### Review Findings

_Code review 2026-07-13 — adversarial layers: Blind Hunter + Edge Case Hunter + Acceptance Auditor. Acceptance Auditor verdict: implementation faithful to spec, no Critical/High deviations against AC1–AC10._

**Patch (unchecked — fixable now):**

- [x] [Review][Patch] Delete failures are not surfaced in the Holidays UI [frontend/src/features/holidays/HolidaysPage.tsx:162] — FIXED 2026-07-13: added a per-row `deleteError` state + `deleteErrorMessage` helper + `handleDelete` with `onError`, mirroring the Departments Pattern A. Lint + build clean. — the screen's own docstring claims "Departments pattern (Pattern A)", but `DepartmentsPage` tracks a per-row `deleteError` with `onError` + `role="alert"`, while the Holidays delete button fires `deleteHoliday.mutate(holiday.id)` with no error rendering anywhere. A failed delete (404 from a concurrent delete, 403, or a network error) is silent: `onSuccess` never fires, so the list is not even refetched, and the admin gets no feedback. The create path here already surfaces errors; only the delete path is missing it.

**Deferred (checked — pre-existing or already declared):**

- [x] [Review][Defer] Enveloped server-side body validation — blank/whitespace `name` accepted, malformed `holiday_date` yields a raw 422 outside the `{code,message,details}` envelope [backend/app/api/v1/holidays.py:50] — deferred, already declared in Dev Agent Record; pends the NFR-17 enveloping decision, consistent with 2.1/1.5/1.6 (departments and leave_types share the identical gap).
- [x] [Review][Defer] List renders only the first page — `useHolidays` calls `/holidays` with no `page`/`page_size` and there are no pagination controls [frontend/src/api/holidays.ts:47] — deferred, pre-existing pattern shared by `useDepartments` and `useLeaveTypes`; no pagination UI exists anywhere in the frontend yet.
- [x] [Review][Defer] Concurrent delete of the same id raises 500 (`StaleDataError`) instead of 404 [backend/app/services/holidays.py:102] — deferred, narrow race (two admins deleting the same row at once); same delete shape as departments/leave_types, so a codebase-wide decision, not a 2.2 defect.
- [x] [Review][Defer] The genuine-TOCTOU `IntegrityError` re-check branch has no test [backend/tests/integration/test_holidays.py] — deferred, test-coverage gap only; the sequential duplicate test never fires the `except IntegrityError` path.
- [x] [Review][Defer] Clamp test seeds fixed dates (`2200-01-01…`) and cleans up only in `finally` [backend/tests/integration/test_holidays.py] — deferred, test robustness; a mid-body crash leaves rows that collide with `UNIQUE (holiday_date)` on the next run.
- [x] [Review][Defer] `_unique_date` picks one date from a ~9,999-day window and can collide under `pytest-xdist` / a shared DB [backend/tests/integration/test_holidays.py] — deferred, test robustness.

_Dismissed as noise (6): AC4 "for a Leave Year" not modeled (correct by design per AC1 — global calendar, auditor-confirmed); duplicate `name` on distinct dates allowed (only `holiday_date` is unique per AC1/AC5, intended); `_to_response(holiday: object)` weak typing (deliberate, documented layering rule — api/ may not import the ORM model); migration/model unique-constraint naming coupling (guarded by the model-migration agreement test + smoke test); `create_holiday` post-commit return relies on `expire_on_commit=False` (documented invariant, consistent with leave_types/departments); `_count_date -> int` type nit and client-only name trim (cosmetic)._

## Change Log

| Date | Version | Description |
|---|---|---|
| 2026-07-13 | 1.0 | Story 2.2 implemented — Company Holiday calendar: `company_holiday` table (`0004`), repository/service/router, `HOLIDAY_DATE_IN_USE` 409, frontend Holidays screen. Backend 232 tests pass; frontend build + lint clean. Status → review. |
