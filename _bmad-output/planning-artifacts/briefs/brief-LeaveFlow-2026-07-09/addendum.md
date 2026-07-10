---
title: "LeaveFlow — Brief Addendum"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# LeaveFlow — Brief Addendum

Depth that belongs downstream rather than in the brief. The PRD (Module 2), architecture (Module 3), and ERD (Module 4) are the intended consumers.

Nothing here is a confirmed business rule unless it is marked as one. Proposals are labelled as proposals.

## Leave Types as Policy-Bearing Data

The confirmed rules describe EL carrying forward while CL and FL lapse, and the specification separately requires that supporting documents be uploaded "when required." Read together, these are not conditional branches to be scattered through a service layer. They are **attributes of a leave type**.

This suggests a leave type carries its own policy, expressed as configurable data rather than code. Two such attributes are grounded in confirmed sources:

- **Carries forward at year end** — grounded in the confirmed business rules (EL yes; CL and FL no).
- **Requires a supporting document** — grounded in the specification's "upload supporting documents when required."

Two further attributes are **proposals only**, and nobody has confirmed they exist. They are listed so the ERD author knows they were considered, not so that columns are created for them:

- A **cap** on carried-forward days. The confirmed rules establish that EL carries forward, without stating a limit. Uncapped carry-forward is unusual in practice. Open question.
- An **accrual method** (monthly accrual versus annual grant). Proration for mid-year joiners is confirmed, which implies *some* accrual model, but none was specified. Open question.

Two consequences worth carrying into the data model. Adding a fourth leave type should require no code change. And carry-forward should be expressed as configuration, so that "EL carries forward, CL and FL lapse" is data rather than an `if` statement. This is what the specification's requirement that the Admin manage and configure leave types and leave policies asks for.

## The Three-Quantity Balance Model

The engineer's decision to deduct on approval while reserving on pending means a single stored integer cannot represent a balance. At minimum, for each employee, leave type, and leave year:

- **Accrued** — entitlement earned to date, subject to proration for mid-year joiners and to carry-forward from the prior year.
- **Reserved** — days committed to requests that are submitted but not yet decided.
- **Consumed** — days deducted by approved requests.

Available leave is `accrued − consumed − reserved`.

**"Leave year" is load-bearing, and is fixed by assumption.** It is the partition key for every balance row, and both carry-forward and proration hinge on where its boundary falls. No source defines it. It is **assumed to be the calendar year, 1 January to 31 December** (A-09), consistent with the confirmed rule about leave "spanning two calendar years." The ERD may key the balance table on that basis. The assumption carries the highest consequence in the register — if wrong, every balance is wrong — and should be confirmed with the assigning manager at the first opportunity.

This raises a product question the specification does not answer. The Employee permission reads "view leave balance," singular. Which quantity does the employee see? Showing `accrued − consumed` overstates what they can request. Showing available understates what they hold if a pending request is later rejected. Most systems display available prominently and disclose the pending reservation alongside it. Proposal, not a decision.

## Leave Request State Machine

Proposed, and derived from the engineering decisions rather than from any source document. The specification names no states. It is set down explicitly because the balance transitions are meaningless without it, and because an ERD author would otherwise have to invent it.

| From | Event | To | Effect on balance |
| --- | --- | --- | --- |
| — | Employee submits request | **Pending** | Reserve the day-count |
| Pending | Manager approves | **Approved** | Release reservation; consume the day-count |
| Pending | Manager rejects | **Rejected** | Release reservation |
| Pending | Employee cancels | **Cancelled** | Release reservation |
| ~~Approved~~ | ~~Cancelled~~ | ~~Cancelled~~ | **Out of scope — do not implement** |

The struck-through row records the requirements contradiction and its resolution. The specification grants the cancel-approved permission to nobody: Employees may cancel only pending requests, Managers may only approve or reject, and Admins may only view. The confirmed restore-on-cancellation rule presumes a transition that no actor is authorized to trigger.

The scope now follows the specification rather than inventing a permission. **Approved leave cannot be cancelled.** `Approved` is a terminal state. The restore rule is retained as documented policy that is not reachable under the defined permissions, and it will matter only if the permission is ever granted. The question of *when* cancellation would be permitted — before the leave starts, once begun — falls away with it.

Each transition is an auditable event, and together they are the natural content of the "audit logs for leave actions" requirement. An audit entry should capture the request, the transition, the actor, and the timestamp.

## Leave-Day Calculation

The day-count for a request is the number of dates in the range that are neither weekend days nor company holidays. It is a pure function of the date range and the holiday table. It should live in one place, be unit-tested directly, and be called by every path that touches a balance.

Two second-order behaviours remain **undecided**, and this addendum deliberately leaves them so:

- If a holiday is declared *after* leave has been approved, is the approved request recalculated? Recalculation is the correct real-world behaviour but a poor use of a seven-day budget. Not recalculating is the defensible position, and it is a proposal rather than a decision. Open question, deferred to design.
- A request consisting entirely of weekend days and holidays would deduct zero days. Whether such a request is valid, or should be rejected at submission, is unaddressed by the specification.

## Cancellation Boundary — closed

This section previously proposed a rule for *when* approved leave might be cancelled. The question is moot: approved leave cannot be cancelled at all (D-07), so there is no boundary to draw. `Approved` is terminal.

Retained only as a note for whoever revisits the permission: were approved-cancellation ever granted, the boundary would need deciding — cancelling leave that has not begun is straightforward, leave already taken should not be cancellable, and leave in progress raises the question of a partial restore.

## Entities the ERD Must Cover

Each is implied by a confirmed requirement but has no shape defined anywhere yet. Listed so the ERD author does not have to rediscover them; their attributes are deliberately not invented here.

- **Holiday** — an input to the day-count function, not merely an administrative screen. Needs at minimum a date and a name. Assumed global (see the register below).
- **Supporting document** — required by the "file upload for leave documents" requirement and by the per-leave-type document flag. Its linkage to a leave request and its storage location are unmodelled.
- **Audit entry** — the sink for state machine transitions, per the "audit logs for leave actions" requirement.
- **Reporting relationship** — the employee-to-manager edge. Load-bearing, because the brief's data-scoped authorization decision and every manager-facing query depend on it. Whether it is an attribute of the employee or a relation in its own right is undecided.

## Simplifications Register

The single source of truth for these. The brief's Documented Assumptions section summarises them; this table is authoritative, and each row names the open question that would resolve it.

| Simplification | Consequence if wrong | Resolved by |
| --- | --- | --- |
| Half-day leave out of scope | Balances become decimal; the day-count returns fractions | Open question 7 |
| Saturday and Sunday are the weekend | Alternate-Saturday patterns miscount every request | Open question 8 |
| Company holidays are global | Multi-location holiday calendars unrepresentable | Open question 9 |

Note that late-declared-holiday recalculation is **not** listed here. It is an open question, not an adopted simplification.

## Open Questions

All route to the assigning manager, the sole external authority on this project. The two formerly blocking items are recorded first, as closed. The numbering of the shaping questions is referenced by the Simplifications Register above.

**Closed — neither by guessing.**

- **The cancellation contradiction** is closed by scope. Approved-leave cancellation is not supported (D-07); the scope follows the specification rather than inventing a permission it grants to nobody.
- **The leave year** is closed by assumption. It is the calendar year, 1 January to 31 December (A-09). Highest consequence in the register; confirm at the first opportunity.

**Shaping — these change the work, not the schema.**

1. What does **FL** stand for? Its rules are confirmed (it lapses at year end); only its expanded name is unknown.
2. Is there a **cap** on how much EL may be carried forward, and does carried-forward EL **expire**?
3. How is proration for a mid-year joiner computed — by **month** or by **day**, and how is a fractional result rounded? Relatedly, does leave **accrue** through the year, or is it granted annually?
4. **Dashboard analytics** — summary cards, or charts with date-range filtering? The phrase spans several days of work.
5. **Notifications** — genuine email delivery via SMTP, or in-app only? The choice carries real infrastructure cost.
6. **Reports and export** — is CSV sufficient, or is PDF required? PDF generation is materially more work.
7. Is **half-day leave** in scope? (Currently assumed out of scope, A-01.)
8. Are **Saturday and Sunday** the weekend for all employees? (Currently assumed yes, A-02.)
9. Do all employees share **one holiday calendar**? (Currently assumed yes, A-03.)
10. **Evaluation mode** — will this be reviewed against the requirements list, discussed in a technical conversation, or both? This changes where the remaining hours should go.
11. **Mid-year policy change.** The Admin may reconfigure a leave type. What happens to balances already accrued under the prior policy? The specification is silent (A-08).
12. Confirmation of **A-09**, the leave-year boundary.

### Deferred, to resolve in design rather than by asking

- Which balance quantity the Employee sees when they "view leave balance."
- Whether a request containing only non-working days is valid.
- Whether approved requests are recalculated when a holiday is subsequently declared.

## Process Note

This brief is an input to Module 1 of the learning path and does not discharge it. Module 1 additionally requires a problem statement, a business requirement document, stakeholder analysis, functional and non-functional requirement specifications, and an assumptions-and-constraints register. The confirmed-requirements, assumptions, and open-questions sections above feed those directly.

The `.memlog.md` alongside this file records the decisions, overrides, and corrections made while producing this brief — including three instances of AI-proposed reasoning corrected by human or adversarial review. It is the seed of the Module 10 prompt improvement log and the record of AI mistakes and corrections, and it cannot be reconstructed later. It should not be discarded when the brief is finalised.
