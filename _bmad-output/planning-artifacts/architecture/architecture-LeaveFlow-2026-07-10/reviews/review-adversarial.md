---
title: "Adversarial Review — ARCHITECTURE-SPINE.md (LeaveFlow)"
lens: "Two compliant units, built incompatibly. Every pair is a hole."
target: "../ARCHITECTURE-SPINE.md"
reviewer_stance: adversarial
created: "2026-07-10"
---

# Adversarial Review — LeaveFlow Architecture Spine

**Verdict:** The spine is strong on *where code lives* and *who opens a transaction*, but it never says **who owns an entity's mutation**. AD-3 is a locking protocol mistaken for an ownership rule; four epics can lawfully write `leave_balance`, three can lawfully write `leave_request.status`, and the spine's one self-declared invariant — AD-6's carry-forward monotonicity — is **false the moment an Admin changes policy**, which FR-06 lets them do at any time. Below are the concrete incompatible-but-compliant pairs, ranked most-severe-first. Each pair names the two epics, the AD(s) each obeys to the letter, the two divergent implementations, and the concrete failure (wrong number, crash, corruption, or silent gap).

The epic partition assumed throughout:

- **Epic A** — Identity, RBAC, employee/department admin (FR-01..05, FR-17)
- **Epic B** — Leave policy + holiday calendar (FR-06, FR-10)
- **Epic C** — Balances, proration, rollover (FR-07)
- **Epic D** — Request lifecycle, approval, cancellation, audit (FR-08, FR-09, FR-16)
- **Epic E** — Dashboards, calendar, history, notifications, export (FR-11..15, FR-18..20)

---

## Finding 1 — CRITICAL — AD-6's monotonicity is a lie under policy change; lowering a cap forces a CHECK-constraint crash

**Epics:** B (FR-06 policy recalc, `services/policy`) vs C (FR-07 carry-forward, `domain/carry_forward` + `jobs/rollover`).
**ADs each obeys:** AD-6 ("`carried_forward(Y+1) = min(carry_forward_cap, available(Y))` … written by assignment … available(Y) is monotonically non-decreasing, so carry-forward is only ever topped up and never clawed back") and AD-5 (`CHECK (accrued - consumed - reserved >= 0)`, `CHECK (accrued = prorated_entitlement + carried_forward)`). Epic B additionally obeys FR-06 ("An Admin can set and change a Leave Type's Carry-Forward Cap … requires the Admin to choose explicitly whether existing balances are recalculated under the new policy").

**The trace (airtight, integer arithmetic):**

Year 2026, leave type EL, `carry_forward_cap = 10`, `annual_entitlement = 12`, full-year employee.

- 2026 row: `prorated_entitlement=12`, `consumed=2`, `reserved=0` → `available = 10`.
- At the boundary the rollover writes `carried_forward(2027) = min(10, available(2026)=10) = 10`.
- 2027 row: `prorated_entitlement=12`, `carried_forward=10`, `accrued=22` (CHECK ok: `22 = 12 + 10`). Employee then consumes heavily: `consumed=20`, `reserved=0` → `available = 2` (CHECK ok: `22-20-0 = 2 ≥ 0`).

March 2027: Admin lowers EL `carry_forward_cap` from 10 to 5 and chooses **recalculate existing balances** (FR-06 lets them). Epic B, obeying AD-6, recomputes by assignment:

- `carried_forward(2027) = min(5, available(2026)=10) = 5`.
- `accrued = prorated_entitlement + carried_forward = 12 + 5 = 17`. (CHECK ok: `17 = 12 + 5`.)
- Now the other CHECK: `accrued - consumed - reserved = 17 - 20 - 0 = -3 < 0` → **`CHECK` violation, transaction aborts.**

**Concrete failure:** A hard crash (constraint violation) on a lawful Admin action. Worse, the recalc is now **permanently inapplicable** for any employee who has already consumed more than the new cap-derived accrued — the Admin can never lower the cap-with-recalc for those employees. AD-6's own sentence "never clawed back" is only true with policy frozen; `available(Y)` being monotone as *Pending requests resolve* has nothing to do with the *cap itself* dropping. The `annual_entitlement`-decrease variant is the same class (`prorated_entitlement 12→8`, `accrued=8+10=18`, `18-20 = -2 < 0`).

**The silent variant (no CHECK to save you):** AD-6 says carry-forward is recomputed "whenever year Y's balance changes, propagating forward through every materialized later year." A cap change is **not** a year-Y balance change — it is a policy change. So Epic B may recompute only the directly-targeted year and skip the forward cascade Epic C's rollover would have run. Then 2028's `carried_forward` (derived from 2027's now-lowered `available`) is stale, 2028 `accrued` is wrong, and if 2028 has light consumption **no CHECK fires** — a silently wrong balance in the following year. Two owners (`services/policy`, `jobs/rollover`), two beliefs about whether the cascade fires.

**Close it — tighten AD-6 + new AD-17:**
- **Binds:** FR-06, FR-07, DR-7, the rollover job.
- **Prevents:** a cap/entitlement decrease crashing on AD-5's CHECK or leaving stale later-year balances; two modules disagreeing on whether a policy change cascades.
- **Rule:** AD-6's monotonicity claim is explicitly scoped to *policy-frozen* resolution of Pending requests; it does **not** hold across a `carry_forward_cap` or `annual_entitlement` decrease. `accrued`, `prorated_entitlement`, and `carried_forward` for a given `(employee, leave_type, leave_year)` are written by **exactly one** module — `services/policy` for policy-driven recompute, `jobs/rollover` for boundary recompute — and both call the single `domain.carry_forward` and `domain.proration` functions. Any recompute that would make `accrued - consumed - reserved < 0` for a row is **refused for that row** (row left unchanged, exception written per AD-20), and the batch continues. Every policy-driven recompute triggers the same forward cascade the rollover does; the cascade owner is `domain.carry_forward`, invoked identically from both entrypoints.

---

## Finding 2 — CRITICAL — No single owner of reserve/consume/release; AD-3 is a lock protocol, not an ownership rule — and a shared `consume` crashes on the very first managerless submission

**Epics:** C (FR-07 balance) and D (FR-08/09 lifecycle) and B (FR-10 holiday recalc) — all three lawfully write `leave_balance` quantities.
**ADs each obeys:** AD-3 ("A command that writes any `leave_balance` quantity first acquires that row with `SELECT ... FOR UPDATE` … Exactly one transaction per command, opened in `services/`"). The Consistency Convention row "Balance quantities move only through reserve, consume, and release (AD-3)." Nothing in the spine *defines the signature or contract* of reserve/consume/release, nor names a single module that owns them.

**Divergence 2a — the `consume` primitive has two irreconcilable meanings.** The lifecycle diagram states two consume paths:
- `Pending → Approved`: "reserved becomes consumed" (AD-6: "Approval transfers Reserved to Consumed").
- `[*] → Approved` (managerless): "SYSTEM consumes immediately … no reservation stage" (FR-08: "consuming its Leave Days without a reservation stage").

If Epic C defines one primitive `consume(row, days)` as `reserved -= days; consumed += days` (the natural reading of "reserved becomes consumed"), then Epic D's **auto-approval** path calling it computes `reserved = 0 - days < 0` → **`CHECK (reserved >= 0)` violation, crash on the first managerless submission.** If instead Epic D open-codes `consumed += days` for auto-approval and never touches `reserved`, then two epics now hold two different consume implementations and the convention "quantities move only through reserve, consume, and release" is satisfied by *neither's* single primitive. The lens's question — "Does AD-3's protocol cover a consume-without-prior-reserve path?" — is answered **no**: AD-3 covers locking, not the arithmetic, so the consume-without-reserve path is undefined and will be built two ways.

**Divergence 2b — Epic B writes quantities Epic D "owns."** FR-10: adding a holiday inside a Pending request's range "recalculates that request's Leave Day count and its Reserved days"; inside a future Approved request it recalculates "the applicant's Leave Balance" (i.e. `consumed`). So `services/holiday` (Epic B) writes `reserved` and `consumed` — the exact quantities the lifecycle (Epic D) moves. Both obey AD-3 (each locks the row). But there is no shared `reserve/release` primitive, so Epic B's "reduce reserved by 1" and Epic D's "reduce reserved by N on rejection" are independent code with independent invariant assumptions. When they disagree on rounding, on whether `reserved` may transiently exceed `accrued`, or on order of writes, the CHECK fires for one and not the other, or the two produce different `reserved` for the same request.

**Concrete failure:** `CHECK (reserved >= 0)` crash on the first auto-approval (2a); divergent `reserved`/`consumed` semantics across Epic B and Epic D (2b).

**Close it — new AD-18:**
- **Binds:** FR-07, FR-08, FR-09, FR-10.
- **Prevents:** an auto-approval crashing a shared consume; two epics implementing balance arithmetic with divergent pre/postconditions; quantities moving outside a defined primitive.
- **Rule:** Exactly one module, `services/balance`, defines the balance-mutation primitives, and every service (leave_request, cancellation, holiday, rollover, policy) routes *all* quantity changes through them. The primitives and their fixed contracts are: `reserve(row, days)` (`reserved += days`, requires resulting `available ≥ 0`); `consume_reserved(row, days)` (`reserved -= days; consumed += days`, asserts `reserved ≥ days`); `consume_direct(row, days)` (`consumed += days`, requires resulting `available ≥ 0`; the **only** consume path with no prior reservation, used solely by managerless auto-approval); `release_reserved(row, days)` (`reserved -= days`); `release_consumed(row, days)` (`consumed -= days`). No service computes `reserved`/`consumed`/`accrued` arithmetic inline. Each primitive locks the row per AD-3 before writing.

---

## Finding 3 — HIGH — `leave_request.leave_days` is unmodelled and unowned; stored-vs-recomputed count drifts history, reserved, and consumed apart

**Epics:** D (stores the count on submit) vs B (recomputes on holiday change) vs E (FR-20 history renders the count).
**ADs each obeys:** AD-2 ("One function, `domain.calendar.count_leave_days`, is the only code that knows what a weekend or a Company Holiday is. Every path that touches a balance calls it. The client obtains every day count from the preview endpoint"). FR-20 ("Each entry shows … the Leave Day count"). FR-10 ("An Approved Leave Request whose dates have already passed is not recalculated").

**The gap:** The core-entities ERD models `leave_balance`'s columns but **never models a `leave_days` column on `leave_request`.** AD-2 mandates one *function*, not one *stored value*. So:
- Epic D stores `leave_days` at submission time (it must, to `reserve` that many days).
- Epic E (FR-20 history) can lawfully *recompute* the count by calling `count_leave_days` against the **current** calendar — AD-2 practically invites this ("every path … calls it").

**Concrete failure — retroactive rewrite of history and balance drift.** An Admin adds a holiday inside the range of a *past* Approved request. FR-10 forbids recalculating past leave. But if Epic E recomputes `leave_days` on read, the history view now shows a count reduced by the new holiday — **violating FR-10** — while the balance's `consumed` (frozen by Epic D) is unchanged. History says 4 days, balance says 5 consumed. Symmetrically, if a holiday is added inside a *Pending* request's range and Epic B updates `reserved` but not the stored `leave_days` (there being no column the spine told it to update), Epic D's history/detail shows 5 while `reserved` is 4. Either way: **the day count a user sees and the day count the balance reserved/consumed disagree**, silently, exactly the "believed wrong number" the PRD Vision exists to kill.

**Close it — new AD-19:**
- **Binds:** FR-08, FR-10, FR-20.
- **Prevents:** a request's displayed count drifting from its reserved/consumed days; a past-dated request being retroactively re-counted against a changed calendar.
- **Rule:** `leave_request` carries a stored `INTEGER leave_days`, the single authoritative count. It is written only by `domain.calendar.count_leave_days`, and only by (a) submission and (b) an AD-permitted FR-10 recalculation while the request is Pending or future-Approved. Once a request's dates are wholly in the past **or** it reaches a terminal state, `leave_days` is frozen and never recomputed. Every reader — history, dashboards, exports, balances — reads the stored value; **no reader recomputes the count against the live calendar.** For any request, `reserved` (if Pending) or `consumed` (if Approved) equals its stored `leave_days`.

---

## Finding 4 — HIGH — FR-10's "refused and flagged for Admin review" has no table and no detection AD; two epics invent two stores, or the flags are invisible

**Epics:** B (FR-10 holiday recalc **and** FR-06 policy recalc — both "refuse where it would go negative") vs E (FR-11 Admin dashboard, which must *surface* the flags).
**ADs each obeys:** FR-10 ("A recalculation never produces a negative Available; where it would, it is refused: the affected Leave Request and balance are left unchanged, and the case is flagged for Admin review"). AD-8 ("`audit_entry` holds exactly one row per state transition … **and nothing else**") — which explicitly forbids parking the flag in `audit_entry`. AD-9 grants the app only INSERT/SELECT there. `rollover_run` is rollover-only.

**The gap:** No table exists for "flagged for Admin review." No AD tells Epic B *how* to detect the negative case (compute would-be `available` and compare? per-row or per-batch?), and no AD tells Epic B whether "refused" means the whole holiday insert is rejected or just the one offending request is skipped. FR-10's own text resolves the latter ("the holiday is added, the request left unchanged") — meaning the calendar and that request's `leave_days` are now knowingly inconsistent (ties back to Finding 3). So:
- Epic B (holiday) invents `holiday_recalc_flag(leave_request_id, reason)`.
- Epic B (policy, same FR-06 negative case) invents `policy_recalc_exception(employee_id, leave_type_id, …)` — a *different shape for the same concept*, even inside one epic.
- Epic E's Admin dashboard reads **neither** (it was never told they exist) → **flagged cases are invisible; the Admin never reviews them; FR-10's "flag for Admin review" is silently unmet.**

**Concrete failure:** Two divergent flag tables (or none), and a "review" surface that shows nothing to review.

**Close it — new AD-20:**
- **Binds:** FR-06, FR-10, FR-11.
- **Prevents:** two epics inventing two exception stores; refused recalculations vanishing without an Admin surface; ambiguity over per-row vs whole-batch refusal.
- **Rule:** A single append-until-resolved table `recalc_exception(id, subject_type, subject_id, employee_id, leave_type_id, leave_year, source ∈ {HOLIDAY, POLICY}, detail_json, created_at, resolved_at)` records every recalculation refused because it would drive `available < 0`. Written only by `services/holiday` and `services/policy`; exposed to Admin through exactly one FR-11 endpoint. Detection is per-row: the recalc computes the would-be `available`; if `< 0`, it writes one exception row and leaves that request/balance unchanged; the remaining rows in the batch proceed. This is the **only** "flag for Admin review" mechanism; no other epic defines another.

---

## Finding 5 — HIGH — status / subject_type / from_state string vocabulary is unpinned; AD-4's guarded UPDATE silently refuses every transition and SM-4's audit counts miss rows

**Epics:** D (writes `leave_request.status`, `audit_entry`) vs E (reports/history/dashboards filter on those strings) vs any epic that reads a status.
**ADs each obeys:** AD-4 ("Every transition is a single `UPDATE ... SET status = :to WHERE id = :id AND status = :from`. Zero affected rows means the transition is refused"). AD-8 (columns `subject_type`, `from_state`, `to_state`, `actor_type` — actor_type is enumerated EMPLOYEE/SYSTEM, **the others are not**). AD-11 ("`leave_request.status` … are `TEXT` constrained by `CHECK`") — but the CHECK's *value set is never stated*.

**The gap:** The spine's state diagrams use Title Case ("Pending", "Approved"). Nothing says the *database* stores Title Case. Epic D, following common convention, writes `'PENDING'`. A helper constant elsewhere reads `'Pending'`. Then AD-4's `... WHERE status = :from` with `from = 'Pending'` matches **zero rows** against a stored `'PENDING'` → the transition is "refused," the transaction rolls back — **every approval silently fails and rolls back forever**, indistinguishable from AD-4's legitimate first-committed-wins refusal. And `audit_entry.to_state`: if Epic D writes `'APPROVED'` for leave requests while the cancellation path writes `'Approved'`, then Epic E's report filtering `to_state = 'Approved'` (or SM-4's one-to-one count query) **misses half the rows**. `subject_type` has the same disease: `'LEAVE_REQUEST'` vs `'leave_request'` vs `'LeaveRequest'`.

**Concrete failure:** Either a total silent failure of a transition class (casing mismatch in AD-4's guard) or under-counted audit/report queries (SM-4 reported passing while genuinely broken).

**Close it — new AD-21:**
- **Binds:** FR-08, FR-09, FR-16, DR-16, SM-4, and AD-4/AD-8/AD-11.
- **Prevents:** a casing mismatch silently refusing every transition; report/audit queries missing rows; two epics writing synonyms of one status.
- **Rule:** One shared constants module, imported by every layer, defines the exact strings: `leave_request.status ∈ {PENDING, APPROVED, REJECTED, CANCELLED}`; `cancellation_request.status ∈ {PENDING, APPROVED, REJECTED}`; `audit_entry.subject_type ∈ {LEAVE_REQUEST, CANCELLATION_REQUEST}`; `audit_entry.actor_type ∈ {EMPLOYEE, SYSTEM}`; `from_state`/`to_state` draw from the relevant status set plus the sentinel `''` (empty string, **never NULL**) for a creation transition's `from_state`. All values are SCREAMING_SNAKE_CASE. The `CHECK` constraints enumerate exactly these literals. No layer writes a differently-cased or synonym value.

---

## Finding 6 — HIGH — AD-3 prevents the deadlock but not the phantom: a request submitted during a holiday recalc permanently escapes recalculation; and one holiday add serializes against every submission org-wide

**Epics:** B (FR-10 holiday recalc, locks MANY balance + request rows) vs D (FR-08 submission, locks one balance + one request row).
**ADs each obeys:** AD-3 ("Where several balance rows are locked, they are locked in ascending `(employee_id, leave_type_id, leave_year)`. Balance rows are always locked before request rows.").

**On the deadlock the lens asks about — AD-3 *does* hold.** The ascending `(employee_id, leave_type_id, leave_year)` order is a valid total order, so multiple balance-row lockers cannot cycle; "balance before request" kills the classic two-resource cycle between Epic B and Epic D. Rollover locking ascending `leave_year` composes cleanly. So **deadlock proper is prevented.** But two things AD-3 does *not* prevent:

**6a — Phantom / TOCTOU (correctness).** To recalc, Epic B must first `SELECT` the set of requests whose range contains the new holiday, then derive and lock their balance rows, then update. Between the discovery `SELECT` and the lock acquisition, Epic D submits a *new* request covering that same date. Under READ COMMITTED, Epic D's `count_leave_days` reads the holiday calendar at statement time; if the holiday INSERT has not yet committed, the new request **counts the holiday as a working day and over-reserves.** Epic B's recalc set was snapshotted before that request existed, so it never corrects it. You cannot `FOR UPDATE` a row that does not yet exist — AD-3's lock ordering is powerless against a phantom. The over-reserved request escapes recalculation **permanently.** AD-3 orders locks; it says nothing about isolation level for the recalc-vs-submit race.

**6b — Liveness (not deadlock, but a stall).** "Exactly one transaction per command" (AD-3) means one holiday addition locks *every* affected balance row across the *whole organization* in a single long transaction. While it runs, every submission/approval touching any of those rows blocks. AD-3 buys correctness at the cost of org-wide serialization on a routine Admin action, and reserves no batching seam.

**6c — Latent (request-row order undefined).** AD-3 fixes the lock order for *balance* rows only. Epic B locks many *request* rows; their order is unspecified. Today only Epic B locks multiple request rows, so no cycle — but the first future command that locks two request rows reintroduces deadlock, because the spine never fixed a request-row order.

**Concrete failure:** A request over-reserves the value of one holiday and is never corrected (6a); org-wide write stalls during holiday edits (6b); latent deadlock the day a second multi-request-locking command is written (6c).

**Close it — new AD-22 (extends AD-3):**
- **Binds:** FR-08, FR-10, NFR-07, DR-5.
- **Prevents:** a concurrently-submitted request escaping FR-10 recalculation; latent deadlock from unordered request-row locks.
- **Rule:** An FR-10 recalculation command runs at SERIALIZABLE isolation (or takes an advisory lock keyed on the holiday calendar), so a Leave Request submitted concurrently is either included in the recalc set or fails serialization and retries against the committed calendar — a request can never reserve against a calendar edit it missed. AD-3's ascending lock order is extended to request rows: where several request rows are locked, they are locked in ascending `id`. The recalc's affected-row working set is documented as bounded per command; batching beyond that bound is an allowed refinement, not a schema change.

---

## Finding 7 — MED-HIGH — Notification ownership and cardinality are undefined: double-notify, a null-recipient crash on managerless auto-approval, and an unrepresentable cancellation notification

**Epics:** D (owns the transition and its transaction) vs E (FR-14 notifications, `api/v1/notifications`).
**ADs each obeys:** AD-16 ("A Notification is written inside the same transaction as the transition that causes it … a `kind` discriminator (REQUEST_SUBMITTED, REQUEST_APPROVED, REQUEST_REJECTED), the Leave Request it concerns, a nullable `read_at`"). AD-3 ("services own the transaction"). FR-14 ("Submission … creates exactly one Notification addressed to the applicant's Manager").

**7a — Who writes it? Two writers → two notifications.** AD-16 says the notification is written in the transition's transaction; AD-3 says only the transitioning service owns that transaction. But FR-14 belongs to Epic E, which owns `api/v1/notifications`. If Epic E ships a `notification_service.create(...)` *and* Epic D inlines a notification INSERT (both lawful), a submission produces **two** notifications → unread count doubled, FR-14's "exactly one" broken. Conversely if each assumes the other writes it, **zero**.

**7b — Managerless auto-approval: null recipient crash.** FR-14: submission notifies "the applicant's Manager." A managerless employee has **no manager**. Epic D's auto-approval path either (i) emits a REQUEST_SUBMITTED to a null recipient → NOT NULL / FK violation, **crash**, or (ii) skips it — but the spine never says which, and it must also decide whether a REQUEST_APPROVED fires to the applicant for their *own* auto-approval (notifying yourself of a decision you triggered). Epic D and Epic E will answer differently: 0, 1, or 2 notifications for one managerless submission.

**7c — Cancellation notifications are unrepresentable.** AD-16's `kind` enum has no CANCELLATION value, and its FK is "the Leave Request it concerns." When an Admin approves/rejects a Cancellation Request, notifying the applicant (obviously desirable) requires a kind not in the enum, and the thing it concerns is a `cancellation_request`, not a `leave_request` — which AD-16's schema cannot point at. Epic D either does not notify (product gap) or invents a shape AD-16 forbids.

**Concrete failure:** Duplicate or zero notifications (7a); a NOT NULL crash on managerless submission (7b); no way to notify a cancellation decision (7c).

**Close it — new AD-23:**
- **Binds:** FR-11, FR-14, and AD-16.
- **Prevents:** duplicate/zero notifications; a null-recipient insert; an unrepresentable cancellation notification.
- **Rule:** The transitioning service is the sole writer, via one helper `notifications.emit(kind, recipient_id, subject_type, subject_id)` called inside the transition's transaction; `api/v1/notifications` only reads and marks-read, never creates. `recipient_id` is NOT NULL and `emit` is never called with a null recipient. Cardinality per transition is fixed: submit → 1 to manager; manager-approve → 1 to applicant; manager-reject → 1 to applicant; **managerless auto-approval → 0** (no manager exists; the applicant is the actor); cancellation-request decided by Admin → 1 to applicant. The notification `kind` set is extended to include CANCELLATION_APPROVED and CANCELLATION_REJECTED, and its subject link is polymorphic (`subject_type` + `subject_id`, mirroring AD-8) so a cancellation notification can point at a `cancellation_request`.

---

## Finding 8 — MED-HIGH — Two owners of the `Approved → Cancelled` edge; a shared "cancel" releases the wrong quantity and Available is never restored

**Epics:** D internal split — `services/leave_request` vs `services/cancellation` (both live in Epic D per the capability map, but the spine assigns the edge to neither).
**ADs each obeys:** AD-4 ("Every transition of a Leave Request … is a single guarded UPDATE"). AD-13 ("Only an approved Cancellation Request moves it to Cancelled, releasing its Consumed days"). AD-6 ("only release raises [available]"). The lifecycle diagram shows `Cancelled` reachable **two ways**: `Pending → Cancelled` (applicant cancel, release **reserved**) and `Approved → Cancelled` (Admin approves cancellation, release **consumed**).

**The gap:** `services/leave_request` owns `Pending → Cancelled`; `services/cancellation` owns the Cancellation Request lifecycle. But the *target* leave request's `Approved → Cancelled` transition is caused by the cancellation approval — is it written by `services/cancellation` (which is deciding) or `services/leave_request` (which "owns" leave-request transitions per AD-4)? The spine assigns it to neither. Two failure modes:
- **Neither writes it** (each assumes the other) → the target request never actually moves to Cancelled, or is double-audited (SM-4 one-to-one broken: 0 or 2 rows).
- **A shared `cancel(request)` primitive** that always `release_reserved` (correct for the common `Pending → Cancelled` path) is reused for `Approved → Cancelled`. But an Approved request has `reserved = 0`; releasing reserved does nothing, and `consumed` is **never released.** No crash — `available` simply stays too low forever. **BR-05 ("cancelling approved leave restores the deducted balance") silently violated; a wrong, believed number.**

**Concrete failure:** The target request either isn't cancelled at all / double-audited (owner ambiguity), or is cancelled but `consumed` is never released so Available never recovers (shared-primitive wrong-quantity).

**Close it — new AD-24:**
- **Binds:** FR-09, DR-4, DR-14, BR-05, and AD-4/AD-6/AD-13.
- **Prevents:** an ownerless / double-owned Cancelled edge; releasing the wrong quantity on cancellation.
- **Rule:** `services/leave_request` owns the edges `[*]→Pending`, `[*]→Approved` (auto), `Pending→Approved`, `Pending→Rejected`, `Pending→Cancelled`. `services/cancellation` owns the Cancellation Request's own edges **and** the target Leave Request's `Approved→Cancelled` edge, since only an approved Cancellation Request causes it. Each edge names its AD-18 balance primitive explicitly: `Pending→Cancelled` uses `release_reserved`; `Approved→Cancelled` uses `release_consumed`. There is no generic "cancel" primitive that infers which quantity to release.

---

## Finding 9 — MED — No owner of `leave_balance` row creation / initial accrual; a submission finds no row and either crashes or invents an entitlement

**Epics:** A (FR-04 employee create) vs C (FR-07 proration + rollover) vs D (FR-08 submission).
**ADs each obeys:** AD-5 (`UNIQUE (employee_id, leave_type_id, leave_year)`). AD-3 (submission locks the balance row `FOR UPDATE`). FR-07 ("An Employee who joins mid-Leave-Year receives a Prorated Accrued balance"). Nothing names *who creates the row, when*.

**The gap:** A `leave_balance` row can lawfully be created by employee-activation (Epic A), by the rollover for the next year (Epic C), or lazily by a submission that finds none (Epic D). Proration (FR-07) must run at creation, but employee creation is Epic A's and proration is Epic C's `domain`. So:
- If Epic A seeds only the join-year row and Epic C's rollover seeds next-year rows, an employee submitting for a valid year with **no row yet** hits Epic D. Epic D either crashes on a NULL row, or lazily inserts one with an *invented* entitlement (zero → request wrongly refused as INSUFFICIENT_BALANCE; or full annual → **double-grant**, ignoring proration).
- If two creators race, `UNIQUE` makes one INSERT crash rather than silently duplicating — a crash surfacing to a user for a lawful action.

**Concrete failure:** Missing-row crash, or a wrong initial `accrued` (zero or un-prorated) that produces a wrong Available.

**Close it — new AD-25:**
- **Binds:** FR-04, FR-07, and AD-5.
- **Prevents:** a submission inventing an entitlement; racing creators crashing on UNIQUE; proration bypassed at row creation.
- **Rule:** A `leave_balance` row is created for a given `(employee, leave_type, leave_year)` by exactly one path — `services/balance.ensure_year_balance` — which computes `prorated_entitlement` via `domain.proration` from the employee's joining date and the leave type's current `annual_entitlement`, and sets `carried_forward` per AD-6. It is invoked on employee activation (for the current Leave Year) and by the rollover (for the next). **No submission path lazily creates a balance row.** A submission against a non-existent balance row is a defined refusal, never a lazy insert.

---

## Finding 10 — MED — Are the two creation edges audited? SYSTEM-vs-EMPLOYEE actor and `from_state` for `[*]→` transitions are undefined; SM-4 can be off by the whole request count

**Epics:** D (FR-16 audit) vs any SM-4 verifier.
**ADs each obeys:** AD-8 (`from_state` is a column, required; `actor_type` EMPLOYEE/SYSTEM; `actor_id` NULL iff SYSTEM). SM-4 ("Audit Entry count equals state-transition count, one-to-one"). FR-09 (managerless auto-approval "names the actor SYSTEM and the reason AUTO_APPROVED_NO_MANAGER"). The lifecycle diagram draws `[*]→Pending` and `[*]→Approved` as transitions.

**The gap:** For a creation edge (`[*]→Pending`), what is `from_state`? AD-8 requires the column but never defines the initial-transition value. One epic writes `from_state = NULL` (which AD-8's schema may or may not permit), another writes `''`, another decides "creation is not a transition" and writes **no audit row at all** — making SM-4's one-to-one count off by the entire count of created requests. And the actor: `[*]→Pending` is actor EMPLOYEE (the applicant); `[*]→Approved` (managerless) is actor SYSTEM — yet **both are triggered by the same employee clicking submit.** A literal-minded engineer could record the auto-approval's actor as the EMPLOYEE who clicked (they did act), directly contradicting FR-09's SYSTEM. AD-8's "NULL iff SYSTEM" rule constrains `actor_id` but does **not** settle *who the actor conceptually is* for an employee-triggered auto-approval.

**Concrete failure:** SM-4 reported passing or failing depending on an unstated convention; an auto-approval attributed to EMPLOYEE, contradicting FR-09 and mis-attributing the audit trail the product exists to protect.

**Close it — fold into AD-21 + tighten AD-8:**
- **Rule:** Both creation edges in each state diagram are transitions and each writes exactly one `audit_entry`, with `from_state = ''` (the sentinel from AD-21). `[*]→Pending` records `actor_type = EMPLOYEE`, `actor_id =` the applicant. `[*]→Approved` (managerless auto-approval) records `actor_type = SYSTEM`, `actor_id = NULL`, `reason = AUTO_APPROVED_NO_MANAGER`, regardless of which employee's submission triggered it — the *triggering* employee is never the *actor* of a SYSTEM transition.

---

## Finding 11 — MED-LOW — Pagination style/param/limit and the error-code registry are under-pinned; the shared typed client faces a non-uniform API

**Epics:** all of them expose list endpoints and error envelopes; E owns the single shared `frontend/src/api` client.
**ADs each obeys:** Consistency Conventions ("Every list endpoint enforces a server-side maximum page size; a client asking for more receives the maximum"; "A single envelope of machine code, human message, and structured details"). The Deferred section claims "Only the base path, the error envelope, and the pagination bound are fixed here" — but the *value* and *shape* are not.

**The gap:** "A server-side maximum" fixes neither the number, the parameter names, nor the pagination style. Epic A ships `?page=`, Epic D ships `?offset=&limit=`, Epic E ships `?cursor=`, with maxima of 50 vs 100 vs 200 and different response envelopes (`{items,total}` vs bare array). The single typed client cannot be uniform, and FR-12's "filters compose" can't be exercised consistently. Likewise the error `code` vocabulary is only exemplified (INSUFFICIENT_BALANCE, SPANS_TWO_LEAVE_YEARS); each epic coins its own `NOT_FOUND` vs `RESOURCE_NOT_FOUND`, and AD-10's out-of-scope-404 code is unspecified, so the client cannot switch on codes reliably. (The `kind` discriminator, by contrast, *is* pinned in AD-16 — good — except for the cancellation gap in Finding 7.)

**Concrete failure:** A frontend that must special-case pagination and error handling per endpoint; brittle client-side error branching.

**Close it — new AD-26:**
- **Binds:** FR-12, NFR-11, and the error-envelope convention.
- **Prevents:** divergent pagination contracts and ad-hoc error codes across epics.
- **Rule:** Every list endpoint uses one pagination contract — query params `?limit=&offset=`, a fixed default (50) and maximum (200), and a response envelope `{items, total, limit, offset}`; a `limit` above the maximum is clamped, not rejected. Error `code` values are drawn from one enumerated registry in `core/`; AD-10's out-of-scope response uses the same `NOT_FOUND` code and 404 as a genuinely missing resource, byte-identically.

---

## Summary table

| # | Severity | Epics | Core ADs stressed | Failure | Fix |
|---|---|---|---|---|---|
| 1 | Critical | B vs C | AD-6, AD-5, FR-06 | CHECK crash / permanently inapplicable recalc / silent stale later-year | tighten AD-6 + AD-17 |
| 2 | Critical | C/D/B | AD-3, balance convention | `CHECK(reserved>=0)` crash on first auto-approval; divergent arithmetic | AD-18 (one balance-primitive owner) |
| 3 | High | D vs B vs E | AD-2, FR-10, FR-20 | history/reserved/consumed drift; past leave re-counted | AD-19 (stored, frozen `leave_days`) |
| 4 | High | B vs E | FR-10, FR-06, AD-8 | two flag tables or none; flags invisible to Admin | AD-20 (`recalc_exception`) |
| 5 | High | D vs E | AD-4, AD-8, AD-11 | casing mismatch silently refuses every transition; audit under-count | AD-21 (canonical string vocabulary) |
| 6 | High | B vs D | AD-3 | phantom: over-reserved request escapes recalc; org-wide stall | AD-22 (isolation + request-row order) |
| 7 | Med-High | D vs E | AD-16, AD-3 | double/zero notify; null-recipient crash; cancellation unrepresentable | AD-23 (one emitter, fixed cardinality) |
| 8 | Med-High | D internal | AD-4, AD-6, AD-13 | Cancelled edge unowned; consumed never released, Available stuck | AD-24 (edge ownership + explicit release) |
| 9 | Med | A vs C vs D | AD-5, AD-3 | missing-row crash or invented entitlement | AD-25 (one balance-row creator) |
| 10 | Med | D | AD-8, SM-4 | creation edges maybe unaudited; auto-approval mis-attributed | fold into AD-21 + tighten AD-8 |
| 11 | Med-Low | all | conventions | non-uniform pagination + error codes | AD-26 |

**Two structural observations the individual findings share.** First, the spine repeatedly fixes *where code lives* (AD-1's layering) and *who opens the transaction* (AD-3) but almost never *who owns an entity's mutation* — findings 2, 8, 9 are all the same missing concept ("one writer per quantity/edge/row"), and findings 1 and 3 are its consequence for `accrued` and `leave_days`. A single "single-owner" doctrine AD would subsume much of this. Second, the spine's most confident sentence — AD-6's "never clawed back … idempotent by construction" — is the one that breaks first, because it assumes a frozen policy that FR-06 explicitly makes mutable.

---

*Full review written to this file. The spine was not modified.*
