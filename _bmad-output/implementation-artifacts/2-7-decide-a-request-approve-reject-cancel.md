---
baseline_commit: f5132447f883e6de642605530d829a8856b673dc
---

# Story 2.7: Decide a Request — Approve, Reject, Cancel

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **Manager**,
I want **to approve or reject the requests of my own Direct Reports**,
so that **a decision is made by someone with the authority to make it**.

This is the **transition** half of the Leave Request lifecycle. Story 2.6 created the `leave_request`
and `audit_entry` tables and the atomic `POST /leave-requests` that admits a row as `PENDING` (or
managerless-`APPROVED`). This story adds the four state changes that move a `PENDING` row onward —
**approve**, **reject**, **cancel** — each a single AD-4 guarded `UPDATE`, plus the **two scoped read
endpoints** (`GET /leave-requests` and `GET /leave-requests/<id>`) a Manager needs to *see* the queue
they decide from. It introduces **no schema migration** (the tables already exist) and **satisfies
SM-3** for the first time — populating the harness Story 1.7 built.

## Acceptance Criteria

> Verbatim from `epics.md` §"Story 2.7" (lines 1091–1144). BDD blocks numbered AC1–AC10 for task
> traceability. **This story adds no migration** — every table it touches already ships from 0006.

**AC1 — approve / reject move the days and write one Audit Entry**
**Given** a Pending request and its applicant's current Manager
**When** the Manager calls `POST /api/v1/leave-requests/<id>/approve` or `.../reject`
**Then** approval moves the days from `reserved` to `consumed` via `consume_reserved`, and rejection
releases them via `release_reserved`
**And** each transition writes **exactly one** Audit Entry naming that Manager and the moment (`FR-09`,
`AD-17`, `AD-8`).

**AC2 — every transition is a guarded conditional UPDATE; a lost race is 409, not a silent overwrite**
**Given** any transition of a Leave Request
**When** it is performed
**Then** it is a single `UPDATE ... SET status = :to WHERE id = :id AND status = :from`
**And** zero affected rows means the transition is refused with `409 TRANSITION_NOT_ALLOWED` and the
transaction rolls back — a Manager approving a request the applicant has just cancelled receives a
failure, not a silent overwrite (`AD-4`, `FR-09`).

**AC3 — the applicant cancels their own Pending request**
**Given** the applicant
**When** they call `POST /api/v1/leave-requests/<id>/cancel` on their own Pending request
**Then** the reservation is released (`release_reserved`)
**And** no other Employee can cancel it (a non-owner gets a byte-identical `404`), and it cannot be
cancelled once it leaves `PENDING` (a settled request gets `409 TRANSITION_NOT_ALLOWED`) (`FR-09`).

**AC4 — `GET /leave-requests`: scoped, paged, filterable by status**
**Given** an authenticated caller
**When** they call `GET /api/v1/leave-requests`, optionally filtered by `status`
**Then** an Employee receives their own Leave Requests, a Manager receives their Direct Reports', and
an Admin receives all — the scope applied as a **SQL predicate, never as a post-filter**
**And** the response carries `items`, `page`, `page_size` and `total`, bounded by the server maximum
(`FR-03`, `AD-10`, `NFR-04`, `NFR-11`).

**AC5 — `GET /leave-requests/<id>`: scoped, returns the stored (frozen) `leave_days`**
**Given** an authenticated caller and a Leave Request identifier inside their scope
**When** they call `GET /api/v1/leave-requests/<id>`
**Then** the request is returned with its Leave Type, date range, stored `leave_days` and current state
**And** `leave_days` is the value stored at admission and is **never recomputed** (`AD-18`).

**AC6 — an Admin may read every request and decide none → `403 ACTION_NOT_PERMITTED`**
**Given** an Admin
**When** they attempt to approve or reject any Leave Request
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — an Admin may read every request and
decide none (`DR-13`, api-contracts §1). *(This is a **role** denial, decided before any row is read —
G3: role admits → run scope → miss is 404; role denies → 403.)*

**AC7 — a non-manager of the applicant gets a byte-identical `404` on every id-bearing endpoint**
**Given** a Manager who is not the applicant's Manager
**When** they call any endpoint naming that Leave Request's identifier — including
`GET /api/v1/leave-requests/<id>`, `approve`, `reject` and `cancel`
**Then** the response is `404`, **byte-identical** to a nonexistent identifier
**And** the endpoint is registered in Story 1.7's `SM-3` matrix, which this story **populates** (`FR-03`,
`AD-10`, `SM-3`).

**AC8 — authority is evaluated at decision time (reassignment)**
**Given** a Pending request whose applicant is reassigned to a different Manager
**When** the new Manager decides it
**Then** the decision succeeds, because authority is evaluated **at decision time** rather than at
submission (`DR-12`) — the scope predicate binds `Employee.manager_id == :actor_id` at request time,
not from a stored edge.

**AC9 — the Manager queue (frontend)**
**Given** the React application and an authenticated Manager
**When** they open their queue
**Then** they see the requests awaiting their decision (their Direct Reports' `PENDING` requests), and
can approve or reject each — after which the queue and any affected balances refresh.

**AC10 — SM-3 is satisfied here (the correctness proof, not just the harness)**
**Given** the four new identifier endpoints
**When** the test suite runs
**Then** `tests/test_scope_matrix.py` registers each with the scope api-contracts §4 grants it, **and**
integration tests prove a non-report Manager, and a non-owner Employee, receive a `404` byte-identical
to a nonexistent id — the first *satisfaction* of `SM-3`, whose harness Story 1.7 built (`SM-3`,
`SM-4`).

---

## Tasks / Subtasks

> Ordered so each task compiles and tests green before the next. Backend first (vocabulary → repository
> reads + guarded transition → service commands + reads → routes), then the SM-3 matrix registration,
> then the frontend queue, then tests, then the full gate. **No migration, no model change** — the
> tables and columns already ship from 0006.

- [x] **Task 1 — Vocabulary: one new code + the transition reasons (AC1, AC2, AC6, AC7)**
  - [x] In [backend/app/domain/vocabulary.py](backend/app/domain/vocabulary.py) add **one** new error code: `TRANSITION_NOT_ALLOWED = "TRANSITION_NOT_ALLOWED"` (→ 409, api-contracts §2 — "the guarded update matched zero rows; someone committed first"). Declare it beside its raise site's rationale, following the per-code comment discipline.
  - [x] `ACTION_NOT_PERMITTED` (403) and `RESOURCE_NOT_FOUND` (404) **already exist** ([vocabulary.py:69-70](backend/app/domain/vocabulary.py#L69), both already mapped in `main.py`). The role gate raises the first via `authz.assert_role`; the scoped read raises the second via `authz.not_found()`. **Do not redeclare or rewire either.**
  - [x] Add the three transition **reason** constants for the `audit_entry.reason` column (NOT NULL, AD-21). See **Open Decision #1** in Dev Notes for naming. Recommended: `REASON_APPROVED = "APPROVED"`, `REASON_REJECTED = "REJECTED"`, `REASON_CANCELLED = "CANCELLED"` — symmetric with the existing `REASON_SUBMITTED`/`REASON_AUTO_APPROVED_NO_MANAGER`. Add every new name to `__all__`.
  - [x] The actor/subject vocabulary this story needs **already exists**: `ACTOR_EMPLOYEE`, `SUBJECT_LEAVE_REQUEST`, and the four `STATUS_*` constants ([vocabulary.py:158-196](backend/app/domain/vocabulary.py#L158)). Reuse them; the guarded `UPDATE`'s `:from`/`:to` **must** be `STATUS_*` constants (AD-21 exists precisely so a case/typo mismatch never makes AD-4's UPDATE match zero rows spuriously).
  - [x] **Do not** introduce bare enumerated strings anywhere in `app/` — `test_vocabulary_literals.py` AST-scans and fails on any. The only exempt literal copies remain the model `__table_args__` CHECK and the migration DDL (unchanged here).

- [x] **Task 2 — Wire the one new code in the composition root (AC2)**
  - [x] In [backend/app/main.py](backend/app/main.py) `CODE_TO_STATUS.update({...})` add exactly one entry: `vocabulary.TRANSITION_NOT_ALLOWED: 409` (beside the Story 2.6 block at [main.py:93-97](backend/app/main.py#L93)). Statuses are set **here only** — `api/v1/errors.py` imports neither `domain/` nor the vocabulary (contract 2).

- [x] **Task 3 — Repository: the scoped reads + the guarded transition (AC2, AC4, AC5, AC7)**
  - [x] **Extend** [backend/app/repositories/leave_request.py](backend/app/repositories/leave_request.py) (do not create a parallel file). Add three functions:
    - `get_leave_request(session, actor, request_id, scope) -> LeaveRequest | None` — a **scoped** single-row read. Join `leave_request → employee` and apply `employee_scope_predicate(scope, actor)` in the `WHERE` alongside `LeaveRequest.id == request_id`. Returns `None` for a nonexistent id **OR** an out-of-scope one (the service turns both into a byte-identical 404). This is the exact shape of [employee.py `get_employee`](backend/app/repositories/employee.py#L127) and [leave_balance.py `get_balance`](backend/app/repositories/leave_balance.py). It is a `get_` getter taking a `session`, so `test_scoped_getters.py` requires the `actor` param — which it has. **Not** `with_for_update()` (see the lock-order note in Dev Notes).
    - `list_leave_requests(session, actor, *, scope, status, limit, offset) -> tuple[list[LeaveRequest], int]` — the **scoped, paged, optionally status-filtered** list. Join `leave_request → employee`, apply `employee_scope_predicate(scope, actor)`, add `LeaveRequest.status == status` **only when** `status is not None`, order deterministically (recommend `LeaveRequest.id.desc()` — UUIDv7 is time-ordered, so this is newest-first; document the choice), `.limit(limit).offset(offset)`; compute `total` with the same predicate+filter. Return `(rows, total)` — the [employee.py `list_employees`](backend/app/repositories/employee.py#L94) shape. Eager-load `LeaveType` if the response needs the Leave Type (see AC5/Open Decision #2 on the response shape). `list_` getter → takes `actor` (guard satisfied).
    - `transition_status(session, *, request_id, from_status, to_status) -> int` — the AD-4 guarded conditional update: `session.execute(update(LeaveRequest).where(LeaveRequest.id == request_id, LeaveRequest.status == from_status).values(status=to_status).execution_options(synchronize_session=False))` and **return `result.rowcount`**. `synchronize_session=False` because we do not reuse a stale ORM object's `status` after (we hold the row locked by the UPDATE itself). This is a write governed by the command's transaction, not a scoped getter, and it is **not** free-form: it is the single sanctioned conditional transition (AD-4). Do **not** add a general `update_*`/`delete_*` method.
  - [x] **Update the module docstring** — it currently says the module "exposes an INSERT and a COUNT — and NOTHING that updates or deletes". That was true through 2.6; now this story adds the AD-4 guarded transition and the two scoped reads. Reframe: `audit_entry` stays strictly append-only (INSERT only); `leave_request` gains its **guarded, conditional** transition (the *only* sanctioned mutation) plus scoped reads — no free-form update/delete path.

- [x] **Task 4 — Service: the three transition commands + the two reads (AC1–AC8)**
  - [x] **Extend** [backend/app/services/leave_requests.py](backend/app/services/leave_requests.py) (alongside `preview_leave_request`/`submit_leave_request` — do not create a new file). Add a `_transition_not_allowed() -> DomainError` factory (code `TRANSITION_NOT_ALLOWED`, empty `details` — a state conflict names no numbers; message like "the request is no longer in a state that allows this action"), following the module's `_invalid_date_range` idiom.
  - [x] Add a **private helper** that all three transitions share, e.g. `_decide(actor, request_id, *, from_status, to_status, scope, actor_type, actor_id, reason, mutate)` — one transaction that: (1) locates the request scoped via `get_leave_request` → `None` ⇒ `authz.not_found()` (404, AC7); (2) runs `transition_status(from_status → to_status)` → `0 rows` ⇒ `raise _transition_not_allowed()` (409, AC2 — the transaction rolls back, nothing else has been written); (3) `mutate(session, ...)` the balance (`consume_reserved` or `release_reserved`) using the located row's `employee_id`, `leave_type_id`, `leave_days` and `leave_year = request.start_date.year`; (4) write **exactly one** `audit_entry` (`subject_type=SUBJECT_LEAVE_REQUEST`, `subject_id=request_id`, `from_state=from_status`, `to_state=to_status`, `actor_type`, `actor_id`, `reason`, `occurred_at=_now()`); (5) `commit()`. **Order matters — see the lock-order note in Dev Notes: the guarded transition runs BEFORE the balance mutation.**
    - `approve_leave_request(actor, request_id)` → `from=PENDING`, `to=APPROVED`, `scope=REPORTS`, `mutate=balances.consume_reserved`, `actor_type=ACTOR_EMPLOYEE`, `actor_id=actor.id`, `reason=REASON_APPROVED`.
    - `reject_leave_request(actor, request_id)` → `from=PENDING`, `to=REJECTED`, `scope=REPORTS`, `mutate=balances.release_reserved`, `actor_type=ACTOR_EMPLOYEE`, `actor_id=actor.id`, `reason=REASON_REJECTED`.
    - `cancel_leave_request(actor, request_id)` → `from=PENDING`, `to=CANCELLED`, `scope=SELF`, `mutate=balances.release_reserved`, `actor_type=ACTOR_EMPLOYEE`, `actor_id=actor.id`, `reason=REASON_CANCELLED`.
  - [x] Add the two reads:
    - `get_leave_request(actor, request_id) -> <view>` — resolve scope from role (`ALL` for Admin, `REPORTS` for Manager, `SELF` otherwise — the [balance_reads.py:99](backend/app/services/balance_reads.py#L99) idiom, extended to three-way), open a **read** session (no commit), `get_leave_request(session, actor, request_id, scope)`, `None` ⇒ `authz.not_found()`, else project a frozen view carrying `id`, `leave_type_id`, `start_date`, `end_date`, `leave_days` (**stored**, AD-18), `status` (and the Leave Type code/name if the response includes them — Open Decision #2).
    - `list_leave_requests(actor, *, status, limit, offset) -> tuple[list[<view>], int]` — same three-way scope resolution, read session, `list_leave_requests(session, ...)`, map rows → frozen views, return `(views, total)`.
  - [x] Reuse the existing `_now()` shell clock ([leave_requests.py:146](backend/app/services/leave_requests.py#L146)) for `occurred_at`. The clock lives in the shell (AD-1) — `domain/` never reads it.

- [x] **Task 5 — Routes: the three transitions + the two reads (AC1–AC7, AC9)**
  - [x] **Extend** [backend/app/api/v1/leave_requests.py](backend/app/api/v1/leave_requests.py) (the router is already `include_router`-ed — no router edit). Import `require_role` and `authz` for the role gate; import `PageParams`/`Page` from [pagination.py](backend/app/api/v1/pagination.py) for the list.
  - [x] **`POST /leave-requests/{request_id}/approve`** and **`.../reject`** — guard `Depends(require_role(authz.ROLE_MANAGER))` so an Admin (or Employee) is refused `403 ACTION_NOT_PERMITTED` **before the body runs** (AC6 — a role denial by G3, decided before any row is read). `status_code=200`. Call the matching service command; the domain-error handler maps `TRANSITION_NOT_ALLOWED`→409 and `RESOURCE_NOT_FOUND`→404. Project the returned view (or return `204`/the updated row — Open Decision #2).
  - [x] **`POST /leave-requests/{request_id}/cancel`** — guard `Depends(get_current_employee)` (role **any**; scope `self` is intrinsic to the applicant). `status_code=200`. A non-owner's request is out of scope → `404`; a settled request → `409`.
  - [x] **`GET /leave-requests`** — guard `Depends(get_current_employee)` (role **any**). Accept `params: PageParams = Depends()` **and** an optional `status: <StatusEnum> | None = None` query param. Validate `status` against the four allowed values — **reuse the `vocabulary.STATUS_*` constants indirectly** (via `authz` re-export or a small `api/`-side literal-free enum); a bad value is a framework 422, not a domain error. Call `leave_requests_service.list_leave_requests(...)`, return `Page[LeaveRequestResponse](items=..., page=params.page, page_size=params.page_size, total=total)`.
  - [x] **`GET /leave-requests/{request_id}`** — guard `Depends(get_current_employee)`. Call `leave_requests_service.get_leave_request(...)`; project the view by hand (`api/` imports neither the ORM nor the service dataclass — the `balances.py` precedent). `leave_days` is read from the stored value (AD-18).
  - [x] Define the response model(s) — `LeaveRequestResponse` (`id`, `employee_id?`, `leave_type_id`, `start_date`, `end_date`, `leave_days`, `status`; add Leave Type `code`/`name` per Open Decision #2). Project by hand via `_to_...` helpers typed `object`, no `from_attributes`.
  - [x] **`status` filter param name is `status`** (api-contracts §1 "Filters compose"). Only `status` is added here; `leave_type_id`/`date_from`/`date_to` are **Story 3.1's** (`FR-12`) — do **not** add them.

- [x] **Task 6 — Register the four identifier endpoints in the SM-3 matrix (AC7, AC10)**
  - [x] In [backend/tests/test_scope_matrix.py](backend/tests/test_scope_matrix.py) `_SCOPE_REGISTRY` (line 73) add — matching the exact FastAPI path templates (the path param name you choose, e.g. `{request_id}`):
    - `("GET", "/api/v1/leave-requests/{request_id}"): frozenset({Scope.SELF, Scope.REPORTS, Scope.ALL})`
    - `("POST", "/api/v1/leave-requests/{request_id}/approve"): frozenset({Scope.REPORTS})`
    - `("POST", "/api/v1/leave-requests/{request_id}/reject"): frozenset({Scope.REPORTS})`
    - `("POST", "/api/v1/leave-requests/{request_id}/cancel"): frozenset({Scope.SELF})`
  - [x] `GET /leave-requests` and `POST /leave-requests/preview`/`POST /leave-requests` carry **no path parameter** → out of the matrix (the completeness gate ignores them). Confirm the parametrized `test_every_identifier_endpoint_is_registered` and `test_no_registered_entry_names_a_route_the_app_does_not_expose` both pass — the path templates must be byte-exact.

- [x] **Task 7 — REVISE the 2.6 append-only surface test — do NOT let it false-block (AC1, AC2)**
  - [x] [backend/tests/integration/test_leave_request_submit.py](backend/tests/integration/test_leave_request_submit.py) `test_audit_and_request_repositories_expose_no_update_or_delete` ([line 515](backend/tests/integration/test_leave_request_submit.py#L515)) asserts the `leave_request` repo surface is **exactly** `{"insert_leave_request", "count_pending_for_employee"}`. This story legitimately adds `get_leave_request`, `list_leave_requests` and `transition_status`. **Update the expected `leave_request` set** to include them. **Keep the `audit_entry` clause unchanged** (`{"insert_audit_entry"}` — audit is *strictly* append-only, forever). Reframe the assertion/docstring: `leave_request` exposes reads + the **single AD-4 guarded conditional transition**, never a free-form update or delete. Consider moving this now-cross-story test into a 2.7 test file, or leave it in place and note the 2.7 revision — either is fine; do not delete it.

- [x] **Task 8 — Frontend: the Manager queue (AC9)**
  - [x] Extend [frontend/src/api/leaveRequests.ts](frontend/src/api/leaveRequests.ts): add typed hooks on `apiFetch` (mirror `useLeaveTypes`/`useSubmitLeaveRequest`):
    - `useLeaveRequests(status?: string)` — `useQuery` on `GET /leave-requests?status=...`, returning `Page<LeaveRequest>`. Reuse the `Page<T>` type from [departments.ts](frontend/src/api/departments.ts) (its single home). Add a `LEAVE_REQUESTS_QUERY_KEY` that includes the `status` so a filtered query caches distinctly.
    - `useApproveLeaveRequest()` / `useRejectLeaveRequest()` / `useCancelLeaveRequest()` — `useMutation` POSTing to the `/approve|/reject|/cancel` endpoint; `onSuccess` invalidate `LEAVE_REQUESTS_QUERY_KEY` **and** `BALANCES_QUERY_KEY` (a decision moves the applicant's reserved/consumed — the Manager's own balance is unaffected, but invalidating is cheap and correct; the applicant's balance is what changed server-side).
    - Export via the barrel [frontend/src/api/index.ts](frontend/src/api/index.ts).
  - [x] New feature under [frontend/src/features/leave/](frontend/src/features/leave/) — a `ManagerQueuePanel.tsx` (mirror `RequestPreviewPanel.tsx` structure + the `EmployeesPage` role-gate idiom): render **only for a Manager** (`useMe().data?.role === 'MANAGER'`, the `EmployeesPage` `ADMIN_ROLE` gate pattern — the client hides it, the server's 403 is the real guard). List the caller's Direct Reports' `PENDING` requests (`useLeaveRequests('PENDING')`), each row showing the request's dates, `leave_days` and status, with **Approve** and **Reject** buttons wired to the mutations. Render a `409 TRANSITION_NOT_ALLOWED` (the request was cancelled/decided under them) as an inline message and refetch, so the queue self-heals. **No client day count** — render the server's `leave_days` as-is (`test_frontend_no_client_day_count.py` line-scans for `getDay`/`getUTCDay`; never emit those tokens, not even in a comment — Story 2.5 tripped this).
  - [x] Mount `ManagerQueuePanel` in `AppShell` in [frontend/src/App.tsx](frontend/src/App.tsx) beside `RequestPreviewPanel` (line 83). Add any new CSS classes to [frontend/src/index.css](frontend/src/index.css) reusing the existing panel/table styles.

- [x] **Task 9 — Domain unit tests, DB-free (AC2)**
  - [x] The transition logic is thin orchestration; the only genuinely pure surface is the role→scope mapping if you extract it to a helper. If you add a pure `_scope_for_role(role) -> Scope` (Admin→ALL, Manager→REPORTS, else SELF), unit-test it DB-free in [backend/tests/domain/](backend/tests/domain/) or a service-level test with a fake actor. Otherwise the correctness lives in the integration suite (Task 10) — note that honestly, do not fabricate a domain test with no pure logic to cover.

- [x] **Task 10 — Integration tests, real PostgreSQL (AC1–AC8, AC10)**
  - [x] New [backend/tests/integration/test_leave_request_decide.py](backend/tests/integration/test_leave_request_decide.py). Reuse the `_World` fixture shape from [test_leave_request_submit.py](backend/tests/integration/test_leave_request_submit.py) — Department + Manager + a Direct Report + LeaveType + materialized balances + tokens via `security.create_token` + `TestClient(app)`. Cover:
    - **AC1 approve:** a Manager approves a report's PENDING request → `200`, status `APPROVED`, balance moves `reserved → consumed` by exactly `leave_days`, `available` unchanged; exactly **one** new `audit_entry` (`from=PENDING`, `to=APPROVED`, `actor_type=EMPLOYEE`, `actor_id=<manager>`, `reason`).
    - **AC1 reject:** → `200`, status `REJECTED`, `release_reserved` (reserved down, available up), one audit row (`to=REJECTED`).
    - **AC2 guarded transition:** approving an already-`CANCELLED`/`APPROVED` request → `409 TRANSITION_NOT_ALLOWED`, **no** balance change, **no** new audit row (the transaction rolled back). Assert the balance is byte-unchanged and the audit count is unchanged.
    - **AC3 cancel:** the applicant cancels their own PENDING request → `200`, `CANCELLED`, reservation released, one audit row (`actor_type=EMPLOYEE`, `actor_id=<applicant>`, `to=CANCELLED`). A **non-owner** cancelling → `404`. Cancelling a **settled** request → `409`.
    - **AC6 Admin:** an Admin calling approve/reject → `403 ACTION_NOT_PERMITTED` (role denial). Assert the body is the standard envelope with that code.
    - **AC7 non-report Manager (SM-3 satisfaction):** a *different* Manager (not the applicant's) calling `GET /leave-requests/<id>`, `approve`, `reject`, and a non-owner Employee calling `cancel` → **all `404`**, and the response body is **byte-identical** to the `404` for a random nonexistent UUID. This is the AC10/SM-3 correctness proof — assert byte-equality of the two 404 bodies.
    - **AC4 list scoping:** an Employee's `GET /leave-requests` returns only their own; a Manager's returns only their reports' (not their own, not other teams'); an Admin's returns all — assert the scope is a predicate (a report of *another* Manager never appears). Assert the `items`/`page`/`page_size`/`total` envelope, the `status` filter narrows correctly, and `page_size` is clamped to `MAX_PAGE_SIZE` (100).
    - **AC5 by-id read:** returns the stored `leave_days` (freeze it, mutate nothing, confirm the read value equals the admitted count); an out-of-scope id → `404`.
    - **AC8 reassignment:** submit a PENDING request under Manager A, reassign the applicant to Manager B (`PATCH /employees/<id>` manager change), then Manager B approves successfully and Manager A now gets `404` — authority is evaluated at decision time (`DR-12`).
    - **SM-4 one-to-one:** after a sequence of transitions, assert the count of `audit_entry` rows equals the count of state transitions performed (submission + each decision), one-to-one.

- [x] **Task 11 — Full gate pass**
  - [x] `cd backend && pytest` — all pass (baseline **332** after Story 2.6; expect the count to rise). Fix every armed guard this story touches: `test_scope_matrix.py` (four new registrations), `test_scoped_getters.py` (the two new `get_`/`list_` reads must take `actor` — they do), `test_leave_request_submit.py` (the revised surface test), `test_vocabulary_literals.py`, `test_architecture.py` (import-linter, 7 contracts).
  - [x] `cd frontend && npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean.
  - [x] Record a manual click-through (Manager approves/rejects from the queue → row leaves the queue, applicant balance updates) in the Dev Agent Record — honestly note if no live server was driven.

---

## Dev Notes

### The one-paragraph mental model
Story 2.6 turned a date range into a `PENDING` `leave_request` row + a `reserve` + one `audit_entry`,
atomically. **2.7 is the transitions off that row.** Each decision is *one transaction* that (1) locates
the target **under the actor's scope** (a miss is a byte-identical 404), (2) performs the **AD-4 guarded
`UPDATE ... WHERE status = :from`** (a lost race is a clean 409, the whole transaction rolls back), (3)
moves the balance via the AD-17 mutator the transition implies (`consume_reserved` on approve,
`release_reserved` on reject/cancel), and (4) writes **exactly one** `audit_entry` naming the actor.
Plus the two scoped reads a Manager needs to *see* the queue. **No schema. No migration. No new table.**
Everything it composes already exists.

### Reuse map — DO NOT reinvent these
| Need | Reuse (exact) | Source |
|---|---|---|
| Approve: reserved→consumed | `balances.consume_reserved(session, *, employee_id, leave_type_id, leave_year, days)` — locks the row, guards `days ≤ reserved` | [services/balances.py:123](backend/app/services/balances.py#L123) |
| Reject/cancel: release the reservation | `balances.release_reserved(session, *, employee_id, leave_type_id, leave_year, days)` | [services/balances.py:176](backend/app/services/balances.py#L176) |
| Scope predicate (SELF/REPORTS/ALL) | `employee_scope_predicate(scope, actor)` — composes into `select().where()`, never a post-filter | [repositories/scoping.py](backend/app/repositories/scoping.py) |
| Role→scope resolution | `Scope.ALL if actor.role == authz.ROLE_ADMIN else Scope.REPORTS` — **extend to three-way** (else `SELF`) | [services/balance_reads.py:99](backend/app/services/balance_reads.py#L99) |
| Scoped single-row read shape | `employee_repo.get_employee(session, actor, id, scope)` — `None` for nonexistent-OR-out-of-scope | [repositories/employee.py:127](backend/app/repositories/employee.py#L127) |
| Scoped paged list shape | `employee_repo.list_employees(session, actor, limit, offset)` → `(rows, total)` | [repositories/employee.py:94](backend/app/repositories/employee.py#L94) |
| 404 raise (byte-identical) | `authz.not_found()` — one message, empty `details`, no interpolation | [services/authorization.py](backend/app/services/authorization.py) |
| 403 role gate | `require_role(authz.ROLE_MANAGER)` → `authz.assert_role` raises `ACTION_NOT_PERMITTED` before the body | [api/v1/dependencies.py](backend/app/api/v1/dependencies.py) |
| Audit row (append-only) | `audit_entry_repo.insert_audit_entry(session, *, subject_type, subject_id, from_state, to_state, actor_type, actor_id, reason, occurred_at)` | [repositories/audit_entry.py:28](backend/app/repositories/audit_entry.py#L28) |
| Pagination bound + envelope | `PageParams` (clamps to `MAX_PAGE_SIZE=100`) + `Page[T]` | [api/v1/pagination.py](backend/app/api/v1/pagination.py) |
| Typed-refusal factory idiom | `_invalid_date_range()` (one `_MESSAGE` const + factory, `details` names numbers) | [services/leave_requests.py:100](backend/app/services/leave_requests.py#L100) |
| Frontend role gate + query hook | `EmployeesPage` `ADMIN_ROLE`/`useMe` gate; `useLeaveTypes` `useQuery` on `Page<T>` | [features/employees/EmployeesPage.tsx](frontend/src/features/employees/EmployeesPage.tsx), [api/leaveTypes.ts](frontend/src/api/leaveTypes.ts) |

### Non-negotiable invariants (a violation is a review reject)
- **AD-4 — the transition IS the guarded conditional UPDATE.** Never read `status` then write it. It is
  a single `UPDATE ... SET status = :to WHERE id = :id AND status = :from`; `rowcount == 0` ⇒ raise
  `TRANSITION_NOT_ALLOWED` (409) and let the transaction roll back. This is FR-09's first-committed-wins.
  The `:from`/`:to` are `STATUS_*` constants (AD-21) — a bare `"PENDING"` literal is both a
  `test_vocabulary_literals` failure and a latent zero-row bug.
- **AD-8 — audit is append-only and same-transaction.** Exactly **one** `audit_entry` per transition,
  inserted in the *same* transaction; a rolled-back transition (a lost race, or a failed balance mutate)
  leaves **no** audit row and **no** status change. `audit_entry` never gains an update/delete method —
  ever. `leave_request` gains only the AD-4 *guarded conditional* transition (Task 7 reframes the 2.6
  surface test around exactly this distinction).
- **AD-10 — authorization is a query predicate; absence is 404; 403 is "may see, may not act".** Every
  read and every transition locates its target with `employee_scope_predicate` in the SQL. A scope miss
  is `authz.not_found()` — byte-identical to a nonexistent id (AC7). `403 ACTION_NOT_PERMITTED` is
  reserved for the **role** denial (an Admin deciding, AC6), decided by the `require_role` gate *before
  any row is read* (G3). Never post-filter rows in Python.
- **AD-17 — one balance writer, eight methods.** Only `services/balances.py` writes a balance column.
  Approve uses `consume_reserved`; reject/cancel use `release_reserved`. Do **not** add a ninth method
  (`test_balances_module_surface.py`) and do **not** touch `reserved`/`consumed` anywhere else.
- **AD-18 — `leave_days` is frozen.** The reads return the **stored** `leave_days`; no read path
  recomputes it. The transitions do not touch `leave_days` at all (only `status` and the balance).
- **AD-1 layering.** `api → services → {repositories, domain}`; `api/` imports neither `repositories/`
  nor `domain/` (role constants come via `authz`, the ORM/service dataclasses are duck-typed `object`);
  `domain/` is pure; statuses wired in `main.py`. import-linter's 7 contracts stay green
  (`test_architecture.py`).
- **DR-12 — authority at decision time.** The `REPORTS` predicate binds `Employee.manager_id ==
  :actor_id` at request time. A reassigned applicant is decided by their *new* Manager; the old one now
  gets a 404 (AC8). Never cache or store the reporting edge at submission.
- **AD-21 / DR-10.** Every enumerated string is a `vocabulary.py` constant; `leave_days` and balance
  quantities are `INTEGER`.

### The lock order — READ THIS (it differs from Story 2.6 on purpose)
Story 2.6's submission locks the **balance row first** (`reserve`), then **inserts** the request row —
AD-3's "balance before request". **The transitions here invert that: guarded `UPDATE` (request row)
first, then the balance mutation.** This is deliberate and safe:

1. **Correctness demands it.** If a transition mutated the balance *first* and then found the guarded
   `UPDATE` matched zero rows (a concurrent cancel already released the reservation and set
   `CANCELLED`), `consume_reserved` would find `days > reserved` and raise `ValueError` → a raw **500**,
   not the clean **409** AC2 requires. Doing the guarded `UPDATE` first means a lost race is caught as
   `TRANSITION_NOT_ALLOWED` **before** any balance is touched.
2. **It cannot deadlock.** A deadlock needs two transactions locking the same two rows in opposite
   orders. The *submission* never locks an **existing** request row (it `INSERT`s a new one), so it
   never contends with a transition over a request row. All *transitions* agree on the same order
   (request row, then balance row), so they queue behind each other on the request row's lock — the
   loser's guarded `UPDATE` simply matches zero rows. No cycle exists.

So: **`get_leave_request` (plain SELECT, no lock) to authorize → `transition_status` (the guarded
UPDATE, which locks the request row) → check rowcount → balance mutate → audit insert → commit.** One
transaction, opened and committed in `services/`.

### Scope, role, and the 403-vs-404 split (get this exactly right — it is half the story)
| Endpoint | Role gate (`api/`) | Scope (service) | Denials |
|---|---|---|---|
| `POST .../{id}/approve` | `require_role(ROLE_MANAGER)` | `REPORTS` | Admin/Employee role → **403**; non-report → **404**; not PENDING → **409** |
| `POST .../{id}/reject` | `require_role(ROLE_MANAGER)` | `REPORTS` | same as approve |
| `POST .../{id}/cancel` | `get_current_employee` (any) | `SELF` | non-owner → **404**; not PENDING → **409** |
| `GET /leave-requests` | `get_current_employee` (any) | role→scope: Emp `SELF` / Mgr `REPORTS` / Admin `ALL` | — (a filtered empty list, never 404) |
| `GET .../{id}` | `get_current_employee` (any) | role→scope (as above) | out-of-scope id → **404** |

Two things people get wrong here:
- **Approve/reject are `require_role(ROLE_MANAGER)`, not "any".** That is what makes an **Admin** a
  clean `403` (AC6, DR-13 — "read every request, decide none") *before* any row is read (G3). An
  Employee hitting approve is also `403` by the same gate. Only a `MANAGER` role passes; the `REPORTS`
  scope then decides whether *this* manager owns *this* applicant (404 if not).
- **A Manager's `GET /leave-requests` scope is `REPORTS` — their Direct Reports' requests, not their
  own.** The AC says "a Manager receives their Direct Reports'". A Manager who is *also* an applicant
  sees their own submitted requests as an *Employee* would only via the... they do not, under this AC —
  `REPORTS` is `Employee.manager_id == actor.id`, which excludes the Manager's own row. Implement the AC
  literally: three-way role→scope, `REPORTS` for a Manager. (If product later wants "my team **and**
  me", that is a filter change in a later story, not this one.)

### SM-3 is *satisfied* here, not just registered (AC7, AC10)
Story 1.7 built `test_scope_matrix.py` as a **completeness harness** — it fails the build if any
identifier endpoint lacks a registered scope, but it could not yet *satisfy* SM-3 because no Leave
Request table existed. This story is where SM-3 becomes true: register the four identifier endpoints
(Task 6), **and** prove in integration (Task 10, AC7) that a non-report Manager and a non-owner Employee
get a `404` **byte-identical** to a nonexistent UUID. Assert the byte-equality explicitly — that is the
DR-12/FR-03 guarantee the whole scope machinery exists for. `GET /leave-requests` (collection, no path
param) is correctly *out* of the matrix.

### No migration, no model change — confirm this and move on
The `leave_request` and `audit_entry` tables, all columns, CHECKs and the two indexes already ship from
`0006_leave_request` (Story 2.6). This story adds **behavior and endpoints only**. Do **not** author a
`0007` migration, do **not** touch `models.py`, and do **not** edit the schema/migration guard tests
(`test_schema_1_2.py`, `test_migrations_insert_nothing.py`, `test_migration_smoke.py`) — they are
already green for these tables and must stay untouched. The `ix_leave_request_employee_status` index
([models.py](backend/app/repositories/models.py)) already covers the `(employee_id, status)` access path
`GET /leave-requests?status=PENDING` walks.

### Open Decision #1 — the three transition `reason` constants (AC1)
`audit_entry.reason` is `NOT NULL` (2.6). api-contracts §3 names only `AUTO_APPROVED_NO_MANAGER`; the
spine/ERD name no reason string for a manual approve/reject/cancel. Options: (a) coin
`REASON_APPROVED`/`REASON_REJECTED`/`REASON_CANCELLED` (values `"APPROVED"`/`"REJECTED"`/`"CANCELLED"`),
symmetric with `REASON_SUBMITTED`; (b) coin descriptive forms (`MANAGER_APPROVED`, `MANAGER_REJECTED`,
`APPLICANT_CANCELLED`) that don't duplicate the status values. **Recommendation: (a)** — concise,
symmetric with the existing pattern; the `from_state`/`to_state` already carry the *what*, `reason`
carries a stable label. Declare each once (AD-21), add to `__all__`. Pick one, keep it consistent
across the three commands and their tests.

### Open Decision #2 — the read/response shape (AC1, AC5, AC9)
api-contracts §5 defers per-endpoint body schemas to the generated OpenAPI, so you have latitude. Decide
and keep consistent: (1) do the transition endpoints return `200` **with the updated request** or `200`
with a minimal `{id, status}` (a queue refetch reloads the row either way)? Recommendation: return the
updated row for symmetry with submit's `SubmitResponse`. (2) Does `LeaveRequestResponse` carry the Leave
Type **`code`/`name`** (a join in the list/read) or just `leave_type_id`? AC5 says "returned with its
Leave Type" — recommendation: include `code`/`name` via a `joinedload(LeaveRequest.leave_type)` in the
repo (the `list_employees`/`joinedload(department)` precedent), so the Manager queue and the by-id read
are human-readable without a second round-trip. (3) Does the list/read include `employee_id` (and the
applicant's name) so a Manager can tell whose request it is? For the Manager queue (AC9) it must show
*who* — recommendation: include `employee_id` and eager-load the applicant's `full_name`. Whatever you
choose, project **by hand** in `api/` (no `from_attributes`, no ORM import) and mirror it in the
frontend `LeaveRequest` interface.

### The transitions never touch `leave_days` or dates
A decision changes **`status`** (the guarded UPDATE) and the **balance** (the AD-17 mutator) — nothing
else. `leave_days`, `start_date`, `end_date`, `leave_type_id`, `employee_id` are immutable on the row
(AD-18 for `leave_days`). If you find yourself writing any of them in a transition, stop — that is a
different story (2.11 recalculation is the *only* path that may change `leave_days`, and only for
Pending/future-Approved requests).

### Testing standards (this codebase)
- `pytest` **is** the build — no CI; guards run in-suite. Baseline **332** (post-2.6).
- **DB-free domain tests** → [backend/tests/domain/](backend/tests/domain/) (no `db_connection`, stdlib
  + pure fn + `vocabulary`). **Integration tests** → [backend/tests/integration/](backend/tests/integration/)
  against real PostgreSQL (`conftest.py` skips loudly if unreachable); `import app.main` wires
  `CODE_TO_STATUS`.
- **Assert the negatives:** a lost-race transition leaves the balance byte-unchanged and adds no audit
  row; two 404 bodies (out-of-scope and nonexistent) are byte-identical; SM-4's audit count equals the
  transition count one-to-one; an out-of-scope row never appears in a list.
- Frontend has no test runner — proof is `npm run build` + `npm run lint` clean, plus a declared manual
  click-through. **No `getDay`/`getUTCDay` under `frontend/src`**, not even in a comment
  (`test_frontend_no_client_day_count.py`).

### Project Structure Notes
- **Extend, do not create parallel files:** `services/leave_requests.py`, `api/v1/leave_requests.py`,
  `repositories/leave_request.py`, `frontend/src/api/leaveRequests.ts` all already exist and are named
  to be extended here. The router is already `include_router`-ed — new routes need no router edit.
- **New files:** `tests/integration/test_leave_request_decide.py`, `frontend/src/features/leave/ManagerQueuePanel.tsx`
  (and possibly a small `tests/domain/` test if you extract a pure role→scope helper).
- **No new migration, no model edit.**
- **Naming:** service/router files plural (`leave_requests`); domain/repo fns `verb_noun`
  (`transition_status`, `get_leave_request`, `list_leave_requests`, `approve_leave_request`).
- **Commit:** `feat(story-2.7): <summary>`, matching the `feat(story-2.6): …` git-log convention; one
  commit after review → done.

### Cross-story context (Epic 2 sequencing)
- **Story 3.1** *extends* `GET /leave-requests` and `GET /leave-requests/<id>` with `FR-12`'s composable
  filters (`leave_type_id`, `date_from`, `date_to`) and `FR-20`'s cross-Leave-Year history. This story
  delivers **only** the `FR-03`-scoped reads with the **`status`** filter — do not add the other filter
  params (epics.md line 1417, line 1431).
- **Story 2.8** adds approved-leave cancellation via a *separate* `cancellation_request` table and
  `POST /cancellation-requests/<id>/approve` (Admin), using `release_consumed`. Do **not** conflate it
  with this story's `cancel` (which is the **applicant** cancelling their own **Pending** request via
  `release_reserved`). 2.8 also reuses this story's AD-4 guarded-transition pattern.
- **Story 2.9** (the audit trail read) adds `GET /audit-entries` (Admin-only) and the `SM-4` one-to-one
  count test across *all* transitions. This story must keep audit strictly one-row-per-transition so
  2.9's count holds.
- **Inherited, accepted limitations (do not "fix" here):** (1) a deactivated Employee holding a live
  token can still act until it expires (`get_current_employee` does not re-check `is_active` — AD-14,
  deferred in 2.6); (2) the concurrent-create materialization race (a `reserve`/`consume_reserved`
  against an unmaterialized balance → `LookupError` → 500). Awareness only; both are in
  [deferred-work.md](_bmad-output/implementation-artifacts/deferred-work.md).

### References
- [Source: epics.md#Story 2.7] (lines 1091–1144) — acceptance criteria, verbatim; the "these two read
  endpoints land here" rationale; the 404-not-403 settlement (`G3`).
- [Source: ARCHITECTURE-SPINE.md] — AD-4 (guarded conditional update), AD-8 (audit append-only,
  same-transaction), AD-10 (predicate authorization, absence-is-404), AD-17 (`consume_reserved`/
  `release_reserved`), AD-18 (frozen `leave_days`), AD-21 (vocabulary), DR-12 (authority at decision
  time), DR-13 (Admin reads, decides none); the AD-1 layering and the state-mutation conventions.
- [Source: api-contracts.md §1, §2] — the `{code, message, details}` envelope; `TRANSITION_NOT_ALLOWED`
  → 409; `ACTION_NOT_PERMITTED` → 403; the 403-vs-404 status semantics and the G3 settlement; the
  pagination envelope (`items`/`page`/`page_size`/`total`, clamp-not-reject) and the `status` filter.
  §4.5 — the five endpoints, their roles (`Manager` for approve/reject, `any` for cancel/reads) and
  scopes (`reports`, `self`, `self/reports/all`).
- [Source: 2-6-…submit.md] — the tables, vocabulary and command this story transitions; the code-layer
  append-only decision (AD-9); the `_World` integration fixture; the lock-order precedent (submission is
  balance-first — this story inverts it for transitions, and why that is safe).
- [Source: 2-4-…balances.md] — the 8-method AD-17 module; `consume_reserved`/`release_reserved`
  semantics and their `days ≤ reserved` guards.
- [Source: 1-7-…scope-authority.md / test_scope_matrix.py] — the SM-3 harness this story *satisfies*;
  the registry shape and the byte-identical-404 requirement.
- [Source: balance_reads.py] — the role→scope resolution idiom (`ALL` for Admin, else `REPORTS`) this
  story extends to three-way (`SELF` for a plain Employee).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context)

### Debug Log References

- Full backend suite: **357 passed** (baseline 334 post-2.6 → +23 this story). `import-linter`
  7/7 contracts kept; `test_scope_matrix.py`, `test_scoped_getters.py`, `test_vocabulary_literals.py`,
  the revised `test_leave_request_submit.py` surface test, and `test_frontend_no_client_day_count.py`
  all green.
- Frontend `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) both clean.
- One self-inflicted failure caught and fixed mid-run: the first draft of `ManagerQueuePanel.tsx`
  named the forbidden `getDay`/`getUTCDay` tokens *in a comment*, tripping
  `test_frontend_no_client_day_count.py` (the exact trap the Dev Notes flagged from Story 2.5). The
  comment was reworded to describe the primitives without naming them; guard re-green.

### Completion Notes List

**Decisions taken (from the Dev Notes' open decisions):**
- **Open Decision #1 — transition reasons:** chose option (a), the symmetric
  `REASON_APPROVED`/`REASON_REJECTED`/`REASON_CANCELLED` (values `"APPROVED"`/`"REJECTED"`/
  `"CANCELLED"`), matching the existing `REASON_SUBMITTED` idiom. Declared once in `vocabulary.py`
  (AD-21), added to `__all__`.
- **Open Decision #2 — response shape:** transitions return the **updated request** (full
  `LeaveRequestResponse`, symmetric with submit); the response carries the Leave Type
  `code`/`name` and the applicant `employee_id`/`employee_name` (one join to `employee` serves both
  the scope predicate and the applicant name; one join to `leave_type` the labels). Mirrored in the
  frontend `LeaveRequest` interface.
- **`status` filter (Task 5):** implemented as a literal-free FastAPI query-param enum built at
  runtime from `leave_requests_service.LEAVE_STATUS_VALUES` (a new `api → services` re-export), so no
  status literal appears in `api/` (vocabulary guard) and `api/` never imports `domain/` (contract 2).
  A bad value is a framework **422**, consistent with the existing span-cap 422. Wire param name is
  `status` via `Query(alias="status")` (the Python name stays `status_filter` to avoid shadowing
  `fastapi.status`).
- **Manager's own requests in `GET /leave-requests` (Open Question #4):** implemented as `REPORTS`
  (Direct Reports' only), per the AC's literal wording — a Manager does not see their own submitted
  requests through this list. Left as a later filter change if product wants "my team **and** me".

**Correctness invariants honoured:**
- **AD-4** — every transition is the single guarded conditional `UPDATE … WHERE status = :from`
  (`repositories/leave_request.transition_status`); `rowcount == 0` → `409 TRANSITION_NOT_ALLOWED`
  and the whole transaction rolls back.
- **Lock order** — guarded UPDATE runs **before** the balance mutation (the inverse of 2.6's
  balance-first submit), so a lost race is a clean 409 before any balance is touched; proven by the
  AC2 test asserting the balance byte-unchanged and no audit row on a 409.
- **AD-8** — exactly one `audit_entry` per transition, same transaction; `audit_entry` stays
  strictly INSERT-only. The 2.6 append-only surface test was **revised** (not deleted) to admit the
  new reads + the one guarded transition on `leave_request` while keeping the `audit_entry` clause
  `{insert_audit_entry}` and still forbidding any free-form update/delete of a request row.
- **AD-10 / SM-3** — the four identifier endpoints are registered in `test_scope_matrix.py`, and the
  integration suite asserts a **byte-identical 404** (`response.content` equality) for a non-report
  Manager and a non-owner Employee vs. a nonexistent UUID — the first *satisfaction* of SM-3.
- **DR-12** — authority at decision time: the AC8 test reassigns the applicant to a new Manager and
  proves the new Manager decides successfully while the old one now gets a 404.
- **AD-18** — reads/transitions never recompute `leave_days`; the stored figure is returned.

**Manual click-through:** No live browser/server session was driven (honest note per Task 11). The
full request path is exercised end-to-end against **real PostgreSQL** through FastAPI's `TestClient`
in `test_leave_request_decide.py` (17 cases): approve/reject balance moves, the 409 guard, cancel
ownership, the Admin 403, the byte-identical 404s, list scoping/filter/clamp, the by-id frozen
`leave_days`, decision-time reassignment, and SM-4's one-to-one audit count. The frontend compiles
and lints clean; the queue's approve/reject/self-heal wiring is covered by type-checking and the
server behaviour it calls, not by a driven UI (the frontend has no test runner).

### File List

**Backend — modified:**
- `backend/app/domain/vocabulary.py` — added `TRANSITION_NOT_ALLOWED` (→409) and
  `REASON_APPROVED`/`REASON_REJECTED`/`REASON_CANCELLED`; extended `__all__`.
- `backend/app/main.py` — wired `TRANSITION_NOT_ALLOWED: 409` in `CODE_TO_STATUS`.
- `backend/app/repositories/leave_request.py` — added `get_leave_request` (scoped single-row read),
  `list_leave_requests` (scoped/paged/status-filtered), `transition_status` (the AD-4 guarded
  UPDATE); reframed the module docstring around the new mutation surface.
- `backend/app/services/leave_requests.py` — added `LeaveRequestView`, the `_transition_not_allowed`
  factory, `_scope_for_role`, `_row_to_view`, the `_decide` helper, `approve_leave_request`/
  `reject_leave_request`/`cancel_leave_request`, `get_leave_request`/`list_leave_requests`, and the
  `LEAVE_STATUS_VALUES` re-export.
- `backend/app/api/v1/leave_requests.py` — added the `LeaveStatusFilter` runtime enum,
  `LeaveRequestResponse` + `_to_leave_request_response`, and the five routes (approve/reject/cancel
  transitions, `GET /leave-requests`, `GET /leave-requests/{request_id}`).

**Backend — tests:**
- `backend/tests/test_scope_matrix.py` — registered the four Leave Request identifier endpoints.
- `backend/tests/integration/test_leave_request_submit.py` — revised the append-only surface test
  to admit the two reads + the guarded transition (audit clause unchanged).
- `backend/tests/domain/test_scope_for_role.py` — **new**; DB-free unit tests for `_scope_for_role`.
- `backend/tests/integration/test_leave_request_decide.py` — **new**; 17 real-PostgreSQL cases
  covering AC1–AC8, AC10/SM-3 and SM-4.

**Frontend — modified:**
- `frontend/src/api/leaveRequests.ts` — added the `LeaveRequest` type, `LEAVE_REQUESTS_QUERY_KEY`,
  `useLeaveRequests(status?, options?)`, and `useApproveLeaveRequest`/`useRejectLeaveRequest`/
  `useCancelLeaveRequest`.
- `frontend/src/api/index.ts` — exported the new hooks and `LeaveRequest` type.
- `frontend/src/App.tsx` — imported and mounted `ManagerQueuePanel` beside `RequestPreviewPanel`.

**Frontend — new:**
- `frontend/src/features/leave/ManagerQueuePanel.tsx` — the Manager decision queue (role-gated,
  approve/reject, 409 self-heal), reusing the existing `emp-*`/`panel` styles (no new CSS).

## Change Log

- 2026-07-13 — Story 2.7 context engineered (create-story). Transitions (approve/reject/cancel) as AD-4
  guarded conditional UPDATEs with 409 `TRANSITION_NOT_ALLOWED`; `consume_reserved`/`release_reserved`
  balance moves; one `audit_entry` per transition (AD-8); the two `FR-03`-scoped reads
  (`GET /leave-requests` + `/<id>`) with `status` filter and pagination; role gate makes an Admin a 403
  and a non-report Manager a byte-identical 404 (SM-3 satisfied, AD-10/G3); DR-12 decision-time
  authority; Manager queue frontend. No migration, no model change. Status backlog → ready-for-dev.
- 2026-07-13 — Story 2.7 implemented (dev-story). Vocabulary: `TRANSITION_NOT_ALLOWED` (409) +
  `REASON_APPROVED/REJECTED/CANCELLED`. Repo: `get_leave_request`/`list_leave_requests` scoped reads
  + `transition_status` (the one AD-4 guarded UPDATE). Service: `_decide` (guarded-UPDATE-then-balance
  lock order) driving approve/reject/cancel + the two scoped reads + `_scope_for_role`. Routes: five
  endpoints (approve/reject `require_role(MANAGER)`→403 for Admin; cancel/reads any-role); `status`
  filter as a runtime literal-free enum → framework 422. SM-3 registered + satisfied (byte-identical
  404 asserted on `response.content`). 2.6 append-only surface test revised, not deleted. Frontend:
  `ManagerQueuePanel` + list/approve/reject/cancel hooks. Backend pytest **357 passed** (+23),
  import-linter 7/7; frontend build + lint clean. Open Decisions #1(a) and #2(updated-row + labels +
  applicant) taken. Status ready-for-dev → in-progress → review.

## Open Questions (for the dev agent / reviewer)

1. **Transition `reason` constants (Open Decision #1).** `REASON_APPROVED/REJECTED/CANCELLED` (symmetric,
   values duplicate the status strings) vs. descriptive `MANAGER_APPROVED`/`APPLICANT_CANCELLED`. Pick
   one, declare once (AD-21), keep consistent across commands and tests. Recommendation: the symmetric
   form.
2. **Response shape (Open Decision #2).** (a) transitions return the updated row vs. minimal `{id,
   status}`; (b) include Leave Type `code`/`name` (a `joinedload`) per AC5's "with its Leave Type"; (c)
   include `employee_id` + applicant `full_name` so the Manager queue shows *whose* request it is.
   Recommendations noted inline — decide and mirror in the frontend `LeaveRequest` interface.
3. **The 2.6 append-only surface test (Task 7).** It must be *revised*, not deleted — `leave_request`
   legitimately gains reads + the guarded transition; `audit_entry` stays strictly INSERT-only. Confirm
   the reframing keeps a real guarantee (no free-form update/delete of a request row) rather than
   trivially widening to accept anything.
4. **Manager's own requests in `GET /leave-requests`.** Implemented as `REPORTS` (Direct Reports' only),
   per the AC's literal wording. Confirm product does not want "my team **and** my own" — if they do,
   it is a later filter change, not this story.

## Review Findings

> Code review 2026-07-13 (bmad-code-review, three parallel adversarial layers: Blind Hunter,
> Edge Case Hunter, Acceptance Auditor). 13 raw findings → 1 decision-needed, 4 patch, 3 defer,
> 5 dismissed. The transition/locking/audit core (AD-4 lock order, AD-8 one-audit-per-transition,
> AD-10 byte-identical 404, SM-3/SM-4) verified clean and well-tested.

- [x] [Review][Decision] **Manager cannot see or list their own leave requests** — `_scope_for_role` resolves a Manager to `REPORTS` only ([services/leave_requests.py:601](backend/app/services/leave_requests.py#L601)), whose predicate is `Employee.manager_id == actor.id` — which excludes the Manager's own row. **RESOLVED 2026-07-13: keep `REPORTS`-only as correct** (Open Question #4 answered — the AC's literal wording stands; a Manager's own requests are intentionally not returned by these reads, though they can still `cancel` via the explicit `SELF` scope). Follow-up: add a documenting test (see patch below).
- [x] [Review][Patch] Add a documenting test: a Manager's OWN submitted request is intentionally absent from `GET /leave-requests` and returns a byte-identical 404 from `GET /leave-requests/{id}` (locks in the Open-Question-#4 decision) [backend/tests/integration/test_leave_request_decide.py]
- [x] [Review][Patch] Failed (409/404) decisions never refetch — only `onSuccess` invalidates, yet the inline message falsely claims "the queue has been refreshed" (violates AC9/Task 8 self-heal) [frontend/src/api/leaveRequests.ts:170,181,191]
- [x] [Review][Patch] Stale/mis-attributed decision error persists on the wrong row after a different-row action settles (single shared mutation object, error state never reset) [frontend/src/features/leave/ManagerQueuePanel.tsx:61]
- [x] [Review][Patch] `useLeaveRequests` interpolates `status` into the URL without `encodeURIComponent` — safe only because callers pass the closed enum today; the public signature is `string` [frontend/src/api/leaveRequests.ts:145]
- [x] [Review][Patch] AC6 test proves only the Admin 403 on an existing id — not the Employee-role 403, nor the G3 "decided before any row is read" property (an Admin should get 403, not 404, on a nonexistent id) [backend/tests/integration/test_leave_request_decide.py]
- [x] [Review][Defer] `consume_reserved`/`release_reserved` `ValueError` → raw 500 if `reserved` is moved out of band below `leave_days` while the request stays PENDING (latent — needs an out-of-band reserved-adjust endpoint) [backend/app/services/leave_requests.py] — deferred, latent cross-story
- [x] [Review][Defer] The clean-409 (AD-4/AC2) guarantee silently depends on READ COMMITTED isolation; a future engine isolation change would turn a lost race into a 40001 → raw 500 [backend/app/repositories/leave_request.py] — deferred, pre-existing architectural assumption
- [x] [Review][Defer] Unbounded `page` overflows the SQL bigint `OFFSET` → raw 500 on `GET /leave-requests` (root cause in shared `pagination.py`, affects every list endpoint) [backend/app/api/v1/pagination.py] — deferred, pre-existing
