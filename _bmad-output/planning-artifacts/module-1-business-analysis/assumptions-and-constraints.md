---
title: "LeaveFlow — Assumptions and Constraints"
module: "1 — Understanding the Problem"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Assumptions and Constraints

A **constraint** is a boundary imposed from outside. It is not negotiable and not a decision.

An **engineering decision** is a position the engineer chose and must defend. It could have been decided otherwise.

An **assumption** is something taken as true without confirmation. It may be wrong, and it is recorded so that it can be corrected rather than discovered.

An **open question** is something explicitly *not* assumed, because assuming it would be unsafe. Open questions are listed separately at the end and are never filed as assumptions.

These four are separated deliberately, because conflating them is how a team comes to believe it chose something it was merely handed — or handed off something it in fact chose.

---

## Constraints

### Imposed by the assigning manager

| Constraint | Detail |
| --- | --- |
| **Time budget** | Seven days, per the learning path's day-by-day plan. |
| **Process** | The BMAD lifecycle must be followed and its artifacts produced. Days 3–5 are the only days allocated to application code. |
| **Technology options** | A bounded set of technology options was offered. The selection within that set was the engineer's — see D-05 and D-06. |

### Imposed by the specification

| Constraint | Detail |
| --- | --- |
| **Roles** | Exactly three: Admin, Manager, Employee. No role may be added. |
| **Scope** | The eighteen functional requirements — sixteen enumerated in the specification's requirements list, and two (FR-17, FR-18) drawn from permissions the specification grants in its role definitions. Features not named in the specification are out of scope. |
| **Authorization model** | Manager authority extends only to direct reports. |
| **Policy ownership** | The Admin manages and configures leave types and leave policies. |
| **Delivery form** | A web-based application. |

---

## Confirmed Business Rules

Clarifications received and confirmed during requirement analysis. These are confirmed rules, not assumptions. Where a confirmed rule has an unresolved gap, that gap is flagged in Open Questions — see BR-05.

| # | Rule |
| --- | --- |
| BR-01 | Three leave types exist: EL (Earned Leave), CL (Casual Leave), FL. |
| BR-02 | An employee joining mid-year receives a prorated leave balance. |
| BR-03 | At year end, EL carries forward. CL and FL lapse. |
| BR-04 | Leave spanning two calendar years may not be one application. The employee submits one application per calendar year. |
| BR-05 | Cancelling approved leave restores the deducted balance. *(Retained as a policy clarification only. No role is authorized to cancel approved leave, so this rule is **not reachable** under the defined permissions — see D-07. It is documented because it will matter if the permission is ever granted.)* |
| BR-06 | No restriction applies when multiple employees from the same team request the same dates. |

---

## Engineering Decisions

Positions the engineer chose. Each is defensible, and each could have gone another way.

| # | Decision | Rationale |
| --- | --- | --- |
| D-01 | **Balance is deducted on approval; pending requests reserve days.** | Prevents several pending requests from collectively exceeding entitlement. Implies three quantities — accrued, reserved, consumed. |
| D-02 | **Only working days are deducted.** Weekends and company holidays are excluded. | Makes holiday management an input to the day-count rather than an isolated screen. |
| D-03 | **Authorization is data-scoped, not role-checked.** | The specification scopes a Manager to *direct reports*. Establishing the role is insufficient; the reporting relationship must be established. |
| D-04 | **Leave policy is configuration, not code.** | The specification requires the Admin to configure leave types and policies. Carry-forward and lapse behaviour therefore become data; adding a leave type requires no code change. |
| D-05 | **FastAPI for the backend.** Selected from the options offered. | Python framework with typed request and response models, automatic OpenAPI generation, and first-class validation — which serves the learning path's API-documentation deliverable directly. |
| D-06 | **React for the frontend.** Selected from the options offered. | Existing familiarity, which conserves scarce days for the parts of the project that carry the engineering risk. |
| D-07 | **Cancellation of approved leave is out of scope.** Employees may cancel pending requests only. No approved-cancellation transition is implemented. | Resolves the requirements contradiction by following the specification rather than inventing a permission it grants to nobody. BR-05 survives as documented policy that is not reachable under the defined permissions. |

D-05 and D-06 are the engineer's selections from a set the assigning manager offered. They are decisions to defend, not constraints to cite.

---

## Assumptions

Each will be either confirmed or corrected. The consequence column states what breaks if the assumption is wrong. All route to the assigning manager.

| # | Assumption | Consequence if wrong |
| --- | --- | --- |
| A-01 | **Half-day leave is out of scope.** It appears in no source. | Balances become decimal rather than integer; the day-count function returns fractions; schema change. |
| A-02 | **Saturday and Sunday are the weekend** for all employees. | Alternate-Saturday working patterns miscount every leave request. |
| A-03 | **Company holidays are global**, not scoped by office location or department. | Multi-location holiday calendars become unrepresentable; balances differ by office. *(The single-calendar claim is also implied by A-08; this row is its home.)* |
| A-04 | **FL's expanded name is unconfirmed.** Its lapse behaviour is already confirmed by BR-01 and BR-03; only the label is uncertain. | Nothing structural. |
| A-05 | **Leave accrues in some form**, since BR-02 confirms proration. **Whether monthly or as an annual grant is unstated.** | Proration is computed against the wrong entitlement model. |
| A-06 | **A single approval step suffices.** No escalation, delegation, or second approver is implied by the specification. | The request state machine is missing states. |
| A-07 | **The organization is single-tenant** — one policy set, one hierarchy, one holiday calendar (see A-03). | Nothing in the data model is scoped to an organization. |
| A-08 | **Leave policy will not in practice be changed mid-year.** The specification permits the Admin to reconfigure policy, and says nothing about balances already accrued under a prior policy. | Reconfiguring a leave type silently invalidates existing balances. |
| A-09 | **The leave year is the calendar year, 1 January to 31 December.** No source defines it; a calendar year is consistent with BR-04's reference to leave "spanning two calendar years." | The balance table is keyed wrongly. Carry-forward and proration fire at the wrong boundary. Every balance in the system is affected. |

A-09 carries the highest consequence in this register. It is a deliberate assumption rather than an open question, taken so that the data model can be keyed and work can proceed; it should still be confirmed with the assigning manager at the first opportunity, because correcting it later means rebuilding every balance.

This register was renumbered during editorial review. The FL and accrual entries previously asserted content that BR-01, BR-03, and BR-02 already confirm; both have been narrowed to the genuine uncertainty. Identifiers A-01 through A-09 above are the current set; any earlier reference to A-10 is obsolete.

---

## Open Questions

Explicitly not assumed. Held in full in the brief's `addendum.md`. All route to the assigning manager, except where noted as a design decision to be taken later.

**Nothing now blocks the data model.** The two former blockers are closed: the cancellation contradiction by decision D-07, and the leave-year boundary by assumption A-09. Neither was resolved by guessing — the first follows the specification, the second is recorded as an assumption with its consequence stated.

**Deferred to design rather than to the assigning manager.**

**Recalculation after a late-declared holiday.** If a holiday is declared after leave has been approved, is the approved request recalculated? Not recalculating is the defensible position, and it remains a proposal rather than an adopted one.

**Outstanding, shaping the work without blocking the schema.** The scope of dashboard analytics (FR-11); the notification delivery mechanism (FR-14); the export format (FR-15); the expanded name of FL (A-04); whether carried-forward EL is capped or expires; the proration method and its rounding (A-05); and confirmation of A-09, the leave-year boundary.
