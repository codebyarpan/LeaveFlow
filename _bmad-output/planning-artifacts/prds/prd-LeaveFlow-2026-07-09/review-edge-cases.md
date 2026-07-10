---
title: "LeaveFlow PRD — Edge-Case Review (unhandled cases only)"
status: draft
created: 2026-07-09
method: branching-path and boundary-condition walk; reports only cases the PRD's rules, read literally, do not determine
---

# LeaveFlow PRD — Unhandled Edge Cases

**Scope of this document.** This is a method-driven walk of every branching path and boundary condition in the PRD's specified behavior (`prd.md`) and its addendum. It reports **only** places where the PRD's rules, read literally, fail to determine what the system should do. It proposes no requirements, rules, assumptions, or invariants, and it does not decide what the behavior should be. Where the PRD already flags a gap as an Open Question, that is noted rather than claimed as new.

Each entry states the concrete scenario, quotes the PRD rule that fails to determine the outcome, names the consequence, and rates whether it would bite during the 3-day implementation window (§9: Days 3–5).

**Convention.** `NEW` = newly surfaced here. `FLAGGED` = already an Open Question or Out-of-Scope note in the PRD.

---

## 0. Cases checked and found *determined* (not reported below)

To show the method covered them: the following (state, actor, action) pairs from the brief are **determined** by the closed-world state-machine table (§4.5) plus `FR-09`/`DR-14`, and are therefore **not** unhandled:

- **Approve an already-Approved request** — `FR-09`: "No actor can transition a request out of Approved. No endpoint offers the transition." Determined: refused / no endpoint.
- **Cancel a Rejected request** — `FR-09`: "Only the applicant can cancel, and only while **Pending**." Rejected is not Pending; determined: refused.
- **Two concurrent submissions exceeding Available** — `FR-08` ("Two concurrent submissions that would together exceed **Available** cannot both succeed") + `NFR-07`/`DR-5`. Determined.
- **A different Manager or an Admin approving** — `FR-09`/`DR-13`. Determined: refused.
- **Pagination widening authorization** — `FR-12`: "Filtering never widens authorization." Determined (residual reassignment interaction is folded into S-2 below).

---

## 1. State machine (§4.5)

### S-1. Concurrent approve (Manager) vs cancel (Employee) out of Pending — winner undetermined `NEW`
**Scenario.** A request is Pending. The applicant's Manager submits Pending→Approved at the same instant the applicant submits Pending→Cancelled. Both are legal transitions from Pending per the §4.5 table.
**Rule that fails.** `DR-5`: "`Available ≥ 0` is an invariant… Reserve, consume, and release are atomic." `NFR-07`: "Reserve, consume, and release are transactional." These constrain the **balance arithmetic** (no negative, no double-count) but say nothing about **which of two competing valid state transitions wins**, or what the losing actor sees. The §4.5 table lists both transitions as legal from Pending and does not order them.
**Consequence.** Undefined tie-break: a request could end Approved with a Consume even though the employee cancelled, or Cancelled after the manager believed they approved; `FR-16`/`DR-16` ("exactly one Audit Entry" per transition) is ambiguous if both fire. The balance may stay correct while the *state* and *audit trail* are wrong.
**Bite: HIGH.** The developer must choose a locking/ordering discipline the moment both endpoints touch one row; the PRD gives the balance rule but not the transition rule.

### S-2. Applicant's Manager reassigned while a request is Pending — approver binding undetermined `NEW`
**Scenario.** Employee submits (Pending). Before a decision, an Admin uses `FR-04` to change the employee's Manager from M1 to M2. Who can now approve — M1 (manager at submission) or M2 (manager now)?
**Rule that fails.** `DR-12`: "A **Manager**'s authority over a **Leave Request** derives from the **Direct Report** relationship to its applicant… the scope is applied in the query." `FR-04`: "Assigning a Manager… establishes the **Direct Report** relationship that `FR-03` enforces." The PRD never fixes **when** that relationship is evaluated for an in-flight Pending request (at submission, latched onto the request; or live at decision time). `NFR-04` ("scope applied in the query") implies live evaluation, which points to M2 — but the request was never surfaced to M2, and M1 holds it in queue.
**Consequence.** Either the request is orphaned (M1 loses authority, M2 never saw it) or authority silently transfers mid-flight. Ties directly to N-2 (notification) and P-1 (queue scoping).
**Bite: HIGH.** Manager reassignment is a first-class Admin action (`FR-04`); the query scope is written on Day 3–5 and must resolve this.

### S-3. Applicant deactivated (FR-04) while a request is Pending `NEW`
**Scenario.** Employee has a Pending request; Admin deactivates the employee.
**Rule that fails.** `FR-04`: "Deactivating an Employee preserves their **Leave Requests**, **Leave Balances**, and **Audit Entries**" and "A deactivated Employee cannot authenticate." It preserves the record but does **not** state whether the Pending request stays Pending, whether its **Reserved** days are released, or whether the Manager may still approve/reject it. `FR-09` still permits the Manager to decide "while it is **Pending**."
**Consequence.** Undefined: a deactivated employee could be Approved into Consumed leave they can no longer take; or Reserved days sit locked against a balance no one can spend; or the request is stranded. The employee can no longer cancel (cannot authenticate), removing one of the two Pending exits.
**Bite: MEDIUM.** Deactivation is core `FR-04`; the interaction with in-flight requests is not scripted.

### S-4. Applicant's Manager deactivated while a report's request is Pending `NEW`
**Scenario.** M is the only Manager of employee E; E has a Pending request; Admin deactivates M.
**Rule that fails.** `FR-04`: "A deactivated Employee cannot authenticate" (a Manager is an Employee, per Glossary). `FR-09`: "Only the applicant's **Manager** can approve or reject." §2.2 `A-06`: "no delegation, no escalation, no second approver." With M unable to authenticate and no delegation path, no actor can decide E's Pending request.
**Consequence.** The request is permanently stuck in Pending; its Reserved days never release. The PRD determines that *nobody else* may act (`A-06`) but not what happens to the stranded request.
**Bite: MEDIUM.** Reachable through ordinary Admin lifecycle actions.

### S-5. No modify/edit transition exists for a Pending request `NEW`
**Scenario.** An employee wants to change the dates or leave type of a request that is still Pending.
**Rule that fails.** The §4.5 table defines exactly four transitions; none is "edit/amend." `UJ-1` describes only "He can cancel it himself while it remains Pending." No FR defines editing a Pending request or recomputing its **Reserved** days on edit.
**Consequence.** Undefined whether amendment is possible at all, and if attempted, whether/how the reservation recalculates. Read literally, editing simply does not exist — but the PRD never says so, so the boundary is undetermined rather than closed.
**Bite: LOW–MEDIUM.**

---

## 2. Balance arithmetic

### B-1. Admin lowering an individual's Accrued below current Consumed + Reserved `NEW`
**Scenario.** An employee has Accrued 10, Consumed 6, Reserved 2 (Available 2). An Admin sets Accrued to 5.
**Rule that fails.** `DR-5`: "`Available ≥ 0` is an invariant. It holds after every **transition** … Reserve, consume, and release are atomic." The invariant is scoped to **Leave Request state transitions**. An Admin editing Accrued is **not** a request transition, so `DR-5`'s literal guarantee does not cover it. Separately, **no FR grants the Admin the ability to edit Accrued directly**: `FR-04` enumerates "**Department**, role, joining date, and **Manager**," not balance quantities; `FR-17` only says the *employee* cannot edit balances. Whether the Admin can set Accrued at all is undefined, and if they can, whether Available may go negative is undefined.
**Consequence.** Either a needed capability is missing, or an Admin edit can drive Available negative — the exact "wrong balance that is believed" failure §1 exists to prevent — without violating `DR-5` as literally written.
**Bite: MEDIUM.** Depends on whether balance-editing is implemented; the PRD does not settle that it is.

### B-2. Reserved days on a still-Pending request at the Leave-Year rollover boundary `NEW`
**Scenario.** Employee has a Pending request for late-December dates; it is still Pending at 00:00 on 1 January. Its **Leave Days** are Reserved against the old year's balance.
**Rule that fails.** `DR-7`: "At the Leave Year boundary, unused **Accrued** days … carry forward … or **Lapse**." The rule operates on **Accrued** only and is silent on **Reserved**. `Glossary`: "**Reserved** — Leave Days committed to **Pending** Leave Requests and not yet **Consumed**." Nothing states whether Reserved days on a Pending request survive rollover, are lapsed with the Accrued they sit against (for CL/FL), or migrate.
**Consequence.** For CL/FL (which lapse), it is undetermined whether the reservation lapses out from under a live Pending request, and whether the derived `Available = Accrued − Consumed − Reserved` is even computable if Accrued was lapsed while Reserved remained. Open Question 1 flags the boundary *date* but not this Reserved-survival question.
**Bite: HIGH.** The rollover routine is Phase-1 `FR-07` and must decide it.

### B-3. December-dated Pending request approved in January — which Leave-Year balance is consumed `NEW`
**Scenario.** Continuing B-2: the Manager approves in January a request whose dates are in December.
**Rule that fails.** `DR-3`: balance is stored "per **Employee**, per **Leave Type**, per **Leave Year**." The approving transition (`DR-4`: "Approving consumes them") must Consume from *a* Leave-Year balance row, but the PRD does not say whether it consumes from the year of the request's **dates** (old) or the year of the **decision** (new). `DR-6` guarantees a request does not span years, but not which year's row a cross-boundary decision hits.
**Consequence.** Consume could land on the wrong year's balance row, or on a row whose Accrued already lapsed. Silent balance corruption at exactly the year boundary the product markets itself on.
**Bite: MEDIUM–HIGH.**

### B-4. Admin changes a Leave Type's carry-forward attribute after rollover has run `FLAGGED (Open Question 5 / A-08)`
**Scenario.** Rollover fires on 1 January using EL's carries-forward = true. On 5 January the Admin flips EL's carries-forward attribute.
**Rule that fails.** `FR-06` permits changing the attribute; Open Question 5 already states: "The specification permits an **Admin** to reconfigure a **Leave Type** and is silent on employees who accrued under the prior policy. `FR-06` as specified allows the change; nothing defines its effect." The *after-rollover* timing sharpens it (the boundary event already consumed the old attribute value) but is subsumed by OQ5's stated gap.
**Consequence.** Undetermined whether the already-executed rollover is re-run, reversed, or left. Already flagged.
**Bite: LOW** within a 3-day build (rollover is a one-shot boundary event unlikely to be re-triggered in the window).

---

## 3. Day count (DR-1, DR-2)

### D-1. Date range containing zero Working Days `FLAGGED (Open Question 6; FR-08 Out of Scope)`
**Scenario.** A range consisting only of weekend days and/or Company Holidays → 0 Leave Days.
**Rule that fails.** `FR-08` Out of Scope: "Leave requests that resolve to zero **Leave Days** — see §11; the system's behavior for a range containing no Working Days is undecided." Open Question 6 restates it.
**Confirmation it is genuinely unhandled: yes.** Explicitly declared undecided in two places.
**Downstream consequences (per brief).** A 0-day request trivially passes the `FR-08` balance check (0 ≤ Available always), Reserves 0 days, and if approved Consumes 0 — creating an Approved absence that costs nothing and against which `DR-15` overlap visibility and `FR-18` calendar display must still render. It also interacts with `FR-13` (a 0-day request could still require a Supporting Document) and with `SM-2`, which *lists* "a range consisting entirely of non-Working Days" as a required day-count test while §11 leaves the *request-acceptance* behavior undecided — the count is defined (0) but acceptance is not.
**Bite: MEDIUM.** The count function must return something; acceptance policy is undecided.

### D-2. Single-day range on a Company Holiday `FLAGGED (sub-case of Open Question 6)`
**Scenario.** A one-day request whose single date is a Company Holiday → 0 Working Days.
**Rule that fails.** Same as D-1. `SM-2` requires a passing test for "a single-day range" and separately for "a range consisting entirely of non-Working Days"; their intersection (single day that is itself a holiday) is a 0-day request whose acceptance is undecided.
**Bite: MEDIUM.**

### D-3. Start date after end date `NEW`
**Scenario.** An employee submits a request whose start date is later than its end date.
**Rule that fails.** `DR-1`: "the number of **Working Days** it contains" and `FR-08`: "a contiguous date range." Neither defines validity or the count for a reversed range. "Contiguous" does not state direction.
**Consequence.** Undefined: refuse, silently swap, or count as zero/negative. A negative or empty span could bypass the Available check.
**Bite: MEDIUM–HIGH.** Basic input the day-count function meets immediately; PRD gives no rule.

### D-4. Start date in the past `NEW`
**Scenario.** An employee submits leave for dates that have already passed.
**Rule that fails.** No FR or DR constrains leave dates to the present or future. `FR-08` prices "a contiguous date range" with no temporal floor.
**Consequence.** Undetermined whether backdated leave is accepted; affects `FR-18` calendar, `FR-11` "on approved leave today," and audit meaning.
**Bite: LOW–MEDIUM.**

### D-5. Company Holiday added inside an already-Approved range `FLAGGED (Open Question 7)`
**Scenario.** Admin adds a holiday inside the dates of an Approved (Consumed) request.
**Rule that fails.** Open Question 7 verbatim: "Recalculating mutates a terminal state and contradicts `DR-14`'s spirit; not recalculating leaves **Consumed** days that the day-count function would no longer produce. **This is an open question, not an adopted simplification.**"
**Bite: LOW** in-window (requires an Admin holiday edit against an existing Approved request).

### D-6. Company Holiday *deleted* from inside an Approved (or Pending) range `NEW`
**Scenario.** A holiday previously counted-out of an Approved (or Pending) request is deleted by the Admin, so the range now contains one more Working Day than when the request was priced.
**Rule that fails.** `FR-10` says an Admin "can maintain the **Company Holiday** calendar" but its consequences enumerate only *recording* a holiday; deletion's effect on existing requests is never stated. Open Question 7 addresses only holidays **added** ("declared after approval") — deletion is the symmetric case and is **not** covered. `DR-14` (Approved terminal) makes recalculating a Consumed request contradictory, exactly as in OQ7, but for deletion the PRD has raised no question at all.
**Consequence.** Undetermined whether Consumed (or Reserved) days are recomputed upward; if not, the day-count function would now produce a *higher* number than the stored Consumed/Reserved — a silent under-charge, the mirror of OQ7's over-charge. `FR-10` does not even explicitly grant delete, so its very availability is ambiguous.
**Bite: MEDIUM.** Newly surfaced and symmetric to a rule the PRD already worried about.

### D-7. Holiday added or deleted inside a *Pending* range — reservation recalculation `NEW`
**Scenario.** A holiday is added to or removed from inside the dates of a still-Pending request whose **Reserved** days were computed at submission.
**Rule that fails.** `DR-4`/`FR-08`: "On admission, the request's **Leave Days** are **Reserved**." The PRD prices at admission and never states whether a Pending reservation is recomputed when the holiday calendar changes underneath it. OQ7 is explicitly about **Approved** requests only.
**Consequence.** A Pending request's Reserved amount can diverge from what `DR-1` would now compute; on approval it Consumes a stale number. `DR-3`'s `Available = Accrued − Consumed − Reserved` then rests on a stale Reserved.
**Bite: MEDIUM.**

---

## 4. Authorization (DR-12, FR-03)

### A-1. Employee with no Manager assigned submits a request — no possible approver `NEW`
**Scenario.** Glossary: an Employee "has **at most one Manager**," so zero is valid. An employee with no Manager submits a request.
**Rule that fails.** `FR-08` lets any Employee submit and reserve; `FR-09`: "Only the applicant's **Manager** can approve or reject." With no Manager, no actor satisfies the approve/reject precondition, and `A-06` forbids any escalation/second approver. `FR-14`: "Submission … creates exactly one **Notification** addressed to the applicant's **Manager**" — the addressee does not exist.
**Consequence.** The request is stuck Pending forever (Reserved days locked), and the mandatory submission Notification has no valid addressee (a null-target / crash path). The PRD permits the state (no manager) and the action (submit) but does not determine the outcome.
**Bite: HIGH.** Reachable on Day 1 of use by anyone at the top of the hierarchy; the submission and notification code hit a null Manager immediately.

### A-2. A Manager who is their own Manager `NEW`
**Scenario.** `FR-04` sets an employee's Manager field; nothing forbids setting it to themselves. That employee then has a self-referential reporting edge.
**Rule that fails.** `DR-12`: authority "derives from the **Direct Report** relationship to its applicant." If the applicant is their own Direct Report, they satisfy their own approval precondition. No FR forbids the self-edge or self-approval.
**Consequence.** Undetermined whether a person can approve their own leave via a self-manager loop — defeating the single-approval control the product exists to enforce.
**Bite: LOW–MEDIUM.**

### A-3. A Manager submitting their own leave request — who approves (the "Manager is an Employee" trace) `NEW`
**Scenario.** Glossary: "A **Manager** is themselves an **Employee** with their own balances and requests." A Manager M submits their own request.
**Rule that fails.** By `DR-12`/`FR-09`, M's request must be decided by *M's own* Manager (M is not their own Direct Report unless self-assigned per A-2). If M has no Manager (e.g., the top of the one-employee-to-one-manager hierarchy), this collapses into A-1: no approver exists. The PRD asserts every Manager is also an Employee with requests, but does not determine the approver for a Manager who has no Manager.
**Consequence.** Top-of-hierarchy Managers (and, plausibly, Admins-who-are-also-Employees) can submit requests that no one is authorized to decide; Reserved days lock permanently. This is the same structural gap as A-1, surfaced specifically along the Manager-as-Employee path the brief calls out.
**Bite: HIGH.**

---

## 5. Department / Employee lifecycle

### L-1. A Department whose only assigned Employees are all deactivated `NEW`
**Scenario.** Admin attempts to remove a Department all of whose Employees have been deactivated (not deleted — `FR-04` preserves them).
**Rule that fails.** `FR-05`/Glossary: "A Department with at least one assigned **Employee** cannot be removed." "Assigned" is not defined to include or exclude **deactivated** Employees, who still hold a Department per `FR-04` ("preserves their … records") and are still members per the Glossary ("An organizational grouping of **Employees**").
**Consequence.** Undetermined whether the Department is removable; the removal-guard's predicate ("has assigned Employees") is ambiguous for deactivated members.
**Bite: LOW–MEDIUM.**

### L-2. Reassigning an Employee's Department (and/or Manager) mid-Pending-request `NEW`
**Scenario.** Admin changes a Pending applicant's Department (which may or may not change the Manager) while a request is Pending.
**Rule that fails.** `FR-04` permits the change; no rule states its effect on an in-flight request. Where the change also moves the Manager, this is S-2. Where only the Department changes, the effect on `FR-18` (Department Leave Calendar visibility of the request) and on `FR-11`/`FR-12` scoping is undefined.
**Consequence.** A Pending request may appear on, or vanish from, calendars/queues mid-decision with no defined rule. Overlaps S-2 for the Manager dimension.
**Bite: MEDIUM** (via the Manager dimension), LOW for Department-only.

---

## 6. File upload (FR-13)

### F-1. Leave Type's requires-document attribute flipped to true while document-less requests are Pending `NEW / partly FLAGGED (OQ5)`
**Scenario.** Requests were submitted while a Leave Type's requires-supporting-document = false, so they carry no document. The Admin flips the attribute to true while those requests are Pending.
**Rule that fails.** `FR-13`: "A Leave Request for a Leave Type configured as requiring a **Supporting Document** cannot be submitted without one" — a **submission-time** check only. Nothing states whether an already-Pending, document-less request is now invalid, or whether approval (`FR-09`) re-checks the document requirement. Open Question 5 covers Leave-Type reconfiguration generally but frames its consequence in terms of **balances** ("existing balances are silently invalidated"), not documents — so the document-requirement retroactive effect is not covered by OQ5's stated consequence.
**Consequence.** Undetermined whether such requests are approvable, blocked, or must be amended (and no amend transition exists — see S-5).
**Bite: LOW–MEDIUM.**

### F-2. Supporting Document on a Cancelled (or Rejected) request `NEW`
**Scenario.** A request with an attached document is Cancelled by the applicant (or Rejected by the Manager).
**Rule that fails.** `FR-13`: "A **Supporting Document** is retrievable by its applicant and by that applicant's **Manager**." The retrieval right is stated with no dependence on request state; nothing says whether the document is retained, deleted, or still retrievable after Cancellation/Rejection.
**Consequence.** Undetermined retention/retrievability of a document attached to a terminated request (a data-lifecycle and, given `NFR-05` storage-outside-web-root, a cleanup gap).
**Bite: LOW.**

---

## 7. Notifications (FR-14)

### N-1. Notification addressee is deactivated `NEW`
**Scenario.** A submission notification is addressed to a Manager who is later deactivated, or a decision notification is addressed to an applicant who was deactivated (S-3).
**Rule that fails.** `FR-14`: "A **Notification** is readable only by its addressee," and `FR-04`: "A deactivated Employee cannot authenticate." A Notification addressed to a deactivated Employee is created but can never be read (its addressee cannot authenticate). The PRD does not state whether such a Notification is still created, suppressed, or redirected.
**Consequence.** Notifications silently sink; unread counts (`FR-14`: "An unread count is retrievable") accrue to an account that can never clear them. Couples with S-4 (deactivated Manager) and A-1 (no Manager → null addressee).
**Bite: LOW–MEDIUM.**

### N-2. Manager reassigned between submission and decision — who is notified `NEW`
**Scenario.** Submission notified M1 (`FR-14`: "addressed to the applicant's **Manager**"). Before the decision, the Manager is changed to M2 (S-2). The decision is made.
**Rule that fails.** `FR-14`: "Submission … creates exactly one **Notification** addressed to the applicant's **Manager**" fired once at submit-time to M1. Nothing states whether M2 receives a submission notification, or whether M1 (who no longer holds authority) is left with a stale queued Notification. `FR-14`'s decision notification goes to the applicant, so that side is determined; the Manager side is not.
**Consequence.** The now-authoritative Manager (M2) may never be notified a decision is pending; overlaps S-2.
**Bite: MEDIUM.**

---

## 8. Pagination / filter (FR-12) interacting with authorization scope

### P-1. Scope-vs-pagination interaction is largely *determined*; residual is the reassignment window `NEW (marginal)`
**Assessment.** `FR-12` is mostly determined: "Every list endpoint enforces a maximum page size," "Filtering never widens authorization. A **Manager** filtering across all **Departments** sees only their **Direct Reports** (`FR-03`)," and `NFR-04` requires scope in the query (so scope precedes paging). The requested "interaction" therefore does not, on its own, produce an unhandled case.
**Residual undetermined case.** The one place FR-12 does not determine an outcome is under S-2: during a Manager reassignment, whether a Pending request that has just left (or just entered) a Manager's scope appears in that Manager's *paginated, filtered* queue is governed by the same unresolved authority-binding question as S-2, not by FR-12. FR-12 assumes a stable scope; the reassignment window is where "sees only their Direct Reports" is temporally ambiguous.
**Bite: MEDIUM** (inherited from S-2), otherwise this category is determined.

---

## Ranked summary (most likely to bite during Days 3–5)

| Rank | Case | Category | Status |
|---|---|---|---|
| 1 | A-1 / A-3 — applicant (incl. top-of-hierarchy Manager) with **no Manager** has no possible approver; submission Notification has null addressee | Authorization | NEW |
| 2 | S-2 — Manager **reassigned mid-Pending**; DR-12 doesn't fix whether authority binds at submit or decision | State machine | NEW |
| 3 | B-2 — **Reserved days on a still-Pending request at the year-rollover** boundary; DR-7 covers only Accrued | Balance | NEW |
| 4 | S-1 — **Concurrent approve vs cancel** out of Pending; DR-5 covers balance sign, not which transition wins | State machine | NEW |
| 5 | S-3 / S-4 — **applicant or Manager deactivated mid-Pending**; request status, Reserved release, and stranding undefined | State machine | NEW |
| 6 | D-3 / D-4 — **start > end** and **past start date**; DR-1/FR-08 give no validity rule for the day-count function | Day count | NEW |

Also material but lower in-window bite: B-3 (which year's balance a cross-boundary approval consumes), D-6/D-7 (holiday **deleted**, and holiday change against a **Pending** range — symmetric to but not covered by OQ7), B-1 (Admin lowering Accrued below Consumed+Reserved), N-1/N-2 (notification to deactivated/reassigned parties), L-1 (Department with only deactivated members), F-1/F-2 (document-requirement flip; document on a terminated request), A-2 (self-manager loop enabling self-approval), S-5 (no edit transition for a Pending request).

---

## Tally

- **Total unhandled cases reported: 25** — S-1…S-5 (5), B-1…B-4 (4), D-1…D-7 (7), A-1…A-3 (3), L-1…L-2 (2), F-1…F-2 (2), N-1…N-2 (2). P-1 is assessed as determined with an S-2-inherited residual (not counted as an independent unhandled case).
- **Already flagged by the PRD: 4** — B-4 (Open Question 5 / A-08), D-1 (Open Question 6 + FR-08 Out of Scope), D-2 (sub-case of Open Question 6), D-5 (Open Question 7). F-1 is *partly* flagged (OQ5 covers the reconfiguration but not the document-specific consequence).
- **Newly surfaced: 21** (F-1 counted as new because OQ5's stated consequence is balance-only).
- **Determined and therefore not reported: 5** (see §0).
