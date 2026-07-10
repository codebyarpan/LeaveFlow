# Reconciliation Review — PRD → ARCHITECTURE-SPINE

**Target (spine):** `../ARCHITECTURE-SPINE.md`
**Input (PRD):** `../../../prds/prd-LeaveFlow-2026-07-09/prd.md`
**Reviewer stance:** fidelity only. This checks whether every obligation in the PRD landed somewhere in the spine's Capability Map, ADs, conventions, or a conscious Deferred note. It does not judge the spine's quality.
**Date:** 2026-07-10

---

## Verdict

The spine is a high-fidelity projection of the PRD. Every FR is bound and mapped; every DR is either encoded in an AD/convention or (for DR-15) legitimately a non-constraint; every heavily-funded NFR (03/04/07/08) is structural; the four primary success metrics (SM-1..SM-4) are each made measurable by a named AD plus the Testing convention. Two of the "quiet" obligations the reconciliation specifically hunts for — FR-06's mandatory recorded Admin choice on policy change, and FR-10's *flag-for-Admin-review* on a refused recalculation — have **no home** in the spine and are genuine gaps that need an AD or convention. A third (FR-10's past-dated-leave-not-recalculated) and one security invariant (FR-01 login non-enumeration) are absent but plausibly below altitude. Everything else lands.

---

## Gaps that NEED an AD or convention (real architectural teeth, no home in the spine)

### G1 — FR-06: policy change requires an *explicit, recorded* Admin choice (recalculate vs. leave). `[NEEDS AD / convention]`
- **Locus:** §4.3 FR-06, consequence: *"When a Leave Policy change would affect Leave Balances that already exist, the system does not decide the outcome: it requires the Admin to choose explicitly whether existing balances are recalculated under the new policy or left as accrued under the old one. The change cannot be applied without that choice being made and recorded."*
- **Spine coverage:** **Partial.** The Structural Seed adds `entitlement_basis` to `leave_balance` precisely "so that an Admin choosing to recalculate an existing balance under a new policy has something to recalculate from." That supplies the *data* to recalculate. But three obligations are unaddressed: (a) the change is **gated** on a choice being made; (b) the choice is one of two explicit branches; (c) the choice **must be recorded**. There is no workflow gate, and nowhere to persist the decision — AD-8 restricts `audit_entry` to *Leave Request / Cancellation Request* transitions only, and `rollover_run` is for rollovers. A policy-change decision has no table and no AD.
- **Why it matters:** This is a correctness-and-accountability obligation with a mandatory audit-like record ("and recorded"). It is exactly the kind of prose obligation an AD list drops. FR-06 is Phase 1 (correctness core). Recommend an AD (or at minimum a convention) fixing where the recalc-or-leave choice is enforced and where it is persisted.

### G2 — FR-10: a recalculation that would drive a balance negative is REFUSED, left unchanged, and **flagged for Admin review**. `[NEEDS AD / convention for the flag]`
- **Locus:** §4.4/§4.3 FR-10, consequence: *"A recalculation never produces a negative Available balance (DR-5). Where a recalculation would, it is refused: the affected Leave Request and balance are left unchanged, and the case is flagged for Admin review."*
- **Spine coverage:** **Partial.** Non-negativity is enforced structurally — AD-5's `CHECK (accrued - consumed - reserved >= 0)` guarantees the recalc cannot commit a negative, and AD-3's single-transaction/rollback discipline gives "left unchanged" for free. So *refuse* and *unchanged* are covered. **But "flagged for Admin review" has no mechanism.** A bare `CHECK` violation surfaces as a transaction rollback / raw error, not as a durable, Admin-visible flag. AD-16's notification `kind` set is `{REQUEST_SUBMITTED, REQUEST_APPROVED, REQUEST_REJECTED}` — no holiday-recalc-refused kind; there is no flag entity, queue, or status. The Admin has no defined surface on which this case appears.
- **Why it matters:** The whole point of the refusal is that the Admin's holiday edit silently failed to apply to one request and someone must reconcile it. Without a surfacing mechanism the obligation is unmet. Recommend an AD or convention naming the flag's home (a notification kind, a review-queue row, or a documented error surface the holiday endpoint returns).

---

## Gaps likely below the spine's altitude, but wholly absent (flagged so the omission is a decision, not an accident)

### G3 — FR-10: past-dated Approved leave is **never** recalculated on a holiday-calendar change. `[likely below altitude; absent]`
- **Locus:** §4.3 FR-10, consequence: *"An Approved Leave Request whose dates have already passed is not recalculated. Historical leave is not revised when the holiday calendar changes."* Reinforced in §11 ("holiday-calendar changes recalculate Pending and future Approved requests, never past-dated leave").
- **Spine coverage:** **Not at all.** The spine covers the recalculation *mechanism* (AD-3 balance mutation; FR-10 → `services/holiday`, `domain/calendar`) but nowhere encodes the temporal predicate that decides *which* Approved requests are in scope for recalc. Nothing says "future-dated only."
- **Assessment:** This is a load-bearing correctness rule (it bounds a mutation), of the same family as the refusal rules the review is told to hunt. It is service/domain policy and arguably below the spine's feature altitude — but it is *entirely* missing, whereas its sibling ("Cancellation against passed dates is refused") *is* stated in AD-13. The asymmetry is worth closing: either add the "future-dated Approved only" predicate to AD-3/the FR-10 mapping, or accept it as a Deferred domain rule explicitly.

### G4 — FR-01: a failed authentication does not disclose whether the account exists (byte-identical unknown-identity vs. wrong-password). `[security invariant; likely below altitude; absent]`
- **Locus:** §4.1 FR-01, consequence: *"A failed authentication does not disclose whether the account exists: the response to an unknown identity and the response to a wrong password are byte-identical in body and equal in status code."*
- **Spine coverage:** **Not at all** for the auth endpoint. AD-10 establishes a byte-identical-404 principle, but it is scoped to *authorization* ("a resource outside the actor's scope returns 404, byte-identical to a nonexistent resource") — it governs resource reads, not the login endpoint's failure response. The non-enumeration property of `/auth` login is a distinct invariant (no branch on user-existence; identical timing/body), and it is not stated. AD-14 covers hashing and JWT but not this.
- **Assessment:** Real security teeth (prevents account enumeration), but a small endpoint-local rule — plausibly below altitude. Given the spine already articulates the *analogous* byte-identical principle for AD-10, extending one sentence to the auth endpoint would be cheap and would close FR-01's second consequence.

### G5 — FR-04: the two deactivation guards, and "deactivate, never delete". `[partly below altitude; one guard is architecturally load-bearing]`
- **Locus:** §4.2 FR-04 consequences + the FR-04 Notes: (i) an Employee with unresolved Pending requests cannot be deactivated; (ii) a Manager with ≥1 Direct Report cannot be deactivated "until every Direct Report has been reassigned … This keeps FR-09's managerless auto-approval from being reached by an Admin deactivating a Manager"; plus "An Employee is never physically deleted."
- **Spine coverage:** **Partial (pointer only).** The Capability Map row for FR-04 says "AD-10; deactivation guards in `services`." It names *that* guards exist and where they live, but not *what* they are. Guard (i) is ordinary service policy (below altitude). Guard (ii) is architecturally load-bearing — it is the integrity constraint that keeps AD-8's SYSTEM/`AUTO_APPROVED_NO_MANAGER` path (referenced in the spine's lifecycle diagram) from being reachable illegitimately. "Never physically deleted" is a data-lifecycle stance underpinning FR-16/audit survivability.
- **Assessment:** Acceptable to leave the *mechanics* in `services/`, but the Manager-with-reports guard's coupling to FR-09's auto-approval invariant, and the never-delete stance, are the sort of cross-cutting obligation the spine usually states. A one-line note (e.g., under AD-8 or the FR-04 mapping) would make the coupling explicit rather than implicit.

### G6 — FR-17: role/department/manager/joining-date/balance are not editable via the profile endpoint. `[security-relevant write restriction; likely below altitude]`
- **Locus:** §4.2 FR-17, consequence: *"Role, Department, Manager, joining date, and any Leave Balance quantity are not editable by the Employee who owns them. An attempt to alter them through the profile endpoint is refused."*
- **Spine coverage:** **Partial.** AD-10 is a *read*-scope invariant (404 on out-of-scope reads). AD-14 enforces operation-level authorization at the API boundary. Neither encodes *field-level* immutability *within* an operation the actor is otherwise allowed (profile self-edit). This is a privilege-escalation guard (an Employee must not raise their own role or edit their own balance).
- **Assessment:** Genuinely security-relevant, but naturally lives in the `api/` Pydantic write-schema / `services/employee`. Below altitude is defensible; worth a mention because "self-edit but not these fields" is easy to get wrong and the spine says nothing about write-field allow-lists.

### G7 — FR-08: refusal set — zero-working-day, reversed range, wholly-past range. `[below altitude; only spanning-two-years is surfaced]`
- **Locus:** §4.5 FR-08 consequences: request refused when day count is zero (range of only weekends/holidays); when end date precedes start; when the range lies wholly in the past; and when it spans two Leave Years.
- **Spine coverage:** **Partial.** Only *spans two Leave Years* is surfaced (Error-shape convention names `SPANS_TWO_LEAVE_YEARS`, and AD-12/DR-6 bind it). The **zero-day**, **reversed-range**, and **wholly-past** refusals are not represented — they are `domain`/`services` validations. SM-2 (validated by the Testing convention) does exercise the zero-working-day refusal, so that one at least has a test home.
- **Assessment:** These are input-validation refusals, comfortably below altitude — but they are named in the reconciliation brief as "quiet requirements," and the spine surfaces one of the four while silently dropping three. No AD needed; acceptable as domain-layer policy. Noted for completeness.

---

## Minor / genuinely below altitude (covered elsewhere or correctly out of the spine's reach)

- **NFR-02 — token lifetime in hours, not days.** Not in the spine; AD-14 covers signing/verification but not TTL. Config-level; below altitude. Minor.
- **NFR-10 — read endpoints ~500 ms.** Explicitly "an order of magnitude, not a contractual figure." Indirectly supported by the Indexing convention (NFR-12). Below altitude.
- **NFR-18 — responsive across desktop/tablet.** Frontend styling; the Deferred bucket explicitly defers "styling." Below altitude.
- **FR-05 — Department with assigned Employees cannot be removed (names the obstruction).** Service-policy guard, parallel to FR-04's guards; the Error-shape convention supplies "names the obstruction." Below altitude.
- **FR-13 — a doc-requiring Leave Type cannot be submitted without a document.** The enforcement rule is service-layer; AD-15 covers storage/validation/retrieval. The Deferred section consciously flags the FR-06→FR-13 phase gap and the unspecified seed value of `requires_supporting_document`. Below altitude, and the phase gap is acknowledged.
- **FR-11 — every dashboard supports a date-range filter.** Query/feature detail over scoped aggregates. Below altitude.
- **FR-19 — a deactivated Direct Report is distinguishable from active.** Implies an `is_active`/deactivation column on `employee`; attribute-level, explicitly Deferred to Module 4's ERD. Below altitude.
- **DR-15 / FR-18 — overlapping leave is permitted; the system informs, never blocks.** Bound to no AD, correctly: it is the *absence* of a constraint (no warning, no block, no acknowledgement). There is nothing to build, so nothing to encode. Legitimate.

---

## Confirmation — the "quiet requirement" hunt list resolves as follows

| Quiet obligation (from brief) | Locus | Spine coverage | Disposition |
| --- | --- | --- | --- |
| Holiday recalc driving balance negative is refused + flagged for Admin review | FR-10 | Partial — refuse/unchanged via AD-5/AD-3; **flag has no home** | **G2 — needs AD/convention** |
| Past-dated Approved leave never recalculated | FR-10 | Not at all | **G3 — absent (likely below altitude)** |
| Admin must explicitly choose recalculate-or-leave on policy change (and it's recorded) | FR-06 | Partial — data via `entitlement_basis`; **gate + record have no home** | **G1 — needs AD/convention** |
| Two distinct deactivation guards | FR-04 | Partial — pointer only ("guards in services") | **G5 — one guard is load-bearing** |
| FR-08 refusal cases (zero-day, reversed, wholly-past, spans two years) | FR-08 | Partial — only spans-two-years surfaced | **G7 — three below altitude** |
| "Filtering never widens authorization" | FR-12 | **Fully** — AD-10 applies scope as SQL predicate regardless of filters | Covered |
| Document retrievability scope (applicant / Manager / Admin only) | FR-13 | **Fully** — AD-15 re-applies AD-10's scope on the streaming endpoint | Covered |
| Admin-only audit read | FR-16 | **Fully** — Capability Map ("Admin only") + AD-10 | Covered |

---

## Coverage ledger (for completeness)

- **FR-01..FR-20:** all bound (front-matter) and all mapped (Capability → Architecture Map). Gaps within specific consequences: G1 (FR-06), G2/G3 (FR-10), G4 (FR-01), G5 (FR-04), G6 (FR-17), G7 (FR-08). All other consequences trace to an AD, convention, lifecycle diagram, or Deferred note.
- **DR-1..DR-16 (incl. DR-2a, DR-7a):** all encoded in an AD/convention. DR-15 correctly a non-constraint (no AD). DR-8's calendar-year definition is implied by `leave_year` (INTEGER) + the rollover CLI's `--year`; the literal Jan-1/Dec-31 boundary is a domain constant, below altitude.
- **NFR (§8):** the four funded ones — NFR-03, NFR-04, NFR-07, NFR-08 — are structural (AD-10, AD-3/AD-5, AD-2/AD-1). NFR-01/05/06/09/11/12/13/14/15/16/17/19/20/21 all map to an AD or convention. NFR-02/10/18 below altitude (noted above).
- **SM-1..SM-4 (primary):** each measurable. SM-1 → AD-5 + integration double-submit test; SM-2 → AD-2 + `tests/domain` (no DB); SM-3 → AD-10 (explicitly bound, `SM-3`); SM-4 → AD-8 (spine explicitly cites "SM-4's one-to-one count"). SM-5/SM-6/SM-8 covered; SM-7/SM-9 and SM-C1/C2/C3 are process/document metrics outside architecture altitude (SM-C2 aligns with the charts non-goal in Deferred).
- **§9 constraints:** three-roles, Manager→reports-only, Admin-no-approval, one-org-per-deployment, FastAPI/React, tech-from-bounded-set — all reflected (AD-10, AD-13, Deployment seed, Stack). Day-budget / BMAD-lifecycle constraints are process, not architecture.

---

## Recommendation

Two additions would close the only obligations with real teeth that currently have no home in the spine:

1. **An AD (or convention) for policy-change application (G1):** the recalc-or-leave choice is a required gate, and the chosen outcome must be persisted somewhere with actor+timestamp. Decide whether that record extends the audit model or gets its own table — AD-8 currently forecloses `audit_entry`.
2. **A surfacing mechanism for the refused holiday recalculation (G2):** name where "flagged for Admin review" lives — a notification `kind`, a review-queue row, or a documented endpoint error the Admin acts on.

Optionally, one sentence each would tidy G3 (future-dated-Approved-only recalc predicate) and G4 (extend AD-10's byte-identical principle to the auth endpoint's failure response).
