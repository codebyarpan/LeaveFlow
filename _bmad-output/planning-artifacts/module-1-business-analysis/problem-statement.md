---
title: "LeaveFlow — Problem Statement"
module: "1 — Understanding the Problem"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Problem Statement

> **Provenance note.** The specification describes a system to build; it does not describe the problem that system solves. Sections 1 and 2 below are therefore **engineer-authored context** — a reasoned account of why such a system exists, not a business problem supplied by any source. Sections 3 onward are grounded in the specification, the confirmed business rules, and the assignment's learning path, except where a sentence is explicitly marked as the engineer's judgement.

## 1. The Problem — engineer-authored context

Organizations must record, approve, and account for employee leave. Where this is done with spreadsheets, email threads, or paper forms, four failures recur:

**Balances cannot be trusted.** Entitlement, carry-forward, and proration for mid-year joiners are computed by hand. Errors are discovered late, usually by the employee who has been told they have fewer days than they believe.

**Requests have no state.** An emailed request is either answered or forgotten. Nobody can say how many requests await a decision, or how long they have waited.

**Approval authority is unenforced.** Nothing prevents a manager from approving leave for an employee who does not report to them, or an employee from viewing a colleague's leave history.

**Decisions leave no trail.** When a balance is disputed, there is no record of who approved what, when, or on what basis.

## 2. Who Feels It — engineer-authored context

Employees cannot see what leave they hold or where a request stands. Managers make approval decisions without visibility of who else on the team is away. Administrators reconcile balances manually at year end and answer entitlement questions individually.

## 3. What Is Required

Grounded in the specification.

A web-based system in which employees apply for leave against a balance the system computes, managers decide on requests from their own direct reports, and the Admin manages employees and departments and configures the policies — leave types, leave policies, holidays — that govern both. Access is enforced by role and, for managers, scoped to their own direct reports; every leave action is recorded.

*The engineer's judgement:* correctness matters more than breadth. A leave balance that is wrong is worse than a leave balance that is absent, because it will be believed.

## 4. Why This Project Exists

This is a company-assigned trainee project. The system is the vehicle; the objective, stated in the learning path, is to learn the complete AI-first software engineering lifecycle using BMAD — "to transform a business idea into production-ready software using AI agents rather than using AI only as a code generator."

The problem above is therefore solved not to ship a product into a market, but to practise the discipline of understanding a business before writing code, and of producing the engineering artifacts that professional delivery requires.

## 5. Scope Boundary

In scope: leave application, approval, balance computation, policy configuration, and audit, for a single organization with three roles.

Out of scope: payroll integration, attendance or time tracking, and any workflow beyond a single-manager approval step (an assumption — see A-06). The authoritative and complete out-of-scope list is held in `brd.md` §4, which distinguishes exclusions settled by the specification from those resting on unconfirmed assumptions.
