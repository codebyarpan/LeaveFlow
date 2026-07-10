---
title: "LeaveFlow — Business Requirement Document"
module: "1 — Understanding the Problem"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Business Requirement Document

This document states what the business needs and why. It does not restate the detail held in its companions; it references them, so that each fact has one home.

| Companion | Holds |
| --- | --- |
| `problem-statement.md` | The problem, who feels it, and the scope boundary |
| `stakeholder-analysis.md` | Who has an interest, who holds authority, where interests conflict |
| `functional-requirements.md` | The eighteen requirements, with identifiers and, where testable, acceptance criteria |
| `non-functional-requirements.md` | Quality attributes — all engineer-proposed, none confirmed |
| `assumptions-and-constraints.md` | What is imposed, what was decided, what is assumed |
| `../briefs/brief-LeaveFlow-2026-07-09/addendum.md` | Domain model depth and the open-question list |

**Provenance vocabulary.** `SPEC` — the assignment specification. `RULE` — a confirmed business rule, established by clarification during requirement analysis. `ENG` — a decision the engineer made and must defend. `ASSUMPTION` — taken as true without confirmation. `OPEN` — unresolved.

---

## 1. Purpose

To specify the business need for LeaveFlow, a web-based Employee Leave Management System, in sufficient detail that product definition (Module 2) and system design (Module 3) can proceed without returning to first principles.

## 2. Background

Leave administration performed by spreadsheet, email, or paper fails predictably: balances are computed by hand and cannot be trusted, requests carry no state, approval authority goes unenforced, and decisions leave no trail. `problem-statement.md` develops this, and marks it as engineer-authored context rather than a problem supplied by any source.

This is a company-assigned trainee project. The system is the vehicle; the stated objective is to learn the complete AI-first software engineering lifecycle using BMAD, producing at each stage the artifacts professional delivery requires. Feature coverage is a floor, not the measure of success.

## 3. Business Objectives

1. **Leave balances are correct**, including across proration for mid-year joiners, carry-forward at year end, and the leave-year boundary.
2. **Leave requests have an explicit lifecycle** — submitted, decided, cancelled — with the balance effect of every defined transition specified.
3. **Approval authority is enforced**, not assumed. A manager acts on their own direct reports and no one else's.
4. **Leave policy is configurable by the Admin**, so that changing it does not mean changing code.
5. **Every leave action is attributable** to an actor and a time.

## 4. Scope

**In scope.** The three roles and their stated permissions. The eighteen functional requirements enumerated in `functional-requirements.md` — sixteen from the specification's requirements list, plus FR-17 (personal profile management) and FR-18 (department leave calendar), both drawn from permissions the specification grants in its role definitions. The confirmed business rules in §6. The engineering decisions recorded in `assumptions-and-constraints.md`.

**Out of scope, settled.** Payroll integration. Attendance and time tracking. Any role beyond Admin, Manager, and Employee. Any feature not named in the specification. Cancellation of approved leave (D-07).

**Out of scope on current assumptions**, pending the assigning manager (see `assumptions-and-constraints.md`): half-day leave (A-01), alternate-Saturday working patterns (A-02), location-specific holiday calendars (A-03), approval workflows beyond a single manager step (A-06), and multi-organization tenancy (A-07).

This document's out-of-scope list is authoritative. The companions cite it rather than restating it.

## 5. Roles

Exactly three, fixed by the specification and not extensible.

- **Admin** — manages employees, managers, and departments; manages and configures leave types, leave policies, and company holidays; views organization-wide reports and all leave requests.
- **Manager** — views team members; reviews, approves, and rejects requests from direct reports; views the department leave calendar and team reports.
- **Employee** — authenticates; views leave balance; applies for leave; uploads supporting documents where required; views leave history; cancels pending requests; updates their profile.

Two permissions the specification grants in its role definitions but omits from its requirements list — the Employee's profile update and the Manager's department leave calendar — are now specified as FR-17 and FR-18. They are specified capabilities, not invented ones.

## 6. Business Rules

Confirmed during requirement analysis. Settled, and not assumptions.

| # | Rule |
| --- | --- |
| BR-01 | Three leave types exist: EL (Earned Leave), CL (Casual Leave), FL. |
| BR-02 | An employee joining mid-year receives a prorated leave balance. |
| BR-03 | At year end, EL carries forward. CL and FL lapse. |
| BR-04 | Leave spanning two calendar years may not be one application. The employee submits one application per year. |
| BR-05 | Cancelling approved leave restores the deducted balance. *(Policy clarification only. Not reachable under the defined permissions — approved-leave cancellation is out of scope by D-07. See §9.)* |
| BR-06 | No restriction applies when multiple employees from the same team request the same dates. |

Two further rules govern the system but are **not** confirmed clarifications. They follow from engineering decisions, carry no BR identifier, and are cited by their decision identifiers so their origin is never mistaken: leave balance is deducted on approval while pending requests reserve their days (**D-01**), and only working days are deducted, weekends and company holidays excluded (**D-02**).

## 7. Constraints and Decisions

The distinction is load-bearing and is developed in `assumptions-and-constraints.md`.

**Constraints.** Seven days, of which only three are allocated to application code. The BMAD lifecycle and its artifacts are themselves a requirement. Three roles, eighteen requirements, manager authority scoped to direct reports, Admin ownership of leave policy configuration — all fixed by the specification. The assigning manager offered a bounded set of technology options.

**Decisions.** FastAPI (D-05) and React (D-06) were selected by the engineer from the options offered. They are choices to defend, not constraints to cite. So are deduct-on-approval (D-01), working-days-only (D-02), data-scoped authorization (D-03), policy-as-configuration (D-04), and the exclusion of approved-leave cancellation (D-07).

## 8. Success Criteria

The requirements are covered, and every lifecycle stage has produced its artifact — such that any decision in the codebase traces to a document, and any decision in a document can be defended aloud.

The system is correct where correctness is hard: balances hold across proration, carry-forward, and the leave-year boundary; the day-count excludes weekends and holidays; authorization scopes managers to their own direct reports; every leave action leaves an audit trail.

Assumptions and open questions are visible rather than buried. A reader who disagrees with a decision can find where it was made and on what basis.

## 9. Open Items

**Nothing blocks downstream work.** The two former blockers are closed, neither by guessing.

**The cancellation contradiction is closed by scope.** Cancelling approved leave restores the balance (BR-05), yet the specification authorizes no role to do it. Rather than invent a permission, decision **D-07** narrows scope: approved-leave cancellation is not supported, and Employees may cancel pending requests only. BR-05 remains documented as a policy clarification that is not reachable under the defined permissions.

**The leave year is closed by assumption.** **A-09** fixes it as the calendar year, 1 January to 31 December, consistent with BR-04's reference to leave spanning "two calendar years." This is the highest-consequence assumption in the register — every balance depends on it — and it should be confirmed with the assigning manager at the first opportunity.

Remaining questions shape the work without blocking the schema: the scope of dashboard analytics (FR-11), the notification delivery mechanism (FR-14), the export format (FR-15), the expanded name of FL, carry-forward caps, and proration rounding. All are listed in `addendum.md`.

## 10. Glossary

| Term | Meaning |
| --- | --- |
| **EL** | Earned Leave. Carries forward at year end (BR-03). |
| **CL** | Casual Leave. Lapses at year end (BR-03). |
| **FL** | A confirmed leave type that lapses at year end (BR-01, BR-03). Its expanded name is unconfirmed (A-04). |
| **Accrued** | Entitlement earned to date, after proration and carry-forward. |
| **Reserved** | Days committed to submitted but undecided requests. |
| **Consumed** | Days deducted by approved requests. |
| **Available** | `accrued − consumed − reserved`. The quantity against which a new request is checked. |
| **Leave year** | The period partitioning balances. Assumed to be the calendar year, 1 January to 31 December (A-09). |
| **Direct report** | An employee whose manager is a given user. The unit of a Manager's authority. |
| **Day-count** | The number of dates in a request that are neither weekend days nor company holidays. |
| **Working day** | A date that is neither a weekend day nor a company holiday. |
