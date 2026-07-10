---
title: "LeaveFlow — Reconciliation Review: architecture.md & api-contracts.md vs. amended PRD"
reviewer: reconciliation reviewer
date: 2026-07-10
scope: "Effect of the seven PRD amendments (A1–A5, B1–B2) on the two downstream documents"
---

# Reconciliation Review — amended PRD vs. architecture.md and api-contracts.md

**Verdict:** The two downstream documents are **substantively still correct** — every architecture invariant (`AD-*`) and every endpoint/error code the amended PRD needs is present and matches. What the amendments broke is **the narrative around those invariants**: architecture §6/§8/§9 and api §4.8 still describe defects the PRD *has now fixed*, so they read as unresolved when they are resolved. Two findings are more than cosmetic — a per-Employee vs. per-Employee+Leave-Type mismatch, and a `PATCH /me` refusal list that omits Email Address.

The seven amendments, confirmed present in the PRD:
- **A1** — DR-7 (prd line 473) now defines "unused Accrued days" = **Available** (`Accrued − Consumed − Reserved`); DR-7a (line 474) cross-references it.
- **A2** — FR-07 (line 251) now records the rollover to "a separate append-only rollover log, not among Audit Entries"; the "Audit Entries record the actor SYSTEM" wording is gone.
- **A3** — FR-10 (line 231) refusal now covers "neither in the recalculated Leave Year nor in any later one," per **Employee and Leave Type**, into "a durable store the Admin can read and resolve," remainder proceeds; FR-06 (line 214) mirror consequence; DR-5 (line 466) now names "a Leave Policy change."
- **A4** — FR-14 (line 429): "An addressee can mark a Notification read. Marking read is idempotent, and only the addressee may do it."
- **A5** — §1 Vision (line 22) narrowed to "Every **Leave Request** state change is attributable to an actor and a moment." FR-16/NFR-19 not widened.
- **B1** — Glossary (line 88) Employee identified by Email Address + Full Name; Email Address (line 93) Admin-maintained, not Employee-editable; Full Name (line 94) the only field its owner may edit; FR-17 (lines 190–191) states Full Name is the only Employee-editable field.
- **B2** — FR-06 (line 210) seeds EL/CL/FL requires-supporting-document **false**; §7.3 (line 538) now "Resolved."

---

## architecture.md

### Check 1 — §9 opener "Five. Each needs a PRD edit …" — **STALE**

Line 323: *"Five. Each needs a PRD edit, and each is recorded in the spine's Upstream Amendments Required section."*

All five listed defects have now been fixed **inside the amended PRD**:
1. DR-7/DR-7a composition → A1 (DR-7 now defines "unused Accrued days" = Available).
2. FR-14 mark-read has no requirement → A4 (FR-14 now states it).
3. FR-07 vs. glossary/SM-4 → A2 (FR-07 now writes a separate rollover log).
4. FR-10 refuse-and-flag too narrow / no store → A3 (FR-10 now covers later years + durable store; FR-06 mirror).
5. Vision attribution promise → A5 (§1 narrowed to Leave Request state changes).

So "Each needs a PRD edit" is no longer true — the edits are made. The section heading "Defects found in the upstream documents" and the opening are now a historical record, not a to-do.

**Should say:** *"Five defects were found in the upstream documents. All five have now been resolved by amendments to the PRD (the fifth surfaced later by the Module 4 ERD). Each is recorded in the spine's Upstream Amendments Required section as incorporated."* Then each numbered item should switch from "resolved by `AD-n`" (in the architecture) to "resolved by `AD-n` **and now carried by the amended PRD**."

### Check 2 — §9 item 5 "Not resolved here … routed to the PM" — **STALE**

Line 329 quotes §1 as *"every state change is attributable to an actor and a moment"* and concludes the gap is **"Not resolved here … Surfaced by the Module 4 ERD and routed to the PM."**

Two problems now:
- The quote is inaccurate. Amended §1 reads *"Every **Leave Request** state change is attributable to an actor and a moment"* (A5) — the word "Leave Request" is exactly the narrowing.
- The PM **has** resolved it — by narrowing the Vision to match what FR-16/NFR-19 deliver, **not** by adding an audit requirement (A5 deliberately did not widen FR-16/NFR-19). Item 5's factual observation that FR-16/NFR-19 attribute only Leave Request transitions is still true; its conclusion ("not resolved, routed to PM") is stale. The gap is closed.

### Check 3 — §8 "FR-07 also says the rollover's 'Audit Entries record the actor SYSTEM'" — **STALE**

Line 313 quotes FR-07 as saying the rollover writes Audit Entries recording actor SYSTEM, then argues this would falsify SM-4. Per A2 that quote no longer exists — FR-07 (line 251) now says the rollover "records its execution in a separate append-only rollover log, not among Audit Entries, because it transitions no Leave Request." The PRD has already adopted exactly what AD-8 prescribes. AD-8 itself remains correct; the "FR-07 also says …" sentence describing a contradiction to be fixed is stale. Rewrite to note the PRD now agrees with AD-8 (FR-07 already routes rollover to a separate log; the glossary/SM-4 conflict no longer exists).

### Check 4 — §6.3 "AD-19 … generalizes a rule the PRD had already written for a narrower case … which FR-10 never reaches" — **STALE** (now contradicts amended FR-10)

Line 293: *"AD-19 extends exactly that rule to FR-06's policy recalculation, and — crucially — to downstream Leave Years, **which FR-10 never reaches**."*

Amended FR-10 (line 231) now reads: *"never produces a negative Available balance … **neither in the recalculated Leave Year nor in any later one** … The same guard governs a recalculation triggered by a Leave Policy change under FR-06."* And FR-06 (line 214) carries the mirror. So:
- FR-10 **now reaches** downstream Leave Years — the clause "which FR-10 never reaches" is now factually opposite to the PRD.
- FR-06's policy recalculation is now covered by the PRD itself, not only by AD-19.

AD-19 remains a valid invariant (it agrees with the amended PRD). But the reasoning "AD-19 generalizes what the PRD wrote narrowly" is overtaken: the PRD is no longer narrow. Rephrase to "AD-19 restates, in one place, the guard the amended FR-10/FR-06 now carry, and pins its transaction/per-row semantics."

### Check 5 — §10 seed decision — **STALE (minor); seed value agrees**

Line 343: seed value `requires_supporting_document = false` for EL/CL/FL **agrees exactly** with amended FR-06 (line 210) and §7.3 (line 538). The Admin-may-enable-later note also agrees. Substantively CLEAN.

Minor staleness: §10 says *"PRD §7.3 raised, and declined to answer, whether any seeded Leave Type demands a document; it is now settled by project decision …"* — §7.3 no longer declines; it is now headed **"Resolved."** and states the decision, and FR-06 carries it as a testable consequence. The framing "the PRD raised but declined; the architecture settles it" is stale — the PRD now settles it. The decision is identical, so no conflict; only the attribution is out of date.

### Check 6 — §11 Risks (Pending-lifetime, encashment) — **CLEAN**

- **Encashment forfeiture** (line 349): matches PRD §6 (line 498) and §11 (line 641) verbatim in substance. Accurate.
- **Pending-lifetime** (line 351): *"Nothing bounds how long a Leave Request may stay Pending … Routed to the PM as an open question."* The amendments (A1 DR-7/DR-7a) refine the semantics of a Pending request **crossing one boundary** but add **no bound** on Pending lifetime and do not address the multi-year propagation the risk describes. So the risk is still factually accurate. CLEAN.

  Note (pre-existing, not created by these amendments): the architecture calls this an "open question routed to the PM," while PRD §11 declares "None." That tension predates the seven amendments and none of them touched it — flagged for awareness, not as an amendment-induced defect.

### Check 7 — Does architecture assert the PRD "has no open questions"? Is it still true? — **STALE (the gap claim); the no-open-questions claim remains true**

Line 251 (§6): *"the PRD — which is otherwise unusually complete, carrying no open questions of its own — turns out to have a gap."* Section heading (line 249): *"The Leave Year boundary, and a hole in the requirements."*

- The clause "carrying no open questions of its own" is **still true**: amended PRD §11 (line 635) still says *"None"* and §12 (line 660) still says *"This document contains no assumptions."* A1–B2 did not add open questions.
- But "turns out to have a gap" / "a hole in the requirements" is **STALE**. The specific gap §6 is about — DR-7 and DR-7a not composing, "unused" undefined when days are Reserved — is exactly what A1 closed: DR-7 (line 473) now states *"'Unused Accrued days' means Available"* and walks through the Reserved-across-boundary case; DR-7a cross-references it. The PRD no longer has that hole. §6's premise ("here is where the otherwise-complete PRD is incomplete") should become "here is the interaction the amended DR-7/DR-7a now define, and how AD-6/AD-19 implement it."

---

## api-contracts.md

### Check 8 — §4.8 "FR-14 states no requirement for this mutation … the PRD needs the requirement" — **STALE**

Line 207: *"**FR-14 states no requirement for this mutation** — the PRD's own addendum calls it 'the smallest absence in the document.' AD-16 supplies the surface; the PRD needs the requirement."*

FR-14 (line 429) now states the requirement (A4), and PRD §11 (line 651) confirms *"FR-14's mark-read transition is now stated as a testable consequence of FR-14 itself. The absence recorded in addendum §3.2a is closed."* So "FR-14 states no requirement" and "the PRD needs the requirement" are both false now. STALE. Replace with: "FR-14 now states this mutation (idempotent, addressee-only); AD-16 fixes its surface."

### Check 9 — Does `PATCH /notifications/<id>/read` match FR-14's new consequence? — **CLEAN**

Endpoint (line 205): scope **self**; note (line 207): *"Mark-read is idempotent and permitted only to the addressee."* FR-14's new consequence (line 429): *"Marking read is idempotent, and only the addressee may do it"* + (line 427) *"A Notification is readable only by its addressee."* Idempotent ✓, addressee-only ✓ (self scope). Exact match. The **endpoint** is clean; only the surrounding "FR-14 states no requirement" prose (Check 8) is stale.

### Check 10 — §4.3 `PATCH /leave-types/<id>` disposition + POLICY_DISPOSITION_REQUIRED, and the AD-19/`/admin-review-flags` note — **CLEAN on the disposition surface; STALE on refusal granularity**

- Disposition: line 135 requires `RECALCULATE`/`PRESERVE` when a change affects existing balances, else `POLICY_DISPOSITION_REQUIRED`, persisted to `policy_change`. Matches amended FR-06 (line 213) exactly. The `POLICY_DISPOSITION_REQUIRED` error (line 72) is still valid. **CLEAN.**
- Downstream-year coverage: line 137's note runs AD-19's forward check on holiday add/delete **and** policy recalculation, checks "any materialized Leave Year," and returns 200 with a summary while the rest proceeds. This matches amended FR-10 (line 231, "nor in any later one," remainder proceeds) and FR-06 (line 214). **CLEAN.**
- **Granularity mismatch — STALE:** line 137 says *"that **Employee** is left unchanged."* Amended FR-10/FR-06 (A3) refuse *"for that **Employee and Leave Type**"* — i.e., only the affected Leave Type of that Employee is left unchanged; that Employee's other Leave Types still recalculate. The API (and architecture §6.3 line 293, *"that Employee's balance is left entirely untouched"*) coarsens this to the whole Employee. If an Employee's EL recalculation fails but CL is fine, the PRD wants CL to proceed; the API/architecture wording would freeze both. Tighten both to per-Employee-per-Leave-Type.

### Check 11 — Any endpoint or error code the amended PRD now contradicts? — **CLEAN**

Swept every endpoint (§4.1–§4.10) and every error code (§2). None is contradicted by A1–B2:
- Rollover has no endpoint (§4.10) — consistent with A2's separate rollover log (rollover is a CLI job, not audited, no API surface).
- `POLICY_DISPOSITION_REQUIRED` / `/policy-changes` / `/admin-review-flags` — consistent with amended FR-06/FR-10 (A3).
- `PATCH /notifications/<id>/read` — consistent with amended FR-14 (A4).
- `SUPPORTING_DOCUMENT_REQUIRED` (line 68) — still valid despite B2's false seed, because an Admin may set the flag true (FR-06 line 210), so the error can still be raised.
- Vocabulary (§3) `notification.kind`, `policy_change.disposition`, `audit_entry.*`, `role` — all consistent.

No contradicted endpoint or code. The only defects are the stale prose (Check 8) and the granularity wording (Check 10).

### Check 12 — Email Address / Full Name vs. FR-17's new rule — **STALE (`PATCH /me`); `PATCH /employees/<id>` CLEAN**

- **`PATCH /me` — STALE.** Line 103: *"PATCH /me refuses any attempt to alter role, department, manager, joining date, or a balance quantity."* This list **omits Email Address.** Amended FR-17 (line 191) now says Role, Department, Manager, joining date, **Email Address**, and any balance quantity are all non-editable, and Full Name is the *only* Employee-editable field; the glossary (line 93) makes Email Admin-maintained under FR-04. As written, `PATCH /me`'s refusal list does not bar an Employee from changing their own Email Address — their login identity (FR-01). This must be added to the refusal list. (Full Name is correctly editable: not in the refused list, matching FR-17.)
- **`PATCH /employees/<id>` — CLEAN.** Line 112: Admin, scope all, realizes FR-04. Amended FR-17 (line 191) says *"The Email Address is maintained by the Admin under FR-04"* — so this is the correct and only place Email is edited. Consistent, no conflict.

---

## Summary table

| # | Document / section | Verdict |
| --- | --- | --- |
| 1 | arch §9 opener "Five. Each needs a PRD edit" | STALE |
| 2 | arch §9 item 5 "not resolved, routed to PM" (+ misquotes §1) | STALE |
| 3 | arch §8 "FR-07 also says … Audit Entries record SYSTEM" | STALE |
| 4 | arch §6.3 "which FR-10 never reaches" (downstream years) | STALE (now contradicts amended FR-10) |
| 5 | arch §10 "§7.3 raised, and declined to answer" | STALE (minor); seed value CLEAN |
| 6 | arch §11 encashment + Pending-lifetime risks | CLEAN |
| 7 | arch §6 "a hole in the requirements" / DR-7 gap | STALE; "no open questions" still true |
| 8 | api §4.8 "FR-14 states no requirement … PRD needs it" | STALE |
| 9 | api `PATCH /notifications/<id>/read` vs FR-14 | CLEAN (exact match) |
| 10 | api §4.3 disposition + AD-19 note | CLEAN; refusal granularity STALE (per-Employee vs per-Employee+Leave-Type) |
| 11 | api endpoints / error codes | CLEAN (none contradicted) |
| 12 | api `PATCH /me` (Email) / `PATCH /employees/<id>` | `PATCH /me` STALE (omits Email); `/employees/<id>` CLEAN |

**Nothing in either document needs its design changed.** Every `AD-*` invariant and every endpoint/error code the amended PRD requires is present and consistent. The work is editorial (retire "defect found / needs a PRD edit" narrative now that the PRD carries the fixes) plus two precision fixes: add Email Address to `PATCH /me`'s refusal list, and change "that Employee is left unchanged" to per-Employee-per-Leave-Type in api §4.3 and architecture §6.3.
