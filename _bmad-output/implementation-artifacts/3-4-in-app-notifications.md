---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

# Story 3.4: In-App Notifications

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Manager,
I want to learn that a decision is waiting for me, and as an applicant to learn that mine was made,
So that a request that reaches nobody stops being an email in a different costume.

## Acceptance Criteria

*(Verbatim from `epics.md:1513-1545`. FR-14 is owned by Epic 3 and by this story alone — readiness report `:435` (the coverage matrix) and `:954` (F-3's remediation, which assigns each shared FR to exactly one owning epic).)*

**AC1 — the schema**
**Given** a database migrated by this story
**When** the schema is inspected
**Then** `notification` carries `recipient_employee_id`, `leave_request_id`, a `kind` of `REQUEST_SUBMITTED`, `REQUEST_APPROVED` or `REQUEST_REJECTED`, a nullable `read_at`, and `created_at`
**And** a partial index exists on `recipient_employee_id WHERE read_at IS NULL` (`AD-16`, ERD §4.4)

**AC2 — the submission notification, in the submission's transaction**
**Given** an Employee with a Manager submitting a Leave Request
**When** the submission commits
**Then** exactly one Notification of kind `REQUEST_SUBMITTED` exists, addressed to that Manager
**And** it was written by the service performing the transition, inside that transition's transaction, so a rolled-back submission leaves none (`AD-16`, `FR-14`)

**AC3 — the decision notification**
**Given** a Leave Request approved or rejected
**When** the transition commits
**Then** exactly one Notification exists, addressed to the applicant, of kind `REQUEST_APPROVED` or `REQUEST_REJECTED` (`FR-14`)

**AC4 — the managerless applicant**
**Given** an applicant with no Manager whose request is auto-approved
**When** the notifications are counted
**Then** the applicant holds one `REQUEST_APPROVED` Notification, and no `REQUEST_SUBMITTED` Notification exists, because it would have no addressee (`FR-09`, `FR-14`)

**AC5 — the reads, addressee-scoped**
**Given** an authenticated Employee
**When** they call `GET /api/v1/notifications` or `GET /api/v1/notifications/unread-count`
**Then** they see only Notifications addressed to them
**And** the unread count is computed as `COUNT(*) WHERE read_at IS NULL` and is never stored (`AD-16`)

**AC6 — idempotent mark-read, addressee-only**
**Given** an addressee
**When** they call `PATCH /api/v1/notifications/<id>/read`, twice
**Then** the Notification is marked read and the unread count decrements once
**And** marking read is idempotent, and no Employee other than the addressee may do it (`FR-14`, `AD-16`)

**AC7 — the React application**
**Given** the React application
**When** an Employee is authenticated
**Then** an unread count is visible, and opening a Notification marks it read

---

## Tasks / Subtasks

> **Task order is deliberate.** Tasks 1–10 are the notification slice and are self-contained. **Task 11 is the AD-6 ruling** (Open Decision #1) — it touches the balance core, is independently revertable, and is done **LAST, only after 1–10 are green**. If Task 11 cannot be completed safely, declare it NOT DONE — do **not** ship the naive one-liner (Landmine 15).

- [x] **Task 1 — Migration `0012_notification` + the model (AC1)**
  - [x] Create `backend/alembic/versions/0012_notification.py`, `down_revision = "0011_policy_change"`. Copy `0011_policy_change.py` wholesale as the template: the `_OFFLINE_REFUSAL` guard in **both** `upgrade()` and `downgrade()`, the re-declared `_quoted_role()` helper (**re-declared, never imported** — revisions are standalone modules, not a package), `uuidv7()` server-default PK, `sa.Text()` + named `CheckConstraint` for the enumerated `kind`, `sa.DateTime(timezone=True)` for both instants.
  - [x] Columns: `id` (PK, `server_default=sa.text("uuidv7()")`), `recipient_employee_id` (Uuid, **NOT NULL**, FK → `employee.id`), `leave_request_id` (Uuid, **NOT NULL**, FK → `leave_request.id`), `kind` (Text, NOT NULL), `read_at` (`DateTime(timezone=True)`, **NULLABLE** — the only nullable column), `created_at` (`DateTime(timezone=True)`, NOT NULL).
  - [x] `CheckConstraint("kind IN ('REQUEST_SUBMITTED', 'REQUEST_APPROVED', 'REQUEST_REJECTED')", name="notification_kind_check")` — ERD §4.1 fixes `TEXT` + `CHECK`, **never a PostgreSQL `ENUM`** (`erd.md:338`).
  - [x] **No `ON DELETE` clause on either FK.** No binding artifact names one, and neither parent is ever deleted (AD-22: an Employee is never deleted, only deactivated; a Leave Request has no DELETE endpoint). `ON DELETE CASCADE` would signal a deletion path the product forbids.
  - [x] 🚨 **The partial index — the codebase's FIRST** (`grep postgresql_where` across `alembic/versions/` and `models.py` returns nothing today):
        `op.create_index("ix_notification_recipient_unread", "notification", ["recipient_employee_id"], postgresql_where=sa.text("read_at IS NULL"))`
  - [x] 🚨 **The GRANT — `notification` is the FIRST post-`0008` table that is NOT append-only. See Landmine 5.** Issue `GRANT SELECT, INSERT, UPDATE ON notification TO <app_role>` (via `sql.SQL(...).format(table=sql.Identifier("notification"), role=role)`). **NOT** `GRANT INSERT, SELECT` — that is the append-only shape `0009`/`0010`/`0011` all used, and copying it makes `PATCH …/read` fail at runtime with `InsufficientPrivilege`. **`DELETE` is deliberately omitted** (no requirement deletes a notification); state that in the migration docstring, and clean up tests through `owner_engine` (Landmine 6).
  - [x] Do **NOT** edit `0008`'s `_READ_WRITE_TABLES` tuple — it is historical, it already ran, and adding to it does nothing on an existing database while misleading the next reader.
  - [x] Add `class Notification(Base)` to `app/repositories/models.py`, **byte-faithful** to the migration: every constraint `name=` and the index name identical, `Index("ix_notification_recipient_unread", "recipient_employee_id", postgresql_where=text("read_at IS NULL"))` in `__table_args__`. `read_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)` — **`DateTime(timezone=True)` is mandatory and explicit**; a bare `Mapped[datetime]` maps to a naive `TIMESTAMP` and drops the offset (`models.py:382-383`).
  - [x] Grow the four schema registries by exactly one entry each (the 2.8 precedent): `tests/test_migrations_insert_nothing.py` (append `"0012_notification.py"` to the ordered chain), `tests/integration/test_migration_smoke.py` (`HEAD_REVISION = "0012_notification"`), `tests/integration/test_schema_1_2.py` (add `"notification"` to the expected-tables set), and `test_model_migration_agreement.py` needs no edit but must stay green (`alembic check` → empty diff).

- [x] **Task 2 — Vocabulary (AD-21)**
  - [x] Add to `app/domain/vocabulary.py`, beside a comment naming this story: `NOTIFICATION_REQUEST_SUBMITTED = "REQUEST_SUBMITTED"`, `NOTIFICATION_REQUEST_APPROVED = "REQUEST_APPROVED"`, `NOTIFICATION_REQUEST_REJECTED = "REQUEST_REJECTED"`. **Add all three to `__all__`** — a constant absent from `__all__` is not enforced by the guard.
  - [x] 🚫 **There is NO `SUBJECT_NOTIFICATION`, and there must not be one.** (Landmine 4.)
  - [x] 🚫 **No new error code.** `app/main.py`'s `CODE_TO_STATUS` is **UNTOUCHED** — every refusal this story can produce (`404 RESOURCE_NOT_FOUND`, `401 TOKEN_INVALID`) is already mapped. A notification `kind` is a stored value, not an error code — it maps to no HTTP status, exactly like `CAUSE_*` and `EXCLUSION_*`.
  - [x] 🚫 **No `Literal["REQUEST_SUBMITTED", …]` anywhere under `app/` or `seed/`.** The moment the three values land in `__all__`, `test_vocabulary_literals.py` makes that annotation *unwritable* (it AST-walks for `ast.Constant` string nodes equal to an exported value — docstrings are skipped, annotations are not). If the API needs a runtime enum, build it from a service re-export, the `LeaveStatusFilter` pattern at `app/api/v1/leave_requests.py:62-65`.

- [x] **Task 3 — `app/repositories/notification.py` (new module, AC2/AC3/AC5/AC6)**
  - [x] One repository module per table (the `policy_change.py` shape). 🚨 **Do NOT add functions to `repositories/leave_request.py` or `repositories/audit_entry.py`** — `test_leave_request_submit.py:519-619` hard-pins both surfaces by name (`{"insert_audit_entry", "list_audit_entries"}` and the 7 leave-request names); adding one fails the build. A new table getting a new module is legitimate, not an evasion.
  - [x] `insert_notification(session, *, recipient_employee_id, leave_request_id, kind, created_at) -> None` — `session.add(...)` + `session.flush()`, **never `commit()`** (the caller owns the transaction).
  - [x] `list_notifications(session, actor, limit, offset) -> tuple[list[Row], int]` — page + count in one round-trip, `_READ_COLUMNS` as plain columns (never the ORM entity — a `Row` is already detached, so nothing lazy-loads after the session closes).
  - [x] 🚨 **`ORDER BY created_at DESC, id DESC`.** The `id` tiebreak is load-bearing, not decoration: `created_at DESC` alone is not a **total** order, and Postgres may return tied rows in either order between two queries — a paginated read then shows one row twice and skips another. `id` is UUIDv7, time-ordered by construction. Stories 2.9 and 2.11 each found this the hard way (`repositories/policy_change.py:126-132`).
  - [x] `count_unread(session, actor) -> int` — `SELECT COUNT(*) WHERE recipient_employee_id = :actor AND read_at IS NULL`. **Never stored** (AD-16). The `count_` prefix is deliberate: `test_scoped_getters`'s `_READ_VERB_PREFIXES` are `get_/list_/find_/fetch_`, so `count_` sidesteps the matcher — the `count_pending_for_employee` precedent (`repositories/leave_request.py:31-38`). The scope predicate is still required, for correctness rather than to satisfy a guard.
  - [x] `get_notification(session, actor, notification_id) -> Row | None` — the single-row scoped getter Task 4 needs to tell "not yours" (404) from "already read" (200). Being a `get_`, it is caught by `test_scoped_getters`'s `_READ_VERB_PREFIXES` and **must take a param literally named `actor`**.
  - [x] `mark_read(session, *, notification_id, recipient_employee_id, read_at) -> int` — the guarded conditional UPDATE, returning `rowcount`:
        `UPDATE notification SET read_at = :now WHERE id = :id AND recipient_employee_id = :actor AND read_at IS NULL` with `.execution_options(synchronize_session=False)`. See Landmine 3 for how the service reads a `rowcount` of 0 — **it is NOT a 409.**
  - [x] 🚨 **Every `get_`/`list_` here takes a param literally named `actor`** and applies the scope **in the SQL**. `notification` has an owner column (`recipient_employee_id`) → it is **NOT exemptible**. **`tests/test_scoped_getters.py`'s `EXEMPT` frozenset must NOT change — that is the tell you did it right.**
  - [x] The scope predicate is the direct column compare `Notification.recipient_employee_id == actor.id`, **not** `employee_scope_predicate(Scope.SELF, actor)` — that helper predicates over the `Employee` table (`Employee.id == actor.id`), and reusing it here would mean joining `Employee` purely to reuse a helper. Document the choice in the module docstring (Open Decision #3).

- [x] **Task 4 — `app/services/notifications.py` (new module, AC5/AC6)**
  - [x] The small-read-module shape (`services/team.py`, `services/audit.py`): one session, opened, queried, closed. `list_notifications(limit, offset, actor)`, `unread_count(actor)`, `mark_notification_read(actor, notification_id)`.
  - [x] `mark_notification_read` opens **one write transaction**: locate the row **scoped to the actor** → `None` ⇒ `authz.not_found()` (404); then call `mark_read`; `rowcount == 0` ⇒ **already read ⇒ SUCCESS (200)**, not a conflict. `commit()`. (Landmine 3.)
  - [x] Notifications are intrinsically scope `self`, so there is exactly one scope and it is decided **here**, never in the route (`api/` may not import `Scope` — import-linter contract 2).
  - [x] 🚫 No role check in this module. All three endpoints are role **`any`** (Landmine 2) — a role check here would be dead code implying the gate is optional (the `services/audit.py` posture, inverted).

- [x] **Task 5 — `app/api/v1/notifications.py` + router + scope matrix (AC5/AC6)**
  - [x] Three routes, **all guarded by `Depends(get_current_employee)` — NOT `require_role`** (Landmine 2). The `POST /leave-requests` precedent: "Scope `self` is intrinsic to the token subject, so the guard is `get_current_employee` (any authenticated role)" (`leave_requests.py:19`).
    - `GET /notifications` → `Page[NotificationResponse]` with `params: PageParams = Depends()` — the `items`/`page`/`page_size`/`total` envelope, clamped (NFR-11). **Reuse `Pager` on the frontend; do not ship a fourth page-1-only list** (deferred-work `:62`, `:70`, `:76`).
    - `GET /notifications/unread-count` → the derived count.
    - `PATCH /notifications/{notification_id}/read` → 200.
  - [x] ⚠️ **Route-ordering:** declare `GET /notifications/unread-count` **before** any `GET /notifications/{id}` route, or FastAPI matches `unread-count` as a path param and 422s on the UUID parse. (This story specs no `GET /notifications/{id}`, so the hazard only exists if one is added.)
  - [x] `api/` imports **only** `fastapi`, `pydantic`, `app.api.v1.*`, `app.services.*` (contract 2 — it may import **neither `app.repositories` nor `app.domain`**, *even under `TYPE_CHECKING`*). Project the service's view to the response **by hand**, typing the argument `object`, the `team.py:_to_response` pattern.
  - [x] `app/api/v1/router.py` — **two lines**: add `notifications` to the import tuple (alphabetical, between `me` and `policy_changes`) **and** `api_v1_router.include_router(notifications.router)`. 🚨 Miss the second and **every notification test 404s**, including the no-token case (3.2's red-green).
  - [x] 🚨 **`tests/test_scope_matrix.py` — register the ONE path-param endpoint** (Landmine 8):
        `("PATCH", "/api/v1/notifications/{notification_id}/read"): frozenset({Scope.SELF}),`
        The path template must be **byte-exact** to the FastAPI declaration. `GET /notifications` and `GET /notifications/unread-count` carry no path param → **OUT of the matrix by construction**; registering either trips `test_no_registered_entry_names_a_route_the_app_does_not_expose`. Do **not** declare the PATCH route `include_in_schema=False` (deferred-work `:24` — it would escape the completeness gate).

- [x] **Task 6 — Hook the submit transaction (AC2, AC4)**
  - [x] In `submit_leave_request` (`app/services/leave_requests.py:300-440`), insert the notification **after** `insert_audit_entry` (ends `:426`) and **before** the `SubmitView` snapshot (`:431`) — inside the `with Session(...)` block, **before `session.commit()`** at `:439`. `request.id` (from `:404`) is flushed and available. `created_at=_now()` (the shell clock, AD-1).
  - [x] 🚨 **The two branches produce DIFFERENT notifications** (Landmine 1):
    - `actor.manager_id is not None` (the `else:` branch, `:391-402`) → **one `REQUEST_SUBMITTED`, recipient = `actor.manager_id`.** No lookup query is needed — the manager is read straight off the authenticated actor.
    - `actor.manager_id is None` (the managerless auto-approve branch, `:377-390`) → **one `REQUEST_APPROVED`, recipient = `actor.id` (the applicant notifies themselves), and ZERO `REQUEST_SUBMITTED`** — AC4 is explicit, "because it would have no addressee."
  - [x] The naive implementation — one unconditional `REQUEST_SUBMITTED` insert with `recipient=actor.manager_id` — violates a **NOT NULL** FK on the managerless path and surfaces as a **raw 500**, and it fails AC4 twice over.

- [x] **Task 7 — Hook the decide transaction (AC3) — and NOT the cancel one**
  - [x] 🚨 **`_decide` (`:449-558`) is SHARED by all three of its callers — approve (`:561`), reject (`:587`) and cancel (`:611`).** An unconditional insert inside it fires on **self-cancellation**, which AC3 does not grant and the `kind` CHECK does not admit. (Landmine 1.)
  - [x] Add a **keyword-only opt-in** to `_decide`, mirroring `recompute_carry_forward: bool = False` exactly — that parameter exists for precisely this reason and is the house precedent for "a transition-specific side effect that must be a stated decision, not an accident":
        `notify_kind: str | None = None`
  - [x] `approve_leave_request` passes `notify_kind=vocabulary.NOTIFICATION_REQUEST_APPROVED`; `reject_leave_request` passes `notify_kind=vocabulary.NOTIFICATION_REQUEST_REJECTED`; **`cancel_leave_request` passes nothing** and the default `None` means no notification. Say so in the docstring, as 2.10 did for the carry-forward hook.
  - [x] Insert between `insert_audit_entry` (ends `:554`) and `view = row_to_view(...)` (`:556`), before `session.commit()` (`:557`).
  - [x] 🚨 **The recipient is `row.employee_id` — the APPLICANT — never `actor.id`, who is the Manager deciding.** Getting this backwards notifies the Manager about their own decision, and an AC5 "only my notifications" test still passes.
  - [x] `services/cancellation.py` is **safe by construction** — approving a Cancellation Request transitions the Leave Request to CANCELLED via `leave_request_repo.transition_status` **directly** (`cancellation.py:299-306`), never through `_decide`. It writes **zero** notifications, which is the settled contract (readiness F-4, `epics.md:473`): FR-14's three kinds are exhaustive; an Admin discovers a Cancellation Request through `GET /cancellation-requests`, not a notification. It is *accidentally* safe, so **assert it with a test** rather than relying on it.

- [x] **Task 8 — Backend tests (`tests/integration/test_notifications.py`)**
  - [x] 🚨 **That basename is currently free — keep it unique.** The test tree has no `__init__.py`; a duplicate basename anywhere under `tests/**` is a pytest "import file mismatch" that **aborts the entire suite** while the file passes standalone (3.3 hit this and had to rename). Do not also add a `tests/domain/test_notifications.py`. **Run the FULL suite, not just the new file.**
  - [x] `import app.main` in the test module, or the routes are unregistered and the suite **false-greens** (the 2.9 trap).
  - [x] **AC1 (the schema, and the part `alembic check` CANNOT see):** assert from the live catalog that `notification` has the six columns, the `kind` CHECK admits exactly the three values, and — 🚨 **critically** — that the index is **PARTIAL**:
        `SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname='ix_notification_recipient_unread'` → assert the definition contains the `read_at IS NULL` predicate.
        **Asserting only the index NAME (the `test_migration_smoke.py:262-271` precedent) is NOT enough here.** See Landmine 7: Alembic 1.18.5 does not compare a partial index's predicate at all, so a plain, non-partial index passes `alembic check`, passes `test_model_migration_agreement`, and passes a name-only assertion — while silently failing AC1.
  - [x] **AC2:** a managed Employee submits → exactly one row, `kind=REQUEST_SUBMITTED`, `recipient_employee_id == the manager's id`. **And the rollback half:** a submission refused with `INSUFFICIENT_BALANCE` leaves **zero** notification rows (the transaction is the boundary — AD-16's "one exists if and only if the transition committed").
  - [x] **AC3:** approve → one `REQUEST_APPROVED` to `leave_request.employee_id`; reject → one `REQUEST_REJECTED` to the same. **And the negative that AC3 implies:** a **self-cancel writes ZERO notifications**, and a **409'd approve** (a lost race) writes zero — pin both.
  - [x] **AC4:** a managerless applicant submits → the applicant holds exactly one `REQUEST_APPROVED`, and `COUNT(kind='REQUEST_SUBMITTED') == 0` across the world.
  - [x] **AC5:** two employees, notifications each → each `GET /notifications` returns only their own; `unread-count` matches `COUNT(*) WHERE read_at IS NULL`. **Pin the exact key set** of a notification item and of the unread-count body (Landmine 12) — accidental widening must fail the build. Pin the page envelope as exactly `{items, page, page_size, total}`.
  - [x] **AC6:** PATCH twice → first call marks read and the count decrements by one; **second call is a 200, not a 409, and the count does not move again**. A **different** Employee PATCHing that id gets **404** with the full `{code, message, details}` envelope and `details == {}` — **never a 403** (Landmine 2). A nonexistent-but-valid UUID is byte-identical to the not-yours case (AD-10).
  - [x] 🚨 **SM-4 must still be exactly 14.** Run `tests/integration/test_audit_entries.py::test_sm4_...` **unchanged**; if it reports 15+, you wrote an audit row for a notification. Unlike `rollover.py`/`recalculation.py` — which prove it by *not importing* `audit_entry_repo` at all — this story writes **inside** the two functions that already call `insert_audit_entry`, so the discipline is: **add zero `insert_audit_entry` call sites.** The count of those call sites must be byte-identical before and after (six: `leave_requests.py` ×2, `cancellation.py` ×4).
  - [x] Seed extra rows at **repository level** where possible (the 3.1/3.3 precedent) — a direct INSERT writes no audit row and leaves SM-4's ledger undisturbed.
  - [x] Teardown through the **`owner_engine`** fixture, not `get_engine()` (Landmine 6).

- [x] **Task 8b — 🚨 REPAIR THE EIGHT EXISTING TEARDOWNS, or the suite goes red (Landmine 16)**
  - [x] From the moment `notification` exists, **every existing integration test that submits a Leave Request through the API now creates notification rows** — and those tests' teardowns bulk-delete the `leave_request` and `employee` rows those notifications reference. With NOT NULL FKs and no `ON DELETE` clause, that is a **`ForeignKeyViolation` → fixture error → the whole module red.** This story creates the breakage; this story fixes it.
  - [x] In each teardown, add `session.execute(delete(Notification).where(...))` **BEFORE** the `delete(LeaveRequest)` / `delete(Employee)` statements — precisely where `delete(AuditEntry)` already sits, and for exactly the same reason (`test_leave_request_submit.py:176-207` is the canonical ordering comment: audit rows have no FK to `leave_request`, so they go first; notifications **do** have one, so they must go first too). These teardown blocks already run under `owner_engine`, so the missing `DELETE` grant is not an obstacle.
  - [x] The eight files: `tests/integration/test_leave_request_decide.py` (`:207-209`, `:218`), `test_leave_request_submit.py`, `test_audit_entries.py` (`:234`, `:239`), `test_cancellation_request.py`, `test_leave_request_history.py`, `test_rollover.py`, `test_policy_change.py`, `test_holiday_recalculation.py`. (`test_department_calendar.py` seeds at repository level and deletes both parents at `:375`/`:389` — check it too.) **Verify by running the full suite, not by trusting this list.**
  - [x] 🚫 The two instinctive "fixes" are both **forbidden**: granting the app role `DELETE` (Landmine 6 — the teardown runs as owner already, so it is unnecessary as well as wrong) and adding `ON DELETE CASCADE` (Task 1 — it would signal a deletion path the product explicitly forbids). Delete the children explicitly.

- [x] **Task 9 — Frontend (AC7)**
  - [x] `src/api/notifications.ts` — follow `calendar.ts` (the newest idiom) exactly: `export const NOTIFICATIONS_QUERY_KEY = ['notifications'] as const`, per-params entries at `[...KEY, params]` (TanStack v5 hashes structurally, so prefix invalidation fans out), a `PARAM_NAMES` map, `encodeURIComponent` on **every** value, `` path: `/${string}` ``, `options?: { enabled?: boolean }`. Export `useNotifications`, `useUnreadCount`, `useMarkNotificationRead`. Types via `import type` — `verbatimModuleSyntax: true` makes a plain type import a **compile error**.
  - [x] Barrel: add the value + type exports to `src/api/index.ts` **before** the `queryClient` line. Features import through `src/api`, never `src/api/client`.
  - [x] **The badge** — a local component in `App.tsx`, modelled on `HealthIndicator` (`App.tsx:35-42`), rendered as a third flex child in `.shell__header` (`App.tsx:62-65`). `.shell__header` is already `display:flex; justify-content:space-between; flex-wrap:wrap`, so it slots in with **ZERO new CSS**: `<span className="badge badge--waiting">{n} unread</span>` reuses the existing `.badge` pill (`index.css:96-115`).
  - [x] 🚨 **NO ROLE GATE on the badge.** AC7's "an Employee is authenticated" means *an authenticated person*, **not** the `EMPLOYEE` role — and all three endpoints are role `any` (api-contracts §4.8). **A Manager is the primary recipient** (`REQUEST_SUBMITTED` is addressed to them); gating on `role === 'EMPLOYEE'` would hide exactly the notification FR-14 exists to deliver. The panel-gate idiom (`if (!isEmployee) return null`) is **wrong here** — this is the one surface in the app with no role gate. (Landmine 2.)
  - [x] **The list** — a `NotificationsPanel` in `src/features/notifications/`, the standard skeleton: the mandatory loading/error/empty triad, `.panel`/`.emp-list`/`.emp-row`/`.emp-summary`/`.muted`, and `Pager` from `src/components/Pager.tsx`. "Opening a Notification marks it read" (AC7) — the per-row mutation idiom from `ManagerQueuePanel` (`mutation.variables` as the in-flight/failed id, `busyId` to disable, inline `.emp-error` on the failing row).
  - [x] Render `created_at` **verbatim, as received**. No date arithmetic, no `new Date(...)` formatting — the `auditEntries.ts` precedent. 🚨 The tokens `getDay`/`getUTCDay` must not appear **anywhere under `frontend/src`, including in a comment** — `backend/tests/test_frontend_no_client_day_count.py` line-scans raw source and has already tripped twice (2.5, 2.7) on a comment.
  - [x] **Invalidation — be precise, and do NOT copy the fan-out blindly:**
    - `useMarkNotificationRead` → `onSettled` (not `onSuccess` — the 2.7 review patch) invalidating `NOTIFICATIONS_QUERY_KEY`. The prefix reaches both the badge's count query and the list's paged queries **only if they share the `['notifications']` prefix** — so key the count as `[...NOTIFICATIONS_QUERY_KEY, 'unread-count']`.
    - `useSubmitLeaveRequest` → **add `NOTIFICATIONS_QUERY_KEY` to its invalidation.** This is the **only** same-user case: a **managerless** applicant's submit creates a notification addressed to *themselves* (AC4), so without this their badge is stale.
    - 🚫 **Do NOT add `NOTIFICATIONS_QUERY_KEY` to `invalidateAfterDecision`** (`leaveRequests.ts:211-215`). A decision notifies the **applicant**, and the actor is the **Manager** — the decider is *never* the recipient (a Manager cannot decide their own request; scope `reports` excludes their own row, pinned since 2.7). Note the one case that looks like a counter-example and is not: `invalidateAfterDecision` is *also* `useCancelLeaveRequest`'s handler (`:243`), where the actor **is** the applicant — but a self-cancel writes **zero** notifications (AC3's implied negative), so there is still nothing to invalidate. Cross-user freshness is `staleTime` + refetch, not invalidation (Open Decision #4).
  - [x] 🚨 **Sign-out hygiene.** Add `queryClient.removeQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })` beside the existing `ME_QUERY_KEY` removal at **both** `App.tsx:183` (the `SESSION_EXPIRED_EVENT` handler) and `App.tsx:195` (`onAuthenticated`). Without it, on a shared browser the next user sees the **previous user's unread count** for up to `staleTime` (30 s) — a genuine cross-user disclosure, not a cosmetic staleness.

- [x] **Task 10 — Full verification**
  - [x] **Measure the baseline FIRST**, before writing a line: `cd backend && .venv/bin/python -m pytest --collect-only -q | tail -3`. It is **537** (measured 2026-07-14 on this tree — 3.2's recorded baseline undercounted by 2, so measure, never assume).
  - [x] Expected total = **537 + your new tests + 3 + 1**. Two *existing* parametrized guards auto-generate cases from the files this story adds, and both must be accounted for or the arithmetic will not close:
        **+3** — `test_vocabulary_literals` is parametrized **one case per `.py` file** under `app/`, and this story adds three (`repositories/notification.py`, `services/notifications.py`, `api/v1/notifications.py`).
        **+1** — `test_migrations_insert_nothing.py:150` is parametrized over `_migration_files()`, which globs `alembic/versions/*.py`; `0012_notification.py` is a **12th case**.
        (`test_frontend_no_client_day_count.py` is **not** per-file — it is one test looping internally — so the two new frontend files add nothing.)
        Verify by collecting with and without the story's files so the arithmetic is **explained, not assumed** (the 3.3 standard).
  - [x] Backend: `.venv/bin/python -m pytest` (integration needs `docker compose up -d`); `import-linter` **7/7 byte-identical** (`pyproject.toml` must not appear in the diff); `alembic check` clean; migration `up → down → up` idempotent; `python -m seed` exit 0.
  - [x] Frontend: `npm run build` (`tsc -b && vite build`) + `npm run lint` (oxlint).
  - [x] ⚠️ **State plainly in the Dev Agent Record: there is STILL no frontend test runner** (`package.json` has only dev/build/lint/preview — no vitest, no jest, no testing-library). **AC7 is verified by tsc + vite build, oxlint, the day-count guard scan, and code reading — and by NOTHING ELSE.** Say so rather than implying coverage that does not exist.

- [x] **Task 11 — RULE ON THE AD-6 SUBMIT GAP (Open Decision #1) — LAST, and separable**
  - [x] Read Open Decision #1 in full. **This story is the named forcing point** — five stories (2.11 #8 → 2.12 #11 → 3.1 #6 → 3.2 #4 → 3.3 #7) deferred it explicitly to 3.4, and only 3.5 (a read-only dashboard) remains in the epic. **Silence ships the bug.**
  - [x] 🚨 **Do NOT implement the "one-line fix" that `deferred-work.md:67,75` recommends.** It is unsafe as written — see Landmine 15.
  - [x] Implement the **forward-checked** fix, or **declare it NOT DONE with a reason**. Either is acceptable; doing it naively is not.

### Review Findings (code review 2026-07-15)

- [x] [Review][Decision] Refused carry-forward recompute appends a new `admin_review_flag` on every retry with no dedupe — an Employee submitting several requests against an unreconcilable pair grows the Admin queue unboundedly for one underlying defect (backend/app/services/rollover.py:414-421, reached from every submit via leave_requests.py). The correct dedupe semantics (when does a flag become re-raisable?) need a product call. — RESOLVED 2026-07-15 (reviewer: dedupe on an open identical flag): `flag_exists` added to the repo (a SELECT, inside the INSERT+SELECT grant) and both refusal writers skip the insert when an identical (pair, year, cause) flag already stands; pinned by the extended AD-6 submit test and the new rollover batch test
- [x] [Review][Decision] The unread badge renders nothing at zero — deviates from AC7's literal "an unread count is visible" and the deviation is not declared in the Dev Agent Record, contrary to this epic's posture on declared deviations (frontend/src/App.tsx:69-72). Accept-and-declare, or render "0 unread"? — RESOLVED 2026-07-15 (reviewer: accept and declare): behavior kept, deviation declared in the Completion Notes List below
- [x] [Review][Patch] `run_rollover`'s own loop still calls `set_accrual` unguarded — a stale refused pair (a population the new submit-path refusals grow) makes a legal AC5 re-run of `run_rollover(Y)` abort the entire org-wide batch on one `ValueError`; the "both defects die here" claim does not cover this path, and the deleted canary's batch-abort coverage was not replaced [backend/app/services/rollover.py:178-196] — FIXED 2026-07-15: the batch forward-checks each pair (write nothing, flag `CAUSE_ROLLOVER_RECALCULATION`, count in `RolloverSummary.refused_pairs`, continue); pinned by `test_a_refused_pair_does_not_abort_the_rollover_batch`; the overstated docstring claims corrected
- [x] [Review][Patch] One transition stamps three different `_now()` instants (recompute, audit row, notification) while this same diff refactored cancellation.py to hoist a single `occurred_at` for exactly this reason — hoist one instant per transition [backend/app/services/leave_requests.py] — FIXED 2026-07-15: one hoisted `occurred_at` per transition in both `submit_leave_request` and `_decide` (and one per batch in `run_rollover`)
- [x] [Review][Patch] No index serves the paged notification list — read rows fall outside the partial index's `WHERE read_at IS NULL` predicate, so `GET /notifications` degrades to a full scan+sort as history accumulates (DELETE is deliberately withheld); the `leave_request_id` FK is also unindexed [backend/alembic/versions/0012_notification.py:150] — FIXED 2026-07-15: `ix_notification_recipient_created (recipient_employee_id, created_at, id)` and `ix_notification_leave_request` added to the unreleased 0012 and the model, and created on the dev database
- [x] [Review][Patch] `deferred-work.md:67`/`:74`/`:75` still record the AD-6 defects as live, name a deleted test as their passing pin, and prescribe the exact one-liner Landmine 15 brands UNSAFE — strike/update them per Open Decision #1's closure claim [_bmad-output/implementation-artifacts/deferred-work.md:67] — FIXED 2026-07-15: all three entries struck with closure notes naming 3.4 Task 11 and the review's batch guard
- [x] [Review][Defer] The forward-check `FOR UPDATE` walk now runs on every submit even in the common case where no later year is materialized, and serializes all writers of a pair on a multi-year lock chain once Y+1 exists — deferred, settled Task 11 design; revisit with measurement, not speculation
- [x] [Review][Defer] `REQUEST_SUBMITTED` can be addressed to a deactivated Manager (only `manager_id is None` is tested, not the manager's `is_active`) [backend/app/services/leave_requests.py:417] — deferred, pre-existing reporting-line gap: deactivation does not reassign reports, so the whole approval flow (not just the notification) is broken for that report

---

## Dev Notes

### What already exists — reuse it, do not rebuild it

| You need | It already exists | Do not |
|---|---|---|
| The submit transaction | `services/leave_requests.py:300-440`, one `Session`, commits at `:439` | open a second transaction, or write the notification after the commit |
| The decide transaction | `_decide`, `:449-558`, commits at `:557` | duplicate it per transition — the three callers are thin delegations that own no session |
| A transition-specific opt-in flag | `recompute_carry_forward: bool = False` (`:460`) — the exact precedent | insert unconditionally (it fires on cancel) |
| The manager's id | `actor.manager_id`, read off the authenticated actor (`:377`) | issue a lookup query |
| The shell clock | `_now()` (`:244-246`) → `datetime.now(timezone.utc)` | call `datetime.now()` in a repository (AD-1: the clock lives in the service shell) |
| Pagination | `PageParams` + `Page[T]` (`api/v1/pagination.py`), clamped, `MAX_PAGE_SIZE=100`, `MAX_PAGE=1_000_000` | re-type a page bound |
| The pager UI | `src/components/Pager.tsx` (lifted in 3.2) | ship a fourth page-1-only list |
| The 404 convention | `authz.not_found()` — one message, `details == {}` | interpolate an id into the message |
| The guarded UPDATE idiom | `transition_status` (`repositories/leave_request.py:350-388`) | read-then-write |
| The badge pill | `.badge` / `.badge--*` in `index.css:96-115`, and `HealthIndicator` as the local-component precedent | add CSS |
| An endpoint module | `api/v1/team.py` (90 lines) — the whole shape | let `api/` import `Scope`, the ORM, or `vocabulary` |

### 🚨 The Landmines

**1. `_decide` (`leave_requests.py:449-558`) is shared by CANCEL, and submit has TWO branches.** The two highest-probability defects in this story, and both ship green under a careless test.
   - An unconditional insert in `_decide` fires on **self-cancellation** — no AC grants it, and there is no `kind` for it. Use the keyword-only `notify_kind: str | None = None` opt-in.
   - An unconditional `REQUEST_SUBMITTED` in `submit_leave_request` hits a **NOT NULL** recipient FK on the managerless path → raw 500. AC4 requires the managerless applicant to receive a **`REQUEST_APPROVED` addressed to themselves**, and **zero** `REQUEST_SUBMITTED` to exist.
   - On decide, the recipient is **`row.employee_id`** (the applicant), **not `actor.id`** (the Manager).

**2. 🚨 Role `any`, scope `self` — a non-addressee gets 404, NOT 403. This inverts the app's habit.** api-contracts §4.8 (`:215-223`) grants all three notification endpoints to **Role: `any`**, Scope: `self`. Every other read in this app has a role gate, and 3.2/3.3 both shipped a *Manager-only* inversion — the muscle memory is to reach for `require_role`. **Do not.** Use `get_current_employee`. And because the role gate always admits, the **G3 settlement** (`api-contracts.md:37-44`) decides the rest: *"does the actor's role admit them to this endpoint at all? If no → 403 … If yes → the scope predicate runs, and a miss is 404."* A notification belonging to someone else is a **scope miss → 404**, byte-identical to a nonexistent id (AD-10). This also means **the frontend badge has no role gate** — a Manager is the primary recipient.

**3. Idempotent mark-read is NOT AD-4's `rowcount == 0 ⇒ 409`.** Every existing guarded UPDATE reads a zero rowcount as a lost race (409 `TRANSITION_NOT_ALLOWED`). Here, `rowcount == 0` has **two** causes and they get **different** answers:
   - *already read* → **SUCCESS, 200.** That is what "idempotent" means (AC6: "marked read and the count decrements **once**").
   - *not yours / nonexistent* → **404.**
   Disambiguate by **locating the row under the actor's scope first** (`None` ⇒ `authz.not_found()`), **then** running the guarded UPDATE and treating `rowcount == 0` as already-read. This is a conscious departure from the AD-4 reflex — **say so in the docstring**, or a reviewer reads it as a bug. (Inherited caveat, awareness only: the clean-behaviour of a guarded UPDATE under a lost race silently depends on READ COMMITTED — deferred-work `:57`. Do not fix.)

**4. SM-4 is pinned at exactly 14 audit rows. A notification is not a state transition.** `tests/integration/test_audit_entries.py:511-525` asserts `len(rows) == 14` **and** the per-`subject_type` breakdown (`LEAVE_REQUEST: 10, CANCELLATION_REQUEST: 4`). AD-8 reserves `audit_entry` for *"exactly one row per state transition of a Leave Request or a Cancellation Request, **and nothing else**"* — that "and nothing else" is the clause that keeps SM-4 literally true. `rollover_run`, `admin_review_flag` and `policy_change` are each their own log for exactly this reason; **`notification` is the log of itself.** There is no `SUBJECT_NOTIFICATION` and there must not be one. Add **zero** `insert_audit_entry` call sites.

**5. `notification` is the FIRST non-append-only table since `0008` — and every migration since has taught the wrong lesson.** `0009`, `0010`, `0011` all created append-only tables and all wrote `GRANT INSERT, SELECT`. The dev agent copying the nearest template will copy that line — and `PATCH …/read` then fails at **runtime** with `InsufficientPrivilege` while the unit suite stays green (only an integration test against real Postgres catches it). `read_at` is **mutable**: the grant is **`GRANT SELECT, INSERT, UPDATE`**. There is deliberately **no `ALTER DEFAULT PRIVILEGES`** in this codebase (`0008:100-104`) precisely so that *"a migration that adds a table must add its grant, deliberately. That is a feature."*

**6. The app role cannot DELETE a notification — so tests cannot clean up through `get_engine()`.** Follow the audit-row precedent exactly: cleanup runs through the session-scoped **`owner_engine`** fixture (`tests/integration/conftest.py:35-73`). A test "fixing" its teardown by granting the app role `DELETE` is deleting the guarantee.

**7. 🚨 `alembic check` CANNOT see that the index is partial — verified, not assumed.** `grep -rl postgresql_where` across `alembic 1.18.5` returns **nothing**: Alembic compares an index's name, columns, uniqueness and expressions, but its PostgreSQL `_dialect_options()` returns only `nulls_not_distinct`. SQLAlchemy 2.0.51 *does* reflect the predicate (`dialects/postgresql/base.py:5015`), but **Alembic never compares it.** Consequences, both of which matter:
   - **Good news:** there is no spurious-diff risk. Declaring `postgresql_where` on both the model and the migration will not make `alembic check` fail on a normalization mismatch (`read_at IS NULL` vs `(read_at IS NULL)`).
   - **Bad news, and this is the trap:** a **plain, non-partial** index passes `alembic check`, passes `test_model_migration_agreement`, and passes a name-only `pg_indexes` assertion — while **silently failing AC1**, which demands a partial one. The existing index assertions in `test_migration_smoke.py:262-271` check `indexname` only and are **not sufficient here**. Assert `indexdef` and require the `read_at IS NULL` predicate in it.

**8. `PATCH /notifications/{notification_id}/read` has a path param → the SM-3 scope matrix is not optional.** `tests/test_scope_matrix.py` discovers every `/api/v1` operation whose template contains `{`, and `test_every_identifier_endpoint_is_registered` fails on any that is unregistered. The two `GET`s have no path param and must **NOT** be registered (a stale entry fails a different test). **This makes 3.4 the first Epic-3 story to legitimately edit a guard file** — 3.1, 3.2 and 3.3 all shipped zero. Declare it as an owned change, not an accident.

**9. `test_vocabulary_literals` forbids the three `kind` strings as literals anywhere under `app/` or `seed/`** — annotations included, docstrings excluded, exact equality (not substring), AST-walked. `Literal["REQUEST_SUBMITTED", …]` is therefore **unwritable**. It also adds **one parametrized case per `.py` file** under `app/`, so this story's three new modules move the test count by +3 before a single new test is written. (`alembic/versions/` and `tests/` are **not** scanned.)

**10. The packageless test tree: a duplicate basename aborts the WHOLE suite.** No `__init__.py` anywhere under `tests/`. `tests/integration/test_notifications.py` is currently a free basename — keep it that way, and **run the full suite**, because a colliding file passes standalone and only fails on collection of the whole tree. This is exactly what 3.3 hit.

**11. `api/` may import neither `app.repositories` nor `app.domain` — even under `TYPE_CHECKING`.** So `api/v1/notifications.py` cannot name `Scope`, cannot import `vocabulary`, cannot import the ORM `Notification`, and cannot import the service's view dataclass. Duck-type it as `object` and project by hand. The `Scope.SELF` decision lives in `services/notifications.py`.

**12. Pin the exact response key sets.** The house rule (3.2 `test_team.py:52`, 3.3 `test_department_calendar.py:86-97`): assert `set(item) == _EXPECTED_ITEM_KEYS` so accidental widening — a disclosure — **fails the build**. Also: `tests/test_pagination.py` pins the page envelope at exactly `{items, page, page_size, total}` — **a fifth field fails the build**; compute page count client-side.

**13. `LeaveRequestResponse`'s ten keys are FROZEN.** `test_department_calendar.py:634` asserts the **approve endpoint's response body** is exactly the pre-story ten keys. Do **not** add `notification_id`, `notified: true`, or anything else to the decide/submit responses. The notification is a side effect of the transaction, not a field of its response.

**14. Do not add a ninth balance method.** `test_balances_module_surface.py` pins `services/balances.py` at exactly 8 public callables. This story needs none.

**15. 🚨 The AD-6 "one-line fix" that `deferred-work.md` recommends is UNSAFE. Do not implement it as written.** See Open Decision #1 — this is the most consequential correction in this story.

**16. 🚨 Creating the table turns EIGHT existing integration modules red — and the story that creates the breakage must fix it.** The instant `notification` exists, every existing test that submits a Leave Request through the API produces notification rows that FK-reference `leave_request` and `employee`. Those tests' teardowns bulk-delete exactly those parents, and with NOT NULL FKs and no `ON DELETE` clause the delete raises **`ForeignKeyViolation`** → fixture error → the **whole module** fails, not just one test. This will not show up in the new test file; it shows up in the full-suite run. See **Task 8b**. The two fixes that will occur to you first — grant the app role `DELETE`, or add `ON DELETE CASCADE` — are **both forbidden** (Landmine 6 and Task 1 respectively), and both are unnecessary: those teardown blocks already run under `owner_engine`. Delete the notification rows explicitly, ahead of their parents, exactly where `delete(AuditEntry)` already sits.

### Architecture compliance

- **AD-16** (`ARCHITECTURE-SPINE.md:157-161`), the governing decision, all four clauses: *"A notification carries a recipient, a `kind` discriminator, the Leave Request it concerns, a nullable `read_at`, and `created_at`. The unread count is `COUNT(*) WHERE read_at IS NULL` and is **never stored**. **The service that performs a transition is the service that writes its Notification, inside that transition's transaction**, so one exists if and only if the transition committed; **no other service writes notifications.** Mark-read is an idempotent `PATCH` on the notification, permitted only to its addressee."*
- **AD-3** — exactly one transaction per command, opened in `services/`, never in a route or repository. This story opens **no new transaction on the write path**: it rides the existing submit and decide transactions.
- **AD-1** — `api → services → {repositories, domain}`; 7 import-linter contracts, pinned by name **and content**.
- **AD-10** — authorization is a query predicate; a scope miss is a 404 byte-identical to a nonexistent id.
- **AD-21** — every enumerated string declared once in `domain/`, `UPPER_SNAKE_CASE`, a literal nowhere else. Binds FR-14 by name.
- **AD-9 does NOT apply.** Its append-only grant list is exactly `audit_entry` and `rollover_run`. `notification` is a mutable table with exactly one mutable column.
- **NFR-04** — the scope predicate is **in the SQL**, never a filter over retrieved rows. **NFR-11** — the list is server-bounded. **NFR-18** — responsive (the existing `.badge` + the `@media` at `index.css:119-136` handle it).

### The `kind` enum is EXACTLY three values — cancellations notify nobody

Settled twice, and a review proposal to the contrary was **rejected**. Readiness F-4 remediation (`:955`): *"Epic 3's note corrected: `services/cancellation` writes **no** Notification. FR-14's three kinds are exhaustive, and notifying 'the Admin' would require a fan-out semantics no source fixes while FR-14 demands *exactly one* Notification per event."* And `epics.md:473`: *"an Admin discovers a Cancellation Request through `GET /cancellation-requests` (Story 2.8), not through a notification."* **No notification is ever addressed to an Admin** (readiness `:566`).

⚠️ `architecture/…/reviews/review-adversarial.md:166` proposes extending `kind` with `CANCELLATION_APPROVED`/`CANCELLATION_REJECTED` and a polymorphic subject. **That proposal was NOT adopted.** `reviews/` are companions, not the spine. Do not build from it.

The complete cardinality table — every transition the system can perform:

| Transition | Notifications | Kind | Recipient |
|---|---|---|---|
| Submit, applicant **has** a Manager (→ PENDING) | 1 | `REQUEST_SUBMITTED` | the applicant's **Manager** |
| Submit, applicant has **no** Manager (→ APPROVED, SYSTEM) | 1 | `REQUEST_APPROVED` | the **applicant** |
| PENDING → APPROVED (Manager decides) | 1 | `REQUEST_APPROVED` | the **applicant** |
| PENDING → REJECTED (Manager decides) | 1 | `REQUEST_REJECTED` | the **applicant** |
| PENDING → CANCELLED (applicant cancels own) | **0** | — | — |
| Cancellation Request raised / approved / rejected | **0** | — | — |
| APPROVED → CANCELLED (via approved CR) | **0** | — | — |
| Any **refused** transition (409/400/404) | **0** | — | — |

### File structure

**New**
- `backend/alembic/versions/0012_notification.py`
- `backend/app/repositories/notification.py`
- `backend/app/services/notifications.py`
- `backend/app/api/v1/notifications.py`
- `backend/tests/integration/test_notifications.py` *(basename must stay globally unique)*
- `frontend/src/api/notifications.ts`
- `frontend/src/features/notifications/NotificationsPanel.tsx`

**Modified**
- `backend/app/domain/vocabulary.py` — 3 constants + `__all__`
- `backend/app/repositories/models.py` — `class Notification(Base)`
- `backend/app/api/v1/router.py` — 2 lines
- `backend/app/services/leave_requests.py` — the two hooks (+ Task 11, if adopted)
- `backend/tests/test_scope_matrix.py` — 1 registry entry
- `backend/tests/test_migrations_insert_nothing.py`, `backend/tests/integration/test_migration_smoke.py`, `backend/tests/integration/test_schema_1_2.py` — 1 entry each
- 🚨 **Eight existing integration teardowns (Task 8b / Landmine 16)** — `tests/integration/test_leave_request_{decide,submit,history}.py`, `test_audit_entries.py`, `test_cancellation_request.py`, `test_rollover.py`, `test_policy_change.py`, `test_holiday_recalculation.py` (+ check `test_department_calendar.py`). Each needs `delete(Notification)` ahead of its `delete(LeaveRequest)`/`delete(Employee)`.
- `frontend/src/api/index.ts`, `frontend/src/App.tsx`, `frontend/src/api/leaveRequests.ts`

**Must NOT change:** `app/main.py` (`CODE_TO_STATUS`), `pyproject.toml` (`[tool.importlinter]`), `services/balances.py` (8-method surface), `repositories/audit_entry.py` and `repositories/leave_request.py` (pinned surfaces), `tests/test_scoped_getters.py` (`EXEMPT`), `LeaveRequestResponse`'s 10 keys, `0008`'s grant tuples, `frontend/src/index.css` (zero new CSS — and if a class is genuinely needed, it is the app's **first** story-added CSS and must be **declared** as such).

### Testing requirements

`pytest` **is** the build — there is no CI pipeline, so checks that must "fail the build" fail `pytest` instead. Backend: `cd backend && .venv/bin/python -m pytest` (Python 3.13, not 3.14; integration tests skip with a reason if `docker compose up -d` is absent). Frontend: `npm run build && npm run lint`.

**Baseline: 537 collected (measured 2026-07-14 on this tree). Measure it again first.**

---

## Open Decisions

### 🚨 #1 — THE AD-6 SUBMIT GAP. This story is the forcing point, and the recommended fix in `deferred-work.md` is WRONG.

**The history.** Five stories have deferred this, each naming the next: 2.11 (#8) → 2.12 (#11) → 3.1 (#6) → 3.2 (#4) → 3.3 (#7). 3.3 is unambiguous: *"**3.4 (notifications, which hooks the very transitions in `services/leave_requests`) is the named forcing point, and 3.5 closes the epic.**"* `deferred-work.md:75`: *"**It now ships unless Epic 3 picks it up.**"* 3.5 is a read-only dashboard and will not touch submit. **This story rules, or the bug ships.**

**The bug.** AD-6 requires `carried_forward` be re-derived on *"every event that can change its inputs."* Its only input is `available(Y)`. Story 2.10 wired `rollover.recompute_carry_forward` into the **three sites where `available(Y)` RISES** (reject, self-cancel, approve-CR) — its docstring says so explicitly (`services/rollover.py:229-238`). **Submission LOWERS `available(Y)` and recomputes nothing.** So once the rollover has run for `Y` (permitted — `run_rollover` has no clock and only *warns* when rolling an open year, `rollover.py:103-106`), a subsequently-submitted year-`Y` request leaves the stored `carried_forward(Y+1)` **higher than `min(cap, available(Y))`** now is. A leave balance that is wrong and will be believed — PRD §1's central promise.

**⚠️ THE CORRECTION — and it is the reason this must not be done casually.** `deferred-work.md:67` and `:75` both prescribe *"one more `recompute_carry_forward` call in `submit_leave_request`, after `reserve`/`consume_direct`."* **That fix is unsafe as written, and it introduces a new raw 500 on the most-trafficked write path in the application.** Here is why, and it is verifiable in the source:

- `recompute_carry_forward` (declared `rollover.py:214`, body `:265-316`) re-derives `carried_forward(y)` from `available(y-1)` and writes it via `balances.set_accrual` — walking forward through every materialized year.
- It has **no forward check**. Its only backstop is `set_accrual`'s `available >= 0` guard (`balances.py:328-333`), which raises a **bare `ValueError`** — not a `DomainError` — and **no `ValueError` handler exists** in `app/main.py` or `app/api/v1/errors.py`, so it surfaces as a **raw 500** (`deferred-work.md:74`).
- The three existing call sites are all sites where `available(Y)` **RISES**, so the recompute only ever *raises* `carried_forward(Y+1)`. **Submit is the opposite direction:** it **lowers** `available(Y)`, so the recompute **lowers** `carried_forward(Y+1)`, which lowers `accrued(Y+1)`. If year `Y+1` is already substantially spent, `accrued` falls below `consumed + reserved` → `ValueError` → **raw 500 on the submitting Employee.**
- This is the *identical* mechanism as 2.12's one shipped defect (`deferred-work.md:74`), which is already pinned by a **passing** test, `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject`. Adding a fourth call site in submit adds a **new way to reach that same 500**.

So the naive fix trades a wrong-but-quiet balance for a 500 on submit. That is not an improvement, and it is why four reviewers have flinched.

**The fix that actually works — and it closes BOTH open defects at once.** The design call `deferred-work.md:74` names and declines to make (*"refuse? — no error code exists; clamp? — arithmetic no requirement grants; **skip-and-flag? — a fourth flag writer**"*) has a clear answer, and every mechanism it needs **already exists**:

1. **Make `recompute_carry_forward` forward-checked.** Project the walk purely **before** the first write — `domain/recalculation.project_forward` is exactly that function, pure and DB-free, built by 2.11 for exactly this purpose and already serving two callers.
2. **On refusal, skip the write and raise an `admin_review_flag`** with a new `CAUSE_SUBMISSION_RECALCULATION` constant. `admin_review_flag` is the mechanism 2.11 built for *"the arithmetic cannot be made consistent — tell an Admin"*, it already has a read endpoint and a frontend panel, and `CAUSE_*` values are **stored reasons, not error codes** — so `CODE_TO_STATUS` stays untouched (the `CAUSE_HOLIDAY_RECALCULATION` / `CAUSE_POLICY_RECALCULATION` precedent, `domain/vocabulary.py:260,273`). The writer is `insert_admin_review_flag` in `app/repositories/admin_review_flag.py`, which today has exactly **two** call sites, both in `services/recalculation.py` (`:361`, `:577`). This makes `services/leave_requests.py` its **third** writer and adds a new `app.services.leave_requests → app.repositories.admin_review_flag` import — legal under AD-1, but state it as an owned change.
3. **Never refuse the submission itself.** Refusing an Employee's leave request because of a carry-forward artifact in a *later* year would be indefensible, and no error code exists for it. The submission commits; the balance the system cannot reconcile is surfaced to an Admin.
4. Then **add the call in `submit_leave_request`** — now safe — after `reserve`/`consume_direct`, before `commit()`, with `leave_year=start.year`. 🚨 **Use `start.year`, NOT `_current_leave_year()`** — the wrong helper is defined 60 lines above in the same module and is already in scope; `_decide`'s comment at `:529-535` is a standing warning about exactly this trap.

This single change **also fixes `deferred-work.md:74`** — the 2.12 defect where a refused pair's stale cap raises a raw 500 on an innocent third party's reject, and aborts the whole `run_rollover` batch. Both live balance defects die together, because they have one root cause: **`recompute_carry_forward` is unguarded.**

⚠️ **It will break `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject` — and that is correct.** `deferred-work.md:74` says so in advance: *"if that test ever fails, someone fixed the bug; delete it."* Replace it with a test asserting the flag is raised and no 500 occurs.

**RECOMMENDATION: ADOPT the forward-checked fix, as Task 11, executed LAST and kept independently revertable** (its own tests, its own commit-sized change, no entanglement with the notification slice). Rationale: this is the last story with a claim on it; the mechanisms all exist; and it converts two wrong-balance/raw-500 defects into a surfaced, Admin-visible condition.

**If Task 11 cannot be completed safely, DECLARE IT NOT DONE and log it — do not ship the naive one-liner.** A declared miss is honest; an unguarded recompute on the submit path is a regression. This is the PRD's own posture (§7.3): a missed target is reported as a missed target, never reclassified afterwards as a deferral that was always intended.

### #2 — `unread-count`'s response shape is **undefined by every artifact.** RECOMMEND: `{"unread": <int>}`, key set pinned by test.
No binding artifact fixes it — deliberately: api-contracts §5 (`:249-251`) hands per-endpoint schemas to the generated OpenAPI document, *"Fixing them twice would guarantee they diverge."* So the Pydantic model **is** the contract. A single-key object (not a bare integer) keeps it extensible and consistent with every other response in the app being a JSON object. Pin the exact key set by test either way.

### #3 — The scope predicate: a direct column compare, not `employee_scope_predicate`. RECOMMEND: direct, documented.
`employee_scope_predicate(scope, actor)` (`repositories/scoping.py:59-79`) predicates over the **`Employee`** table. A notification's owner column is `recipient_employee_id`, so reusing that helper means joining `Employee` **purely to reuse a helper**. `Notification.recipient_employee_id == actor.id` is the honest predicate, it is applied **in the SQL** (NFR-04/AD-10 satisfied), and the getters still take `actor` (so `test_scoped_getters` is satisfied without an `EXEMPT` edit). Document the reasoning in the module docstring so it does not read as an oversight. There is exactly one scope for a notification — `self` — and it is decided in `services/notifications.py`.

### #4 — Cross-user freshness of the badge. RECOMMEND: no `refetchInterval`. Ship zero new patterns.
A decision notifies the **applicant**, whose browser is not the one that acted — so no invalidation on the actor's client can help. The app has **zero** polling precedent (`refetchInterval` appears nowhere in `frontend/src`). The existing defaults already give a reasonable answer: `staleTime: 30_000` plus TanStack v5's `refetchOnWindowFocus` (on by default) means the badge refreshes when the user returns to the tab — which is when they would look at it. **No AC requires real-time delivery.** Adding the codebase's first `refetchInterval` is a new pattern with a standing cost; if the reviewer wants it, it should be a declared decision, not a silent one.

### #5 — Notification list item shape. RECOMMEND: minimal — `{id, kind, leave_request_id, read_at, created_at}`.
No AC requires the notification to *carry* the request's details; AC7 asks only that a count is visible and that opening marks read. A minimal shape keeps the read a **single-table query with no join** — which also sidesteps 3.1's Landmine 3 (a filter or projection over a joined column makes the page query and the count query disagree, and `total` lies). The UI renders the `kind` as a sentence and the timestamp verbatim. A richer shape is a widening no requirement grants; if a later story wants the leave-request context inline, it can add it deliberately. Pin the exact key set.

---

## Previous Story Intelligence

**From 3.3 (the immediately preceding story):**
- The **baseline must be measured, not assumed** — 3.2 predicted 512 and measured 514. 3.3 measured first and held exactly. Current measured baseline: **537**.
- The **packageless test tree** cost 3.3 a declared deviation: `tests/integration/test_calendar.py` collided with `tests/domain/test_calendar.py` and **aborted the whole suite** while passing standalone. Basenames are globally unique across `tests/**`.
- 3.3 shipped **zero guard-file changes** and said so proudly. **3.4 cannot** — the scope-matrix entry is mandatory (Landmine 8). Declare it as owned.
- `_decide` was left **byte-untouched** by 3.3 (its AC4 was a zero-diff assertion). **3.4 is the story that changes it** — the first since 2.10. Tread carefully and keep the change to the one keyword-only parameter.
- The `row_to_view` / `to_leave_request_response` promotions (private → public) were 3.3's; the single-home rule for response shapes stands — **never redeclare a response model.**

**From 3.2:** the `Pager` lift to `src/components/` (the second-caller rule); the exact-key-set pin as a disclosure guard; the "role gate is usability, the server is the guard" idiom.

**From 3.1:** the app's first pagination UI; filters must be over **local columns** or `total` lies; `MAX_PAGE` clamp closed `deferred-work.md:58`/`:19` (those two entries are now **stale** — this story may strike them).

**From 2.9:** the owner/app two-role split, and `owner_engine` for teardown. Its warning applies directly here: *"the next reader must not 'fix' it by granting the app role `DELETE`."*

**From 2.6/2.7:** the submit and decide transactions this story hooks — read their docstrings before editing; they state their own lock order and explain why submit is balance-first while decide is guarded-UPDATE-first.

## Git Intelligence

HEAD is `4fc1629` ("feat(stories-2.9-2.12): complete leave approval and balance workflow"). **This story builds on the UNCOMMITTED working tree of stories 3.1, 3.2 and 3.3** (all in `review`), exactly as 3.2 and 3.3 each built on their predecessor's uncommitted tree. Modified: `api/v1/{leave_requests,pagination,router}.py`, `repositories/{employee,leave_request}.py`, `services/leave_requests.py`, `App.tsx`, `api/{index,leaveRequests}.ts`. Untracked: `api/v1/{calendar,team}.py`, `services/{calendar,team}.py`, `components/Pager.tsx`, `features/team/`, and three integration test files.

## Latest Technical Information

Stack (pinned, `epics.md:169`): Python 3.13 · FastAPI 0.139.0 · Pydantic 2.13.4 · **SQLAlchemy 2.0.51** · **Alembic 1.18.5** · psycopg 3.3.4 · PostgreSQL 18 · pytest 9.1.1 · React 19.2.7 · Vite 8.1.4 · TypeScript 6.0.3 · **TanStack Query 5.101.2**. Do not upgrade Python to 3.14 — the stack is pinned to 3.13 for library compatibility and the README forbids it.

**Partial index, verified against the installed versions** (this is the basis of Landmine 7): SQLAlchemy 2.0.51 reflects a partial index's predicate into `dialect_options["postgresql_where"]` (`dialects/postgresql/base.py:5015`), but **Alembic 1.18.5 contains no reference to `postgresql_where` anywhere** — its PostgreSQL `_dialect_options()` compares only `nulls_not_distinct`. Therefore `alembic check` neither false-fails on predicate normalization **nor detects a missing predicate**. Syntax, identical on both sides:
- migration: `op.create_index(..., postgresql_where=sa.text("read_at IS NULL"))`
- model: `Index(..., postgresql_where=text("read_at IS NULL"))`

**TanStack Query v5:** query keys are hashed structurally, so `invalidateQueries({ queryKey: ['notifications'] })` matches every `[...key, params]` variant by prefix. `refetchOnWindowFocus` defaults to **true** — which is what makes Open Decision #4's "no polling" recommendation viable.

## References

- `_bmad-output/planning-artifacts/epics.md:1507-1545` — Story 3.4 and its seven ACs; `:472-473` — Epic 3's note that FR-14 hooks `services/leave_request` **only**, and that `services/cancellation` writes no Notification
- `_bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md:157-161` — **AD-16**; `:109-113` — AD-8 ("and nothing else"); `:115-119` — AD-9 (append-only list = `audit_entry`, `rollover_run`); `:121-125` — AD-10; `:187-191` — AD-21 (binds FR-14)
- `_bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md:215-223` — **§4.8, the three endpoints, Role `any` / Scope `self`**; `:37-44` — the G3 403-vs-404 settlement; `:50` — pagination; `:56-66` — the error envelope; `:249-251` — per-endpoint schemas are the code's
- `_bmad-output/planning-artifacts/module-4-erd/erd.md:116-123`, `:249-257`, `:316-317`, `:381` — the `notification` table, its provenance, its relationships, **its partial index**; `:338` — TEXT + CHECK, never a PG ENUM; `:366-368` — §4.3 grants
- `_bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md:419-437` — **FR-14 in full**; `:631` — SM-4
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-07-10.md:506-510` + `:955` — **F-4: `services/cancellation` writes no Notification**; `:566` — no notification is addressed to an Admin; `:667` — Story 3.4 owns the `notification` migration
- `_bmad-output/implementation-artifacts/deferred-work.md:67`, `:74`, `:75` — **the AD-6 submit gap and the 2.12 unguarded-recompute defect** (Open Decision #1)
- `backend/app/services/leave_requests.py:300-440` (submit), `:449-558` (`_decide`), `:526-541` (the `start.year`-not-`_current_leave_year()` warning)
- `backend/app/services/rollover.py:214` (`recompute_carry_forward`, declared), `:229-238` (the three RISING call sites, named in its docstring), `:265-316` (the unguarded walk); `backend/app/services/balances.py:328-333` (`set_accrual`'s bare `ValueError`); `backend/app/domain/recalculation.py:107` (`project_forward`, pure and already serving two callers)
- `backend/alembic/versions/0008_audit_read_surface.py:79-104`, `:144-161` — the two grant shapes and the no-`ALTER DEFAULT PRIVILEGES` rule; `0011_policy_change.py` — the migration template
- `backend/tests/test_scope_matrix.py:73-128` — the registry; `backend/tests/integration/test_audit_entries.py:442-553` — **SM-4 == 14**; `backend/tests/test_vocabulary_literals.py`; `backend/tests/test_scoped_getters.py:68-154`; `backend/tests/integration/test_leave_request_submit.py:519-619` — the pinned repository surfaces
- `frontend/src/App.tsx:62-65` (the header), `:35-42` (`HealthIndicator`), `:183`/`:195` (sign-out hygiene); `frontend/src/api/calendar.ts` (the newest api-module idiom); `frontend/src/api/leaveRequests.ts:196-245` (`invalidateAfterDecision`); `frontend/src/components/Pager.tsx`; `frontend/src/index.css:96-115` (`.badge`)

---

## Dev Agent Record

### Agent Model Used

`claude-opus-4-8[1m]` (Claude Opus 4.8, 1M context) — via the `bmad-dev-story` workflow.

### Debug Log References

**🔴 The suite was RED on pickup, and it was NOT the code — it was the test database.**

This story was resumed mid-flight: Tasks 1–10 had been implemented in the working tree by an earlier
session that was interrupted before it recorded anything (every checkbox unticked, this record empty).
The first full run reported **4 failed, 539 passed, 18 errors in 664s**, with a single `test_rollover`
case taking **29 minutes** on its own.

None of it was a code defect. Diagnosis, in order:

1. `pg_stat_user_tables` showed **`leave_balance` at 311,108 rows, `employee` at 999, `leave_type` at
   223** against a seed that provisions 1 / 3 / 3. The dev database had been polluted by the
   interrupted session, whose teardowns died on the very `ForeignKeyViolation` Task 8b exists to
   prevent — leaving their rows behind.
2. `run_rollover` iterates *employees × leave types*, so 999 × 223 is precisely why one test ran for
   29 minutes: the slowness **was** the pollution, wearing a different hat.
3. **The counts were still CLIMBING between queries.** Three orphaned `pytest test_rollover` processes
   from earlier runs were still alive and still writing (`TaskStop` had killed the shell wrappers, not
   the Python children). Killed with `pkill -9`.
4. ⚠️ **A silent-failure trap worth recording:** the first `DROP SCHEMA public CASCADE` appeared to
   succeed and changed nothing, because `docker exec` **without `-i`** does not attach stdin — psql
   received no input and exited 0. The reset only actually ran once re-issued as `docker exec -i`. A
   destructive command that no-ops silently and reports success is worth checking rather than trusting.

Reset: `DROP SCHEMA public CASCADE` → recreate → restore the schema ACL byte-identically
(`leaveflow_app=U`, `=U/pg_database_owner`) → `alembic upgrade head` → `python -m seed`. `uuidv7()` is
a Postgres 18 **built-in** (`pg_catalog`) and there are no extensions, so nothing else needed restoring.

**On a clean database the same tree ran 561 passed / 0 failed in 70 seconds.** All 4 failures and all
18 errors were environmental. Recorded because the failure mode is invisible from the test output and
would cost the next reader the same hours: *a red suite here is a dirty database until proven otherwise.*

### Completion Notes List

**Tasks 1–10 (the notification slice) — verified, not merely inherited.** The code was in the tree
when this session began; every landmine was re-checked against the source rather than assumed:

- **AC1** — asserted from the live catalog: six columns, `read_at` the only nullable, both instants
  `timestamptz`, `TEXT` + `CHECK` (never a PG `ENUM`), FKs with **no `ON DELETE`**, and the index
  genuinely **PARTIAL** (`WHERE (read_at IS NULL)` — the thing `alembic check` provably cannot see,
  Landmine 7). Grants are `SELECT, INSERT, UPDATE` — **not** the append-only shape `0009`–`0011` use
  (Landmine 5); `DELETE` deliberately absent.
- **Landmine 1 (the two hooks) — the story's sharpest trap, and it is handled correctly.** Submit
  branches: managerless → **one `REQUEST_APPROVED` to the applicant themselves**, zero
  `REQUEST_SUBMITTED` (AC4); managed → one `REQUEST_SUBMITTED` to `actor.manager_id`. `_decide` takes a
  keyword-only `notify_kind: str | None = None` mirroring `recompute_carry_forward`; approve/reject
  pass a kind, **`cancel_leave_request` passes nothing**. The decide recipient is **`row.employee_id`
  (the applicant)**, never `actor.id` (the deciding Manager) — the error an AC5 test would still pass.
- **SM-4 is still exactly 14.** `insert_audit_entry` call sites: **6, byte-identical before and after**.
  A Notification is a consequence of a transition, not a transition.
- **Guard files behaved as the story predicted:** `tests/test_scoped_getters.py`'s `EXEMPT` frozenset
  is **unchanged** (the tell that the scope predicate went into the SQL), and the scope matrix gained
  exactly the one `PATCH …/read` entry.
- **AC7 — the honest limit, stated as the story demands:** there is **STILL no frontend test runner**
  (`package.json` has only dev/build/lint/preview — no vitest, no jest, no testing-library). AC7 is
  verified by `tsc -b && vite build`, `oxlint`, the `getDay`/`getUTCDay` source scan (**0 hits**), and
  code reading — **and by nothing else.** No frontend test asserts the badge renders.
- **DECLARED DEVIATION (code review 2026-07-15, accepted by the reviewer): the unread badge renders
  nothing at zero.** AC7's literal text is "an unread count is visible" for any authenticated person;
  `UnreadBadge` returns `null` when `unread === 0` (and while loading / on error) — "0 unread" in the
  header is noise, and a broken pill is worse than no pill (`frontend/src/App.tsx`). The deviation
  shipped undeclared and was caught in review; the reviewer chose to keep the behavior and declare it
  here rather than render the zero.

**📐 Task 10's test arithmetic did not close, and the story's own formula was the reason.** It predicts
`537 + new + 3 + 1`, which gives 558 against an actual **561**. The three missing cases are two
*further* auto-generated guards the formula omits. Explained, not assumed (the 3.3 standard):

| source | cases | why |
|---|---|---|
| `test_notifications.py` | +17 | the new tests |
| `test_vocabulary_literals` | +3 | parametrized per `app/**.py`; 3 new modules |
| `test_migrations_insert_nothing` | +1 | globs `alembic/versions/*.py`; `0012` is the 12th |
| **`test_scoped_getters`** | **+2** | **parametrized per getter — `get_notification`, `list_notifications`** |
| **`test_scope_matrix`** | **+1** | **parametrized per registry entry — the `PATCH …/read` entry** |
| | **537 + 24 = 561** | ✅ closes exactly |

---

**✅ TASK 11 — THE AD-6 SUBMIT GAP: ADOPTED AND CLOSED.** (Not deferred. Not the naive one-liner.)

Five stories deferred this (2.11 #8 → 2.12 #11 → 3.1 #6 → 3.2 #4 → 3.3 #7) and named 3.4 the forcing
point; 3.5 is a read-only dashboard and could not have fixed it. **The bug shipped if this story stayed
silent.** The forward-checked fix was implemented, exactly as Open Decision #1 recommends:

1. **`rollover.recompute_carry_forward` is now FORWARD-CHECKED.** It projects the whole walk with
   `domain.recalculation.project_forward` — pure, DB-free, built by 2.11 for precisely this — **before
   its first write**. On refusal it writes **no balance** and appends **one `admin_review_flag`**.
   It returns `bool` (applied / refused-and-flagged) and **never raises on an unreconcilable balance.**
2. **The submit hook** lands in `submit_leave_request` after `reserve`/`consume_direct`, with
   **`leave_year=start.year`** — *not* `_current_leave_year()`, the wrong helper that sits ~60 lines
   above in the same module (the trap `_decide` carries a standing warning about).
3. **The submission ALWAYS commits.** Refusing an Employee's leave over a carry-forward artifact in a
   *later* year would be indefensible and no error code exists for it. The balance the system cannot
   reconcile goes to an **Admin**, not to the applicant.

🚨 **Why the `deferred-work.md:67,75` one-liner was refused, concretely.** The three pre-existing call
sites all *raise* `available(Y)`, so the recompute could only ever *raise* `carried_forward` — safe by
accident. Submit is the only caller that **lowers** it, which lowers `accrued(Y+1)`, and on a `Y+1`
already spent that trips `set_accrual`'s **bare `ValueError`** (`balances.py:328`) — for which **no
handler exists** in `app/main.py` or `api/v1/errors.py`. The prescribed fix would have shipped a **new
raw 500 on the application's most-trafficked write path.** It is pinned now by
`test_ad6_a_submission_that_cannot_reconcile_is_flagged_and_still_commits`, which asserts **201 + a
flag**, and would have caught it.

**It closed a SECOND, already-shipped defect for free** (`deferred-work.md:74`, Story 2.12's known bug):
a policy-refused pair kept a stale cap, and the next *innocent* reject of an unrelated request walked
into the same unguarded `set_accrual` and **500'd the Manager** (aborting a whole `run_rollover` batch
with it). Both defects had **one root cause — this function was unguarded — so both died together.**

**Owned scope changes, stated rather than smuggled:**

- **`services/leave_requests.py` is `insert_admin_review_flag`'s THIRD writer** (2 → 3), and
  `services/rollover.py` is where the write actually lives. Legal under AD-1; called out because the
  story asked for it to be.
- **TWO new `CAUSE_*` constants, where Decision #1 named one.** `CAUSE_SUBMISSION_RECALCULATION` is the
  story's; `CAUSE_TRANSITION_RECALCULATION` is mine and is **required**: Decision #1 reasoned only about
  the submit call site, but its own step 1 ("make `recompute_carry_forward` forward-checked")
  necessarily covers **all four** callers, and stamping a *reject*-triggered refusal
  `SUBMISSION_RECALCULATION` would put a **false reason in the Admin's queue**. Both are **stored
  reasons, not error codes** — `CODE_TO_STATUS` is untouched — and `admin_review_flag.cause` is plain
  `TEXT` with **no `CHECK`**, so **neither needs a migration**.
- **`_materialized_years` MOVED** from `services/recalculation.py` to `rollover.materialized_years`, as
  the one implementation. `recalculation` already imports `rollover` (`:80`), so the reverse edge would
  have been **circular**; the projection and the write loop must agree about which years exist, and two
  copies of that walk is exactly the drift AD-6 cannot survive. `recalculation._materialized_years`
  stays as a named delegation to keep its caller-specific notes.

**Four tests changed, each because it encoded the OLD behaviour — and the story said so in advance:**

- ✅ **`test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject` → REPLACED** by
  `test_a_refused_pair_with_a_stale_cap_is_flagged_not_500`. It asserted a **raw 500** and passed
  *because the bug was real*. `deferred-work.md:74`: *"if that test ever fails, someone fixed the
  bug."* Replaced, not quietly deleted.
- ✅ **`test_an_ADD_refuses_when_carried_forward_is_STALE_HIGH`** — its docstring called the stale-high
  condition *"a PRE-EXISTING gap in Story 2.10… this test does not pretend to fix it."* Task 11 fixes
  it, so the submission now raises its own flag: **2 flags, not 1**, and their causes are asserted. On
  this deliberately pathological pair the balance still cannot be reconciled — Task 11 never claimed it
  could — but the condition is **no longer silent**.
- ✅ **`test_the_forward_check_is_what_refuses_not_the_constraint`** — it blinds `project_forward` to
  prove the check is load-bearing. There are now **two** checks, so **both** must be blinded to reach
  the backstop. The original claim is preserved exactly; that it takes two lobotomies instead of one is
  defence in depth, not a weakened test.
- ✅ **`test_the_explicit_recomputation_is_a_no_op`** — direct call, given the new `cause`/`occurred_at`.

**Two new tests** pin Task 11's mandate: `test_ad6_a_submission_after_the_rollover_re_derives_carry_forward`
(the fix — `carried_forward(Y+1)` now falls 20 → 17 on submit, where it used to stay a stale 20 forever)
and the refusal-path test above. `test_rollover.py`'s teardown gained an `AdminReviewFlag` delete —
this story made that table reachable from that world, and its NOT NULL FKs would otherwise take the
module red on cleanup (Landmine 16, again).

**Final verification (clean DB):** **563 passed, 0 failed** (561 + 2 new; the canary was replaced 1:1).
`import-linter` **7 kept / 0 broken**, `pyproject.toml` **not in the diff**. `alembic check` clean;
migration **down → up** round-trips and restores the partial index. `python -m seed` exit **0**.
Frontend `tsc -b && vite build` ✅ and `oxlint` ✅ (0 warnings). **`insert_audit_entry` call sites: still
exactly 6 — SM-4 is undisturbed.**

### File List

**New — the notification slice (Tasks 1–9)**
- `backend/alembic/versions/0012_notification.py`
- `backend/app/repositories/notification.py`
- `backend/app/services/notifications.py`
- `backend/app/api/v1/notifications.py`
- `backend/tests/integration/test_notifications.py`
- `frontend/src/api/notifications.ts`
- `frontend/src/features/notifications/NotificationsPanel.tsx`

**Modified — the notification slice**
- `backend/app/domain/vocabulary.py` — 3 notification kinds (+ 2 `CAUSE_*`, Task 11); all in `__all__`
- `backend/app/repositories/models.py` — `Notification`, incl. the partial `Index`
- `backend/app/api/v1/router.py` — import + `include_router` (the 2 lines)
- `backend/app/services/leave_requests.py` — submit hook (AC2/AC4), `_decide`'s `notify_kind` (AC3)
- `backend/tests/test_scope_matrix.py` — the one `PATCH …/read` entry
- `backend/tests/test_migrations_insert_nothing.py` — `0012` appended to the chain
- `backend/tests/integration/test_migration_smoke.py` — `HEAD_REVISION = "0012_notification"`
- `backend/tests/integration/test_schema_1_2.py` — `notification` in the expected-tables set
- `frontend/src/App.tsx` — the unread badge (no role gate) + sign-out hygiene at **both** sites
- `frontend/src/api/index.ts` — barrel exports
- `frontend/src/api/leaveRequests.ts` — `NOTIFICATIONS_QUERY_KEY` on submit **only** (never on decide)

**Modified — Task 8b, the eight teardowns (this story created the breakage; this story fixed it)**
- `backend/tests/integration/test_leave_request_submit.py`, `test_leave_request_decide.py`,
  `test_audit_entries.py`, `test_cancellation_request.py`, `test_leave_request_history.py`,
  `test_rollover.py`, `test_policy_change.py`, `test_holiday_recalculation.py`

**Modified — Task 11 (the AD-6 fix; independently revertable)**
- `backend/app/services/rollover.py` — the forward check + `materialized_years` (the one walk)
- `backend/app/services/recalculation.py` — delegates the walk; passes `cause`/`occurred_at`
- `backend/app/services/cancellation.py` — passes `cause`/`occurred_at`
- `backend/app/services/leave_requests.py` — **the submit-side recompute** (`leave_year=start.year`)
- `backend/tests/integration/test_rollover.py` — 2 new AD-6 tests, `_flags` helper, flag teardown
- `backend/tests/integration/test_policy_change.py` — the 2.12 canary **replaced**
- `backend/tests/integration/test_holiday_recalculation.py` — 2 tests updated to the fixed behaviour

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-14 | **Story resumed mid-flight.** Tasks 1–10 were present in the working tree from an interrupted session that recorded nothing (all checkboxes unticked, Dev Agent Record empty). Implementation verified against every AC and landmine rather than assumed. |
| 2026-07-14 | **Test database reset.** The suite was red (4 failed / 18 errors / 664s) purely from DB pollution left by the interrupted session's failed teardowns — `leave_balance` held 311k rows, and three orphaned `pytest` processes were still writing. After `DROP SCHEMA public CASCADE` → migrate → seed, the *same tree* ran **561 passed / 0 failed in 70s**. No code defect was involved. |
| 2026-07-14 | **Tasks 1–10 complete.** `notification` table + partial index (AC1), addressee-scoped reads (AC5), idempotent mark-read (AC6), both transition hooks (AC2/AC3/AC4), the eight teardown repairs (Task 8b), and the React badge + panel (AC7). SM-4 undisturbed at 6 `insert_audit_entry` call sites. |
| 2026-07-14 | **Task 10's test arithmetic corrected.** The story's formula (`537 + new + 3 + 1`) omitted two auto-generated guards — `test_scoped_getters` (+2, parametrized per getter) and `test_scope_matrix` (+1, per registry entry). With them the count closes exactly: **537 + 24 = 561.** |
| 2026-07-14 | **Task 11 — the AD-6 submit gap: ADOPTED, not deferred.** `rollover.recompute_carry_forward` is now forward-checked via `project_forward`; on refusal it writes no balance and raises an `admin_review_flag`. The submit-side recompute is wired in with `leave_year=start.year`, and **the submission always commits**. The naive `deferred-work.md:67,75` one-liner was refused: it would have shipped a new raw 500 on the submit path. |
| 2026-07-14 | **Task 11 closed Story 2.12's shipped defect for free** (`deferred-work.md:74`) — a stale cap on a refused pair no longer 500s an innocent third party's reject. Both defects had one root cause: an unguarded recompute. The 2.12 canary test is **replaced**, as `deferred-work.md` said it should be. |
| 2026-07-14 | **Final:** 563 passed / 0 failed; import-linter 7/7; `alembic check` clean; migration down→up round-trips; seed exit 0; frontend build + oxlint clean. Status → **review**. |
