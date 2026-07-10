---
title: "LeaveFlow — Stakeholder Analysis"
module: "1 — Understanding the Problem"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Stakeholder Analysis

A stakeholder is anyone with an interest in the system. This is **not** the same question as who holds an account in it.

The system has exactly three roles — Admin, Manager, Employee — as fixed by the specification. No role may be added.

## System Users

| Stakeholder | Interest | Influence | Needs from the system |
| --- | --- | --- | --- |
| **Employee** | High — their leave, their balance | Low | Trustworthy balance; ability to apply, track, and cancel a pending request; visibility of leave history |
| **Manager** | High — team capacity and coverage | Medium | Requests from their own direct reports only; department leave calendar; enough context to decide |
| **Admin** | High — policy correctness and reporting | High | Management and configuration of leave types, leave policies, holidays, departments, and employees; organization-wide reporting and oversight |

The Admin owns leave policy within the system, as the specification states.

## Project Stakeholders Who Are Not System Users

| Stakeholder | Role in the project | Authority over | Not a system role because |
| --- | --- | --- | --- |
| **Assigning manager** | Project sponsor and evaluator | Scope, requirement interpretation, evaluation mode, the technology options offered | Owns the assignment, not the software |
| **Trainee engineer** | Sole developer and analyst | Engineering decisions, technology selection from the offered options, assumptions, sequencing | Builds the system; does not operate it |

## Authority Map

One external authority answers every question this project cannot answer for itself: **the assigning manager**. Requirement ambiguities, scope boundaries, the cancellation contradiction, the definition of the leave year, and the evaluation mode all route to him.

Everything else is the engineer's to decide and defend. The full open-question list is held in the brief's `addendum.md`.

## Conflicts and Tensions

**Employee versus Manager on visibility.** The confirmed rule places no restriction on multiple team members taking the same dates. The manager nonetheless needs the department leave calendar to see the consequence before approving. The system informs; it does not block.

**Assigning manager versus system.** The assigning manager's interest is in what the trainee learns and can defend. The assigning manager's interest diverges from what a real user would want: exhaustive feature coverage is worth less here than a smaller system with traceable reasoning behind every decision.

**Admin authority versus policy stability.** Because the Admin configures leave types and policies, a policy could change mid-year, with consequences for balances already accrued under the prior policy. The specification does not address this, and it is recorded as an assumption (A-08) rather than resolved here.
