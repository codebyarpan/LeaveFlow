---
title: "LeaveFlow PRD — Memlog Reconciliation"
status: audit
created: 2026-07-09
scope: report-only (fixes nothing; proposes nothing)
---

# Memlog Reconciliation — LeaveFlow PRD run (2026-07-09)

Source of truth: `.memlog.md`, 32 append-only entries.
Derived artifacts checked: `prd.md`, `addendum.md`.

Each memlog entry is assigned exactly one disposition:
- **PRD** — captured in `prd.md` (section cited)
- **ADD** — captured in `addendum.md` (section cited)
- **SET ASIDE** — audit/process information that belongs in neither document
- **LOST** — records a decision or reasoning present in neither document that should be

## Disposition table

| # | Entry gist | Type | Disposition | Location |
|---|---|---|---|---|
| 1 | PRD run bound to path; Create intent, no prior PRD | event | SET ASIDE | Run-binding / dispatch event |
| 2 | `uv` unavailable; memlog.py run via `python3` | override | SET ASIDE | Tooling override — belongs in neither |
| 3 | Subagent-extracted inputs; 18 FR / 21 NFR / BR / D / A carried into Discovery | event | SET ASIDE | Extraction event (counts independently present in PRD §0, §4, §8) |
| 4 | Stakes = evaluated deliverable, Fast path; PRD must be defensible aloud and chain into Architecture/ERD/Epics | decision | PRD | §0 Document Purpose (defensible + downstream chain); Fast-path/stakes label is process |
| 5 | FR-11 dashboard: per-role summary cards only, no charts; charts = stretch | decision | PRD | §4.6 FR-11 note, §7.4, OQ4 (grounding addendum 1.2) |
| 6 | FR-14: in-app only; avoids SMTP infra, deliverability, managed secret; unread badge | decision | PRD | §4.7 FR-14 note (grounding addendum 1.1) |
| 7 | FR-15: CSV only; PDF = stretch | decision | PRD | §4.8 FR-15 note, §7.4 |
| 8 | PRD phases 18 FRs; facilitator proposes, Arpan approves/moves | decision | PRD | §7 intro |
| 9 | A-04: FL = Floater Leave; lapse rule decisive; Flexi ruled out | assumption | PRD | §4.3 FR-06 note (A-04) (grounding addendum 2.1) |
| 10 | A-09 escalated to blocking; calendar vs financial-year; lapse 31 Dec vs 31 Mar | event | PRD | §11 OQ1 Blocking (grounding addendum 2.2) |
| 11 | EL-above-cap must be encashed not forfeited; silent forfeiture may be non-compliant; surface as OQ | event | PRD | §11 OQ2, §6 (grounding addendum 2.2) |
| 12 | Comparables validate D-01 / D-02; balance triple ≈ industry ledger | event | ADD | §2.5 (also §2.3) |
| 13 | COUNTER-EVIDENCE: email is table-stakes; state as known departure, not neutral simplification | event | PRD | §4.7 FR-14 note, §7.4, §6 (grounding addendum 1.1) |
| 14 | Deferred-to-design resolved: employee sees Available + projected Remaining; dept calendar inline on approval, colour-coded | decision | PRD | §4.4 FR-07, UJ-1, §4.6 FR-18 (grounding addendum 2.3, 2.4) |
| 15 | NEW invariant: leave day = calendar date in locale, not UTC timestamp | event | ADD | §3.1 (referenced in PRD §11 reclassified-out) |
| 16 | In-app only CONFIRMED by Arpan after counter-evidence; email deferred with trade-off | decision | PRD | §4.7 FR-14 note |
| 17 | FR IDs FR-01..18 preserved verbatim; new req starts FR-19 | decision | PRD | §0, §4 intro (grounding addendum 1.3) |
| 18 | Domain Rules §5 CONSOLIDATION ONLY; research items barred, routed to OQ + addendum | decision | PRD | §5 intro (also addendum §3 intro) |
| 19 | Personas Rahul/Meera/Anil fictional only; not stakeholders/roles/reqs | decision | PRD | §2.3 intro (also addendum §4) |
| 20 | PRD draft written 12 sections; dropped Compliance/Monetization/Integration/Data-Governance clusters; addendum written | event | SET ASIDE | Document-assembly event; cluster-drop rationale is authoring process (scope partly embodied in §6) |
| 21 | Phasing: P1 FR-01..10,16,17 / P2 FR-11,18,12,14 / P3 FR-13,15 | decision | PRD | §7.1 / §7.2 / §7.3 (assignments match exactly) |
| 22 | SM reject coverage-counting; SM-1..4 correctness, SM-5..7 policy/traceability; counter-metrics SM-C1..C3 | decision | PRD | §10 |
| 23 | SM reworked: coverage necessary-but-not-sufficient; add SM-8; SM-C1 narrowed to "coverage read in isolation" | change | PRD | §10 (SM-8, SM-C1) |
| 24 | Reviewer gate: 7 reviewers; rubric 6/7; DR 15/16 faithful, DR-5 drifted; FR-13 silent drift | event | SET ASIDE | Review/audit event (findings themselves captured via #26/#28) |
| 25 | CORRECTION: miscounted open-item density 10/6, actual 7/5 (legend + index) | change | SET ASIDE | Facilitator miscount — audit fact; belongs in neither |
| 26 | FR-13 drift corrected: doc retrievable by applicant, Manager, AND Admin | decision | PRD | §4.5 FR-13 (3rd consequence) |
| 27 | FR-11 reframed: UNILATERAL scope reduction, not OR-authorized; escalate to OQ | decision | PRD | §4.6 FR-11 note, §11 OQ4 (grounding addendum 1.2) |
| 28 | Applied gate corrections bundle (FR-13/FR-11/SM-1/DR-5/DR-6/DR-16/FR-01/FR-06/FR-17/FR-18/FR-13 bounds) | change | PRD | §4.5, §4.6, §10 SM-1, §5.2 DR-5, DR-6, DR-16, §4.1 FR-01, §4.3 FR-06, FR-17/FR-18 notes — all landed |
| 29 | Open Questions restructured; count held 10; OUT (FL→A-04, leave-date→addendum 3.1, NFR-eval→§8, eval-mode→plan); IN OQ4/8/9/10; OQ3 blocker; OQ1 downgraded | change | PRD | §11 (Blocking / Non-blocking / Reclassified-out) |
| 30 | A-05 WITHDRAWN → OQ3; identifier retired; assumptions index round-trips 8=8 | change | PRD | §12, §11 OQ3 |
| 31 | §7 states phasing risk; SM-8 missed → reported as missed; FR-06/FR-13 phase gap; addendum 3.4 DR-2 no-preview-exception | change | PRD | §7 (risk para + phase-gap NOTE), addendum §3.4 |
| 32 | Addendum §3.2a added (rollover no caller; audit read undefined; FR-14 mark-read implied); Leave Type + Notification added to entity list | change | ADD | §3.2a, §3.2 |

## Counts by disposition

- **CAPTURED IN PRD:** 23 — entries 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16, 17, 18, 19, 21, 22, 23, 26, 27, 28, 29, 30, 31
- **CAPTURED IN ADDENDUM:** 3 — entries 12, 15, 32
- **DELIBERATELY SET ASIDE:** 6 — entries 1, 2, 3, 20, 24, 25
- **LOST:** 0
- **Total:** 32

Every entry lands somewhere. No memlog entry is LOST.

---

## Question 1 — Every `decision` entry: is the decision AND its stated reason preserved?

The 14 `decision`-tagged entries are 4, 5, 6, 7, 8, 14, 16, 17, 18, 19, 21, 22, 26, 27. For each, both the decision and its reason survive into an artifact (per SM-6's promise that a reader can find where a decision was made and on what basis):

| Entry | Decision preserved | Reason preserved | Where |
|---|---|---|---|
| 4 | yes | yes (evaluated deliverable) | PRD §0 |
| 5 | yes | yes (no acceptance criteria; 3-day budget) | PRD §4.6, OQ4, §7.4 |
| 6 | yes | yes (SMTP infra, deliverability, managed secret) | PRD §4.7 |
| 7 | yes | yes (PDF materially more work) | PRD §4.8, §7.4 |
| 8 | yes | yes (18 FRs vs 3 code days) | PRD §7 |
| 14 | yes | yes (Workday/BambooHR pattern) | PRD §4.4/§4.6 + addendum §2.3/§2.4 |
| 16 | yes | yes (spec "email or in-app"; budget) | PRD §4.7 |
| 17 | yes | yes (preserve traceability chain) | PRD §0, §4 + addendum §1.3 |
| 18 | yes | yes (Arpan constraint; otherwise scattered) | PRD §5 intro |
| 19 | yes | yes (force specificity; not real actors) | PRD §2.3 + addendum §4 |
| 21 | yes | yes (correctness core funded first) | PRD §7 |
| 22 | yes | yes (coverage ≠ correctness) | PRD §10 |
| 26 | yes | yes (Admin reads all per FR-03) | PRD §4.5 |
| 27 | yes | yes (single spec term, not an OR) | PRD §4.6, OQ4 + addendum §1.2 |

**No decision is half-lost.** Every decision's reason travelled with it into an artifact.

Weakest case, noted for completeness: entry 4's "Fast path working mode / Stakes = evaluated deliverable" calibration is workflow metadata that does not itself appear in an artifact — but the externally-meaningful decision it produced (the PRD must be defensible aloud and must chain into Architecture/ERD/Epics) and its reason (it is an evaluated deliverable) are both in §0. Nothing a downstream reader needs is missing.

## Question 2 — Did the counter-evidence against in-app-only notifications reach the PRD reader, or only the memlog reader?

**It reached the PRD reader — prominently and in the exact framing the memlog demanded.**

Memlog entry 13 required that the decision be stated "as a known departure from production norms made for budget reasons, NOT as a neutral simplification." The PRD honors this in three places:

- **§4.7 FR-14 note:** "in industry practice email is table-stakes for approval workflows, because managers do not live in the application and applicants book travel against pending requests. In-app-only notification is therefore a known departure from how production leave systems behave."
- **§7.4:** "Production systems consider email table-stakes for approval workflows. `[NOTE FOR PM: the deferral most likely to be challenged by a reviewer who knows the domain.]`"
- **Addendum §1.1:** the full comparable evidence (Zoho People email + push; 48-hour reminder guidance) and the "worst of both" rejection of the feature-flag variant.

The counter-evidence is not confined to the memlog. A reader of the PRD alone encounters it, labelled as a budget-driven departure rather than a neutral choice. This is the model outcome, not a failure.

## Question 3 — The facilitator's miscount (claimed 10 assumptions / 6 PM notes; actual 7 / 5): should it stay out of both documents?

**Yes — it is correctly confined to the memlog (entry 25) and appears in neither `prd.md` nor `addendum.md`.**

The miscount is an audit fact about the facilitator's own process, recorded (per the entry) because the PRD's SM-7 concerns assumptions being accurately surfaced. It has no place in a requirements document or its addendum.

**Confirming the skill's rule that audit and override information never goes in the addendum:** the addendum's own scoping statement fixes its contents to exactly three kinds — "**rejected alternatives** ... **research grounding** ... and **technical-how** that belongs to Architecture or the ERD" — and states plainly "Nothing here is a requirement. Nothing here is a domain rule." Audit/process/override material is outside that charter by construction. The reconciliation confirms the rule held in practice:

- Entry 25 (miscount) — audit — is in neither document.
- Entry 2 (`uv` unavailable → `python3`) — override — is in neither document.
- Entry 24 (reviewer-gate results) — audit — is in neither document.

All three audit/override items stayed in the memlog. The addendum contains no audit or override content.

## Question 4 — Decisions in the PRD or addendum that appear NOWHERE in the memlog (the reverse failure)

Three undocumented decisions were found — choices present in a derived artifact with no corresponding memlog entry. None is severe, but all are decisions a strict decision-record should have logged:

1. **PRD §8 — the selection of NFR-03, NFR-04, NFR-07, NFR-08 as "the four this PRD funds most heavily," on the judgment that they are the ones a technical discussion would probe.** This is an explicit, self-described deliberate choice ("That alignment is deliberate and unverified"), yet no memlog entry records picking these four or the reasoning. The memlog only notes "21 NFRs" carried in (entry 3).

2. **Addendum §2.4 — the decision NOT to adopt the employee-side, request-time team calendar (the Keka pattern).** The memlog (entry 14) records adopting the manager-side inline calendar but is silent on rejecting the employee-side variant. The rejected alternative is documented only in the addendum, not in the decision log.

3. **Addendum §1.1 — the rejection of the "email-behind-a-feature-flag" variant** as "the worst of both." The parent decision (in-app only) is well documented in the memlog (entries 6, 13, 16), but this specific sub-variant rejection is not. Minor — an elaboration of a logged decision rather than a free-standing one.

Borderline, judged adequately traced (not counted as undocumented):
- **DR-14 / FR-09 note — "Approved is terminal," resolving the BR-05 contradiction.** Not logged as its own memlog entry, but it is Module 1 decision D-07 carried in (entry 3 records D-01..07), and it is fully documented in addendum §1.4. Traceable via provenance.
- **Addendum §2.3 — LeaveFlow refuses rather than warns on a negative projected balance.** Framed as "a deliberate difference," but it is dictated by FR-08's specified behavior (Module 1), not a fresh PRD choice.
- **Open Questions OQ5, OQ6, OQ7** (mid-year policy change; zero-working-day request; holiday calendar changing under a request). These are deferrals, not decisions; entry 29 records the OQ restructure and §11 attributes the edge-case set to `review-edge-cases.md`. Surfaced items rather than decisions, so out of scope for this question.

---

*Report only. This audit changed nothing in `prd.md`, `addendum.md`, or `.memlog.md`, and proposes no new requirements, rules, assumptions, invariants, or scope.*
