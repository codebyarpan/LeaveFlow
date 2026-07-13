---
baseline_commit: 4dc28aabcac56eafd086c5eea5c48624d6aaa751
---

# Story 2.6: Submit a Leave Request

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an **Employee**,
I want **to apply for leave and have its days reserved immediately**,
so that **a request I have made cannot be spent twice**.

This is the first **write** in the Leave Request lifecycle. Stories 2.3 (the day count), 2.4 (the balance quantities + the AD-17 mutation module) and 2.5 (the advisory preview) built every piece this story now composes into a single atomic command: `POST /api/v1/leave-requests`. It also creates the two lifecycle tables (`leave_request`, `audit_entry`), makes Story 1.6's `EMPLOYEE_HAS_PENDING_REQUESTS` guard executable, and owns the `SM-1` concurrent-double-submit correctness test.

## Acceptance Criteria

> Verbatim from `epics.md` §"Story 2.6" (lines 1051–1089). BDD blocks numbered AC1–AC8 for task traceability.

**AC1 — `leave_request` schema (migration by this story)**
**Given** a database migrated by this story
**When** the schema is inspected
**Then** `leave_request` carries `start_date` and `end_date` as `DATE`, `leave_days` as `INTEGER`, and `status` as `TEXT` with `CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED'))`, plus `CHECK (end_date >= start_date)` and `CHECK (leave_days > 0)`
**And** it carries **no `created_at`** and **no `leave_year`** column (ERD §2.1, §4.5).

**AC2 — `audit_entry` schema + append-only guarantee**
**Given** the first state transition in the system
**When** `audit_entry` is created by this story
**Then** it carries `subject_type`, `subject_id`, `from_state`, `to_state`, `actor_type`, `actor_id`, `reason`, `occurred_at`, with `CHECK ((actor_type = 'SYSTEM') = (actor_id IS NULL))`
**And** the application's database role is granted `INSERT` and `SELECT` on it and **neither `UPDATE` nor `DELETE`**, with migrations running as the owner (`AD-8`, `AD-9`). **See the Decision Point in Dev Notes — the codebase currently runs a single Postgres role; the binding, testable form of "append-only" is the code-layer one (no repository update/delete method for either table).**

**AC3 — the submission command (happy path)**
**Given** an authenticated Employee with a Manager
**When** they call `POST /api/v1/leave-requests`
**Then** `leave_days` is computed **once** by Story 2.3's `count_leave_days` and stored, and no read path ever recomputes it (`FR-08`, `AD-18`)
**And** the balance row is acquired with `SELECT ... FOR UPDATE`, `available` is computed **from that locked row inside that transaction**, the days are `reserve`d, and **one** Audit Entry is written in the **same** transaction (`FR-08`, `AD-3`, `AD-8`).

**AC4 — the domain refusals (all `400`, all under the lock)**
**Given** a submission the domain refuses
**When** the response is returned
**Then** it is `400` carrying the matching code: `INSUFFICIENT_BALANCE` naming `days_requested` and `days_available`; `SPANS_TWO_LEAVE_YEARS` naming the boundary; `ZERO_LEAVE_DAYS`; `INVALID_DATE_RANGE`; or `PAST_DATE_RANGE`
**And** the refusal is raised by the service (never surfaced from a `CHECK` violation, which would be a defect and a `500`) (`FR-08`, `AD-5`, `NFR-17`).

**AC5 — managerless auto-approval (FR-09)**
**Given** an applicant whose `manager_id` is NULL
**When** they submit
**Then** the request is admitted directly as `APPROVED`, consuming its days through `consume_direct` **without ever touching `reserved`**
**And** its Audit Entry names actor type `SYSTEM` and reason `AUTO_APPROVED_NO_MANAGER`, and the Available check **still applied** (`FR-09`, `AD-17`).

**AC6 — concurrency (SM-1, real PostgreSQL)**
**Given** two concurrent submissions that would together exceed Available
**When** both are attempted against real PostgreSQL
**Then** **exactly one** succeeds and the other is refused with `INSUFFICIENT_BALANCE`
**And** the balance is **neither negative nor double-counted** (`SM-1`, `NFR-07`, spine *Testing*).

**AC7 — the pending-request deactivation guard becomes executable**
**Given** an Employee holding a Pending Leave Request
**When** an Admin attempts to deactivate them
**Then** the response is `409` with `EMPLOYEE_HAS_PENDING_REQUESTS` — Story 1.6's criterion becomes executable here (`AD-22`).

**AC8 — the frontend submission slice**
**Given** the React application and an authenticated Employee
**When** they submit a request
**Then** their Available balance falls **immediately** by the reserved days, and a refusal states its numbers (`NFR-17`).

---

## Tasks / Subtasks

> Ordered so each task compiles and tests green before the next. Backend first (schema → vocabulary → repository → service → route), then the deactivation guard, then guard-test updates, then the frontend, then the SM-1 test, then gates.

- [x] **Task 1 — Migration `0006_leave_request` + the two models (AC1, AC2)**
  - [x] Add `class LeaveRequest(Base)` to [backend/app/repositories/models.py](backend/app/repositories/models.py) (`__tablename__ = "leave_request"`). Columns: `id` (`Uuid`, PK, `server_default=text("uuidv7()")`), `employee_id` (`ForeignKey("employee.id")`, NOT NULL), `leave_type_id` (`ForeignKey("leave_type.id")`, NOT NULL), `start_date`/`end_date` (`Mapped[datetime.date]`, NOT NULL → `DATE`), `leave_days` (`Mapped[int]`, NOT NULL), `status` (`Mapped[str]`, `Text`, NOT NULL). **No `created_at`, no `leave_year`** (ERD §4.5 — the year is derivable from `start_date`; ordering comes from the UUIDv7 PK). `__table_args__`: `CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CANCELLED')", name="leave_request_status_check")`, `CheckConstraint("end_date >= start_date", name="leave_request_date_order_check")`, `CheckConstraint("leave_days > 0", name="leave_request_leave_days_positive_check")`, and the two ERD §4.4 indexes: `Index("ix_leave_request_employee_status", "employee_id", "status")` and `Index("ix_leave_request_start_end", "start_date", "end_date")`.
  - [x] Add `class AuditEntry(Base)` (`__tablename__ = "audit_entry"`). Columns: `id` (PK, uuidv7), `subject_type` (`Text`, NOT NULL), `subject_id` (`Uuid`, NOT NULL — **polymorphic, NO foreign key**, ERD §2), `from_state` (`Text`, **nullable** — a creation has no from-state), `to_state` (`Text`, NOT NULL), `actor_type` (`Text`, NOT NULL), `actor_id` (`Uuid`, `ForeignKey("employee.id")`, **nullable** — NULL iff SYSTEM), `reason` (`Text`, NOT NULL — carry `AUTO_APPROVED_NO_MANAGER` / a submit reason), `occurred_at` (`Mapped[datetime.datetime]` → `TIMESTAMP WITH TIME ZONE`, NOT NULL). `__table_args__`: `CheckConstraint("(actor_type = 'SYSTEM') = (actor_id IS NULL)", name="audit_entry_system_actor_null_check")`.
  - [x] Create [backend/alembic/versions/0006_leave_request.py](backend/alembic/versions/0006_leave_request.py) with `revision = "0006_leave_request"`, `down_revision = "0005_leave_balance"`. `upgrade()` creates **both** tables via `op.create_table`, constraint `name=` **byte-identical** to the model `__table_args__`. Follow the [0005_leave_balance.py](backend/alembic/versions/0005_leave_balance.py) shape exactly (native `uuidv7()`, `sa.ForeignKeyConstraint`, `sa.PrimaryKeyConstraint`, named `sa.CheckConstraint`, `op.create_index` for the two indexes). `downgrade()` drops both. **No `INSERT`/DML** (AD-11 — `test_migrations_insert_nothing.py` fails on any `insert()`).
  - [x] Decide the `audit_entry` grant question — see **Decision Point (AD-9)** in Dev Notes. Default: implement the code-layer append-only guarantee (Task 4/its repository), and add a `GRANT`/`REVOKE` DDL block only if a distinct application role is introduced; otherwise record the single-role rationale in the migration docstring and the Dev Agent Record.

- [x] **Task 2 — Vocabulary: the status constants + five new codes (AC1, AC4, AC5, AC7)**
  - [x] In [backend/app/domain/vocabulary.py](backend/app/domain/vocabulary.py) add the four Leave Request statuses as constants (`STATUS_PENDING = "PENDING"`, `STATUS_APPROVED = "APPROVED"`, `STATUS_REJECTED = "REJECTED"`, `STATUS_CANCELLED = "CANCELLED"`), the four range-refusal error codes (`ZERO_LEAVE_DAYS`, `SPANS_TWO_LEAVE_YEARS`, `INVALID_DATE_RANGE`, `PAST_DATE_RANGE`), `EMPLOYEE_HAS_PENDING_REQUESTS`, and the audit vocabulary needed now: `ACTOR_EMPLOYEE = "EMPLOYEE"`, `ACTOR_SYSTEM = "SYSTEM"`, `SUBJECT_LEAVE_REQUEST = "LEAVE_REQUEST"`, `REASON_AUTO_APPROVED_NO_MANAGER = "AUTO_APPROVED_NO_MANAGER"` (and a submit reason, e.g. `REASON_SUBMITTED` if you name the PENDING transition's reason — check the AuditEntry `reason` NOT NULL decision below). Add **every** new name to `__all__`. Follow the existing per-code comment discipline (declare the code **with** its raise site — this is exactly why `EMPLOYEE_HAS_PENDING_REQUESTS` was withheld from Story 1.6; its raise site now exists).
  - [x] `INSUFFICIENT_BALANCE` is **already declared** (Story 2.4, [vocabulary.py:148](backend/app/domain/vocabulary.py#L148)) and already mapped to 400 — **do not redeclare it**. This story merely calls `reserve`, which raises it.
  - [x] **Do not** introduce `ROLE_*`-style literals or reuse the DB `CHECK` literal outside `vocabulary.py`/the model/migration — `test_vocabulary_literals.py` AST-scans `app/` and `seed/` and fails on any bare enumerated string. The `status IN (...)` and `actor_type = 'SYSTEM'` literals in the model `__table_args__` and the migration are the **only** exempt copies (the migration `alembic/versions/` path and the model mirroring it), exactly as `employee.role`'s check is exempt.

- [x] **Task 3 — Wire the five codes to statuses in the composition root (AC4, AC7)**
  - [x] In [backend/app/main.py](backend/app/main.py) `CODE_TO_STATUS.update({...})` add: `vocabulary.ZERO_LEAVE_DAYS: 400`, `vocabulary.SPANS_TWO_LEAVE_YEARS: 400`, `vocabulary.INVALID_DATE_RANGE: 400`, `vocabulary.PAST_DATE_RANGE: 400`, `vocabulary.EMPLOYEE_HAS_PENDING_REQUESTS: 409` (api-contracts §2, lines 77–87). Statuses are set **here only** — `api/v1/errors.py` may import neither `domain/` nor the vocabulary (contract 2).

- [x] **Task 4 — Repositories: write `leave_request`/`audit_entry`, and the pending-count read (AC3, AC5, AC7)**
  - [x] New [backend/app/repositories/leave_request.py](backend/app/repositories/leave_request.py): an `insert_leave_request(session, *, employee_id, leave_type_id, start_date, end_date, leave_days, status) -> LeaveRequest` (build, `session.add`, `session.flush()` to assign the uuidv7 `id`, return the row), and `count_pending_for_employee(session, employee_id) -> int` (name it `count_*`, **not** `get_/list_/find_/fetch_`, so it is not a scoped-getter candidate — mirrors `count_active_direct_reports`; the deactivation guard already knows the target employee, no `actor` scoping). Expose **no** update or delete method (AD-8 append-only intent extends to the request row's lifecycle transitions, which are Story 2.7's guarded `UPDATE`).
  - [x] New [backend/app/repositories/audit_entry.py](backend/app/repositories/audit_entry.py): `insert_audit_entry(session, *, subject_type, subject_id, from_state, to_state, actor_type, actor_id, reason, occurred_at) -> None` (INSERT + flush). **INSERT and SELECT only — no update, no delete method** (AD-8). This is the code-layer realization of AC2's append-only guarantee.

- [x] **Task 5 — The submission command in `services/leave_requests.py` (AC3, AC4, AC5)**
  - [x] **Extend** [backend/app/services/leave_requests.py](backend/app/services/leave_requests.py) — **do not create a new file**; add `submit_leave_request(actor, *, leave_type_id, start, end) -> <view>` alongside the existing `preview_leave_request`. Add typed-refusal factories following the `_insufficient_balance`/`_employee_has_direct_reports` idiom: one module-level `_XXX_MESSAGE` + a `def _xxx(...) -> DomainError` per new code, `details` carrying the numbers (`SPANS_TWO_LEAVE_YEARS` → `details={"boundary": "<YYYY-12-31>"}` or the boundary date the range crosses).
  - [x] The command opens **one** write transaction: `with Session(get_engine(), expire_on_commit=False) as session:` … `session.commit()` inside (AD-3, the `create_employee`/`create_leave_type` precedent). Sequence **inside** the transaction:
    1. **Pure range validity (pre-lock, order matters):** `INVALID_DATE_RANGE` if `end < start`; `PAST_DATE_RANGE` if the range lies wholly in the past (compare against `date.today()` obtained in the service shell, AD-1 — decide and document the "wholly past" rule: `end < today`); `SPANS_TWO_LEAVE_YEARS` if `start.year != end.year`, naming the boundary. Put the pure predicates in `domain/` (a `domain.calendar` or a small `domain/leave_request_rules` helper) so they are DB-free-testable and `domain/`-pure; the service raises the typed `DomainError`. **Do not** put these in `count_leave_days` — Story 2.3/2.5 deliberately kept that function total and permissive; range validity is 2.6's.
    2. `leave_year = start.year` (a single-year request by rule 1's guard). Read Company Holidays in `[start, end]` via `holiday_repo.holidays_in_range(session, start, end)` and build the `{holiday_date: name}` map (reuse the preview's shape).
    3. `leave_days = calendar.count_leave_days(start, end, holiday_map.keys())` — the **sole** day-count authority (AD-2). If `leave_days == 0` → raise `ZERO_LEAVE_DAYS`.
    4. **Branch on `actor.manager_id`** (read the applicant's `manager_id`):
       - **Has a manager** → `balances.reserve(session, employee_id=actor.id, leave_type_id=leave_type_id, leave_year=leave_year, days=leave_days)`. `reserve` acquires the row `SELECT … FOR UPDATE` and raises `INSUFFICIENT_BALANCE` from the **locked** row before any write (AD-3/AD-5). Then `insert_leave_request(status=STATUS_PENDING)` and `insert_audit_entry(subject_type=SUBJECT_LEAVE_REQUEST, subject_id=<new request id>, from_state=None, to_state=STATUS_PENDING, actor_type=ACTOR_EMPLOYEE, actor_id=actor.id, reason=<submit reason>, occurred_at=<now>)`.
       - **`manager_id is None`** → `balances.consume_direct(...)` (**never touches `reserved`**; the Available check still fires, AC5). Then `insert_leave_request(status=STATUS_APPROVED)` and `insert_audit_entry(from_state=None, to_state=STATUS_APPROVED, actor_type=ACTOR_SYSTEM, actor_id=None, reason=REASON_AUTO_APPROVED_NO_MANAGER, occurred_at=<now>)`.
    5. `session.commit()`. Return the stored row (or a frozen view dataclass) so the route projects it. `leave_days` is now frozen on the row (AD-18) — no read path recomputes it.
  - [x] **Lock order (AD-3):** balance rows are locked **before** request rows; a single balance row here, so order is trivial, but do the `reserve`/`consume_direct` (which locks the balance) **before** inserting the request row.
  - [x] **Clock in the shell (AD-1):** `occurred_at` and "today" come from `datetime` in the service, never from `domain/`. Reuse/extend the existing `_current_leave_year()` pattern.

- [x] **Task 6 — The `POST /leave-requests` route (AC3, AC8)**
  - [x] **Extend** [backend/app/api/v1/leave_requests.py](backend/app/api/v1/leave_requests.py) — add the route to the existing router (already `include_router`-ed in [router.py](backend/app/api/v1/router.py); **no router change needed**). `@router.post("/leave-requests", status_code=status.HTTP_201_CREATED, tags=["leave-requests"])`, guard `Depends(get_current_employee)` (scope `self` is intrinsic to the token subject — **not** `require_role`; api-contracts §4.5 line 169: role `any`, scope `self`).
  - [x] New `SubmitRequest(BaseModel)`: `leave_type_id: uuid.UUID`, `start_date: date`, `end_date: date`. Add the **same defensive span cap** as `PreviewRequest` (`_MAX_PREVIEW_SPAN_DAYS = 366` → 422 `model_validator`) — an unbounded range is a CPU/memory exhaustion vector; the real `SPANS_TWO_LEAVE_YEARS` refusal is the domain error under lock, the cap is framework input-validation (no new code). Consider extracting the shared validator so preview and submit share it.
  - [x] `SubmitResponse(BaseModel)`: project the created request — `id`, `leave_type_id`, `start_date`, `end_date`, `leave_days`, `status`. Project **by hand** in a `_to_response(view: object)` (typed `object`; `api/` may not import the ORM or service dataclass — the `balances.py`/preview precedent). No `from_attributes`. `leave_days` is read from the stored value, never recomputed (AD-18).

- [x] **Task 7 — Make `EMPLOYEE_HAS_PENDING_REQUESTS` executable in deactivation (AC7)**
  - [x] In [backend/app/services/employee.py](backend/app/services/employee.py) `deactivate_employee` (line 327): after the existing `count_active_direct_reports` guard, add the pending-request guard — `if leave_request_repo.count_pending_for_employee(session, employee.id) > 0: raise _employee_has_pending_requests(count)`. Add the typed-refusal factory `_employee_has_pending_requests(pending: int) -> DomainError` (code `EMPLOYEE_HAS_PENDING_REQUESTS`, `details={"pending_requests": pending}`), mirroring `_employee_has_direct_reports` ([employee.py:90](backend/app/services/employee.py#L90)). Update the docstring at [employee.py:334-336](backend/app/services/employee.py#L334) — it currently says the guard "lands in Epic 2, when `leave_request` exists … Deliberately NOT queried here." That "when" is now.
  - [x] Decide the ordering vs. `EMPLOYEE_HAS_DIRECT_REPORTS` and document it (both are 409; either is a valid refusal; pick a deterministic order and note it).

- [x] **Task 8 — Update the four table-aware architecture guards (AC1, AC2)**
  - [x] [backend/tests/integration/test_schema_1_2.py](backend/tests/integration/test_schema_1_2.py) `test_exactly_the_expected_tables_exist` — add `"leave_request"` and `"audit_entry"` to the expected set (line ~41). Exact-set equality; both new tables must appear.
  - [x] [backend/tests/test_migrations_insert_nothing.py](backend/tests/test_migrations_insert_nothing.py) — add `"0006_leave_request.py"` to the ordered revision-chain list (near line 126).
  - [x] [backend/tests/integration/test_migration_smoke.py](backend/tests/integration/test_migration_smoke.py) — bump `HEAD_REVISION = "0006_leave_request"` (line 19) and add a smoke test asserting `leave_request`/`audit_entry` shipped with their columns, CHECKs and indexes (mirror `test_leave_balance_table_shipped_...` at line 122).
  - [x] [backend/tests/integration/test_model_migration_agreement.py](backend/tests/integration/test_model_migration_agreement.py) runs `alembic check` — no edit needed, but it fails the build if any model/migration constraint `name` differs. Verify green.
  - [x] No new **identifier** (`/<id>`) endpoint is added by this story (those are Story 2.7), so `test_scope_matrix.py` needs no new registration here.

- [x] **Task 9 — Domain unit tests, DB-free (AC4)**
  - [x] New [backend/tests/domain/](backend/tests/domain/) test for the pure range-validity predicates (`INVALID_DATE_RANGE`, `PAST_DATE_RANGE` boundary, `SPANS_TWO_LEAVE_YEARS` boundary, `ZERO_LEAVE_DAYS` via `count_leave_days == 0`). No `db_connection` fixture — stdlib + the pure function + `vocabulary` only, the `test_calendar.py`/`test_excluded_dates.py` template. Assert the boundary date carried by `SPANS_TWO_LEAVE_YEARS`.

- [x] **Task 10 — Integration tests incl. SM-1 concurrency, real PostgreSQL (AC3, AC4, AC5, AC6, AC7)**
  - [x] New [backend/tests/integration/test_leave_request_submit.py](backend/tests/integration/test_leave_request_submit.py). Reuse the `_World` fixture shape from [test_leave_request_preview.py](backend/tests/integration/test_leave_request_preview.py) (Department + Employee + LeaveType + materialized balance via `leave_types_service.create_leave_type`, token via `security.create_token`, `TestClient(app)`, `_auth(token)` header, teardown in `finally`). Assert: happy PENDING path stores `leave_days` and moves `reserved` up by exactly that; each of the five refusals returns 400 with its code + `details`; the managerless applicant is auto-`APPROVED` via `consume_direct` (`reserved` stays 0, `consumed` rises) with a `SYSTEM`/`AUTO_APPROVED_NO_MANAGER` audit row; exactly one `audit_entry` row per submission; the balance CHECK never surfaces (an overspend is a typed 400, not a 500); AC7 — an Admin deactivating an Employee who holds a Pending request gets 409 `EMPLOYEE_HAS_PENDING_REQUESTS`.
  - [x] **SM-1 concurrent double-submit (AC6):** two submissions that together exceed Available, run **concurrently** against real PostgreSQL (two sessions/connections, the second blocking on `SELECT … FOR UPDATE`). Assert **exactly one** succeeds and the other is 400 `INSUFFICIENT_BALANCE`, and the final balance is neither negative nor double-counted. This is the test Story 2.4 built `reserve` lock-correct for. Note the conftest **skips loudly** if Postgres is unreachable — SQLite cannot serve this (no real `FOR UPDATE`).

- [x] **Task 11 — Frontend submission slice (AC8)**
  - [x] Extend [frontend/src/api/leaveRequests.ts](frontend/src/api/leaveRequests.ts): add `useSubmitLeaveRequest()` — a `useMutation` calling `apiFetch('/leave-requests', {method:'POST', body})`, and on success `queryClient.invalidateQueries` for the balances query so **Available falls immediately** (AC8). Mirror the `usePreviewLeaveRequest` + `useCreateLeaveType`/`useCreateHoliday` idiom. Export via the barrel [frontend/src/api/index.ts](frontend/src/api/index.ts).
  - [x] Extend [frontend/src/features/leave/](frontend/src/features/leave/) (currently `RequestPreviewPanel.tsx`) into the full submission form — a Submit button that posts the previewed range, renders the returned `status`/`leave_days`, and **renders the server's refusal `details` numbers** on a 400 (AC8: "a refusal states its numbers"). Reuse the existing form state + CSS classes. **No client day count** — render server figures as-is (`test_frontend_no_client_day_count.py` line-scans for `getDay`/`getUTCDay`; do not write those tokens even in a comment/docstring — Story 2.5 tripped this).
  - [x] Mount in `AppShell` in [frontend/src/App.tsx](frontend/src/App.tsx) if not already surfaced.

- [x] **Task 12 — Full gate pass**
  - [x] `cd backend && pytest` — all pass (baseline is **310** after Story 2.5; expect the count to rise). Fix any armed guard this story touches (schema/migration set, vocabulary literals, module surface).
  - [x] `cd frontend && npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean.
  - [x] Record a manual click-through of submit → Available-falls in the Dev Agent Record (honestly note if the running Docker image predates the change).

---

## Review Findings

> Code review 2026-07-13 (adversarial: Blind Hunter · Edge Case Hunter · Acceptance Auditor). 2 decision-needed, 2 patch, 3 deferred, 3 dismissed. Acceptance Auditor: all 8 ACs and all named invariants (AD-1/2/3/5/8/17/18/21, DR-10) satisfied — no AC violations.

- [x] [Review][Decision→Accepted] **AD-9 append-only realized at the code layer only (AC2)** — RESOLVED 2026-07-13 (option a): accept code-layer append-only (repo surface exposes no update/delete method for `audit_entry`/`leave_request`); the DB-role `GRANT`/`REVOKE` split is deferred pending a least-privilege role (a REVOKE on the single owning Postgres role is a no-op). Rationale recorded in the `0006` migration docstring + Dev Agent Record. [backend/app/repositories/audit_entry.py, backend/alembic/versions/0006_leave_request.py]
- [x] [Review][Patch] **Submit returns 500 (not 404) on a missing balance row** — FIXED 2026-07-13 (option a: mirror preview). Added a non-locking `SELF`-scoped `get_balance(leave_type_id, leave_year=start.year)` guard in `submit_leave_request` before the mutate; `None` → `authz.not_found()` (404 RESOURCE_NOT_FOUND), exactly as `preview_leave_request`. Regression test `test_unknown_leave_type_is_404_not_500` added. [backend/app/services/leave_requests.py:249]
- [x] [Review][Patch] **Stale preview persists after a successful submit** — FIXED 2026-07-13. `handleSubmit` now resets the preview in an `onSuccess` callback, so after a submit the screen shows only the submitted outcome, never a pre-reservation cost figure. [frontend/src/features/leave/RequestPreviewPanel.tsx:91]
- [x] [Review][Patch] **Missing test: managerless applicant refused `INSUFFICIENT_BALANCE`** — FIXED 2026-07-13. Added `test_managerless_overspend_is_refused_insufficient_balance` — a managerless overspend is a typed 400 (not a CHECK 500), reserved AND consumed both stay 0. [backend/tests/integration/test_leave_request_submit.py]
- [x] [Review][Defer] **No duplicate / overlapping-request guard** [backend/app/services/leave_requests.py:288] — deferred, out of 2.6 scope. The same leave-type + range can be submitted twice (double-click, two tabs, or API), creating two PENDING requests that each reserve the days (bounded by Available). No AC covers overlap/duplicate detection; the frontend also keeps the form + re-enables Submit after success. Candidate for a later story.
- [x] [Review][Defer] **Deactivation guard is a TOCTOU race** [backend/app/services/employee.py:374] — deferred, pre-existing pattern. `deactivate_employee` reads `count_pending_for_employee` without locking the `employee` row; a concurrent `submit_leave_request` (which locks only the balance row) can strand a PENDING request against a now-inactive employee. Narrow interleaving; admin deactivation is effectively serial; mirrors the existing direct-reports guard's shape.
- [x] [Review][Defer] **Deactivated employee with a live token can still submit** [backend/app/services/leave_requests.py:202] — deferred, pre-existing (AD-14). `get_current_employee` deliberately does not re-check `is_active` at token resolution, so a deactivated user holding an unexpired token can submit and reserve balance until the token expires. Not caused by this change; the new write endpoint is its first balance-mutating consequence.

## Dev Notes

### The one-paragraph mental model
`POST /leave-requests` is **one transaction** that turns a validated date range into a persisted `leave_request` row + a balance mutation + an `audit_entry` row, atomically. Everything it needs already exists: the day count (2.3), the lockable balance and its `reserve`/`consume_direct` gates (2.4), the holiday read and preview scaffolding (2.5). This story adds the two tables, the five refusal codes, the command that composes them under a lock, and the correctness test that proves two racers cannot both spend the same day.

### Reuse map — DO NOT reinvent these
| Need | Reuse (exact) | Source |
|---|---|---|
| Day count | `calendar.count_leave_days(start, end, holidays) -> int` (total, never raises, `weekday()<5 and not holiday`) | [domain/calendar.py:37](backend/app/domain/calendar.py#L37) |
| Reserve days (PENDING path) | `balances.reserve(session, *, employee_id, leave_type_id, leave_year, days)` — locks `FOR UPDATE`, raises `INSUFFICIENT_BALANCE` pre-write | [services/balances.py:99](backend/app/services/balances.py#L99) |
| Consume directly (managerless) | `balances.consume_direct(...)` — never touches `reserved`, same Available gate | [services/balances.py:151](backend/app/services/balances.py#L151) |
| Lock the balance row | done **inside** `reserve`/`consume_direct` via `leave_balance_repo.lock_balance` (`populate_existing=True` TOCTOU fix) | [repositories/leave_balance.py:37](backend/app/repositories/leave_balance.py#L37) |
| Holidays in range | `holiday_repo.holidays_in_range(session, start, end) -> list[CompanyHoliday]` | [repositories/holiday.py:74](backend/app/repositories/holiday.py#L74) |
| `INSUFFICIENT_BALANCE` code | **already declared + mapped to 400** — just call `reserve` | [vocabulary.py:148](backend/app/domain/vocabulary.py#L148), [main.py:87](backend/app/main.py#L87) |
| Pending-request guard shape | copy `count_active_direct_reports` + `_employee_has_direct_reports` factory | [repositories/employee.py:175](backend/app/repositories/employee.py#L175), [services/employee.py:90](backend/app/services/employee.py#L90) |
| Migration/model shape | copy `0005_leave_balance` + `LeaveBalance.__table_args__` | [alembic/versions/0005_leave_balance.py](backend/alembic/versions/0005_leave_balance.py), [models.py:170](backend/app/repositories/models.py#L170) |
| Typed refusal + `details` idiom | `_insufficient_balance` (one `_MESSAGE` const + factory, numbers in `details`) | [services/balances.py:48](backend/app/services/balances.py#L48) |
| Frontend mutation + panel | `usePreviewLeaveRequest` + `RequestPreviewPanel.tsx` + span-cap validator | [api/leaveRequests.ts](frontend/src/api/leaveRequests.ts), [features/leave/](frontend/src/features/leave/) |

### Non-negotiable invariants (a violation is a review reject)
- **AD-2 — one day-count authority.** Only `domain/calendar.count_leave_days` knows weekends/holidays. Do not compute a day count in the service, the route, the repo, or the client. The client renders server figures — no `getDay`/`getUTCDay` anywhere under `frontend/src`, not even in a comment.
- **AD-3 — decide under the lock, never off the preview.** The `available` that admits or refuses is read from the row held under `SELECT … FOR UPDATE` in *this* transaction. `reserve`/`consume_direct` already do this — do **not** re-read with the non-locking `get_balance` and decide off that. One transaction per command, opened in `services/`, committed in `services/`. Lock balance rows before request rows.
- **AD-5 — the service is the gate, the CHECK is the backstop.** Every refusal is raised by the service **before** the write. A `leave_balance` or `leave_request` CHECK reaching the client is a defect and a 500, never a refusal. Pre-check `leave_days > 0` (`ZERO_LEAVE_DAYS`), `end >= start` (`INVALID_DATE_RANGE`), etc., so the DB CHECKs never fire in normal operation.
- **AD-8 — audit is append-only and same-transaction.** Exactly **one** `audit_entry` row per transition, inserted in the same transaction as the transition; a rolled-back submit leaves no request row **and** no audit row. Expose **no** update/delete method for `audit_entry` (or `leave_request` create). `from_state = NULL` for a creation.
- **AD-17 — one balance writer.** Only `services/balances.py` writes a balance column, and it has **exactly 8** public methods (`test_balances_module_surface.py`). Do **not** add a ninth, and do **not** touch `reserved`/`consumed` anywhere else. Submit uses `reserve` (PENDING) or `consume_direct` (managerless).
- **AD-18 — `leave_days` is frozen at admission.** Computed once by `count_leave_days`, stored on the row, never recomputed by any read path (history, dashboard, calendar, export — all later stories read the stored value).
- **AD-21 — every enumerated string is a `vocabulary.py` constant.** Statuses, actor types, subject type, reason, error codes — declared once, literal nowhere else (`test_vocabulary_literals.py`). The only exempt copies are the model `__table_args__` CHECK and the migration DDL.
- **AD-1 layering.** `api → services → {repositories, domain}`; `api/` imports neither `repositories/` nor `domain/`; `domain/` is pure (no ORM/IO); statuses wired in `main.py`. `test_architecture.py` runs import-linter (7 contracts) — keep them green.
- **DR-10 — integers only.** `leave_days` and every balance quantity is `INTEGER`; never float/`NUMERIC`.

### The auto-approval branch (AC5) — read carefully
`manager_id IS NULL` means there is no possible approver, so the request is admitted **directly as `APPROVED`** (it never passes through `PENDING`) and its days are `consume_direct`ed (straight to `consumed`, `reserved` untouched — a shared `consume` that decremented `reserved` from 0 would violate `CHECK (reserved >= 0)`, which is precisely why `consume_direct` exists as a separate op). The **Available check still applies** — a managerless applicant can still be refused `INSUFFICIENT_BALANCE`. The audit row is `actor_type=SYSTEM`, `actor_id=NULL`, `reason=AUTO_APPROVED_NO_MANAGER`, `from_state=NULL`, `to_state=APPROVED`. Note there is **no manager to notify** (notifications are a later story; do not invent one). AD-22 guarantees deactivation can never *create* a managerless active employee, so this branch is only ever hit for a genuinely manager-less applicant (e.g. the top of the org / an Admin who is also an applicant).

### Refusal precedence (decide and document)
Validity refusals are date properties checkable **before** the lock; `INSUFFICIENT_BALANCE` is decided **under** the lock. A sensible order: `INVALID_DATE_RANGE` → `PAST_DATE_RANGE` → `SPANS_TWO_LEAVE_YEARS` → `ZERO_LEAVE_DAYS` → (lock) → `INSUFFICIENT_BALANCE`. The epic does not pin the order; pick a deterministic one and cover it in tests. Keep the pure predicates in `domain/` so they are DB-free-testable; the service raises the typed `DomainError`.

### DECISION POINT — AD-9 database grants on `audit_entry` (AC2)
AC2 requires the *application database role* to hold `INSERT`+`SELECT` on `audit_entry` and **neither `UPDATE` nor `DELETE`**, with migrations running as the **owner**. **This presumes a two-role split (owner ≠ app role) that this codebase does not have today** — [docker-compose.yml](docker-compose.yml) provisions a single `POSTGRES_USER`, migrations and the app connect as that same role, and no existing migration issues any `GRANT`/`REVOKE` (verified). Options:
1. **(Recommended, ship-now)** Realize "append-only" at the **code layer** — the binding, testable guarantee: the `audit_entry` repository exposes only `insert`/`select`, no update/delete method (AD-8's own words: *"No repository exposes an update or delete method for either table"*). Add a test asserting the repo surface. Record in the Dev Agent Record that the DB-role GRANT is deferred pending a role split, with rationale (a `GRANT`/`REVOKE` against the owning role is a no-op — an owner cannot be denied on its own table). Consistent with how the codebase has treated other defense-in-depth-vs-current-infra gaps (see `deferred-work.md`).
2. Introduce a distinct least-privilege app role now (compose + settings change + migration `GRANT`/`REVOKE` run as owner). Larger scope than this story's slice; only take it if you also change the runtime connection role.

**Do not** silently drop AC2 — pick an option and declare it. Surface this in the review.

### Testing standards (this codebase)
- `pytest` **is** the build — there is no CI; guards run in-suite. Baseline **310** tests (post-2.5).
- **DB-free domain tests** → [backend/tests/domain/](backend/tests/domain/) (no `db_connection` fixture, stdlib + pure fn + `vocabulary`). **Integration tests** → [backend/tests/integration/](backend/tests/integration/) against real PostgreSQL (`conftest.py` skips loudly if unreachable); `import app.main` at top wires `CODE_TO_STATUS`.
- **SM-1 must run against real PostgreSQL** — SQLite would pass it falsely (global writer serialization, no real `FOR UPDATE`). Use two connections; the second blocks on the lock.
- Assert the **negatives**: exactly one audit row per submit; a CHECK never reaches the client; the balance is byte-consistent after a refusal; a 404 body is byte-identical to any other not-found.
- Frontend has no test runner — proof is `npm run build` + `npm run lint` clean, plus a declared manual click-through.

### Project Structure Notes
- **Extend, do not create parallel files:** `services/leave_requests.py`, `api/v1/leave_requests.py`, `frontend/src/api/leaveRequests.ts`, `frontend/src/features/leave/` all already exist (Story 2.5) and were deliberately named/placed so 2.6 extends them. The router is already `include_router`-ed — adding a route needs no router edit.
- **New files:** `repositories/leave_request.py`, `repositories/audit_entry.py`, `alembic/versions/0006_leave_request.py`, `tests/domain/test_leave_request_rules.py` (or similar), `tests/integration/test_leave_request_submit.py`.
- **Naming:** service/router files plural (`leave_requests`); tables/models singular snake_case (`leave_request`, `audit_entry`) / PascalCase (`LeaveRequest`, `AuditEntry`); domain fns `verb_noun`; migration `0006_leave_request`, `down_revision="0005_leave_balance"`.
- **Commit:** `feat(story-2.6): <summary>`, matching the `feat(story-2.4): implement leave balance management` git-log convention; one commit after review → done.

### Cross-story context (Epic 2 sequencing)
- Story **2.7** (approve/reject/cancel) consumes what 2.6 stores: it transitions the `leave_request` via a guarded `UPDATE … WHERE status=:from` (AD-4), moving `reserved → consumed` (`consume_reserved`) on approve or `release_reserved` on reject, and delivers the `GET /leave-requests` + `GET /leave-requests/<id>` reads (the first multi-scope identifier endpoints → will need `test_scope_matrix.py` registration **there**, not here). Do not build any transition/UPDATE path in 2.6 beyond the create.
- Story **4.1** will add a `SUPPORTING_DOCUMENT_REQUIRED` check to *this* submission service; EL/CL/FL seed `requires_supporting_document=false`, so it is safely absent now.
- **Inherited, accepted limitation (do not "fix"):** a concurrently-created employee/leave-type pair can lack a materialized balance row; a `reserve` then hits `_lock` → `LookupError` → 500. Known/deferred (2.4 review) — admin creates are effectively serial and recoverable. Awareness only.

### References
- [Source: epics.md#Story 2.6] (lines 1045–1089) — acceptance criteria, verbatim.
- [Source: ARCHITECTURE-SPINE.md] — AD-2 (line 77), AD-3 (line 83), AD-5 (line 95), AD-8 (line 113), AD-9 (line 119), AD-17 (line 167), AD-18 (line 173), AD-21 (line 191), AD-22 (line 197); layering (line 71); conventions (lines 203–218).
- [Source: architecture.md §5.2–5.3] — why `consume_direct` is distinct; the concurrent double-submit lock walk; why real PostgreSQL for SM-1.
- [Source: api-contracts.md §2] (lines 68–89) — the five 400 codes + `EMPLOYEE_HAS_PENDING_REQUESTS` (409) + the `{code,message,details}` envelope; §4.5 (line 169) — `POST /leave-requests`, role any, scope self, `FR-08`.
- [Source: erd.md §2, §4.2–4.5] — `leave_request` columns/CHECKs, no `created_at`/no `leave_year`; `audit_entry` columns + the SYSTEM-actor CHECK; the two `leave_request` indexes; grants (§4.3).
- [Source: 2-5-…preview.md] — the seam this story extends; range validity explicitly deferred to 2.6; the 366-day span-cap, `preview.reset()`, and select-state patterns.
- [Source: 2-4-…balances.md] — the 8-method AD-17 module; `reserve`/`consume_direct`; `lock_balance` `populate_existing` TOCTOU fix; negative-days guards; SM-1 assigned to 2.6.
- [Source: 2-3-…day-count.md] — `count_leave_days` signature/semantics; the AD-2 frontend guard; range validity deferred to 2.6; AD-18 freeze is 2.6's.
- [Source: 1-6-…employees.md] — `EMPLOYEE_HAS_PENDING_REQUESTS` withheld ("vacuous in this epic"); `deactivate_employee` is where the guard lands; the `count_/factory/details` refusal shape.
- [Source: deferred-work.md] — the inherited materialization-race limitation; the defense-in-depth-vs-infra precedent for the AD-9 decision.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — dev-story workflow.

### Debug Log References

- `alembic upgrade head` → `0006_leave_request` applied; `alembic check` reports "No new upgrade
  operations detected" (model/migration byte-agreement).
- One integration-test correction during red→green: the managerless auto-approval path yields **4**
  Working Days for Fri→Wed (no holiday seeded in that test), not 3 — the assertion was fixed to the
  true count; the code was correct.

### Completion Notes List

**All 8 ACs satisfied; backend pytest 332 passed (baseline 310, +22 new); frontend build + lint clean.**

- **AC1/AC2 (schema):** `0006_leave_request` ships `leave_request` (DATE range, INTEGER
  `leave_days`, TEXT `status` with the four-state CHECK, `end_date >= start_date`, `leave_days > 0`,
  the two ERD §4.4 indexes, NO `created_at`/`leave_year`) and `audit_entry` (polymorphic
  `subject_*` with no FK, nullable `from_state`/`actor_id`, TIMESTAMPTZ `occurred_at`, the
  `(actor_type='SYSTEM') = (actor_id IS NULL)` biconditional CHECK). Constraint/index names are
  byte-identical to the models; `alembic check` is clean.
- **AC3 (happy path):** `submit_leave_request` opens one write transaction; `count_leave_days`
  computes `leave_days` once (frozen on the row, AD-18); `balances.reserve` locks the row `FOR
  UPDATE` and decides from the locked row; one `audit_entry` (`EMPLOYEE`/`SUBMITTED`, `NULL →
  PENDING`) is written in the same transaction. Verified: `reserved` rises by exactly the count,
  exactly one audit row.
- **AC4 (refusals):** all five are 400 with their code + `details`, raised by the service before the
  write. Precedence (documented + tested): `INVALID_DATE_RANGE → PAST_DATE_RANGE →
  SPANS_TWO_LEAVE_YEARS → ZERO_LEAVE_DAYS → (lock) → INSUFFICIENT_BALANCE`. The overspend test
  asserts the balance CHECK never surfaces (typed 400, balance byte-unchanged), not a 500.
- **AC5 (managerless):** a NULL-`manager_id` applicant is admitted directly as `APPROVED` via
  `consume_direct` (`reserved` stays 0, `consumed` rises); audit row is `SYSTEM`/`AUTO_APPROVED_NO_
  MANAGER`, `actor_id` NULL, `NULL → APPROVED`. The Available check still fires.
- **AC6 (SM-1):** two threads submit the same 5-day week against an Available saturated to exactly
  5, contending on `SELECT … FOR UPDATE` (barrier-synchronized) against real PostgreSQL — exactly
  one succeeds, the other is `INSUFFICIENT_BALANCE`; final `reserved == 5`, `available == 0` (never
  negative), exactly one `leave_request` row.
- **AC7 (deactivation guard):** `deactivate_employee` now calls `count_pending_for_employee` after
  the direct-reports guard; an Admin deactivating an Employee holding a PENDING request gets 409
  `EMPLOYEE_HAS_PENDING_REQUESTS` (`details.pending_requests`). Ordering vs.
  `EMPLOYEE_HAS_DIRECT_REPORTS` is deterministic and documented (reports first — the older
  structural refusal is primary).
- **AC8 (frontend):** `useSubmitLeaveRequest` posts the range and invalidates `BALANCES_QUERY_KEY`
  so Available falls immediately; `RequestPreviewPanel` gained a Submit button, renders the returned
  `status`/`leave_days`, and renders the server's refusal `details` numbers (never a client day
  count — `test_frontend_no_client_day_count.py` green).

**Open-Question decisions (declared, not dropped):**
1. **AD-9 grants (AC2):** Option 1 — **code-layer append-only** (ship-now). The codebase runs a
   single Postgres role, so a `REVOKE UPDATE/DELETE` on the owning role is a no-op; the binding,
   testable guarantee is that neither `repositories/audit_entry` nor `repositories/leave_request`
   exposes an update/delete method, asserted by
   `test_audit_and_request_repositories_expose_no_update_or_delete`. The DB-role GRANT is deferred
   pending a least-privilege role split; rationale recorded in the `0006` migration docstring.
   **Flag for review.**
2. **`audit_entry.reason` for the PENDING submit:** coined `REASON_SUBMITTED = "SUBMITTED"`, keeping
   `reason` NOT NULL and symmetric with `AUTO_APPROVED_NO_MANAGER`.
3. **"Wholly in the past" rule:** `end < today` (a range with any today-or-later day stays
   actionable), documented in `domain/leave_request_rules.is_wholly_past`.

**Manual click-through (honest note):** a browser click-through was **not** performed in this
headless session (no running dev server/Docker image driven). The full submit → Available-falls
HTTP path is exercised by `tests/integration/test_leave_request_submit.py` against real PostgreSQL
(reserved/consumed move exactly as expected, from which `GET /balances` derives Available), and the
frontend compiles and lints clean. A live browser pass is recommended at review.

### File List

**New — backend:**
- `backend/alembic/versions/0006_leave_request.py`
- `backend/app/repositories/leave_request.py`
- `backend/app/repositories/audit_entry.py`
- `backend/app/domain/leave_request_rules.py`
- `backend/tests/domain/test_leave_request_rules.py`
- `backend/tests/integration/test_leave_request_submit.py`

**Modified — backend:**
- `backend/app/repositories/models.py` (LeaveRequest + AuditEntry models; `Index`/`DateTime` imports)
- `backend/app/domain/vocabulary.py` (4 status constants, 5 codes, audit vocab; `__all__`)
- `backend/app/main.py` (`CODE_TO_STATUS`: 4×400 + 1×409)
- `backend/app/services/leave_requests.py` (`submit_leave_request`, `SubmitView`, refusal factories, clock helpers)
- `backend/app/api/v1/leave_requests.py` (`POST /leave-requests`, `SubmitRequest`/`SubmitResponse`, shared span-cap validator)
- `backend/app/services/employee.py` (pending-request guard in `deactivate_employee` + factory)
- `backend/tests/integration/test_schema_1_2.py` (expected tables += leave_request, audit_entry)
- `backend/tests/test_migrations_insert_nothing.py` (revision chain += 0006)
- `backend/tests/integration/test_migration_smoke.py` (HEAD_REVISION 0006 + two smoke tests)

**Modified — frontend:**
- `frontend/src/api/leaveRequests.ts` (`useSubmitLeaveRequest` + types)
- `frontend/src/api/index.ts` (barrel exports)
- `frontend/src/features/leave/RequestPreviewPanel.tsx` (submission form + refusal details)
- `frontend/src/App.tsx` (comment updated; panel already mounted)
- `frontend/src/index.css` (two new result/refusal classes)

---

## Change Log

- 2026-07-13 — Implemented Story 2.6 (dev-story). Migration `0006` (leave_request + audit_entry);
  vocabulary (4 statuses, 5 codes, audit vocab); `submit_leave_request` one-transaction command
  reusing `count_leave_days` + `reserve`/`consume_direct` under lock, one `audit_entry` same txn,
  AD-18 freeze; managerless auto-APPROVE via `consume_direct`; `POST /leave-requests`;
  `EMPLOYEE_HAS_PENDING_REQUESTS` guard executable in `deactivate_employee`; SM-1 concurrent
  double-submit on real PostgreSQL; frontend submission slice with immediate Available update and
  refusal-details rendering. AD-9 realized code-layer (single-role); `REASON_SUBMITTED` coined;
  `PAST_DATE_RANGE` = `end < today`. Backend pytest 332 passed; frontend build + lint clean.
  Status ready-for-dev → in-progress → review.

## Open Questions (for the dev agent / reviewer)

1. **AD-9 grants (AC2).** Which option — code-layer append-only (recommended, ship-now) or a real least-privilege role split? See the Decision Point. Must be declared, not dropped.
2. **`audit_entry.reason` for the PENDING submit transition.** `AUTO_APPROVED_NO_MANAGER` is the only reason api-contracts §3 currently names; the ERD/spine give no explicit reason string for an ordinary employee submission. Options: make `reason` nullable and store `NULL` for the plain submit, or coin a `SUBMITTED`/`REQUEST_SUBMITTED` reason constant. Pick one and keep `reason` and its NULL/NOT-NULL decision consistent between model, migration and the SYSTEM-actor CHECK. (Recommendation: a `REASON_SUBMITTED` constant keeps `reason` NOT NULL and symmetric.)
3. **"Wholly in the past" rule for `PAST_DATE_RANGE`.** Confirm the boundary (`end < today` vs `start < today`). Recommendation: `end < today` — a range that has any future working day is still actionable. Document the chosen rule in the domain predicate.
