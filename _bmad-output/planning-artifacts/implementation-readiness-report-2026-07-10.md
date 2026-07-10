---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
  - remediation-applied
readinessStatus: READY (conditional — see Remediation)
findingsTotal: 17
blockingFindings: 0
findingsClosed: 13
findingsOpen: 4
remediationDate: 2026-07-10
documentsAmended:
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md
  - _bmad-output/planning-artifacts/module-4-erd/erd.md
documentsUnderAssessment:
  prd: _bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md
  prdAddendum: _bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/addendum.md
  architecture: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md
  architectureSpine: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md
  apiContracts: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md
  epics: _bmad-output/planning-artifacts/epics.md
  erd: _bmad-output/planning-artifacts/module-4-erd/erd.md
  brd: _bmad-output/planning-artifacts/module-1-business-analysis/brd.md
  functionalRequirements: _bmad-output/planning-artifacts/module-1-business-analysis/functional-requirements.md
  nonFunctionalRequirements: _bmad-output/planning-artifacts/module-1-business-analysis/non-functional-requirements.md
  assumptionsAndConstraints: _bmad-output/planning-artifacts/module-1-business-analysis/assumptions-and-constraints.md
  brief: _bmad-output/planning-artifacts/briefs/brief-LeaveFlow-2026-07-09/brief.md
  ux: null
shardedDocuments: none
duplicatesFound: none
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-10
**Project:** LeaveFlow

## Step 1: Document Discovery

### Discovery Method

Searched `_bmad-output/planning-artifacts` for whole documents (`*prd*.md`, `*architecture*.md`, `*epic*.md`, `*ux*.md`) and for sharded document sets (`*/index.md`). No `index.md` file exists anywhere under the planning artifacts tree, so **no documents are sharded and no whole-vs-sharded duplicates exist.**

### PRD Documents

**Whole Documents:**
- `prds/prd-LeaveFlow-2026-07-09/prd.md` (74K, modified Jul 10 16:53) — primary PRD
- `prds/prd-LeaveFlow-2026-07-09/addendum.md` (24K, modified Jul 10 16:53) — amendments to the PRD

**Sharded Documents:** none

**Supporting review/reconcile artifacts (process outputs, not specs):** `review-rubric.md`, `review-adversarial.md`, `review-edge-cases.md`, `review-downstream.md`, `review-fr-integrity.md`, `review-dr-traceability.md`, `review-open-items.md`, `review-amendment-integrity.md`, `reconcile-brd.md`, `reconcile-brief.md`, `reconcile-erd.md`, `reconcile-spine.md`, `reconcile-requirements.md`, `reconcile-architecture-and-api.md`, `reconcile-memlog.md`, `.memlog.md`

### Architecture Documents

**Whole Documents:**
- `architecture/architecture-LeaveFlow-2026-07-10/architecture.md` (30K, modified Jul 10 16:54) — primary architecture
- `architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md` (34K, modified Jul 10 14:39) — invariants spine
- `architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md` (13K, modified Jul 10 16:54) — API contracts

**Sharded Documents:** none

**Supporting review/reconcile artifacts:** `reviews/review-adversarial.md`, `reviews/review-data-integrity.md`, `reviews/review-rubric.md`, `reviews/review-versions.md`, `reviews/reconcile-prd.md`, `reviews/reconcile-addendum-module1.md`, `reviews/editorial-structure.md`, `reviews/editorial-prose.md`, `.memlog.md`

### Epics & Stories Documents

**Whole Documents:**
- `epics.md` (122K, modified Jul 10 17:44) — 4 epics, 27 stories

**Sharded Documents:** none

**Note:** `_bmad-output/implementation-artifacts/` is empty — no individual story context files have been generated yet. This is expected before Phase 4 and is not a readiness defect.

### UX Design Documents

**Whole Documents:** none found
**Sharded Documents:** none found

Searched for `*ux*`, `*design*`, `*wireframe*`, `*ui*`, `*user-experience*`, `*journey*`. No standalone UX specification exists. However, `epics.md` contains an embedded `### UX Design Requirements` section (line 220), so some UX intent has been captured inline rather than in a dedicated artifact.

### Additional Specification Documents Found

These are not in the four standard search patterns but are load-bearing specs that the assessment must trace against:

- `module-1-business-analysis/brd.md` (9.4K) — business requirements
- `module-1-business-analysis/functional-requirements.md` (12K, modified Jul 10 12:10)
- `module-1-business-analysis/non-functional-requirements.md` (6.1K)
- `module-1-business-analysis/problem-statement.md` (3.5K)
- `module-1-business-analysis/stakeholder-analysis.md` (2.9K)
- `module-1-business-analysis/assumptions-and-constraints.md` (8.7K)
- `module-4-erd/erd.md` (30K, modified Jul 10 16:54) — entity relationship model
- `briefs/brief-LeaveFlow-2026-07-09/brief.md` (8.5K) + `addendum.md` (12K)

### Issues Found

**Duplicates (CRITICAL):** None. No sharded versions exist alongside whole documents.

**Missing Documents (WARNING):**
- ⚠️ **No standalone UX design document.** UX requirements appear only as an embedded section inside `epics.md`. Assessment of UX completeness and UX→story traceability will be limited to that section.

**Observations carried into later steps:**
- `epics.md` contains an `## Unresolved Gaps` section listing **G1–G8**, of which only **G1 is marked RESOLVED**. Seven open gaps (G2–G8) are decision points that may block story implementation. These will be examined in the cohesion and story-readiness steps.
- Module numbering jumps from `module-1-business-analysis` to `module-4-erd`. Modules 2 and 3 have no output folders. This may be intentional (numbering reflects a pipeline stage, not a required artifact) but is worth confirming.

---

## Step 2: PRD Analysis

### Sources Read

- `prds/prd-LeaveFlow-2026-07-09/prd.md` — read in full (694 lines)
- `prds/prd-LeaveFlow-2026-07-09/addendum.md` — read; **introduces no new FR or NFR.** It records rejected alternatives, research grounding, and material bound for Architecture.
- `module-1-business-analysis/non-functional-requirements.md` — read in full. The PRD (§8) explicitly states the full 21-NFR register lives in Module 1 and only a constraining subset is restated. Extracting the complete NFR set therefore requires this file.
- `module-1-business-analysis/functional-requirements.md`, `brd.md` — read for BR/D identifiers cited by the PRD's domain rules.

**Authority note:** The PRD carries `FR-01`–`FR-18` verbatim from the Module 1 BRD and adds `FR-19`, `FR-20`. Module 1 defines only `FR-01`–`FR-18` as headings; **`FR-19` and `FR-20` are defined solely in the PRD.** The PRD is the authoritative requirement source for this assessment.

### Functional Requirements

Twenty requirements. Numbering is global and non-contiguous by section (deliberate — identifiers are stable across the artifact chain per addendum §1.3). Listed below in PRD section order, with the normative statement and its testable consequences.

**§4.1 Identity and Access**

**FR-01: User Authentication** — An **Employee** can exchange credentials for an authenticated session.
- A correct credential pair returns a session token; an incorrect one does not.
- The credential pair is the Employee's **Email Address** and the initial password an **Admin** supplied when creating them (`FR-04`). LeaveFlow offers no other way to establish a password, and no way to change one.
- A failed authentication does not disclose whether the account exists: the response to an unknown identity and the response to a wrong password are byte-identical in body and equal in status code.
- No stored representation of a password permits recovery of the password.

**FR-02: JWT-Based Authorization** — The system carries the authenticated session as a JSON Web Token presented on each request.
- A request with no token is rejected.
- A request with an expired token is rejected.
- A request whose token signature does not verify is rejected, including one whose payload was altered to change the subject or role.

**FR-03: Role-Based Access Control** — The system grants each **Employee** the capabilities of exactly one role — Employee, Manager, or Admin — and scopes every Manager action to that Manager's **Direct Reports**.
- A Manager can read and decide a Leave Request whose applicant is their Direct Report.
- A Manager attempting to read or decide a Leave Request belonging to a non-report receives the same response as for a nonexistent request. Holding the Manager role is insufficient; the reporting relationship is checked.
- An Admin can read every Leave Request and can decide none. Approval is not among the Admin's capabilities.
- Authorization is enforced at the API boundary. A client that does not render a control cannot invoke it by calling the endpoint directly.
- *Feature NFR:* Data scoping is applied where data is fetched, not by filtering results after retrieval (`NFR-04`).

**§4.2 Organization Administration**

**FR-04: Employee Management** — An **Admin** can create, read, update, and deactivate **Employee** records, including each Employee's Department, role, joining date, and Manager.
- An Employee is never physically deleted. Deactivation preserves their Leave Requests, Leave Balances, and Audit Entries.
- An Employee with unresolved **Pending** Leave Requests cannot be deactivated.
- A Manager with at least one Direct Report cannot be deactivated. Every Direct Report must first be reassigned. This keeps `FR-09`'s managerless auto-approval from being reached by an Admin deactivating a Manager.
- A deactivated Employee cannot authenticate.
- Assigning a Manager to an Employee establishes the Direct Report relationship that `FR-03` enforces.
- Creating an Employee requires the Admin to supply that Employee's initial password. It is hashed before persistence and never stored recoverably (`NFR-01`). No response from any endpoint returns a password or its hash.
- Updating an Employee does not accept a password. There is no re-issue path, and no other role or endpoint can set one.

**FR-05: Department Management** — An **Admin** can create, read, update, and remove **Departments**.
- A Department with at least one assigned Employee cannot be removed; the attempt is refused and names the obstruction.

**FR-17: Personal Profile Management** — An **Employee** can update their own profile.
- An Employee can edit their own profile fields and no other Employee's.
- The only profile field an Employee may edit is their **Full Name**.
- Role, Department, Manager, joining date, Email Address, and any Leave Balance quantity are not editable by their owner. An attempt to alter them through the profile endpoint is refused.
- *Explicit:* a password is a credential, not a profile field. No endpoint anywhere permits an Employee to change their own password.

**§4.3 Leave Policy Configuration**

**FR-06: Leave Type Management** — An **Admin** can configure **Leave Types** and their attributes.
- Three Leave Types exist at initialization: EL, CL, FL.
- Each Leave Type carries an **Annual Entitlement**, a **carries-forward** attribute, a **Carry-Forward Cap**, and a **requires-supporting-document** attribute, all stored as data.
- At initialization EL, CL and FL are seeded with *requires-supporting-document* **false**. An Admin may set it true for any Leave Type at any time.
- An Admin can set and change a Leave Type's Annual Entitlement.
- An Admin can set and change a Leave Type's Carry-Forward Cap. No cap value is fixed in code.
- When a Leave Policy change would affect existing Leave Balances, the system does not decide the outcome: it **requires the Admin to choose explicitly** whether existing balances are recalculated under the new policy or left as accrued under the old one. The change cannot be applied without that choice being made and recorded.
- Such a recalculation obeys the same non-negativity guard as `FR-10`: never a negative Available in any Leave Year; where it would, it is **refused** for the affected Employee and Leave Type, recorded in the durable store the Admin reads, and the remainder proceeds.
- Creating a fourth Leave Type through configuration alone yields a type that can be applied for, reserved against, approved, and rolled over, with no code change and no schema migration.
- Carry-Forward and Lapse behavior is decided by reading the *carries-forward* attribute.

**FR-10: Holiday Management** — An **Admin** can maintain the **Company Holiday** calendar for a **Leave Year**.
- A Company Holiday is a date and a name.
- A date recorded as a Company Holiday is not a Working Day, and is therefore not counted as a Leave Day by `FR-08`.
- The holiday calendar is global; no Company Holiday is scoped to a Department or a location.
- Adding or deleting a Company Holiday inside the range of a **Pending** Leave Request recalculates that request's Leave Day count and its Reserved days.
- Adding or deleting a Company Holiday inside the range of an **Approved** Leave Request whose dates are still **in the future** recalculates that request's Leave Day count and the applicant's Leave Balance.
- A recalculation never produces a negative Available balance (`DR-5`) — neither in the recalculated Leave Year nor any later one. Where it would, it is **refused** for that Employee and Leave Type; their requests and balances are left unchanged; the case is recorded in a durable store the Admin can read; the remainder proceeds.
- An Admin can read the cases recorded by a refused recalculation. No other role can.
- An Approved Leave Request whose dates have already passed is **not** recalculated.

**§4.4 Leave Balances**

**FR-07: Leave Balance Tracking** — The system maintains, for each Employee, Leave Type, and Leave Year, the quantities **Accrued**, **Reserved**, **Consumed**, and derives **Available**.
- `Available = Accrued − Consumed − Reserved` holds after every state transition of every Leave Request.
- No sequence of transitions produces a negative Available balance.
- An Employee joining mid-Leave-Year receives a **Prorated** Accrued balance (`BR-02`).
- Proration is monthly against remaining months: `Annual Entitlement × (remaining months ÷ 12)`, joining month through December inclusive.
- The prorated result is rounded **down**. Entitlement 12, joining September → `12 × 4/12 = 4`. A computed 4.16 yields 4.
- At the Leave Year boundary, unused Accrued EL carries forward up to its Carry-Forward Cap; the excess, and unused Accrued CL and FL, lapse (`BR-03`, `DR-7`).
- The Leave Year rollover is invoked by a **system-triggered scheduled process**, not a user action. It records execution in a **separate append-only rollover log**, not among Audit Entries.
- An Employee viewing their balance sees **Available** as the primary figure, with **Reserved** disclosed alongside it.

**§4.5 Leave Request Lifecycle**

*Leave Request state machine (PRD §4.5):*

| From | To | Actor | Effect on balance |
|---|---|---|---|
| — | Pending | Employee (own) | Reserve Leave Days |
| — | Approved | System, when applicant has no Manager | Consume immediately; no reservation stage |
| Pending | Approved | Manager (of applicant) | Release reservation; Consume |
| Pending | Rejected | Manager (of applicant) | Release reservation |
| Pending | Cancelled | Employee (own) | Release reservation |
| Approved | Cancelled | Admin, by approving a Cancellation Request | Release Consumed days, restoring Available (`BR-05`) |

*Cancellation Request lifecycle — a separate entity, not a state of the Leave Request:*

| From | To | Actor | Effect on the Leave Request |
|---|---|---|---|
| — | Pending | Employee (own), future-dated leave only | None; remains Approved |
| Pending | Approved | Admin | Targeted Leave Request moves to Cancelled |
| Pending | Rejected | Admin | None; remains Approved |

**FR-08: Leave Request Workflow** — An **Employee** can submit a Leave Request for a Leave Type over a contiguous date range, which the system prices in **Leave Days** and admits as **Pending**.
- The Leave Day count equals the number of Working Days in the range — weekends and Company Holidays excluded. Friday-to-Tuesday spanning Sat, Sun, and a Monday holiday costs **2** Leave Days.
- A request whose Leave Day count exceeds the applicant's Available balance is refused, and the refusal states days requested and days available.
- A request whose date range spans two Leave Years is refused (`BR-04`).
- On admission, the request's Leave Days are Reserved and Available falls immediately.
- Two concurrent submissions that would together exceed Available cannot both succeed.
- A request by an Employee with no Manager is admitted directly as **Approved**, consuming its Leave Days without a reservation stage (`FR-09`). The Available check still applies.
- A request whose Leave Day count is **zero** is refused as invalid.
- A request whose **end date precedes its start date** is refused as invalid.
- A request whose date range lies **wholly in the past** is refused as invalid.
- *Out of scope:* half-day and hourly leave.

**FR-09: Approval and Rejection** — The **Manager** of the applicant can approve or reject a Pending request. The applicant can cancel it while Pending, and can raise a **Cancellation Request** once Approved. A managerless applicant's request is approved automatically by the system.
- Approval moves Reserved days to Consumed. Rejection and cancellation of a Pending request release Reserved days.
- Only the applicant's Manager can approve or reject. An Admin cannot. A different Manager cannot (`FR-03`).
- Only the applicant can cancel a Pending request, and only their own.
- Only the applicant can raise a Cancellation Request against their own Approved request. Only an Admin can approve or reject it.
- While a Cancellation Request is Pending, the Leave Request remains Approved and its days remain Consumed.
- An approved Cancellation Request moves the Leave Request to Cancelled and releases its Consumed days (`BR-05`). A rejected one changes nothing.
- An Approved Leave Request whose dates have **already passed** cannot be cancelled.
- Authority is evaluated **at decision time**, not at submission. If the applicant's Manager changes while Pending, the **current** Manager decides.
- A managerless Employee's request is Approved on submission with no Pending stage. Its Audit Entry names actor `SYSTEM` and reason `AUTO_APPROVED_NO_MANAGER`.
- Every transition writes exactly one Audit Entry (`FR-16`).
- Concurrent conflicting transitions: first to commit succeeds, second fails on the changed state. No silent overwrite.

**FR-13: Supporting Document Upload** — An Employee can attach a **Supporting Document** to a Leave Request whose Leave Type requires one.
- A Leave Request for a Leave Type configured as requiring a document cannot be submitted without one.
- Uploads are validated before storage. Permitted types: PDF, JPG/JPEG, PNG. Maximum size 5 MB per file. A file failing either check is rejected.
- A Supporting Document is retrievable only by the applicant, the applicant's Manager, and the Admin (`FR-03`).
- *Feature NFR:* stored outside the web root; a client-supplied filename is never used as a storage path (`NFR-05`).

**FR-16: Audit Logs** — The system records every Leave Request state transition as an **Audit Entry**.
- Each entry names the Leave Request, the transition, the actor, and the timestamp.
- A system-caused transition records actor `SYSTEM` with an explicit reason (`AUTO_APPROVED_NO_MANAGER`). No human approver is fabricated.
- Audit Entries are append-only. No application code path updates or deletes one.
- Full read access to the audit log is restricted to the Admin. No Employee or Manager can read it.
- The number of Audit Entries for a Leave Request equals the number of state transitions it has undergone.

**§4.6 Visibility and Decision Support**

**FR-11: Dashboard** — Each role sees a dashboard scoped to what that role can act on.
- Employee dashboard: per Leave Type — Available, Reserved, Consumed; plus a count of Pending requests.
- Manager dashboard: count of Leave Requests awaiting their decision, and Direct Reports on approved leave within the next seven days.
- Admin dashboard: organization-wide totals — Employees on approved leave today, and Pending request count.
- Every dashboard supports a **date-range filter**; figures presented are those inside the selected range.
- A Manager requesting the Employee dashboard sees their own balances. An Employee requesting the Manager dashboard is refused (`FR-03`).
- *Scope:* summary cards with date-range filtering. Charts and trend lines are out of scope (§7.4).

**FR-18: Department Leave Calendar** — A Manager can view their Direct Reports' leave across a date range.
- Shows **Approved** and **Pending** leave, visually distinguished from one another.
- Shows only the viewing Manager's Direct Reports (`FR-03`).
- Presented **on the approval screen** for the dates of the Leave Request under decision.
- Never prevents an approval. Overlapping leave produces no warning, no block, no required acknowledgement (`BR-06`).

**FR-19: Team Member List** — A Manager can view the Employees who report to them.
- Contains exactly the viewing Manager's Direct Reports, and no other Employee (`FR-03`).
- Each entry identifies the Employee and their Department.
- A deactivated Direct Report is distinguishable from an active one.

**FR-20: Leave History** — An Employee can view their own Leave Requests across Leave Years.
- Contains every Leave Request the Employee has submitted, in every state, including Cancelled and Rejected.
- Each entry shows the Leave Type, the date range, the Leave Day count, and the current state.
- An Employee sees only their own history. A Manager sees a Direct Report's; an Admin sees any Employee's (`FR-03`).

**FR-12: Search, Filtering, and Pagination** — List endpoints support filtering and return bounded pages.
- Every list endpoint enforces a **maximum page size on the server**. A client requesting a larger page receives the maximum.
- Filters compose: Leave Type, state, and date range together.
- Filtering never widens authorization. A Manager filtering across all Departments sees only their Direct Reports (`FR-03`).

**§4.7 Notifications**

**FR-14: In-App Notifications** — The system notifies the Manager when a Direct Report submits a Leave Request, and notifies the applicant when the request is approved or rejected.
- Submission creates exactly one Notification addressed to the applicant's Manager.
- Approval or rejection creates exactly one Notification addressed to the applicant.
- A Notification is readable only by its addressee.
- An unread count is retrievable, and reading a Notification decrements it.
- An addressee can **mark a Notification read**. Marking read is idempotent, and only the addressee may do it.
- *Scope:* in-app only. Email delivery is deferred (§7.4).

**§4.8 Reporting and Export**

**FR-15: Reports and Export** — A Manager can export a leave report for their Direct Reports; an Admin can export one organization-wide.
- Export format is **CSV**. (PDF is out of scope.)
- The exported rows are exactly the rows matching the applied filters.
- A Manager's export contains only their Direct Reports (`FR-03`). An Admin's contains all Employees.

**Total FRs: 20** (`FR-01`–`FR-20`)

### Non-Functional Requirements

**Total NFRs: 21** (`NFR-01`–`NFR-21`). The PRD §8 restates 20 of them; **`NFR-19` is cited by `DR-16` but not restated in the PRD body**, and is recovered here from Module 1.

*Security*
- **NFR-01** Credentials are stored as salted hashes (bcrypt or Argon2). No reversible representation exists.
- **NFR-02** Token lifetime is measured in hours, not days, absent a refresh mechanism.
- **NFR-03** Authorization is enforced server-side, at the API boundary.
- **NFR-04** Data scoping is applied in the query, not by post-filtering retrieved rows.
- **NFR-05** Uploads are validated for type and size, stored outside the web root; client filenames are never trusted as paths.
- **NFR-06** Credentials and tokens travel over TLS in any deployed environment.
- **NFR-20** Secrets, database credentials, and signing keys come from the environment. None are committed.

*Correctness and reliability*
- **NFR-07** Reserve, consume, and release are transactional. A concurrent double submission produces neither a negative nor a double-counted balance.
- **NFR-08** The leave-day calculation is a single, pure, unit-tested function (`DR-2`).
- **NFR-09** Audit Entries are append-only.
- **NFR-15** The hard rules carry tests: proration, carry-forward, the Leave Year boundary, the day count, and authorization scope.

*Performance*
- **NFR-10** Read endpoints respond within roughly 500 ms at this project's data scale. An order of magnitude, not a contractual figure.
- **NFR-11** Result sets are bounded by a server-enforced maximum page size.
- **NFR-12** Indexed access paths exist for employee, manager, department, leave year, and request state.

*Maintainability and operability*
- **NFR-13** Routes, business logic, and data access are separated; policy lives in the service layer.
- **NFR-14** Adding a Leave Type requires no code change (`DR-11`).
- **NFR-21** Setup is reproducible from a documented command sequence on a clean machine.

*Usability*
- **NFR-16** A control a role cannot invoke is not rendered for that role. A usability measure, not a security measure.
- **NFR-17** Errors state the reason. "Insufficient balance" names days requested and days available; "spans two leave years" names the boundary.
- **NFR-18** Layout is responsive across desktop and tablet widths.

*Auditability*
- **NFR-19** Every leave state transition records who caused it and when. An approved request can be traced to the manager who approved it. **(Not restated in PRD §8; cited by `DR-16`.)**

**A standing risk the PRD itself declares (§8):** all 21 NFRs are engineer-proposed. **None has been confirmed by the assigning manager.** `NFR-03`, `NFR-04`, `NFR-07`, `NFR-08` are the four funded most heavily.

### Additional Requirements

**Domain Rules and Invariants (PRD §5) — 18 identifiers, `DR-1`–`DR-16` including `DR-2a` and `DR-7a`.** These are normative and must be traced into stories:

- **DR-1** Leave Day count = Working Days in range; weekends and Company Holidays excluded. *(D-02)*
- **DR-2** The calculation is a pure function of range + holiday calendar. **Exactly one implementation**; every balance-touching path calls it. A second implementation anywhere is a defect. *(D-02, NFR-08)*
- **DR-2a** A Leave Date is a calendar `DATE`. No time component; never stored or compared as a UTC timestamp.
- **DR-3** A Leave Balance is three stored quantities and one derived. **Available is never stored.** *(D-01)*
- **DR-4** Submit reserves; approve consumes; reject/cancel release — including Admin-approved Cancellation Request releasing Consumed days. *(D-01, BR-05)*
- **DR-5** `Available ≥ 0` is an invariant after every transition, under concurrency, and after any recalculation triggered by `FR-06`/`FR-10`. Reserve/consume/release are atomic. Racing transitions: **first-committed-wins**.
- **DR-6** A Leave Request may not span two Leave Years. *(BR-04)*
- **DR-7** At the boundary, unused Accrued of a carries-forward type carries up to its Cap; above-cap days **Lapse**. Non-carrying types Lapse. **"Unused Accrued days" means Available**, recomputed whenever the closing year's balance changes — so Carry-Forward may *increase* after the boundary when a Pending request is rejected or cancelled. No transition ever decreases it.
- **DR-7a** **Reserved days held by a Pending request do not lapse at the boundary.** They remain reserved against their Leave Year until resolved; their resolution changes that year's Available and therefore its Carry-Forward.
- **DR-8** The Leave Year is the calendar year, 1 Jan – 31 Dec.
- **DR-9** Proration = `Annual Entitlement × (remaining months ÷ 12)`, joining month through December inclusive, rounded **down**. *(BR-02)*
- **DR-10** A Leave Day is a whole number. Fractional leave is not expressible.
- **DR-11** Annual Entitlement, Carry-Forward, Cap, and Supporting-Document requirement are Leave Type attributes stored as data and read at runtime. *(D-04, NFR-14)*
- **DR-12** A Manager's authority derives from the Direct Report relationship, **evaluated at decision time**. Scope is applied in the query. *(D-03, NFR-04)*
- **DR-13** An Admin reads every Leave Request and approves none. The Admin decides Cancellation Requests. Full audit-log read is the Admin's alone.
- **DR-14** **Approved is not terminal.** A Cancellation Request is a separate entity with its own lifecycle, decided by an Admin. Past-dated leave cannot be cancelled. *(Reverses `D-07`, makes `BR-05` reachable.)*
- **DR-15** Overlapping leave among Direct Reports is permitted without restriction. The system informs; it never blocks. *(BR-06)*
- **DR-16** Every transition writes **exactly one** append-only Audit Entry naming actor and timestamp. System transitions record `SYSTEM` and an explicit reason. *(FR-16, NFR-09, NFR-19)*

**Business Rules carried from Module 1 BRD:** `BR-01` three leave types; `BR-02` mid-year proration; `BR-03` EL carries forward, CL and FL lapse; `BR-04` no request spans two calendar years; `BR-05` cancelling approved leave restores balance; `BR-06` no restriction on same-team overlapping dates.

**Engineering Decisions:** `D-01` reserve-on-pending/deduct-on-approve; `D-02` working days only; `D-03` data-scoped authorization; `D-04` policy as configuration; `D-05` FastAPI; `D-06` React; `D-07` approved-leave cancellation out of scope — **`D-07` is reversed by `DR-14`.**

**Constraints and Guardrails (§9):** seven days total, **Days 3–5 the only days allocated to application code**; BMAD lifecycle artifacts take precedence over feature count; exactly three roles; Manager authority limited to Direct Reports; Admin owns policy and holds no approval authority; web-based delivery; one organization per deployment; FastAPI backend; React frontend.

**MVP phasing (§7)** — a build order and depth allocation, not deletions:
- **Phase 1 (correctness core):** `FR-01`, `FR-02`, `FR-03`, `FR-04`, `FR-05`, `FR-17`, `FR-06`, `FR-10`, `FR-07`, `FR-08`, `FR-09`, `FR-16`
- **Phase 2 (usable):** `FR-11`, `FR-18`, `FR-12`, `FR-14`, `FR-19`, `FR-20`
- **Phase 3 (completes coverage):** `FR-13`, `FR-15`
- The PRD names Phase 3 as **the part most likely to go undelivered**, and requires the shortfall be reported as a missed `SM-8` target rather than reclassified as an intended deferral.

**Success Metrics (§10):** `SM-1` balance arithmetic consistent under concurrency; `SM-2` day count right at boundaries; `SM-3` authorization scoped to data not role; `SM-4` every leave action attributable (Audit Entry count = transition count, 1:1); `SM-5` policy is data (fourth Leave Type with no code change); `SM-6` decisions traceable both directions; `SM-7` assumptions visible; `SM-8` **all twenty FRs delivered, each with ≥1 passing test exercising a stated testable consequence**; `SM-9` every lifecycle stage produced its artifact. Counter-metrics `SM-C1`–`SM-C3` (do not optimize coverage %, dashboard richness, or documentation volume).

**Non-Goals (§6):** no payroll/loss-of-pay; no encashment; no attendance tracking; no fourth role, delegation, escalation, or second approver; no multi-tenancy within a deployment; no sub-day leave; no unpaid leave or negative balance; no per-location/per-department holiday or weekend variation; no email; **no password management beyond setting it once**; no HA, horizontal scalability, i18n, or formal WCAG conformance.

### PRD Completeness Assessment

**Overall: exceptionally strong.** This is a PRD written by someone who understands that a requirement without a testable consequence is a requirement not yet understood. Every FR carries explicit, falsifiable consequences. Terminology is fixed in a glossary and used consistently. Edge cases that normally surface during implementation — reversed date ranges, zero-working-day requests, racing transitions, decision-time authority binding, managerless auto-approval attribution — are decided in the text rather than deferred.

**Positive findings:**
- §11 Open Questions and §12 Assumptions Index both legitimately resolve to **zero**. Spot-checking confirms the `[ASSUMPTION:` tag appears nowhere in the document body. This is not a hollow claim.
- The state machine is fully specified, including the Cancellation Request as a **separate entity** with its own lifecycle — a modelling decision that is easy to get wrong and is here made explicitly.
- `DR-7` / `DR-7a` handle the genuinely hard case: a Pending request that survives the Leave Year boundary. The PRD notices that without this reading the two rules are *jointly under-determined*, and says so. That is a level of rigor that most PRDs never reach.
- Known limitations (encashment vs. Indian statute; no password recovery; attribution binds an account not a person) are recorded as accepted limitations with their consequences enumerated, rather than hidden.

**Gaps and risks carried into later steps:**

1. **`NFR-19` is cited but never restated.** `DR-16` derives its actor-attribution requirement partly from `NFR-19`, yet PRD §8 omits it from the restated subset. Recoverable from Module 1, so this is a documentation seam rather than a missing requirement — but any story tracing to `NFR-19` must reach outside the PRD to find it.
2. **All 21 NFRs are unconfirmed.** The PRD says so plainly. Every NFR-derived acceptance criterion in the epics therefore rests on engineer judgment, not stakeholder agreement.
3. **`D-07` is reversed by `DR-14`, but Module 1 still asserts it.** The BRD (`brd.md` lines 74, 99) still records `BR-05` as "not reachable" and `D-07` as narrowing approved-leave cancellation out of scope. The PRD supersedes both. **Module 1 was never amended.** Any reader or downstream workflow sourcing from the BRD rather than the PRD will build the wrong scope.
4. **Module 1's role-to-requirement matrix is wrong on `FR-11`** (PRD §4.6 note explicitly flags it), and Module 1 defines only `FR-01`–`FR-18` — `FR-19` and `FR-20` exist solely in the PRD. Module 1's own amendment note (line 133) acknowledges this but the requirement bodies were never added.
5. **Phase 3 (`FR-13`, `FR-15`) is declared at-risk by the PRD itself.** `SM-8` demands all twenty FRs. Epic sequencing must not bury these where a budget overrun silently deletes them.
6. **Two requirements imply mutations whose surfaces are thinly specified:** `FR-14`'s mark-read transition (now stated as an `FR-14` consequence, closing addendum §3.2a) and `FR-06`'s "Admin must explicitly choose recalculate-or-not" — the latter implies a decision-capture surface and a durable refusal store shared with `FR-10`. Whether the epics carry stories for the **refusal-record read surface** (`FR-10`: "An Admin can read the cases recorded by a refused recalculation") is a specific thing to verify.
7. **The rollover log is a second append-only store**, distinct from Audit Entries (`FR-07`). It needs its own story or it will be conflated with the audit log.

---

## Step 3: Epic Coverage Validation

### Method

Read `epics.md` in full (1,522 lines): 4 epics, 27 stories. Extracted the document's own **FR Coverage Map** (lines 235–258), then **independently verified each claim against the acceptance criteria of the stories themselves** rather than trusting the map. Also built a mechanical FR→story citation index to find requirements whose behavior is delivered but whose identifier is never named.

### Coverage Matrix

| FR | PRD Requirement | Epic | Delivering Story / Stories | Status |
|---|---|---|---|---|
| FR-01 | User Authentication | 1 | 1.2 (login, byte-identical failure, constant-fallback hash, `pwdlib`) | ✓ Covered |
| FR-02 | JWT-Based Authorization | 1 | 1.3 (absent / expired / tampered token) | ✓ Covered |
| FR-03 | Role-Based Access Control | 1 | 1.4 (role gate, scoped repo, 404 convention), 1.7 (scope = `manager_id`, decision-time), 2.7 (non-report → 404) | ✓ Covered |
| FR-04 | Employee Management | 1 | 1.6 (CRUD, initial password, both deactivation guards), 1.2 (deactivated cannot authenticate) | ✓ Covered |
| FR-05 | Department Management | 1 | 1.5 (CRUD, `DEPARTMENT_NOT_EMPTY`) | ✓ Covered |
| FR-17 | Personal Profile Management | 1 | 1.8 (`PATCH /me`, `full_name` only, no password path) | ✓ Covered |
| FR-06 | Leave Type Management | 2 | 2.1 (types as data, seeded `requires_supporting_document=false`), 2.12 (`POLICY_DISPOSITION_REQUIRED`, RECALCULATE/PRESERVE) | ✓ Covered |
| FR-07 | Leave Balance Tracking | 2 | 2.4 (3 quantities + derived Available, proration, `AD-17` mutation module), 2.10 (rollover, carry-forward, lapse, `rollover_run`) | ✓ Covered |
| FR-08 | Leave Request Workflow | 2 | 2.3 (`count_leave_days`), 2.5 (preview), 2.6 (submit, reserve, all five refusal codes, concurrency) | ✓ Covered |
| FR-09 | Approval and Rejection | 2 | 2.7 (approve/reject/cancel, `AD-4` CAS, decision-time authority), 2.8 (Cancellation Request lifecycle), 2.6 (managerless auto-approval) | ✓ Covered |
| FR-10 | Holiday Management | 2 | 2.2 (global calendar, `DATE`), 2.11 (recalculation, forward check, refusal, `GET /admin-review-flags`) | ✓ Covered |
| FR-16 | Audit Logs | 2 | 2.9 (append-only grants, 1:1 count, `SYSTEM` actor, Admin-only read) | ✓ Covered |
| FR-11 | Dashboard | 3 | 3.5 (three role dashboards, date-range filter, no charts) | ✓ Covered |
| FR-12 | Search, Filtering, Pagination | 3 | 3.1 (composable filters, `items/page/page_size/total`, scope never widened) | ✓ Covered |
| FR-14 | In-App Notifications | 3 | 3.4 (three kinds, in-transaction write, unread count, idempotent mark-read) | ✓ Covered |
| FR-18 | Department Leave Calendar | 3 | 3.3 (inline on approval screen, Approved+Pending distinguished, never blocks) | ✓ Covered |
| FR-19 | Team Member List | 3 | 3.2 (`GET /team`, Department shown, deactivated distinguishable) | ✓ Covered |
| FR-20 | Leave History | 3 | 3.1 (every state incl. Cancelled/Rejected, stored `leave_days`) | ✓ Covered |
| FR-13 | Supporting Document Upload | 4 | 4.1 (type/size before bytes written, UUID storage name, scoped streaming) | ✓ Covered |
| FR-15 | Reports and Export | 4 | 4.2 (CSV, filter parity, scope) | ✓ Covered |

### Missing Requirements

**None.** Every one of the twenty functional requirements resolves to at least one story whose acceptance criteria assert a stated testable consequence of that requirement. There are no phantom FRs — the epics introduce no requirement absent from the PRD.

I specifically hunted for the seven risks carried out of Step 2. **Three of them are resolved by the epics, and I record that rather than repeat the suspicion:**

- `FR-10`'s **refusal-record read surface** — I doubted it would be storied. It is: Story 2.11 asserts `GET /api/v1/admin-review-flags`, Admin-only, with the explicit note that *no endpoint clears a flag* because no requirement grants a resolve.
- `FR-06`'s **explicit-disposition capture** — Story 2.12 asserts `POLICY_DISPOSITION_REQUIRED` on a missing disposition and a `policy_change` row recording it.
- The **rollover log as a second append-only store** — Story 2.10 asserts `rollover_run` with `INSERT`/`SELECT` grants only, and explicitly that the rollover "writes to `rollover_run` and never to `audit_entry`, because … `SM-4`'s one-to-one count must stay true."
- `FR-14`'s **mark-read transition** — Story 3.4 asserts an idempotent `PATCH /notifications/<id>/read` restricted to the addressee.

### Coverage Statistics

- **Total PRD FRs: 20**
- **FRs covered in epics: 20**
- **Coverage percentage: 100%**
- **FRs in epics but not in PRD: 0**
- Total epics: 4 · Total stories: 27 (Epic 1: 8, Epic 2: 12, Epic 3: 5, Epic 4: 2)

### Findings — coverage is complete, but three claims in the epics document do not survive verification

Coverage is not the problem here. These are defects in the epics document's own structural claims, found by checking them rather than reading them.

**🔴 F-1 (MEDIUM–HIGH) — Epic 2 requires Epic 3. The "stands alone" claim is false.**

`epics.md:399` states: *"Each delivers complete functionality for its domain and stands alone; **none requires a future epic to function**."* It does not hold.

- Story 2.7's acceptance criterion: *"Given the React application and an authenticated Manager, When they open **their queue**, Then they see the requests awaiting their decision."*
- Story 2.8's: *"When they **view an Approved future-dated request**, Then they can raise a Cancellation Request."*
- Story 2.7's `404` criterion: *"When they call **any endpoint naming that Leave Request's identifier**…"*

All three require reading Leave Requests. **Epic 2 names no read endpoint for them.** Its stories specify only `POST /leave-requests`, `POST /leave-requests/preview`, the approve/reject/cancel actions, and the cancellation endpoints. `GET /api/v1/leave-requests` and `GET /api/v1/leave-requests/<id>` — both defined in `api-contracts.md` lines 157–158, bound there to `FR-12`, `FR-20` and `FR-03` — are **first delivered by Epic 3, Story 3.1.**

*Impact:* Epics 1+2 are PRD §7.1's Phase 1, the "correctness core" that the budget funds first. As sequenced, completing Phase 1 yields a system in which **a Manager cannot see the queue they are meant to decide from, and an Employee cannot view the Approved request they are meant to cancel.** The backend is correct; the phase is not shippable. Because Epic 4 is the declared budget casualty, this also means an overrun that stops mid-Epic-3 leaves Epic 2's UI criteria unmet.

*Recommendation:* Either move a minimal `GET /leave-requests` + `GET /leave-requests/<id>` (self + reports scope, no composable filters) into Epic 2 as its own story or as criteria on Story 2.7, leaving `FR-12`'s filters and `FR-20`'s cross-year history in Story 3.1 — the same seam the document already uses to split `NFR-11`'s page bound from `FR-12`'s filters — or withdraw the "stands alone" claim and state the Epic 2 → Epic 3 dependency explicitly.

**🟠 F-2 (MEDIUM) — Story-level FR traceability is patchy, which puts `SM-6` and `SM-8` at risk.**

Five stories carry **no `FR-` citation at all**, and two headline FRs are cited by only one story each despite being delivered across several:

| Story | Implements | Cites |
|---|---|---|
| 2.1 Leave Types as Configuration | `FR-06` | no FR |
| 2.5 See What a Request Will Cost | `FR-08` (preview) | no FR |
| 2.6 Submit a Leave Request | `FR-08` (reserve, all five refusals, concurrency) | `FR-09` only |
| 2.10 The Leave Year Rollover | `FR-07` (carry-forward, lapse, idempotence) | no FR |
| 1.1 Project Foundation | — (scaffolding) | no FR *(expected)* |

So `FR-07` is cited by Story 2.4 alone, and `FR-08` by Story 2.3 alone — yet the substance of both lands in 2.6 and 2.10.

*Impact:* `SM-8` counts a requirement delivered "only when a consequence from its FR is demonstrably exercised by a passing test," tracked **per requirement, per phase**. `SM-6` requires "every module names the FR or DR it implements." A per-FR delivery tracker built from these story labels would under-report `FR-07` and `FR-08` — the two requirements carrying the product's central correctness claim. The behavior is specified; only the label is missing.

*Recommendation:* Add the missing `FR-06`/`FR-07`/`FR-08` citations to Stories 2.1, 2.5, 2.6 and 2.10. Low cost, and it is exactly what `SM-6` asks for.

**🟡 F-3 (LOW) — "No FR is split across epics" is an overstatement, though the document discloses the exceptions in place.**

`FR-03`, `FR-09`, `FR-12` and `FR-14` each carry acceptance criteria in more than one epic. Most instances are cross-references rather than divided ownership, and the two that matter are disclosed exactly where they occur:

- `FR-04`'s `EMPLOYEE_HAS_PENDING_REQUESTS` guard is asserted in Story 1.6 and, as the story itself says, is *"vacuously satisfied in this epic"* because no `leave_request` table exists yet; it becomes executable in Story 2.6, which re-asserts it.
- `FR-03`'s headline consequence — a Manager reaching a non-report's Leave Request gets a 404 — cannot be tested until a Leave Request exists. Story 1.7 says so plainly: *"it does not claim to satisfy `SM-3`, which Epic 2 does."*

This is honest sequencing, not a defect. The summary sentence at `epics.md:237` simply promises more uniformity than the body delivers.

**🟡 F-4 (LOW) — An implementation note promises a hook no story delivers.**

Epic 3's notes state: *"`FR-14` adds a hook to Epic 2's `services/leave_request` **and `services/cancellation`**."* But Story 3.4's schema criterion fixes exactly three notification kinds — `REQUEST_SUBMITTED`, `REQUEST_APPROVED`, `REQUEST_REJECTED` — and no acceptance criterion anywhere covers a notification arising from a Cancellation Request transition.

The PRD does not require one (`FR-14`'s consequences name submission and the approval/rejection of a *Leave Request*), so **this is not a coverage gap against the PRD.** It is an internal inconsistency: either the `services/cancellation` hook is unnecessary and the note is wrong, or a fourth notification kind is missing. Worth one sentence to settle, because an implementer reading the note will go looking for the kind.

### Coverage Verdict

**PASS.** 100% FR coverage, independently verified against story acceptance criteria rather than accepted from the coverage map. No requirement is orphaned and none is invented. The defects found are structural (F-1) and clerical (F-2), not gaps in what the epics set out to build. **F-1 should be resolved before implementation begins**, because it changes what "Phase 1 complete" means.

---

## Step 4: UX Alignment Assessment

### UX Document Status

**Not Found — by decision, not by oversight.**

`epics.md:26` records: *"No UX Design Specification exists for this project. Confirmed with the product owner on 2026-07-10: the workflow proceeds without one."* The epics retain an intentionally empty **UX Design Requirements** section (line 220) so that its emptiness reads as a decision. The Architecture Spine explicitly defers *"React state shape below the page level, styling, and component library."* Formal WCAG conformance is explicitly not required (PRD §6, Module 1 NFR register).

### Is UX Implied?

**Yes, unambiguously.** LeaveFlow is a web-based, user-facing application: PRD §9 fixes web delivery; `D-06` fixes React; `FR-11` specifies three role dashboards; `FR-18` specifies a calendar rendered inline on an approval screen; `NFR-16`, `NFR-17` and `NFR-18` are all interface requirements. Twenty-three of the twenty-seven stories carry a frontend acceptance criterion.

**⚠️ WARNING (accepted):** UX is implied and no UX specification exists. This is a genuine risk, but a **well-mitigated** one, and the mitigation is worth stating precisely rather than waving through:

- The PRD carries the UI requirements that matter as *testable consequences* rather than as a separate artifact (`FR-11` per-role dashboard contents; `FR-18` inline-on-approval-screen placement with Approved/Pending visually distinguished; `NFR-16`/`NFR-17`/`NFR-18`).
- `UJ-1`'s climax — the excluded holiday **named on screen** rather than silently netted out — is asserted as an acceptance criterion in Story 2.5. `UJ-2`'s climax — the overlap visible *at the moment of decision* — is asserted in Story 3.3.
- `AD-2` removes the highest-risk frontend decision from the frontend entirely: the client obtains every day count from the preview endpoint, and *"no frontend module references a weekday or a holiday"* is a testable criterion in Story 2.3. The architecture predicted precisely where a duplicate day-count implementation would appear and structurally forbade it.

For a three-day implementation budget on a system whose correctness bar is arithmetic rather than visual, proceeding without a UX spec is defensible. **The warning is recorded, not escalated.**

### PRD UI Requirements ↔ Architecture Alignment

No misalignment found. Each UI requirement the PRD states is supported by an architecture invariant or an explicit deferral:

| PRD UI requirement | Architecture support | Status |
|---|---|---|
| `FR-11` per-role dashboards, date-range filter, no charts | `AD-10` scoping; Story 3.5 criteria | ✓ Aligned |
| `FR-18` calendar inline on approval screen | `AD-10`, `AD-18` (stored `leave_days`, never recomputed) | ✓ Aligned |
| `UJ-1` excluded holiday named on screen | `AD-2` preview endpoint returns `excluded_dates` with reason + holiday name | ✓ Aligned |
| `NFR-16` role-appropriate rendering | `AD-14` api-layer gate; never the sole guard | ✓ Aligned |
| `NFR-17` errors state their numbers | Error envelope `{code, message, details}`; `details` carries the numbers | ✓ Aligned |
| `NFR-18` responsive desktop/tablet | Story 1.1 shell + Story 3.5 dashboards | ✓ Aligned |
| Component library, styling, page-level state | Explicitly deferred by the Spine | ✓ Deliberate |

### Alignment Issues — the Admin cannot reach the decisions the system forces them to make

The frontend criteria are thorough for the Employee and the Manager. **They are systematically thin for the Admin**, and the pattern is consistent: the epics story-ify *commands* rigorously and *queries* spottily. Four stories in Epic 2 — 2.9, 2.10, 2.11, 2.12 — carry no frontend criterion at all. (2.10 is the rollover CLI and correctly has none. 1.4 and 1.7 are backend primitives and correctly have none.)

I diffed all 46 endpoints in `api-contracts.md` against all 43 endpoints named in any story. Three appear in the contract but in no story; one of them is serious.

**🔴 F-5 (HIGH) — `GET /cancellation-requests` exists in the contract and in no story. The Admin has no way to discover a Cancellation Request awaiting their decision.**

`api-contracts.md:187` defines `GET /cancellation-requests` (any role; scope self/all), bound to `DR-14`. **No story delivers it.** Story 2.8 names only `POST /leave-requests/<id>/cancellation-requests` (raise) and `POST /cancellation-requests/<id>/approve` (decide), and its sole frontend criterion is Employee-facing: *"they can raise a Cancellation Request, and see its state while an Admin decides it."*

Nothing anywhere tells the Admin a decision is waiting:
- No list endpoint is storied, so the Admin cannot enumerate Pending Cancellation Requests.
- No frontend criterion gives the Admin a cancellation-decision screen.
- The Admin dashboard (`FR-11`, Story 3.5) presents *"Employees on approved leave today, and the Pending request count"* — that count is **Leave Requests**, not Cancellation Requests.
- `FR-14`'s notification kinds are exactly `REQUEST_SUBMITTED` (→ Manager), `REQUEST_APPROVED` and `REQUEST_REJECTED` (→ applicant). **No notification is addressed to an Admin.**

*Impact.* An Employee raises a Cancellation Request. It enters Pending. The Admin who must decide it receives no notification, sees no count, has no queue, and cannot list them — they could only act by guessing a UUIDv7 primary key, which `erd.md` deliberately chose to be non-enumerable so that `AD-10`'s 404 stays honest. **The request is undecidable in practice, and the Leave Request stays Approved with its days Consumed indefinitely.**

This is a regression against a decision the PRD made deliberately. `D-07` had ruled approved-leave cancellation out of scope precisely because *"the specification authorizes no role to do it."* `DR-14` reversed that so `BR-05` would be *"a live rule rather than documented-but-unreachable policy."* As storied, **`BR-05` is unreachable again** — not by permission this time, but by discoverability.

*Recommendation:* Add `GET /cancellation-requests` (Admin: all; Employee: self) to Story 2.8 with an Admin decision-queue frontend criterion, and name `POST /cancellation-requests/<id>/reject` explicitly. Optionally add a fourth notification kind addressed to the Admin — which would also settle **F-4**, since Epic 3's note already promises an `FR-14` hook into `services/cancellation` that currently has no notification kind to write.

**🟠 F-6 (MEDIUM) — `FR-06` compels the Admin to choose a disposition; no screen offers the choice.**

`FR-06` requires that a policy change affecting existing balances *"cannot be applied without that choice being made and recorded,"* and Story 2.12 correctly asserts `400 POLICY_DISPOSITION_REQUIRED` when `PATCH /leave-types/<id>` arrives without one. But Story 2.12 has **no frontend criterion**, and Story 2.1's only Admin UI criterion is *"they can view and create Leave Types and set each attribute"* — creation, not amendment.

*Impact.* As specified, an Admin using the React app can create a Leave Type but cannot successfully edit one: every edit requires a `RECALCULATE`/`PRESERVE` disposition that no screen collects, so every edit returns `400`. This is the single highest-consequence Admin action in the product — `AD-19` lets it re-derive balances across every materialized Leave Year — and it has no interface.

*Root cause worth naming:* `NFR-16` states that a control a role **cannot** invoke is not rendered. No requirement states the converse — that a control a role **must** invoke **is** rendered. F-5 and F-6 both live in that blind spot.

**🟠 F-7 (MEDIUM) — A refused recalculation is recorded where no one will see it.**

Story 2.11 asserts `GET /api/v1/admin-review-flags` (Admin-only) and that the holiday endpoint *"returns `200` with a summary rather than failing wholesale."* Neither has a frontend criterion, and no story asserts that the summary is shown to the Admin who triggered the edit.

*Impact.* An Admin adds a holiday. The response is `200`. Three Employees' balances were silently left unchanged because recalculating them would have driven `Available` negative; rows were written to `admin_review_flag`. The Admin is told nothing, and no screen exists to read the flags. Since `FR-10` grants only a read and *"no endpoint clears a flag,"* the flags accumulate unseen.

The literal requirement is satisfied — `FR-10` grants a read and the endpoint provides it. But this is the exact failure mode the product exists to prevent. PRD §1: *"a leave balance that is wrong is worse than a leave balance that is absent, because it will be believed."* Here the Admin believes a holiday edit fully succeeded when it partially did not.

*Recommendation:* Add a frontend criterion to Story 2.11 surfacing the `200` summary at the moment of the edit, plus an Admin review-flags screen. This is small and it protects the product's central claim.

**🟡 F-8 (LOW) — Two more Admin read surfaces have endpoints and no screen.**

`GET /api/v1/audit-entries` (Story 2.9) and `GET /api/v1/policy-changes` (Story 2.12) are both Admin-only reads with no frontend criterion. Neither the PRD nor `FR-16` requires a *screen* — the endpoint satisfies the requirement as written — so this is recorded rather than escalated. It is, however, the same pattern as F-5 through F-7.

**🟡 F-9 (LOW) — `POST /cancellation-requests/<id>/reject` is never named.**

Story 2.8 asserts the rejection's *behavior* (*"a rejection changes nothing, and no role other than Admin may decide it"*) without naming the endpoint that `api-contracts.md:189` defines. Cosmetic; the behavior is covered.

*(Checked and dismissed as a false positive: `POST /leave-requests/<id>/reject` appeared unstoried by mechanical diff, but Story 2.7 names it as* `POST /api/v1/leave-requests/<id>/approve` or `.../reject`. *Not a finding.)*

### Warnings

1. **⚠️ UX specification absent while UI is implied.** Accepted and well-mitigated (see above). Recorded so the absence reads as a decision.
2. **🔴 The Admin persona's interface is materially under-specified relative to the Employee and Manager.** F-5 makes an in-scope, deliberately-reinstated capability (`BR-05` / `DR-14`) unreachable. F-6 makes `FR-06`'s mandatory disposition uncollectable. F-7 hides the one signal that tells an Admin a balance recalculation silently didn't happen.
3. **No architectural gap.** Every one of these is fixable inside the epics document by adding acceptance criteria. None requires an architecture change: `AD-10` already scopes the reads, `AD-20` already stores the flags, and `api-contracts.md` already defines `GET /cancellation-requests`. **The architecture anticipated all three surfaces; the stories did not carry them.**

### UX Verdict

**CONDITIONAL PASS.** Proceeding without a UX specification is defensible for this project and this budget. The PRD↔Architecture alignment on interface requirements is sound. But **F-5 is a genuine functional hole, not a cosmetic one**, and should be closed before Epic 2 is implemented — it is the difference between `BR-05` being a live rule and being documented-but-unreachable policy, which is precisely the state the PRD reversed `D-07` to escape.

---

## Step 5: Epic Quality Review

Validated against `create-epics-and-stories` standards: user value, epic independence, forward dependencies, story sizing, acceptance-criteria quality, table-creation timing, and the starter-template rule.

### A. Epic Structure Validation

**User Value Focus — ✅ PASS (all four epics).**

No technical-milestone epics. There is no "Set up database," no "API development," no "Infrastructure setup." Every epic title and goal names a user outcome:

| Epic | Title | User-value framing | Verdict |
|---|---|---|---|
| 1 | Secure Access and Organization Administration | *"An Admin can stand up the organization … everyone with an account can log in"* | ✓ Pass |
| 2 | Trustworthy Leave Balances and the Request Lifecycle | *"An Employee sees what a request will cost … before committing to it"* | ✓ Pass |
| 3 | Visibility and Decision Support | *"A Manager sees which Direct Reports are already away at the moment of decision"* | ✓ Pass |
| 4 | Supporting Documents and Reporting | *"An Employee attaches the document their leave type requires"* | ✓ Pass |

Epic 1 is the borderline case the checklist warns about ("Authentication System — is that user value?"). It survives: it is scoped as *organization administration*, delivering Departments, Employees, reporting lines and self-service profile editing — an Admin can genuinely use it alone. It is not "Authentication System."

**Epic Independence — ❌ FAIL.** See **F-1** (Step 3). Epic 2 requires Epic 3's `GET /leave-requests` and `GET /leave-requests/<id>` for Stories 2.7 and 2.8 to satisfy their own frontend acceptance criteria. `epics.md:399` asserts the opposite. Epics 1, 3 and 4 pass: Epic 3 consumes only Epics 1–2, Epic 4 consumes only Epics 2–3.

### B. Story Quality Assessment

**Acceptance-Criteria Format — ✅ EXCELLENT.** All 172 acceptance criteria across 27 stories use proper `Given / When / Then / And` BDD structure. They are specific and machine-checkable to an unusual degree — schema criteria name columns, constraints and index predicates; concurrency criteria name the isolation behavior; the day-count criterion names the arithmetic (*"a Friday-to-Tuesday range … Then it is 2"*). There is no "user can login"-class vagueness anywhere in the document.

Error paths are covered thoroughly: `INSUFFICIENT_BALANCE`, `SPANS_TWO_LEAVE_YEARS`, `ZERO_LEAVE_DAYS`, `INVALID_DATE_RANGE`, `PAST_DATE_RANGE`, `LEAVE_ALREADY_TAKEN`, `TRANSITION_NOT_ALLOWED`, `DEPARTMENT_NOT_EMPTY`, `EMPLOYEE_HAS_PENDING_REQUESTS`, `EMPLOYEE_HAS_DIRECT_REPORTS`, `POLICY_DISPOSITION_REQUIRED`, `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`, `SUPPORTING_DOCUMENT_REQUIRED`.

Two criteria deserve specific praise as evidence of real rigor:
- Story 1.2 **replaces** a wall-clock timing assertion with a structural one (*"the login path executes exactly one password hash comparison, against a constant fallback hash"*), explicitly because a timing assertion "would have been a flaky test rather than an acceptance criterion."
- Story 2.10 asserts rollover idempotence *and* the `DR-7a` top-up case (a Pending request crossing the boundary, later rejected, raising `available(Y)` and re-deriving `carried_forward(Y+1)`).

**Story Sizing — 🟠 CONCERN.** See **F-13** below.

### C. Dependency Analysis

**Within-epic dependencies — ✅ PASS.** All within-epic ordering is backward or disclosed. Every forward *reference* in the document is a deliberate note, stated in place, and none creates a functional block:

- Story 1.4 → 1.5/1.7: *"Its first scoped resource is a Department in Story 1.5"* — the story delivers mechanism and unit tests; complete alone.
- Story 1.6 → Epic 2: the `EMPLOYEE_HAS_PENDING_REQUESTS` guard is, in the document's own words, *"vacuously satisfied in this epic"* and re-asserted as a running test in Story 2.6. Honest.
- Story 2.2 → 2.11: *"Adding or deleting a holiday also recalculates existing Leave Requests. That behavior needs `leave_request` and `leave_balance`, so it lands in Story 2.11."* Story 2.2 is complete alone.

**This is the important point about F-1:** the epics document discloses *every forward reference it is aware of*. F-1 is the single dependency it is **not** aware of — Stories 2.7 and 2.8 never mention Story 3.1, because the dependency is implicit in "open their queue" and "view an Approved request" rather than stated. Undisclosed dependencies are the dangerous kind.

**Database/entity creation timing — 🟠 MOSTLY EXCELLENT, TWO TABLES NEVER CREATED.**

The document follows the correct pattern — each story creates only the tables it needs — and enforces it with an explicit criterion in Story 1.1: *"no domain table has been created by this story."* Story 1.2 likewise asserts *"`department` and `employee` exist and no other domain table does."* This is textbook.

Eleven of the ERD's thirteen entities have an explicit creating story:

| Table | Created by | | Table | Created by |
|---|---|---|---|---|
| `department`, `employee` | Story 1.2 | | `cancellation_request` | Story 2.8 |
| `leave_type` | Story 2.1 | | `rollover_run` | Story 2.10 |
| `company_holiday` | Story 2.2 | | `notification` | Story 3.4 |
| `leave_balance` | Story 2.4 | | `supporting_document` | Story 4.1 |
| `leave_request`, `audit_entry` | Story 2.6 | | **`admin_review_flag`** | ❌ **none** |
| | | | **`policy_change`** | ❌ **none** |

See **F-10**.

### D. Special Implementation Checks

**Starter template — ✅ PASS, and handled better than the checklist requires.**

The checklist rule is: *if Architecture specifies a starter template, Epic 1 Story 1 must be "set up from starter template."* Here the Architecture **explicitly evaluated and rejected** one, and the epics document reproduces the reasoning under a 🚨 banner (lines 125–129): `fastapi/full-stack-fastapi-template` was rejected because it ships **SQLModel**, whose fusion of Pydantic schema and SQLAlchemy table is exactly the coupling `AD-1` forbids and which dissolves the structural guarantee `DR-2` depends on; it also ships email-based password recovery, a PRD §6 non-goal. Its `docker-compose` and Alembic wiring are retained as reference only.

Story 1.1 correctly scaffolds the four-package tree by hand. **This is a case where the plan anticipated the checklist item and answered it with a documented rationale.** Compliant.

**Greenfield indicators — ✅ mostly.** Initial project setup story ✓ (1.1). Development environment configuration ✓ (`.env.example`, `docker compose up`, `NFR-21` three-command setup). **CI/CD pipeline — no story.** See **F-14** (minor).

### E. Findings

#### 🔴 Critical Violations

**F-1 (carried from Step 3) — Forward dependency breaking epic independence.** Epic 2's Stories 2.7 and 2.8 cannot satisfy their frontend acceptance criteria without `GET /leave-requests` and `GET /leave-requests/<id>`, first delivered by Epic 3's Story 3.1. The document explicitly claims *"none requires a future epic to function."* This is the checklist's canonical critical violation ("Epic 2 requires Epic 3 features to function"), and it is undisclosed.

**F-5 (carried from Step 4) — `GET /cancellation-requests` delivered by no story.** Makes `DR-14`/`BR-05` unreachable in practice.

#### 🟠 Major Issues

**F-10 (MEDIUM) — Two tables are written to but never created.**

`AD-20` defines `admin_review_flag` and `policy_change`; the ERD lists both among its thirteen entities. Story 2.11 asserts *"a row is written to `admin_review_flag`"* and Story 2.12 asserts *"a `policy_change` row records …"*. **Neither story carries a `Given a database migrated by this story / When the schema is inspected` criterion** — they are the only two stories in Epic 2 that introduce persistence without a schema criterion, and no other story creates these tables.

*Impact:* an implementer following the stories literally writes to two nonexistent tables. The Alembic migration has no owning story, so the `admin_review_flag` columns (cause, subject Employee, subject Leave Type) and the `policy_change` columns (leave type, attribute, old value, new value, disposition, moment — and explicitly **no actor column**, per `AD-20`) are never fixed by any acceptance criterion. Both are also the stores behind F-6 and F-7.

*Recommendation:* add a schema-migration criterion to Story 2.11 (`admin_review_flag`) and Story 2.12 (`policy_change`), matching the pattern used by the other nine table-creating stories, and asserting `policy_change`'s deliberate absence of an actor column.

**F-11 (MEDIUM) — The document crossed its own gate; six acceptance criteria are unassertable as written.**

`G3` (status code for a role-denied read) states its own blocking condition at `epics.md:345`: **"Settle before Epic 2 story creation."** All twelve Epic 2 stories, and all five Epic 3 stories, were nevertheless written with `G3` open. The consequence is visible in the text — six acceptance criteria assert a refusal without an assertable outcome:

| Story | Criterion | Missing |
|---|---|---|
| 1.6 | *"the request is refused server-side, and nothing is read or written"* | status code (`G3`) |
| 1.8 | *"the attempt is refused and nothing is persisted"* | status + error code (`G5`) |
| 2.9 | *"no Employee or Manager can read the audit log"* | status code (`G3`) |
| 2.11 | *"they read the recorded refusals, and no other role can"* | status code (`G3`) |
| 2.12 | *"they read the recorded changes … and no other role can"* | status code (`G3`) |
| 3.2 | *"the request is refused server-side"* — annotated *"(No status code asserted, per `G3`.)"* | status code (`G3`) |
| 3.5 | *"an Employee calling `GET /dashboard/manager` is refused"* | status code (`G3`) |

The document is *honest* about each omission and points at the gap. But `G3` predicted exactly this — *"Two epics decide it differently, precisely the divergence api-contracts exists to prevent"* — and the gate it set to prevent it was passed. A developer implementing Story 2.9 must invent a status code, and a developer implementing Story 3.2 must invent it again.

*Recommendation:* `G3` is a **one-line decision** (choose `403` for role-denied reads and amend `api-contracts.md §1`'s definition, or choose `404` and reconcile with `AD-10`). It unblocks seven criteria across three epics. Settle it before any Epic 2 or Epic 3 story is coded. `G5` is similarly trivial.

**F-12 (MEDIUM–HIGH) — `G7` is not a documentation gap; it is a latent authorization defect that will ship.**

The epics state *"None of `G2`–`G8` blocks implementation"* and *"neither prevents any story below from being built or tested."* Both statements are true and both are beside the point for `G7`.

`G7`: nothing forbids a reporting cycle, so an Employee may be their own Manager. As the document itself works out: *"An Employee who is their own Manager approves their own leave. `FR-09` grants approval to 'the Manager of the applicant,' and `DR-12` derives that authority from the relationship rather than the role, so the check passes."*

Every story in Epic 2 can be built and can pass. `SM-3` ("authorization is scoped to data, not to role") would report green — self-approval *is* data-scoped. **The system would ship with a self-approval hole and every declared metric satisfied.** The same reasoning applies to `G8`: demoting a Manager who still holds Direct Reports orphans them, reaching *"precisely the orphaning `AD-22` exists to prevent, through a door `AD-22` does not cover."*

"Does not block implementation" and "is safe to implement" are different claims. The epics prove the first and are read as asserting the second.

*Recommendation:* `G7` closes with one `CHECK (id <> manager_id)` plus a cycle guard in the employee service; `G8` closes by extending `AD-22`'s guard from `deactivate` to any `PATCH` that lowers `role` below `MANAGER`. Both are small, both belong in Epic 1's Story 1.6, and both should be settled before Epic 2 is coded — which is when they become reachable.

**F-13 (MEDIUM–HIGH) — Story volume is not sized to the declared budget, and the plan's stated risk understates it.**

The implementation budget is **three days** (Days 3–5 of seven; PRD §9, restated in `epics.md:205`). The plan is **27 full-stack vertical-slice stories carrying 172 acceptance criteria**, each story shipping "its backend and its React surface together."

| Epic | Stories | Given-blocks | Phase |
|---|---|---|---|
| 1 | 8 | 57 | Phase 1 |
| 2 | 12 | 74 | Phase 1 |
| 3 | 5 | 30 | Phase 2 |
| 4 | 2 | 11 | Phase 3 |
| **Total** | **27** | **172** | |

That is nine full-stack stories per day, or roughly 57 acceptance criteria per day. **Phase 1 alone — the "correctness core" that must not be compromised — is 20 stories and 131 acceptance criteria, 76% of the total.**

The planning documents declare exactly one budget risk: that **Phase 3** (`FR-13`, `FR-15` — 2 stories, 11 criteria) may go undelivered. That is the *cheapest* 6% of the plan. The arithmetic says the exposure is in Phase 1, and no document acknowledges it.

This is not a defect in the epics — the stories are correctly decomposed and the decomposition is honest. It is a **plan-versus-budget risk that the artifacts under-declare**, and `SM-C1` ("when coverage and correctness compete for the last hours, correctness wins, and the shortfall is declared") is the mechanism that will be invoked. Surfacing it now is better than invoking it on Day 5.

*Recommendation:* re-examine the three-day figure against 172 criteria before Day 3 begins, and decide *in advance* which Phase 1 stories carry reduced frontend scope if the budget compresses. Note that Epic 1's Story 1.1 alone carries 8 criteria spanning Docker, Alembic, TLS proxy, import-direction enforcement, dependency pinning, and a Vite/React/TanStack Query SPA shell.

#### 🟡 Minor Concerns

**F-4 (carried from Step 3)** — Epic 3's note promises an `FR-14` hook into `services/cancellation` for which no notification `kind` exists.

**F-9 (carried from Step 4)** — `POST /cancellation-requests/<id>/reject` behavior is asserted but the endpoint is never named.

**F-14 (LOW) — Build-failing checks are asserted; no CI story owns them.** Story 1.1 requires that an import-direction violation *"fails the build rather than merely warning,"* and Story 1.2 requires *"a standing check fails the build"* for `AD-21` literals. No story establishes the pipeline in which a build fails. `NFR-21` covers reproducible local setup, not CI, and Module 1 does not require CI. Defensible for a three-day trainee project; recorded because two acceptance criteria depend on a mechanism no story creates.

**F-15 (LOW) — Seven open gaps live only in the epics artifact.** `epics.md:294`: *"**Nothing has been routed upstream**"* for `G2`–`G8`. The PRD (§11) simultaneously declares *"No open question blocks implementation … Every product decision this PRD depends on has been made."* Both are locally true, but a reader of the PRD alone would not know that seven decisions remain open. `G1` was correctly amended back into the PRD, addendum, `api-contracts.md`, `architecture.md` and the ERD — that precedent should be followed for `G2`–`G8` as they are settled.

**F-16 (MEDIUM) — Module 1 is stale in three ways, and it is still an input document.**

`epics.md` lists `module-1-business-analysis/brd.md`, `functional-requirements.md`, `non-functional-requirements.md` and `assumptions-and-constraints.md` among its `inputDocuments`. All four remain unamended against decisions the PRD has since made:

1. **`D-07` was reversed by `DR-14`, and the BRD does not know it.** `brd.md:74` still records `BR-05` as *"Not reachable under the defined permissions — approved-leave cancellation is out of scope by D-07,"* and `brd.md:99` still explains the scope narrowing. The PRD reversed this: approved-leave cancellation is in scope via a Cancellation Request an Admin decides. **Anyone sourcing scope from the BRD builds the wrong product** — they would omit Story 2.8 entirely.
2. **`FR-19` and `FR-20` have no requirement bodies in Module 1.** They appear only in its role matrix (line 125–126) and an amendment note (line 133) that says they *"are now required capabilities, specified in the PRD."* The bodies were never written.
3. **Module 1's role-to-requirement matrix is wrong on `FR-11`**, assigning it to Admin and Manager only, contradicting Module 1's own `FR-11` prose. The PRD flags this in §4.6 and states plainly: *"The matrix is wrong and needs correcting upstream — this PRD is not the defect."* It was not corrected.

Additionally, **`NFR-19` is cited by `DR-16` but never restated in PRD §8**, so a story tracing to it must reach into Module 1 to find it. A documentation seam rather than a missing requirement.

*Impact:* the PRD and epics are internally correct and consistent with each other. The risk is entirely to a reader — or a downstream workflow — that treats Module 1 as authoritative, which `epics.md`'s own `inputDocuments` list invites.

*Recommendation:* amend `brd.md` to record `D-07`'s reversal, add `FR-19`/`FR-20` bodies to `functional-requirements.md`, and fix the `FR-11` row of the role matrix. Follow `G1`'s precedent, which was amended into five documents rather than left in one.

### F. Best-Practices Compliance Checklist

| Check | Epic 1 | Epic 2 | Epic 3 | Epic 4 |
|---|---|---|---|---|
| Epic delivers user value | ✅ | ✅ | ✅ | ✅ |
| Epic can function independently | ✅ | ❌ **F-1** | ✅ | ✅ |
| Stories appropriately sized | ⚠️ **F-13** | ⚠️ **F-13** | ✅ | ✅ |
| No forward dependencies | ✅ | ❌ **F-1** | ✅ | ✅ |
| Database tables created when needed | ✅ | ❌ **F-10** | ✅ | ✅ |
| Clear acceptance criteria | ⚠️ **F-11** | ⚠️ **F-11** | ⚠️ **F-11** | ✅ |
| Traceability to FRs maintained | ✅ | ⚠️ **F-2** | ✅ | ✅ |
| Starter-template rule honored | ✅ | — | — | — |

### Quality Verdict

**CONDITIONAL PASS.** The epics are, in craft terms, the strongest artifact in this set: user-value framing throughout, 172 rigorously testable BDD criteria, disciplined table-creation timing, and a documented rationale for rejecting the starter template. The document repeatedly catches its own weaknesses and says so in place.

The failures are concentrated and fixable. **Epic 2 carries all three structural defects** (F-1 forward dependency, F-10 uncreated tables, and the F-5/F-6/F-7 Admin surfaces) — which is unsurprising, since Epic 2 is 12 stories and 74 criteria of mutually-dependent correctness logic that the document declined to split for good reasons. None of them requires an architecture change. All can be closed by editing `epics.md`.

---

## Summary and Recommendations

### Overall Readiness Status

# ⚠️ NEEDS WORK

Not *NOT READY* — the foundations are sound and no finding requires re-architecting anything. Not *READY* either: as the artifacts currently stand, implementing them faithfully produces a system with an unreachable in-scope capability, a self-approval authorization hole, and two tables that no migration creates.

**What is genuinely strong, stated plainly because it is unusual:**

- **100% functional-requirement coverage**, independently verified against story acceptance criteria rather than accepted from the coverage map. All 20 FRs trace to stories that assert a stated testable consequence. No requirement is orphaned; none is invented.
- **The PRD has zero open questions and zero assumptions, and the claim survives inspection.** The `[ASSUMPTION:` tag appears nowhere in its body. `DR-7`/`DR-7a` notice that a Pending request crossing the Leave Year boundary leaves the two rules *jointly under-determined*, and supply the reading that resolves it. Most PRDs never reach that level of rigor.
- **The Architecture found five real defects in its own upstream documents and routed all five back** rather than absorbing them silently — including that `FR-07`'s original rollover wording would have made success metric `SM-4` false the day it was written.
- **172 acceptance criteria in disciplined BDD form**, specific enough to test. Story 1.2 explicitly *replaces* a flaky wall-clock timing assertion with a structural one, on the grounds that a flaky test is not an acceptance criterion.
- **`AD-2` structurally forbids the highest-risk frontend defect** — a duplicate day-count implementation — by making "no frontend module references a weekday or a holiday" a testable criterion.

The findings below are not a verdict on the quality of this planning. They are the residue left after checking work that was already good.

### Critical Issues Requiring Immediate Action

**1. 🔴 F-5 — `BR-05` is unreachable. The Admin cannot find a Cancellation Request to decide.**

`api-contracts.md:187` defines `GET /cancellation-requests`. **No story delivers it.** No notification is addressed to an Admin (`FR-14`'s three kinds all target the Manager or the applicant). The Admin dashboard's "Pending request count" means Leave Requests. There is no Admin decision screen. The only way to reach `POST /cancellation-requests/<id>/approve` is to guess a UUIDv7 primary key that the ERD deliberately made non-enumerable.

An Employee raises a Cancellation Request; it sits Pending forever; the Leave Request stays Approved with its days Consumed.

This is a regression against a decision the PRD made on purpose. `D-07` ruled approved-leave cancellation out of scope *because "the specification authorizes no role to do it."* `DR-14` reversed that so `BR-05` would be *"a live rule rather than documented-but-unreachable policy."* **As storied, it is documented-but-unreachable policy again** — by discoverability rather than by permission.

**2. 🔴 F-1 — Epic 2 requires Epic 3, and does not know it.**

Stories 2.7 (*"they open their queue"*) and 2.8 (*"they view an Approved future-dated request"*) require `GET /leave-requests` and `GET /leave-requests/<id>`, which Story 3.1 first delivers in Epic 3. `epics.md:399` asserts *"none requires a future epic to function."*

Epics 1+2 are PRD §7.1's Phase 1 — the correctness core the budget funds first. **Completing Phase 1 as sequenced yields a system in which a Manager cannot see the queue they are meant to decide from.** Every other forward reference in the document is disclosed in place; this one is implicit, which is why it survived.

**3. 🔴 F-12 — `G7` ships a self-approval hole with every metric green.**

Nothing forbids an Employee being their own Manager. The epics work the consequence out themselves: *"An Employee who is their own Manager approves their own leave … the check passes."* Every Epic 2 story still builds and passes. `SM-3` ("authorization is scoped to data, not to role") reports green, because self-approval **is** data-scoped.

The epics say `G2`–`G8` do not *block implementation*. True — and routinely read as "safe to implement." They are different claims. `G8` is the same shape: demoting a Manager who still holds Direct Reports reaches *"precisely the orphaning `AD-22` exists to prevent, through a door `AD-22` does not cover."*

**4. 🟠 F-10 — Two tables are written to and never created.**

`admin_review_flag` (Story 2.11) and `policy_change` (Story 2.12) are the only two of the ERD's thirteen entities with no schema-migration criterion in any story. An implementer following the stories literally writes to tables that do not exist.

**5. 🟠 F-11 — The epics crossed their own gate. Seven acceptance criteria have no assertable outcome.**

`G3` states: **"Settle before Epic 2 story creation."** Twelve Epic 2 stories and five Epic 3 stories were written with it open. Seven criteria now assert *"is refused server-side"* / *"no other role can"* with no status code. `G3` predicted this exactly: *"Two epics decide it differently — precisely the divergence api-contracts exists to prevent."*

**6. 🟠 F-6 — `FR-06` compels a choice that no screen collects.**

A Leave Type edit requires a `RECALCULATE`/`PRESERVE` disposition (Story 2.12 correctly returns `400 POLICY_DISPOSITION_REQUIRED` without one). Story 2.1's only Admin UI criterion covers *creating* a Leave Type. **In the React app, every Leave Type edit returns 400.**

### The Open-Gap Gate Schedule

`G2`–`G8` are open and, per `epics.md:294`, **nothing has been routed upstream.** Meanwhile PRD §11 declares *"No open question blocks implementation."* Both are locally true; a reader of the PRD alone would not know seven decisions remain open. Their own gates, ordered by urgency:

| Gap | The document's own gate | Status |
|---|---|---|
| `G3` role-denied read status code | *"Settle before Epic 2 story creation"* | 🔴 **Gate already crossed** |
| `G2` duplicate email refusal | *"before Story 1.6 is implemented"* | 🟠 Story 1.6 is Epic 1 — **due on Day 3** |
| `G7` reporting cycle / self-approval | *"becomes reachable in Epic 2"* | 🔴 Correctness defect (F-12) |
| `G8` demoting a Manager with reports | *"becomes reachable in Epic 2"* | 🔴 Correctness defect (F-12) |
| `G4` token for deactivated Employee | *"decide before deployment"* | 🟡 Security-relevant |
| `G5` `PATCH /me` forbidden-field code | *"Trivial once decided"* | 🟡 Blocks one AC |
| `G6` `DELETE /departments` 2xx code | *"Cosmetic"* | 🟢 Cosmetic |

`G1` was correctly amended back into the PRD, addendum, `api-contracts.md`, `architecture.md` and the ERD. **That precedent should be followed for the rest.**

### A Risk the Artifacts Do Not Declare

**F-13.** The implementation budget is **three days**. The plan is **27 full-stack vertical-slice stories carrying 172 acceptance criteria** — nine stories per day, each shipping backend and React surface together.

The documents declare exactly one budget risk: that **Phase 3** may go undelivered. Phase 3 is 2 stories and 11 criteria — the cheapest 6% of the plan. **Phase 1 alone is 20 stories and 131 criteria, 76% of the total.** The exposure is in Phase 1, and no artifact says so. `SM-C1` ("when coverage and correctness compete for the last hours, correctness wins, and the shortfall is declared") is the mechanism that will be invoked. Better to decide the shortfall now than on Day 5.

### Recommended Next Steps

**Before Day 3 (implementation start) — all six are edits to `epics.md`; none touches the architecture:**

1. **Settle `G3` and `G5`.** One decision each. `G3` unblocks seven acceptance criteria across three epics. Choose `403` for role-denied reads and amend `api-contracts.md §1`'s definition of `403`, or choose `404` and reconcile with `AD-10`. Amend upstream, following `G1`'s precedent.
2. **Close `G7` and `G8`** (F-12). `G7`: a `CHECK (id <> manager_id)` plus a cycle guard in the employee service. `G8`: extend `AD-22`'s guard from `deactivate` to any `PATCH` lowering `role` below `MANAGER`. Both belong in Story 1.6, both are small, and both become reachable in Epic 2.
3. **Add `GET /cancellation-requests` and an Admin decision queue to Story 2.8** (F-5). Name `POST /cancellation-requests/<id>/reject` explicitly (F-9). Consider a fourth notification kind addressed to the Admin — which also settles F-4, since Epic 3 already promises an `FR-14` hook into `services/cancellation` that has no kind to write.
4. **Resolve F-1.** Either move a minimal `GET /leave-requests` + `GET /leave-requests/<id>` (self + reports scope, no composable filters) into Epic 2 — leaving `FR-12`'s filters and `FR-20`'s cross-year history in Story 3.1, the same seam already used to split `NFR-11`'s page bound from `FR-12`'s filters — or withdraw the "stands alone" claim and state the dependency.
5. **Add schema-migration criteria** to Story 2.11 (`admin_review_flag`) and Story 2.12 (`policy_change`), matching the pattern the other nine table-creating stories use (F-10). Assert `policy_change`'s deliberate absence of an actor column, per `AD-20`.
6. **Add a frontend criterion to Story 2.12** collecting the `RECALCULATE`/`PRESERVE` disposition (F-6), and to Story 2.11 surfacing the `200` summary and an Admin review-flags screen (F-7).

**Before Day 3, non-editorial:**

7. **Re-baseline the three-day budget against 172 acceptance criteria** (F-13), and decide *in advance* which Phase 1 stories ship with reduced frontend scope if it compresses. Story 1.1 alone spans Docker, Alembic, a TLS proxy, import-direction enforcement, dependency pinning, and a Vite/React/TanStack Query SPA shell.
8. **Settle `G2`** (duplicate email) — its own gate is Story 1.6, which is Day 3.

**During or after implementation:**

9. **Add the missing `FR-` citations** to Stories 2.1 (`FR-06`), 2.5 and 2.6 (`FR-08`), and 2.10 (`FR-07`) (F-2). `SM-8` tracks delivery per requirement; as labelled, a tracker would under-report the two FRs carrying the product's central correctness claim.
10. **Amend Module 1** (F-16): the BRD still records `D-07` and `BR-05` as out-of-scope/unreachable, which `DR-14` reversed; `FR-19` and `FR-20` exist only in the PRD; and Module 1's role-to-requirement matrix is wrong on `FR-11` by the PRD's own account. Anyone sourcing scope from the BRD builds the wrong product.
11. **Decide `G4`** before deployment (security-relevant) and `G6` whenever convenient (cosmetic).

### What This Assessment Did Not Find

Stated so their absence reads as a check performed, not a check skipped:

- **No missing functional requirement.** Coverage is genuinely 100%.
- **No architectural gap.** Every finding is fixable in `epics.md`. `AD-10` already scopes the reads F-5 needs, `AD-20` already defines the stores F-10 must create, and `api-contracts.md` already declares the endpoint F-5 is missing. **The architecture anticipated every one of these surfaces; the stories did not carry them.**
- **No technical-milestone epics**, no vague acceptance criteria, no circular dependency, no starter-template violation.
- **No duplicate or sharded document conflicts.**

### Standing Risks (accepted, not defects)

- **All 21 NFRs are engineer-proposed and unconfirmed by the assigning manager.** The PRD says so plainly. Every NFR-derived acceptance criterion rests on engineer judgment.
- **`NFR-10` (~500 ms reads) is verified by no story** — declared openly in the epics' NFR table.
- **Known production limitations**, each recorded rather than solved: Earned Leave above the Carry-Forward Cap is forfeited where Indian statute generally requires encashment; there is no password recovery path and lockout is permanent; audit attribution binds an account rather than a person.

### Final Note

This assessment identified **16 findings across 5 categories** (requirement coverage, interface completeness, structural dependencies, story quality and traceability, and plan-versus-budget). **Six are blocking** and every one of them is an edit to `epics.md`, not a redesign.

The pattern worth carrying away: **this plan specifies commands rigorously and queries spottily.** Every mutation — submit, approve, reject, cancel, recalculate, roll over — has a story, an endpoint, error codes and a screen. Several reads that the same actors depend on (`GET /cancellation-requests`, `GET /leave-requests` in Epic 2, the `admin_review_flag` screen, the policy-disposition form) have an endpoint in the contract, an invariant in the architecture, and no story. `NFR-16` requires that a control a role *cannot* invoke is not rendered. **Nothing anywhere requires that a control a role *must* invoke *is* rendered** — and that single missing rule is where F-5, F-6 and F-7 all live.

Address the six blocking findings and this plan is ready to build. They are, collectively, perhaps two hours of editing.

---

**Assessed by:** Implementation Readiness workflow (`bmad-check-implementation-readiness`)
**Assessor role:** Product Manager — requirements traceability and planning-gap analysis
**Date:** 2026-07-10
**Documents assessed:** PRD + addendum, Architecture (solution, spine, API contracts), Epics & Stories, ERD, Module 1 Business Analysis (BRD, FR, NFR, assumptions), Product Brief
**UX specification:** none (absent by confirmed product-owner decision, 2026-07-10)

---

## Remediation Applied — 2026-07-10

All six blocking findings are closed. Amendments were made to `epics.md`, `api-contracts.md` and `erd.md`, and routed upstream following the precedent `G1` set. **No architecture invariant was reversed; two were added or widened.**

### Decisions taken

| Gap | Decision | Recorded in |
|---|---|---|
| `G3` role-denied read | **`403 ACTION_NOT_PERMITTED`** — api-contracts §1's `403` widened to *"the actor's **role** does not grant this endpoint, **or** may see but may not act."* The distinguishing test: does the actor's role admit them to this endpoint at all? If no → `403`, before any row is read. If yes → the scope predicate runs and a miss is `404`. **`AD-10` unchanged**; its `404` still means exactly one thing. | api-contracts §1, §2; epics |
| `G2` duplicate email | **`409 EMAIL_ALREADY_IN_USE`**, raised by the service before the write, never surfaced from the `UNIQUE` violation. Does not disclose whether the holder is active. Extends `AD-5`'s "schema is the backstop, service is the gate" to `employee`. | api-contracts §2; Story 1.6 |
| `G5` `PATCH /me` forbidden field | **`400 FORBIDDEN_FIELD`**, `details` naming the rejected fields. `400` not `403`: the actor owns the resource; the domain refuses the request's *content*. FastAPI's `422` suppressed so the envelope holds. | api-contracts §2; Story 1.8 |
| `G7` reporting cycle | **`AD-23` added.** `CHECK (id <> manager_id)` as backstop; transitive cycle walk in the employee service as the gate, refusing `400 REPORTING_CYCLE`. | epics invariants; erd §4.2; Stories 1.2, 1.6 |
| `G8` demoting a Manager | **`AD-22` widened.** The Direct-Report guard now refuses any update lowering `role` below `MANAGER`, with the existing `409 EMPLOYEE_HAS_DIRECT_REPORTS`. Deactivation and demotion are two doors to one orphaning; both closed. | epics invariants; api-contracts §2; Story 1.6 |

`G4` (token for a since-deactivated Employee — security-relevant, decide before deployment) and `G6` (`DELETE /departments` 2xx code — cosmetic) remain open, as intended. Both are recorded and neither blocks.

### 🆕 F-17 — a latent hole found while fixing, not present in the original 16

**api-contracts §2 declared sixteen error codes and not one of them was a `403`** — while Story 1.5 already asserted `403` for an Employee calling `POST /departments`, Story 2.7 already asserted `403` for an Admin approving leave, and §2 requires *every* non-2xx body to carry the `{ code, message, details }` envelope. Any implementer hitting those two criteria would have invented a code that `AD-21` never declared. `ACTION_NOT_PERMITTED` closes it, independent of `G3`.

### Structural fixes

- **F-1** — `GET /leave-requests` and `GET /leave-requests/<id>` (scoped by `FR-03` alone, `status` filter only) moved into **Story 2.7**, which is where Epic 2's own criteria need them. Story 3.1 now *extends* them with `FR-12`'s composable filters and `FR-20`'s cross-Leave-Year history, using the same seam that already splits `NFR-11`'s page bound from `FR-12`'s filters. The false "stands alone" claim at the Epic List is corrected in place rather than deleted, with the reason it survived four reviews.
- **F-5** — `GET /cancellation-requests` added to **Story 2.8**, with an Admin decision-queue frontend criterion and an explicitly named `POST /cancellation-requests/<id>/reject`. `BR-05` is reachable again.
- **F-10** — schema-migration criteria added for **`admin_review_flag`** (Story 2.11) and **`policy_change`** (Story 2.12), matching the pattern the other nine table-creating stories use. `policy_change`'s deliberate absence of an actor column is asserted, per `AD-20`.
- **F-6** — Story 2.12 gains a frontend criterion requiring the Admin to choose `RECALCULATE` or `PRESERVE` before the form will submit. Without it, an Admin could create a Leave Type but never edit one.
- **F-7** — Story 2.11 gains two frontend criteria: the `200` summary must state how many Employee-and-Leave-Type pairs were **left unchanged**, naming each; and an Admin Review Flags screen. *An Admin is never shown an unqualified success for an operation that partially refused.*
- **F-2** — missing `FR-` citations added: `FR-06` → Story 2.1; `FR-08` → Stories 2.5 and 2.6; `FR-07` → Story 2.10. `SM-8`'s per-requirement tracker now resolves correctly for the two FRs carrying the product's central correctness claim.
- **F-3** — the FR Coverage Map's "no FR is split across epics" is restated as "**owned** by exactly one epic," with the three disclosed exceptions named.
- **F-4** — Epic 3's note corrected: `services/cancellation` writes **no** Notification. `FR-14`'s three kinds are exhaustive, and notifying "the Admin" would require a fan-out semantics no source fixes while `FR-14` demands *exactly one* Notification per event. Discovery is by queue, not by notification.
- **F-9** — `POST /cancellation-requests/<id>/reject` named, with the assertion that a rejection leaves the Leave Request `APPROVED` and its days `consumed`.
- **F-11** — all seven previously unassertable criteria now name a status and an error code (Stories 1.6, 1.8, 2.7, 2.9, 2.11, 2.12, 3.2, 3.5).
- **F-12** — `G7` and `G8` closed as above, in Story 1.6, deliberately upstream of the approval path that would have exploited them.

### Verification

Re-ran the mechanical checks that originally found the defects:

| Check | Before | After |
|---|---|---|
| api-contracts endpoints with no story | 3 (1 real, 2 nominal) | **0** (`.../reject` shorthand only) |
| ERD tables with no creating story | 2 | **0** |
| Acceptance criteria asserting a refusal with no code | 7 | **0** |
| FRs with no story citation | 0 | **0** |
| `FR-06` / `FR-07` / `FR-08` story citations | 1 / 1 / 1 | **3 / 2 / 3** |
| Open gaps | 7 | **2** (`G4`, `G6` — neither blocking) |

### Status After Remediation

# ✅ READY — conditionally

**13 of 17 findings closed.** Zero blocking findings remain. Four are open, none of them a defect in the artifacts:

- **F-13 (MEDIUM–HIGH, decision required) — the budget.** Unresolved, and **the remediation made it worse**: the plan is now **191 acceptance criteria across 27 full-stack stories** (up from 172), against a **three-day** implementation budget. Epic 2 alone grew from 74 to 90 criteria. Phase 1 is now 150 criteria — 79% of the total — while the only budget risk any artifact declares is Phase 3's 11. **This needs a decision from the PM before Day 3, not a document edit.** Decide in advance which Phase 1 stories ship with reduced frontend scope, rather than discovering it on Day 5 and invoking `SM-C1`.
- **F-16 (MEDIUM) — Module 1 is stale.** `brd.md` still records `D-07` and `BR-05` as out-of-scope/unreachable, which `DR-14` reversed; `FR-19`/`FR-20` have no requirement bodies; the role matrix is wrong on `FR-11`. All four Module 1 files remain `inputDocuments` to the epics. Anyone sourcing scope from the BRD builds the wrong product. Fix when convenient — it misleads readers, not implementers.
- **F-8 (LOW)** — `GET /audit-entries` still has no screen. `FR-16` grants a read, not a screen, so the endpoint satisfies the requirement. (`GET /policy-changes` now has one.)
- **F-14 (LOW)** — no CI story owns the "fails the build" mechanism that Stories 1.1 and 1.2 depend on. Defensible for a three-day trainee project.

**The pattern that produced these findings, now closed:** this plan specified *commands* rigorously and *queries* spottily. `NFR-16` requires that a control a role **cannot** invoke is not rendered; nothing anywhere required that a control a role **must** invoke **is** rendered. F-5, F-6 and F-7 all lived in that blind spot. Worth carrying into the next project as a checklist item of its own.

**Recommended next step:** decide F-13, then run `[SP]` Sprint Planning (`bmad-sprint-planning`) in a fresh context window.
