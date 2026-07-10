---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - "_bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md"
  - "_bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/addendum.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md"
  - "_bmad-output/planning-artifacts/module-4-erd/erd.md"
  - "_bmad-output/planning-artifacts/module-1-business-analysis/brd.md"
  - "_bmad-output/planning-artifacts/module-1-business-analysis/functional-requirements.md"
  - "_bmad-output/planning-artifacts/module-1-business-analysis/non-functional-requirements.md"
  - "_bmad-output/planning-artifacts/module-1-business-analysis/assumptions-and-constraints.md"
---

# LeaveFlow - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for LeaveFlow, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

**No UX Design Specification exists for this project.** Confirmed with the product owner on 2026-07-10: the workflow proceeds without one. The PRD carries testable UI consequences directly (`FR-11`, `FR-18`, `NFR-16`, `NFR-17`, `NFR-18`), and the Architecture Spine explicitly defers "React state shape below the page level, styling, and component library" as out of scope. The **UX Design Requirements** section below is therefore intentionally empty rather than omitted.

**Identifier discipline.** `FR-01`–`FR-20`, `NFR-01`–`NFR-21`, `DR-1`–`DR-16`, `BR-01`–`BR-06`, `D-01`–`D-07`, `AD-1`–`AD-22`, and `SM-1`–`SM-9` are carried verbatim from their source documents. PRD addendum §1.3 fixed this deliberately: stable identifiers across the artifact chain outweigh numeric contiguity within any one document. Numeric order is not reading order — `FR-17` belongs to Organization Administration, `FR-12` to Visibility.

## Requirements Inventory

### Functional Requirements

Twenty requirements. `FR-01`–`FR-16` come from the assignment specification's enumerated list. `FR-17` and `FR-18` were derived in Module 1 from permissions the specification grants in its role definitions. `FR-19` and `FR-20` were added by the PRD to cover two further granted permissions Module 1 never enumerated.

**FR-01: User Authentication.** An Employee exchanges credentials — their Email Address and the initial password an Admin supplied when creating them (`FR-04`) — for an authenticated session. LeaveFlow offers no other way to establish a password, and no way to change one. A failed authentication does not disclose whether the account exists: the response to an unknown identity and to a wrong password are byte-identical in body and equal in status code. No stored representation of a password permits its recovery.

**FR-02: JWT-Based Authorization.** The system carries the authenticated session as a JSON Web Token presented on each request. A request with no token, an expired token, or a token whose signature does not verify is rejected — including one whose payload was altered to change the subject or role.

**FR-03: Role-Based Access Control.** Each Employee holds exactly one role — Employee, Manager, or Admin — and every Manager action is scoped to that Manager's Direct Reports. A Manager reaching a non-report's Leave Request receives the same response as for a nonexistent request. An Admin reads every Leave Request and decides none. Authorization is enforced at the API boundary: a client that does not render a control cannot invoke it by calling the endpoint directly.

**FR-04: Employee Management.** An Admin creates, reads, updates, and deactivates Employee records, including each Employee's Department, role, joining date, and Manager. Creating an Employee requires the Admin to supply that Employee's initial password, which is hashed before persistence and never returned in any response; updating an Employee accepts no password, and no re-issue path exists. The Admin communicates the initial password outside LeaveFlow, which sends no email. An Employee is never physically deleted. Deactivation is refused while that Employee holds any Pending Leave Request, and refused while any active Employee names them as Manager. A deactivated Employee cannot authenticate. Assigning a Manager establishes the Direct Report relationship `FR-03` enforces.

**FR-05: Department Management.** An Admin creates, reads, updates, and removes Departments. A Department with at least one assigned Employee cannot be removed; the refusal names the obstruction.

**FR-06: Leave Type Management.** An Admin configures Leave Types and their four attributes — Annual Entitlement, carries-forward, Carry-Forward Cap, requires-supporting-document — all stored as data. EL, CL and FL exist at initialization, seeded with requires-supporting-document **false**. No cap value and no entitlement value is fixed in code. When a policy change would affect existing Leave Balances, the system requires the Admin to choose explicitly between recalculating under the new policy and preserving balances as accrued under the old one; the change cannot be applied without that choice being made and recorded. A chosen recalculation obeys `FR-10`'s non-negativity guard and is refused per affected Employee and Leave Type, recorded in the same durable store `FR-10` writes. Creating a fourth Leave Type through configuration alone yields a type that can be applied for, reserved against, approved, and rolled over — with no code change and no schema migration.

**FR-07: Leave Balance Tracking.** For each Employee, Leave Type, and Leave Year the system maintains Accrued, Reserved, and Consumed, and derives Available. `Available = Accrued − Consumed − Reserved` holds after every state transition of every Leave Request, and no sequence of transitions produces a negative Available. A mid-year joiner receives a Prorated Accrued balance: `Annual Entitlement × (remaining months ÷ 12)`, counting the joining month through December inclusive, rounded **down** to a whole Leave Day. At the Leave Year boundary, unused Accrued days of a carrying-forward Leave Type carry forward up to its Carry-Forward Cap; the excess, and the unused Accrued days of non-carrying-forward types, lapse. The rollover is invoked by a system-triggered scheduled process, not a user action, and records its execution in a separate append-only rollover log rather than among Audit Entries, because it transitions no Leave Request. An Employee viewing their balance sees Available as the primary figure, with Reserved disclosed alongside it.

**FR-08: Leave Request Workflow.** An Employee submits a Leave Request for a Leave Type over a contiguous date range, which the system prices in Leave Days and admits as Pending. The Leave Day count equals the number of Working Days in the range — weekend days and Company Holidays are excluded. A request whose Leave Day count exceeds the applicant's Available balance is refused, and the refusal states the days requested and the days available. A request spanning two Leave Years is refused. On admission the Leave Days are Reserved and Available falls immediately. Two concurrent submissions that would together exceed Available cannot both succeed. A request whose Leave Day count is zero, whose end date precedes its start date, or whose range lies wholly in the past, is refused as invalid. A request from an Employee with no Manager is admitted directly as Approved, consuming its Leave Days without a reservation stage; the Available check still applies.

**FR-09: Approval and Rejection.** The Manager of a Leave Request's applicant can approve or reject it while it is Pending. Approval moves Reserved days to Consumed; rejection and cancellation of a Pending request release them. Only the applicant may cancel their own Pending request. Only the applicant may raise a Cancellation Request against their own Approved request, and only an Admin may approve or reject it; the Leave Request remains Approved and its days remain Consumed throughout that decision. An approved Cancellation Request moves the Leave Request to Cancelled and releases its Consumed days; a rejected one changes nothing. An Approved Leave Request whose dates have already passed cannot be cancelled. Authority is evaluated at decision time, so where an applicant's Manager changes while their request is Pending, the current Manager decides it. A managerless Employee's request is Approved on submission, with the Audit Entry naming actor `SYSTEM` and reason `AUTO_APPROVED_NO_MANAGER`. Every transition writes exactly one Audit Entry. When two conflicting transitions race, the first to commit succeeds and the second fails.

**FR-10: Holiday Management.** An Admin maintains the Company Holiday calendar. A Company Holiday is a date and a name, global to the organization, scoped to no Department or location. A holiday date is not a Working Day and is therefore not counted as a Leave Day. Adding or deleting a Company Holiday inside the range of a Pending Leave Request recalculates that request's Leave Day count and its Reserved days; inside the range of an Approved Leave Request whose dates are still in the future, it recalculates the count and the applicant's Leave Balance. An Approved Leave Request whose dates have already passed is **not** recalculated. A recalculation never produces a negative Available balance in the recalculated Leave Year or any later one; where it would, it is refused for that Employee and Leave Type — whose requests and balances are left unchanged — the case is recorded in a durable store the Admin can read, and the remainder of the operation proceeds. Only an Admin can read those recorded cases.

**FR-11: Dashboard.** Each role sees a dashboard scoped to what that role can act on. The Employee dashboard presents, per Leave Type, Available, Reserved and Consumed, plus a count of Pending requests. The Manager dashboard presents a count of Leave Requests awaiting their decision, and their Direct Reports on approved leave within the next seven days. The Admin dashboard presents organization-wide totals: Employees on approved leave today, and Pending request count. Every dashboard supports a date-range filter. A Manager requesting the Employee dashboard sees their own balances, not their reports'; an Employee requesting the Manager dashboard is refused.

**FR-12: Search, Filtering, and Pagination.** Every list endpoint enforces a maximum page size on the server; a client requesting a larger page receives the maximum, not the larger page. Filters compose: Leave Type, state, and date range can be applied together. Filtering never widens authorization — a Manager filtering across all Departments sees only their Direct Reports.

**FR-13: Supporting Document Upload.** An Employee attaches a Supporting Document to a Leave Request whose Leave Type requires one. Such a request cannot be submitted without one. Uploads are validated before storage: permitted types are PDF, JPG/JPEG and PNG, and the maximum size is 5 MB per file. A Supporting Document is retrievable only by the applicant, the applicant's Manager, and the Admin. Documents are stored outside the web root, and a client-supplied filename is never used as a storage path.

**FR-14: In-App Notifications.** Submission of a Leave Request creates exactly one Notification addressed to the applicant's Manager. Approval or rejection creates exactly one Notification addressed to the applicant. A Notification is readable only by its addressee. An unread count is retrievable, and reading a Notification decrements it. An addressee can mark a Notification read; marking read is idempotent, and only the addressee may do it.

**FR-15: Reports and Export.** A Manager exports a leave report for their Direct Reports; an Admin exports one organization-wide. Export format is CSV. The exported rows are exactly the rows matching the applied filters — the filter set applied to the view is applied to the export.

**FR-16: Audit Logs.** The system records every Leave Request state transition as an Audit Entry naming the Leave Request, the transition, the actor, and the timestamp. Where a transition was caused by the system rather than a person, the actor is `SYSTEM` together with an explicit reason; no human approver is fabricated. Audit Entries are append-only — no application code path updates or deletes one. Full read access to the audit log is restricted to the Admin. The number of Audit Entries for a Leave Request equals the number of state transitions it has undergone.

**FR-17: Personal Profile Management.** An Employee updates their own profile and no other Employee's. The only editable field is their Full Name. Role, Department, Manager, joining date, Email Address, and any Leave Balance quantity are not editable by their owner; an attempt to alter them through the profile endpoint is refused. The Email Address is maintained by the Admin under `FR-04`.

**FR-18: Department Leave Calendar.** A Manager views their Direct Reports' leave across a date range. The calendar shows Approved and Pending leave, visually distinguished from one another, and shows only the viewing Manager's Direct Reports. It is presented on the approval screen for the dates of the Leave Request under decision, so that overlap is visible at the moment of decision. It never prevents an approval: overlapping leave produces no warning, no block, and no required acknowledgement.

**FR-19: Team Member List.** A Manager views the Employees who report to them. The list contains exactly the viewing Manager's Direct Reports and no other Employee. Each entry identifies the Employee and their Department. A deactivated Direct Report is distinguishable from an active one.

**FR-20: Leave History.** An Employee views their own Leave Requests across Leave Years. The history contains every Leave Request the Employee has submitted, in every state, including Cancelled and Rejected. Each entry shows the Leave Type, the date range, the Leave Day count, and the current state. An Employee sees only their own history; a Manager sees a Direct Report's; an Admin sees any Employee's.

### NonFunctional Requirements

Twenty-one requirements, carried from the Module 1 NFR register. **A standing risk, recorded in PRD §8:** all twenty-one are engineer-proposed. None has been confirmed by the assigning manager. `NFR-03`, `NFR-04`, `NFR-07` and `NFR-08` are the four the PRD and Architecture fund most heavily, on the judgment that they are the ones a technical discussion would probe.

**Security**

**NFR-01:** Credentials are stored as salted hashes using a deliberately slow algorithm (bcrypt or Argon2). Plaintext and reversible encryption are prohibited.
**NFR-02:** Access tokens expire, with a lifetime measured in hours rather than days, absent a refresh mechanism.
**NFR-03:** Authorization is enforced server-side, at the API boundary, independently of the frontend. Hiding a control in the frontend is not access control.
**NFR-04:** Data scoping is applied in the query, where data is fetched — never by filtering results after retrieval.
**NFR-05:** Uploaded documents are validated for type and size, stored outside the web root, and served only to authorized callers. Client-supplied filenames are never trusted as paths.
**NFR-06:** Credentials and tokens travel over TLS in any deployed environment.

**Correctness and reliability**

**NFR-07:** Reserve, consume and release occur within a transaction. A concurrent double submission produces neither a negative nor a double-counted balance.
**NFR-08:** The leave-day calculation is a single, pure, directly unit-tested function called by every path that touches a balance. A second implementation of weekend-and-holiday logic anywhere in the codebase is a defect.
**NFR-09:** Audit Entries are append-only. No application code path updates or deletes one.

**Performance**

**NFR-10:** Typical read endpoints respond within roughly 500 ms at this project's data scale. An order of magnitude, not a contractual figure.
**NFR-11:** No endpoint returns an unbounded collection. Pagination has a maximum page size enforced server-side, regardless of what the client requests.
**NFR-12:** Indexed access paths exist for employee, manager, department, leave year, and request status.

**Maintainability and operability**

**NFR-13:** Route handlers, business logic and data access are separated. Leave policy rules live in the service layer, not in route handlers and not in the database.
**NFR-14:** Leave Type behaviour — carry-forward, lapse, document requirement, entitlement, cap — is data the Admin configures. Adding a Leave Type requires no code change.
**NFR-15:** The hard rules carry tests: proration, carry-forward, the Leave Year boundary, the weekend-and-holiday day count, and the authorization scope. Coverage of CRUD scaffolding matters less.
**NFR-20:** Secrets, database credentials, and token signing keys come from the environment. None are committed.
**NFR-21:** The project starts from a documented command sequence on a clean machine.

**Usability**

**NFR-16:** A control a role cannot successfully invoke is not rendered for that role. This is a usability measure, not a security measure; `NFR-03` is the security measure.
**NFR-17:** Errors state the reason. "Insufficient balance" names days requested and days available; "spans two leave years" names the boundary.
**NFR-18:** Layout is responsive across common desktop and tablet widths.

**Auditability**

**NFR-19:** Every leave state transition records who caused it and when. An approved request traces to the Manager who approved it.

**Explicitly not required** (recorded so their absence reads as a decision): high availability, horizontal scalability, multi-tenancy, internationalization, formal WCAG conformance, rate limiting, disaster recovery and backup policy, penetration testing, and performance under concurrent load beyond a handful of users.

### Additional Requirements

Technical requirements from the Architecture Spine (`AD-1`–`AD-22`), the solution architecture, the API contracts, and the Module 4 ERD, that constrain how stories are written and sequenced.

#### 🚨 Starter template — there is NO starter template. The skeleton is hand-rolled.

**This is a decision, not an omission, and it directly shapes Epic 1 Story 1.** The Architecture Spine's *Structural Seed* section considered `fastapi/full-stack-fastapi-template` — current, actively maintained, matching the stack almost exactly — and **rejected it on one specific ground**: the template ships **SQLModel**, in which one class serves as both the Pydantic API schema and the SQLAlchemy table. That fusion is precisely the coupling `AD-1` forbids, and it dissolves the structural guarantee `DR-2` depends on. The template also ships email-based password recovery, which PRD §6 excludes as a non-goal.

Its `docker-compose` and Alembic wiring are used **as reference only**. Epic 1 Story 1 must therefore scaffold the four-package source tree by hand, not run a template generator.

#### Architecture invariants (`AD-1`–`AD-22`)

- **`AD-1`** — Imports flow `api → services → {repositories, domain}` and `repositories → domain`. `domain/` imports no ORM, no web framework, and performs no I/O. `api/` never imports `repositories/` or `domain/`. `repositories/` never imports `services/`. Any function that computes a leave quantity lives in `domain/`.
- **`AD-2`** — One function, `domain.calendar.count_leave_days`, is the only code that knows what a weekend or a Company Holiday is. The client obtains every day count from the preview endpoint, which returns the count, each excluded date with its reason and the holiday's name, and the projected Available balance. No frontend module references a weekday or a holiday.
- **`AD-3`** — Transactions run at READ COMMITTED. Exactly one transaction per command, opened in `services/`. A command writing any `leave_balance` quantity first acquires that row with `SELECT ... FOR UPDATE`, and **the Available value that decides admission is computed from the row read under that lock, in that transaction** — a value returned earlier by the preview endpoint is never load-bearing. Balance rows lock in ascending `(employee_id, leave_type_id, leave_year)`, and always before request rows.
- **`AD-4`** — Every transition is a single `UPDATE ... SET status = :to WHERE id = :id AND status = :from`. Zero affected rows means the transition is refused and the transaction rolls back. This *is* `FR-09`'s first-committed-wins.
- **`AD-5`** — `leave_balance` carries `CHECK (accrued - consumed - reserved >= 0)`, `CHECK (reserved >= 0 AND consumed >= 0)`, `CHECK (accrued = prorated_entitlement + carried_forward)`, and `UNIQUE (employee_id, leave_type_id, leave_year)`. `available` is never a column. These constraints are a **backstop, never a gate**: a CHECK violation reaching a client is a defect and a 500, never a refusal.
- **`AD-6`** — `carried_forward(Y+1) = min(leave_type.carry_forward_cap, available(Y))`, written by assignment, never by increment. Recomputed on every event that can change its inputs, including a change to `carry_forward_cap` or `annual_entitlement` — which is not a balance change and must be wired as an explicit trigger. The rollover is idempotent by construction.
- **`AD-7`** — The rollover is a CLI entrypoint, `python -m app.jobs.rollover --year YYYY`, invoked by an external scheduler. No scheduler is registered inside the FastAPI application. The job is directly callable from a test with no running server and no clock manipulation.
- **`AD-8`** — `audit_entry` holds exactly one row per state transition of a Leave Request or a Cancellation Request, and nothing else. Columns: `subject_type`, `subject_id`, `from_state`, `to_state`, `actor_type`, `actor_id`, `reason`, `occurred_at`. `actor_id` is a nullable FK to `employee`, NULL if and only if `actor_type` is `SYSTEM`. The audit row is inserted inside the same transaction as the transition it records. The rollover writes to `rollover_run`.
- **`AD-9`** — The application's database role is granted `INSERT` and `SELECT` on `audit_entry` and `rollover_run`, and **neither `UPDATE` nor `DELETE`**. Alembic migrations run under the owner role. No repository exposes an update or delete method for either table.
- **`AD-10`** — No repository exposes an unscoped getter. Every read that could return another Employee's data takes the actor and applies the scope as a predicate *in the SQL*. A resource outside the actor's scope returns **404**, byte-identical to a nonexistent resource; **403** is reserved for a resource the actor may see but not act upon. A Manager's scope is `employee.manager_id = :actor_id`, evaluated at request time.
- **`AD-11`** — `leave_type` is a table row: never a Python `Enum`, never a PostgreSQL `ENUM`, and no branch anywhere tests a Leave Type by name or code. Its three seed rows are inserted by a **seed command, never by a migration**. Conversely `leave_request.status` and `cancellation_request.status` are `TEXT` constrained by `CHECK`.
- **`AD-12`** — Leave dates, Company Holiday dates and the Leave Year boundary are PostgreSQL `DATE` and Python `datetime.date`. Audit and notification instants are `TIMESTAMPTZ`. No leave date is ever stored, compared, or transported as a timestamp. The API transports leave dates as `YYYY-MM-DD`.
- **`AD-13`** — `cancellation_request` is its own table with its own Pending/Approved/Rejected lifecycle, decided by an Admin, targeting exactly one Approved Leave Request. Both objects' transitions write to `audit_entry`.
- **`AD-14`** — The JWT travels as `Authorization: Bearer` and carries an `exp` claim in hours. Every restricted operation is checked in an `api/` dependency against the database. Passwords are hashed with bcrypt or Argon2 via **`pwdlib`** — `passlib` is not used, being unmaintained since 2020 and broken against bcrypt 5. JWTs use **`PyJWT`** — `python-jose` is not used, on the strength of CVE-2024-33663.
- **`AD-15`** — A document is written to a volume outside the web root under a **server-generated UUID name**. The client-supplied filename is persisted as a data column and never used as a path component. Documents are served only by an authorized streaming endpoint that re-applies `AD-10`'s scope; no static route maps to the volume. Type and size are validated **before any bytes are written**.
- **`AD-16`** — A notification carries a recipient, a `kind` discriminator, the Leave Request it concerns, a nullable `read_at`, and `created_at`. The unread count is `COUNT(*) WHERE read_at IS NULL` and is never stored. The service that performs a transition writes its Notification inside that transition's transaction; no other service writes notifications. Mark-read is an idempotent `PATCH`, permitted only to its addressee.
- **`AD-17`** — Exactly one module mutates a `leave_balance` quantity, exposing exactly: `reserve`, `consume_reserved`, `consume_direct`, `release_reserved`, `release_consumed`, `adjust_reserved`, `adjust_consumed`, `set_accrual`. `consume_direct` is `FR-09`'s managerless auto-approval and never touches `reserved`. `release_consumed` is `BR-05`'s approved-cancellation path. `set_accrual` writes `accrued`, `prorated_entitlement` and `carried_forward` in one statement. No route, repository, job, or other service writes these columns.
- **`AD-18`** — `leave_request.leave_days` is computed once at admission and stored. Every read path — history, dashboard, calendar, export — reads the stored value and never recomputes it. Only `AD-19`'s recalculation may change it, and only for a Pending request or an Approved request whose dates lie wholly in the future.
- **`AD-19`** — A holiday add/delete, and a Leave Type `annual_entitlement`/`carry_forward_cap` change under disposition `RECALCULATE`, both re-derive the affected `leave_days`, balance quantities, and `carried_forward` in every materialized later year. Within the same transaction, independently for each affected Employee **and Leave Type**, the operation verifies that no year's Available becomes negative. Where it would, that pair is left **entirely unchanged**, a row is written under `AD-20`, and the remainder of the operation proceeds.
- **`AD-20`** — `admin_review_flag` records every refusal `AD-19` produces, with its cause and its subject. It is the only such store, is **read-only to the Admin**, and no other role reads it. `policy_change` records every Leave Type attribute change with the Admin's explicit disposition — `RECALCULATE` or `PRESERVE` — which `FR-06` requires be chosen and recorded before the change is applied. It carries **no actor, by decision**. Neither table is `audit_entry`.
- **`AD-21`** — Every enumerated string — Leave Request and Cancellation Request `status`, `subject_type`, `actor_type`, notification `kind`, error `code` — is `UPPER_SNAKE_CASE`, declared exactly once as a constant in `domain/`, and appears as a literal nowhere else. Leave Request statuses are `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`. Actor types are `EMPLOYEE` and `SYSTEM`.
- **`AD-22`** — An Employee is never deleted, only deactivated. Deactivation is refused while that Employee has any Pending Leave Request, and refused while any active Employee names them as Manager. **Amended 2026-07-10 (`G8`): the same Direct-Report guard refuses any update that lowers an Employee's `role` below `MANAGER` while an active Employee still names them as Manager.** Deactivation and demotion are the two doors to the same orphaning; both are now closed. `FR-09`'s auto-approval is reachable only for an Employee whose `manager_id` is NULL — a state this rule prevents either door from ever creating.
- **`AD-23`** *(added 2026-07-10, `G7`)* — The reporting graph is acyclic. `employee` carries `CHECK (id <> manager_id)` as a backstop, and the employee service refuses any manager assignment that would close a cycle — directly or transitively — with `400 REPORTING_CYCLE`. Per `AD-5`'s principle the service is the gate and the constraint is the backstop. Without this, an Employee who is their own Manager approves their own Leave Requests: `FR-09` grants approval to "the Manager of the applicant" and `DR-12` derives that authority from the relationship rather than the role, so the check passes and `SM-3` still reports green.

#### Infrastructure, deployment, and setup

- One Docker Compose deployment = one organization. Services: `proxy` (TLS termination), `web` (static React bundle), `api` (FastAPI + uvicorn), `postgres:18`, a documents volume outside the web root, and a `scheduler` (cron).
- **No organization, tenant, or company column exists on any table.** A second organization is a second deployment with its own database. Deliberate, and expensive to reverse.
- Reproducible setup (`NFR-21`) is three commands: `docker compose up`, then `alembic upgrade head`, then the seed command.
- Two environments only: local development and one deployed environment.
- Source tree: `backend/app/{api/v1,services,repositories,domain,jobs,core}`, `backend/alembic/` (schema only, never seeds a Leave Type), `backend/seed/` (inserts EL, CL, FL as data), `backend/tests/{domain,integration}`, and `frontend/src/{api,features,components}`.
- Configuration via `pydantic-settings`, read from the environment. `.env` is never committed; `.env.example` is (`NFR-20`).
- Observability: structured JSON logs to stdout, and a `GET /health` endpoint the deployment probes. Metrics and error monitoring are deferred.

#### Pinned stack (verified against PyPI, npm, and official release pages on 2026-07-10)

Python 3.13 · FastAPI 0.139.0 · Pydantic 2.13.4 · SQLAlchemy 2.0.51 · Alembic 1.18.5 · psycopg 3.3.4 · PostgreSQL 18 · PyJWT 2.13.0 · pwdlib 0.3.0 · bcrypt 5.0.0 · pytest 9.1.1 · React 19.2.7 · Vite 8.1.4 · TypeScript 6.0.3 · TanStack Query 5.101.2.

Three pins are **deliberately behind** the newest release and must not be "helpfully" upgraded: SQLAlchemy holds at the 2.0 line because 2.1 is beta; TypeScript holds at 6.0.3 rather than 7.0.2 (the Go rewrite, which shipped two days before the spine was written); Python holds at 3.13 rather than 3.14 for library compatibility. A three-day implementation budget cannot absorb a toolchain surprise.

#### API contract requirements

- Base path `/api/v1`. Paths plural and kebab-case. Dates `YYYY-MM-DD`; instants RFC 3339 UTC; never interchanged.
- The FastAPI-generated OpenAPI document is the **runtime source of truth** for per-endpoint request/response schemas. `api-contracts.md` fixes only what the generated schema cannot express: the resource surface, per-endpoint scope, status-code semantics, the error vocabulary, and the pagination contract.
- Status codes carry meaning: `400` domain refusal (body names why, with numbers) · `401` no valid token · `403` **denied by role grant**, or may see but may not act · `404` does not exist **or** lies outside scope, byte-identical · `409` state conflict.
- **`403` vs `404`, settled (`G3`, 2026-07-10).** The distinguishing test is *does the actor's role admit them to this endpoint at all?* If no → `403 ACTION_NOT_PERMITTED`, decided before any row is read. If yes → the scope predicate runs, and a miss is `404`. `AD-10`'s `404` therefore still means exactly one thing: *outside your scope*. See api-contracts §1.
- Error envelope: `{ code, message, details }`. `code` is machine-readable and declared once in `domain/`. `details` carries the numbers a refusal must state.
- Error vocabulary (**twenty codes** after the `G2`/`G3`/`G5`/`G7` amendments of 2026-07-10): `AUTH_FAILED`, `TOKEN_INVALID`, `ACTION_NOT_PERMITTED`, `FORBIDDEN_FIELD`, `EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE`, `INSUFFICIENT_BALANCE`, `ZERO_LEAVE_DAYS`, `SPANS_TWO_LEAVE_YEARS`, `INVALID_DATE_RANGE`, `PAST_DATE_RANGE`, `SUPPORTING_DOCUMENT_REQUIRED`, `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`, `LEAVE_ALREADY_TAKEN`, `POLICY_DISPOSITION_REQUIRED`, `DEPARTMENT_NOT_EMPTY`, `EMPLOYEE_HAS_PENDING_REQUESTS`, `EMPLOYEE_HAS_DIRECT_REPORTS`, `TRANSITION_NOT_ALLOWED`.
- **`ACTION_NOT_PERMITTED` closes a latent hole:** api-contracts §2 previously declared sixteen codes and **none of them was a `403`**, while Stories 1.5 and 2.7 already asserted `403` responses and §2 requires every non-2xx body to carry the envelope.
- Pagination: list endpoints accept `page` and `page_size`; responses carry `items`, `page`, `page_size`, `total`.
- `POST /leave-requests/preview` is the **only** way a client obtains a day count. Its returned value is **advisory only**; admission is decided against the balance row read under lock at submission time.
- **The Leave Year rollover has no endpoint.** It is a CLI job invoked by an external scheduler.

#### Data model requirements (Module 4 ERD)

- Entities: `department`, `employee`, `leave_type`, `company_holiday`, `leave_balance`, `leave_request`, `cancellation_request`, `supporting_document`, `notification`, `audit_entry`, `rollover_run`, `admin_review_flag`, `policy_change`.
- Primary keys are `UUID DEFAULT uuidv7()` — native in PostgreSQL 18, no extension. Time-ordered (so creation order comes free) and non-enumerable (which keeps `AD-10`'s 404 honest).
- Leave quantities are `INTEGER` everywhere. Never `NUMERIC`, never float.
- Enumerated strings are `TEXT` + `CHECK`, never a PostgreSQL `ENUM`.
- `leave_request` has **no `created_at`** — creation is itself a transition, recorded in `audit_entry`, and ordering comes from the UUIDv7 key. It has **no `leave_year` column** — `DR-6` forbids spanning two Leave Years, so the year of `start_date` is the request's Leave Year, and storing it would create a second source of truth.
- `cancellation_request` has **no requester column** (only the applicant may raise one) and **no decider column** (the deciding Admin is the actor on its `audit_entry` transition).
- `supporting_document` has **no `size_bytes`** — size is validated before bytes are written and no requirement reads it afterwards.
- Additional constraints: `employee UNIQUE (email)`; `employee CHECK (role IN ('EMPLOYEE','MANAGER','ADMIN'))`; **`employee CHECK (id <> manager_id)`** *(added 2026-07-10, `AD-23`/`G7` — a backstop for the self-reference; the transitive cycle gate is the employee service)*; `leave_request CHECK (end_date >= start_date)` and `CHECK (leave_days > 0)`; `audit_entry CHECK ((actor_type = 'SYSTEM') = (actor_id IS NULL))`; `company_holiday UNIQUE (holiday_date)`; `leave_type UNIQUE (code)`; `supporting_document UNIQUE (leave_request_id)`; `policy_change CHECK (disposition IN ('RECALCULATE','PRESERVE'))`.
- Indexes serving `NFR-12`: `employee(manager_id)`, `employee(department_id)`, `leave_balance(employee_id, leave_type_id, leave_year)`, `leave_request(employee_id, status)`, `leave_request(start_date, end_date)`, `notification(recipient_employee_id) WHERE read_at IS NULL`, `audit_entry(subject_type, subject_id)`.
- A deactivated Employee's row and email persist indefinitely, so **an email address is never reusable**. `FR-01`'s byte-identical failure response must not leak through lookup timing either — the hash comparison must run regardless of whether the email exists.
- A Leave Request may not span two Leave Years. Enforced in `domain/`, **not** by a `CHECK`, because the refusal must carry the boundary date in its message (`NFR-17`).

#### Testing and traceability requirements

- `tests/domain/` runs with **no database fixture** (`SM-2`, `NFR-15`). `tests/integration/` runs against real PostgreSQL and owns `SM-1`'s concurrent double-submit test.
- Every module names in its docstring the FR or DR it implements (`SM-6`).
- `SM-8` counts a requirement as delivered only when a consequence from its FR is **demonstrably exercised by a passing test** — not when its endpoint exists.

#### Scope, budget, and phasing constraints

- The implementation budget is **three days** (Days 3–5 of a seven-day plan). Days 1, 2, 6 and 7 produce artifacts.
- PRD §7 fixes a build order and a depth allocation, not a set of deletions:
  - **Phase 1 (the correctness core):** `FR-01`, `FR-02`, `FR-03`, `FR-04`, `FR-05`, `FR-17`, `FR-06`, `FR-10`, `FR-07`, `FR-08`, `FR-09`, `FR-16`.
  - **Phase 2 (the product becomes usable):** `FR-11`, `FR-18`, `FR-12`, `FR-14`, `FR-19`, `FR-20`.
  - **Phase 3 (completes specification coverage):** `FR-13`, `FR-15`.
- **The risk this phasing carries, stated in the PRD:** anything scheduled last is what fails to exist when the budget runs out. Phase 3 is the part most likely to go undelivered, and calling it "in scope" does not make it safe. If Phase 3 does not land, `SM-8` is **missed and reported as a missed target**, not reclassified after the fact as a deferral that was always intended.
- Counter-metric `SM-C1`: when coverage and correctness compete for the last hours, **correctness wins**, and the shortfall is declared.

#### Known limitations carried into implementation

- **Nothing bounds how long a Leave Request may remain Pending.** By project decision no bound is introduced. `AD-6`'s recomputation and `AD-19`'s forward check are correct for any number of open Leave Years, so this is a performance characteristic, not a correctness defect.
- **A holiday edit stalls submissions organization-wide** for the duration of its transaction, because `AD-19` locks every affected balance row. Acceptable at this data scale.
- **Earned Leave above the Carry-Forward Cap is forfeited**, where Indian statute generally requires it be encashed. Encashment is a PRD §6 non-goal. Accepted for a trainee project; a production deployment must address it first. No seam is reserved.
- **`policy_change` and holiday edits are deliberately unattributed.** PRD §1 was narrowed to promise attribution for Leave Request state changes only.

### UX Design Requirements

**None. No UX Design Specification exists for this project**, and the product owner confirmed on 2026-07-10 that the workflow proceeds without one.

This section is retained rather than deleted so that its emptiness reads as a decision rather than an oversight. The UI requirements that do exist live in the PRD and the Architecture Spine, and are captured above:

- `FR-11` (per-role dashboards: summary cards with date-range filtering — **charts and trend lines are explicitly out of scope**, counter-metric `SM-C2`)
- `FR-18` (Department Leave Calendar, inline on the approval screen, Approved and Pending visually distinguished)
- `AD-2` (the client obtains every day count from the preview endpoint, which names each excluded date and its reason — this is what `UJ-1` turns on; **no frontend module references a weekday or a holiday**)
- `NFR-16` (a control a role cannot invoke is not rendered — a usability measure, never the only thing preventing an action)
- `NFR-17` (errors state the reason with their numbers)
- `NFR-18` (responsive across desktop and tablet widths)

The Architecture Spine explicitly defers "React state shape below the page level, styling, and component library," on the grounds that no two epics can diverge structurally once `AD-2`, `AD-14` and `AD-21` hold. Formal WCAG conformance is explicitly not required.

### FR Coverage Map

Every one of the twenty functional requirements is **owned** by exactly one epic, and none is orphaned.

**"Owned" is doing work in that sentence.** Three FRs carry acceptance criteria in an epic that does not own them, always for the same reason — the criterion is not *executable* until a later epic creates the rows it needs. Each is disclosed where it occurs, and none divides ownership:

- `FR-04`'s `EMPLOYEE_HAS_PENDING_REQUESTS` guard is asserted in Story 1.6 and, as that story says, "vacuously satisfied in this epic"; Story 2.6 re-asserts it as a running test.
- `FR-03`'s headline consequence — a Manager reaching a non-report's Leave Request receives a 404 — cannot be tested before a Leave Request exists. Story 1.7 says so: "it does not claim to satisfy `SM-3`, which Epic 2 does."
- `FR-12` and `FR-20` are owned by Epic 3, but the `FR-03`-scoped `GET /leave-requests` they build on is delivered in Epic 2's Story 2.7, because Epic 2's own stories require it. Epic 3 adds the composable filters (`FR-12`) and the cross-Leave-Year history (`FR-20`). This is the seam already used to split `NFR-11`'s server page bound, delivered in Story 1.5, from `FR-12`'s filters.

- **FR-01:** Epic 1 — An Employee exchanges credentials for an authenticated session; failure discloses nothing about account existence.
- **FR-02:** Epic 1 — The session is carried as a JWT presented on each request; absent, expired and tampered tokens are rejected.
- **FR-03:** Epic 1 — Data-scoped role-based access control; a Manager's authority derives from the Direct Report relationship, not the role.
- **FR-04:** Epic 1 — Admin manages Employee records; deactivation never deletes, and is guarded against orphaning Direct Reports.
- **FR-05:** Epic 1 — Admin manages Departments; one holding Employees cannot be removed.
- **FR-17:** Epic 1 — An Employee edits their own Full Name, and nothing else.
- **FR-06:** Epic 2 — Leave Types and their four attributes are configured as data; a policy change demands an explicit disposition.
- **FR-07:** Epic 2 — Accrued, Reserved and Consumed are maintained and Available derived; proration, carry-forward, lapse, and the scheduled rollover.
- **FR-08:** Epic 2 — Leave Request submission, the Working-Day Leave Day count, and the reservation of days on admission.
- **FR-09:** Epic 2 — Approval, rejection, cancellation of Pending leave, and the Admin-decided Cancellation Request against Approved leave.
- **FR-10:** Epic 2 — The Company Holiday calendar, and the forward-checked, refusable recalculation an edit to it triggers.
- **FR-16:** Epic 2 — Exactly one append-only Audit Entry per state transition, readable in full by the Admin alone.
- **FR-11:** Epic 3 — A dashboard per role, scoped to what that role can act on, with a date-range filter.
- **FR-12:** Epic 3 — Composable filters and server-bounded pagination that never widen authorization.
- **FR-14:** Epic 3 — In-app notifications on submission and on decision, with an unread count and an idempotent mark-read.
- **FR-18:** Epic 3 — The Department Leave Calendar, inline on the approval screen, informing a decision it never blocks.
- **FR-19:** Epic 3 — A Manager views exactly their Direct Reports, active and deactivated distinguishable.
- **FR-20:** Epic 3 — An Employee views their own Leave Requests across Leave Years, in every state.
- **FR-13:** Epic 4 — A Supporting Document, validated before storage and stored opaquely outside the web root.
- **FR-15:** Epic 4 — CSV export of exactly the rows the applied filters selected, scoped to the caller.

**Where the NFRs land.** Corrected after Epic 1's stories were written, because several NFRs are first delivered earlier than the initial assignment claimed. An NFR is listed against the epic whose stories **first carry an acceptance criterion verifying it**; where it is enforced continuously thereafter, that is stated.

| NFR | First verified in | Note |
| --- | --- | --- |
| `NFR-01` credential storage | Epic 1 (1.2) | |
| `NFR-02` token lifetime | Epic 1 (1.2, 1.3) | |
| `NFR-03` server-side authorization | Epic 1 (1.4) | Enforced by every later endpoint |
| `NFR-04` scoping in the query | Epic 1 (1.4, 1.7) | Exercised against real scoped resources from Epic 2 |
| `NFR-05` upload validation | Epic 4 | |
| `NFR-06` TLS | Epic 1 (1.1) | The `proxy` service terminates TLS; deployed environment only |
| `NFR-07` atomic balance operations | Epic 2 | |
| `NFR-08` one pure day-count function | Epic 2 | |
| `NFR-09` append-only audit | Epic 2 | |
| `NFR-10` ~500 ms reads | — | **Not independently verified by any story.** An order of magnitude, not a contractual figure; it motivates `NFR-12` rather than carrying a test of its own |
| `NFR-11` bounded result sets | Epic 1 (1.5, 1.6) | The spine's *Pagination* convention binds **every** list endpoint, so it is enforced from Epic 1's first list endpoint onward, not from `FR-12` in Epic 3 |
| `NFR-12` indexed access paths | Epic 1 (1.2), completed Epic 2 | Epic 1 indexes employee, manager, department; Epic 2 adds leave year and request status |
| `NFR-13` layered structure | Epic 1 (1.1) | Enforced by the standing import-direction check |
| `NFR-14` policy as configuration | Epic 2 | |
| `NFR-15` tests for the hard rules | Epics 2 and 3 | |
| `NFR-16` role-appropriate interface | Epic 1 (1.5, 1.8) | Never the only thing preventing an action |
| `NFR-17` errors state the reason | Epic 1 (1.5) | Refusals carrying *numbers* arrive in Epic 2 |
| `NFR-18` responsive layout | Epic 1 (1.1) | |
| `NFR-19` attribution | Epic 2 | |
| `NFR-20` environment-supplied config | Epic 1 (1.1) | |
| `NFR-21` reproducible setup | Epic 1 (1.1) | |

**Where the success metrics land.** `SM-3` in Epic 1. `SM-1`, `SM-2`, `SM-4` and `SM-5` — four of the five correctness metrics — all fall inside Epic 2. That concentration is deliberate, and is the reason Epic 2 was not split.

**Phase alignment.** Epics 1 and 2 together are PRD §7.1's Phase 1. Epic 3 is Phase 2. Epic 4 is Phase 3.

## Unresolved Gaps

Eight items that the finalized sources — PRD, addendum, Architecture Spine, solution architecture, API contracts, ERD, and Module 1 — **do not resolve**. Each was verified against those documents rather than assumed. Where a story's acceptance criteria stop short of asserting a behavior, a status code, or an error code, it is because of an item below; the story says so in place and points here.

**`G1`, `G2`, `G3`, `G5`, `G7` and `G8` are resolved.** `G4` and `G6` remain open, and neither blocks implementation. All six resolutions were **routed upstream** into `api-contracts.md` (§1 status semantics, §2 error vocabulary) and, for `G7` and `G8`, into the architecture invariants above (`AD-22` amended, `AD-23` added) — following the precedent `G1` set on 2026-07-10.

Three earlier suspicions dissolved under verification and are deliberately **not** listed: `NFR-11`'s page bound (fixed by the spine's *Pagination* convention, which binds every list endpoint), TLS responsibility (fixed by the spine's deployment topology and architecture §2, on the `proxy` service), and the login timing criterion (fixed by ERD §4.2 and GAP-1: "the hash comparison must run regardless").

| # | Gap | Status |
| --- | --- | --- |
| `G1` | How an Employee gets their first password | ✅ **RESOLVED** 2026-07-10 |
| `G2` | Duplicate email address on create or update | ✅ **RESOLVED** 2026-07-10 — `409 EMAIL_ALREADY_IN_USE` |
| `G3` | The status code for a role-denied read | ✅ **RESOLVED** 2026-07-10 — `403 ACTION_NOT_PERMITTED` |
| `G4` | An outstanding token for a since-deactivated Employee | ⚠️ Open — does not block; settle before deployment |
| `G5` | Rejection code for `PATCH /me` with a forbidden field | ✅ **RESOLVED** 2026-07-10 — `400 FORBIDDEN_FIELD` |
| `G6` | Success status code for `DELETE /departments/<id>` | ⚠️ Open — cosmetic, no correctness impact |
| `G7` | Nothing forbids a reporting cycle | ✅ **RESOLVED** 2026-07-10 — `AD-23`, `400 REPORTING_CYCLE` |
| `G8` | An Admin may demote a Manager who still has Direct Reports | ✅ **RESOLVED** 2026-07-10 — `AD-22` amended |

**Why `G7` and `G8` were escalated rather than carried.** Both were previously recorded as "does not block implementation," which was true and which read as "safe to implement." They are different claims. `G7` in particular would have shipped a **self-approval hole with every declared metric green** — `SM-3` ("authorization is scoped to data, not to role") passes, because a self-manager's approval genuinely *is* data-scoped. Neither gap blocked story *creation*; both would have blocked story *correctness*.

### G1 — How an Employee gets their first password  ✅ RESOLVED (2026-07-10)

**The gap, as found.** Nothing stated how an Employee created by an Admin obtained an initial credential.

**Why the finalized sources did not resolve it.** `FR-04` enumerated what an Admin sets — Department, role, joining date, Manager — and never mentioned a password. `FR-01` presumed credentials already existed. `FR-17` restricts the Employee's editable surface to `full_name`, so they could not set one themselves. `FR-14` and PRD §6 forbid LeaveFlow from sending email, so there was no invite link and no reset path. `POST /employees` in api-contracts §4.2 fixed no password field. ERD GAP-1 resolved the login *identifier* (the email address) and explicitly never asked what the *credential* was. `AD-14` specifies only how a password is hashed — `pwdlib`, bcrypt or Argon2 — never where it comes from.

**Implementation consequence, had it been left unresolved.** Only the Admin created by the seed command could ever authenticate. Every Employee created through `FR-04` would be permanently unable to log in, making `FR-07`, `FR-08`, `FR-09`, `FR-13`, `FR-17` and `FR-20` unreachable for anyone but that Admin.

**The resolution — PM decision, 2026-07-10.** An Admin supplies an Employee's initial password when creating them. The backend hashes it before persistence using the existing `AD-14` hashing architecture, never stores it recoverably, and never returns it in any response. Communication of the initial password occurs outside LeaveFlow.

No forced first-login change, no `must_change_password` state, no password-change endpoint, no reset, no forgot-password flow, no Admin re-issue, no periodic expiry, no email capability, and **no password complexity or minimum-length policy**. A forced first-login change was drafted and rejected as disproportionate to a three-day implementation budget: it would have required a persisted column, a global authorization gate, a new endpoint, a new error code whose status code no source could supply, an amendment to `AD-14`, and possibly an `FR-21`.

**Recorded as resolution of the credential-provisioning gap jointly exposed by `FR-01` and `FR-04` — not as a new standalone requirement.** `SM-8`'s twenty-requirement denominator is preserved, following the precedent ERD GAP-1 and GAP-2 set when `email` and `full_name` were added as Glossary terms plus one acceptance criterion. The Architecture Spine required no change; the ERD required no schema change.

**Security limitation accepted, and recorded in PRD §6 and architecture §11.** No recovery path. A permanent lockout, because `FR-04` forbids deletion and `UNIQUE (email)` on a row that persists forever means the address is never reusable. Attribution that binds an *account* rather than a person, since the Admin knows every password and none is rotated. And a compromised credential revocable only by a deactivation that `AD-22` may refuse and no endpoint reverses.

**Blocking status.** Cleared.

### G2 — Duplicate email address on create or update  ✅ RESOLVED (2026-07-10)

**The gap, as found.** No defined refusal when an Admin creates or updates an Employee with an email address already in use.

**Why the finalized sources did not resolve it.** ERD §4.2 fixes `UNIQUE (email)` and notes that because `FR-04` forbids deletion, a deactivated Employee's row and address persist indefinitely and the address is never reusable — so the collision will occur in normal operation. No functional requirement stated the refusal. api-contracts §2 declared sixteen error codes and none covered it. `AD-21` requires every error code be declared exactly once in `domain/`, so introducing one is an amendment to a binding document rather than a story-level choice.

**Implementation consequence, had it been left unresolved.** With no service-layer gate, the `UNIQUE` violation surfaces as a database `IntegrityError` and the Admin receives a `500`. `AD-5` establishes for `leave_balance` that "the schema is the backstop, the service is the gate," and that a constraint violation reaching a client is a defect rather than a refusal — but no rule extended `AD-5` to `employee`.

**The resolution.** `POST /employees` and `PATCH /employees/<id>` refuse a colliding email address with **`409 EMAIL_ALREADY_IN_USE`**, raised by the service before the write, never surfaced from the `UNIQUE` violation. The refusal does **not** disclose whether the holder is active or deactivated. `AD-5`'s "schema is the backstop, service is the gate" principle now extends to `employee` explicitly. `NFR-17` is satisfied: the error states its reason. Declared once in `domain/` per `AD-21`; recorded in api-contracts §2.

**Blocking status.** Cleared. Asserted in Story 1.6.

### G3 — The status code for a role-denied read  ✅ RESOLVED (2026-07-10)

**The gap, as found.** What code is returned when an actor is denied an endpoint by role and may not read the resource at all — a non-Admin calling `GET /employees` or `GET /employees/<id>`, or an Employee calling `GET /dashboard/manager`.

**Why the finalized sources did not resolve it.** api-contracts §1 defined `403` as "the actor may **see** this resource but may not perform **this action** on it," which cannot describe a denied *read*. `AD-10`'s `404` rule governs "a resource outside the actor's **scope**"; here the actor is denied by role grant, not by an empty scope. `FR-11` and api-contracts §4.9 said an Employee requesting the Manager dashboard "is refused," naming no code. `FR-03` and api-contracts §1 fixed `404` only for the Leave Request case.

**Implementation consequence, had it been left unresolved.** Two epics decide it differently — precisely the divergence api-contracts exists to prevent, per its own §0. Seven acceptance criteria across Stories 1.6, 2.9, 2.11, 2.12, 3.2 and 3.5 asserted that a request "is refused server-side" with no code to assert.

**The resolution — PM decision, 2026-07-10.** **`403 ACTION_NOT_PERMITTED`.** api-contracts §1's definition of `403` is widened to *"the actor's **role** does not grant this endpoint, **or** the actor may see this resource but may not perform this action on it."*

The distinguishing test: **does the actor's role admit them to this endpoint at all?** If no → `403`, decided before any row is read. If yes → the scope predicate runs, and a miss is `404`. **`AD-10` is unchanged** and its `404` continues to mean exactly one thing: *outside your scope*. `FR-03`'s byte-identical requirement — a Manager naming a non-report's Leave Request — is a scope miss and remains `404`.

**Why `403` discloses nothing.** The endpoint's existence and its role requirement are already public in the FastAPI-generated OpenAPI document, which `D-05` chose the framework to produce and which api-contracts §0 names the runtime source of truth. A `403` therefore leaks no fact the actor could not read from the schema. A blanket `404` would additionally make a mis-routed request and a genuine authorization denial indistinguishable during a three-day build.

**A latent hole this closed.** api-contracts §2 declared sixteen error codes and **not one of them was a `403`** — while Story 1.5 already asserted `403` for an Employee calling `POST /departments` and Story 2.7 already asserted `403` for an Admin approving leave, and §2 requires every non-2xx body to carry the `{ code, message, details }` envelope. `ACTION_NOT_PERMITTED` was missing entirely, independent of `G3`.

**Blocking status.** Cleared. Asserted in Stories 1.6, 2.7, 2.9, 2.11, 2.12, 3.2 and 3.5.

### G4 — An outstanding token for a since-deactivated Employee

**The gap.** Whether an unexpired, correctly-signed token issued before an Employee was deactivated continues to authorize their requests.

**Why the finalized sources do not resolve it.** `AD-14` enumerates exactly three rejection cases: a token "absent, expired, or whose signature does not verify." `AD-22` and `FR-04` state that a deactivated Employee "cannot **authenticate**" — which is `FR-01`'s credential exchange, not `FR-02`'s token presentation. No source connects `employee.is_active` to the `api/` authorization dependency, though `AD-14` does require that dependency to check "against the database."

**Implementation consequence if left unresolved.** A deactivated Employee retains full access until their token expires — bounded by `NFR-02` at hours rather than days. If the intended reading is that `AD-14`'s database check includes `is_active`, this is a one-line change to the dependency; if not, deactivation is not immediate and `AD-22`'s guarantees are weaker than they read. Story 1.3 asserts only what `AD-14` fixes: that the dependency loads the Employee row and reads the role from it.

**Blocking status.** Does not block. Security-relevant; decide before deployment.

### G5 — Rejection code for `PATCH /me` with a forbidden field  ✅ RESOLVED (2026-07-10)

**The gap, as found.** The status code and error code when `PATCH /me` carries any field other than `full_name`.

**Why the finalized sources did not resolve it.** api-contracts §4.1 fixed the *behavior* — "accepts exactly one field: `full_name`. It refuses any attempt to alter `email`, role, department, manager, joining date, or a balance quantity" — but §1's status table enumerated only `400`, `401`, `403`, `404` and `409`, and §2's vocabulary declared no matching code. FastAPI's natural response, `422`, appears nowhere in any source, and §2 requires every non-2xx body to carry the `{ code, message, details }` envelope.

**Implementation consequence, had it been left unresolved.** The implementer either returns `400` with an error code that `AD-21` never declared, or `422` with no envelope, violating api-contracts §2 and `NFR-17`.

**The resolution.** **`400 FORBIDDEN_FIELD`**, with `details` naming the rejected fields. It is a `400` and not a `403` because the actor is permitted the endpoint and the resource — it is their own profile — and the domain refuses the *content* of the request. FastAPI's default `422` is suppressed for this endpoint so the envelope holds.

**Blocking status.** Cleared. Asserted in Story 1.8.

### G6 — Success status code for `DELETE /departments/<id>`

**The gap.** Whether a successful Department deletion returns `200` or `204`.

**Why the finalized sources do not resolve it.** api-contracts §1's status table covers non-2xx codes only. The sole 2xx semantic fixed anywhere is §4.3's "these endpoints return `200` with a summary rather than failing wholesale," which applies to the holiday and policy endpoints alone.

**Implementation consequence if left unresolved.** The implementer chooses, and the React client must match whatever is chosen. No correctness impact.

**Blocking status.** Does not block. Cosmetic.

### G7 — Nothing forbids a reporting cycle  ✅ RESOLVED (2026-07-10)

**The gap, as found.** No rule prevented an Employee from being their own Manager, or a cycle A → B → A.

**Why the finalized sources did not resolve it.** `DR-12` defines a Manager's authority by the Direct Report relationship and says nothing about that relationship's shape. ERD §3 models `employee → employee` as `0..1 → 0..*`, nullable, with no acyclicity constraint, and ERD §4.2 lists no `CHECK` for it. `AD-22` guarded deactivation only. No business rule, functional requirement, or architecture decision addressed it.

**Implementation consequence, had it been left unresolved.** An Employee who is their own Manager **approves their own leave.** `FR-09` grants approval to "the Manager of the applicant," and `DR-12` derives that authority from the relationship rather than the role, so the check passes. `FR-09`'s managerless auto-approval is never reached, because `manager_id` is not NULL. Self-approval is both representable and permitted — and **every declared success metric still reports green**, because `SM-3` asks whether authorization is scoped to data rather than to role, and a self-manager's approval genuinely *is* data-scoped.

That is the reason this gap was escalated from "does not block implementation" to a resolution. It never blocked story *creation*. It would have blocked story *correctness*, silently.

**The resolution — `AD-23`, 2026-07-10.** The reporting graph is acyclic. `employee` carries `CHECK (id <> manager_id)` as a **backstop**, and the employee service refuses any manager assignment closing a cycle — directly or transitively — with **`400 REPORTING_CYCLE`**. Per `AD-5`'s established principle, the service is the gate and the constraint is the backstop; a `CHECK` violation reaching a client would be a defect and a `500`, never the refusal. The transitive walk is bounded by the employee count and runs inside the assignment transaction.

**Blocking status.** Cleared. Asserted in Story 1.6.

### G8 — An Admin may demote a Manager who still has Direct Reports  ✅ RESOLVED (2026-07-10)

**The gap, as found.** `AD-22` refused to *deactivate* an Employee whom an active Employee names as Manager. Nothing refused to change that Employee's `role` to `EMPLOYEE`.

**Why the finalized sources did not resolve it.** `AD-22` named deactivation explicitly and only. `FR-04` grants the Admin an unqualified power to update an Employee's role. api-contracts §4.2's `PATCH /employees/<id>` named no guard, and the `EMPLOYEE_HAS_DIRECT_REPORTS` code was bound in §2 to the deactivate endpoint alone.

**Implementation consequence, had it been left unresolved.** `DR-12` says authority derives from the reporting relationship, not the role. api-contracts §4.5 grants `approve` and `reject` to `Role = Manager`, `Scope = reports`. For a demoted Employee who still holds Direct Reports the two disagree: the relationship says they may decide, the role gate says they may not. Their reports' Pending Leave Requests then have **no approver** — and receive no auto-approval either, since their `manager_id` is not NULL. That is precisely the orphaning `AD-22` exists to prevent, reached through a door `AD-22` did not cover.

**The resolution — `AD-22` amended, 2026-07-10.** The same Direct-Report guard now refuses **any update that lowers an Employee's `role` below `MANAGER`** while an active Employee still names them as Manager, with **`409 EMPLOYEE_HAS_DIRECT_REPORTS`** — the existing code, now bound in api-contracts §2 to both the deactivate endpoint and `PATCH /employees/<id>`. Deactivation and demotion are the two doors to the same orphaning; both are now closed.

**Blocking status.** Cleared. Asserted in Story 1.6.

## Epic List

Four epics. Each delivers complete functionality for its domain and stands alone; none requires a future epic to function.

**This claim was false when first written, and the fix is recorded rather than quietly applied.** Epic 2's Stories 2.7 and 2.8 have frontend criteria — a Manager "opens their queue," an Employee "views an Approved future-dated request" — that cannot be met without `GET /leave-requests` and `GET /leave-requests/<id>`, which were delivered only by Epic 3's Story 3.1. Since Epics 1 and 2 together are PRD §7.1's Phase 1, completing the correctness core would have left a Manager unable to see the queue they are meant to decide from. Both reads now land in Story 2.7, scoped by `FR-03` alone; Epic 3 still owns `FR-12`'s filters and `FR-20`'s history. Every other forward reference in this document is disclosed in place; this one was implicit, which is why it survived four reviews.

### Epic 1: Secure Access and Organization Administration

An Admin can stand up the organization — Departments, Employees, roles, joining dates and reporting lines — and everyone with an account can log in, carry a session across requests, and edit their own name. Every interaction is authenticated, and every authorization decision is made server-side against the reporting data rather than against the caller's role name: a Manager who is not *this* applicant's Manager is, for that request, indistinguishable from a stranger.

**FRs covered:** FR-01, FR-02, FR-03, FR-04, FR-05, FR-17

**Why these belong together.** PRD §4.1 (Identity and Access) and §4.2 (Organization Administration) are separate feature groups but one component end-to-end: the `employee` table, the `api/v1` authorization dependencies, `api/v1/employees`, `api/v1/departments` and `api/v1/me`. Splitting them would churn the same files twice.

**Implementation notes.**
- **There is no starter template.** `fastapi/full-stack-fastapi-template` was considered and rejected — it ships SQLModel, whose fusion of Pydantic schema and SQLAlchemy table is exactly the coupling `AD-1` forbids. Its `docker-compose` and Alembic wiring are reference only. Story 1.1 scaffolds the four-package tree by hand.
- This epic establishes `employee.manager_id`, the single column every later epic's authorization scope is a SQL predicate on (`AD-10`).
- `AD-22`'s two deactivation guards are load-bearing here, not housekeeping: without the second, deactivating a Manager would orphan their Direct Reports and cause `FR-09` to auto-approve their Pending requests with no human approver.
- `AD-14` fixes the libraries: `pwdlib` (not `passlib`, unmaintained since 2020 and broken against bcrypt 5) and `PyJWT` (not `python-jose`, CVE-2024-33663).
- Satisfies `SM-3`: zero endpoints authorize on role name alone.

### Epic 2: Trustworthy Leave Balances and the Request Lifecycle

An Admin configures the Leave Policy and the Company Holiday calendar as data, without a code change. Every Employee holds a balance that stays correct across proration, carry-forward and the Leave Year boundary. An Employee sees what a request will cost — weekends and named holidays excluded — *before* committing to it, and applies against a balance that cannot go negative even under concurrent submission. A Manager decides their own reports' requests, and only theirs. Approved leave can be cancelled through a Cancellation Request an Admin decides. Every state transition is attributable to an actor and a moment.

**FRs covered:** FR-06, FR-07, FR-08, FR-09, FR-10, FR-16

**Why these belong together.** These six are mutually dependent and admit no honest seam. `FR-08` cannot count a Leave Day without holidays (`FR-10`), and `FR-07` cannot accrue or roll over without Leave Type attributes (`FR-06`) — PRD §7.1 names both as prerequisites. Running the other way, `FR-06`'s `RECALCULATE` disposition and `FR-10`'s holiday recalculation both re-derive `leave_days` and balance quantities on requests that `FR-07` and `FR-08` create. Splitting the cycle would force an epic to depend on a future epic. They also share `AD-17`'s single balance-mutation module, which submission, approval, rejection, cancellation, recalculation and the rollover all call.

**Implementation notes.**
- This is PRD §7.1's correctness core, and where the product's central claim to trustworthiness lives. Four of the five correctness success metrics land here: `SM-1` (balance arithmetic), `SM-2` (day count at the boundaries), `SM-4` (audit one-to-one), `SM-5` (policy is data).
- `AD-2`: exactly one function, `domain.calendar.count_leave_days`, knows what a weekend or a Company Holiday is. The preview endpoint is the only way a client obtains a day count, and its value is **advisory only** — admission is decided against the balance row read under lock (`AD-3`).
- `AD-17`'s `consume_direct` exists as an operation distinct from `consume_reserved` because `FR-09`'s managerless auto-approval consumes without ever having reserved; a shared `consume` would decrement `reserved` from zero and violate `CHECK (reserved >= 0)`.
- `AD-6`: carry-forward is **derived, never accumulated**, which is what makes the rollover idempotent by construction and what prevents days being both Consumed in year Y and carried into Y+1.
- `AD-5`: the CHECK constraints are a **backstop, never a gate**. A CHECK violation reaching a client is a defect and a 500 — never the refusal `FR-08` and `NFR-17` require.
- `AD-7`: the rollover is a CLI entrypoint with **no endpoint**, so that N uvicorn workers do not register N schedulers.

### Epic 3: Visibility and Decision Support

Each role opens a dashboard scoped to what that role can act on. A Manager sees which of their other Direct Reports are already away on the requested dates *at the moment of decision*, rather than discovering the overlap the following week. Employees see their own history across Leave Years; Managers see their team. Notifications close the loop: the Manager learns a decision is waiting, and the applicant learns it was made. Every list is filtered, composable, and bounded by the server.

**FRs covered:** FR-11, FR-12, FR-14, FR-18, FR-19, FR-20

**Why these belong together.** This is PRD §7.2 — the phase in which the product becomes usable. `FR-18` exists so that `BR-06`'s "no restriction on overlapping leave" is an informed choice rather than an unnoticed one.

**Implementation notes.**
- `AD-16`: `FR-14`'s notification write happens **inside the transition's own transaction**, so a Notification exists if and only if the transition committed. This means `FR-14` adds a hook to Epic 2's `services/leave_request` **only**. That is incidental sharing, not shared ownership — no other service writes notifications.
- **`services/cancellation` writes no Notification, deliberately.** `FR-14`'s three kinds are exhaustive: `REQUEST_SUBMITTED` to the applicant's Manager, and `REQUEST_APPROVED` / `REQUEST_REJECTED` to the applicant. `FR-14`'s consequences name the submission and the approval-or-rejection of a **Leave Request**; a Cancellation Request is a separate entity (`AD-13`, `DR-14`) and its transitions notify no one. An Admin discovers a Cancellation Request through `GET /cancellation-requests` (Story 2.8), not through a notification. Notifying "the Admin" would require deciding which Admin, and `FR-14` requires **exactly one** Notification per event — a fan-out semantics no source document fixes.
- `FR-11` is summary cards with a date-range filter. **Charts and trend lines are out of scope**, per PRD §7.4 and counter-metric `SM-C2`: charts are the cheapest way to look finished and the least defensible under questioning.
- `AD-18`: every read path here — history, dashboard, calendar — reads the stored `leave_request.leave_days` and never recomputes it against today's holiday calendar.
- `AD-10` governs all of it: filtering never widens authorization, and a resource outside the actor's scope returns 404, byte-identical to a nonexistent one.

### Epic 4: Supporting Documents and Reporting

An Employee attaches a Supporting Document to a Leave Request whose Leave Type requires one — validated for type and size before a single byte is written, and stored under a server-generated name on a volume outside the web root. A Manager exports their Direct Reports' leave as CSV; an Admin exports organization-wide. Both exports carry exactly the rows the applied filters selected.

**FRs covered:** FR-13, FR-15

**Why it is its own epic, small as it is.** This is PRD §7.3, and the PRD is blunt about it: Phase 3 "is the part of the specification most likely to go undelivered, and calling it 'in scope' does not make it safe." Keeping it separate and last makes that risk visible rather than buried inside a larger epic. **If it does not land, `SM-8` is missed and reported as a missed target — not reclassified after the fact as a deferral that was always intended.**

**Implementation notes.**
- `FR-13` adds a document-required check to Epic 2's submission service. This is safe to defer *because* PRD §7.3 settled that EL, CL and FL seed with `requires_supporting_document = false`, so no document-requiring Leave Type exists before this epic lands. An Admin who sets the attribute true beforehand creates a requirement that is configurable but unenforced — a deliberate act, not a latent gap.
- `AD-15`: the client-supplied filename is persisted as a data column and **never** used as a path component. Documents are served only by an authorized streaming endpoint that re-applies `AD-10`'s scope; no static route maps to the volume.
- `FR-15` reuses Epic 3's `FR-12` filters and reads `AD-18`'s frozen `leave_days`. PDF export is a non-goal.

---

## Epic 1: Secure Access and Organization Administration

An Admin can stand up the organization — Departments, Employees, roles, joining dates and reporting lines — and everyone with an account can log in, carry a session across requests, and edit their own name. Every interaction is authenticated, and every authorization decision is made server-side against the reporting data rather than against the caller's role name: a Manager who is not *this* applicant's Manager is, for that request, indistinguishable from a stranger.

Stories are full-stack vertical slices: each ships its backend and its React surface together, where the requirement implies a user-facing one.

### Story 1.1: Project Foundation and Reproducible Setup

As a developer joining LeaveFlow,
I want a hand-rolled four-package skeleton that runs from a documented command sequence on a clean machine,
So that every later story lands in a structure where a domain rule cannot be implemented in the wrong layer.

**Acceptance Criteria:**

**Given** a clean machine with Docker installed and no prior LeaveFlow state
**When** I run `docker compose up`, then `alembic upgrade head`, then the seed command
**Then** `GET /api/v1/health` answers `200` and the static React bundle is served
**And** no step required a configuration value absent from `.env.example` (`NFR-21`, `NFR-20`)

**Given** the backend source tree `app/{api,services,repositories,domain,jobs,core}`
**When** the import-direction check runs as part of the test suite
**Then** `domain/` imports no ORM, no web framework, and performs no I/O; `api/` imports neither `repositories/` nor `domain/`; `repositories/` does not import `services/`
**And** a violation of any of these fails the build rather than merely warning (`AD-1`, `NFR-13`)

**Given** a typed domain exception raised in `services/`
**When** it propagates to the `api/` layer
**Then** a single `api/` exception handler maps it to the envelope `{ code, message, details }` and to a status code
**And** `domain/` and `services/` import no HTTP, verified by the same import-direction check (spine *Errors in code*)

*(The endpoint-level assertion — that every non-2xx response carries this envelope — is relocated to Story 1.2, the first story in which any endpoint can return a non-2xx response. The `AD-21` vocabulary assertion is likewise relocated to Story 1.2, where the first enumerated values come into existence. Asserted here, both would test a codebase that does not yet exist.)*

**Given** the `docker compose` topology
**When** the deployed environment is inspected
**Then** a `proxy` service terminates TLS in front of the `web` and `api` services, which sit alongside `postgres:18`
**And** credentials and tokens travel over TLS in any deployed environment (`NFR-06`; spine *Deployment*, architecture §2)

**Given** the repository
**When** version control is inspected
**Then** `.env` is ignored and `.env.example` is committed
**And** no secret, database credential, or JWT signing key appears in any committed file (`NFR-20`)

**Given** the Alembic directory after `alembic upgrade head`
**When** the database is inspected
**Then** no domain table has been created by this story, and no migration inserts a Leave Type row (`AD-11`, and the principle that a story creates only the tables it needs)

**Given** the installed dependency set
**When** versions are compared against the Architecture Spine's stack table
**Then** every version matches exactly
**And** SQLAlchemy remains on the 2.0 line, TypeScript on 6.0.3, and Python on 3.13 — the three pins deliberately behind latest, which a later story must not upgrade

**Given** the frontend
**When** it is built
**Then** it is a Vite + React + TypeScript SPA with TanStack Query and a typed API client
**And** its shell is usable at common desktop and tablet widths (`NFR-18`)

### Story 1.2: Log In and Receive a Session

As an Employee,
I want to exchange my email address and password for a session token,
So that I can use LeaveFlow without a failed attempt revealing whether anyone's account exists.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `department` and `employee` exist and no other domain table does
**And** `employee` carries `UNIQUE (email)`, `CHECK (role IN ('EMPLOYEE','MANAGER','ADMIN'))`, `CHECK (id <> manager_id)`, a NOT NULL `department_id` foreign key, a **nullable** self-referencing `manager_id`, a `joining_date` of type `DATE`, `is_active`, and `password_hash`, with indexes on `manager_id` and `department_id`
**And** `CHECK (id <> manager_id)` is a **backstop** for `AD-23`, never the gate: the transitive cycle refusal lives in the employee service (Story 1.6), and a `CHECK` violation reaching a client is a defect and a `500` (`AD-5`, `AD-23`)

*(`employee.department_id` is NOT NULL — every Employee belongs to exactly one Department, PRD §3 — so `department` is created here rather than in Story 1.5, which adds its endpoints.)*

**Given** the seed command has run
**When** the database is inspected
**Then** exactly one Department and exactly one Admin Employee exist, both taken from the environment
**And** that Admin has `manager_id` NULL and `is_active` true

**Given** an active Employee and their correct password
**When** `POST /api/v1/auth/login` is called
**Then** the response is `200` carrying a JSON Web Token whose claims identify the subject and the role
**And** the token carries an `exp` claim whose lifetime is measured in hours, not days (`FR-01`, `NFR-02`)

**Given** an email address belonging to no Employee
**When** `POST /api/v1/auth/login` is called
**Then** the response is `401` with code `AUTH_FAILED`
**And** the body is byte-identical, and the status code equal, to the response for a known email with a wrong password (`FR-01`)

**Given** an email address belonging to no Employee
**When** authentication is attempted
**Then** the login path executes exactly one password hash comparison, against a constant fallback hash, before returning `AUTH_FAILED`
**And** a test asserting the verification function was invoked passes identically on the unknown-email path and the wrong-password path, so the lookup never short-circuits on a missing row (ERD §4.2 and GAP-1: "the hash comparison must run regardless")

*(This replaces a wall-clock timing assertion, which would have been a flaky test rather than an acceptance criterion. The structural form is what ERD §4.2 and GAP-1 actually require, and `FR-06`'s own note establishes that criteria provable only by inspection belong to code review, not to acceptance.)*

**Given** any Employee row
**When** `password_hash` is inspected
**Then** it is a salted hash produced by bcrypt or Argon2 through `pwdlib`
**And** no stored representation permits recovery of the password, and neither `passlib` nor `python-jose` appears in the dependency set (`NFR-01`, `AD-14`)

**Given** an Employee whose `is_active` is false
**When** they present their correct credentials
**Then** authentication is refused with the same `AUTH_FAILED` response (`FR-04`, `AD-22`)

**Given** the `401` response produced by any failed login
**When** its body is inspected
**Then** it carries exactly the envelope `{ code, message, details }` with `code` equal to `AUTH_FAILED`
**And** `POST /api/v1/auth/login` is the first endpoint capable of a non-2xx response, so the envelope is exercised here rather than in Story 1.1 (`NFR-17`, api-contracts §2)

**Given** the enumerated values this story introduces — the role values `EMPLOYEE`, `MANAGER`, `ADMIN`, and the error codes `AUTH_FAILED` and `TOKEN_INVALID`
**When** the codebase is checked
**Then** each is `UPPER_SNAKE_CASE` and declared exactly once as a constant in `domain/`
**And** a standing check fails the build if any such value appears as a literal outside that module, for these values and for every enumerated value a later story adds (`AD-21`)

**Given** the React application and an unauthenticated visitor
**When** they open the app
**Then** a login screen is presented; a successful login stores the token and lands them on the application shell
**And** a failed login shows a message that does not disclose whether the account exists

### Story 1.3: Carry the Session on Every Request

As an authenticated Employee,
I want my session verified server-side on every request I make,
So that an absent, expired, or forged token cannot reach protected data.

**Acceptance Criteria:**

**Given** a valid, unexpired token
**When** `GET /api/v1/me` is called with `Authorization: Bearer <token>`
**Then** the response is `200` carrying the caller's own id, full name, email, role, department and joining date
**And** it carries no `password_hash` and no Leave Balance quantity

**Given** a request bearing no `Authorization` header
**When** any protected endpoint is called
**Then** the response is `401` with code `TOKEN_INVALID` (`FR-02`)

**Given** a token whose `exp` claim has passed
**When** any protected endpoint is called
**Then** the response is `401` with code `TOKEN_INVALID` (`FR-02`, `NFR-02`)

**Given** a token whose payload was altered to change its subject or its role
**When** any protected endpoint is called
**Then** signature verification fails and the response is `401`
**And** the altered role is never honoured (`FR-02`)

**Given** any protected endpoint
**When** the `api/` authorization dependency resolves the caller
**Then** it loads the Employee row from the database using the token's subject, and reads the caller's role from that row
**And** it relies on nothing the client sent beyond that subject (`AD-14`, `NFR-03`)

*(What happens when that row is a **since-deactivated** Employee is not fixed by any source, and no criterion is asserted for it here. `AD-14` enumerates exactly three rejection cases — a token absent, expired, or whose signature does not verify — and `AD-22`'s "a deactivated Employee cannot authenticate" governs `FR-01` login, not `FR-02` token presentation. See the unresolved-gaps list.)*

**Given** the React typed API client
**When** any request is issued
**Then** the token is attached as a Bearer header
**And** a `401` clears the stored session and returns the user to the login screen

### Story 1.4: Authorization Primitives — the Role Gate, Scoped Reads, and the 404 Convention

As a developer implementing any protected endpoint,
I want the role gate, the scoped-repository contract and the status-code semantics to exist before the first protected resource does,
So that no endpoint invents its own authorization and no later story rewrites the one that came before it.

**Acceptance Criteria:**

**Given** the `repositories/` package
**When** an architecture test inspects the signature of every getter that can return another Employee's data
**Then** each takes the acting Employee as a parameter
**And** no getter exists that returns such data without one (`AD-10`, `NFR-04`)

**Given** a scoped repository getter
**When** it executes
**Then** the actor's scope is applied as a predicate in the SQL
**And** it is never applied as a filter over rows already retrieved (`NFR-04`, architecture §7)

**Given** a resource the actor is permitted to see but not permitted to act upon
**When** the acting endpoint is called
**Then** the response is `403`, which is reserved for exactly this case (api-contracts §1)

**Given** a scoped read whose predicate matches no row
**When** the `api/` layer handles it
**Then** the response is `404`, byte-identical in body and equal in status to the response for an identifier that names nothing at all
**And** it is never `403`, which would disclose that the resource exists (`AD-10`, `FR-03`)

**Given** a restricted operation
**When** it is invoked directly, by a client that never rendered its control
**Then** it is refused in an `api/` dependency, at the API boundary
**And** `NFR-16`'s role-appropriate rendering is never the only thing preventing the action (`NFR-03`, `AD-14`)

*(This story delivers the mechanism and its unit tests. Its first scoped **resource** is a Department in Story 1.5; its first genuinely data-scoped resource — where one Employee's row is invisible to another — is a Leave Request in Epic 2. Ordering it here means Stories 1.5 and 1.6 consume these primitives rather than each inventing a role check that Story 1.7 would then rewrite.)*

### Story 1.5: Manage Departments

As an Admin,
I want to create, view, rename and remove Departments,
So that Employees can be grouped, and a Department that still holds people cannot quietly vanish.

**Acceptance Criteria:**

**Given** an authenticated Admin
**When** they call `POST /api/v1/departments` with a name
**Then** the Department is created and returned

**Given** any authenticated Employee of any role
**When** they call `GET /api/v1/departments`
**Then** the response is `200` with the list of Departments (any role, all scope, per api-contracts §4.2)

**Given** a client calling `GET /api/v1/departments` with a `page_size` larger than the server maximum
**When** the response is returned
**Then** it carries the server maximum, not the larger page
**And** the response body carries `items`, `page`, `page_size` and `total` (`NFR-11`; spine *Pagination*, which binds **every** list endpoint, and api-contracts §1)

*(The page **bound** is a spine convention and lands here, with Epic 1's first list endpoint. `FR-12`'s composable filters remain in Epic 3. The two are separate: the bound is `NFR-11`, the filters are `FR-12`.)*

**Given** an authenticated Employee or Manager, who may read Departments under `GET /api/v1/departments`
**When** they call `POST /api/v1/departments`, `PATCH /api/v1/departments/<id>` or `DELETE /api/v1/departments/<id>`
**Then** the response is `403` — a resource the actor may see but may not act upon, which is exactly what api-contracts §1 reserves `403` for
**And** the refusal happens server-side, independently of whether the client rendered the control (`NFR-03`, Story 1.4)

**Given** a Department with at least one assigned Employee
**When** an Admin calls `DELETE /api/v1/departments/<id>`
**Then** the response is `409` with code `DEPARTMENT_NOT_EMPTY`
**And** the refusal names the obstruction, and the Department is unchanged (`FR-05`)

**Given** a Department with no assigned Employee
**When** an Admin calls `DELETE /api/v1/departments/<id>`
**Then** the Department is removed

**Given** a request with no valid token
**When** any `/api/v1/departments` endpoint is called
**Then** the response is `401` (`FR-02`)

**Given** the React application
**When** an Admin opens the Departments screen
**Then** create, rename and delete controls are present, and a refused delete surfaces the message naming the obstruction (`NFR-17`)
**And** for an Employee or Manager those controls are not rendered — a usability measure that is never the only thing preventing the action (`NFR-16`)

### Story 1.6: Manage Employees and Reporting Lines

As an Admin,
I want to create, view, update and deactivate Employees — including each one's Department, role, joining date and Manager —
So that the reporting relationship every authorization decision depends on is data I control, and a departing Employee never takes their history with them.

**Acceptance Criteria:**

**Given** an authenticated Admin
**When** they call `POST /api/v1/employees` with an email, full name, role, department, joining date and **initial password**, and an optional manager
**Then** the Employee is created and active, and can immediately authenticate with that email and password
**And** assigning a manager establishes the Direct Report relationship that `FR-03` enforces (`FR-04`, api-contracts §4.2)

**Given** an Employee created by an Admin
**When** the stored row is inspected
**Then** `password_hash` holds a salted hash produced through `pwdlib`, written once from the supplied initial password
**And** no response body from any `/api/v1/employees` endpoint carries a password or a password hash (`FR-04`, `NFR-01`, `AD-14`)

**Given** an authenticated Admin
**When** they call `GET /api/v1/employees`, `GET /api/v1/employees/<id>` or `PATCH /api/v1/employees/<id>`
**Then** they may read every Employee, and may change the email address, full name, role, Department, Manager and joining date of any of them
**And** `PATCH /api/v1/employees/<id>` accepts **no** password — there is no re-issue path (`FR-04`, `FR-17`, api-contracts §4.2, PRD §6)

**Given** a client calling `GET /api/v1/employees` with a `page_size` larger than the server maximum
**When** the response is returned
**Then** it carries the server maximum, and the body carries `items`, `page`, `page_size` and `total` (`NFR-11`; spine *Pagination*)

**Given** an authenticated Employee or Manager
**When** they call any `/api/v1/employees` endpoint, all of which api-contracts §4.2 grants to the Admin alone
**Then** the response is `403` with code `ACTION_NOT_PERMITTED`, and nothing is read or written
**And** the refusal is decided by the role gate in the `api/` dependency *before any row is read*, so it never reaches the scope predicate (`G3`, api-contracts §1)

*(`403` here, `404` in Story 1.7, and the two do not conflict. The test is whether the actor's **role** admits them to the endpoint at all: if no, `403`, decided before any row is read; if yes, the scope predicate runs and a miss is `404`. `AD-10`'s `404` still means exactly one thing — outside your scope. Settled by `G3`.)*

**Given** an email address already belonging to an Employee, whether active or deactivated
**When** an Admin calls `POST /api/v1/employees` or `PATCH /api/v1/employees/<id>` with it
**Then** the response is `409` with code `EMAIL_ALREADY_IN_USE`, raised by the service before the write
**And** it is never surfaced from the `UNIQUE (email)` violation, which is a backstop and would be a `500`; and the refusal does not disclose whether the holder is active (`G2`, `AD-5`, `NFR-17`)

**Given** an Admin assigning a Manager to an Employee
**When** the assignment would make that Employee their own Manager, or would close a cycle A → B → A
**Then** the response is `400` with code `REPORTING_CYCLE`, and nothing is persisted
**And** `employee` carries `CHECK (id <> manager_id)` as a backstop, while the transitive cycle walk is the gate, in the service, inside the assignment transaction (`AD-23`, `G7`)

*(Without this, an Employee who is their own Manager approves their own Leave Requests: `FR-09` grants approval to "the Manager of the applicant" and `DR-12` derives that authority from the relationship rather than the role, so the check passes — and `SM-3` still reports green, because self-approval genuinely **is** data-scoped.)*

**Given** an Employee whom at least one **active** Employee names as their Manager
**When** an Admin calls `POST /api/v1/employees/<id>/deactivate`
**Then** the response is `409` with code `EMPLOYEE_HAS_DIRECT_REPORTS`
**And** the Employee remains active, because deactivating them would orphan their Direct Reports and cause `FR-09` to auto-approve those reports' requests with no human approver (`AD-22`)

**Given** an Employee whom at least one **active** Employee names as their Manager
**When** an Admin calls `PATCH /api/v1/employees/<id>` lowering their `role` below `MANAGER`
**Then** the response is `409` with code `EMPLOYEE_HAS_DIRECT_REPORTS`, and the role is unchanged
**And** deactivation and demotion are the two doors to the same orphaning, and both are closed (`AD-22` as amended, `G8`)

*(A demoted Manager who still holds Direct Reports is the worst of both worlds: `DR-12` says the relationship grants them authority to decide, the role gate says it does not, and their reports' Pending requests have no approver and receive no auto-approval, because `manager_id` is not NULL.)*

**Given** an Employee holding any Pending Leave Request
**When** an Admin calls `POST /api/v1/employees/<id>/deactivate`
**Then** the response is `409` with code `EMPLOYEE_HAS_PENDING_REQUESTS` (`FR-04`, `AD-22`)

*(Vacuously satisfied in this epic: no `leave_request` table exists yet, so no Employee can hold a Pending request. Epic 2's Leave Request submission story creates that table and makes this guard executable. It is asserted here because it is `FR-04`'s consequence, and re-asserted there as a running test.)*

**Given** an Employee with no active Direct Report and no Pending Leave Request
**When** an Admin deactivates them
**Then** `is_active` becomes false and the row persists
**And** the Employee can no longer authenticate, and their history is preserved rather than deleted (`FR-04`, `AD-22`)

**Given** the API surface
**When** it is enumerated
**Then** no endpoint deletes an Employee — an Employee is never physically deleted (`FR-04`)
**And** because a deactivated Employee's row persists under `UNIQUE (email)`, their email address is never reusable (ERD §4.2)

**Given** the React application and an authenticated Admin
**When** they open the Employees screen
**Then** they can create, edit and deactivate Employees, assign a Manager, and set an initial password on the create form
**And** a refused deactivation surfaces the reason, naming the blocking Direct Reports or Pending requests (`NFR-17`)
**And** a refused demotion, a duplicate email address, and a refused manager assignment each surface their reason — `EMPLOYEE_HAS_DIRECT_REPORTS`, `EMAIL_ALREADY_IN_USE`, `REPORTING_CYCLE` (`NFR-17`, `G2`, `G7`, `G8`)
**And** the Admin communicates the initial password outside LeaveFlow, which sends no email (`FR-14`, PRD §6)

### Story 1.7: Scope Authority to the Reporting Relationship

As a Manager,
I want my authority to come from the Employees who actually report to me rather than from my job title,
So that another Manager's people are, to me, indistinguishable from people who do not exist.

**Acceptance Criteria:**

**Given** a Manager and the scope resolver introduced by Story 1.4
**When** the resolver is evaluated for that Manager
**Then** the scope is the predicate `employee.manager_id = :actor_id`
**And** it is evaluated at request time, not cached from the token or from login (`DR-12`, `AD-10`)

**Given** an Employee reporting to Manager A
**When** an Admin reassigns them to Manager B through `PATCH /api/v1/employees/<id>`
**Then** the next evaluation of Manager B's scope includes that Employee, and the next evaluation of Manager A's excludes them
**And** no restart, re-login, or token refresh is required, because authority is evaluated at decision time (`DR-12`, architecture §7)

**Given** an Employee whose `manager_id` is NULL
**When** their scope membership is evaluated
**Then** they fall inside no Manager's scope
**And** `AD-22`'s deactivation guard is what prevents an Admin from creating this state for an Employee who previously had a Manager (`FR-09`, `AD-22`)

**Given** the `SM-3` coverage matrix test
**When** the test suite runs
**Then** every endpoint that accepts a resource identifier is registered in the matrix with the scope api-contracts §4 grants it
**And** an endpoint added by a later story but never registered fails the test

*(`SM-3`'s stated target is narrower than the matrix: "for every endpoint accepting a **Leave Request identifier**, an authenticated Manager who is not the applicant's Manager receives the same response as for a nonexistent request." No Leave Request exists in Epic 1, so those assertions are added by Epic 2. This story builds the harness and registers Epic 1's endpoints; it does not claim to satisfy `SM-3`, which Epic 2 does.)*

### Story 1.8: Edit My Own Name

As an Employee,
I want to correct my own Full Name,
So that I am identified correctly wherever I appear, without being able to grant myself a role or a balance.

**Acceptance Criteria:**

**Given** an authenticated Employee
**When** they call `PATCH /api/v1/me` with a full name
**Then** the response is `200` and the new name is returned by a subsequent `GET /api/v1/me` (`FR-17`)

**Given** an authenticated Employee
**When** they call `PATCH /api/v1/me` with an email address, role, department, manager, joining date, or any Leave Balance quantity
**Then** the response is `400` with code `FORBIDDEN_FIELD`, whose `details` names the rejected fields, and nothing is persisted
**And** `full_name` is the only field the endpoint accepts (`FR-17`, api-contracts §4.1, `G5`)

*(`400` and not `403`: the actor is permitted both the endpoint and the resource — it is their own profile — and the domain refuses the **content** of the request. FastAPI's default `422` is suppressed for this endpoint so the `{ code, message, details }` envelope holds, per api-contracts §2. Settled by `G5`.)*

**Given** two Employees
**When** one calls `PATCH /api/v1/me`
**Then** only the authenticated caller's own record changes
**And** no endpoint exists by which an Employee edits another Employee's profile (`FR-17`)

**Given** an Employee whose email address must change
**When** the change is made
**Then** it is made by an Admin through `PATCH /api/v1/employees/<id>`
**And** never through `/api/v1/me` — the Email Address is a credential identity maintained by the Admin (`FR-04`, `FR-17`)

**Given** the routed API surface
**When** it is enumerated
**Then** no endpoint permits an Employee to change their own password
**And** a password is a credential rather than a profile field, so `FR-17`'s editable surface remains Full Name alone (`FR-17` Notes, PRD §6)

**Given** the React application and an authenticated Employee
**When** they open their profile screen
**Then** email, role, Department, Manager and joining date are shown read-only, and Full Name alone is editable (`NFR-16`)

---

## Epic 2: Trustworthy Leave Balances and the Request Lifecycle

An Admin configures the Leave Policy and the Company Holiday calendar as data, without a code change. Every Employee holds a balance that stays correct across proration, carry-forward and the Leave Year boundary. An Employee sees what a request will cost — weekends and named holidays excluded — before committing to it, and applies against a balance that cannot go negative even under concurrent submission. A Manager decides their own reports' requests, and only theirs. Approved leave can be cancelled through a Cancellation Request an Admin decides. Every state transition is attributable to an actor and a moment.

Four of the five correctness success metrics land in this epic: `SM-1` (balance arithmetic), `SM-2` (day count at the boundaries), `SM-4` (audit one-to-one), `SM-5` (policy is data).

**The two gaps that would have become reachable here are now closed.** `G7` (a self-managed Employee approving their own leave) is resolved by `AD-23`; `G8` (demoting a Manager who still holds Direct Reports) is resolved by the amended `AD-22`. Both guards live in Epic 1's Story 1.6, where the reporting relationship is set — deliberately upstream of the approval path this epic builds, because that is where the invalid state would otherwise be created. Neither was ever able to block story creation; both would have shipped a correctness defect with every declared metric green.

### Story 2.1: Leave Types as Configuration

As an Admin,
I want to define Leave Types and their attributes as data,
So that changing leave policy is configuration rather than a code change.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `leave_type` carries `code`, `name`, `annual_entitlement`, `carries_forward`, a nullable `carry_forward_cap`, and `requires_supporting_document`, with `UNIQUE (code)`
**And** it is a table, never a PostgreSQL `ENUM` and never a Python `Enum` (`FR-06`, `AD-11`, `DR-11`)

**Given** the seed command
**When** it runs
**Then** `EL`, `CL` and `FL` exist, each with `requires_supporting_document` set to **false**
**And** no Alembic migration inserts a Leave Type row (`AD-11`, spine *Seeding*)

**Given** an authenticated Admin
**When** they call `POST /api/v1/leave-types` with a fourth type
**Then** it is created and returned by `GET /api/v1/leave-types`
**And** no schema migration was required (`SM-5`)

**Given** any authenticated Employee of any role
**When** they call `GET /api/v1/leave-types`
**Then** the response is `200` (any role, all scope, api-contracts §4.3)

**Given** the React application and an authenticated Admin
**When** they open the Leave Types screen
**Then** they can view and create Leave Types and set each attribute (`NFR-16`)

### Story 2.2: The Company Holiday Calendar

As an Admin,
I want to maintain the calendar of days the organization does not work,
So that no Employee spends leave on a day nobody was working anyway.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `company_holiday` carries `holiday_date` of type `DATE` and `name`, with `UNIQUE (holiday_date)`
**And** no column scopes a holiday to a Department or a location — the calendar is global (`FR-10`, ERD §3)

**Given** a Company Holiday
**When** it is stored, compared or transported
**Then** it is a calendar `DATE` and never a `TIMESTAMPTZ`, and the API transports it as `YYYY-MM-DD` (`AD-12`, `DR-2a`)

**Given** an authenticated Admin
**When** they call `POST /api/v1/holidays` or `DELETE /api/v1/holidays/<id>`
**Then** the holiday is added or removed
**And** any authenticated role may call `GET /api/v1/holidays` (api-contracts §4.3)

**Given** the React application and an authenticated Admin
**When** they open the Holidays screen
**Then** they can add and delete holidays for a Leave Year

*(Adding or deleting a holiday also recalculates existing Leave Requests. That behavior needs `leave_request` and `leave_balance`, so it lands in Story 2.11. Until then no request exists to recalculate.)*

### Story 2.3: The Leave Day Count — One Implementation, Nowhere Else

As an Employee,
I want a request to cost only the working days inside its range,
So that a weekend or a company holiday never comes out of my balance.

**Acceptance Criteria:**

**Given** `domain/calendar.py`
**When** it is inspected
**Then** it exposes exactly one function, `count_leave_days`, taking a date range and the holiday calendar and returning a whole number
**And** it imports no ORM, no web framework and performs no I/O (`AD-1`, `AD-2`, `NFR-08`, `DR-2`)

**Given** a Friday-to-Tuesday range spanning a Saturday, a Sunday, and a Monday that is a Company Holiday
**When** the count is computed
**Then** it is `2` (`FR-08`, `SM-2`)

**Given** a range consisting only of weekend days and Company Holidays
**When** the count is computed
**Then** it is `0` (`SM-2`)

**Given** a range that begins and ends on non-working days, and a single-day range
**When** each count is computed
**Then** both are correct at the boundary (`SM-2`)

**Given** `tests/domain/`
**When** the test suite runs
**Then** these tests pass with **no database fixture** (`SM-2`, `NFR-15`, spine *Testing*)

**Given** the frontend source
**When** it is searched
**Then** no module references a weekday or a Company Holiday — the client never computes a day count (`AD-2`)

### Story 2.4: Leave Balances — Three Quantities, One Derived

As an Employee,
I want my balance expressed as what I was granted, what is committed, and what is spent,
So that the number I act on is the number I can actually spend.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `leave_balance` carries `accrued`, `reserved`, `consumed`, `prorated_entitlement`, `carried_forward`, `entitlement_basis` and `leave_year`, all `INTEGER`
**And** it carries `CHECK (accrued - consumed - reserved >= 0)`, `CHECK (reserved >= 0 AND consumed >= 0)`, `CHECK (accrued = prorated_entitlement + carried_forward)` and `UNIQUE (employee_id, leave_type_id, leave_year)`, and **no `available` column** (`AD-5`, `DR-3`)

**Given** an Employee joining in September and a Leave Type with an Annual Entitlement of 12
**When** their balance is materialized
**Then** `prorated_entitlement` is `4` — `12 × 4/12`, counting the joining month through December inclusive, rounded **down**
**And** a computed entitlement of `4.16` yields `4`; the rounding is never to nearest (`DR-9`, spine *Proration*)

**Given** an Admin creates an Employee, or creates a Leave Type
**When** the command commits
**Then** a `leave_balance` row exists for that Employee and every Leave Type, for the current Leave Year
**And** a Leave Type created after the fact has a balance to be applied for, which is what `SM-5` requires

**Given** the module that owns balance mutation
**When** it is inspected
**Then** it exposes exactly `reserve`, `consume_reserved`, `consume_direct`, `release_reserved`, `release_consumed`, `adjust_reserved`, `adjust_consumed` and `set_accrual`
**And** no route, repository, job or other service writes a balance column (`AD-17`)

**Given** an authenticated Employee
**When** they call `GET /api/v1/balances`
**Then** each Leave Type returns `available` as the primary figure with `reserved` and `consumed` alongside it
**And** `available` is derived as `accrued − consumed − reserved` and never read from a column (`FR-07`, `DR-3`)

**Given** a Manager or an Admin
**When** they call `GET /api/v1/employees/<id>/balances`
**Then** a Manager sees only their Direct Reports, and an Admin sees anyone (`FR-03`, `AD-10`)

**Given** the React application and an authenticated Employee
**When** they open their dashboard
**Then** each Leave Type shows Available prominently, with Reserved disclosed alongside it (`FR-07`)

### Story 2.5: See What a Request Will Cost Before Committing to It

As an Employee,
I want to see the day count and my projected balance before I submit,
So that I understand what the request costs, and why it costs less than the calendar span suggests.

**Acceptance Criteria:**

**Given** an authenticated Employee and a date range
**When** they call `POST /api/v1/leave-requests/preview`
**Then** the response carries `leave_days`, `available_before` and `available_after`
**And** `excluded_dates` names each excluded date with a reason of `WEEKEND` or `HOLIDAY`, and a holiday carries its name (`FR-08`, api-contracts §4.5)

**Given** the client
**When** it needs a day count anywhere
**Then** it obtains it from this endpoint and from no other source (`AD-2`)

**Given** a preview response
**When** a request is later submitted
**Then** the previewed value is advisory only, and never decides admission (`AD-3`)

**Given** the React application and an Employee selecting a range containing a Company Holiday
**When** the preview returns
**Then** the day count resolves to a number smaller than the number of dates picked, and the excluded holiday is **named on screen** rather than silently netted out (`UJ-1`)

### Story 2.6: Submit a Leave Request

As an Employee,
I want to apply for leave and have its days reserved immediately,
So that a request I have made cannot be spent twice.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `leave_request` carries `start_date` and `end_date` as `DATE`, `leave_days` as `INTEGER`, and `status` as `TEXT` with `CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED'))`, plus `CHECK (end_date >= start_date)` and `CHECK (leave_days > 0)`
**And** it carries no `created_at` and no `leave_year` column (ERD §2.1, §4.5)

**Given** the first state transition in the system
**When** `audit_entry` is created by this story
**Then** it carries `subject_type`, `subject_id`, `from_state`, `to_state`, `actor_type`, `actor_id`, `reason`, `occurred_at`, with `CHECK ((actor_type = 'SYSTEM') = (actor_id IS NULL))`
**And** the application's database role is granted `INSERT` and `SELECT` on it and **neither `UPDATE` nor `DELETE`**, with migrations running as the owner (`AD-8`, `AD-9`)

**Given** an authenticated Employee with a Manager
**When** they call `POST /api/v1/leave-requests`
**Then** `leave_days` is computed once by Story 2.3's function and stored, and no read path ever recomputes it (`FR-08`, `AD-18`)
**And** the balance row is acquired with `SELECT ... FOR UPDATE`, `available` is computed from that locked row inside that transaction, the days are `reserve`d, and one Audit Entry is written in the same transaction (`FR-08`, `AD-3`, `AD-8`)

**Given** a submission the domain refuses
**When** the response is returned
**Then** it is `400` carrying the matching code: `INSUFFICIENT_BALANCE` naming `days_requested` and `days_available`; `SPANS_TWO_LEAVE_YEARS` naming the boundary; `ZERO_LEAVE_DAYS`; `INVALID_DATE_RANGE`; or `PAST_DATE_RANGE`
**And** the refusal is raised by the service inside the lock, never surfaced from a `CHECK` violation, which would be a defect and a `500` (`FR-08`, `AD-5`, `NFR-17`)

**Given** an applicant whose `manager_id` is NULL
**When** they submit
**Then** the request is admitted directly as `APPROVED`, consuming its days through `consume_direct` without ever touching `reserved`
**And** its Audit Entry names actor type `SYSTEM` and reason `AUTO_APPROVED_NO_MANAGER`, and the Available check still applied (`FR-09`, `AD-17`)

**Given** two concurrent submissions that would together exceed Available
**When** both are attempted against real PostgreSQL
**Then** exactly one succeeds and the other is refused with `INSUFFICIENT_BALANCE`
**And** the balance is neither negative nor double-counted (`SM-1`, `NFR-07`, spine *Testing*)

**Given** an Employee holding a Pending Leave Request
**When** an Admin attempts to deactivate them
**Then** the response is `409` with `EMPLOYEE_HAS_PENDING_REQUESTS` — Story 1.6's criterion becomes executable here (`AD-22`)

**Given** the React application and an authenticated Employee
**When** they submit a request
**Then** their Available balance falls immediately by the reserved days, and a refusal states its numbers (`NFR-17`)

### Story 2.7: Decide a Request — Approve, Reject, Cancel

As a Manager,
I want to approve or reject the requests of my own Direct Reports,
So that a decision is made by someone with the authority to make it.

**Acceptance Criteria:**

**Given** a Pending request and its applicant's current Manager
**When** the Manager calls `POST /api/v1/leave-requests/<id>/approve` or `.../reject`
**Then** approval moves the days from `reserved` to `consumed` via `consume_reserved`, and rejection releases them via `release_reserved`
**And** each transition writes exactly one Audit Entry naming that Manager and the moment (`FR-09`, `AD-17`, `AD-8`)

**Given** any transition of a Leave Request
**When** it is performed
**Then** it is a single `UPDATE ... SET status = :to WHERE id = :id AND status = :from`
**And** zero affected rows means the transition is refused with `409 TRANSITION_NOT_ALLOWED` and the transaction rolls back — a Manager approving a request the applicant has just cancelled receives a failure, not a silent overwrite (`AD-4`, `FR-09`)

**Given** the applicant
**When** they call `POST /api/v1/leave-requests/<id>/cancel` on their own Pending request
**Then** the reservation is released
**And** no other Employee can cancel it, and it cannot be cancelled once it leaves `PENDING` (`FR-09`)

**Given** an authenticated caller
**When** they call `GET /api/v1/leave-requests`, optionally filtered by `status`
**Then** an Employee receives their own Leave Requests, a Manager receives their Direct Reports', and an Admin receives all — the scope applied as a SQL predicate, never as a post-filter
**And** the response carries `items`, `page`, `page_size` and `total`, bounded by the server maximum (`FR-03`, `AD-10`, `NFR-04`, `NFR-11`)

**Given** an authenticated caller and a Leave Request identifier inside their scope
**When** they call `GET /api/v1/leave-requests/<id>`
**Then** the request is returned with its Leave Type, date range, stored `leave_days` and current state
**And** `leave_days` is the value stored at admission and is never recomputed (`AD-18`)

*(**These two read endpoints land here, not in Epic 3, because this epic's own acceptance criteria require them:** a Manager cannot "open their queue" and an Employee cannot "view an Approved future-dated request" without them. What Epic 3's Story 3.1 adds is `FR-12`'s composable filters — `leave_type_id`, `date_from`, `date_to` — and `FR-20`'s cross-Leave-Year history view. This is the same seam already used to split `NFR-11`'s server page bound, delivered in Story 1.5, from `FR-12`'s filters. Epic 2 delivers the `FR-03`-scoped read; Epic 3 delivers the `FR-12`/`FR-20` capability on top of it.)*

**Given** an Admin
**When** they attempt to approve or reject any Leave Request
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — an Admin may read every request and decide none (`DR-13`, api-contracts §1)

**Given** a Manager who is not the applicant's Manager
**When** they call any endpoint naming that Leave Request's identifier — including `GET /api/v1/leave-requests/<id>`, `approve`, `reject` and `cancel`
**Then** the response is `404`, byte-identical to a nonexistent identifier
**And** the endpoint is registered in Story 1.7's `SM-3` matrix, which this story populates (`FR-03`, `AD-10`, `SM-3`)

*(`404` and not `403`, and the two do not conflict: the Manager's **role** admits them to this endpoint, so the scope predicate runs, and a miss is `404`. Story 1.6's `403` is a **role** denial decided before any row is read. Settled by `G3`.)*

**Given** a Pending request whose applicant is reassigned to a different Manager
**When** the new Manager decides it
**Then** the decision succeeds, because authority is evaluated at decision time rather than at submission (`DR-12`)

**Given** the React application and an authenticated Manager
**When** they open their queue
**Then** they see the requests awaiting their decision, and can approve or reject each

### Story 2.8: Cancel Approved Leave through a Cancellation Request

As an Employee,
I want to ask for approved leave to be cancelled when my plans change,
So that days I will not take are returned to my balance.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `cancellation_request` is its own table with `leave_request_id` and a `status` of `PENDING`, `APPROVED` or `REJECTED`
**And** it is not a fifth Leave Request status, which is what makes "Approved, with a cancellation pending" representable (`AD-13`, `DR-14`)

**Given** the applicant and their own Approved request whose dates lie in the future
**When** they call `POST /api/v1/leave-requests/<id>/cancellation-requests`
**Then** a Pending Cancellation Request is created
**And** no other Employee may raise one (`FR-09`)

**Given** an Approved request whose dates have already passed
**When** a Cancellation Request is raised against it
**Then** the response is `400` with `LEAVE_ALREADY_TAKEN` (`DR-14`)

**Given** a Pending Cancellation Request
**When** its target is inspected
**Then** the Leave Request remains `APPROVED` and its days remain `consumed` (`AD-13`)

**Given** an authenticated caller
**When** they call `GET /api/v1/cancellation-requests`, optionally filtered by `status`
**Then** an Admin receives every Cancellation Request and an Employee receives only their own, the scope applied as a SQL predicate
**And** the response carries `items`, `page`, `page_size` and `total` (`DR-14`, `AD-10`, `NFR-11`, api-contracts §4.6)

*(**Without this endpoint an Admin cannot discover that a Cancellation Request exists.** No notification is addressed to an Admin — `FR-14`'s three kinds all target the Manager or the applicant — and the Admin dashboard's Pending count is a count of **Leave** Requests. The only remaining route to `POST /cancellation-requests/<id>/approve` would be to guess a `uuidv7` primary key that the ERD deliberately made non-enumerable so `AD-10`'s `404` stays honest. `D-07` once ruled approved-leave cancellation out of scope precisely because "the specification authorizes no role to do it"; `DR-14` reversed that so `BR-05` would be a live rule rather than documented-but-unreachable policy. This endpoint is what keeps it reachable.)*

**Given** an Admin
**When** they call `POST /api/v1/cancellation-requests/<id>/approve`
**Then** the targeted Leave Request moves to `CANCELLED` and its days are returned through `release_consumed`, restoring Available (`BR-05`, `AD-17`)

**Given** an Admin
**When** they call `POST /api/v1/cancellation-requests/<id>/reject`
**Then** the Cancellation Request moves to `REJECTED` and the targeted Leave Request remains `APPROVED` with its days still `consumed` — a rejection changes nothing about the leave itself (`FR-09`, `AD-13`)

**Given** any caller whose role is not Admin
**When** they call `POST /api/v1/cancellation-requests/<id>/approve` or `.../reject`
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — only an Admin decides a Cancellation Request (`FR-09`, `DR-13`, `G3`)

**Given** an approved Cancellation Request
**When** the Audit Entries are counted
**Then** there is one for the Cancellation Request's own transition and one for the Leave Request's move to `CANCELLED`, discriminated by `subject_type` (`AD-8`, `DR-14`)

**Given** the React application and an authenticated Employee
**When** they view an Approved future-dated request
**Then** they can raise a Cancellation Request, and see its state while an Admin decides it

**Given** the React application and an authenticated Admin
**When** they open the Cancellation Requests screen
**Then** they see every Pending Cancellation Request, each naming its applicant, the targeted Leave Request and its dates, and can approve or reject it
**And** this is the Admin's only route to a Cancellation Request, because none is announced to them by notification or dashboard (`FR-09`, `DR-14`)

### Story 2.9: The Audit Trail

As an Admin,
I want an append-only record of every state transition,
So that a disagreement about what was approved is settled by the system rather than by whoever kept better notes.

**Acceptance Criteria:**

**Given** an authenticated Admin
**When** they call `GET /api/v1/audit-entries`
**Then** the response is `200`, and every entry names its subject, the transition, the actor and the timestamp

**Given** an authenticated Employee or Manager
**When** they call `GET /api/v1/audit-entries`
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — full audit-log read access is the Admin's alone (`FR-16`, `DR-13`, `G3`)

**Given** the application's database role
**When** it attempts `UPDATE` or `DELETE` on `audit_entry`
**Then** the database refuses, because the grant was never made
**And** no repository exposes an update or delete method for it, and Alembic migrations run under the owner role (`AD-9`, `NFR-09`)

**Given** the full test suite
**When** Audit Entries are counted against state transitions
**Then** the counts are equal, one-to-one (`SM-4`, `DR-16`)

**Given** a transition whose transaction rolls back
**When** the audit log is read
**Then** no entry exists for it, because the row was inserted inside that transaction (`AD-8`)

**Given** an Audit Entry written by the managerless auto-approval path
**When** it is inspected
**Then** `actor_type` is `SYSTEM`, `actor_id` is NULL, and `reason` is `AUTO_APPROVED_NO_MANAGER`
**And** no human approver is fabricated (`FR-16`)

### Story 2.10: The Leave Year Rollover

As an Admin,
I want unused Earned Leave to carry forward and lapsing types to lapse at the year boundary,
So that the organization begins each Leave Year with balances that are right.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `rollover_run` carries `leave_year` and `occurred_at`, and is append-only
**And** the application's database role is granted `INSERT` and `SELECT` on it and **neither `UPDATE` nor `DELETE`**, with migrations running as the owner (`AD-8`, `AD-9`, `NFR-09`)

**Given** the rollover
**When** it is invoked
**Then** it is the CLI entrypoint `python -m app.jobs.rollover --year YYYY`, called by an external scheduler
**And** no scheduler is registered inside the FastAPI application, and no endpoint triggers it (`AD-7`)

**Given** a Leave Year `Y` and a Leave Type whose `carries_forward` is true
**When** the rollover runs
**Then** `carried_forward(Y+1) = min(carry_forward_cap, available(Y))`, written by assignment rather than by increment
**And** the excess above the cap lapses (`FR-07`, `AD-6`, `DR-7`)

**Given** a Leave Type whose `carries_forward` is false
**When** the rollover runs
**Then** its unused days lapse
**And** the behaviour was decided by reading the attribute, not by testing the Leave Type's name — `EL` carries forward, `CL` and `FL` lapse (`FR-07`, `DR-11`, `AD-11`)

**Given** the rollover has already run for a Leave Year
**When** it runs again against the same year
**Then** nothing changes, because it assigns a derived value rather than accumulating one (`AD-6`)

**Given** a Pending request holding Reserved days in Leave Year `Y` across the boundary
**When** it is later rejected or cancelled
**Then** its days do not lapse at the boundary, `available(Y)` rises, and `carried_forward(Y+1)` is recomputed and tops up
**And** approval leaves `available(Y)` unchanged, so carry-forward is never clawed back (`DR-7a`, `AD-6`)

**Given** a fourth Leave Type created through `POST /leave-types` with `carries_forward` true
**When** the rollover runs
**Then** its unused days carry forward, with no code change and no schema migration between creating it and rolling it over (`SM-5`)

**Given** the rollover
**When** it records its execution
**Then** it writes to `rollover_run` and never to `audit_entry`, because it transitions no Leave Request and `SM-4`'s one-to-one count must stay true (`AD-8`)

**Given** a test
**When** it calls the rollover
**Then** it runs with no server and no clock manipulation (`AD-7`, `NFR-15`)

### Story 2.11: A Holiday Change Recalculates, and May Be Refused

As an Admin,
I want a change to the holiday calendar to correct the requests it affects,
So that a day the organization declared a holiday is not still charged against someone's balance.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `admin_review_flag` exists, carrying the `employee_id` and `leave_type_id` pair it left unchanged, the `leave_year`, a `cause`, and `occurred_at`
**And** it is not `audit_entry`, and no endpoint updates or deletes a row in it (`AD-20`, `AD-8`)

**Given** a Pending Leave Request whose date range contains the added or deleted holiday
**When** an Admin calls `POST /api/v1/holidays` or `DELETE /api/v1/holidays/<id>`
**Then** that request's `leave_days` and its Reserved days are recalculated (`FR-10`, `AD-19`)

**Given** an Approved Leave Request whose dates lie wholly in the future
**When** the holiday calendar changes inside its range
**Then** its `leave_days` and the applicant's balance are recalculated
**And** an Approved request whose dates have already passed is **never** recalculated (`AD-18`, `FR-10`)

**Given** a recalculation that would drive Available negative in the edited Leave Year or in any materialized later one
**When** the forward check runs inside the same transaction
**Then** that **Employee and Leave Type pair** is left entirely unchanged, the same Employee's other Leave Types still proceed, and the rest of the operation succeeds
**And** the endpoint returns `200` with a summary rather than failing wholesale (`AD-19`, api-contracts §4.3)

**Given** a refused recalculation
**When** it occurs
**Then** a row is written to `admin_review_flag` carrying its cause and the Employee and Leave Type it left unchanged
**And** the refusal was discovered by the forward check, never by an `AD-5` `CHECK` violation (`AD-19`, `AD-20`)

**Given** an authenticated Admin
**When** they call `GET /api/v1/admin-review-flags`
**Then** they read the recorded refusals
**And** no endpoint clears a flag — `FR-10` grants the read and no requirement grants a resolve (`AD-20`)

**Given** an authenticated Employee or Manager
**When** they call `GET /api/v1/admin-review-flags`
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` — only an Admin reads the recorded refusals (`FR-10`, `AD-20`, `G3`)

**Given** the React application and an authenticated Admin who has just added or deleted a holiday
**When** the `200` summary returns
**Then** the screen states how many Employee-and-Leave-Type pairs were recalculated and how many were **left unchanged**, naming each refused pair
**And** the Admin is never shown an unqualified success for an operation that partially refused (`FR-10`, `AD-19`, `NFR-17`)

*(This is the criterion that keeps PRD §1's promise. A refusal recorded where nobody looks is a balance the Admin believes is right and is not — "a leave balance that is wrong is worse than a leave balance that is absent, because it will be believed.")*

**Given** the React application and an authenticated Admin
**When** they open the Review Flags screen
**Then** they see every recorded refusal with its cause, the Employee and Leave Type it left unchanged, and when it occurred
**And** no control clears a flag, because no requirement grants a resolve (`AD-20`)

### Story 2.12: Change Leave Policy with an Explicit Disposition

As an Admin,
I want to be forced to choose what happens to existing balances when I change policy,
So that the system never silently decides on my behalf.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `policy_change` exists, carrying `leave_type_id`, the `attribute` changed, its `old_value` and `new_value`, the `disposition`, and `occurred_at`, with `CHECK (disposition IN ('RECALCULATE','PRESERVE'))`
**And** it carries **no actor column, by decision**, and it is not `audit_entry` (`AD-20`, `AD-8`)

*(`policy_change` and holiday edits are deliberately unattributed. PRD §1 was narrowed to promise attribution for Leave Request state changes only, rather than widening `FR-16` and `NFR-19` — architecture §9, defect 5.)*

**Given** a Leave Type change that would affect existing Leave Balances
**When** an Admin calls `PATCH /api/v1/leave-types/<id>` without a disposition
**Then** the response is `400` with `POLICY_DISPOSITION_REQUIRED`, and nothing is applied (`FR-06`, api-contracts §4.3)

**Given** an Admin supplying a disposition of `RECALCULATE` or `PRESERVE`
**When** the change is applied
**Then** a `policy_change` row records the Leave Type, the attribute, its old and new values, the disposition and the moment
**And** it carries **no actor column**, by decision — PRD §1 promises attribution for Leave Request state changes only (`AD-20`)

**Given** the disposition `PRESERVE`
**When** the change is applied
**Then** existing balances remain as accrued under `entitlement_basis`, and only future accruals use the new value (`FR-06`, `AD-5`)

**Given** the disposition `RECALCULATE`
**When** the change is applied
**Then** `accrued`, `prorated_entitlement` and `carried_forward` are re-derived from `entitlement_basis` in one statement, `AD-19`'s forward check runs, and a pair it would drive negative is left unchanged and flagged under `AD-20`
**And** the same guard governs it as governs a holiday change (`FR-06`, `AD-19`)

**Given** a change to `carry_forward_cap` or `annual_entitlement`
**When** it commits
**Then** `AD-6`'s carry-forward recomputation is triggered explicitly, because a policy change is not a balance change and would otherwise never fire (`AD-6`)

**Given** an authenticated Admin
**When** they call `GET /api/v1/policy-changes`
**Then** they read the recorded changes and their dispositions (api-contracts §4.3)

**Given** an authenticated Employee or Manager
**When** they call `GET /api/v1/policy-changes`
**Then** the response is `403` with code `ACTION_NOT_PERMITTED` (`G3`)

**Given** a fourth Leave Type created entirely through configuration
**When** it is applied for, reserved against, approved, and rolled over at the Leave Year boundary
**Then** every step succeeds with no code change and no schema migration (`SM-5`)

**Given** the React application and an authenticated Admin editing a Leave Type
**When** the change would affect existing Leave Balances
**Then** the form **requires** them to choose `RECALCULATE` or `PRESERVE` before it will submit, and states in plain language what each does to existing balances
**And** without this the Admin can create a Leave Type but never successfully edit one, because every edit returns `POLICY_DISPOSITION_REQUIRED` (`FR-06`, `NFR-16`, `NFR-17`)

**Given** the React application and an authenticated Admin who chose `RECALCULATE`
**When** the `200` summary returns
**Then** the screen names every Employee-and-Leave-Type pair the forward check refused and left unchanged, exactly as a holiday edit does in Story 2.11 (`AD-19`, `AD-20`, `NFR-17`)

**Given** the React application and an authenticated Admin
**When** they open the Policy Changes screen
**Then** they see each recorded change, its old and new value, and the disposition applied (api-contracts §4.3)

---

## Epic 3: Visibility and Decision Support

Each role opens a dashboard scoped to what that role can act on. A Manager sees which of their other Direct Reports are already away on the requested dates *at the moment of decision*, rather than discovering the overlap the following week. Employees see their own history across Leave Years; Managers see their team. Notifications close the loop: the Manager learns a decision is waiting, and the applicant learns it was made. Every list is filtered, composable, and bounded by the server.

`FR-18` exists so that `BR-06`'s "no restriction on overlapping leave" is an informed choice rather than an unnoticed one. `FR-11` ships summary cards with a date-range filter — **charts and trend lines are out of scope**, per PRD §7.4 and counter-metric `SM-C2`.

### Story 3.1: My Leave History, Filtered and Bounded

As an Employee,
I want to see every Leave Request I have ever made, filtered and paged,
So that I can answer what I took, when, and what it cost, without asking anyone.

**Acceptance Criteria:**

*(This story **extends** the `FR-03`-scoped `GET /api/v1/leave-requests` and `GET /api/v1/leave-requests/<id>` that Story 2.7 delivers. It adds `FR-12`'s composable filters and `FR-20`'s cross-Leave-Year history. It does not introduce the endpoints.)*

**Given** an authenticated Employee
**When** they call `GET /api/v1/leave-requests`
**Then** the response contains every Leave Request they have submitted, **across every Leave Year**, in every state, including `CANCELLED` and `REJECTED`
**And** each entry shows the Leave Type, the date range, the Leave Day count and the current state (`FR-20`)

**Given** any list response
**When** it is inspected
**Then** it carries `items`, `page`, `page_size` and `total`, and a client requesting a `page_size` above the server maximum receives the maximum (`NFR-11`, `FR-12`)

**Given** the filters `status`, `leave_type_id`, `date_from` and `date_to`
**When** they are applied together
**Then** they compose, and the result is the intersection
**And** Story 2.7 delivered `status` alone; `leave_type_id`, `date_from` and `date_to` are added here (`FR-12`)

**Given** a Manager filtering across every Department
**When** the results return
**Then** they contain only that Manager's Direct Reports — filtering never widens authorization
**And** an Employee sees only their own, and an Admin sees anyone's (`FR-12`, `FR-03`, `AD-10`)

**Given** a Leave Request identifier outside the caller's scope
**When** they call `GET /api/v1/leave-requests/<id>`
**Then** the response is `404`, byte-identical to a nonexistent identifier (`AD-10`, `SM-3`)

**Given** any history entry
**When** its Leave Day count is read
**Then** it is the value stored on the request at admission, never recomputed against today's holiday calendar (`AD-18`)

**Given** the React application and an authenticated Employee
**When** they open their history
**Then** they can filter by type, state and date range, and page through the results

### Story 3.2: My Team

As a Manager,
I want to see the Employees who report to me,
So that I know whose leave is mine to decide.

**Acceptance Criteria:**

**Given** an authenticated Manager
**When** they call `GET /api/v1/team`
**Then** the response contains exactly their Direct Reports and no other Employee (`FR-19`, `AD-10`)

**Given** each entry in that list
**When** it is inspected
**Then** it identifies the Employee by Full Name and names their Department (`FR-19`)

**Given** a Direct Report who has been deactivated
**When** the list is returned
**Then** they are distinguishable from an active one (`FR-19`)

**Given** an Employee or an Admin
**When** they call `GET /api/v1/team`, which api-contracts §4.9 grants to a Manager
**Then** the response is `403` with code `ACTION_NOT_PERMITTED`, decided by the role gate before any row is read (`G3`, api-contracts §1)

**Given** the React application and an authenticated Manager
**When** they open their team screen
**Then** they see their Direct Reports with Department and active state

### Story 3.3: The Department Leave Calendar, at the Moment of Decision

As a Manager,
I want to see who else on my team is already away on the dates I am deciding,
So that I authorize an overlap knowingly rather than discover it the following week.

**Acceptance Criteria:**

**Given** an authenticated Manager and a date range
**When** they call `GET /api/v1/calendar`
**Then** the response contains the leave of their Direct Reports across that range, and of no other Employee (`FR-18`, `AD-10`)

**Given** the calendar
**When** it is rendered
**Then** Approved and Pending leave are both shown, visually distinguished from one another (`FR-18`)

**Given** a Manager opening a Pending Leave Request to decide it
**When** the approval screen renders
**Then** the calendar for that request's dates is presented inline on the same screen (`FR-18`, `UJ-2`)

**Given** two Direct Reports already approved as away on a requested date
**When** the Manager approves the request under decision
**Then** the approval succeeds
**And** the overlap produced no warning, no block, and no required acknowledgement — the system informs, and never blocks (`BR-06`, `DR-15`)

**Given** any leave shown on the calendar
**When** its day count is read
**Then** it is the value stored on the request, never recomputed (`AD-18`)

### Story 3.4: In-App Notifications

As a Manager,
I want to learn that a decision is waiting for me, and as an applicant to learn that mine was made,
So that a request that reaches nobody stops being an email in a different costume.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `notification` carries `recipient_employee_id`, `leave_request_id`, a `kind` of `REQUEST_SUBMITTED`, `REQUEST_APPROVED` or `REQUEST_REJECTED`, a nullable `read_at`, and `created_at`
**And** a partial index exists on `recipient_employee_id WHERE read_at IS NULL` (`AD-16`, ERD §4.4)

**Given** an Employee with a Manager submitting a Leave Request
**When** the submission commits
**Then** exactly one Notification of kind `REQUEST_SUBMITTED` exists, addressed to that Manager
**And** it was written by the service performing the transition, inside that transition's transaction, so a rolled-back submission leaves none (`AD-16`, `FR-14`)

**Given** a Leave Request approved or rejected
**When** the transition commits
**Then** exactly one Notification exists, addressed to the applicant, of kind `REQUEST_APPROVED` or `REQUEST_REJECTED` (`FR-14`)

**Given** an applicant with no Manager whose request is auto-approved
**When** the notifications are counted
**Then** the applicant holds one `REQUEST_APPROVED` Notification, and no `REQUEST_SUBMITTED` Notification exists, because it would have no addressee (`FR-09`, `FR-14`)

**Given** an authenticated Employee
**When** they call `GET /api/v1/notifications` or `GET /api/v1/notifications/unread-count`
**Then** they see only Notifications addressed to them
**And** the unread count is computed as `COUNT(*) WHERE read_at IS NULL` and is never stored (`AD-16`)

**Given** an addressee
**When** they call `PATCH /api/v1/notifications/<id>/read`, twice
**Then** the Notification is marked read and the unread count decrements once
**And** marking read is idempotent, and no Employee other than the addressee may do it (`FR-14`, `AD-16`)

**Given** the React application
**When** an Employee is authenticated
**Then** an unread count is visible, and opening a Notification marks it read

### Story 3.5: A Dashboard per Role

As a user of any role,
I want a dashboard scoped to what I can act on,
So that the first screen I see answers the question my role actually asks.

**Acceptance Criteria:**

**Given** an authenticated Employee
**When** they call `GET /api/v1/dashboard/employee`
**Then** the response presents, per Leave Type, Available, Reserved and Consumed, plus a count of their Pending requests (`FR-11`)

**Given** an authenticated Manager
**When** they call `GET /api/v1/dashboard/manager`
**Then** the response presents a count of Leave Requests awaiting their decision, and their Direct Reports on approved leave within the next seven days (`FR-11`, `AD-10`)

**Given** an authenticated Admin
**When** they call `GET /api/v1/dashboard/admin`
**Then** the response presents organization-wide totals: Employees on approved leave today, and the Pending request count (`FR-11`)

**Given** any dashboard endpoint and a `date_from` and `date_to`
**When** the figures are computed
**Then** they are those falling inside the selected range (`FR-11`, api-contracts §4.9)

**Given** a Manager calling `GET /api/v1/dashboard/employee`
**When** the response returns
**Then** it carries their own balances, not their reports'
**And** an Employee calling `GET /api/v1/dashboard/manager` receives `403` with code `ACTION_NOT_PERMITTED` (`FR-11`, `FR-03`, `G3`)

**Given** the React application
**When** any dashboard renders
**Then** it presents summary cards with a date-range filter
**And** it presents no chart and no trend line, which are out of scope (PRD §7.4, `SM-C2`)
**And** it is usable at desktop and tablet widths (`NFR-18`)

---

## Epic 4: Supporting Documents and Reporting

An Employee attaches a Supporting Document to a Leave Request whose Leave Type requires one — validated for type and size before a single byte is written, and stored under a server-generated name on a volume outside the web root. A Manager exports their Direct Reports' leave as CSV; an Admin exports organization-wide. Both exports carry exactly the rows the applied filters selected.

**This is PRD §7.3, and the PRD is blunt about it:** Phase 3 "is the part of the specification most likely to go undelivered, and calling it 'in scope' does not make it safe." If it does not land, `SM-8` is missed and reported as a missed target — not reclassified after the fact as a deferral that was always intended.

### Story 4.1: Attach a Supporting Document

As an Employee,
I want to attach the document my leave type requires,
So that my request carries its evidence and can be decided.

**Acceptance Criteria:**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `supporting_document` carries `leave_request_id` with `UNIQUE (leave_request_id)`, a `storage_name`, an `original_filename` and a `content_type`
**And** it carries no `size_bytes`, because size is validated before the bytes are written and no requirement reads it afterwards (ERD §2.1)

**Given** an upload to `POST /api/v1/leave-requests/<id>/document`
**When** it is neither PDF, JPG/JPEG nor PNG, or exceeds 5 MB
**Then** the response is `400` with `UNSUPPORTED_FILE_TYPE` or `FILE_TOO_LARGE`
**And** both checks ran **before any bytes were written** to the volume (`FR-13`, `AD-15`)

**Given** an accepted upload
**When** it is stored
**Then** it is written to a volume outside the web root under a server-generated UUID name
**And** the client-supplied filename is persisted as a data column and is never used as a path component (`NFR-05`, `AD-15`)

**Given** a Leave Type whose `requires_supporting_document` is true
**When** an Employee submits a Leave Request for it without a document
**Then** the response is `400` with `SUPPORTING_DOCUMENT_REQUIRED`
**And** Story 2.6's submission service is the one place this is enforced (`FR-13`)

*(Safe to arrive last: `EL`, `CL` and `FL` seed with `requires_supporting_document` **false**, so no document-requiring Leave Type exists before this story lands. An Admin who sets it true beforehand creates a requirement that is configurable but unenforced — a deliberate act, not a latent gap, per PRD §7.3.)*

**Given** the applicant, the applicant's Manager, or an Admin
**When** they call `GET /api/v1/leave-requests/<id>/document`
**Then** the document is streamed by an authorized endpoint that re-applies `AD-10`'s scope
**And** any other Employee receives `404`, and no static route maps to the storage volume (`FR-13`, `AD-15`)

**Given** the React application and a Leave Type requiring a document
**When** an Employee fills the request form
**Then** an upload control is presented, and a rejected file states why (`NFR-17`)

### Story 4.2: Export Leave as CSV

As a Manager,
I want to export my team's leave, and as an Admin the organization's,
So that I can answer a question the dashboard does not.

**Acceptance Criteria:**

**Given** an authenticated Manager
**When** they call `GET /api/v1/reports/leave.csv`
**Then** the export contains only their Direct Reports
**And** an Admin's export contains every Employee (`FR-15`, `FR-03`, `AD-10`)

**Given** a filter set applied to the view
**When** the export runs
**Then** the exported rows are exactly the rows matching those filters — the same filters Story 3.1 established (`FR-15`, `FR-12`)

**Given** any exported row
**When** its Leave Day count is read
**Then** it is the value stored on the request at admission, never recomputed against today's holiday calendar (`AD-18`)

**Given** the export format
**When** it is produced
**Then** it is CSV
**And** no PDF export exists, which is a declared non-goal (PRD §7.4)

**Given** the React application and an authenticated Manager or Admin
**When** they open the report screen
**Then** they can apply filters and export exactly what they see
