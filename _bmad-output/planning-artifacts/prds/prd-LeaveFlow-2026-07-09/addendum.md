---
title: "LeaveFlow PRD — Addendum"
status: final
created: 2026-07-09
updated: 2026-07-10
---

# LeaveFlow PRD — Addendum

Material that earned a place in this run's record but does not belong in `prd.md`. Three kinds of thing live here: **rejected alternatives** with the reasoning that rejected them, **research grounding** that supports a PRD claim without being a PRD claim, and **technical-how** that belongs to Architecture (Module 3) or the ERD (Module 4) rather than to a requirements document.

Nothing here is a requirement. Nothing here is a domain rule. Where this document informs a decision recorded in `prd.md`, it names the section.

---

## 1. Rejected alternatives

### 1.1 Email notifications (`FR-14`)

**Chosen:** in-app notifications only.
**Rejected:** SMTP email; email-behind-a-feature-flag.

The specification's own wording — "email **or** in-app notifications" — authorizes either. The decision is therefore a scope choice, not a deviation.

**What was given up.** Comparable products treat email as table-stakes for approval workflows, and for a specific reason: managers do not live inside the HR application, and leave requests are time-sensitive because employees book travel and make commitments against them. Zoho People dispatches email *and* push notification to the approver on submission. Practitioner guidance goes further and recommends automated reminders to approvers who have not acted within roughly 48 hours. An in-app-only system depends on the manager choosing to log in.

**Why in-app nonetheless.** SMTP introduces a real infrastructure dependency, a delivery failure mode that must be designed for (bounces, retries, silent non-delivery), and a managed secret under `NFR-20`. Against a seven-day budget whose implementation window is three days, that cost is not justified. The email-behind-a-flag variant was rejected as the worst of both: it costs design time to specify a path that will not be built or tested.

**Consequence.** `FR-14` states this trade-off in the PRD body; §7.4 flags email as the deferral a domain-aware reviewer is likeliest to challenge.

### 1.2 Charted dashboard analytics (`FR-11`)

**Chosen:** per-role summary cards.
**Rejected:** cards plus charts with date-range filtering; deferring the shape of `FR-11` to Architecture.

The specification says "dashboard analytics" and supplies no acceptance criteria — the requirement is, as written, not testable. Deferring it to Architecture was rejected because an FR with no acceptance criteria is precisely what an evaluator probes, and pushing the gap downstream does not close it.

**Superseded, 2026-07-10.** This section recorded a live tension: `FR-14` and `FR-15` offer the specification's own choice ("email **or** in-app"; "CSV **or** PDF") and exercising a choice is not narrowing, whereas `FR-11` said "dashboard analytics" and offered no alternative — so summary cards were a *reduction*, with the budget a reason for it rather than a licence. That tension is closed: the scope of `FR-11` is now agreed as summary cards **with date-range filtering**, and charts are out. The reasoning is preserved because the reduction was real before it was agreed.

Comparables research supports the narrowing on its merits rather than only on budget. Across BambooHR, Zoho People, Keka, Freshteam, and greytHR, the employee-facing surface is consistently **summary cards per leave type plus a transaction ledger**, not charts. Charts appear at the admin and analytics tier. Freshteam's employee statement is literally a ledger — `Created on | event | dates | days | running balance`. So "cards for the employee, a queue and a calendar for the manager, charts for the admin" is the industry shape, and this PRD builds the first two and declares the third a stretch item.

### 1.3 Renumbering functional requirements

**Chosen:** carry `FR-01`–`FR-18` verbatim from the Module 1 BRD.
**Rejected:** renumbering to `FR-1`…`FR-N` in PRD reading order.

The template numbers FRs globally in document order. Following it would have been cosmetically tidier and would have broken every existing cross-reference — the BRD's role-to-requirement traceability matrix, the stakeholder analysis, and the NFR register all cite the Module 1 identifiers. Stable identifiers across the artifact chain are worth more than numeric contiguity within one document. New requirements, should any arise, begin at `FR-19`.

**This paid off.** Two new requirements did arise — `FR-19` (Manager views team members) and `FR-20` (Employee views leave history), covering permissions the specification grants that Module 1 never enumerated. They append cleanly at 19 and 20, and every existing reference to `FR-01`–`FR-18` in the BRD, the stakeholder analysis, and the NFR register still resolves.

### 1.4 Inventing a cancellation permission for approved leave

**Chosen at the time:** `Approved` is terminal (`D-07`).
**Rejected at the time:** granting the Admin, or the applicant's Manager, authority to cancel approved leave.

**REVERSED, 2026-07-10.** `BR-05` states that cancelling approved leave restores the deducted balance, yet the specification granted no role the authority to perform that cancellation. Rather than invent a permission to make an orphaned rule reachable, this PRD narrowed scope: approved leave could not be cancelled.

The project owner has since granted the authority explicitly — an **Employee** may cancel their own **Approved** request with **Admin** permission. `BR-05` is now a live, reachable rule, and `DR-14` states the opposite of what it once did. The original reasoning is preserved rather than deleted, because it was correct on the information available: the contradiction was resolved by *asking*, not by guessing, and the answer arrived from the only authority who could give it. The mechanism is now settled: the **Employee** raises a **Cancellation Request**, which an **Admin** approves or rejects, and leave whose dates have passed cannot be cancelled at all. What remains open is only the modelling shape — whether **Cancellation Requested** is a status on the request or a separate entity — which is Architecture's call.

### 1.5 Adding leave encashment

**Chosen:** encashment is a Non-Goal (§6) — proposed by this PRD, since confirmed as a project decision. The legal exposure is raised as Open Question 2.
**Rejected:** designing encashment into `FR-07`'s year-boundary behavior.

Research surfaced a genuine compliance concern (§2.2 below). The temptation was to resolve it by adding an encashment capability. That was rejected on two grounds. It was absent from the requirement set, and inventing scope is the specific failure mode the brief warns against. And it is a payroll-adjacent capability in a system that explicitly does not touch payroll. The correct move is to surface the exposure where a human decides, not to quietly build a feature nobody asked for.

### 1.6 Credential provisioning (`FR-01`, `FR-04`)

**Chosen, 2026-07-10:** an **Admin** supplies an **Employee**'s initial password when creating them; it is hashed before persistence and never returned; it is communicated outside LeaveFlow.
**Rejected:** a forced password change on first login; an email invitation; a password-reset or forgot-password flow; an Admin re-issue path; periodic expiry.

**How the gap surfaced.** During epic and story decomposition, not during requirements analysis. `FR-04` enumerates what an Admin sets when creating an Employee — Department, role, joining date, Manager — and never mentions a password. `FR-01` presumes credentials already exist. `FR-17` restricts the Employee's editable surface to **Full Name**. `FR-14` and §6 forbid email. ERD GAP-1 settled what the login *identity* is and, in its own words, never asked what the *credential* was. Every document in the chain assumed another had answered it, so an Admin could create an Employee who could never log in.

**Why not the forced first-login change**, which was the first plan drafted. It was the better product and the worse fit. It required a persisted `must_change_password` column, an authorization gate on every endpoint, a new endpoint, a new error code whose status code no source document could supply, an amendment to `AD-14`, and a live question about whether it constituted `FR-21` — which would have moved `SM-8`'s twenty-requirement denominator that addendum §1.3 exists to protect. Against a three-day implementation window, that is disproportionate. It was rejected on scope, not on merit.

**Why this is not new scope.** §6's governing exclusion — any feature not named in the specification is out of scope — would bar a forced change. It does not bar this. Nothing is added: the Admin's creation act is `FR-04`'s, and supplying a credential is the minimum that makes `FR-01` reachable at all. The decision is recorded as acceptance criteria on `FR-01` and `FR-04`, exactly as ERD GAP-1 and GAP-2 were recorded as glossary terms plus one criterion, and for the same reason.

**What was given up.** Recorded in §6 as a known production limitation: no recovery path; a permanent lockout, because `FR-04` forbids deletion and the **Email Address** is never reusable; attribution that binds an account rather than a person, because the Admin knows every password and none is rotated; and a compromised credential that cannot be revoked except by a refusable, irreversible deactivation. Comparable products all ship a reset flow. This one does not, and says so.

---

## 2. Research grounding

Two web-research passes were run during Discovery. Findings that support a PRD claim are recorded here; the PRD cites the conclusion, not the evidence.

### 2.1 The expansion of `FL` (supports `FR-06` note, `A-04`)

In Indian HR practice, *Floater Leave*, *Festival Leave*, *Floating Holiday*, *Optional Holiday*, and the government's *Restricted Holiday* denote a single benefit: a small pool, typically one to three days a year, of employee-chosen days off tied to festivals absent from the fixed company calendar.

The decisive evidence is not the abbreviation but the confirmed lapse rule (`BR-03`). This class of leave is universally use-it-or-lose-it — it cannot be carried forward, accumulated, or encashed. That matches FL exactly. And a triad of one carrying-forward type plus two lapsing types, where the second lapsing type is a short discretionary festival bucket, is the textbook Indian pattern.

*Flexi Leave* is ruled out: greytHR's own leave-type guide uses "flexi holiday" as a synonym for Earned Leave, which already occupies a separate slot in the triad.

"Floater Leave" is the most common HRMS field label and is the safest single expansion to record. "Festival Leave" denotes the same thing. The distinction is a company-convention matter with no structural consequence (`A-04`).

*Sources: greytHR leave-types guide; Keka floating-holiday glossary; hrsoftwarehyderabad.com on restricted holidays.*

### 2.2 Leave year, carry-forward caps, and the encashment obligation (supports Open Questions 1 and 2)

**Leave year.** The Factories Act 1948, §79, computes earned-leave entitlement from days worked in the *previous calendar year*, which is where `A-09` draws support. But the statute constrains how entitlement is *earned*, not which twelve-month window an employer runs internally. Many Indian organizations deliberately adopt an **April–March financial-year** leave cycle so that leave-encashment liability lands inside the same accounting close. Practitioner discussion frames the calendar cycle as *creating* extra work, because it forces a separate January–March accrual reconciliation at year-end.

The consequence for LeaveFlow is mechanical and total: a calendar-year system lapses CL and FL on 31 December; a financial-year system lapses them on 31 March. Carry-forward evaluates at a different boundary. `BR-04`'s prohibition on requests spanning two leave years bites on different dates. This is why Open Question 1 is flagged as blocking Day 3.

**Carry-forward caps and encashment.** Statutory ceilings: 30 days for adults under the Factories Act; commonly 30–45 days under state Shops and Establishments Acts, varying by state (Maharashtra and Delhi around 45; Karnataka around 30; Tamil Nadu restricts carry-forward). The materially important finding is that **earned leave above the cap is generally required to be encashed rather than forfeited**, and all accrued EL is encashed on separation at Basic + DA. Income Tax Act §10(10AA) caps the tax exemption on such encashment for non-government employees.

`DR-7` as written discards unused days of non-carrying-forward types, and the brief's open question about an EL cap contemplated silent forfeiture of the excess. That may be non-compliant depending on the state of operation. Casual and floater leave are generally non-statutory and contractual, which is consistent with them lapsing freely without an encashment obligation — so the exposure is specific to EL.

**Proration.** Monthly accrual is the common Indian HRMS default: annual entitlement ÷ 12, credited each month. Rounding to the nearest half-day is the most-recommended convention, as the neutral middle between round-up (favours the employee) and round-down (favours the employer). All rounding is company policy, not law. The collision with `A-01` — which forbids fractional leave days — is what makes Open Question 3 sharper than the brief originally framed it: the industry's default rounding rule *cannot be expressed* in this system, so a different rule must be chosen deliberately.

*Sources: Indian Kanoon, Factories Act §79; leavebalance.com on annual-leave entitlement; Pluxee leave-encashment guide; wisemonk.io and zotrack.com on prorated leave; CiteHR on financial vs calendar leave cycles.*

### 2.3 How comparable products present a balance with pending days (supports `FR-07`, `FR-11`)

The brief deferred a question to design: *which of the three balance quantities does the employee see when they "view leave balance"?*

The consistent industry pattern is that pending days are shown as a **distinct state**, never silently netted out. Workday displays *Available Balance* and *Remaining Balance* — the projected balance after this request — side by side on the request form. BambooHR moves approved days into a "Scheduled" bucket beneath the available balance, and at request time warns if the request would drive the balance negative, showing the projected negative figure before the user confirms. greytHR maintains a separate Pending tab and a ledger reading `Opening | Granted | Availed | Lapsed | Closing | Encashed`. Workday's calendar convention distinguishes pending from approved by colour: grey and green.

This grounds two PRD decisions. `FR-07` requires **Available** as the primary figure with **Reserved** disclosed alongside. `FR-08` requires the refusal message to name days requested against days available. Both follow the same principle the brief already articulated: a number that is wrong is worse than a number that is absent, because it will be believed.

*Note on divergence:* BambooHR and Workday **warn rather than block** on a negative projected balance. LeaveFlow **refuses** the submission (`FR-08`), because `FR-08`'s specified behavior is to refuse and because there is no unpaid-leave path to absorb the overage (§6).

### 2.4 Overlap and the department leave calendar (supports `FR-18`, `DR-15`)

`BR-06` places no restriction on multiple team members taking the same dates. The design risk is that "no restriction" silently becomes "no awareness."

Every serious comparable ships a shared team calendar as the manager's overlap-decision surface: BambooHR's "Who's Out", Freshteam's team calendar scopable to direct reports, Workday's Team Absence Calendar, Keka's shared team calendar, Darwinbox's single view of all reportees. The presentation converges on a month or week grid with one lane per team member and coloured bars per leave, so overlapping bars are visually obvious.

Two placements reduce bad approvals, and the first is the one `FR-18` adopts: show the team calendar **inline on the approval screen**, so the manager sees who else is away on those dates before deciding. The second — showing the team calendar to the employee at request time, as Keka does, so conflicts are avoided before submission — is **not** adopted. It is a plausible enhancement, out of scope for this budget, and recorded here rather than in the PRD because nothing in the specification asks for it.

### 2.5 Documented failure modes in leave systems (supports several)

Recorded because they independently corroborate decisions Module 1 reached on its own reasoning.

- **Pending days not reserved.** If a pending request does not reserve its days, two overlapping pending requests can each pass an "available" check and double-spend the same balance. This is `D-01` and `NFR-07`, arrived at independently.
- **Naive day counting.** Failing to exclude weekends and holidays inside a range overcharges the balance. Splitting leave around holidays is expected behavior. This is `D-02`.
- **Proration ignored for mid-year joiners**, who receive a full year's allotment. This is `BR-02`.
- **Year-end reconciliation.** The closing-balance identity `opening + granted − availed − lapsed − encashed` must reconcile exactly; carry-forward, lapse, and encashment edge cases are where leave systems break.
- **Negative-balance policy left undefined.** Whether to allow-with-warning or hard-block is a policy fork, not a default — one that real leave systems must choose deliberately.

---

## 3. Bound for Architecture (Module 3) and the ERD (Module 4)

Technical-how, recorded here deliberately and kept out of `prd.md`. Per the constraint governing §5 of the PRD, the **Domain Rules and Invariants** section consolidates existing rules only and introduces none — so the items below, which are new, are barred from it. They are raised for Architecture to settle explicitly rather than by default.

### 3.1 A leave date is a date, not an instant

**Decided.** A **Leave Date** is a calendar `DATE`, with no time component, never a UTC timestamp. This is now `DR-2a` in the PRD.

The reasoning, retained: storing or comparing leave dates as UTC timestamps produces off-by-one-day errors at midnight boundaries — a common, well-documented defect in leave systems that stays silent until it surfaces. It bears directly on `DR-1`, because it determines what "day" means in the day-count function. The failure mode it prevents: a request submitted late in the evening in one timezone counting an extra day, or a holiday falling on the wrong side of a boundary. Architecture implements the choice; it no longer makes it.

### 3.2 Entities whose shape is still open

Drawn from the brief's addendum, carried forward because the ERD will need them.

- **Reporting relationship.** Whether the employee-to-manager edge is an attribute on the employee record or a standalone relation. Load-bearing, because `DR-12` makes data-scoped authorization depend on it, and `NFR-04` requires the scope be applied *in the query*. The shape chosen determines whether that is a join or a column predicate. Note that `DR-12` evaluates the relationship **at decision time**, so a historical record of who managed whom is not required — but a reassignment must take effect immediately for **Pending** requests.
- **Supporting document.** Linkage to the leave request and the storage mechanism are unmodelled. `NFR-05` constrains it: outside the web root, client filenames never trusted as paths.
- **Audit entry.** Append-only (`NFR-09`). Whether it is one table for all transitions or specialized per transition type is undecided.
- **Company holiday.** A date and a name, global to the organization (`A-03`).
- **Leave balance.** Keyed per employee, per leave type, per **Leave Year** (`DR-3`). The **Leave Year** is confirmed as the calendar year, so this key is now safe — it was the highest-consequence open risk in the earlier draft.
- **Leave type.** Four attributes, all configured by the **Admin**: **Annual Entitlement** (a quantity), *carries-forward*, **Carry-Forward Cap**, and *requires-supporting-document*. The entitlement and the cap were missing from every source document and were supplied as project decisions; without the entitlement, `FR-07` had nothing to prorate. Proration is monthly against remaining months (`DR-9`), so a balance row needs an accrual basis the ERD must represent, not merely a total.
- **Notification.** Underspecified. Its link to the **Leave Request**, whether it carries a type discriminator (submitted / approved / rejected), and how read-state is represented are all undetermined. `FR-14` names the behavior, not the shape.
- **Cancellation Request.** **Decided: a separate entity**, linked to the **Leave Request** it targets, with its own **Pending**/**Approved**/**Rejected** lifecycle decided by an **Admin** (`FR-09`, `DR-14`). The targeted Leave Request remains **Approved** throughout. A cancellation therefore writes **Audit Entries** for both objects — the Cancellation Request's own transitions, and the Leave Request's move to **Cancelled** — which `DR-16` and `SM-4` both constrain.
- **Audit entry.** Must accommodate a non-human actor: a managerless auto-approval records `SYSTEM` with the reason `AUTO_APPROVED_NO_MANAGER` (`FR-16`). An actor column typed as a foreign key to Employee cannot represent it.

### 3.2a Surfaces the PRD implies

Raised by the downstream-readiness review. Two of the three have since been decided; the third remains an absence.

- **The leave-year rollover.** **Decided:** invoked by a system-triggered scheduled process, not a user action, with **Audit Entries** naming the actor `SYSTEM` (`FR-07`, `FR-16`). What remains for Architecture: idempotence. Nothing in the PRD says what happens if the scheduled process runs twice against the same **Leave Year**, and carry-forward is not naturally idempotent.
- **The audit read surface.** **Decided:** full read access to the audit log belongs to the **Admin** alone (`FR-16`, `DR-13`). The endpoint shape is Architecture's.
- **`FR-14`'s mark-read mutation is implied, not stated.** `FR-11` requires an unread count that decrements on reading. The transition that decrements it has no requirement of its own. Still an absence.

### 3.3 Concurrency

`NFR-07` requires reserve, consume, and release to be atomic, and `DR-5` makes `Available ≥ 0` an invariant under concurrent submission. The mechanism — row-level locking, an optimistic version column, a serializable transaction, or a database constraint — is Architecture's to choose. The PRD states the invariant and the test (`SM-1`) without prescribing the mechanism.

### 3.4 The leave-day function

`DR-2` requires exactly one implementation, pure, unit-tested, called by every balance path. Its signature takes a date range and the holiday calendar and returns a whole number. Architecture should site it where no layer can bypass it.

The likeliest place for a second implementation to appear is the frontend, computing a preview of the day count before submission — `UJ-1` turns on Rahul seeing the cost of his request before he commits to it. **`DR-2` admits no exception for the preview.** The frontend must obtain the count from the same implementation, by calling it, rather than reproducing weekend-and-holiday logic in the client. A client-side reimplementation drifts the moment the holiday calendar changes, even if it agrees with the server today.

---

## 4. Notes on personas

`UJ-1`'s protagonist Rahul was supplied by the author as a journey persona. Meera (`UJ-2`) and Anil (`UJ-3`) were invented to force the same specificity for the manager and admin paths.

As PRD §2.3 states, all three are illustrative fictions, not stakeholders or requirements; the three real roles are fixed in the PRD glossary. The real project stakeholders are the assigning manager (sponsor and evaluator, and the single external authority to whom every open question routes) and the trainee engineer (sole developer and analyst). Neither is a system user.
