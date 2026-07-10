---
title: "LeaveFlow — Functional Requirement Specification"
module: "1 — Understanding the Problem"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Functional Requirement Specification

Eighteen functional requirements, derived from the assignment specification and, where noted, from confirmed business rules and engineering decisions, and given stable identifiers for traceability. Downstream artifacts — epics, stories, API contracts, test cases — should cite these identifiers.

FR-01 through FR-16 come from the specification's enumerated requirements list. FR-17 and FR-18 come from permissions the specification grants in its role definitions but omits from that list. Both are specified capabilities, not invented ones.

Acceptance criteria are stated where the requirement admits a precise test. Where a requirement is too loosely specified to test, that is recorded rather than papered over.

**Source key.** `SPEC` — the assignment specification. `RULE` — a confirmed business rule, established by clarification during requirement analysis. `ENG` — an engineering decision made by the engineer. `OPEN` — an unresolved question, flagged inline with an **Open:** annotation on the affected requirement rather than appearing on a *Source* line; see `addendum.md`.

---

## Authentication and Authorization

### FR-01 — User Authentication
*Source: SPEC.* A user authenticates with credentials and receives a session. Unauthenticated requests to protected resources are refused.
**Acceptance:** Valid credentials establish a session. Invalid credentials are rejected without disclosing whether the account exists. Passwords are never stored in recoverable form.

### FR-02 — JWT-Based Authorization
*Source: SPEC.* Authenticated sessions are carried by a JSON Web Token presented on each request.
**Acceptance:** A request bearing no token, an expired token, or a tampered token is refused. A valid token identifies the user and their role.

### FR-03 — Role-Based Access Control
*Source: SPEC, ENG.* Every endpoint and UI surface is restricted to the roles permitted to reach it. Exactly three roles exist: Admin, Manager, Employee.
**Acceptance:** An Employee cannot reach Admin or Manager functions. A Manager can act only on their **own direct reports** — establishing that a user is a Manager is insufficient; the system must establish the reporting relationship. An Admin may view all leave requests but is not granted approval authority by the specification.

---

## Organization Management

### FR-04 — Employee Management
*Source: SPEC.* The Admin creates, views, updates, and deactivates employees and managers, including the reporting relationship that FR-03 depends on.
**Acceptance:** An employee record carries a department and a manager. Deactivation preserves historical leave records.

### FR-05 — Department Management
*Source: SPEC.* The Admin creates, views, updates, and removes departments.
**Acceptance:** A department cannot be removed while employees are assigned to it.

### FR-17 — Personal Profile Management
*Source: SPEC.* An employee views and updates their own personal profile.
**Acceptance:** A user may update only their own profile. Fields governing entitlement, authorization, or organizational structure — role, department, reporting manager, joining date, leave balances — are not editable by the profile owner.

---

## Leave Policy Configuration

### FR-06 — Leave Type Management
*Source: SPEC, RULE.* The Admin manages and configures leave types and their governing leave policies. Three types are confirmed: EL (Earned Leave), CL (Casual Leave), FL.
**Acceptance:** EL carries forward at year end; CL and FL lapse. This behaviour is configuration the Admin controls, not code — adding a fourth leave type requires no code change.
**Open:** The expanded name of FL; whether carried-forward EL is capped or expires; the accrual method.

### FR-07 — Leave Balance Tracking
*Source: SPEC, RULE, ENG.* The system computes and maintains each employee's leave balance per leave type and leave year.
**Acceptance:** A balance comprises three quantities — accrued, reserved, consumed — with available leave equal to `accrued − consumed − reserved`. Balances are partitioned by leave year, assumed to run 1 January to 31 December (A-09). A mid-year joiner receives a prorated balance. Carry-forward and lapse behaviour is governed by FR-06.
**Open:** The proration method and its rounding.

### FR-10 — Holiday Management
*Source: SPEC, ENG.* The Admin maintains the company holiday calendar. Holidays are an **input to the leave-day calculation** (FR-08), not merely an administrative screen.
**Acceptance:** A date marked as a holiday is excluded from any leave-day count spanning it.
**Assumption:** Holidays are global, not scoped by location or department.

---

## Leave Request Lifecycle

### FR-08 — Leave Request Workflow
*Source: SPEC, RULE, ENG.* An employee submits a leave request for a date range against a leave type. The system computes the leave days and reserves them.
**Acceptance:** Only working days are deducted; weekends and company holidays are excluded. A Friday-to-Tuesday request spanning a weekend and one holiday counts as two days. A request may not span two calendar years — a leave crossing year-end is submitted as a separate application for each calendar year. A request whose day-count exceeds available leave is refused at submission.

### FR-09 — Approval and Rejection Process
*Source: SPEC, RULE, ENG.* A Manager approves or rejects a pending request from a direct report.
**Acceptance:** Approval converts the reservation into consumption. Rejection releases the reservation. An employee may cancel their own **pending** request, releasing the reservation. No restriction applies when several team members request the same dates.
**Out of scope, by decision D-07.** Cancellation of **approved** leave is not supported. The specification authorizes it to nobody — Employees may cancel only pending requests, Managers may only approve or reject, Admins may only view — and the scope follows the specification rather than inventing a permission. The confirmed rule that cancelling approved leave restores the balance (BR-05) is retained as a policy clarification only; it is not reachable under the defined permissions, and no approved-cancellation transition is to be implemented.

### FR-13 — File Upload for Leave Documents
*Source: SPEC.* An employee uploads a supporting document with a leave request where the leave type requires one.
**Acceptance:** The document is associated with the request and retrievable by those authorized to view that request. File type and size are validated on upload.

### FR-16 — Audit Logs for Leave Actions
*Source: SPEC, ENG.* Every leave state transition is recorded.
**Acceptance:** An audit entry captures the request, the transition, the acting user, and the timestamp. Entries are append-only and are not modified or deleted by application logic.

---

## Reporting and Interface

### FR-11 — Dashboard Analytics
*Source: SPEC.* Each role sees a dashboard appropriate to its permissions.
**Open — scope undefined.** "Dashboard analytics" spans anything from summary cards to charts with date-range filtering. Not testable as written; the assigning manager must define it.

### FR-18 — Department Leave Calendar
*Source: SPEC, ENG.* A Manager views a calendar of leave across their team, so that coverage is visible before a decision is taken.
**Acceptance:** The calendar shows approved and pending leave for the Manager's own direct reports, scoped per FR-03. It is informational: BR-06 places no restriction on concurrent leave, so the calendar informs a decision but never blocks one.

### FR-12 — Search, Filtering, and Pagination
*Source: SPEC.* Collection endpoints support search, filtering, and pagination.
**Acceptance:** Results are paginated with a bounded page size. Filters compose. Results respect the caller's authorization scope — a Manager filtering leave requests sees only those of their direct reports.

### FR-14 — Email or In-App Notifications
*Source: SPEC.* Users are notified of events relevant to them: a submitted request reaching its manager, a decision reaching the employee.
**Open — scope undefined.** The specification permits either email or in-app delivery. The choice carries materially different infrastructure cost and must be settled by the assigning manager.

### FR-15 — Reports and Export
*Source: SPEC.* Managers export team leave reports; Admins export organization-wide leave reports.
**Acceptance:** Export content respects the caller's authorization scope.
**Open:** Whether CSV suffices or PDF is required. PDF generation is materially more work.

---

## Traceability — Role to Requirement

*Corrected 2026-07-10 to reflect confirmed project decisions. See `../prds/prd-LeaveFlow-2026-07-09/prd.md` and its `.memlog.md` for the decisions and their reasoning.*

| Role | Requirements |
| --- | --- |
| **Admin** | FR-04, FR-05, FR-06, FR-10, FR-11, FR-15, read-only visibility of FR-08, decision authority over Cancellation Requests under FR-09, and sole full read access to the audit log under FR-16 |
| **Manager** | FR-09, FR-11, FR-12, FR-14, FR-15, FR-18, FR-19, read access to their direct reports under FR-03, and read access to a direct report's history under FR-20 |
| **Employee** | FR-07, FR-08, FR-13, FR-14, FR-17, FR-20, cancellation of pending requests under FR-09, and raising a Cancellation Request against approved leave under FR-09 |
| **All roles** | FR-01, FR-02, FR-03, FR-11, FR-12, FR-17 |
| **System** | FR-16, auto-approval of a managerless Employee's request under FR-09, and the scheduled Leave Year rollover under FR-07 |

**What changed, and why**

1. **FR-11 moved to All roles.** This matrix previously assigned FR-11 to Admin and Manager only, contradicting FR-11's own prose in this document ("each role"). Confirmed: all three roles receive a role-specific dashboard — Employee sees personal leave information, Manager sees team and department information within authorization scope, Admin sees organization-wide information. Dashboards are summary cards with date-range filtering.
2. **FR-19 and FR-20 added.** The specification grants the Manager "view team members" and the Employee "view leave history". Neither was enumerated in this document's requirement list, so neither had a requirement to cover it. Both are now required capabilities, specified in the PRD as FR-19 and FR-20.
3. **FR-09's actor set widened.** D-07 (approved leave cannot be cancelled) has been **reversed**. An Employee raises a Cancellation Request against their own approved leave; an Admin decides it. BR-05 is now a reachable rule. Leave whose dates have already passed cannot be cancelled.
4. **The System is an actor.** A managerless Employee's request is auto-approved, and the audit entry records the actor SYSTEM with reason AUTO_APPROVED_NO_MANAGER. The Leave Year rollover is a scheduled system process.

## Requirements Not Fully Implementable As Written

*Superseded 2026-07-10. Every requirement below is now testable.*

FR-11 and FR-14 formerly had no acceptance criteria because their scope was undefined. Both are now specified: FR-11 delivers per-role summary cards with date-range filtering; FR-14 delivers in-app notifications, with email deferred and the trade-off recorded in the PRD.

FR-09's cancellation contradiction was originally closed by decision D-07, which narrowed scope to the permissions the specification actually granted rather than inventing one. **D-07 has since been reversed by project decision:** the authority to cancel approved leave was granted explicitly, via a Cancellation Request that an Admin decides. Narrowing scope was the correct move on the information then available — the contradiction was resolved by asking rather than guessing, and the answer arrived from the only authority who could give it.
