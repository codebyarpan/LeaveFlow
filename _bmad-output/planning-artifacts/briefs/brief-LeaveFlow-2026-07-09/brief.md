---
title: "Product Brief: LeaveFlow"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Product Brief: LeaveFlow

## Executive Summary

LeaveFlow is a web-based Employee Leave Management System that lets employees apply for leave, managers review and decide on those requests, and administrators manage employees, departments, leave policies, and company holidays. Access is governed by role-based access control, with a distinct dashboard and permission set for each role.

It is a company-assigned trainee project, and the system is the vehicle rather than the destination. The assignment's stated objective is to learn the complete AI-first software engineering lifecycle using BMAD — "to transform a business idea into production-ready software using AI agents rather than using AI only as a code generator." Its seven-day plan devotes only Days 3 through 5 to application code. Days 1, 2, 6, and 7 produce artifacts: a BRD, a PRD, an ERD, architecture and flow diagrams, API contracts, a test plan, a code review report, a prompt library, a retrospective.

This shapes how the project is judged. Nothing in the learning path rewards shipping all eighteen functional requirements, so coverage is treated here as a floor to reach, not the measure of success. The measure of success is a coherent system whose every stage is documented and defensible. The evaluation mode remains unknown — it may be a checklist review, a technical discussion, or both — and under that uncertainty the strategy is to cover the explicitly given requirements while keeping the implementation clean enough to explain and defend. That hedge is sound either way, but it deliberately re-weights the work: process artifacts and engineering reasoning take precedence over feature count wherever the two compete for time.

## Confirmed Requirements

Taken from the original assignment specification. These are fixed and non-negotiable.

**Roles.** Exactly three: Admin, Manager, Employee. No others.

- **Admin** — manage employees and managers; manage departments; configure leave types and leave policies; manage company holidays; view organization-wide leave reports; view all leave requests.
- **Manager** — view team members; review leave requests from direct reports; approve or reject requests; view the department leave calendar; view team leave reports.
- **Employee** — log in securely; view leave balance; apply for leave; upload supporting documents when required; view leave history; cancel pending leave requests; update personal profile.

**Functional requirements.** User authentication; JWT-based authorization; role-based access control; employee management; department management; leave type management; leave balance tracking; leave request workflow; approval and rejection process; holiday management; dashboard analytics; search, filtering, and pagination; file upload for leave documents; email or in-app notifications; reports and export to CSV or PDF; audit logs for leave actions.

## Confirmed Business Rules

Established by clarification during requirement analysis. Settled, and not assumptions.

- There are three leave types: **EL** (Earned Leave), **CL** (Casual Leave), and **FL**.
- An employee joining mid-year receives a **prorated** leave balance.
- At year end, **EL carries forward**. **CL and FL lapse.**
- Leave spanning two calendar years may **not** be submitted as a single application. The employee submits two separate applications, one per year.
- Cancelling approved leave **restores** the deducted balance.
- **No restriction** applies when multiple employees from the same team request the same dates.

## Engineering Decisions

Decisions the engineer made, not dictated by the specification or by any confirmed rule. Each is a defensible position rather than a discovered fact, and each could have gone another way.

**Technology.** **FastAPI** for the backend and **React** for the frontend, selected by the engineer from the options the assigning manager offered. FastAPI provides typed request and response models and automatic OpenAPI generation, which serves the learning path's API-documentation deliverable directly. React is chosen on existing familiarity, conserving scarce days for the parts of the project carrying real engineering risk.

**Balance deduction timing.** Leave balance is deducted on **approval**. Pending requests **reserve** their requested days against the available balance, so that several pending requests cannot together exceed an employee's entitlement. A balance is therefore not one number but three — accrued, reserved, consumed — with available leave equal to `accrued − consumed − reserved`. The model is developed in `addendum.md`.

**Leave-day calculation.** Only **working days** are deducted. Weekends and company holidays are excluded. A request spanning Friday to Tuesday, where Saturday and Sunday are weekend days and Monday is a company holiday, deducts **two** days. This makes holiday management an input to the leave-day calculation rather than an isolated administrative screen, and it is the reason the holiday-management requirement exists.

**Authorization is data-scoped, not role-checked.** Manager permissions are scoped to *direct reports*. Establishing that a user is a manager is insufficient; the system must establish that these specific employees report to this specific manager.

**Cancellation of approved leave is out of scope.** The confirmed rules restore the balance when approved leave is cancelled, yet the specification authorizes no role to cancel it. Rather than invent a permission, the scope follows the specification: Employees may cancel pending requests only, and no approved-cancellation transition is implemented. The restore rule remains documented, unreachable.

## Documented Assumptions

Positions taken in the absence of guidance, recorded so they can be corrected rather than discovered.

- **Half-day leave is out of scope.** It appears in neither the specification nor the confirmed business rules. Should it later come into scope, leave balances become fractional and must be modelled as decimals rather than integers.
- **Saturday and Sunday are the weekend** and are excluded from leave-day calculations. A simplification: alternate-Saturday working patterns are not modelled.
- **Company holidays are global**, not scoped by office location or department. A simplification.
- **The leave year is the calendar year**, 1 January to 31 December. No source defines it; a calendar year is consistent with the confirmed rule about leave spanning "two calendar years." This is the highest-consequence assumption here — every balance in the system is partitioned by it — and it should be confirmed at the first opportunity.

## Open Questions

Questions to be asked, not guessed at. All route to the assigning manager. The full list is in `addendum.md`.

**Nothing blocks the data model.** The contradiction over who may cancel approved leave was closed by narrowing scope to what the specification authorizes, and the leave-year boundary by a documented assumption. Neither was resolved by guessing.

Outstanding: the expanded name of **FL**; whether carried-forward EL is capped or expires; the proration method and its rounding; and the intended scope of requirements stated so broadly that their real scope is undefined — "dashboard analytics" and "email or in-app notifications" among them.

## Scope

In scope: the three roles and their stated permissions, the eighteen functional requirements as a coverage floor, the confirmed business rules, and the engineering decisions above.

Out of scope: cancellation of approved leave; half-day leave; location-specific or department-specific holiday calendars; alternate-Saturday working patterns; any role beyond Admin, Manager, and Employee; any feature not named in the specification. The authoritative list, distinguishing settled exclusions from those resting on assumptions, is in `../../module-1-business-analysis/brd.md` §4.

## Success Criteria

The requirements are covered, and every lifecycle stage has produced its artifact — such that any decision in the codebase can be traced to a document, and any decision in a document can be defended aloud.

The system is correct where correctness is hard: balances hold across proration, carry-forward, and year boundaries; the day count excludes weekends and holidays; authorization scopes managers to their own direct reports; and every leave action leaves an audit trail.

Assumptions and open questions are visible rather than buried. A reader who disagrees with a decision can find where it was made and on what basis.
