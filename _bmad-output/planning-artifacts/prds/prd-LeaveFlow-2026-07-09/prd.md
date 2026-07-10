---
title: "LeaveFlow — Product Requirements Document"
status: final
created: 2026-07-09
updated: 2026-07-10
---

# PRD: LeaveFlow

## 0. Document Purpose

This PRD specifies LeaveFlow, a web-based employee leave management system for a single organization with three roles. It is written for the assigning manager who evaluates it, and for the downstream workflows that consume it: Architecture (Module 3), ERD (Module 4), and the epics and stories that follow. It builds on two existing artifacts and does not duplicate them — the [product brief](../../briefs/brief-LeaveFlow-2026-07-09/brief.md) establishes intent and scope, and [Module 1 Business Analysis](../../module-1-business-analysis/) establishes the requirement set, stakeholder map, and the register of business rules, engineering decisions, and assumptions.

The document is organized so that every claim has one home. Vocabulary is fixed in §3 Glossary and used verbatim everywhere else. Features are grouped behaviorally in §4, with functional requirements nested beneath them and numbered globally. §5 consolidates the domain rules that govern leave correctness; every one traces to a business rule or engineering decision established in Module 1. Requirement identifiers `FR-01` through `FR-18` are carried over unchanged from the Module 1 BRD so that the traceability chain into architecture and stories survives. `FR-19` and `FR-20` are new, added to cover two permissions the specification grants that Module 1 never turned into requirements.

Inferences the assigning manager has not confirmed would be tagged inline as `[ASSUMPTION: …]` and indexed in §12; as of finalization none remain. Tensions that need a human decision are marked `[NOTE FOR PM]`. Where a decision was made against known counter-evidence, the counter-evidence appears alongside the decision.

## 1. Vision

Leave administration by spreadsheet and email fails in four specific ways, and every one of them is a failure of record rather than a failure of effort. *(The four failures below are engineer-authored inference. The specification describes a system to build; it never states the problem that system solves.)* Balances cannot be trusted, because proration and carry-forward are computed by hand and the errors surface months later. Requests have no state — a request is an email, and an email that has been read looks exactly like an email that has been decided. Approval authority is unenforced, because nothing prevents the wrong manager from replying "approved." And decisions leave no trail, so a disagreement about what was approved in March is settled by whoever kept better notes.

LeaveFlow replaces that with a system of record. An employee sees a balance they can trust and applies against it. A manager sees the requests of their own direct reports, with the context needed to decide, and approves or rejects them. An administrator configures the leave policy the organization actually runs, and the system enforces it. Every Leave Request state change is attributable to an actor and a moment.

The product's ambition is narrow and its correctness bar is high. It does not integrate with payroll, track attendance, or model organizational structures more complex than one employee reporting to one manager. What it does instead is be right about the things that are hard to be right about: a leave balance that holds across proration, carry-forward, and the year boundary; a day count that excludes weekends and company holidays; an authorization model that scopes a manager to their own reports rather than to their job title; and an audit trail that survives the conversation. The guiding judgment, carried forward from the problem statement: **a leave balance that is wrong is worse than a leave balance that is absent, because it will be believed.**

## 2. Target User

LeaveFlow serves exactly three roles. The specification fixes this; no fourth role is introduced by this PRD.

### 2.1 Jobs To Be Done

**Employee**
- Know, without asking anyone, how much leave I have and what happens to it if I don't use it.
- Apply for leave and know the request actually reached someone who can decide it.
- Understand what a request will cost me *before* I commit to it — not after.
- See where a pending request stands, and withdraw it if my plans change.

**Manager**
- See the requests that are mine to decide, and only those.
- Decide with context: who else on the team is already away on those dates, and whether this person has the balance.
- Not be the reason someone's travel booking falls through, by deciding promptly.

**Admin**
- Configure the leave policy the organization actually runs — types, carry-forward behavior, holidays — without waiting on an engineer.
- Answer "who is off, and how much leave does the organization have on its books" without a manual reconciliation.
- Trust that the year-end rollover happened correctly.

### 2.2 Non-Users (v1)

- **Payroll and finance.** Leave encashment, loss-of-pay, and payroll feeds are out of scope. No number produced by LeaveFlow feeds a payroll system.
- **HR business partners and executives** beyond the Admin role. There is no analyst persona, no organization-wide absenteeism scoring, no Bradford Factor.
- **Employees of other organizations.** LeaveFlow runs one organization per deployment: one policy set, one hierarchy, one holiday calendar. Multi-organization and multi-tenant support *within* a deployment are out of scope. The same codebase may be deployed again, with its own database, for another organization.
- **Anyone approving leave who is not the applicant's direct manager.** Approval is single-step. There is no delegation, no escalation, no second approver. Where an **Employee** has no **Manager**, no one approves: the request is approved automatically (`FR-09`).

### 2.3 Key User Journeys

*Named-protagonist narratives the product enables. Numbered `UJ-1` through `UJ-3`. Functional requirements reference them inline. The protagonists below are illustrative fictions used to force specificity in the design — they are **not** stakeholders, roles, or requirements, and nothing in §4 depends on their existence.*

- **UJ-1. Rahul checks what the leave will cost him before he commits to it.**
  > Rahul has a family function and needs three days. He is authenticated, on the web app, on his own dashboard. He reads his **Available** balance for each **Leave Type** — the number he can actually spend today, not the number he was granted in January. He selects the leave type appropriate to the occasion, enters the date range, and the system shows him the **Leave Days** the request will actually consume: it has excluded the weekend, and it has excluded the **Company Holiday** that falls inside his range, so the request costs less than the calendar span suggests. He sees the balance he will be left with if this is approved. He submits. The request enters **Pending**, the days are **Reserved** against his balance so he cannot spend them twice, and it appears in his manager's queue.
  >
  > **Climax:** the moment the day count resolves to a number smaller than the number of dates he picked, and he understands *why* — the holiday is named on screen, not silently netted out.
  >
  > **Resolution:** the request is Pending. His Available balance has already dropped by the reserved days. He can cancel it himself while it remains Pending.
  >
  > **Edge case:** the request would cost more Leave Days than he has Available. The system refuses the submission and states the reason as a number — days requested against days available — rather than a generic validation failure. Realizes `FR-07`, `FR-08`.

- **UJ-2. Meera decides a request without discovering the overlap afterwards.**
  > Meera manages six people. Her dashboard shows a count of requests awaiting her decision. She opens Rahul's. On the same screen, she sees the **Department Leave Calendar** for the requested dates: two of her other reports are already approved as away for one of those days. Nothing in the system blocks her — `BR-06` places no restriction on overlapping leave — but she can now see the consequence she is authorizing, which is the entire point of showing it. She approves. The reserved days become **Consumed**. Rahul receives an in-app notification.
  >
  > **Climax:** the overlap is visible *at the moment of decision*, not discovered the following week.
  >
  > **Resolution:** the request is **Approved**, which is terminal. An **Audit Entry** records Meera as the actor and the moment.
  >
  > **Edge case:** Meera opens a request from someone who is not her direct report — by guessing a URL. The system does not show it to her. Authorization is scoped to the reporting relationship, not to the fact that she holds the Manager role. Realizes `FR-03`, `FR-09`, `FR-18`.

- **UJ-3. Anil configures the policy and the year rolls over correctly.**
  > Anil administers the system. Before the leave year begins he defines the **Leave Types** and their behavior — which carry forward, which lapse, which require a **Supporting Document** — as configuration rather than as code. He enters the year's **Company Holidays**. A new joiner arrives in August and receives a **Prorated** balance rather than a full year's entitlement. At the **Leave Year** boundary, EL carries forward and CL and FL lapse, per `BR-03`.
  >
  > **Climax:** a fourth leave type could be added without a code change, because carry-forward is a property of the type and not an `if` statement.
  >
  > **Resolution:** the organization runs on a policy Anil configured and can inspect. Realizes `FR-06`, `FR-07`, `FR-10`.

## 3. Glossary

*Downstream workflows and readers must use these terms exactly. Introducing a synonym anywhere in this PRD is a discipline violation.*

- **Employee** — A person with a LeaveFlow account. Also the name of the least-privileged role. Every Employee belongs to exactly one **Department** and has at most one **Manager**, and is identified by an **Email Address** and a **Full Name**.
- **Manager** — An **Employee** who additionally holds authority over their **Direct Reports**. A Manager is themselves an Employee with their own balances and requests.
- **Admin** — The role that configures **Leave Policy**, **Company Holidays**, **Departments**, and **Employee** records. An Admin can view all **Leave Requests** but holds **no approval authority** over them.
- **Direct Report** — An **Employee** whose **Manager** is a given Manager. The reporting relationship, not the role, is what grants a Manager authority over a **Leave Request**.
- **Department** — An organizational grouping of **Employees**. A Department with assigned Employees cannot be removed.
- **Email Address** — The unique identifier an **Employee** exchanges as their credential under `FR-01`. Maintained by the **Admin** (`FR-04`); not editable by the Employee who owns it. It is an identity, not a contact channel: LeaveFlow sends no email (`FR-14`).
- **Full Name** — The human-readable identity of an **Employee**, shown wherever an Employee is listed (`FR-19`). The only profile field its owner may edit (`FR-17`).
- **Leave Type** — A category of leave, configured as data. Three exist: **EL** (Earned Leave), **CL** (Casual Leave), **FL** (Floater Leave). Each carries four configured attributes: its **Annual Entitlement**, whether it **carries forward** at the **Leave Year** boundary, its **Carry-Forward Cap**, and whether it requires a **Supporting Document**.
- **Annual Entitlement** — The number of **Leave Days** a **Leave Type** grants an **Employee** for a full **Leave Year**. Configured by the **Admin** per Leave Type. The base quantity **Proration** reduces for a mid-year joiner.
- **Leave Policy** — The set of configured **Leave Types** and their attributes. Owned by the **Admin**. Changing it is a configuration act, not a deployment.
- **Leave Year** — The twelve-month window over which balances accrue, carry forward, and lapse. The Leave Year is the calendar year, 1 January to 31 December.
- **Company Holiday** — A single dated day on which the organization does not work, maintained by the **Admin**. Global to the organization: no Company Holiday is scoped by location or **Department**.
- **Working Day** — A date that is neither a weekend day nor a **Company Holiday**. Saturday and Sunday are non-working days for every **Employee**.
- **Leave Day** — The unit a **Leave Request** consumes. The count of **Working Days** within the request's date range. Always a whole number: half-day leave is not supported, and a fractional Leave Day cannot be expressed.
- **Leave Request** — An **Employee**'s application for leave of a given **Leave Type** over a contiguous date range, in exactly one of the states **Pending**, **Approved**, **Rejected**, or **Cancelled**.
- **Cancellation Request** — A distinct application, made by an **Employee** against their own **Approved** **Leave Request**, asking for it to be cancelled. It has its own lifecycle — **Pending**, **Approved**, **Rejected** — decided by an **Admin**. The **Leave Request** it targets remains **Approved** while the Cancellation Request is Pending. It is a separate entity, not a state of the Leave Request.
- **Leave Date** — A calendar date. Leave dates carry no time component and are not instants; they are not stored or compared as timestamps.
- **Leave Balance** — An **Employee**'s standing in a **Leave Type** for a **Leave Year**, expressed as three quantities: **Accrued**, **Reserved**, **Consumed**.
- **Accrued** — **Leave Days** granted to an Employee for a Leave Type in a Leave Year, after **Proration** and any **Carry-Forward**.
- **Reserved** — **Leave Days** committed to **Pending** **Leave Requests** and not yet **Consumed**. Reserved days are unspendable.
- **Consumed** — **Leave Days** deducted by **Approved** **Leave Requests**.
- **Available** — The derived quantity `Accrued − Consumed − Reserved`. The number an **Employee** can actually spend. Not stored.
- **Carry-Forward** — The transfer of unused **Accrued** days across the **Leave Year** boundary. A configured property of a **Leave Type**. EL carries forward; CL and FL do not.
- **Carry-Forward Cap** — The maximum number of unused **Accrued** days a **Leave Type** may carry across the **Leave Year** boundary. Configured by the **Admin** per Leave Type. No cap is fixed in code.
- **Lapse** — The discarding of unused **Accrued** days at the **Leave Year** boundary, for **Leave Types** that do not carry forward.
- **Proration** — The reduction of a mid-year joiner's **Accrued** entitlement in proportion to the part of the **Leave Year** they are employed for. The result is rounded **down** to the nearest whole **Leave Day**.
- **Supporting Document** — A file attached to a **Leave Request**, required when the **Leave Type** is configured to require one.
- **Audit Entry** — An append-only record of one **Leave Request** state transition: the request, the transition, the actor, the timestamp.
- **Notification** — An in-app message delivered to an **Employee** on submission (to the **Manager**) or on decision (to the applicant).
- **Department Leave Calendar** — A **Manager**'s view of their **Direct Reports**' leave over a date range. Informational; it never blocks a decision.

## 4. Features

*Functional requirements retain the identifiers assigned in the Module 1 BRD (`FR-01`–`FR-18`). They are grouped here by behavior rather than by number, so numeric order is not reading order.*

### 4.1 Identity and Access

**Description:** Every interaction is authenticated and every authorization decision is made server-side against the data, not against the caller's role name. This is the feature the rest of the system rests on: a **Manager**'s authority comes from the **Direct Report** relationship, so a Manager who is not *this* applicant's Manager is, for this request, indistinguishable from a stranger. Realizes `UJ-2`.

**Functional Requirements:**

#### FR-01: User Authentication

An **Employee** can exchange credentials for an authenticated session.

**Consequences (testable):**
- A correct credential pair returns a session token; an incorrect one does not.
- The credential pair is the **Employee**'s **Email Address** and the initial password an **Admin** supplied when creating them (`FR-04`). LeaveFlow offers no other way to establish a password, and no way to change one.
- A failed authentication does not disclose whether the account exists: the response to an unknown identity and the response to a wrong password are byte-identical in body and equal in status code.
- No stored representation of a password permits recovery of the password.

#### FR-02: JWT-Based Authorization

The system carries the authenticated session as a JSON Web Token presented on each request.

**Consequences (testable):**
- A request with no token is rejected.
- A request with an expired token is rejected.
- A request whose token signature does not verify is rejected, including one whose payload was altered to change the subject or role.

#### FR-03: Role-Based Access Control

The system grants each **Employee** the capabilities of exactly one role — **Employee**, **Manager**, or **Admin** — and scopes every Manager action to that Manager's **Direct Reports**.

**Consequences (testable):**
- A **Manager** can read and decide a **Leave Request** whose applicant is their **Direct Report**.
- A Manager attempting to read or decide a Leave Request belonging to a non-report receives the same response as for a nonexistent request. Holding the Manager role is insufficient; the reporting relationship is checked.
- An **Admin** can read every Leave Request and can decide none. Approval is not among the Admin's capabilities.
- Authorization is enforced at the API boundary. A client that does not render a control cannot invoke it by calling the endpoint directly.

**Feature-specific NFRs:**
- Data scoping is applied where data is fetched, not by filtering results after retrieval (`NFR-04`).

### 4.2 Organization Administration

**Description:** The **Admin** maintains the people and the structure. Deactivation, not deletion, is how a departed **Employee** leaves the system, because their **Leave Requests** and **Audit Entries** must survive them. Realizes `UJ-3`.

**Functional Requirements:**

#### FR-04: Employee Management

An **Admin** can create, read, update, and deactivate **Employee** records, including each Employee's **Department**, role, joining date, and **Manager**.

**Consequences (testable):**
- An **Employee** is never physically deleted. Deactivation preserves their **Leave Requests**, **Leave Balances**, and **Audit Entries**.
- An Employee with unresolved **Pending** **Leave Requests** cannot be deactivated. The attempt is refused until those requests are approved, rejected, or cancelled.
- A **Manager** with at least one **Direct Report** cannot be deactivated. The attempt is refused until every Direct Report has been reassigned to another Manager. This keeps `FR-09`'s managerless auto-approval from being reached by an **Admin** deactivating a Manager.
- A deactivated Employee cannot authenticate.
- Assigning a Manager to an Employee establishes the **Direct Report** relationship that `FR-03` enforces.
- Creating an **Employee** requires the **Admin** to supply that Employee's initial password. It is hashed before persistence and never stored in a form that permits its recovery (`NFR-01`). No response from any endpoint returns a password or its hash.
- Updating an **Employee** does not accept a password. There is no re-issue path, and no other role or endpoint can set one. The **Admin** communicates the initial password to the **Employee** outside LeaveFlow, which sends no email (`FR-14`).

#### FR-05: Department Management

An **Admin** can create, read, update, and remove **Departments**.

**Consequences (testable):**
- A Department with at least one assigned **Employee** cannot be removed; the attempt is refused and names the obstruction.

#### FR-17: Personal Profile Management

An **Employee** can update their own profile.

**Consequences (testable):**
- An Employee can edit their own profile fields and no other Employee's.
- The only profile field an **Employee** may edit is their **Full Name**.
- Role, **Department**, **Manager**, joining date, **Email Address**, and any **Leave Balance** quantity are not editable by the Employee who owns them. An attempt to alter them through the profile endpoint is refused. The **Email Address** is maintained by the **Admin** under `FR-04`.

**Notes:**
- The two deactivation guards close different holes. The first protects the departing **Employee**'s own in-flight requests. The second protects their **Direct Reports**: without it, deactivating a **Manager** would orphan their reports, and `FR-09` would auto-approve the reports' **Pending** requests because no approver remained. Auto-approval exists for an **Employee** who legitimately has no Manager, not for one whose Manager was deactivated out from under them.
- `FR-17` does not appear in the specification's enumerated requirement list. Module 1 derived it from a permission the specification grants the Employee role ("update personal profile"). The derivation is recorded here so that a reader tracing requirements back to the specification does not find it missing and assume an error. The same applies to `FR-18`.
- **A password is a credential, not a profile field.** A reader may reasonably take "update personal profile" to include changing a password. It does not: `FR-17`'s editable surface is **Full Name** alone, and **no endpoint anywhere permits an Employee to change their own password**. The initial password is set once by the **Admin** under `FR-04`. The security limitation this leaves is recorded in §6.

### 4.3 Leave Policy Configuration

**Description:** Policy is data. The **Admin** defines what a **Leave Type** *is* — whether it survives the **Leave Year** boundary, whether it demands a **Supporting Document** — and the system reads those attributes at runtime. The design target is that a fourth leave type requires no code change. Realizes `UJ-3`.

**Functional Requirements:**

#### FR-06: Leave Type Management

An **Admin** can configure **Leave Types** and their attributes.

**Consequences (testable):**
- Three Leave Types exist at initialization: **EL**, **CL**, **FL**.
- Each Leave Type carries an **Annual Entitlement** quantity, a **carries-forward** attribute, and a **requires-supporting-document** attribute, all stored as data.
- At initialization, **EL**, **CL** and **FL** are seeded with *requires-supporting-document* **false**: no seeded Leave Type requires a **Supporting Document**. An **Admin** may set the attribute true for any Leave Type at any time.
- An **Admin** can set and change a Leave Type's **Annual Entitlement**.
- An **Admin** can set and change a Leave Type's **Carry-Forward Cap**. No cap value is fixed in code; a universal cap is not hardcoded.
- When a **Leave Policy** change would affect **Leave Balances** that already exist, the system does not decide the outcome: it requires the **Admin** to choose explicitly whether existing balances are recalculated under the new policy or left as accrued under the old one. The change cannot be applied without that choice being made and recorded.
- A recalculation chosen under the previous consequence obeys the same non-negativity guard as `FR-10`. It never produces a negative **Available** balance in any **Leave Year**. Where it would, it is **refused** for the affected **Employee** and **Leave Type**, whose **Leave Requests** and **Leave Balances** are left unchanged, and the case is recorded in the same durable store the **Admin** reads (`FR-10`). The remainder of the change proceeds for the **Employees** and **Leave Types** it does not affect.
- Creating a fourth Leave Type through configuration alone yields a type that can be applied for, reserved against, approved, and rolled over at the **Leave Year** boundary, with no code change and no schema migration.
- **Carry-Forward** and **Lapse** behavior is decided by reading the Leave Type's *carries-forward* attribute. The test: create a fourth Leave Type with *carries-forward* true, run the **Leave Year** rollover, and observe its unused **Accrued** days carried forward — with no code change between creating it and rolling it over. *(A code-inspection criterion — that no branch anywhere tests a Leave Type by name — cannot be proven by a passing test; it belongs to code review, not to this requirement's acceptance.)*

**Notes:**
- **FL** denotes **Floater Leave**. The specification did not expand the abbreviation; the expansion is a confirmed project decision, consistent with domain practice — that class of leave is universally use-it-or-lose-it, matching FL's lapse behavior under `BR-03`. Grounding in [addendum §2.1](addendum.md).

#### FR-10: Holiday Management

An **Admin** can maintain the **Company Holiday** calendar for a **Leave Year**.

**Consequences (testable):**
- A Company Holiday is a date and a name.
- A date recorded as a Company Holiday is not a **Working Day**, and therefore is not counted as a **Leave Day** by `FR-08`.
- The holiday calendar is global; no Company Holiday is scoped to a **Department** or a location.
- Adding or deleting a Company Holiday inside the date range of a **Pending** **Leave Request** recalculates that request's **Leave Day** count and its **Reserved** days.
- Adding or deleting a Company Holiday inside the date range of an **Approved** **Leave Request** whose dates are still in the future recalculates that request's **Leave Day** count and the applicant's **Leave Balance**.
- A recalculation never produces a negative **Available** balance (`DR-5`) — neither in the recalculated **Leave Year** nor in any later one. Where it would, the recalculation is **refused** for that **Employee** and **Leave Type**: their **Leave Requests** and **Leave Balances** are left unchanged, and the case is recorded in a durable store the **Admin** can read. The remainder of the operation proceeds for the **Employees** and **Leave Types** it does not affect. The same guard governs a recalculation triggered by a **Leave Policy** change under `FR-06`.
- An **Admin** can read the cases recorded by a refused recalculation. No other role can.
- An **Approved** **Leave Request** whose dates have already passed is **not** recalculated. Historical leave is not revised when the holiday calendar changes.

### 4.4 Leave Balances

**Description:** The balance is the product's central claim to trustworthiness, and it is three numbers rather than one. **Accrued** is what the **Employee** was granted. **Consumed** is what **Approved** leave has spent. **Reserved** is what **Pending** leave has committed but not yet spent. **Available** — the only number an Employee can act on — is derived from all three. Showing a single undifferentiated "balance" that silently included **Reserved** days would reproduce precisely the failure this product exists to eliminate: a number that is wrong and believed. Realizes `UJ-1`.

**Functional Requirements:**

#### FR-07: Leave Balance Tracking

The system maintains, for each **Employee**, **Leave Type**, and **Leave Year**, the quantities **Accrued**, **Reserved**, and **Consumed**, and derives **Available** from them.

**Consequences (testable):**
- `Available = Accrued − Consumed − Reserved` holds after every state transition of every **Leave Request**.
- No sequence of transitions produces a negative **Available** balance.
- An **Employee** who joins mid-**Leave-Year** receives a **Prorated** **Accrued** balance rather than the **Leave Type**'s full **Annual Entitlement** (`BR-02`).
- **Proration** is monthly, against the remaining months of the **Leave Year**: `Annual Entitlement × (remaining months ÷ 12)`, where remaining months counts the joining month through December inclusive.
- The prorated result is rounded **down** to the nearest whole **Leave Day**. An **Annual Entitlement** of 12 days for an **Employee** joining in September yields `12 × 4/12 = 4` days. A computed entitlement of 4.16 days yields 4.
- At the **Leave Year** boundary, unused **Accrued** EL carries forward up to its **Carry-Forward Cap**; the excess, and unused **Accrued** CL and FL, lapse (`BR-03`, `DR-7`).
- The **Leave Year** rollover is invoked by a system-triggered scheduled process, not by a user action. It records its execution in a separate append-only rollover log, not among **Audit Entries**, because it transitions no **Leave Request** (§3, `SM-4`).
- An Employee viewing their balance sees **Available** as the primary figure, with **Reserved** disclosed alongside it, so that days committed to a **Pending** request are visible.

**Notes:**
- **Provenance of the consequence above.** The brief filed "which balance quantity the Employee sees" as a *proposal, not a decision*, and deferred it to design. This PRD promotes it to a requirement. The grounds are that comparable systems (Workday, BambooHR) universally show pending days as a distinct state and display the projected post-request balance. The promotion is recorded here so that a reader comparing this PRD against the brief finds a declared decision.
- Earned Leave above the **Carry-Forward Cap** lapses (`DR-7`). The compliance limitation this creates is recorded in §6.

### 4.5 Leave Request Lifecycle

**Description:** A **Leave Request** has four states and a small number of legal transitions between them. Submitting reserves days. Approving consumes them. Rejecting or cancelling releases them. **Approved** is not terminal, but nothing moves a Leave Request out of Approved directly: an **Employee** raises a separate **Cancellation Request** against it, which an **Admin** approves or rejects, and the Leave Request stays **Approved** throughout that decision. Only an approved Cancellation Request moves it to **Cancelled**. Leave whose dates have already passed cannot be cancelled. An **Employee** who has no **Manager** has no possible approver, so their request is approved on submission by the system, without passing through **Pending**. Every transition writes an **Audit Entry**. Realizes `UJ-1`, `UJ-2`.

The state machine:

| From | To | Actor | Effect on balance |
|---|---|---|---|
| — | Pending | Employee (own) | Reserve **Leave Days** |
| — | Approved | System, when the applicant has no **Manager** | **Consume** immediately; no reservation stage |
| Pending | Approved | Manager (of applicant) | Release reservation; **Consume** |
| Pending | Rejected | Manager (of applicant) | Release reservation |
| Pending | Cancelled | Employee (own) | Release reservation |
| Approved | Cancelled | Admin, by approving a **Cancellation Request** | Release **Consumed** days, restoring **Available** (`BR-05`) |

A **Cancellation Request** has its own lifecycle, and its states are not states of the **Leave Request**:

| From | To | Actor | Effect on the Leave Request |
|---|---|---|---|
| — | Pending | Employee (own), future-dated leave only | None; the Leave Request remains **Approved** |
| Pending | Approved | Admin | The targeted Leave Request moves to **Cancelled** |
| Pending | Rejected | Admin | None; the Leave Request remains **Approved** |

**Functional Requirements:**

#### FR-08: Leave Request Workflow

An **Employee** can submit a **Leave Request** for a **Leave Type** over a contiguous date range, which the system prices in **Leave Days** and admits as **Pending**.

**Consequences (testable):**
- The **Leave Day** count of a request equals the number of **Working Days** in its date range — weekend days and **Company Holidays** within the range are excluded. A Friday-to-Tuesday request spanning a Saturday, a Sunday, and a Monday that is a Company Holiday costs **2** Leave Days.
- A request whose **Leave Day** count exceeds the applicant's **Available** balance for that **Leave Type** is refused, and the refusal states the days requested and the days available.
- A request whose date range spans two **Leave Years** is refused. The Employee submits one request per Leave Year (`BR-04`).
- On admission, the request's **Leave Days** are **Reserved**, and the applicant's **Available** balance falls immediately by that amount.
- Two concurrent submissions that would together exceed **Available** cannot both succeed.
- A request submitted by an **Employee** who has no **Manager** is admitted directly as **Approved**, consuming its **Leave Days** without a reservation stage (`FR-09`). The **Available** check above still applies.
- A request whose **Leave Day** count is zero is refused as invalid. A date range containing only weekend days and **Company Holidays** cannot be submitted.
- A request whose end date precedes its start date is refused as invalid.
- A request whose date range lies wholly in the past is refused as invalid.

**Out of Scope:**
- Half-day and hourly leave.

#### FR-09: Approval and Rejection

The **Manager** of a **Leave Request**'s applicant can approve or reject it while it is **Pending**. The applicant can cancel it while it is **Pending**, and can raise a **Cancellation Request** against it once **Approved**. An applicant who has no Manager has their request approved automatically by the system.

**Consequences (testable):**
- Approval moves **Reserved** days to **Consumed**. Rejection and cancellation of a **Pending** request release **Reserved** days, restoring **Available**.
- Only the applicant's **Manager** can approve or reject a **Pending** request. An **Admin** cannot. A different Manager cannot (`FR-03`).
- Only the applicant can cancel a **Pending** request, and only their own.
- Only the applicant can raise a **Cancellation Request** against their own **Approved** request. Only an **Admin** can approve or reject it. The applicant cannot cancel approved leave unilaterally.
- While a **Cancellation Request** is **Pending**, the **Leave Request** it targets remains **Approved**, and its days remain **Consumed**.
- An approved **Cancellation Request** moves the targeted **Leave Request** to **Cancelled** and releases its **Consumed** days, restoring **Available** (`BR-05`). A rejected one changes nothing.
- An **Approved** **Leave Request** whose dates have already passed cannot be cancelled. A **Cancellation Request** against it is refused.
- Authority to decide a **Pending** **Leave Request** is evaluated at decision time, not at submission. Where an applicant's **Manager** changes while their request is Pending, the applicant's **current** Manager decides it.
- A **Leave Request** submitted by an **Employee** with no **Manager** is **Approved** on submission, without a **Pending** stage. The **Audit Entry** for that transition names the actor `SYSTEM` and the reason `AUTO_APPROVED_NO_MANAGER`. This path is reachable only for an Employee who genuinely has no Manager; `FR-04` forbids deactivating a Manager who still has **Direct Reports**.
- Every transition writes exactly one **Audit Entry** (`FR-16`).
- When two conflicting transitions are attempted concurrently, the first to commit succeeds and the second fails, because the **Leave Request** is no longer in the state that transition requires. A **Manager** approving a request the applicant has just cancelled receives a failure, not a silent overwrite.

**Notes:**
- `BR-05` ("cancelling approved leave restores the deducted balance") was unreachable under the permissions the specification granted, and earlier drafts of this PRD narrowed scope to match (`D-07`). **That narrowing is reversed.** Approved-leave cancellation is now in scope, gated on **Admin** permission, and `BR-05` is a live rule rather than documented-but-unreachable policy.
- A **Cancellation Request** is a distinct entity with its own **Pending**/**Approved**/**Rejected** lifecycle, not a state of the **Leave Request**. A cancellation therefore writes **Audit Entries** for both objects: the Cancellation Request's own transitions, and the Leave Request's move to **Cancelled** when one is approved.

#### FR-13: Supporting Document Upload

An **Employee** can attach a **Supporting Document** to a **Leave Request** whose **Leave Type** requires one.

**Consequences (testable):**
- A **Leave Request** for a **Leave Type** configured as requiring a **Supporting Document** cannot be submitted without one.
- Uploads are validated before storage. Permitted file types are PDF, JPG/JPEG, and PNG. The maximum size is 5 MB per file. A file failing either check is rejected.
- A Supporting Document is retrievable by those authorized to view its **Leave Request** — the applicant, the applicant's **Manager**, and the **Admin** (`FR-03`). No other **Employee** can retrieve it.

**Feature-specific NFRs:**
- Documents are stored outside the web root. A filename supplied by the client is never used as a storage path (`NFR-05`).

**Notes:**

#### FR-16: Audit Logs

The system records every **Leave Request** state transition as an **Audit Entry**.

**Consequences (testable):**
- Each Audit Entry names the **Leave Request**, the transition, the actor, and the timestamp.
- Where a transition was caused by the system rather than a person, the actor is recorded as `SYSTEM` together with an explicit reason — for a managerless auto-approval, `AUTO_APPROVED_NO_MANAGER`. No human approver is fabricated.
- Audit Entries are append-only. No application code path updates or deletes one.
- Full read access to the audit log is restricted to the **Admin**. No **Employee** or **Manager** can read it (`FR-03`).
- The number of Audit Entries for a Leave Request equals the number of state transitions it has undergone.

### 4.6 Visibility and Decision Support

**Description:** A **Manager** deciding a **Leave Request** needs to know what they are authorizing. `BR-06` places no restriction on **Direct Reports** taking leave on the same dates — the system does not block overlap — but a Manager who cannot *see* the overlap is deciding blind, and "no restriction" quietly becomes "no awareness." The **Department Leave Calendar** exists to make `BR-06` a considered choice rather than an accident. Realizes `UJ-2`.

**Functional Requirements:**

#### FR-11: Dashboard

Each role sees a dashboard scoped to what that role can act on.

**Consequences (testable):**
- The **Employee** dashboard presents, per **Leave Type**: **Available**, **Reserved**, and **Consumed**; plus a count of **Pending** requests.
- The **Manager** dashboard presents a count of **Leave Requests** awaiting their decision, and their **Direct Reports** who are on approved leave within the next seven days.
- The **Admin** dashboard presents organization-wide totals: **Employees** on approved leave today, and **Pending** request count.
- Every dashboard supports a **date-range filter**; the figures presented are those falling inside the selected range.
- A **Manager** requesting the Employee dashboard sees their own balances, not their reports'. An **Employee** requesting the Manager dashboard is refused (`FR-03`).

**Notes:**
- All three roles receive a role-specific dashboard: the **Employee** sees personal leave information, the **Manager** sees team and **Department** information within their authorization scope (`FR-03`), and the **Admin** sees organization-wide information. Module 1's role-to-requirement matrix assigns `FR-11` to the Admin and Manager only, contradicting Module 1's own `FR-11` prose. **The matrix is wrong and needs correcting upstream** — this PRD is not the defect.
- `FR-11` delivers per-role summary cards with date-range filtering. Charts and trend lines are out of scope (§7.4). Earlier drafts of this PRD flagged the summary-card scope as an unauthorized reduction of the specification's "dashboard analytics"; that flag is withdrawn — the scope is now agreed.

#### FR-18: Department Leave Calendar

A **Manager** can view their **Direct Reports**' leave across a date range.

**Consequences (testable):**
- The calendar shows **Approved** and **Pending** leave, visually distinguished from one another.
- It shows only the viewing Manager's **Direct Reports** (`FR-03`).
- It is presented on the approval screen for the dates of the **Leave Request** under decision, so that overlap is visible at the moment of the decision.
- It never prevents an approval. Overlapping leave produces no warning, no block, and no required acknowledgement (`BR-06`).

**Notes:**
- Like `FR-17`, `FR-18` is derived in Module 1 from a permission granted to the Manager role ("view department leave calendar") rather than taken from the specification's enumerated list.

#### FR-19: Team Member List

A **Manager** can view the **Employees** who report to them.

**Consequences (testable):**
- The list contains exactly the viewing Manager's **Direct Reports**, and no other **Employee** (`FR-03`).
- Each entry identifies the **Employee** and their **Department**.
- A deactivated **Direct Report** is distinguishable from an active one.

**Notes:**
- `FR-19` covers a permission the specification grants the Manager role ("view team members") that Module 1's enumerated requirement list omitted. Added by project decision; Module 1 should be amended to match.

#### FR-20: Leave History

An **Employee** can view their own **Leave Requests** across **Leave Years**.

**Consequences (testable):**
- The history contains every **Leave Request** the **Employee** has submitted, in every state, including **Cancelled** and **Rejected**.
- Each entry shows the **Leave Type**, the date range, the **Leave Day** count, and the current state.
- An Employee sees only their own history. A **Manager** sees a **Direct Report**'s history; an **Admin** sees any Employee's (`FR-03`).

**Notes:**
- `FR-20` covers a permission the specification grants the Employee role ("view leave history") that Module 1's enumerated requirement list omitted. Added by project decision; Module 1 should be amended to match.

#### FR-12: Search, Filtering, and Pagination

List endpoints support filtering, and return bounded pages.

**Consequences (testable):**
- Every list endpoint enforces a maximum page size on the server. A client requesting a larger page receives the maximum, not the larger page.
- Filters compose: **Leave Type**, state, and date range can be applied together.
- Filtering never widens authorization. A **Manager** filtering across all **Departments** sees only their **Direct Reports** (`FR-03`).

### 4.7 Notifications

**Description:** A **Leave Request** that reaches no one is an email in a different costume. **Notifications** close the loop: the **Manager** learns a decision is waiting, and the applicant learns it was made. Realizes `UJ-1`, `UJ-2`.

**Functional Requirements:**

#### FR-14: In-App Notifications

The system notifies the **Manager** when a **Direct Report** submits a **Leave Request**, and notifies the applicant when the request is approved or rejected.

**Consequences (testable):**
- Submission of a Leave Request creates exactly one **Notification** addressed to the applicant's **Manager**.
- Approval or rejection creates exactly one Notification addressed to the applicant.
- A Notification is readable only by its addressee.
- An unread count is retrievable, and reading a Notification decrements it.
- An addressee can mark a **Notification** read. Marking read is idempotent, and only the addressee may do it.

**Notes:**
- The specification permits "email or in-app notifications." This PRD chooses in-app only. **The trade-off:** in industry practice email is table-stakes for approval workflows, because managers do not live in the application and applicants book travel against pending requests. In-app-only notification is therefore a known departure from how production leave systems behave. It is chosen because SMTP introduces real infrastructure, a delivery failure mode to design for, and a managed secret — costs that are not justified inside a seven-day budget whose implementation window is three days. Email delivery is deferred, not deemed unnecessary. See §6 and §7.

### 4.8 Reporting and Export

**Description:** Reports answer questions the dashboards do not: what did this team's leave look like across a quarter, what does the organization have on its books. They are exports, not analytics. Realizes `UJ-3`.

**Functional Requirements:**

#### FR-15: Reports and Export

A **Manager** can export a leave report for their **Direct Reports**; an **Admin** can export one organization-wide.

**Consequences (testable):**
- Export format is CSV.
- The exported rows are exactly the rows matching the applied filters — the filter set applied to the view is applied to the export.
- A Manager's export contains only their **Direct Reports** (`FR-03`). An Admin's contains all **Employees**.

**Notes:**
- The specification permits "CSV or PDF." CSV alone is chosen; PDF generation is a real dependency and a material cost against the implementation budget. `[NON-GOAL for MVP]` — see §7.

## 5. Domain Rules and Invariants

*This section introduces no new rules. It consolidates rules established in the Module 1 BRD and assumptions register into one normative place, because they are otherwise scattered across business rules, engineering decisions, and NFRs — and because Architecture, the ERD, and the test plan will each need to source them. Every rule below carries its origin.*

### 5.1 Leave-day calculation

- **DR-1.** The **Leave Day** count of a date range is the number of **Working Days** it contains. Weekend days (Saturday, Sunday) and **Company Holidays** are excluded. *(D-02)*
- **DR-2.** The calculation is a pure function of the date range and the holiday calendar. It has exactly one implementation, and every path that touches a **Leave Balance** calls it. A second implementation of weekend-or-holiday logic anywhere in the codebase is a defect. *(D-02, NFR-08)*
- **DR-2a.** A **Leave Date** is a calendar `DATE`. Leave dates carry no time component and are never stored or compared as UTC timestamps, which would produce off-by-one-day errors at midnight boundaries. *(Confirmed decision.)*

### 5.2 Balance model

- **DR-3.** A **Leave Balance** is three stored quantities — **Accrued**, **Reserved**, **Consumed** — and one derived quantity, **Available**, equal to `Accrued − Consumed − Reserved`. **Available** is never stored. *(D-01)*
- **DR-4.** Submitting a **Leave Request** reserves its **Leave Days**. Approving consumes them. Rejecting and cancelling release them — including cancellation of an **Approved** request via an **Admin**-approved **Cancellation Request**, which releases **Consumed** days. *(D-01, BR-05)*
- **DR-5.** `Available ≥ 0` is an invariant. It holds after every transition, including under concurrent submission and after any recalculation triggered by a **Company Holiday** change or a **Leave Policy** change (`FR-06`, `FR-10`). Reserve, consume, and release are atomic. Where two conflicting transitions race, the first to commit wins and the second fails on the changed state. *(Non-negativity originates in `FR-08`; atomicity and the concurrent-double-submission guarantee in NFR-07; first-committed-wins is a confirmed engineering decision, 2026-07-10.)*

### 5.3 Leave year boundary

- **DR-6.** A **Leave Request** may not span two **Leave Years**. The **Employee** submits one request per Leave Year. *(BR-04. The boundary is 31 December, per DR-8.)*
- **DR-7.** At the Leave Year boundary, unused **Accrued** days of a **Leave Type** whose *carries-forward* attribute is true are carried forward, up to that Leave Type's configured **Carry-Forward Cap**; **Accrued** days above the cap **Lapse**. Unused **Accrued** days of a Leave Type whose *carries-forward* attribute is false **Lapse**. EL carries forward; CL and FL lapse. *(BR-01, BR-03; cap and above-cap lapse are Admin-configured and confirmed decisions.)*

  **"Unused Accrued days" means Available** — `Accrued − Consumed − Reserved` — measured whenever the value is computed, not at the boundary alone. Because a **Pending** **Leave Request**'s **Reserved** days survive the boundary (`DR-7a`), **Carry-Forward** is recomputed whenever the closing **Leave Year**'s balance changes. It may therefore *increase* after the boundary, when such a request is rejected or cancelled. No **Leave Request** state transition ever decreases it. *(Confirmed decision. Without this reading, `DR-7` and `DR-7a` are jointly under-determined: counting **Reserved** days as unused double-counts a request later approved, and excluding them silently lapses a request later rejected.)*
- **DR-7a.** **Reserved** days held by a **Pending** **Leave Request** do not lapse at the **Leave Year** boundary. They remain reserved against the **Leave Year** the request belongs to until it is approved, rejected, or cancelled. Their eventual resolution changes **Available** for that Leave Year, and therefore changes that year's **Carry-Forward** (`DR-7`). *(Confirmed decision. `BR-04` prevents a request from spanning two Leave Years; it does not govern a request that remains Pending across the boundary.)*
- **DR-8.** The **Leave Year** is the calendar year, 1 January to 31 December. *(Confirmed decision. Formerly the assumption `A-09`, and formerly the highest-consequence unknown in this document.)*

### 5.4 Entitlement

- **DR-9.** An **Employee** joining mid-**Leave-Year** receives a **Prorated** **Accrued** balance of `Annual Entitlement × (remaining months ÷ 12)`, counting the joining month through December inclusive, rounded **down** to a whole **Leave Day**. *(BR-02; entitlement, monthly basis, and round-down confirmed.)*
- **DR-10.** A **Leave Day** is a whole number. Fractional leave is not expressible. *(Confirmed decision: half-day leave is not supported.)*
- **DR-11.** **Annual Entitlement**, **Carry-Forward**, **Carry-Forward Cap**, and **Supporting-Document** requirements are attributes of a **Leave Type**, stored as data and read at runtime. No cap value and no entitlement value is fixed in code. Adding a **Leave Type** requires no code change. *(D-04, NFR-14)*

### 5.5 Authority

- **DR-12.** A **Manager**'s authority over a **Leave Request** derives from the **Direct Report** relationship to its applicant, not from holding the Manager role. The relationship is evaluated **at decision time**: if an applicant's Manager changes while their request is **Pending**, the current Manager decides it. Authorization is data-scoped, and the scope is applied in the query. *(D-03, NFR-04; decision-time evaluation confirmed.)*
- **DR-13.** An **Admin** may read every **Leave Request** and approve none. The Admin decides **Cancellation Requests** (`DR-14`), which is not approval of leave. Full read access to the audit log is the Admin's alone. *(FR-03, specification; audit read scope confirmed.)*
- **DR-14.** **Approved** is not terminal. An **Employee** may raise a **Cancellation Request** — a separate entity with its own **Pending**/**Approved**/**Rejected** lifecycle — against their own **Approved** **Leave Request**. An **Admin** decides it. The Leave Request remains **Approved** while that decision is pending; only an approved Cancellation Request moves it to **Cancelled**, releasing its **Consumed** days and restoring **Available**. Leave whose dates have already passed cannot be cancelled. *(Confirmed decision, reversing `D-07` and making `BR-05` reachable.)*
- **DR-15.** Overlapping leave among a **Manager**'s **Direct Reports** is permitted without restriction. The system informs; it never blocks. *(BR-06)*
- **DR-16.** Every **Leave Request** state transition writes exactly one append-only **Audit Entry** naming actor and timestamp. A transition caused by the system rather than a person records the actor `SYSTEM` and an explicit reason. *(FR-16 requires every transition to be recorded and the record to be append-only; NFR-09 and NFR-19 add append-only enforcement and actor attribution. The strict one-to-one count is this PRD's explicit reading of "every transition is recorded", stated so that `SM-4` is testable.)*

## 6. Non-Goals (Explicit)

LeaveFlow is not an HRMS and will not become one. The governing exclusion is the BRD's, and it is broader than any list: **any feature not named in the specification is out of scope.** The items below are the ones worth naming explicitly, because a reader could otherwise assume them. Specifically, LeaveFlow does not and will not, in v1:

- **Integrate with payroll or produce a loss-of-pay figure.** No number this system computes is an input to compensation.
- **Encash leave.** Neither at the **Leave Year** boundary nor on separation. A confirmed scope decision.

  **Known production limitation.** Earned Leave above the configured **Carry-Forward Cap** lapses (`DR-7`). Indian statute generally requires earned leave above a cap to be *encashed rather than forfeited*, and accrued EL to be encashed on separation. Because encashment is out of scope, this system forfeits days that a compliant production deployment would have to pay out. This is accepted for a trainee project and recorded as a limitation, not designed around. A production deployment must address it before use.
- **Track attendance or working time.** LeaveFlow knows when an **Employee** is *approved to be absent*, not when they were present.
- **Support any role beyond Employee, Manager, and Admin.** No HR partner, no executive viewer, no delegated approver, no second approver, no escalation on manager inaction.
- **Model more than one organization within a deployment.** LeaveFlow is single-organization-per-deployment. Serving a second organization means a second deployment with its own database, not a tenancy model in the schema.
- **Model leave in units smaller than a day.** No half-days, no hourly leave.
- **Support unpaid leave or leave beyond an exhausted balance.** A request exceeding **Available** is refused, not converted to loss-of-pay.
- **Vary the holiday calendar** by location or **Department**, or the weekend by **Employee**.
- **Send email.** See `FR-14`.
- **Manage a password beyond setting it once.** An **Admin** supplies an **Employee**'s initial password when creating them (`FR-04`), and communicates it outside LeaveFlow. There is no password change, no self-service reset, no forgot-password flow, no **Admin** re-issue, no forced change on first login, and no periodic expiry. No password complexity or minimum-length policy is imposed. *(Adding no capability here is the point: `FR-01` presumed a credential existed and `FR-04` never created one, so the Admin-supplied initial password is the smallest fact that makes the two jointly implementable — not a feature, and therefore not a breach of the governing exclusion above.)*

  **Known production limitation.** Four consequences follow, and none is designed around.
  - An **Employee** who forgets their password cannot regain access. No recovery path exists.
  - The lockout is **permanent within LeaveFlow**. `FR-04` forbids deleting an Employee, so their row and their unique **Email Address** persist indefinitely and the address is never reusable — deactivating and re-creating them does not restore access. `FR-04`'s guards may refuse the deactivation in any case, and no endpoint reverses one.
  - **Attribution is to an account, not to a person.** The **Admin** knows every **Employee**'s password at creation and it is never rotated. `FR-16` and `NFR-19` guarantee that every **Leave Request** transition names an actor and a moment; they cannot guarantee that the named **Employee** is who acted. §1's promise holds for accounts.
  - A compromised credential cannot be revoked except by deactivation, which is refusable, irreversible, and burns the **Email Address**.

  Accepted for a trainee project, and recorded rather than solved. A production deployment must address it before use.
- **Achieve high availability, horizontal scalability, internationalization, or formal WCAG conformance.** Explicitly not required by Module 1's NFR set, and not pursued.

## 7. MVP Scope

The implementation budget is three days (Days 3–5 of a seven-day plan). Twenty functional requirements do not fit three days at equal depth, and pretending otherwise would push the compromise into the code rather than into this document. The phasing below is a *build order and a depth allocation*, not a set of deletions: every FR in the specification appears, and the ones that carry the product's correctness claim are funded first.

**The risk this phasing carries:** anything scheduled last is what fails to exist when the budget runs out. Phase 3 (`FR-13`, `FR-15`) is therefore the part of the specification most likely to go undelivered, and calling it "in scope" does not make it safe. `SM-8` requires all twenty requirements delivered; if Phase 3 does not land, `SM-8` is missed and the shortfall is reported as a missed target, not reclassified after the fact as a deferral that was always intended. The order is chosen because a system with untrustworthy balances and complete CSV export is worth less than the reverse — not because Phase 3 is optional.

### 7.1 In Scope — Phase 1 (the correctness core)

The system is not defensible without these, because they are where being wrong is expensive.

- `FR-01`, `FR-02`, `FR-03` — authentication, token authorization, data-scoped RBAC.
- `FR-04`, `FR-05`, `FR-17` — employees, departments, own-profile.
- `FR-06`, `FR-10` — leave types as configuration; holiday calendar. *(Prerequisites: `FR-08` cannot count **Leave Days** without holidays, and `FR-07` cannot roll over without type attributes.)*
- `FR-07` — the three-quantity balance, proration, carry-forward, lapse.
- `FR-08`, `FR-09` — request submission and the four-state lifecycle with reserve/consume/release.
- `FR-16` — audit entries on every transition.

### 7.2 In Scope — Phase 2 (the product becomes usable)

- `FR-11` — dashboards: summary cards with date-range filtering.
- `FR-18` — department leave calendar, inline on the approval screen. *(Without it, `BR-06` degrades from an informed choice to an unnoticed one.)*
- `FR-12` — filtering and bounded pagination.
- `FR-14` — in-app notifications.
- `FR-19`, `FR-20` — team member list; leave history.

### 7.3 In Scope — Phase 3 (completes specification coverage)

- `FR-13` — supporting document upload.
- `FR-15` — CSV export.

**Resolved.** A gap opens between the phases: `FR-06` (Phase 1) lets an **Admin** mark a **Leave Type** as requiring a **Supporting Document**, but the rule that such a request cannot be submitted without one is enforced by `FR-13`, in Phase 3. No source document specified the seed value. It is now a project decision: **EL**, **CL** and **FL** are seeded with *requires-supporting-document* **false** (`FR-06`), so no document-requiring Leave Type exists before `FR-13` lands. An **Admin** who sets the attribute true before Phase 3 creates a Leave Type whose document requirement is configurable but unenforced — a deliberate act, not a latent gap.

### 7.4 Out of Scope for MVP

- **Email notification delivery.** `FR-14` ships in-app only; the SMTP cost and the table-stakes argument are given in §4.7. `[NOTE FOR PM: the deferral most likely to be challenged by a reviewer who knows the domain.]`
- **PDF export.** `FR-15` ships CSV. PDF is a materially larger dependency.
- **Charted dashboard analytics.** `FR-11` ships summary cards with date-range filtering, which is the agreed scope. Charts and trend lines are not built.
- **Leave encashment.** A confirmed scope decision, not an omission. The compliance limitation it leaves is recorded in §6.
- **Multi-tenancy within a deployment.** A second organization means a second deployment.

## 8. Cross-Cutting Non-Functional Requirements

*Carried from the Module 1 NFR set. The subset below is the one that constrains this PRD's requirements; the full register of twenty-one lives in Module 1, and `NFR-19` (every transition records who and when), cited by `DR-16`, is among those not restated here.*

**A standing risk.** All twenty-one non-functional requirements are engineer-proposed. None has been confirmed by the assigning manager, and whether any will be evaluated is unknown. Everything downstream that cites an NFR therefore rests on unconfirmed ground. `NFR-03`, `NFR-04`, `NFR-07`, and `NFR-08` are the four this PRD funds most heavily, on the judgment that they are the ones a technical discussion would probe. That alignment is deliberate and unverified.

**Security**
- `NFR-01` Credentials are stored as salted hashes (bcrypt or Argon2). No reversible representation exists.
- `NFR-02` Token lifetime is measured in hours, not days, absent a refresh mechanism.
- `NFR-03` Authorization is enforced server-side, at the API boundary.
- `NFR-04` Data scoping is applied in the query, not by post-filtering retrieved rows.
- `NFR-05` Uploads are validated for type and size, stored outside the web root; client filenames are never trusted as paths.
- `NFR-06` Credentials and tokens travel over TLS in any deployed environment.
- `NFR-20` Secrets, database credentials, and signing keys come from the environment. None are committed.

**Correctness and reliability**
- `NFR-07` Reserve, consume, and release are transactional. A concurrent double submission produces neither a negative nor a double-counted balance.
- `NFR-08` The leave-day calculation is a single, pure, unit-tested function (`DR-2`).
- `NFR-09` **Audit Entries** are append-only.
- `NFR-15` The hard rules carry tests: proration, carry-forward, the **Leave Year** boundary, the day count, and authorization scope.

**Performance**
- `NFR-10` Read endpoints respond within roughly 500 ms at the data scale of this project. An order of magnitude, not a contractual figure.
- `NFR-11` Result sets are bounded by a server-enforced maximum page size.
- `NFR-12` Indexed access paths exist for employee, manager, department, leave year, and request state.

**Maintainability and operability**
- `NFR-13` Routes, business logic, and data access are separated; policy lives in the service layer.
- `NFR-14` Adding a **Leave Type** requires no code change (`DR-11`).
- `NFR-21` Setup is reproducible from a documented command sequence on a clean machine.

**Usability**
- `NFR-16` A control a role cannot invoke is not rendered for that role. This is a usability measure, not a security measure; `NFR-03` is the security measure.
- `NFR-17` Errors state the reason. "Insufficient balance" names days requested and days available; "spans two leave years" names the boundary.
- `NFR-18` Layout is responsive across desktop and tablet widths.

## 9. Constraints and Guardrails

**Imposed by the assigning manager**
- Seven days total. Days 1, 2, 6, and 7 produce artifacts; **Days 3–5 are the only days allocated to application code.**
- The BMAD lifecycle is followed and its artifacts produced. Process artifacts take precedence over feature count wherever the two compete for time.
- Technology was selected from a bounded set of offered options.

**Imposed by the specification**
- Exactly three roles. No additions.
- Eighteen enumerated functional requirements as a coverage floor, plus `FR-19` and `FR-20` covering role permissions the specification grants but the enumerated list omitted.
- A **Manager**'s authority extends to **Direct Reports** only.
- The **Admin** owns **Leave Policy** configuration and holds no approval authority.
- Web-based delivery.
- One organization per deployment. Multi-tenancy within a deployment is not modelled; a second organization is served by a second deployment with its own database.

**Chosen, and defensible**
- **FastAPI** for the backend (`D-05`): typed models and generated OpenAPI serve the API-documentation deliverable directly.
- **React** for the frontend (`D-06`): existing familiarity conserves days that the schedule does not have to spare.

**Guardrail on this document**
- LeaveFlow's purpose is to practise the full lifecycle, not to ship into a market. Where feature breadth and demonstrable correctness compete, correctness wins. A requirement that cannot be stated with a testable consequence is a requirement that is not yet understood.

## 10. Success Metrics

All twenty functional requirements must be delivered, and delivery is tracked (`SM-8`). But coverage is a necessary condition, not a sufficient one: twenty requirements marked complete is evidence that the work was done, not evidence that it was done correctly. The primary metrics below measure whether the system is *right where being right is hard*, and whether its reasoning survives inspection — which is what this project is for.

**Primary**

- **SM-1 — Balance arithmetic is internally consistent.** `Available = Accrued − Consumed − Reserved` and `Available ≥ 0` after every **Leave Request** state transition, including under concurrent submission. Target: a property test over randomized transition sequences finds zero violations, and a concurrent double-submit test produces neither a negative nor a double-counted balance. Validates `FR-07`, `FR-08`, `FR-09`, `DR-3`, `DR-5`.

  **What this metric does not establish.** It tests that the arithmetic is consistent, not that the balance is *right*. With the **Leave Year**, the **Annual Entitlement**, and the **Proration** basis all settled, the inputs `SM-1` depends on are now defined rather than assumed — but consistency and correctness remain different properties, and only `SM-2` and the proration tests required by `NFR-15` establish the second.
- **SM-2 — The day count is right at the boundaries.** Target: unit tests over the **Leave Day** function pass for a range containing a weekend, a range containing a **Company Holiday**, a range beginning and ending on non-**Working Days**, and a single-day range. A range consisting entirely of non-Working Days yields zero **Leave Days** and its submission is refused (`FR-08`). Validates `FR-08`, `DR-1`, `DR-2`.
- **SM-3 — Authorization is scoped to data, not to role.** Target: for every endpoint accepting a **Leave Request** identifier, an authenticated **Manager** who is not the applicant's **Manager** receives the same response as for a nonexistent request. Zero endpoints authorize on role name alone. Validates `FR-03`, `DR-12`.
- **SM-4 — Every leave action is attributable.** Target: **Audit Entry** count equals state-transition count, one-to-one, across the full test suite; each entry names an actor and a timestamp. Zero application code paths update or delete one. Validates `FR-16`, `DR-16`.

**Secondary**

- **SM-5 — Policy is data.** Target: a fourth **Leave Type** is added through configuration, is applied for, reserved, approved, and rolled over at the **Leave Year** boundary, with no code change and no schema migration. Validates `FR-06`, `DR-11`. *Now fully testable: a Leave Type carries an **Annual Entitlement** (`FR-06`), so a fourth type has a quantity to accrue and roll over.*
- **SM-6 — Decisions are traceable in both directions.** Target: every FR in this document resolves to a decision recorded in the brief, the BRD, or the run memlog — checkable, and checked. In the reverse direction, every module in the codebase names the FR or DR it implements. *This reverse direction is verified by review, not by a test; "every non-obvious choice" has no machine-enumerable denominator, and claiming otherwise would be the kind of unfalsifiable target `SM-C1` warns against.* A reader who disagrees with a decision can find where it was made and on what basis.
- **SM-7 — Assumptions are visible, not buried.** Target: every `[ASSUMPTION]` inline in this document appears in §12, and every §12 entry appears inline. At finalization the count on both sides is zero — every assumption was resolved rather than shipped — and §12 records what each became. The metric holds trivially, but the discipline it enforces is what produced that result.
- **SM-8 — Requirement coverage.** Target: all twenty functional requirements `FR-01`–`FR-20` are delivered, each with at least one passing test exercising a stated testable consequence. Tracked per requirement, per phase (§7). A requirement is counted as delivered only when a consequence from its FR is demonstrably exercised — not when its endpoint exists. With `FR-19` and `FR-20` added, every permission the specification grants now traces to a requirement, so coverage of the twenty requirements is coverage of the specification.
- **SM-9 — Every lifecycle stage produced its artifact.** Target: the BRD, PRD, ERD, architecture and flow diagrams, API contracts, test plan, code review report, prompt library, and retrospective all exist, and each traces to the decisions that shaped it. Carried directly from the brief, which defines success as "the requirements are covered, **and** every lifecycle stage has produced its artifact." `SM-8` measures the first clause; this measures the second. Without it, the PRD would omit half of the project's own stated definition of success — the half that makes this a lifecycle exercise rather than a shipping exercise.

**Counter-metrics (do not optimize)**

- **SM-C1 — Coverage percentage read in isolation.** `SM-8` is a real target and must reach 100%; what must not be optimized is coverage *at the expense of* `SM-1`–`SM-4`. Twenty requirements shipped shallowly — `FR-07`'s proration untested, `FR-03`'s scoping enforced by role name rather than by the reporting relationship — would report full coverage and still be a system whose balances cannot be trusted. Coverage is the evidence that the work exists; the primary metrics are the evidence that it is correct. Counterbalances `SM-8`: when the two compete for the last hours of the implementation budget, correctness wins, and the shortfall is declared.
- **SM-C2 — Dashboard and report richness.** Charts are the cheapest way to look finished and the least defensible under questioning. Counterbalances `FR-11` and `FR-15`.
- **SM-C3 — Volume of documentation.** Length is not rigor. An artifact that restates the specification back to itself has produced nothing. Counterbalances `SM-6` and `SM-7`.

## 11. Open Questions

**None.** No open question blocks implementation, no assumption remains anywhere in this document, and no requirement carries an undefined term. Every product decision this PRD depends on has been made, recorded, and traced to the requirement it governs.

This section is retained rather than deleted, because a PRD with no open questions is a claim, and the claim should be visible where a reader looks for it. What follows is not an evasion of that claim; it is the boundary of it.

### Accepted limitation, not an open question

- **Earned Leave above the Carry-Forward Cap lapses** (`DR-7`), and **encashment is out of scope** (§6). Indian statute generally requires earned leave above a cap to be encashed rather than forfeited. This system forfeits it. Accepted for a trainee project, recorded in §6 as a production limitation, and **not** designed around. A production deployment must address it before use.

### Decided here, modelled by Architecture

The PRD fixes the behavior; Module 3 chooses the shape. None of these is an open product question.

- **`Cancellation Request` is a separate entity** with its own **Pending**/**Approved**/**Rejected** lifecycle, not a status on the **Leave Request** (`DR-14`). A cancellation writes **Audit Entries** for both objects.
- **A `Leave Date` is a calendar `DATE`**, never a UTC timestamp (`DR-2a`).
- **The Leave Year rollover is a system-triggered scheduled process** (`FR-07`), recorded in its own append-only rollover log rather than among **Audit Entries**, because it transitions no **Leave Request**. *Idempotence is settled:* the rollover assigns derived values rather than accumulating them, so a second run against the same **Leave Year** is a no-op.
- **Full audit-log read access belongs to the Admin alone** (`FR-16`, `DR-13`). The endpoint shape is Architecture's.
- **`FR-14`'s mark-read transition** is now stated as a testable consequence of `FR-14` itself. The absence recorded in [addendum §3.2a](addendum.md) is closed.

### Edge cases: decided, not deferred

The adversarial edge-case review surfaced twenty-five undetermined cases. The ones that would have bitten during implementation are now decided in the text: authority binds at **decision time** (`DR-12`); reversed and wholly-past date ranges are refused (`FR-08`); zero-working-day requests are refused (`FR-08`); racing transitions resolve first-committed-wins (`FR-09`, `DR-5`); a managerless auto-approval names `SYSTEM` as its actor (`FR-16`); deactivation preserves history, is blocked by one's own **Pending** requests, and is blocked for a **Manager** who still has **Direct Reports** (`FR-04`); and holiday-calendar changes recalculate **Pending** and future **Approved** requests, never past-dated leave, and are refused where they would drive a balance negative (`FR-10`). The remainder of `review-edge-cases.md` is Architecture's input.


## 12. Assumptions Index

**This document contains no assumptions.** Every inference it once carried has been confirmed as a project decision, and the `[ASSUMPTION]` tag appears nowhere in the text. That is unusual for a PRD and worth stating plainly: nothing below the Vision rests on a guess.

The nine assumptions Module 1 recorded were resolved as follows. Their identifiers are retired rather than reused, so Module 1's register still resolves.

| Was | Now |
| --- | --- |
| `A-01` half-day leave out of scope | **Decision.** Half-day leave is not supported; a **Leave Day** is a whole number. |
| `A-02` Sat/Sun are the weekend | **Decision.** Saturday and Sunday are non-working days for every **Employee**. |
| `A-03` holidays are global | **Decision.** **Company Holidays** are global to the organization. |
| `A-04` FL denotes Floater Leave | **Decision.** FL is Floater Leave. |
| `A-05` entitlement accrues in some form | **Withdrawn** — it assumed no value. Superseded by the **Annual Entitlement** attribute (`FR-06`) and the monthly proration rule (`DR-9`). |
| `A-06` a single approval step suffices | **Decision.** Approval is single-step. A managerless **Employee**'s request is auto-approved by `SYSTEM` (`FR-09`). |
| `A-07` the organization is single-tenant | **Decision.** One organization per deployment. Multi-tenancy within a deployment is out of scope. |
| `A-08` policy is not changed mid-year | **Decision superseding the assumption.** Policy may change; the **Admin** decides explicitly whether existing balances are recalculated (`FR-06`). |
| `A-09` the Leave Year is the calendar year | **Decision.** 1 January to 31 December. Once the highest-consequence unknown in this document. |


---

*Companion artifacts for this run live alongside this document: [addendum.md](addendum.md) records rejected alternatives, research grounding, and material bound for Architecture; `.memlog.md` is the append-only decision log.*
