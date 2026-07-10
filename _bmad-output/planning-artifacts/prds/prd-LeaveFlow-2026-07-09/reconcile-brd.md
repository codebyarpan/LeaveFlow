---
title: "LeaveFlow — PRD ⇄ Module 1 Reconciliation"
status: report-only
created: 2026-07-09
note: "Report only. No fixes, no new requirements, no resolved open questions."
---

# Reconciliation: Module 1 Business Analysis → PRD

Compares three SOURCE inputs (brd.md, problem-statement.md, stakeholder-analysis.md — plus the Module 1 functional-requirements.md they reference) against the DERIVED prd.md and addendum.md. Reports only what the PRD dropped, distorted, or contradicted. Nothing here is fixed.

A fourth Module 1 file, `functional-requirements.md`, was read because it holds the role-to-requirement traceability matrix that §6 below turns on; the BRD delegates the 18 FRs and their matrix to it.

---

## 1. Business Objectives (BRD §3)

BRD §3 states five business objectives. Every one has a PRD home; none is orphaned.

| # | BRD Objective | Carried by PRD? | Where |
| --- | --- | --- | --- |
| 1 | **Leave balances are correct** (proration, carry-forward, leave-year boundary) | Yes — but see caveat | §1 Vision ("a balance that holds across proration, carry-forward, and the year boundary"); FR-07; DR-3, DR-7, DR-9; SM-1, SM-2 |
| 2 | **Leave requests have an explicit lifecycle** (submitted, decided, cancelled) with the balance effect of every transition specified | Yes | §4.5 (state-machine table); FR-08, FR-09; DR-4 |
| 3 | **Approval authority is enforced** (a manager acts on own direct reports only) | Yes | FR-03; DR-12; SM-3; §4.1 |
| 4 | **Leave policy is configurable by the Admin** (change without code) | Yes | FR-06; DR-11; NFR-14; SM-5 |
| 5 | **Every leave action is attributable** to an actor and a time | Yes | §1 Vision ("Every state change is attributable to an actor and a moment"); FR-16; DR-16; SM-4 |

**Caveat on Objective 1.** The PRD carries the *statement* of the correctness objective but simultaneously declares it unbuildable as written. FR-07's `[NOTE FOR PM]` says "**This requirement cannot be implemented as written**" because no source states how many Leave Days a Leave Type grants, so "there is nothing to prorate and nothing to carry forward." The objective is not dropped, but the PRD honestly records that it cannot presently be met — a fact the BRD's confident §3/§8 phrasing does not surface (see §7 Contradictions, item A).

No objective is without a PRD home.

---

## 2. Out-of-Scope List (BRD §4, "authoritative") vs PRD §6 Non-Goals

BRD §4 declares itself authoritative and splits exclusions into **settled** and **on current assumptions (pending the assigning manager)**. PRD §6 is a flat "will not, in v1" list. Item-by-item:

### 2a. BRD §4 items → PRD §6

| BRD §4 exclusion | Tier | In PRD §6? |
| --- | --- | --- |
| Payroll integration | settled | Yes ("Integrate with payroll or produce a loss-of-pay figure") |
| Attendance / time tracking | settled | Yes ("Track attendance or working time") |
| Any role beyond Admin/Manager/Employee | settled | Yes ("Support any role beyond Employee, Manager, and Admin") |
| **Any feature not named in the specification** | settled | **No explicit equivalent** — the blanket catch-all is not restated as a Non-Goal |
| **Cancellation of approved leave (D-07)** | settled | **Not in §6** — appears instead in §7.4 and DR-14 |
| Half-day leave (A-01) | assumption | Yes ("No half-days, no hourly leave") |
| Alternate-Saturday working patterns (A-02) | assumption | Yes ("vary … the weekend by Employee") |
| Location-specific holiday calendars (A-03) | assumption | Yes ("Vary the holiday calendar by location or Department") |
| Approval workflows beyond a single manager step (A-06) | assumption | Yes ("no delegated approver, no second approver, no escalation") |
| Multi-organization tenancy (A-07) | assumption | Yes ("Model more than one organization … Single-tenant") |

**BRD-excluded but missing from PRD §6:**
- **"Any feature not named in the specification"** — the BRD's blanket exclusion is not carried into §6 as a Non-Goal. (It is honored in spirit elsewhere: §7 says all 18 FRs appear and none is added, and addendum §1.5 rejects encashment as "inventing scope." But the authoritative catch-all itself is dropped from the Non-Goals list.)
- **Approved-leave cancellation** — present in the PRD (§7.4, DR-14, FR-09 note) but absent from §6 specifically, the section the task pins as the comparison target.

**Structural flattening.** BRD §4's two-tier distinction — exclusions *settled by the specification* vs exclusions *resting on unconfirmed assumptions, pending the assigning manager* — is collapsed in §6. A-01/A-02/A-03/A-06/A-07 read in §6 as unconditional "will not" Non-Goals; their provisional "could be reversed by the assigning manager" character survives only via inline `[ASSUMPTION]` tags and the §12 index, not in §6's framing.

### 2b. PRD §6 items the BRD does NOT exclude

- **"Encash leave."** New exclusion. Not in BRD §4. (Subject of PRD Open Question 2; raised because research surfaced a legal exposure — addendum §1.5, §2.2.)
- **"Support unpaid leave or leave beyond an exhausted balance."** New exclusion. Not in BRD §4.
- **"Send email."** New. The specification (per FR-14) permits "email or in-app," so this is a scope *choice*, not a BRD exclusion; the PRD elevates it to a Non-Goal.
- **"Achieve high availability, horizontal scalability, internationalization, or formal WCAG conformance."** New. Sourced from the Module 1 NFR set, not BRD §4.

None of these contradicts the BRD (they are narrower, and most fall under the BRD's own "any feature not named in the specification" umbrella), but they are exclusions the PRD introduces that the authoritative list does not name.

---

## 3. Stakeholder Conflicts (stakeholder-analysis.md §Conflicts and Tensions)

The stakeholder doc names three conflicts. The PRD addresses all three; none is silently dropped.

| Conflict | PRD treatment | Where |
| --- | --- | --- |
| **Employee vs Manager on visibility** — no rule restricts overlapping team leave, yet the manager needs the calendar to see the consequence; "the system informs; it does not block" | **Addressed** — reproduced almost verbatim | §4.6 description; FR-18 ("never prevents an approval … no warning, no block"); DR-15 ("The system informs; it never blocks"); UJ-2; addendum §2.4 |
| **Assigning manager vs system** — sponsor values traceable reasoning over exhaustive feature coverage | **Addressed** | §9 Guardrail ("Where feature breadth and demonstrable correctness compete, correctness wins"); §0; SM-C1, SM-C3; §10 preamble |
| **Admin authority vs policy stability** — Admin can reconfigure a Leave Type mid-year, affecting already-accrued balances; spec silent; recorded as A-08 | **Acknowledged, not resolved** (faithful to source, which also left it at A-08) | FR-06 note (`[ASSUMPTION: A-08]`); Open Question 5; §12 |

---

## 4. System Users vs Project Stakeholders; the invented personas

**The distinction is preserved.** The stakeholder doc separates *System Users* (Employee, Manager, Admin) from *Project Stakeholders Who Are Not System Users* (assigning manager, trainee engineer). The PRD holds this: §2 Target User is the three roles only; addendum §4 states plainly "The real project stakeholders are the assigning manager … and the trainee engineer … Neither is a system user." §0 separately frames the assigning manager as the evaluator/reader, not a user.

Minor location note: the explicit user-vs-stakeholder statement lives in addendum §4 (and §2.3), not in the main PRD body; the two-column Module 1 table is referenced rather than reproduced. Distinction intact, just relocated.

**The personas (Rahul, Meera, Anil) — the line holds.** PRD §2.3 declares them "illustrative fictions used to force specificity … **not** stakeholders, roles, or requirements, and nothing in §4 depends on their existence." Addendum §4 reiterates. Verification:
- The persona names appear **only** in the UJ-1/UJ-2/UJ-3 narrative prose (§2.3). They do not appear in any FR, DR, NFR, SM, glossary entry, or §4 feature description.
- Every functional requirement is written against role names ("An **Employee** can…", "The **Manager** of a **Leave Request**'s applicant…"), never against a persona.
- FRs link to journeys via `Realizes UJ-n` / `Realizes FR-nn`, i.e. to the abstract journey, not the fictional person.

No requirement depends on the personas. The PRD's self-description is accurate and consistently upheld.

---

## 5. Problem Statement core claims vs PRD §1 Vision

All core claims are preserved. One subtle provenance distortion.

**Four failures of spreadsheet/email leave admin.** Preserved faithfully, in the same order.

> problem-statement.md §1: "**Balances cannot be trusted.** … **Requests have no state.** … **Approval authority is unenforced.** … **Decisions leave no trail.**"

> prd.md §1: "Balances cannot be trusted, because proration and carry-forward are computed by hand … Requests have no state — a request is an email … Approval authority is unenforced, because nothing prevents the wrong manager from replying 'approved.' And decisions leave no trail…"

**"Correctness matters more than breadth."** Preserved.
> problem-statement.md §3 (marked *the engineer's judgement*): "correctness matters more than breadth."
> prd.md §1: "The product's ambition is narrow and its correctness bar is high." (§9 restates: "correctness wins.")

**"A leave balance that is wrong is worse than one that is absent."** Preserved verbatim, with attribution.
> problem-statement.md §3: "A leave balance that is wrong is worse than a leave balance that is absent, because it will be believed."
> prd.md §1: "The guiding judgment, carried forward from the problem statement: **a leave balance that is wrong is worse than a leave balance that is absent, because it will be believed.**"

**Distortion (subtle, provenance).** The problem statement wraps its §1 four-failures in an explicit provenance caveat: they are "**engineer-authored context** — a reasoned account of why such a system exists, **not a business problem supplied by any source**." The PRD §1 Vision presents the same four failures as established fact, dropping the "engineer-authored / not supplied by any source" disclaimer. The "engineer's judgement" tag *is* preserved for the wrong-balance line ("carried forward from the problem statement"), but the failures themselves lose their "not a sourced problem" hedge and read as asserted truth.

---

## 6. Role-to-Requirement Traceability

Module 1's authoritative matrix lives in `functional-requirements.md` §Traceability:

| Role | Module 1 Requirements |
| --- | --- |
| Admin | FR-04, FR-05, FR-06, FR-10, **FR-11**, FR-15, read-only FR-08 |
| Manager | FR-09, **FR-11**, FR-12, FR-14, FR-15, FR-18, read access under FR-03 |
| Employee | FR-07, FR-08, FR-13, FR-14, FR-17, cancel-pending under FR-09 |
| All roles | FR-01, FR-02, FR-03, FR-12, FR-17 |
| System | FR-16 |

Checking each FR's actor in the PRD against this matrix, only one actor changed:

**FR-11 — actor CHANGED. The PRD adds the Employee; Module 1's matrix does not.**
- Module 1's traceability matrix assigns **FR-11 to Admin and Manager only**. The Employee is absent from FR-11; the Employee's balance view is carried by FR-07, a separate row.
- The PRD's FR-11 states "**Each role** sees a dashboard" and specifies an explicit **Employee dashboard** ("presents, per **Leave Type**: **Available**, **Reserved**, and **Consumed**; plus a count of **Pending** requests"), and §7.2 schedules it. So the PRD gives the Employee a dashboard under FR-11 that Module 1's matrix does not grant.
- Nuance worth recording: Module 1's own FR-11 *prose* says "Each role sees a dashboard appropriate to its permissions," which conflicts with its *own* matrix (Admin+Manager only). The PRD sided with the prose reading and made an Employee dashboard concrete. Net effect against the authoritative matrix: **the actor set for FR-11 is widened to include the Employee.** This also partially duplicates FR-07 (the Employee-balance figures now appear on both FR-07 and the FR-11 Employee dashboard).

Every other FR's actor is consistent with the Module 1 matrix:
- FR-03 Admin "may view all leave requests but is not granted approval authority" — PRD FR-03/DR-13 identical (Admin reads all, decides none). No change.
- FR-09 Manager approves/rejects, Employee cancels pending — PRD identical. No change.
- FR-14 → Manager + Employee in the matrix; PRD notifies Manager on submission and applicant on decision. Consistent.
- FR-15 → Admin + Manager; PRD Manager (direct reports) + Admin (org-wide). Consistent.
- FR-16 → System; PRD "The system records…". Consistent.
- FR-04/05/06/10 → Admin; FR-07/08/13/17 → Employee; FR-18 → Manager; FR-12 → Manager/all. All consistent.

---

## 7. Contradictions

**A. "Nothing blocks downstream work" (BRD §9) vs the PRD's blocking Open Questions.**
BRD §9 opens: "**Nothing blocks downstream work.** The two former blockers are closed, neither by guessing." It closes the leave year "by assumption" (A-09) and lists "proration rounding" among "Remaining questions [that] shape the work **without blocking** the schema." The PRD reverses this posture on two of those very items:
- PRD Open Question 3 (leave-type granted quantity + proration method) is declared "**the blocking question for implementation**" and "the blocking question, more than Question 1," and FR-07 says the requirement "**cannot be implemented as written**."
- PRD §11 requires Questions 1–3 to "be put to the assigning manager **before Day 3**."
The BRD says nothing blocks; the PRD says two things block implementation. (Partly reconcilable — the BRD scopes "block" to the schema/downstream modeling, the PRD to Day-3 implementation — but the plain reading of BRD §9's "Nothing blocks" and its demotion of proration rounding to a non-blocking "remaining question" is directly contradicted by the PRD's escalation of the same gap to blocking.)

**B. A-05 withdrawn — Module 1 register vs PRD.**
The Module 1 assumptions register (per FR-06 "Open: … the accrual method" and BRD provenance) carried A-05: entitlement "accrues in some form." The PRD §12 **withdraws A-05** ("has been withdrawn," "identifier is retired") and reclassifies its content as blocking Open Question 3. This is a deliberate, documented divergence from Module 1's register rather than a silent drop — but it is a change to the Module 1 assumption set the BRD still references, and Module 1's own numbering now contains a retired identifier the PRD unilaterally retired.

**C. "Requirements are covered" (BRD §8 success) vs FR-11 admitted under-delivery.**
BRD §8 defines success as "The requirements are covered," and §4 places all eighteen FRs in scope. The PRD FR-11 note concedes it "**is delivered at reduced scope, and the reduction is not authorized by the specification**" — summary cards instead of the specified "dashboard analytics" — and §7.4/Open Question 4 label it "a scope reduction against the specification." So the PRD knowingly delivers less than the BRD's coverage-success criterion for FR-11. (The PRD is transparent about this and routes it to the assigning manager; it is a contradiction with the BRD's success definition, surfaced rather than hidden.)

**D. FL expansion — BRD keeps it unconfirmed; PRD glossary states it.**
BRD BR-01/glossary carry FL with its "expanded name … unconfirmed (A-04)." The PRD **glossary** presents "**FL** (Floater Leave)" as a defined term used verbatim throughout, and DR-7 names "Floater Leave." The PRD does tag A-04 at FR-06 and notes "Only display text changes if this is wrong," so this is a soft distortion, not a hard contradiction: an unconfirmed name is elevated to glossary-canonical vocabulary while the underlying assumption remains open.

**No contradiction found** on: the three roles and their fixity; Available = Accrued − Consumed − Reserved; the four-state lifecycle and reserve/consume/release effects; deduct-on-approval (D-01); working-days-only day count (D-02); manager-scoped authorization (D-03); BR-04 (no request spanning two leave years); BR-05/D-07 handling (approved-leave cancellation unreachable, rule preserved not deleted); BR-06 (overlap permitted, informs-not-blocks); the leave-year = calendar-year assumption (A-09) and its flagged fragility.

---

## Summary of the most consequential findings

1. **FR-11 actor widened (Q6).** The PRD gives the **Employee** a dashboard under FR-11; Module 1's authoritative role-to-requirement matrix assigns FR-11 to **Admin and Manager only**. (Module 1's own FR-11 prose says "each role," conflicting with its own matrix.)
2. **BRD §9 "Nothing blocks downstream work" is contradicted (Q7-A)** by the PRD's blocking Open Questions 1 and 3 (leave year; leave-type granted quantity / proration), the latter making FR-07 "cannot be implemented as written."
3. **Two BRD §4 exclusions are missing from PRD §6 (Q2):** the blanket "any feature not named in the specification," and "cancellation of approved leave" (relocated to §7.4). The PRD §6 also **adds** exclusions the BRD does not name (encashment, unpaid/over-balance leave, email, HA/scalability/i18n/WCAG), and flattens BRD §4's settled-vs-assumption tiering.
4. **Provenance distortion (Q5):** the problem statement's four failures are explicitly "engineer-authored context, not a business problem supplied by any source"; PRD §1 presents them as established fact, dropping that hedge. The core quotes themselves are preserved faithfully.
5. **BRD §8 "requirements are covered" vs FR-11's admitted, unauthorized scope reduction (Q7-C).**

All five business objectives (Q1) have PRD homes; all three stakeholder conflicts (Q3) are addressed; the system-user/project-stakeholder distinction and the "personas are fictions" line (Q4) hold consistently.
