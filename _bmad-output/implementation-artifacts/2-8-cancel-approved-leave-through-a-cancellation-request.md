---
baseline_commit: 93fdb566278464be4fa9319115652322a627223e
---

# Story 2.8: Cancel Approved Leave through a Cancellation Request

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an **Employee**,
I want **to ask for approved leave to be cancelled when my plans change**,
so that **days I will not take are returned to my balance**.

This is the **approved-leave cancellation** half of the lifecycle, and the **first NEW table since
Story 2.6**. Story 2.7 delivered the transitions off a `PENDING` request (approve/reject/cancel) and
the applicant's own cancel of a *Pending* request (`release_reserved`). This story adds the entirely
separate path for an **Approved** request: an applicant raises a **Cancellation Request** — its own
row in a new `cancellation_request` table (`AD-13`: **not** a fifth Leave Request status) — which an
**Admin** decides. An approved Cancellation Request moves the Leave Request to `CANCELLED` and returns
its `consumed` days via `release_consumed` (`BR-05`); a rejected one changes nothing. It introduces
**one new migration (0007)**, one new model, one new repository, one new service (`services/
cancellation`), four new routes, and the frontend for both the Employee (raise + track) and the Admin
(the Cancellation Requests screen — the Admin's **only** route to a Cancellation Request, since none
is announced by notification or dashboard).

**Do NOT conflate this with Story 2.7's `POST /leave-requests/<id>/cancel`** — that is the applicant
cancelling their own **Pending** request (`release_reserved`, one guarded `UPDATE` on the Leave
Request). This story's `POST /leave-requests/<id>/cancellation-requests` files a request against
**Approved** leave (`release_consumed`, Admin-decided, a separate table). Two different flows,
deliberately.

## Acceptance Criteria

> Verbatim from `epics.md` §"Story 2.8" (lines 1145–1201). BDD blocks numbered AC1–AC10 for task
> traceability.

**AC1 — the schema: `cancellation_request` is its own table, not a fifth status**
**Given** a database migrated by this story
**When** the schema is inspected
**Then** `cancellation_request` is its own table with `leave_request_id` and a `status` of `PENDING`,
`APPROVED` or `REJECTED`
**And** it is not a fifth Leave Request status, which is what makes "Approved, with a cancellation
pending" representable (`AD-13`, `DR-14`).

**AC2 — the applicant raises one against their own future-dated Approved request**
**Given** the applicant and their own Approved request whose dates lie in the future
**When** they call `POST /api/v1/leave-requests/<id>/cancellation-requests`
**Then** a Pending Cancellation Request is created
**And** no other Employee may raise one — a non-owner target is out of scope and gets a byte-identical
`404` (`FR-09`, `AD-10`).

**AC3 — a Cancellation Request against past-dated leave is refused `400 LEAVE_ALREADY_TAKEN`**
**Given** an Approved request whose dates have already passed
**When** a Cancellation Request is raised against it
**Then** the response is `400` with `LEAVE_ALREADY_TAKEN` (`DR-14`). *("already passed" = `end_date <
today`; an in-progress request whose `end_date` is still today or later is not yet "taken".)*

**AC4 — while a Cancellation Request is Pending, the Leave Request is untouched**
**Given** a Pending Cancellation Request
**When** its target is inspected
**Then** the Leave Request remains `APPROVED` and its days remain `consumed` (`AD-13`) — the balance is
byte-unchanged by the mere existence of a Pending Cancellation Request.

**AC5 — `GET /cancellation-requests`: scoped (self/all), paged, optionally status-filtered**
**Given** an authenticated caller
**When** they call `GET /api/v1/cancellation-requests`, optionally filtered by `status`
**Then** an Admin receives every Cancellation Request and an Employee receives only their own, the
scope applied as a **SQL predicate**
**And** the response carries `items`, `page`, `page_size` and `total` (`DR-14`, `AD-10`, `NFR-11`,
api-contracts §4.6). *(This endpoint is what makes a Cancellation Request discoverable — see the
rationale note below.)*

> *(**Without this endpoint an Admin cannot discover that a Cancellation Request exists.** No
> notification is addressed to an Admin — `FR-14`'s three kinds all target the Manager or the
> applicant — and the Admin dashboard's Pending count is a count of **Leave** Requests. The only
> remaining route to `POST /cancellation-requests/<id>/approve` would be to guess a `uuidv7` primary
> key that the ERD deliberately made non-enumerable so `AD-10`'s `404` stays honest. `DR-14` reversed
> the old "out of scope" ruling so `BR-05` would be a live rule rather than documented-but-unreachable
> policy. This endpoint is what keeps it reachable.)*

**AC6 — an Admin approves: the Leave Request moves to `CANCELLED` and its days return**
**Given** an Admin
**When** they call `POST /api/v1/cancellation-requests/<id>/approve`
**Then** the targeted Leave Request moves to `CANCELLED` and its days are returned through
`release_consumed`, restoring Available (`BR-05`, `AD-17`) — the Cancellation Request itself moves
`PENDING → APPROVED`.

**AC7 — an Admin rejects: nothing about the leave changes**
**Given** an Admin
**When** they call `POST /api/v1/cancellation-requests/<id>/reject`
**Then** the Cancellation Request moves to `REJECTED` and the targeted Leave Request remains `APPROVED`
with its days still `consumed` — a rejection changes nothing about the leave itself (`FR-09`, `AD-13`).

**AC8 — only an Admin decides a Cancellation Request → `403 ACTION_NOT_PERMITTED`**
**Given** any caller whose role is not Admin
**When** they call `POST /api/v1/cancellation-requests/<id>/approve` or `.../reject`
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — only an Admin decides a Cancellation
Request (`FR-09`, `DR-13`, `G3`). *(A **role** denial, decided by the `require_role(ADMIN)` gate
before any row is read.)*

**AC9 — the audit trail: an approval writes one row per subject, discriminated by `subject_type`**
**Given** an approved Cancellation Request
**When** the Audit Entries are counted
**Then** there is one for the Cancellation Request's own transition (`subject_type =
CANCELLATION_REQUEST`) and one for the Leave Request's move to `CANCELLED` (`subject_type =
LEAVE_REQUEST`), discriminated by `subject_type` (`AD-8`, `DR-14`). *(See Open Decision #3 on whether
the **raise** also writes an audit row — it governs the exact count.)*

**AC10 — the frontend: the Employee raises + tracks; the Admin decides**
**Given** the React application and an authenticated Employee
**When** they view an Approved future-dated request
**Then** they can raise a Cancellation Request, and see its state while an Admin decides it.
**And Given** the React application and an authenticated Admin
**When** they open the Cancellation Requests screen
**Then** they see every Pending Cancellation Request, each naming its applicant, the targeted Leave
Request and its dates, and can approve or reject it
**And** this is the Admin's only route to a Cancellation Request, because none is announced to them by
notification or dashboard (`FR-09`, `DR-14`).

---

## Tasks / Subtasks

> Ordered so each task compiles and tests green before the next: **migration + model first** (the new
> table), then vocabulary → repository → service → routes → the SM-3/migration test registrations,
> then the frontend, then tests, then the full gate. **This story DOES ship a migration (0007)** —
> the first since 2.6.

- [x] **Task 1 — Migration 0007 + the `CancellationRequest` model (AC1)**
  - [x] New `backend/alembic/versions/0007_cancellation_request.py`, `down_revision = "0006_leave_request"`. Create table `cancellation_request` with: `id` (`sa.Uuid()`, `server_default=sa.text("uuidv7()")`, PK — the native PG18 built-in, mirroring 0002–0006), `leave_request_id` (`sa.Uuid()`, NOT NULL, `sa.ForeignKeyConstraint(["leave_request_id"], ["leave_request.id"])`), `status` (`sa.Text()`, NOT NULL), and `sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="cancellation_request_status_check")`. **Pure DDL — no `insert()`/DML** (`test_migrations_insert_nothing.py` AST-forbids it, AD-11). **No `UNIQUE (leave_request_id)`** — ERD §3 permits *multiple* Cancellation Requests per Leave Request over time (a rejected one may be followed by another). `downgrade()` drops the table.
  - [x] **No index is declared** — ERD §4.4 names none for `cancellation_request` (unlike `leave_request`'s two). The Admin list filters by `status` at Epic-2 scale (few rows); do not invent an index the ERD does not name (it would break `alembic check` unless mirrored in the model, and the ERD is the source of truth). See Open Decision #4 if you disagree.
  - [x] Add the `CancellationRequest` model to `backend/app/repositories/models.py`, **byte-for-byte faithful** to the migration (every constraint `name=` identical) — `test_model_migration_agreement.py` runs `alembic check` and fails on any diff. Columns: `id` (`server_default=text("uuidv7()")`, PK), `leave_request_id` (`ForeignKey("leave_request.id")`, NOT NULL), `status` (`Text`, NOT NULL); `__table_args__` = the one `CheckConstraint(... name="cancellation_request_status_check")`. **No `created_at`, no requester column, no decider column** (ERD §2.1): the requester is `leave_request.employee_id` (`FR-09`), the deciding Admin is the `actor_id` on the audit row, and creation order comes from the time-ordered UUIDv7 PK. Model docstring: cite AD-13/DR-14/AD-11 and "faithful to 0007", mirroring `LeaveRequest`.

- [x] **Task 2 — Vocabulary: one new code, one new subject, (see Open Decisions) status/reason (AC1, AC3, AC9)**
  - [x] In [backend/app/domain/vocabulary.py](backend/app/domain/vocabulary.py) add the error code `LEAVE_ALREADY_TAKEN = "LEAVE_ALREADY_TAKEN"` (→ 400, api-contracts §2 — "cancellation raised against leave whose dates have passed, `DR-14`"). Declare it beside its raise-site rationale, following the per-code comment discipline; add to `__all__`.
  - [x] Add the subject-type constant `SUBJECT_CANCELLATION_REQUEST = "CANCELLATION_REQUEST"` (ERD §3 audit `subject_type` values are `LEAVE_REQUEST` / `CANCELLATION_REQUEST`; `SUBJECT_LEAVE_REQUEST` already exists). Add to `__all__`.
  - [x] **Cancellation Request statuses** — see **Open Decision #1**. Recommended: **reuse** the existing `STATUS_PENDING`/`STATUS_APPROVED`/`STATUS_REJECTED` (`"PENDING"`/`"APPROVED"`/`"REJECTED"`) — the values are identical and AD-21 says each string is "declared exactly once", so a second constant with the same value would violate that. The `cancellation_request` CHECK's literal DDL (in the migration + the model `__table_args__`) is the only exempt copy, exactly like `leave_request`.
  - [x] **Reason constants** — see **Open Decision #3**. Reuse `REASON_APPROVED`/`REASON_REJECTED` for the Cancellation Request's own decision transitions and `REASON_CANCELLED` for the Leave Request's `APPROVED → CANCELLED` move (all already exist from 2.7). **If** you audit the *raise* (recommended, Option A), add `REASON_CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"` for the `NULL → PENDING` filing row and add it to `__all__`.
  - [x] Every new name goes in `__all__` the moment it is declared — `test_vocabulary_literals.py` then AST-enforces that it appears as a bare literal **nowhere** under `app/` or `seed/` (only imported as `vocabulary.X`). The migration DDL CHECK and the model `__table_args__` CHECK are exempt (exact-equality match, so a compound `"status IN (...)"` clause is fine).

- [x] **Task 3 — Wire the new code in the composition root (AC3)**
  - [x] In [backend/app/main.py](backend/app/main.py) `CODE_TO_STATUS.update({...})` add exactly one entry: `vocabulary.LEAVE_ALREADY_TAKEN: 400` (beside the Story 2.7 `TRANSITION_NOT_ALLOWED` block at [main.py:98-103](backend/app/main.py#L98)). `ACTION_NOT_PERMITTED` (403), `RESOURCE_NOT_FOUND` (404) and `TRANSITION_NOT_ALLOWED` (409) already exist — do **not** redeclare. Statuses are set **here only** (contract 2).

- [x] **Task 4 — Repository: a NEW `cancellation_request` module (AC1, AC2, AC4, AC5, AC6, AC7)**
  - [x] New [backend/app/repositories/cancellation_request.py](backend/app/repositories/cancellation_request.py) (a genuinely new resource — do **not** bolt it onto `leave_request.py`; the append-only surface test pins `leave_request`'s exact surface). Add:
    - `insert_cancellation_request(session, *, leave_request_id, status) -> CancellationRequest` — `session.add` + `flush` (assigns the `uuidv7()` id so the command can write the audit row in the same transaction), no commit (the service owns the transaction, AD-3). A write, not a scoped getter — mirrors `insert_leave_request`.
    - `get_cancellation_request(session, actor, cancellation_request_id, scope) -> Row | None` — a **scoped** single-row read. Join `cancellation_request → leave_request → employee` and apply `employee_scope_predicate(scope, actor)` in the `WHERE` alongside `CancellationRequest.id == cancellation_request_id`. Project the columns the decision needs off the **target Leave Request**: `leave_request_id`, the LR's `employee_id`, `leave_type_id`, `leave_days`, `start_date`, and the LR's `status` (to guard `release_consumed`), plus the CR's own `id`/`status`, plus applicant `full_name` and Leave Type `code`/`name` for the response. Returns `None` for a nonexistent OR out-of-scope id (the service turns both into a byte-identical 404). A `get_` getter taking `session` → **must** take `actor` (`test_scoped_getters.py`).
    - `list_cancellation_requests(session, actor, *, scope, status, limit, offset) -> tuple[list[Row], int]` — the scoped, paged, optionally status-filtered list. Same joins + predicate; `status` filter applied only when `status is not None`; order `CancellationRequest.id.desc()` (UUIDv7 → newest-first); `total` recomputes the same predicate+filter. Returns `(rows, total)`, the `list_employees`/`list_leave_requests` shape. Takes `actor` (scoped getter).
    - `transition_cancellation_status(session, *, cancellation_request_id, from_status, to_status) -> int` — the AD-4 guarded conditional `UPDATE cancellation_request SET status = :to WHERE id = :id AND status = :from`, `execution_options(synchronize_session=False)`, returns `result.rowcount`. The **only** mutation of a CR row (no free-form update/delete). Exactly the shape of `leave_request.transition_status`.
  - [x] Module docstring: cite AD-13 (CR is its own table), AD-4 (the one guarded transition), AD-10 (scoped reads), and the `leave_request.py`/`employee.py` precedents.

- [x] **Task 5 — Service: a NEW `services/cancellation.py` (AC2–AC9)**
  - [x] New [backend/app/services/cancellation.py](backend/app/services/cancellation.py) — the spine's capability map names this module explicitly (`services/cancellation`, distinct from `services/leave_request`). Import `leave_request as leave_request_repo` (for `transition_status` on the LR), `cancellation_request as cancellation_request_repo`, `audit_entry as audit_entry_repo`, `balances`, `authorization as authz`, `Scope`, and the `rules`/`vocabulary` it needs.
  - [x] A `_leave_already_taken() -> DomainError` factory (code `LEAVE_ALREADY_TAKEN`, empty `details` — a past-date refusal names no numbers), one `_MESSAGE` const, mirroring `leave_requests._past_date_range`. Reuse `_now()` (shell clock, AD-1) and a `_today()` helper for the past-date check.
  - [x] A **two-way** scope resolver `_scope_for_role(role) -> Scope`: **`ALL` for an Admin, else `SELF`** (api-contracts §4.6 grants `GET /cancellation-requests` scope `self, all` only — a Manager is NOT `REPORTS` here; they see their own filings as an applicant). This is the *two-way* idiom (Admin/else), NOT `leave_requests._scope_for_role`'s three-way. Pure fn → unit-testable DB-free.
  - [x] `raise_cancellation_request(actor, request_id) -> <view>` (scope `SELF`, role any):
    1. One write transaction. Locate the **target Leave Request** under `Scope.SELF` via `leave_request_repo.get_leave_request(session, actor, request_id, Scope.SELF)` → `None` ⇒ `authz.not_found()` (404, AC2 — a non-owner's target is out of scope).
    2. The located row must be `APPROVED` — a non-`APPROVED` target is refused (see Open Decision #2; recommended `409 TRANSITION_NOT_ALLOWED`). *(A Pending request is cancelled via 2.7's `/cancel`, not here.)*
    3. `LEAVE_ALREADY_TAKEN` if `rules.is_wholly_past(row.end_date, _today())` (AC3) — reuse the existing pure predicate (`domain/leave_request_rules`, the same `end < today` test `PAST_DATE_RANGE` uses).
    4. `cancellation_request_repo.insert_cancellation_request(..., leave_request_id=request_id, status=STATUS_PENDING)`.
    5. **(Open Decision #3)** If auditing the raise: one `audit_entry` (`subject_type=SUBJECT_CANCELLATION_REQUEST`, `subject_id=<cr.id>`, `from_state=None`, `to_state=STATUS_PENDING`, `actor_type=ACTOR_EMPLOYEE`, `actor_id=actor.id`, `reason=REASON_CANCELLATION_REQUESTED`, `occurred_at=_now()`). **The Leave Request is NOT transitioned and its balance is NOT touched** (AC4).
    6. `commit()`; return the created CR as a frozen view.
  - [x] `approve_cancellation_request(actor, cancellation_request_id) -> <view>` (scope `ALL`, role Admin — the route's `require_role(ADMIN)` gate has already refused a non-Admin, AC8):
    1. One write transaction. Locate the CR under `Scope.ALL` (`get_cancellation_request`) → `None` ⇒ `authz.not_found()`.
    2. **Guarded transition of the CR** (`transition_cancellation_status`, `PENDING → APPROVED`) → `0` ⇒ `raise _transition_not_allowed()` (409; reuse the `leave_requests` factory or a local one) and roll back.
    3. **Guarded transition of the target Leave Request** (`leave_request_repo.transition_status`, `APPROVED → CANCELLED`) → `0` ⇒ `raise _transition_not_allowed()` and roll back. *(This is why the CR carries `leave_request_id` and the located row carries the LR's `status`: a race where the LR left `APPROVED` — e.g. a second CR approved first — is a clean 409, not a `release_consumed` `ValueError` → 500.)*
    4. `balances.release_consumed(session, employee_id=<LR.employee_id>, leave_type_id=<LR.leave_type_id>, leave_year=<LR.start_date.year>, days=<LR.leave_days>)` — the AD-17 approved-cancellation path (BR-05), restoring Available (AC6).
    5. **Two** `audit_entry` rows, both in this transaction (AC9): one `subject_type=SUBJECT_CANCELLATION_REQUEST` (`from=PENDING`, `to=APPROVED`, `reason=REASON_APPROVED`) and one `subject_type=SUBJECT_LEAVE_REQUEST` (`from=APPROVED`, `to=CANCELLED`, `reason=REASON_CANCELLED`); both `actor_type=ACTOR_EMPLOYEE`, `actor_id=actor.id` (the Admin), same `occurred_at`.
    6. `commit()`; return the updated CR view (status `APPROVED`).
  - [x] `reject_cancellation_request(actor, cancellation_request_id) -> <view>` (scope `ALL`, role Admin):
    1. Locate the CR under `Scope.ALL` → `None` ⇒ 404.
    2. Guarded transition CR `PENDING → REJECTED` → `0` ⇒ 409.
    3. **One** `audit_entry` (`subject_type=SUBJECT_CANCELLATION_REQUEST`, `from=PENDING`, `to=REJECTED`, `reason=REASON_REJECTED`, actor = the Admin). **The Leave Request is NOT transitioned and its balance is NOT touched** (AC7).
    4. `commit()`; return the updated CR view (status `REJECTED`).
  - [x] `list_cancellation_requests(actor, *, status, limit, offset) -> tuple[list[<view>], int]` and (if the route needs it) the read helpers — resolve scope via the two-way `_scope_for_role`, open a **read** session (no commit), delegate to the repo, map rows → frozen views. Define a `CancellationRequestView` dataclass carrying `id`, `leave_request_id`, `status`, plus the applicant (`employee_id`/`employee_name`) and the target LR summary (`start_date`/`end_date`/`leave_days`/`leave_type_code`/`leave_type_name`) the Admin screen needs (AC10). See Open Decision #5 on the exact fields.
  - [x] **Lock order** (same rationale as 2.7): the guarded `UPDATE`(s) run **before** `release_consumed`, so a lost race is a clean 409 before any balance is touched. See the Lock-order note in Dev Notes.

- [x] **Task 6 — Routes: a NEW `api/v1/cancellation_requests.py` + one route on the leave-requests router (AC2, AC3, AC5–AC8, AC10)**
  - [x] Add `POST /leave-requests/{request_id}/cancellation-requests` to the **existing** [backend/app/api/v1/leave_requests.py](backend/app/api/v1/leave_requests.py) router (it lives under the leave-requests path). Guard `Depends(get_current_employee)` (role **any**; scope `self` is intrinsic to the applicant). `status_code=201`. Call `cancellation_service.raise_cancellation_request(caller, request_id)`; project the created CR by hand. A non-owner target → byte-identical `404`; a past-dated target → `400 LEAVE_ALREADY_TAKEN`; a non-`APPROVED` target → `409` (Open Decision #2).
  - [x] New [backend/app/api/v1/cancellation_requests.py](backend/app/api/v1/cancellation_requests.py) router with the other three routes, and register it in [backend/app/api/v1/router.py](backend/app/api/v1/router.py) via `include_router` (mirror how `leave_requests.router` is included):
    - `GET /cancellation-requests` — `Depends(get_current_employee)` (any). Accept `params: PageParams = Depends()` and an optional `status` filter. **Reuse the same literal-free runtime-enum trick** Story 2.7 used for the leave-status filter: build the enum from a service-side re-export of the three CR status values (`(STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)`), so no status literal is typed in `api/` (`test_vocabulary_literals.py`) and `api/` imports no `domain/` (contract 2). Return `Page[CancellationRequestResponse]`.
    - `POST /cancellation-requests/{cancellation_request_id}/approve` — `Depends(require_role(authz.ROLE_ADMIN))` (**Admin**, not Manager — api-contracts §4.6) so a non-Admin is `403 ACTION_NOT_PERMITTED` before the body (AC8). `status_code=200`. Call `approve_cancellation_request`; project the updated CR.
    - `POST /cancellation-requests/{cancellation_request_id}/reject` — same gate, `status_code=200`, `reject_cancellation_request`.
  - [x] Define `CancellationRequestResponse` (Pydantic) and a `_to_..._response` hand-projector typed `object` (contract 2 — no ORM/service-dataclass import, the `balances.py`/`leave_requests.py` precedent). Fields per Open Decision #5 — at minimum `id`, `leave_request_id`, `status`, plus applicant + target-LR summary so the Admin screen renders "whose request, which leave, its dates" without a second round-trip. `leave_days` is read from the stored value (AD-18), never recomputed.
  - [x] **Only the `status` filter** is added on the list (api-contracts §4.6 / §1); `leave_type_id`/`date_from`/`date_to` are later (`FR-12`) — do not add them.

- [x] **Task 7 — Register the identifier endpoints in the SM-3 matrix (AC2, AC8)**
  - [x] In [backend/tests/test_scope_matrix.py](backend/tests/test_scope_matrix.py) `_SCOPE_REGISTRY` add (matching the **exact** FastAPI path templates, byte-identical — use whatever param names you declared, shown here as `{request_id}` / `{cancellation_request_id}`):
    - `("POST", "/api/v1/leave-requests/{request_id}/cancellation-requests"): frozenset({Scope.SELF})` — the applicant files against their own approved leave (§4.6 role any / scope self).
    - `("POST", "/api/v1/cancellation-requests/{cancellation_request_id}/approve"): frozenset({Scope.ALL})` — the **Admin** decides (§4.6 role Admin / scope all). **`ALL`, not `REPORTS`.**
    - `("POST", "/api/v1/cancellation-requests/{cancellation_request_id}/reject"): frozenset({Scope.ALL})`.
  - [x] **Do NOT register `GET /api/v1/cancellation-requests`** — it carries no path parameter, so it is out of the matrix; registering it would trip `test_no_registered_entry_names_a_route_the_app_does_not_expose`. Confirm both completeness teeth (`test_every_identifier_endpoint_is_registered`, `test_no_registered_entry_names_a_route_the_app_does_not_expose`) pass — the templates must be byte-exact.

- [x] **Task 8 — Register 0007 in the migration-chain guard (AC1)**
  - [x] In [backend/tests/test_migrations_insert_nothing.py](backend/tests/test_migrations_insert_nothing.py) `test_the_migration_history_is_the_expected_ordered_chain` append `"0007_cancellation_request.py"` to the expected ordered list (currently ends at `0006_leave_request.py`). Confirm `test_no_migration_inserts_or_updates_data` still passes (0007 is pure DDL).

- [x] **Task 9 — Frontend: cancellation-request hooks + the two screens (AC10)**
  - [x] New [frontend/src/api/cancellationRequests.ts](frontend/src/api/cancellationRequests.ts) (a cohesive new module, mirroring `leaveRequests.ts`): a `CancellationRequest` wire type, a `CANCELLATION_REQUESTS_QUERY_KEY`, `useCancellationRequests(status?, options?)` (`useQuery` on `GET /cancellation-requests`, per-status cache key, `enabled` gating), and three mutations `useRaiseCancellationRequest()` / `useApproveCancellationRequest()` / `useRejectCancellationRequest()` (`useMutation` on `apiFetch`, `method: 'POST'`). **Invalidate on `onSettled`** (not `onSuccess`, so a 409/404 still self-heals) — invalidate `CANCELLATION_REQUESTS_QUERY_KEY`, `LEAVE_REQUESTS_QUERY_KEY` **and** `BALANCES_QUERY_KEY` (an approval restores the applicant's Available). Export via the barrel [frontend/src/api/index.ts](frontend/src/api/index.ts) (paired `export {}` / `export type {}` blocks, the established convention).
  - [x] **New employee panel** [frontend/src/features/leave/RequestCancellationPanel.tsx](frontend/src/features/leave/RequestCancellationPanel.tsx) — there is **no existing "my requests" view**, so build it. Drive it off `useLeaveRequests('APPROVED')` (the server scopes it to the caller). List the caller's Approved future-dated requests; each row offers **"Request cancellation"** → `useRaiseCancellationRequest()`; render the resulting Cancellation Request's state (Pending/Approved/Rejected) so the applicant tracks it. Handle a `400 LEAVE_ALREADY_TAKEN` inline (a past-dated row) and a `409`/`404` by refetch (self-heal). **Role-gate to the EMPLOYEE role** (see Open Decision #6: a Manager's `GET /leave-requests` returns their *reports'* requests, not their own — the 2.7 own-requests gap — so this panel is for plain Employees; a Manager/Admin self-cancelling Approved leave is API-only until that gap is closed). Reuse the `emp-list`/`emp-row`/`emp-summary`/`emp-actions`/`emp-error`/`muted` classes; **no client day count** (render server `leave_days` as-is).
  - [x] **New Admin panel** [frontend/src/features/leave/CancellationRequestsPanel.tsx](frontend/src/features/leave/CancellationRequestsPanel.tsx) — mirror `ManagerQueuePanel.tsx` structure + the `EmployeesPage` `ADMIN_ROLE` gate. `const ADMIN_ROLE = 'ADMIN'`; `isAdmin = useMe().data?.role === ADMIN_ROLE`; `useCancellationRequests('PENDING', { enabled: isAdmin })`; `if (!isAdmin) return null`. Each row names the **applicant**, the **targeted Leave Request and its dates**, with **Approve**/**Reject** buttons wired to the mutations; branch error rendering on `ApiError.code` (`TRANSITION_NOT_ALLOWED`/`RESOURCE_NOT_FOUND`), track busy/failed rows via mutation `.variables`, and `.reset()` the sibling mutation before acting (the exact ManagerQueuePanel idioms). No client day count.
  - [x] Mount **both** panels in `AppShell` in [frontend/src/App.tsx](frontend/src/App.tsx) (import at top, drop into the flat panel stack beside `ManagerQueuePanel`). Add any new CSS to [frontend/src/index.css](frontend/src/index.css) reusing the existing `panel`/`emp-*` styles.

- [x] **Task 10 — Domain unit tests, DB-free (AC5)**
  - [x] If you extract the two-way `_scope_for_role` (Admin `ALL` else `SELF`) as a pure helper, unit-test it DB-free in [backend/tests/domain/](backend/tests/domain/) (or a service-level test with a bare role string) — Admin → `ALL`, Manager → `SELF`, Employee → `SELF`. The `LEAVE_ALREADY_TAKEN` predicate is `rules.is_wholly_past`, already covered by 2.6's domain tests — reuse, do not duplicate. If no other genuinely pure surface exists, say so honestly; the rest lives in integration.

- [x] **Task 11 — Integration tests, real PostgreSQL (AC1–AC9)**
  - [x] New [backend/tests/integration/test_cancellation_request.py](backend/tests/integration/test_cancellation_request.py). Reuse the `_World` fixture shape from [test_leave_request_decide.py](backend/tests/integration/test_leave_request_decide.py) (Department + Managers + reports + Admin + a materialized 20-day Leave Type + tokens + `TestClient`). **Extend the fixture cleanup** to delete `cancellation_request` rows (and any audit rows with `subject_type = CANCELLATION_REQUEST`) for the run's suffix **before** deleting the leave requests they FK. Helper to `_submit` then `_approve` a request into `APPROVED` (via the applicant's Manager) so a cancellable target exists; a managerless applicant's request is auto-`APPROVED` on submit (a shortcut to an Approved future-dated request). Cover:
    - **AC1 schema:** `cancellation_request` exists as its own table with the three-state CHECK; a `leave_request` still has exactly the four statuses (no fifth).
    - **AC2 raise:** the applicant raises against their own future Approved request → `201`, a `PENDING` CR referencing the LR. A **non-owner** raising against that LR → `404`, byte-identical to a nonexistent-id 404.
    - **AC3 past-dated:** an Approved request whose `end_date < today` → `400 LEAVE_ALREADY_TAKEN` (envelope carries that code). *(Build a past Approved request directly in the DB — a submit path refuses past ranges — or via a managerless past-dated insert; note how you construct it.)*
    - **AC4 pending is inert:** while a CR is `PENDING`, the target LR is still `APPROVED` and the balance `(reserved, consumed)` is **byte-unchanged** from before the raise.
    - **AC5 list scoping:** an Employee's `GET /cancellation-requests` returns only their own (a predicate, never a post-filter — another applicant's CR never appears); an Admin's returns all; the `status` filter narrows; the `items`/`page`/`page_size`/`total` envelope holds; `page_size` clamps to `MAX_PAGE_SIZE`.
    - **AC6 approve:** an Admin approves → `200`, CR `APPROVED`, LR `CANCELLED`, `consumed` down by exactly `leave_days` (Available restored), `reserved` unchanged; **two** new audit rows discriminated by `subject_type` (one CR `PENDING→APPROVED`, one LR `APPROVED→CANCELLED`), both `actor_id = <admin>`.
    - **AC7 reject:** an Admin rejects → `200`, CR `REJECTED`, LR **still** `APPROVED`, `consumed` **unchanged**; **one** new audit row (CR `PENDING→REJECTED`), LR untouched.
    - **AC8 non-Admin:** a Manager and an Employee calling approve/reject → `403 ACTION_NOT_PERMITTED` (role denial; assert the envelope + code), decided before any row is read (also assert a non-Admin gets 403, not 404, on a **nonexistent** id — the G3 property).
    - **AC2/guard race:** approving an already-`APPROVED`/`REJECTED` CR → `409 TRANSITION_NOT_ALLOWED`, **no** balance change, **no** new audit row (the transaction rolled back — assert both). Also: approving a CR whose target LR is no longer `APPROVED` (e.g. cancelled by a first, already-approved CR) → `409`, balance byte-unchanged.
    - **AC9 audit discrimination / SM-4:** after an approve, exactly one audit row with `subject_type=CANCELLATION_REQUEST` for this CR's approve and exactly one with `subject_type=LEAVE_REQUEST & to_state=CANCELLED` for the LR; the total audit count equals the transitions performed one-to-one (see Open Decision #3 for whether the raise adds one).
  - [x] **Append-only surface test is untouched by design:** `test_audit_and_request_repositories_expose_no_update_or_delete` pins only `audit_entry` (`{insert_audit_entry}`) and `leave_request` (the exact 5-set). This story adds **no** function to either — the LR `APPROVED → CANCELLED` move reuses the existing `leave_request.transition_status`; the new CR surface lives in the new `cancellation_request` module the test does not govern. Do **not** add a mutator to `leave_request`, and keep `audit_entry` at exactly `insert_audit_entry`.

- [x] **Task 12 — Full gate pass**
  - [x] `cd backend && pytest` — all pass (baseline **357** after Story 2.7; expect the count to rise). Armed guards this story touches: `test_scope_matrix.py` (three new registrations), `test_migrations_insert_nothing.py` (chain + no-DML), `test_model_migration_agreement.py` (0007 ↔ model `alembic check`), `test_scoped_getters.py` (the new CR reads take `actor`), `test_vocabulary_literals.py` (new constants imported, not typed), `test_balances_module_surface.py` (still exactly 8 — `release_consumed` reused, nothing added), `test_architecture.py` (import-linter, 7 contracts), `test_audit_and_request_repositories_expose_no_update_or_delete` (unchanged surfaces).
  - [x] `cd frontend && npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean. **No `getDay`/`getUTCDay` under `frontend/src`**, not even in a comment (`test_frontend_no_client_day_count.py` — the exact trap 2.5/2.7 tripped).
  - [x] Record a manual click-through (Employee raises a cancellation on an Approved request → it shows Pending; Admin approves from the Cancellation Requests screen → LR shows Cancelled and the applicant's Available rises) in the Dev Agent Record — honestly note if no live server was driven.

---

## Dev Notes

### The one-paragraph mental model
Story 2.7 moved a `PENDING` request onward. **2.8 is the ONLY path that unwinds an `APPROVED` one**, and it
does so through a *separate object*: a `cancellation_request` row (`AD-13` — not a fifth Leave Request
status, so "Approved, with a cancellation pending" is representable). The applicant **raises** one
against their own future-dated Approved request (scope `self`; past-dated → `400 LEAVE_ALREADY_TAKEN`;
the Leave Request is untouched — no transition, no balance move). An **Admin decides** it (scope `all`,
role Admin → a non-Admin is `403`). **Approve** is one transaction: guarded `UPDATE` the CR
`PENDING→APPROVED`, guarded `UPDATE` the LR `APPROVED→CANCELLED`, `release_consumed` returns the days,
and **two** audit rows (one per subject). **Reject** moves only the CR (`PENDING→REJECTED`), one audit
row, the leave untouched. **This story ships a migration** (0007) and a new table, model, repository,
service and routes — the balance primitive (`release_consumed`) and the AD-4 guarded-transition pattern
already exist.

### Reuse map — DO NOT reinvent these
| Need | Reuse (exact) | Source |
|---|---|---|
| Approve: return consumed days | `balances.release_consumed(session, *, employee_id, leave_type_id, leave_year, days)` — locks the row, guards `days ≤ consumed` | [services/balances.py:201](backend/app/services/balances.py#L201) |
| The LR `APPROVED → CANCELLED` guarded transition | `leave_request_repo.transition_status(session, *, request_id, from_status, to_status)` — **already exists**, reuse it (do NOT add a new LR mutator) | [repositories/leave_request.py:209](backend/app/repositories/leave_request.py#L209) |
| Locate the applicant's own Approved request (scope SELF) | `leave_request_repo.get_leave_request(session, actor, request_id, Scope.SELF)` | [repositories/leave_request.py:122](backend/app/repositories/leave_request.py#L122) |
| Past-date predicate for `LEAVE_ALREADY_TAKEN` | `rules.is_wholly_past(end_date, today)` — the same `end < today` test `PAST_DATE_RANGE` uses | [domain/leave_request_rules.py](backend/app/domain/leave_request_rules.py) |
| Scope predicate (SELF/ALL) | `employee_scope_predicate(scope, actor)` — composed into `select().where()`, never a post-filter; join `cancellation_request → leave_request → employee` | [repositories/scoping.py:59](backend/app/repositories/scoping.py#L59) |
| Audit row (append-only, same txn) | `audit_entry_repo.insert_audit_entry(session, *, subject_type, subject_id, from_state, to_state, actor_type, actor_id, reason, occurred_at)` | [repositories/audit_entry.py:28](backend/app/repositories/audit_entry.py#L28) |
| 404 raise (byte-identical) | `authz.not_found()` | [services/authorization.py](backend/app/services/authorization.py) |
| 403 role gate (Admin) | `require_role(authz.ROLE_ADMIN)` → `ACTION_NOT_PERMITTED` before the body | [api/v1/dependencies.py](backend/app/api/v1/dependencies.py) |
| 409 factory | `_transition_not_allowed()` (`TRANSITION_NOT_ALLOWED`, empty details) | [services/leave_requests.py:177](backend/app/services/leave_requests.py#L177) |
| Typed-refusal factory idiom | `_past_date_range()` — one `_MESSAGE` const + factory | [services/leave_requests.py:150](backend/app/services/leave_requests.py#L150) |
| Guarded-transition repo shape | `transition_status` (the `UPDATE … WHERE status = :from`, `synchronize_session=False`, return `rowcount`) — copy its shape for `transition_cancellation_status` | [repositories/leave_request.py:209](backend/app/repositories/leave_request.py#L209) |
| Scoped single-row + paged-list repo shapes | `get_leave_request` / `list_leave_requests` (join + predicate + `_READ_COLUMNS`) | [repositories/leave_request.py:122](backend/app/repositories/leave_request.py#L122) |
| Literal-free status-filter enum in `api/` | the `LeaveStatusFilter` runtime enum built from a service re-export | [api/v1/leave_requests.py:57](backend/app/api/v1/leave_requests.py#L57) |
| Pagination bound + envelope | `PageParams` (clamps to `MAX_PAGE_SIZE=100`) + `Page[T]` | [api/v1/pagination.py](backend/app/api/v1/pagination.py) |
| Migration shape (native uuidv7, DDL-only, named CHECK) | `0006_leave_request.py` | [alembic/versions/0006_leave_request.py](backend/alembic/versions/0006_leave_request.py) |
| Frontend hooks (onSettled self-heal, `.variables`, `ApiError.code`) | `leaveRequests.ts` + `ManagerQueuePanel.tsx` | [api/leaveRequests.ts](frontend/src/api/leaveRequests.ts), [features/leave/ManagerQueuePanel.tsx](frontend/src/features/leave/ManagerQueuePanel.tsx) |
| Frontend Admin role gate | `EmployeesPage` `ADMIN_ROLE`/`useMe` gate | [features/employees/EmployeesPage.tsx](frontend/src/features/employees/EmployeesPage.tsx) |

### Non-negotiable invariants (a violation is a review reject)
- **AD-13 — a Cancellation Request is an ENTITY, not a status.** `cancellation_request` is its own
  table with its own `PENDING/APPROVED/REJECTED` lifecycle, targeting one Approved Leave Request via
  `leave_request_id`. The target stays `APPROVED` (days `consumed`) the whole time a CR is Pending —
  only an *approved* CR moves it to `CANCELLED`. Never model this as a fifth `leave_request.status`.
- **AD-4 — every transition is a guarded conditional UPDATE.** Both the CR transition
  (`PENDING→APPROVED`/`PENDING→REJECTED`) and the LR transition (`APPROVED→CANCELLED`) are single
  `UPDATE … WHERE status = :from`; `rowcount == 0` ⇒ `409 TRANSITION_NOT_ALLOWED` and the whole
  transaction rolls back. `:from`/`:to` are `STATUS_*` constants (AD-21). Never read-then-write a status.
- **AD-8 / AD-9 — audit is append-only and same-transaction.** Every audit row goes through
  `insert_audit_entry` (the ONLY audit write path — the surface test pins it to exactly that). A
  rolled-back decision (a lost race, or a failed second guard) leaves **no** audit rows and **no**
  status change. `audit_entry` never gains an update/delete method. A cancellation writes to **both**
  subjects: the CR's transition and the LR's `CANCELLED` move, discriminated by `subject_type`.
- **AD-10 — authorization is a query predicate; absence is 404; 403 is "may see, may not act".** The
  raise locates the target LR under `Scope.SELF`; the list/decision locate the CR under the caller's
  scope, joining `cancellation_request → leave_request → employee` and applying
  `employee_scope_predicate` **in SQL**. A scope miss is `authz.not_found()` (byte-identical to a
  nonexistent id). `403 ACTION_NOT_PERMITTED` is reserved for the **role** denial (a non-Admin
  deciding, AC8), decided by `require_role(ADMIN)` before any row is read (G3). Never post-filter.
- **AD-17 — one balance writer, eight methods; approve uses `release_consumed`.** Only
  `services/balances.py` writes a balance column, and it stays at **exactly eight** methods
  (`test_balances_module_surface.py`) — `release_consumed` already exists and is the approved-
  cancellation path (BR-05). Do NOT add a ninth method; do NOT touch `consumed` anywhere else.
- **AD-18 — `leave_days` is frozen.** The decision returns/uses the **stored** `leave_days`; nothing
  recomputes it. `release_consumed(days = LR.leave_days)` uses the frozen figure.
- **AD-1 layering.** `api → services → {repositories, domain}`; `api/` imports neither `repositories/`
  nor `domain/` (role constants via `authz`; ORM/service dataclasses duck-typed `object`); `domain/`
  is pure; statuses wired in `main.py`. The new module trio (`api/v1/cancellation_requests.py`,
  `services/cancellation.py`, `repositories/cancellation_request.py`) must keep the 7 import-linter
  contracts green (`test_architecture.py`).
- **AD-21 / DR-10.** Every enumerated string is a `vocabulary.py` constant (import it — the migration
  DDL CHECK and the model `__table_args__` CHECK are the only exempt copies); quantities are `INTEGER`.

### The lock order — guarded UPDATEs BEFORE `release_consumed` (same as 2.7, extended)
Approve is one transaction in this strict order:
1. `get_cancellation_request` (plain SELECT, no lock) to authorize — scope `ALL` (Admin).
2. `transition_cancellation_status` CR `PENDING→APPROVED` (locks the CR row) → `0` ⇒ 409, roll back.
3. `leave_request_repo.transition_status` LR `APPROVED→CANCELLED` (locks the LR row) → `0` ⇒ 409, roll
   back. *(Runs BEFORE the balance mutation on purpose: if the LR already left `APPROVED` — a second CR
   approved first — this is a clean 409, not a `release_consumed` `ValueError` → raw 500.)*
4. `release_consumed` (locks the balance row).
5. Two `audit_entry` rows.
6. `commit()`.

**Deadlock analysis:** all transitions agree on the lock order (CR row → LR row → balance row); the
2.6 submission locks a balance row then INSERTs a *new* LR (never contending an existing LR row), and
2.7's transitions lock LR-then-balance. A CR-approve additionally locks the CR row *first*, but the CR
row is a fresh subject no other flow touches concurrently in a conflicting order. No cycle exists. (If
you are ever unsure, the guarded-UPDATE-before-balance rule alone guarantees a lost race is a 409, not
a 500 — that is the property the tests assert.)

### The two cancel flows — do NOT conflate them
| | 2.7 `POST /leave-requests/<id>/cancel` | 2.8 `POST /leave-requests/<id>/cancellation-requests` |
|---|---|---|
| Target state | `PENDING` request | `APPROVED` request |
| Who | the applicant (scope `self`) | the applicant raises (scope `self`); an **Admin** decides |
| Balance | `release_reserved` (reserved→available) | `release_consumed` (consumed→available), on approve |
| Object | one guarded `UPDATE` on the LR (`PENDING→CANCELLED`) | a **separate** `cancellation_request` row; LR only moves on approve |
| Refusals | non-owner 404, settled 409 | non-owner 404, past-dated **400 `LEAVE_ALREADY_TAKEN`**, non-Admin decide **403**, lost race **409** |

### Scope, role, and the 403-vs-404 split (get this exactly right)
| Endpoint | Role gate (`api/`) | Scope (service) | Denials |
|---|---|---|---|
| `POST /leave-requests/{id}/cancellation-requests` | `get_current_employee` (any) | `SELF` (locate own LR) | non-owner target → **404**; past-dated → **400 LEAVE_ALREADY_TAKEN**; non-`APPROVED` → **409** (Open Dec #2) |
| `GET /cancellation-requests` | `get_current_employee` (any) | Admin `ALL` / else `SELF` | — (a filtered empty list, never 404) |
| `POST /cancellation-requests/{id}/approve` | `require_role(ROLE_ADMIN)` | `ALL` | non-Admin → **403**; nonexistent → **404**; not `PENDING` (CR) or LR not `APPROVED` → **409** |
| `POST /cancellation-requests/{id}/reject` | `require_role(ROLE_ADMIN)` | `ALL` | same as approve (no balance move) |

Two traps people fall into: **(1)** approve/reject are `require_role(ADMIN)` — api-contracts §4.6 grants
the decision to the **Admin**, scope `all` (NOT the Manager, NOT `reports`; a Cancellation Request is
Admin-decided, unlike a Leave Request's approve which is the Manager's). **(2)** `GET
/cancellation-requests` is scope **`self, all`** only — a Manager is not `reports` here; they see their
own filings as an applicant (`SELF`), so the resolver is *two-way* (Admin `ALL` else `SELF`), not the
three-way `_scope_for_role` in `leave_requests.py`.

### No `UNIQUE` on `leave_request_id`, no requester/decider/timestamp columns (ERD §2.1, §3)
A Leave Request may have **multiple** Cancellation Requests over time (a rejected one may be followed
by another — ERD §3, "zero or more"), so **do not** add `UNIQUE (leave_request_id)`, and **do not**
add a guard against a second Pending CR (the spec permits what the model permits). The requester is
`leave_request.employee_id` (**no requester column**); the deciding Admin is the `actor_id` on the
audit row (**no decider column**); ordering comes from the UUIDv7 PK (**no `created_at`**). Adding any
of these is inventing schema the ERD does not name.

### Migration + model must agree, byte-for-byte
`test_model_migration_agreement.py` runs `alembic check`; the `CancellationRequest` model and 0007 must
have identical columns, types, the FK, and the CHECK (same `name="cancellation_request_status_check"`).
`test_migrations_insert_nothing.py` forbids any DML in the migration and pins the ordered chain — append
`0007_cancellation_request.py`. Do NOT touch the earlier migrations or their guard tests.

### Testing standards (this codebase)
- `pytest` **is** the build — no CI; guards run in-suite. Baseline **357** (post-2.7).
- **DB-free domain tests** → [backend/tests/domain/](backend/tests/domain/). **Integration** →
  [backend/tests/integration/](backend/tests/integration/) against real PostgreSQL (`conftest.py`
  skips loudly if unreachable); `import app.main` wires `CODE_TO_STATUS`.
- **Assert the negatives:** a Pending CR leaves the balance byte-unchanged; a rejected CR leaves the LR
  `APPROVED` and `consumed` unchanged; a lost-race approve leaves balance byte-unchanged and adds no
  audit row; two 404 bodies (out-of-scope and nonexistent) are byte-identical; a non-Admin decide is
  403 (not 404) even on a nonexistent id; the audit count matches transitions one-to-one.
- Frontend has no test runner — proof is `npm run build` + `npm run lint` clean, plus a declared manual
  click-through. **No `getDay`/`getUTCDay` under `frontend/src`**, not even in a comment.

### Project Structure Notes
- **New files:** `alembic/versions/0007_cancellation_request.py`, `repositories/cancellation_request.py`,
  `services/cancellation.py`, `api/v1/cancellation_requests.py`,
  `tests/integration/test_cancellation_request.py`, `frontend/src/api/cancellationRequests.ts`,
  `frontend/src/features/leave/RequestCancellationPanel.tsx`,
  `frontend/src/features/leave/CancellationRequestsPanel.tsx` (and possibly a small `tests/domain/`
  test for the two-way scope helper).
- **Extend, do not fork:** `domain/vocabulary.py`, `main.py`, `repositories/models.py`,
  `api/v1/leave_requests.py` (the one raise route), `api/v1/router.py` (include the new router),
  `frontend/src/api/index.ts`, `frontend/src/App.tsx`, `frontend/src/index.css`,
  `tests/test_scope_matrix.py`, `tests/test_migrations_insert_nothing.py`.
- **Naming:** service module `cancellation` (spine's `services/cancellation`); repo/table
  `cancellation_request`; fns `verb_noun` (`raise_cancellation_request`,
  `transition_cancellation_status`, `get_cancellation_request`).
- **Commit:** `feat(story-2.8): <summary>`, matching the git-log convention; one commit after review → done.

### Cross-story context (Epic 2 sequencing)
- **Story 2.9** (the audit trail read) adds `GET /audit-entries` (Admin-only) and the **`SM-4`
  one-to-one** count test across *all* transitions — including this story's. Keep every transition
  exactly one audit row, and settle Open Decision #3 (raise-audit) consistently, so 2.9's count holds.
- **Story 2.10** (leave-year rollover) and **2.11/2.12** (recalculation) touch balances via the other
  AD-17 mutators; nothing here blocks them.
- **Inherited, accepted limitations (do NOT "fix" here):** (1) a Manager's `GET /leave-requests`
  returns their *reports'* requests, not their own (2.7 Open Q#4) — hence the employee cancellation
  panel targets the EMPLOYEE role (Open Decision #6); (2) a deactivated Employee holding a live token
  can still act until it expires (AD-14); (3) the concurrent-create materialization race; (4) unbounded
  `page` → bigint OFFSET 500. All in [deferred-work.md](_bmad-output/implementation-artifacts/deferred-work.md).

### Open Decisions (decide during dev; keep consistent across code + tests)

**#1 — Cancellation Request status constants.** Reuse `STATUS_PENDING`/`STATUS_APPROVED`/
`STATUS_REJECTED` vs. coin `CANCELLATION_STATUS_*`. **Recommendation: reuse** — the values are
identical strings and AD-21 says each string is declared once, so a second same-valued constant would
violate that. The `subject_type` discriminates which entity a status belongs to.

**#2 — a non-`APPROVED` raise target.** The AC covers only Approved targets (future → create, past →
400). For a located target that is `PENDING`/`REJECTED`/`CANCELLED`: **Recommendation: refuse with
`409 TRANSITION_NOT_ALLOWED`** (the "not in a state that allows this action" message fits, reuses
existing vocab, and is not a role/scope issue). A Pending request is cancelled via 2.7's `/cancel`.
Optionally lock the LR row (`with_for_update`) and re-check `APPROVED` under the lock to make a
concurrent LR transition a clean 409 rather than a stale read — nice-to-have, not required by the ACs.

**#3 — does the RAISE write an audit row?** The AC9 count scenario says an approved CR has "one for the
CR's own transition and one for the LR's move to CANCELLED." Two readings:
  - **Option A (recommended): audit every transition, including the raise** (`NULL → PENDING`,
    `reason=REASON_CANCELLATION_REQUESTED`). This keeps AD-8/SM-4 one-to-one and mirrors leave-request
    *submission* (which IS audited, 2.6). Under A, the AC9 test asserts the **approval** produces
    exactly two rows discriminated by `subject_type` (existence/uniqueness per subject), and reject
    produces one; the raise's row was written earlier. Needs the one new `REASON_CANCELLATION_REQUESTED`.
  - **Option B: only decisions write audit rows** (raise writes none). This matches the AC's literal
    total-of-two and needs no new reason constant, but breaks symmetry with submission and risks 2.9's
    SM-4 count if a CR raise is deemed a "transition."
  **Pick one, and make the AC9 test + the 2.9 SM-4 expectation agree with it.** Recommendation: A.

**#4 — an index on `cancellation_request`.** ERD §4.4 names none. **Recommendation: none** (follow the
ERD; the Admin list is a few rows at Epic-2 scale). If added, mirror it byte-identically in the model
or `alembic check` fails.

**#5 — the CR response shape.** api-contracts §4.6 defers bodies to OpenAPI. **Recommendation:**
`CancellationRequestResponse` = `id`, `leave_request_id`, `status`, plus the applicant
(`employee_id`/`employee_name`) and the target-LR summary (`start_date`/`end_date`/`leave_days`/
`leave_type_code`/`leave_type_name`) so the Admin screen renders "whose request, which leave, its
dates" (AC10) without a second round-trip — one join to `employee`, one to `leave_type` off the LR.
Project by hand in `api/`; mirror in the frontend `CancellationRequest` interface.

**#6 — the employee cancellation panel's audience.** A Manager's `GET /leave-requests` returns their
*reports'* requests (2.7 own-requests gap), so a `useLeaveRequests('APPROVED')`-driven panel shows the
wrong list for a Manager, and the SELF-scoped raise would 404 on a report's request. **Recommendation:
gate the panel to the EMPLOYEE role**; a Manager/Admin self-cancelling Approved leave is API-only until
the own-requests gap is closed in a later filter story. (Do not widen `GET /leave-requests` here.)

### References
- [Source: epics.md#Story 2.8] (lines 1145–1201) — acceptance criteria, verbatim; the discoverability
  rationale for `GET /cancellation-requests`; the two-audit-rows-per-approval requirement.
- [Source: ARCHITECTURE-SPINE.md] — AD-13 (Cancellation Request is an entity, not a status; target
  stays Approved; approve releases consumed via AD-17), AD-4 (guarded conditional update, of a Leave
  Request **or Cancellation Request**), AD-8 (audit one-per-transition, both subjects, same txn),
  AD-9 (append-only), AD-10 (predicate authorization, absence-is-404), AD-17 (`release_consumed` is
  BR-05's approved-cancellation path; exactly 8 methods), AD-21 (vocabulary), AD-1 (layering);
  Capability map (`services/cancellation`); the Cancellation Request lifecycle diagram.
- [Source: api-contracts.md §4.6, §2, §1] — the four endpoints with roles/scopes (raise: any/self;
  list: any/self,all; approve+reject: **Admin/all**); `LEAVE_ALREADY_TAKEN` → **400**;
  `ACTION_NOT_PERMITTED` → 403; `TRANSITION_NOT_ALLOWED` → 409; the 403-vs-404 G3 settlement; the
  `items`/`page`/`page_size`/`total` envelope and the `status` filter; the `{code,message,details}`
  envelope.
- [Source: erd.md §2, §2.1, §3, §4.2] — `cancellation_request` (`id`, `leave_request_id` FK, `status`
  TEXT; CHECK `IN ('PENDING','APPROVED','REJECTED')`; no requester/decider/timestamp column; multiple
  per Leave Request over time, no `UNIQUE`); `audit_entry.subject_type` ∈ {`LEAVE_REQUEST`,
  `CANCELLATION_REQUEST`}, polymorphic `subject_id` (no FK); "a cancellation writes entries for both
  objects" (§2.1).
- [Source: 2-7-…decide.md / leave_requests.py] — the AD-4 guarded-transition pattern, the lock-order
  rationale (guarded UPDATE before balance), the `_decide` shape, the literal-free status-filter enum,
  the three-way vs. two-way scope resolver, the `_World` fixture and the byte-identical-404 assertion.
- [Source: 2-6-…submit.md] — the tables/vocabulary this story extends; the code-layer append-only
  decision (AD-9); the audit-row shape (`from_state=None` for a creation).
- [Source: balances.py:201] — `release_consumed` semantics and its `days ≤ consumed` guard.
- [Source: test_scope_matrix.py / test_migrations_insert_nothing.py / test_model_migration_agreement.py]
  — the three registrations/updates this story must make and the migration↔model agreement it must hold.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context)

### Debug Log References

- Migration 0007 applied to live PostgreSQL; `alembic check` (via `test_model_migration_agreement.py`)
  reports an empty diff — model ↔ migration agree byte-for-byte.
- Two pre-existing schema guards grew by one entry, as they do per schema story:
  `test_migration_smoke.py` `HEAD_REVISION` → `0007_cancellation_request`; `test_schema_1_2.py`
  expected-table set gained `cancellation_request`.
- Full backend suite: **388 passed** (baseline 359; +16 cancellation integration, +4 CR-scope domain
  unit, +3 SM-3 matrix registrations, and the grown chain/table/vocabulary guards).
- Frontend `npm run build` (tsc -b && vite build) and `npm run lint` (oxlint) both clean; the
  `test_frontend_no_client_day_count.py` guard (no `getDay`/`getUTCDay`) stays green in the backend
  suite.

### Completion Notes List

Implemented the approved-leave cancellation half of the lifecycle as a NEW `cancellation_request`
entity (AD-13 — not a fifth Leave Request status). All 10 ACs satisfied.

**Open Decisions — resolved as recommended, consistently across code + tests:**
- **#1 (CR status constants):** REUSED `STATUS_PENDING`/`STATUS_APPROVED`/`STATUS_REJECTED` (AD-21 —
  each string declared once; `subject_type` discriminates the entity). The `cancellation_request`
  CHECK DDL (migration + model `__table_args__`) is the only exempt literal copy.
- **#2 (non-`APPROVED` raise target):** refused with `409 TRANSITION_NOT_ALLOWED`
  (`test_raise_against_non_approved_request_is_409`).
- **#3 (raise-audit):** Option A — the raise writes one `NULL → PENDING` audit row
  (`REASON_CANCELLATION_REQUESTED`), keeping AD-8/SM-4 one-to-one. AC9 asserts the APPROVE produces
  exactly one CR-subject row and one LR-subject row; the raise's row is earlier.
- **#4 (index):** none (follows ERD §4.4).
- **#5 (response shape):** `CancellationRequestResponse` = `id`, `leave_request_id`, `status`,
  applicant (`employee_id`/`employee_name`), target-LR summary
  (`start_date`/`end_date`/`leave_days`/`leave_type_code`/`leave_type_name`).
- **#6 (employee-panel audience):** `RequestCancellationPanel` is gated to the EMPLOYEE role (the 2.7
  Manager-own-requests gap); a Manager/Admin self-cancelling Approved leave is API-only until that
  gap closes.

**Reuse (no reinvention):** `balances.release_consumed` (no 9th balance method — surface stays at 8),
`leave_request.transition_status` for the LR `APPROVED → CANCELLED` move (no new LR mutator — the
append-only surface test is untouched), the AD-4 guarded-transition pattern, `authz.not_found()`,
`require_role(ADMIN)`, the literal-free status-filter enum, `PageParams`/`Page[T]`.

**Lock order** (approve, one transaction): guarded UPDATE CR `PENDING→APPROVED` → guarded UPDATE LR
`APPROVED→CANCELLED` → `release_consumed` → two audit rows → commit. A lost race (either guard = 0
rows) is a clean 409 before any balance moves — proved by
`test_approving_a_settled_cr_is_409_and_writes_nothing` and
`test_approving_cr_whose_lr_already_cancelled_is_409` (balance byte-unchanged, no new audit row).

**Manual verification (honest note):** No browser click-through was performed. The full authenticated
flow (raise → PENDING inert → Admin approve → LR CANCELLED → Available restored; reject; 403; 404;
409 races; audit discrimination) is exercised end-to-end by the 16 integration tests against **real
PostgreSQL** through the **real FastAPI router**. A live `uvicorn` server was additionally driven:
`GET /health` → 200; `GET /cancellation-requests` and `POST /cancellation-requests/<id>/approve`
without a token → `401 TOKEN_INVALID` inside the `{code,message,details}` envelope. All four routes
are present in the generated OpenAPI and match the frontend paths.

### File List

**New (backend):**
- `backend/alembic/versions/0007_cancellation_request.py`
- `backend/app/repositories/cancellation_request.py`
- `backend/app/services/cancellation.py`
- `backend/app/api/v1/cancellation_requests.py`
- `backend/tests/domain/test_cancellation_scope_for_role.py`
- `backend/tests/integration/test_cancellation_request.py`

**New (frontend):**
- `frontend/src/api/cancellationRequests.ts`
- `frontend/src/features/leave/RequestCancellationPanel.tsx`
- `frontend/src/features/leave/CancellationRequestsPanel.tsx`

**Modified (backend):**
- `backend/app/repositories/models.py` (added `CancellationRequest` model)
- `backend/app/domain/vocabulary.py` (`LEAVE_ALREADY_TAKEN`, `SUBJECT_CANCELLATION_REQUEST`,
  `REASON_CANCELLATION_REQUESTED` + `__all__`)
- `backend/app/main.py` (`CODE_TO_STATUS`: `LEAVE_ALREADY_TAKEN` → 400)
- `backend/app/api/v1/leave_requests.py` (the raise route + imports)
- `backend/app/api/v1/router.py` (include the new router)
- `backend/tests/test_scope_matrix.py` (3 SM-3 registrations)
- `backend/tests/test_migrations_insert_nothing.py` (chain: append `0007_cancellation_request.py`)
- `backend/tests/integration/test_migration_smoke.py` (`HEAD_REVISION` → `0007`)
- `backend/tests/integration/test_schema_1_2.py` (expected tables + `cancellation_request`)

**Modified (frontend):**
- `frontend/src/api/index.ts` (barrel exports)
- `frontend/src/App.tsx` (mount both panels)

## Change Log

- 2026-07-13 — Story 2.8 implemented (dev-story). NEW `cancellation_request` table (0007 migration +
  model, AD-13 — not a fifth status), repository, `services/cancellation`, `api/v1/
  cancellation_requests` + the raise route on the leave-requests router, and both frontend panels
  (Employee raise/track gated to EMPLOYEE; Admin decide gated to ADMIN). Approve = guarded CR
  `PENDING→APPROVED` + guarded LR `APPROVED→CANCELLED` + `release_consumed` + two audit rows
  (discriminated by `subject_type`); reject = CR `PENDING→REJECTED` + one audit row, leave untouched;
  raise audited `NULL→PENDING` (Option A). Open Decisions #1–#6 resolved as recommended. Reused
  `release_consumed` (balances stays at 8 methods) and `transition_status` (no new LR mutator).
  Backend pytest **388 passed**; frontend build + lint clean. Status in-progress → review.

- 2026-07-13 — Story 2.8 context engineered (create-story). Approved-leave cancellation via a NEW
  `cancellation_request` table (0007 migration + model, AD-13 — not a fifth status): applicant raises
  against own future Approved request (scope self; past-dated → 400 `LEAVE_ALREADY_TAKEN`; LR
  untouched), Admin decides (scope all, role Admin → non-Admin 403). Approve = guarded CR
  `PENDING→APPROVED` + guarded LR `APPROVED→CANCELLED` + `release_consumed` + two audit rows
  (discriminated by subject_type); reject = CR `PENDING→REJECTED` + one audit row, leave untouched.
  New `services/cancellation`, `repositories/cancellation_request`, `api/v1/cancellation_requests`,
  employee raise/track panel + Admin Cancellation Requests screen. Reuses `release_consumed` (no 9th
  balance method), `transition_status` (no new LR mutator), the AD-4 pattern, the SM-3 harness. Open
  Decisions: CR status constants (reuse), non-Approved raise (409), raise-audit (Option A), CR index
  (none), response shape, employee-panel audience (EMPLOYEE role). Status backlog → ready-for-dev.

## Open Questions (for the dev agent / reviewer)

1. **Raise-audit (Open Decision #3)** — does raising a Cancellation Request write a `NULL → PENDING`
   audit row (Option A, recommended, needs `REASON_CANCELLATION_REQUESTED`), or do only Admin decisions
   write audit rows (Option B)? This governs the exact AC9 count and must agree with Story 2.9's SM-4
   one-to-one test. Recommendation: Option A.
2. **Non-`APPROVED` raise target (Open Decision #2)** — refuse with `409 TRANSITION_NOT_ALLOWED`
   (recommended) vs. `404`? The ACs only test Approved targets. Confirm the code and whether to lock
   the LR row for a clean concurrent-transition 409.
3. **CR status constants (Open Decision #1)** — reuse `STATUS_PENDING/APPROVED/REJECTED` (recommended,
   AD-21) vs. coin `CANCELLATION_STATUS_*`.
4. **Response shape + employee-panel audience (Open Decisions #5, #6)** — confirm the
   `CancellationRequestResponse` fields (applicant + target-LR summary) and that the employee raise
   panel is gated to the EMPLOYEE role (inheriting 2.7's Manager-own-requests gap).

## Review Findings

<!-- Code review 2026-07-13 (bmad-code-review): 3 layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor), full spec-aware mode. 2 decision-needed → both resolved as PATCH and applied, 2 deferred, 7 dismissed. -->

- [x] [Review][Patch][Applied] Approve path re-checks the past-date boundary that raise enforces [backend/app/services/cancellation.py:270] — `approve_cancellation_request` now runs `is_wholly_past(row.end_date, today)` after locating the CR and refuses `400 LEAVE_ALREADY_TAKEN` (rolling back) so a CR raised while the leave was future but decided after the dates fully pass cannot un-take taken leave. Reject stays exempt (refunds nothing, LR untouched — AC7). New test `test_approving_cr_whose_leave_is_now_past_is_400`.
- [x] [Review][Patch][Applied] Raise refuses a second concurrent PENDING Cancellation Request for one Leave Request [backend/app/services/cancellation.py:207 + repositories/cancellation_request.py:pending_exists_for_leave_request] — new repo helper `pending_exists_for_leave_request`; `raise_cancellation_request` now refuses `409 TRANSITION_NOT_ALLOWED` when an unresolved PENDING CR already exists for the target LR. Sequential re-raise after a REJECTED filing is still allowed (ERD §3). New tests `test_second_pending_cr_for_same_request_is_409`, `test_re_raise_after_rejection_is_allowed` (obsolete two-concurrent-CR race test `test_approving_cr_whose_lr_already_cancelled_is_409` removed — that state is now unreachable via the API).
- [x] [Review][Defer] Admin queue, applicant approved-leave list, and applicant CR list are all page-1-only (DEFAULT_PAGE_SIZE=50) with no pager [frontend/src/features/leave/CancellationRequestsPanel.tsx:56, RequestCancellationPanel.tsx] — deferred, pre-existing app-wide pattern (ManagerQueuePanel, `useLeaveRequests` from 2.7 share the identical page-1-only idiom). More consequential here because the Admin queue is the sole discovery route for CRs; PENDING CRs beyond 50 are undecidable until earlier ones clear.
- [x] [Review][Defer] Boundary/path test gaps [backend/tests/integration/test_cancellation_request.py] — deferred, pre-existing. The `end_date == today` in-progress boundary of `is_wholly_past` and the role-agnostic Manager/Admin API self-cancel raise path (scope SELF, reachable API-only per Open Decision #6) both ship without coverage.
