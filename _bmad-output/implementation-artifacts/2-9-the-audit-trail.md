---
baseline_commit: 83096b2037766b176e2db0cad9d9bfaf1facd5c2
---

# Story 2.9: The Audit Trail

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want an append-only record of every state transition,
So that a disagreement about what was approved is settled by the system rather than by whoever kept better notes.

---

## Orientation: what this story actually is

**The audit trail already exists.** Stories 2.6, 2.7 and 2.8 built the `audit_entry` table and every write into it. Six call sites already append exactly one row per transition, in the transition's own transaction, with the right actor and reason. **Do not rebuild any of that.**

This story does four things, and nothing else:

1. **Opens the read surface** — `GET /api/v1/audit-entries`, Admin-only (AC1, AC2).
2. **Makes AD-9 true at the database, not just in the code** — the app's DB role loses `UPDATE`/`DELETE` on `audit_entry`. This is the deferral Story 2.6 took and **this story is where it comes due** (AC3).
3. **Proves SM-4 suite-wide** — audit rows counted against state transitions, one-to-one, across *every* transition the system can perform (AC4, AC5, AC6).
4. **Ships the index the ERD named and 0006 never created** — `audit_entry (subject_type, subject_id)`, "the audit read surface" (NFR-12).

**Read-only story on the write path.** No service that writes an audit row changes. No new vocabulary constant. No new error code.

---

## Acceptance Criteria

**AC1 — Admin reads the trail**
**Given** an authenticated Admin
**When** they call `GET /api/v1/audit-entries`
**Then** the response is `200`, and every entry names its subject, the transition, the actor and the timestamp

**AC2 — Nobody else reads the trail**
**Given** an authenticated Employee or Manager
**When** they call `GET /api/v1/audit-entries`
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — full audit-log read access is the Admin's alone (`FR-16`, `DR-13`, `G3`)

**AC3 — Append-only is a grant, not a habit**
**Given** the application's database role
**When** it attempts `UPDATE` or `DELETE` on `audit_entry`
**Then** the database refuses, because the grant was never made
**And** no repository exposes an update or delete method for it, and Alembic migrations run under the owner role (`AD-9`, `NFR-09`)

**AC4 — SM-4, one-to-one**
**Given** the full test suite
**When** Audit Entries are counted against state transitions
**Then** the counts are equal, one-to-one (`SM-4`, `DR-16`)

**AC5 — A rolled-back transition leaves nothing**
**Given** a transition whose transaction rolls back
**When** the audit log is read
**Then** no entry exists for it, because the row was inserted inside that transaction (`AD-8`)

**AC6 — SYSTEM is not a person**
**Given** an Audit Entry written by the managerless auto-approval path
**When** it is inspected
**Then** `actor_type` is `SYSTEM`, `actor_id` is NULL, and `reason` is `AUTO_APPROVED_NO_MANAGER`
**And** no human approver is fabricated (`FR-16`)

---

## 🚨 Three landmines. Read these before writing a line.

### Landmine 1 — A test hard-pins the audit repo surface. Your first read method fails the build.

[backend/tests/integration/test_leave_request_submit.py:551](backend/tests/integration/test_leave_request_submit.py#L551) asserts:

```python
assert audit_surface == {"insert_audit_entry"}, (
    f"audit_entry repo must expose ONLY insert (append-only, AD-8); found {audit_surface}"
)
```

Adding `list_audit_entries` to `repositories/audit_entry.py` **fails this assertion immediately.**

**You must revise this test, not delete it, and not route around it.** Story 2.7 set the precedent when it widened the `leave_request` clause in the same test: it added the new methods to the expected set and rewrote the docstring so the assertion still guarantees something real. Do exactly that here — widen to `{"insert_audit_entry", "list_audit_entries"}` and reframe the docstring around the actual guarantee: **INSERT and SELECT only; never an update, never a delete.**

Do **not** dodge it by putting the read in a new `repositories/audit.py` module. The test only reflects over `audit_entry`, so a sibling module would slip past it silently — and that is precisely the "route around the guardrail" move the assertion exists to catch. Keep one repository module per table. The module's own docstring already anticipates this story: *"it exposes an INSERT (and, later, reads) and NO update or delete method."*

### Landmine 2 — `list_audit_entries` trips the scoped-getters guard.

[backend/tests/test_scoped_getters.py](backend/tests/test_scoped_getters.py) reflects over every module under `app/repositories/` and fails any function matching `get_|list_|find_|fetch_` that takes a `session` but no `actor`.

`audit_entry` has **no employee-owner column**. `actor_id` is who *did* the thing, not who *owns* the row — scoping the trail by it would be semantically wrong and would hide an Admin's own view of the system. The endpoint is Admin-only, scope `all`, so there is no per-row predicate to apply.

**Resolution: add `list_audit_entries` to the `EXEMPT` frozenset** at [backend/tests/test_scoped_getters.py:64](backend/tests/test_scoped_getters.py#L64), alongside `list_departments` / `list_leave_types` / `list_holidays` — the established scope-`all` reference-read exemption — **and give the function a "why exempt" docstring at its definition**, as every other exempt getter carries. The exemption comment must say why: *the audit trail has no Employee-owner column; the gate is the Admin role, applied in `api/` before the query runs.*

### Landmine 3 — Two audit rows can share the exact same `occurred_at`. An unstable sort silently corrupts pagination.

Story 2.8's **CR-approve writes two rows in one transaction** ([services/cancellation.py:317](backend/app/services/cancellation.py#L317) and [:328](backend/app/services/cancellation.py#L328)) — one `CANCELLATION_REQUEST`, one `LEAVE_REQUEST` — **both stamped from the same `_now()` value.** Their `occurred_at` is byte-identical.

`ORDER BY occurred_at DESC` alone is therefore **not a total order**. Postgres may return those two rows in either order between two queries, so a paginated read can show one row twice and skip another entirely.

**Order by `occurred_at DESC, id DESC`.** The `id` tiebreak makes the sort total and deterministic. (UUIDv7 is time-ordered, so it also breaks the tie in a sensible direction.)

---

## Tasks / Subtasks

### Task 1 — Make AD-9 a database fact: the least-privilege application role (AC3)

**This is the story's real work and its only substantial risk. Do it first.**

**The honest starting position.** Story 2.6 recorded a Decision Point and took option (a): the codebase runs a **single Postgres role** (`POSTGRES_USER=leaveflow`), which *owns* `audit_entry`. A `REVOKE UPDATE, DELETE` against an owner is a **no-op** — an owner cannot be denied on its own table. So AD-9's grant guarantee does not exist today; only the code-layer surface test does. That was defensible for 2.6. **It is not defensible for AC3**, which says in as many words: *"the database refuses, because the grant was never made."*

Implement the two-role split AD-9 and ERD §4.3 have specified all along:

- [x] **Provision a second, non-owner role for the application.** The migration/owner role (existing `POSTGRES_USER`) keeps ownership and runs Alembic. Add a distinct application role that the FastAPI app connects as.
  - `docker-compose.yml` — the Postgres service already provisions the owner. Create the app role in the DB init path (an init SQL script, or a bootstrap step in the owner-run migration — see the next subtask for the recommended route).
  - `.env.example` and settings — add the app-role credentials and a second connection URL. The app's engine ([backend/app/repositories/engine.py](backend/app/repositories/engine.py)) connects as the **app role**; Alembic (`alembic/env.py`) connects as the **owner role**. Keep the split explicit and named — a reader must be able to see which role is which.
  - Preserve the existing loud-skip behavior in [backend/tests/integration/conftest.py](backend/tests/integration/conftest.py): a missing/placeholder DB config skips integration tests, it does not fail them.

- [x] **Issue the grant in migration `0008`, which runs as the owner** (`0007_cancellation_request` is `down_revision`; `0008` is next — verified against `backend/alembic/versions/`).
  ```sql
  GRANT INSERT, SELECT ON audit_entry TO <app_role>;
  -- and NOT update, NOT delete. The absence is the guarantee.
  ```
  Grant the app role the privileges it actually needs on the *other* tables too (`SELECT, INSERT, UPDATE, DELETE` as each table requires) — the app must keep working. **Only `audit_entry` is narrowed to `INSERT, SELECT`.** Include the `USAGE` grant on the schema and on any sequence the app writes through. A missed grant here breaks every other endpoint, so run the full suite before believing you are done.
  - `rollover_run` does not exist yet (Story 2.10). Do not pre-create it. AD-9 covers it when it arrives.

- [x] **The AC3 test — the database refuses.** A new integration test that, connected **as the application role**, attempts `UPDATE audit_entry SET reason = ...` and `DELETE FROM audit_entry ...` against a real row, and asserts Postgres raises an insufficient-privilege error (`psycopg.errors.InsufficientPrivilege`). This is the assertion that makes AC3's first clause true. Assert on the *privilege* error specifically — a test that passes because the row did not exist, or because the SQL was malformed, proves nothing.

- [x] **The AC3 second clause** is Landmine 1's revised surface test: no repository exposes update or delete for `audit_entry`. Both clauses must pass.

> **If the role split proves infeasible** (e.g. the container's init path cannot be changed without breaking the reproducible-setup guarantee Story 1.1 established): **stop and say so in the Dev Agent Record.** Do not quietly re-declare the code-layer realization and mark AC3 done — that is the "lying about completion" failure this project's review process exists to catch. Record precisely what blocked it, keep the code-layer test, and flag AC3 as **not met** so it can be triaged. An honestly-missed AC beats a falsely-claimed one.

### Task 2 — The index the ERD named and 0006 never created (NFR-12, in migration `0008`)

- [x] Add to the same `0008` migration:
  ```python
  op.create_index("ix_audit_entry_subject", "audit_entry", ["subject_type", "subject_id"])
  ```
  ERD §4.4 names exactly this index and labels it **"The audit read surface (`FR-16`)"** — this story *is* the audit read surface, so it lands here. Migration 0006's docstring said `audit_entry` "needs none this story"; that was true then.
- [x] **Mirror the index on the model** in [backend/app/repositories/models.py](backend/app/repositories/models.py) (`AuditEntry.__table_args__`). Model and migration must agree byte-for-byte or [backend/tests/integration/test_model_migration_agreement.py](backend/tests/integration/test_model_migration_agreement.py) fails (`alembic check` must produce an empty diff). **Change one, change both, same commit.**
- [x] Add no index the ERD does not name (the Story 2.8 precedent). Notably: no index on `occurred_at`. The list is ordered by it, which is a sequential scan plus sort — acceptable at Epic-2 volume, and adding an unspecified index is a scope decision this story does not own.

### Task 3 — The repository read (AC1)

- [x] Add `list_audit_entries` to **[backend/app/repositories/audit_entry.py](backend/app/repositories/audit_entry.py)** (not a new module — Landmine 1).
- [x] Copy the shape of [repositories/leave_request.py:156](backend/app/repositories/leave_request.py#L156) `list_leave_requests` and [repositories/cancellation_request.py:152](backend/app/repositories/cancellation_request.py#L152):
  - a module-level `_READ_COLUMNS` tuple of **plain columns, never the ORM entity** (nothing detaches when the session closes),
  - `.limit()` / `.offset()` from `PageParams`,
  - a **separate `func.count()`** recomputing the same predicate,
  - return `tuple[list[Row], int]`.
  ```python
  def list_audit_entries(
      session: Session, *, limit: int, offset: int
  ) -> tuple[list[Row], int]:
      """... why exempt from the scoped-getter contract: `audit_entry` has no Employee-owner
      column. `actor_id` records who acted, not who owns the row. The gate is the Admin role,
      applied in `api/` before this query runs (DR-13, G3). Scope is `all`; there is no
      per-row predicate to apply. ..."""
  ```
- [x] **`LEFT OUTER JOIN` to `employee` to resolve the actor's name** — an `INNER JOIN` would silently drop every `SYSTEM` row, because `actor_id` is NULL for them. That would make AC6 unobservable through the endpoint and would quietly under-count SM-4. This is the single most likely way to get this story wrong.
  ```python
  .outerjoin(Employee, AuditEntry.actor_id == Employee.id)
  ```
- [x] `ORDER BY AuditEntry.occurred_at.desc(), AuditEntry.id.desc()` — **the `id` tiebreak is mandatory** (Landmine 3).
- [x] Add `list_audit_entries` to `EXEMPT` in [backend/tests/test_scoped_getters.py](backend/tests/test_scoped_getters.py) (Landmine 2).
- [x] Revise the surface assertion in [backend/tests/integration/test_leave_request_submit.py:551](backend/tests/integration/test_leave_request_submit.py#L551) (Landmine 1).

### Task 4 — The service (AC1)

- [x] New **`backend/app/services/audit.py`**. Follow [services/cancellation.py:64](backend/app/services/cancellation.py#L64) exactly:
  - a `@dataclass(frozen=True) AuditEntryView` — the fields AC1 names: subject (`subject_type`, `subject_id`), transition (`from_state`, `to_state`), actor (`actor_type`, `actor_id`, `actor_name`), timestamp (`occurred_at`), plus `reason` and `id`.
  - `actor_name: str | None` — **NULL for SYSTEM rows. Do not substitute `"System"`, `"—"`, or any placeholder in the service.** AC6's *"no human approver is fabricated"* is a data-layer promise; a display string is the frontend's business, and inventing one here launders a real fact.
  - a `_row_to_view(row)` mapper; a `list_audit_entries(actor, *, limit, offset) -> tuple[list[AuditEntryView], int]`.
  - open the session with `Session(get_engine(), expire_on_commit=False)`; **read path — do not commit** (the 2.5 precedent).
- [x] The service does **not** re-check the role. The gate is the `api/` dependency (Task 5), which runs before this is called — the G3 rule is *"role denied, decided before any row is read."*

### Task 5 — The endpoint (AC1, AC2)

- [x] New **`backend/app/api/v1/audit_entries.py`**. The Admin-only list pattern to copy verbatim is [api/v1/employees.py:147](backend/app/api/v1/employees.py#L147) `list_employees`:
  ```python
  @router.get("/audit-entries", tags=["audit-entries"])
  def list_audit_entries(
      params: PageParams = Depends(),
      admin: Actor = Depends(require_role(authz.ROLE_ADMIN)),
  ) -> Page[AuditEntryResponse]:
      views, total = audit_service.list_audit_entries(
          admin, limit=params.limit, offset=params.offset
      )
      return Page[AuditEntryResponse](
          items=[_to_audit_entry_response(v) for v in views],
          page=params.page, page_size=params.page_size, total=total,
      )
  ```
- [x] `require_role(authz.ROLE_ADMIN)` ([api/v1/dependencies.py:90](backend/app/api/v1/dependencies.py#L90)) raises `ACTION_NOT_PERMITTED` → **403 already mapped** in [main.py:56](backend/app/main.py#L56). **No new error code. No `main.py` change.**
- [x] `AuditEntryResponse(BaseModel)` — hand-projected fields, **no `from_attributes`**, and `_to_audit_entry_response(view: object)` duck-typing the view as `object`. `api/` may import neither `repositories/` nor `domain/` (import-linter contract 2). Reuse `PageParams` / `Page[T]` from [api/v1/pagination.py](backend/app/api/v1/pagination.py) — **pagination is already fully implemented server-side; do not write your own.**
- [x] Register in [api/v1/router.py](backend/app/api/v1/router.py): add `audit_entries` to the import tuple and one `api_v1_router.include_router(audit_entries.router)` line.
- [x] **No filters this story.** The ACs name none. Stories 2.7 and 2.8 both added only the filter their AC named and explicitly refused the rest ("those are Story 3.1's"). Adding a `subject_type` filter would also drag in the AD-21 runtime-enum machinery for no AC. Ship the plain paginated list.
- [x] **Do not register in the SM-3 scope matrix.** [backend/tests/test_scope_matrix.py](backend/tests/test_scope_matrix.py) keys on `(METHOD, path-with-parameter)`. `GET /audit-entries` has **no path parameter**, so it is out of the matrix by construction — registering it trips `test_no_registered_entry_names_a_route_the_app_does_not_expose`. (Same as `GET /leave-requests` and `GET /cancellation-requests`.)

### Task 6 — Prove it (AC2, AC4, AC5, AC6)

New `backend/tests/integration/test_audit_entries.py`. Build the `_World` fixture the way [test_cancellation_request.py](backend/tests/integration/test_cancellation_request.py) does (Department + Manager + report + Admin + leave type + materialized balances + `security.create_token` + `TestClient`), `import app.main` at the top so `CODE_TO_STATUS` is wired, and clean up in a `finally` — **deleting audit rows before the rows they reference.**

- [x] **AC1** — Admin `GET /api/v1/audit-entries` → `200`; the envelope is `{items, page, page_size, total}`; each item carries subject, transition, actor and timestamp. Include at least one `SYSTEM` row in the fixture and assert it **appears in the response** (this is what catches the inner-join bug).
- [x] **AC2** — Employee and Manager both → `403`, `code == vocabulary.ACTION_NOT_PERMITTED`. Copy [test_cancellation_request.py:613](backend/tests/integration/test_cancellation_request.py#L613) `test_non_admin_cannot_decide`.
- [x] **AC3** — the privilege test from Task 1, plus the revised surface test.
- [x] **AC4 (SM-4) — the suite-wide one-to-one count.** This is the AC with the most room to be faked. Drive **every transition the system can perform** through the API in one test, then assert `COUNT(audit_entry) == <the exact expected number>`. The ledger, established by 2.6/2.7/2.8 and verified against the source:

  | Flow | Rows | Shape |
  |---|---|---|
  | Submit, managed | **1** | `LEAVE_REQUEST`, `NULL→PENDING`, `EMPLOYEE`, `SUBMITTED` |
  | Submit, managerless | **1** | `LEAVE_REQUEST`, `NULL→APPROVED`, **`SYSTEM`/NULL**, `AUTO_APPROVED_NO_MANAGER` |
  | Approve | **1** | `LEAVE_REQUEST`, `PENDING→APPROVED`, `EMPLOYEE`, `APPROVED` |
  | Reject | **1** | `LEAVE_REQUEST`, `PENDING→REJECTED`, `EMPLOYEE`, `REJECTED` |
  | Cancel own PENDING | **1** | `LEAVE_REQUEST`, `PENDING→CANCELLED`, `EMPLOYEE`, `CANCELLED` |
  | Raise CR | **1** | `CANCELLATION_REQUEST`, `NULL→PENDING`, `EMPLOYEE`, `CANCELLATION_REQUESTED` |
  | **Approve CR** | **2** | `CANCELLATION_REQUEST` (`PENDING→APPROVED`, `APPROVED`) **+** `LEAVE_REQUEST` (`APPROVED→CANCELLED`, `CANCELLED`) |
  | Reject CR | **1** | `CANCELLATION_REQUEST`, `PENDING→REJECTED`, `REJECTED` |
  | **A refused transition (409/400/403/404)** | **0** | no transition occurred, so no row |

  A **CR raise is a transition** and writes a row — that was Story 2.8's Open Decision #3, settled as Option A. Your count must agree. Assert the total **and** the per-`subject_type` breakdown; a bare total can pass while the discriminator is wrong.
- [x] **AC5 — rollback leaves nothing.** Drive a submission that is **refused after the audit row would have been written** — the cleanest lever is `INSUFFICIENT_BALANCE` (400) on an overspending submit, or a lost-race `409`. Assert the transition's `audit_entry` count is **0** and no `leave_request` row survives. The row is inserted in the same transaction (AD-8), so the rollback takes it. There is already precedent in [test_leave_request_decide.py:665](backend/tests/integration/test_leave_request_decide.py#L665) (*"a refused 409 transition adds NO audit row"*) — extend the idea to a rolled-back *creation*, which is the case AC5 actually describes.
- [x] **AC6 — SYSTEM.** Assert on the managerless auto-approval row: `actor_type == vocabulary.ACTOR_SYSTEM`, `actor_id is None`, `reason == vocabulary.REASON_AUTO_APPROVED_NO_MANAGER`. Assert it **both in the database and through the endpoint's JSON** (`actor_id: null`, `actor_name: null`) — the endpoint assertion is what proves no human approver was fabricated *on the wire*. Precedent: [test_leave_request_submit.py:307](backend/tests/integration/test_leave_request_submit.py#L307).

- [x] Run the full suite. Baseline at HEAD is **390 passed**; import-linter **7/7** must stay green ([test_architecture.py](backend/tests/test_architecture.py) runs `lint_imports()` inside the suite — `pytest` *is* the build; there is no CI).

### Task 7 — Frontend: an Admin audit-log panel (OPTIONAL — no AC covers it)

**Read this before deciding.** The implementation-readiness report ruled explicitly on this endpoint: *"`GET /api/v1/audit-entries` (Story 2.9) … Admin-only reads with no frontend criterion. Neither the PRD nor `FR-16` requires a screen — the endpoint satisfies the requirement as written"* ([implementation-readiness-report-2026-07-10.md:594](_bmad-output/planning-artifacts/implementation-readiness-report-2026-07-10.md#L594), F-8 at :981). **Story 2.9's six ACs contain no frontend criterion.**

So: **if Task 1 runs long, cut this — it is the only thing here that no AC requires.** Epic 2 is the correctness core; the role split is the story's obligation, a screen is not.

If you build it, keep it small and mirror [features/leave/CancellationRequestsPanel.tsx](frontend/src/features/leave/CancellationRequestsPanel.tsx):

- [x] `frontend/src/api/auditEntries.ts` — `AUDIT_ENTRIES_QUERY_KEY`, an `AuditEntry` wire interface, `useAuditEntries(options?: {enabled?: boolean})` on `apiFetch<Page<AuditEntry>>('/audit-entries')`. Import `Page` from the barrel [frontend/src/api/index.ts](frontend/src/api/index.ts) — it is declared once, in `departments.ts`.
- [x] `frontend/src/features/audit/AuditLogPanel.tsx` — the established Admin gate: `const isAdmin = useMe().data?.role === ADMIN_ROLE`, pass `{ enabled: isAdmin }` so a non-Admin never issues the request, and `if (!isAdmin) return null`. Read-only table; reuse existing CSS classes (`panel`, `emp-list`, `emp-row`, `emp-summary`, `emp-error`, `muted`) — **no new CSS**.
- [x] Render a `SYSTEM` row's actor as the literal word `SYSTEM` (from `actor_type`) — **never as a person's name and never as a blank cell that reads like a missing value.** `actor_name` is `null` and that is the point of AC6.
- [x] Render `occurred_at` exactly as received. **The string `getDay` / `getUTCDay` must not appear anywhere under `frontend/src` — not even in a comment.** [backend/tests/test_frontend_no_client_day_count.py](backend/tests/test_frontend_no_client_day_count.py) line-scans for those tokens and **Stories 2.5 and 2.7 both tripped it — 2.7 tripped it inside a comment** (AD-2).
- [x] Mount in [frontend/src/App.tsx](frontend/src/App.tsx) beside `<CancellationRequestsPanel />`; export the new hook/types from the barrel.
- [x] Page-1-only, no pager — the documented app-wide pattern. Proof of correctness is `npm run build` + `npm run lint` clean (there is no frontend test runner).

---

## Dev Notes

### The shape of the code, and the layer rules that force it

`api/v1/audit_entries.py` → `services/audit.py` → `repositories/audit_entry.py`. Imports flow one way (AD-1, import-linter contract 1). Contract 2 is the one that bites: **`api/` may import neither `repositories/` nor `domain/`**, which is why the router duck-types the view as `object` and reaches role constants through `from app.services import authorization as authz` → `authz.ROLE_ADMIN` (`services/authorization.py` re-exports them precisely so `api/` can name a role without importing `domain/`). Only `services/` opens transactions; only `repositories/` issues SQL.

### AD-21: no bare enumerated strings, anywhere

[backend/tests/test_vocabulary_literals.py](backend/tests/test_vocabulary_literals.py) **AST-scans `app/` and `seed/`** and fails the build on any bare literal of an exported vocabulary value. You may not type `"LEAVE_REQUEST"`, `"SYSTEM"`, or `"ADMIN"` in `api/v1/audit_entries.py`. Everything you need already exists in [backend/app/domain/vocabulary.py](backend/app/domain/vocabulary.py) — **this story coins nothing new:**

| | |
|---|---|
| `actor_type` | `ACTOR_EMPLOYEE="EMPLOYEE"`, `ACTOR_SYSTEM="SYSTEM"` |
| `subject_type` | `SUBJECT_LEAVE_REQUEST="LEAVE_REQUEST"`, `SUBJECT_CANCELLATION_REQUEST="CANCELLATION_REQUEST"` |
| `reason` | `REASON_SUBMITTED`, `REASON_AUTO_APPROVED_NO_MANAGER`, `REASON_APPROVED`, `REASON_REJECTED`, `REASON_CANCELLED`, `REASON_CANCELLATION_REQUESTED` |
| `from_state`/`to_state` | the `STATUS_*` constants, reused |
| error code | `ACTION_NOT_PERMITTED` — **already declared, already mapped to 403** |

Values go on the wire **verbatim, UPPER_SNAKE_CASE** (AD-21). `occurred_at` is `TIMESTAMPTZ` → RFC 3339 UTC on the wire (AD-12).

### The table you are reading (do not change it)

`audit_entry`, [repositories/models.py:337](backend/app/repositories/models.py#L337), created by [alembic/versions/0006_leave_request.py](backend/alembic/versions/0006_leave_request.py):

| Column | Type | Null | Note |
|---|---|---|---|
| `id` | Uuid PK | no | `server_default uuidv7()` — time-ordered, carries creation order |
| `subject_type` | Text | no | `LEAVE_REQUEST` \| `CANCELLATION_REQUEST` |
| `subject_id` | Uuid | no | **polymorphic — deliberately NO foreign key** |
| `from_state` | Text | **yes** | NULL = a creation |
| `to_state` | Text | no | |
| `actor_type` | Text | no | `EMPLOYEE` \| `SYSTEM` |
| `actor_id` | Uuid FK→`employee.id` | **yes** | **NULL iff `actor_type='SYSTEM'`** |
| `reason` | Text | no | |
| `occurred_at` | TIMESTAMPTZ | no | set from the service's shell clock |

One CHECK: `audit_entry_system_actor_null_check` = `(actor_type = 'SYSTEM') = (actor_id IS NULL)` — a **biconditional**, so AC6's rule is already a database fact. Your `LEFT OUTER JOIN` exists precisely because this column is nullable by design.

### What is already true, and must stay true

The six write sites — [services/leave_requests.py:411](backend/app/services/leave_requests.py#L411) (submit, both branches), [:502](backend/app/services/leave_requests.py#L502) (the shared `_decide` for approve/reject/cancel), [services/cancellation.py:225](backend/app/services/cancellation.py#L225) (raise), [:317](backend/app/services/cancellation.py#L317) + [:328](backend/app/services/cancellation.py#L328) (approve CR — the two-row case), [:374](backend/app/services/cancellation.py#L374) (reject CR). `insert_audit_entry` **flushes without committing**, so the audit row lives or dies with the transition it records (AD-8). **This story changes none of it.** If you find yourself editing a service that writes audit rows, stop — you have left the story.

`rollover_run` is Story 2.10's table and is deliberately *not* part of the audit trail — AD-8 keeps it separate exactly so SM-4's one-to-one count against transitions stays literally true. **Do not read it, do not create it, do not fold it into this endpoint.**

### Gotchas this codebase has actually produced (from 2.6/2.7/2.8 reviews)

- **`onSettled`, not `onSuccess`,** for React Query invalidation — 2.7 shipped `onSuccess` and a failed mutation never refetched while the UI claimed it had. (Read-only here, but the barrel/hook conventions are shared.)
- **`flush()` assigns the `uuidv7()` id** so the audit row can name its subject in the same transaction. Read paths do not commit.
- **Integration tests skip loudly** when Postgres is unreachable — a green run that skipped everything is not a green run. Check the summary line.
- **`alembic check` must produce an empty diff.** Model and migration, same commit.

---

### Project Structure Notes

**New files** — `backend/app/services/audit.py`, `backend/app/api/v1/audit_entries.py`, `backend/alembic/versions/0008_*.py`, `backend/tests/integration/test_audit_entries.py`; optionally `frontend/src/api/auditEntries.ts`, `frontend/src/features/audit/AuditLogPanel.tsx`.

**Modified files** — `backend/app/repositories/audit_entry.py` (+`list_audit_entries`), `backend/app/repositories/models.py` (index on `AuditEntry`), `backend/app/api/v1/router.py` (+1 import, +1 `include_router`), `backend/tests/test_scoped_getters.py` (`EXEMPT`), `backend/tests/integration/test_leave_request_submit.py` (the surface assertion — **revise, do not delete**), plus `docker-compose.yml` / `.env.example` / settings / `alembic/env.py` for the role split.

No variance from the established structure. One repository module per table; one service per capability; one router per resource.

---

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.9: The Audit Trail] — the six ACs, verbatim.
- [Source: architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-8] — *"`audit_entry` holds exactly one row per state transition … inserted inside the same transaction as the transition it records, so a rolled-back transition leaves no entry. The rollover writes to `rollover_run`, a separate append-only table."*
- [Source: architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-9] — *"The application's database role is granted `INSERT` and `SELECT` on `audit_entry` and `rollover_run`, and is granted neither `UPDATE` nor `DELETE`. Alembic migrations run under the owner role. No repository exposes an update or delete method for either table. NFR-09 therefore holds against code not yet written."*
- [Source: architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-10] — authorization is a query predicate; 403 is reserved for a resource the actor may see but not act upon.
- [Source: architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-21] — one canonical vocabulary, declared once in `domain/`, transported verbatim uppercase; *prevents "SM-4's audit query under-counting on a mis-cased `subject_type`."*
- [Source: architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md#4.9 Visibility and reporting] — `GET /audit-entries` · Admin · scope all · `FR-16`, `DR-13`. *"Full audit read access belongs to the Admin alone; no Employee or Manager may read it."*
- [Source: architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md#1 Conventions] — **G3**: *"403 — denied by role grant … decided before any row is read"* vs *"404 — outside the actor's data scope."* Pagination: *"List endpoints accept `page` and `page_size`. The server enforces a maximum page size; a client requesting more receives the maximum, not the larger page. Responses carry `items`, `page`, `page_size`, `total`."*
- [Source: architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md#3 Vocabulary] — `subject_type` ∈ {`LEAVE_REQUEST`, `CANCELLATION_REQUEST`}; `actor_type` ∈ {`EMPLOYEE`, `SYSTEM`}; `reason` ⊇ {`AUTO_APPROVED_NO_MANAGER`}.
- [Source: architecture/architecture-LeaveFlow-2026-07-10/architecture.md#8. Audit] — *"`DR-16` and `SM-4` require exactly one Audit Entry per state transition, counted one-to-one, append-only"*; *"`actor_id` is a nullable foreign key, NULL exactly when the actor is `SYSTEM` — nullable rather than absent, so referential integrity survives a non-human actor."*
- [Source: module-4-erd/erd.md#AUDIT_ENTRY] — the eight columns; the `CHECK ((actor_type = 'SYSTEM') = (actor_id IS NULL))`; *"`reason` — `AUTO_APPROVED_NO_MANAGER` for a managerless auto-approval. No human approver is fabricated."*; *"A cancellation writes entries for both objects."*
- [Source: module-4-erd/erd.md#4.3 Grants] and [#4.4 Indexes] — the grant split; `audit_entry (subject_type, subject_id)` — **"The audit read surface (`FR-16`)."**
- [Source: _bmad-output/implementation-artifacts/2-6-submit-a-leave-request.md#Decision Point] — the single-Postgres-role finding and the code-layer append-only realization **that this story is meant to close**.
- [Source: _bmad-output/implementation-artifacts/2-7-decide-a-request-approve-reject-cancel.md#Dev Notes] — *"Story 2.9 (the audit trail read) adds `GET /audit-entries` (Admin-only) and the `SM-4` one-to-one count test across all transitions."* Also the precedent for **revising** the append-only surface test rather than deleting it.
- [Source: _bmad-output/implementation-artifacts/2-8-cancel-approved-leave-through-a-cancellation-request.md#Open Decision 3] — the CR raise **is** an audited transition (Option A); CR-approve writes **two** rows, discriminated by `subject_type`.
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-10.md#F-8] — `GET /audit-entries` has **no frontend criterion**; the endpoint satisfies `FR-16` as written.

---

## Open Questions (for the reviewer, not blockers)

1. **AC3's role split is the story's one genuinely new piece of infrastructure.** It touches `docker-compose.yml`, `.env.example`, settings and `alembic/env.py` — the reproducible-setup surface Story 1.1 established. If it destabilizes the one-command setup, that trade is worth surfacing rather than absorbing silently.
2. **`occurred_at` has no index and the list sorts by it.** A sequential scan is fine at Epic-2 volume. If the audit log is expected to be the largest table in the system (it will be — it grows with every transition forever), an `occurred_at DESC` index is the obvious follow-up. Not shipped here because the ERD does not name it and this story does not own that decision.
3. **Page-1-only is app-wide, and the audit log is the list where it hurts most** — 50 rows of an ever-growing table. The pager remains deferred (`deferred-work.md`), but this endpoint is the strongest argument yet for closing that deferral.

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (`claude-opus-4-8[1m]`) — BMad `dev-story` workflow.

### Debug Log References

Backend suite (host, real PostgreSQL 18.4, `.venv/bin/python -m pytest tests/ -q`):

- Baseline at `83096b2` (HEAD): **390 passed**.
- Final: **405 passed, 0 failed, 0 skipped** (+15 new). No integration test skipped — the run is green *and* it actually connected.
- `lint-imports`: **7 contracts kept, 0 broken.**
- Frontend: `npm run build` ✅ · `npm run lint` (oxlint) ✅ — no warnings.
- Migration verified in both directions against the live database: `upgrade head` → `downgrade -1` (role and index both gone) → `upgrade head` again (idempotent re-create). `python -m seed` re-run under the new app role: exit 0.

Two failures were hit and fixed during the run, both worth recording:

1. **`test_migration_smoke.py::test_alembic_version_exists_and_is_stamped_at_head`** — `HEAD_REVISION` was pinned at `0007_cancellation_request`. Expected: the constant advances one story at a time, by design. Bumped to `0008_audit_read_surface`.
2. **My own AC4 tiebreak-premise assertion** — I filtered the CR-approve row pair by `to_state == CANCELLED`, which also caught the *cancel-own-PENDING* row (`PENDING → CANCELLED`) from a different transaction with its own clock reading, so two `occurred_at` values appeared where one was asserted. The system was right and the test was wrong; the filter now selects the pair by `(subject_id, to_state)`. Worth noting because **the SM-4 count itself (14) and the per-`subject_type` breakdown passed on the first run** — the ledger in the story was exactly right.

### Completion Notes List

**AC3 IS MET — the role split shipped. This is the headline, so it is stated plainly rather than buried.** The story authorised declaring AC3 *not met* if the split proved infeasible. It did not prove infeasible, and no fallback was taken. Verified against the live database, connected **as the application role**:

```
connected as: leaveflow_app   (rolsuper = False)
audit_entry:  SELECT True · INSERT True · UPDATE False · DELETE False
leave_request: SELECT/INSERT/UPDATE/DELETE all True
UPDATE audit_entry SET reason = … →  REFUSED  psycopg.errors.InsufficientPrivilege
DELETE FROM audit_entry          →  REFUSED  psycopg.errors.InsufficientPrivilege
```

The 2.6 Decision Point is therefore **closed, not re-declared.** Both clauses of AC3 hold: the database refuses (`test_audit_entries.py::test_the_database_refuses_to_mutate_the_trail`, asserting on the *privilege* error specifically, against a row proven to exist first), and no repository exposes an update or delete (the revised surface test). Alembic still runs under the owner (`alembic/env.py` → `database_url`), as AC3's third clause requires.

**How the role is provisioned, and why not in the container's init path.** Migration `0008` creates it, as the owner. The postgres image's `/docker-entrypoint-initdb.d` runs **only on a fresh data directory**, so a role created there would never appear in any database that already exists — including every developer's and every deployed one. Creating it in the owner-run migration keeps setup at **three commands** (NFR-21/AC1: nothing new to run), provisions existing databases on the next `alembic upgrade head`, and re-syncs a rotated `APP_DB_PASSWORD` on the next upgrade. Role name and password are quoted by `psycopg.sql.Identifier`/`Literal`, not by a format string — a password containing a quote is otherwise an injection.

**⚠️ AC5's suggested lever does not work in this codebase, and I did not pretend it did.** The story proposed proving AC5 with an `INSUFFICIENT_BALANCE` (400) submission. But `reserve`/`consume_direct` raise that refusal **under the balance lock, before `insert_leave_request` and before the audit call** ([services/leave_requests.py:370-420](backend/app/services/leave_requests.py#L370-L420)) — so *no audit row is ever written on that path*. A test that refused a submission and then found no audit row would be asserting that a row **nobody wrote** does not exist: it would pass vacuously, and would keep passing even if `insert_audit_entry` started committing on its own. Same for the 409s: every guarded transition refuses before its audit call.

AC5's *"because"* clause is a claim about the **mechanism** — "the row was inserted inside that transaction" — so the mechanism is what I test. `test_a_rolled_back_transition_leaves_no_audit_row` drives the same two repository calls a real submit makes, in one transaction, **asserts the audit row IS visible inside that transaction** (otherwise the rollback would prove nothing), rolls back, and proves from a *separate* session that both the request and its audit row are gone. The refused-submission case is still covered — as the weaker check it honestly is — and the refused-409 case sits in the SM-4 ledger, where it belongs as a transition writing 0 rows.

**Three landmines, all as advertised, all handled as instructed:**

1. **Surface test** — widened to `{insert_audit_entry, list_audit_entries}` and **revised, not deleted, and not routed around** with a sibling `repositories/audit.py`. Its docstring now says what it still guarantees now that the GRANT is the binding one: it stops a mutator from ever being *written*, which fails at import time with a name, rather than at runtime on the first row it tried to rewrite. Two layers; the cheaper one fails first.
2. **Scoped-getters** — `list_audit_entries` added to `EXEMPT` with the "why exempt" rationale in *both* the registry and the function's own docstring (the trail has no Employee-owner column; `actor_id` is who *acted*, not who *owns*; the gate is the Admin role in `api/`, before the query runs).
3. **The `occurred_at` tie** — `ORDER BY occurred_at DESC, id DESC`. The tie is **real and now asserted as such**: the test proves the CR-approve's two rows share one `occurred_at`, so the tiebreak's reason for existing cannot silently lapse. A separate test pages the whole trail one row at a time and asserts every id appears exactly once — the sharpest available proof that the sort is a total order.

**The LEFT OUTER JOIN** (the story's "single most likely way to get this story wrong") is asserted from the outside: the AC1 test puts a `SYSTEM` row in the fixture and asserts it **appears in the response**. An inner join would have made that row simply *absent* — not wrong, absent — which is the failure mode a schema-shape assertion would never catch.

**`actor_name` stays `null` for SYSTEM rows** through the repository, the service and the wire. No placeholder is substituted anywhere in the backend. The (optional) frontend renders the literal word `SYSTEM` from `actor_type` — chosen in the view, so the *absence of a name* remains a fact about the data all the way down.

**Scope discipline:** no service that writes an audit row was touched; no new vocabulary constant; no new error code; no `main.py` change (`ACTION_NOT_PERMITTED` was already mapped to 403); no filters; not registered in the SM-3 scope matrix (no path parameter, so it is out by construction). No index the ERD does not name — in particular, **no index on `occurred_at`**, which this list actually sorts by (see Open Question 2 — it is the obvious follow-up and this story does not own it).

**Task 7 (frontend) was built.** It is the one thing here no AC requires (readiness report F-8), and the story said to cut it first if Task 1 ran long. Task 1 did not run long, so it shipped: read-only Admin panel, existing CSS classes only, page-1-only per the app-wide pattern, and the AD-2 `getDay`/`getUTCDay` scan is clean (stories 2.5 and 2.7 both tripped it; 2.7 inside a *comment*).

**Beyond the task list — three things I added, each with a reason:**

- **`--sql` (offline) mode is refused loudly** by `0008`. It cannot work (the role bootstrap must ask a live database whether the role exists — `CREATE ROLE` has no `IF NOT EXISTS`), and it *must not* work: an emitted script would carry `APP_DB_PASSWORD` as a plaintext literal into a file someone would paste, commit or mail. Failing with a sentence beats leaking a credential in a script that does not run anyway.
- **Test cleanup moved to the owner engine** in the three files that delete audit rows (`test_leave_request_submit`, `test_leave_request_decide`, `test_cancellation_request`) plus the new one. Their teardown would otherwise be **refused by the app role — which is AC3 working, not a bug**. `conftest` now exposes an `owner_engine` fixture, and each comment says why, so the next reader does not "fix" it by granting the app role `DELETE` and quietly deleting AC3.
- **`conftest` skips loudly if the app role cannot connect.** "Postgres is up but the app role does not exist" is a real state — it is precisely a database on which setup command two has not been run. Unchecked, it would surface as a hard `OperationalError` inside the first test, where the module's entire purpose is an actionable skip. It now names the fix (`alembic upgrade head`).
- **`seed` now runs as the app role** (it writes only domain rows, and needs no privilege the app lacks). This makes setup command three a **live check of the grants**: a missed grant fails at setup, loudly, rather than at the first request that happens to touch the ungranted table. Verified: `python -m seed` → exit 0.

**🔧 OPERATOR ACTION REQUIRED — two of them.**

1. **`.env` needs two new keys**: `APP_DB_USER` and `APP_DB_PASSWORD`. Both are documented in `.env.example` (with the *why*), and `docker-compose.yml` interpolates them with the `:?` guard, so a missing value fails `docker compose up` by name rather than crash-looping. The local gitignored `.env` has been updated so the suite runs.
2. **The running `api` container must be recreated** to pick up the new environment. It has been up for two days on the old env and does not know `APP_DB_USER`; on restart, `settings.py` will refuse to boot without it (deliberately — a placeholder or absent credential must fail at startup, not connect as the wrong role). `docker compose` is not available in this shell, so I could not do it: **run `docker compose up -d --force-recreate api`.** The test suite runs host-side against the published port and is unaffected, which is why it is green while the container is stale.

### File List

**New**

- `backend/alembic/versions/0008_audit_read_surface.py` — the app role, its grants (`INSERT, SELECT` on `audit_entry`; the four verbs elsewhere), and ERD §4.4's `ix_audit_entry_subject`
- `backend/app/services/audit.py` — `AuditEntryView` + `list_audit_entries` (read path, no commit)
- `backend/app/api/v1/audit_entries.py` — `GET /api/v1/audit-entries`, Admin-only
- `backend/tests/integration/test_audit_entries.py` — AC1–AC6 (11 tests)
- `frontend/src/api/auditEntries.ts` — `useAuditEntries`, `AuditEntry`, `AUDIT_ENTRIES_QUERY_KEY`
- `frontend/src/features/audit/AuditLogPanel.tsx` — the Admin panel (optional; no AC)

**Modified**

- `backend/app/core/settings.py` — the two-role split: `app_db_user`/`app_db_password`/`app_database_url`, the shared `_url_for` builder, placeholder guard extended
- `backend/app/repositories/engine.py` — the app engine now connects as the **app role** (`app_database_url`)
- `backend/app/repositories/audit_entry.py` — `+ list_audit_entries` (outer join, `occurred_at DESC, id DESC`), `_READ_COLUMNS`
- `backend/app/repositories/models.py` — `Index("ix_audit_entry_subject", …)` on `AuditEntry`
- `backend/app/api/v1/router.py` — `+ audit_entries` import and `include_router`
- `backend/seed/__main__.py` — seeds as the app role, so command three checks the grants
- `backend/tests/integration/conftest.py` — `owner_engine` fixture; app-role connection proved (loud skip)
- `backend/tests/integration/test_leave_request_submit.py` — **revised** surface assertion (Landmine 1); cleanup as owner
- `backend/tests/integration/test_leave_request_decide.py` — cleanup as owner
- `backend/tests/integration/test_cancellation_request.py` — cleanup as owner
- `backend/tests/integration/test_migration_smoke.py` — `HEAD_REVISION` → `0008_audit_read_surface`
- `backend/tests/test_scoped_getters.py` — `list_audit_entries` in `EXEMPT` (Landmine 2)
- `backend/tests/test_migrations_insert_nothing.py` — `0008` in the ordered chain
- `frontend/src/api/index.ts` — barrel exports for the audit hook/types
- `frontend/src/App.tsx` — mounts `<AuditLogPanel />`
- `docker-compose.yml` — `APP_DB_USER` / `APP_DB_PASSWORD` to the `api` service
- `.env.example` — the app-role section, and why two roles exist

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-14 | Story 2.9 implemented. `GET /api/v1/audit-entries` (Admin-only, paged, newest-first with an `id` tiebreak). **AD-9's grant guarantee made real**: migration `0008` provisions a non-owner application role granted `INSERT, SELECT` on `audit_entry` and neither `UPDATE` nor `DELETE` — Postgres now refuses both with `InsufficientPrivilege`, closing the Story 2.6 Decision Point rather than re-declaring it. ERD §4.4's `ix_audit_entry_subject` shipped. SM-4 proven one-to-one (14 rows) across every transition the system can perform, total *and* per-`subject_type`. No write path, vocabulary constant, error code or `main.py` mapping changed. Backend **405 passed** (from 390), import-linter **7/7 kept**; frontend build + lint clean. Operator: add `APP_DB_USER`/`APP_DB_PASSWORD` to `.env` and recreate the `api` container. |
