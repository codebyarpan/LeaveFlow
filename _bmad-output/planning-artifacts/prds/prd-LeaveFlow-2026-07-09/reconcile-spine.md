---
title: "LeaveFlow — PRD ↔ Architecture Spine Reconciliation"
role: reconciliation-review
prd: "../../prds/prd-LeaveFlow-2026-07-09/prd.md"
spine: "../../architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md"
reviewed: 2026-07-10
verdict: "No live CONTRADICTION. The seven PRD amendments moved the PRD onto the spine's own targets; the fallout is STALE spine meta-commentary — the entire 'Upstream Amendments Required' section plus its §7.3 companion note now describe a past state."
---

# PRD ↔ Spine Reconciliation

**One-line verdict.** Every one of the seven amendments landed the PRD *on* the resolution the spine had already chosen, so there is **no CONTRADICTION** anywhere — but the spine's forward-looking "these still need a PRD edit" commentary is now false in every particular. The load-bearing invariants (AD-6, AD-8, AD-16, AD-19, AD-20) already agree with the amended PRD; only the **"Upstream Amendments Required"** block and its trailing §7.3 note have gone STALE.

Legend: **CONTRADICTION** = PRD and spine now assert incompatible things · **STALE** = spine describes a PRD state that no longer exists · **CLEAN** = they agree.

---

## Check 1 — "Upstream Amendments Required" section (spine lines 405–415)

**Verdict: STALE (whole section).**

Header (line 407): *"This spine resolves five places where the PRD is internally inconsistent or incomplete. Each needs a corresponding PRD edit so the two do not silently diverge."*

All five are now carried by the amended PRD, so the header's operative claim — *"Each needs a corresponding PRD edit"* — is false. Bullet by bullet:

1. **DR-7/DR-7a compose** (bullet, line 409, ends *"The most consequential of the four"*). PRD DR-7 now states, verbatim: *"'Unused Accrued days' means Available — Accrued − Consumed − Reserved … measured whenever the value is computed, not at the boundary alone."* This is exactly AD-6's fix. **Carried → bullet STALE.** (Note also the internal miscount: the header says *five* places, this bullet says *the four* — a pre-existing spine inconsistency, presumably because the Vision bullet was appended after the prose was written.)
2. **FR-07 rollover audit** (line 410). PRD FR-07 now: *"It records its execution in a separate append-only rollover log, not among Audit Entries, because it transitions no Leave Request."* Matches AD-8. **Carried → bullet STALE.** (See Check 2.)
3. **FR-10 recalculation refusal** (line 411). PRD FR-10 now reaches later Leave Years, refuses per Employee+Leave Type, writes a durable Admin-readable store, and extends the guard to FR-06's policy recalculation; FR-06 gained the mirror consequence; DR-5 now names Leave Policy change. Matches AD-19/AD-20. **Carried → bullet STALE.** (See Check 5.)
4. **FR-14 mark-read** (line 412). PRD FR-14 now: *"An addressee can mark a Notification read. Marking read is idempotent, and only the addressee may do it."* Matches AD-16. **Carried → bullet STALE.** (See Check 3.)
5. **§1 Vision attribution promise** (line 413). The spine bullet quotes the *old* Vision — *"every state change is attributable to an actor and a moment"* — and argues FR-16/NFR-19 under-deliver it, closing with *"Neither this spine nor the Module 4 ERD invents the missing requirement. … Raised by the ERD as GAP-3."* The PRD chose **Option (i): it narrowed the Vision** to *"Every **Leave Request** state change is attributable to an actor and a moment"* (line 22) and deliberately did **not** widen FR-16/NFR-19. The tension the bullet describes is therefore gone — but resolved in the *opposite* direction from the one the bullet anticipates. **The bullet no longer describes reality on two counts:** it misquotes the current Vision, and it frames an open GAP-3 that the narrowing has closed. **STALE.**

**What the section should say instead.** Retitle to something like *"Upstream Amendments — Applied (informational record)"* and past-tense every bullet: "PRD DR-7 now defines unused = Available (AD-6)"; "FR-07 now routes the rollover to a separate rollover log (AD-8)"; "FR-10/FR-06/DR-5 now carry the later-year, per-Employee+Type refusal and the policy-recalc guard (AD-19/AD-20)"; "FR-14 now carries mark-read (AD-16)"; "§1 Vision was **narrowed** to Leave Request state changes — GAP-3 resolved by narrowing the promise, not by inventing an attribution requirement." Fix the five/four miscount while editing. Or delete the section outright, since divergence is now zero.

---

## Check 2 — AD-8 vs amended FR-07 (spine lines 109–113)

**Verdict: AD-8 Rule itself CLEAN; the "PRD is to be amended" claim (which lives in the Upstream section, not AD-8) is STALE.**

Correction of premise: the sentence the task attributes to AD-8's Rule — *"PRD FR-07 states the rollover writes Audit Entries; this spine resolves that against the PRD's own glossary and SM-4, and the PRD is to be amended"* — **does not appear in AD-8.** AD-8's Rule ends: *"The rollover writes to `rollover_run`, a separate append-only table."* That is fully consistent with amended FR-07 → **AD-8 CLEAN.** The "and the PRD is to be amended" framing is Upstream bullet 2 (line 410). Because FR-07 has now been amended to route the rollover to a separate log, that framing is **false → STALE** (already counted in Check 1). §11 (line 649) independently confirms the closure: *"Idempotence is settled … a second run against the same Leave Year is a no-op."*

---

## Check 3 — AD-16 vs amended FR-14 (spine lines 157–161)

**Verdict: AD-16 Rule itself CLEAN; the "the PRD is to be amended" claim (Upstream bullet 4) is STALE.**

Same premise correction: the sentence *"FR-14 carries no requirement for this mutation; the PRD is to be amended"* **does not appear in AD-16.** AD-16's Rule ends: *"Mark-read is an idempotent `PATCH` on the notification, permitted only to its addressee."* Amended FR-14: *"Marking read is idempotent, and only the addressee may do it."* These agree exactly → **AD-16 CLEAN.** The "no requirement … to be amended" claim is Upstream bullet 4 (line 412), now **false → STALE** (counted in Check 1).

---

## Check 4 — §7.3 [NOTE FOR PM] companion (spine line 415)

**Verdict: STALE.**

Spine: *"PRD §7.3's `[NOTE FOR PM]` asks whether any seeded Leave Type requires a Supporting Document, and **declines to choose**. It is now answered by project decision: none does. … the PRD should **close the note**."* PRD §7.3 (lines 533–538) no longer declines and no longer carries a `[NOTE FOR PM]`: it now opens **"Resolved."** and records the decision — EL/CL/FL seeded *requires-supporting-document* false. So *"declines to choose"* and *"the PRD should close the note"* both describe a past state → **STALE.** The substance the spine asserts (*"none does"*) still matches reality.

---

## Check 5 — AD-19 & AD-20 vs amended FR-10 & FR-06

**Verdict: CLEAN. Full agreement on all five axes; no exploitable divergence.**

Amended **FR-10** (line 231): *"A recalculation never produces a negative Available balance (DR-5) — neither in the recalculated Leave Year nor in any later one. Where it would, the recalculation is refused for that Employee and Leave Type: their Leave Requests and Leave Balances are left unchanged, and the case is recorded in a durable store the Admin can read and resolve. The remainder of the operation proceeds for the Employees it does not affect. The same guard governs a recalculation triggered by a Leave Policy change under FR-06."*

Amended **FR-06** (line 214): *"A recalculation … obeys the same non-negativity guard as FR-10. It never produces a negative Available balance in any Leave Year. Where it would, it is refused for the affected Employee and Leave Type, whose Leave Requests and Leave Balances are left unchanged, and the case is recorded in the durable store the Admin reads and resolves. The remainder of the change proceeds for the Employees it does not affect."*

**AD-19** (line 179): *"… the operation verifies that no year's Available becomes negative. Where it would, that Employee and Leave Type are left entirely unchanged, a row is written under AD-20, and the remainder of the operation proceeds …"* and **AD-20** (line 185): *"`admin_review_flag` records every refusal AD-19 produces, with its cause, its subject, and its resolution state … the Admin surface reads it."*

Axis-by-axis:

| Axis | FR-10 / FR-06 | AD-19 / AD-20 | Match |
| --- | --- | --- | --- |
| Checks later Leave Years | "nor in any later one" / "in any Leave Year" | "no year's Available … in every materialized later year" | ✔ |
| Refuses per Employee+Leave Type | "for that/the affected Employee and Leave Type" | "independently for each affected Employee and Leave Type" | ✔ |
| Requests & balances unchanged | "Leave Requests and Leave Balances are left unchanged" | "left entirely unchanged" (superset — also freezes `leave_days`) | ✔ |
| Durable Admin-readable store | "durable store the Admin can read and resolve" | `admin_review_flag` w/ resolution state, Admin surface reads it | ✔ |
| Rest of operation proceeds | "remainder … proceeds for the Employees it does not affect" | "the remainder of the operation proceeds" | ✔ |

No divergence in scope or wording that would let a builder satisfy one while violating the other. FR-06's separate requirement that the recalc/preserve **choice be recorded before the change is applied** (line 213) is met by AD-20's `policy_change` table (disposition RECALCULATE/PRESERVE, recorded before apply). **CLEAN.**

---

## Check 6 — AD-6 vs amended DR-7

**Verdict: CLEAN on the "unused" definition; the cap/entitlement trigger is PRD-covered (via FR-06), not architecture-only — minor altitude note only.**

**"Unused" definition.** DR-7 (line 473): *unused Accrued days = Available = Accrued − Consumed − Reserved.* AD-6 (line 101): `carried_forward(Y+1) = min(leave_type.carry_forward_cap, available(Y))`. **Exact match → CLEAN.**

**Recompute triggers.** AD-6 recomputes carry-forward on "a year-Y request transition, a year-Y recalculation under AD-19, **and a change to that Leave Type's `carry_forward_cap` or `annual_entitlement`** — the last of which is not a balance change and must therefore be wired as an explicit trigger."

- *annual_entitlement change* re-derives Accrued, i.e. it **is** a change to the closing year's balance, so DR-7's own clause (*"Carry-Forward is recomputed whenever the closing Leave Year's balance changes"*) already covers it — and it is separately a "Leave Policy change [that] would affect Leave Balances that already exist" under FR-06 line 213.
- *carry_forward_cap change* does **not** alter the closing year's Accrued/Consumed/Reserved, so DR-7's literal balance-change trigger does **not** capture it. But it **is** a Leave Policy change that affects existing (next-year `carried_forward`/`accrued`) balances, so it is covered by FR-06's recalculation-choice mechanism (lines 213–214) and by FR-10's *"same guard governs a recalculation triggered by a Leave Policy change under FR-06."*

So the cap trigger **is** covered by the PRD, at the FR-06 policy-change altitude — it is **not architecture-only**. What is architecture-only is the *explicit "recompute carry-forward on a cap change" wiring*; the PRD never states it as a discrete rule, and DR-7's own trigger list is narrower than AD-6's. This is an altitude/detail gap, not a contradiction. **CLEAN (with note):** if anyone wants belt-and-braces, add a one-line DR-7 rider — "a change to a Leave Type's Carry-Forward Cap or Annual Entitlement is a Leave Policy change and triggers the FR-06 recalculation choice" — but the FR-06 path already authorizes what AD-6/AD-19 implement.

---

## Check 7 — Spine "Open Questions" (spine lines 417–419)

**Verdict: CLEAN.**

- *Pending-lifetime entry* (line 419): still accurate. The amended PRD introduces no bound on how long a Leave Request may stay Pending; DR-7a still keeps Reserved days alive across the boundary "until it is approved, rejected, or cancelled," and PRD §11 reports **no** open questions. The spine's "by project decision none is introduced … recorded as a known limitation … Routed to the PM" remains a true description.
- *requires_supporting_document entry*: **gone, as it should be.** The Open Questions section contains only the Pending-lifetime bullet; the seed-document decision now lives in the Seeding convention (line 215) and the (stale) §7.3 companion note (line 415), not as an open question. Correct.

---

## Check 8 — Seeding convention vs amended FR-06 seed consequence

**Verdict: CLEAN.**

Spine Seeding convention (line 215): *"EL, CL and FL are seeded as data with `requires_supporting_document` set to false. No seeded Leave Type demands a document. An Admin may enable it per Leave Type (FR-06); enabling it before FR-13 ships leaves the requirement configurable but unenforced."* Amended FR-06 (line 210): *"At initialization, EL, CL and FL are seeded with requires-supporting-document false … An Admin may set the attribute true for any Leave Type at any time."* Identical intent, including the pre-FR-13 "configurable but unenforced" reading (also in PRD §7.3). **CLEAN.**

---

## Check 9 — AD-14 & AD-10 vs new Glossary Email Address / Full Name terms

**Verdict: CLEAN. No conflict; these are ERD-home column attributes the spine correctly does not carry.**

New glossary terms: **Email Address** (line 93) — *"the unique identifier an Employee exchanges as their credential under FR-01. Maintained by the Admin (FR-04); not editable by the Employee … LeaveFlow sends no email (FR-14)"*; **Full Name** (line 94) — *"the only profile field its owner may edit (FR-17)."*

- **AD-14** (auth, line 149) never names the credential field; it fixes JWT transport, `exp`, byte-identical auth failures, and bcrypt/Argon2 hashing. "Email Address is the login identifier" and "auth failure discloses nothing about account existence" are consistent, not conflicting.
- **AD-10** (authorization / 404, line 125) is field-agnostic; FR-17's "Full Name is the only editable field" is enforced under AD-10 via `api/v1/me` with no tension.
- **Should the spine mention them?** No. By its own boundary — *"Attributes are shown only where a column is itself an invariant"* (line 277) and *"Attribute-level schema and index tuning … Module 4's ERD owns it"* (Deferred, line 423) — Email Address and Full Name are ordinary `employee` columns, not invariants. The EMPLOYEE box in the ERD (line 280) correctly shows no attributes. **The ERD is their correct home.** (One item worth the ERD's attention, not the spine's: Email Address is glossed as "the unique identifier," so the ERD should carry a `UNIQUE` constraint on it — parallel to AD-5's `UNIQUE (employee_id, leave_type_id, leave_year)`, but at ERD altitude.)

---

## Check 10 — Anything else where PRD and spine now disagree

**No further CONTRADICTION found.** Cross-checks:

- **Vision narrowing does not orphan any spine invariant.** The spine only ever audits Leave Request / Cancellation Request transitions (AD-8, AD-13, AD-21, SM-4). The narrowed Vision (Leave Request state changes only) makes the PRD *more* aligned with the spine, not less. AD-20's `policy_change`/`admin_review_flag` recording is driven by FR-06's "choice … recorded" requirement, independent of the Vision's attribution promise, so nothing there over- or under-reaches. CLEAN.
- **DR-5 (line 466)** now names *"a Leave Policy change (FR-06, FR-10)"* alongside the holiday-change recalculation — consistent with AD-3/AD-19's binding of DR-5. CLEAN.
- **PRD-internal nit (not a spine divergence, flagged for completeness):** FR-17 and the glossary say Email Address is *"maintained by the Admin under FR-04,"* but FR-04's enumerated consequence fields (line 168: Department, role, joining date, Manager) do not explicitly list Email Address. It is implied by "create … Employee records," but the FR-04 field list could name it for symmetry. This is a PRD-internal tidy-up, not a PRD↔spine conflict.

---

## Summary table

| # | Subject | Result |
| --- | --- | --- |
| 1 | "Upstream Amendments Required" section (all 5 bullets + header) | **STALE** — all carried; header claim false; five/four miscount |
| 1.5 | Bullet 5 / §1 Vision | **STALE** — Vision narrowed (Option i); GAP-3 closed by narrowing, not widening; bullet misquotes current Vision |
| 2 | AD-8 vs FR-07 rollover | AD-8 **CLEAN**; Upstream bullet 2 "to be amended" **STALE** |
| 3 | AD-16 vs FR-14 mark-read | AD-16 **CLEAN**; Upstream bullet 4 "no requirement / to be amended" **STALE** |
| 4 | §7.3 [NOTE FOR PM] companion | **STALE** — note resolved; "declines to choose / should close the note" false |
| 5 | AD-19/AD-20 vs FR-10/FR-06 | **CLEAN** — agree on all five axes, no exploitable divergence |
| 6 | AD-6 vs DR-7 | **CLEAN** — "unused=Available" matches; cap trigger PRD-covered via FR-06 (altitude note only) |
| 7 | Open Questions | **CLEAN** — Pending-lifetime still accurate; requires_supporting_document entry correctly absent |
| 8 | Seeding convention vs FR-06 seed | **CLEAN** |
| 9 | AD-14/AD-10 vs Email Address / Full Name | **CLEAN** — ERD-home attributes; spine correctly silent |
| 10 | Sweep for other divergence | **CLEAN** — one PRD-internal FR-04 nit only |

**Net:** zero CONTRADICTION; the spine's entire "Upstream Amendments Required" block plus its §7.3 companion note are STALE and should be past-tensed or removed. Every binding invariant already matches the amended PRD.
