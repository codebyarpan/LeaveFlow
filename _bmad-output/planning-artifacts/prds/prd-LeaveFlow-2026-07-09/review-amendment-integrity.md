# Amendment Integrity Review — PRD LeaveFlow (2026-07-09)

**Reviewer stance:** pedantic, adversarial. Scope of legitimate change = the eight approved items (A1–A5, B1–B2). Anything beyond them is a defect, and anything already-final that the amendment broke is a defect. Line numbers refer to `prd.md`.

**Overall verdict:** ONE hard FAIL (Check 3). All other checks PASS, several with residual/pre-existing notes that are not attributable to the amendment.

---

## 1. IDENTIFIER INTEGRITY — PASS

- 20 FR headings present, each unique, `FR-01`…`FR-20` with none missing, none renumbered, none reused (grep: exactly 20 `#### FR-NN` headings).
  - Behavioral-not-numeric ordering preserved (e.g. FR-17 at line 184, FR-06 at 203, FR-10 at 221) — expected per §4.1 note.
- No functional `FR-21+`. The single `FR-21` regex hit is inside **`NFR-21`** (line 577, a non-functional requirement) — false positive.
- All domain rules present: `DR-1, DR-2, DR-2a, DR-3, DR-4, DR-5, DR-6, DR-7, DR-7a, DR-8, DR-9, DR-10, DR-11, DR-12, DR-13, DR-14, DR-15, DR-16` (18 total, lines 458–489). Nothing missing or added; `DR-2a` and `DR-7a` both present.

## 2. COUNT INTEGRITY — PASS

- "Twenty functional requirements" is consistent: §7 (line 510 "Twenty functional requirements", 512), §9 (line 593 "Eighteen enumerated … plus `FR-19` and `FR-20`" = 20), §10 (line 608), SM-8 (line 624 "all twenty … `FR-01`–`FR-20`"), SM-C1 (line 629). §0 (line 14) states the count by enumeration (FR-01–FR-18 carried + FR-19/FR-20 new = 20).
- SM-8's denominator (`FR-01`–`FR-20`) still holds — all 20 identifiers exist (Check 1).
- The separate NFR count "twenty-one" (§8 lines 550, 552) is a distinct, correct figure — not confused with the FR count. No drift introduced by the amendment.

## 3. NO NEW BEHAVIOR — **FAIL (headline finding — flagged loudly)**

The amendment introduced an **Admin-facing surface that no functional requirement grants**, and its wording exceeds what was approved.

**Evidence.**
- FR-10 (line 231): "…the case is recorded in **a durable store the Admin can read and resolve**."
- FR-06 (line 214): "…the case is recorded in **the durable store the Admin reads and resolves**."

**Why this is a defect (two-fold):**

1. **"resolve / resolves" exceeds the approved change.** Approved item A3 authorized a *"durable **Admin-readable** store"* — read only. The implemented text adds **"resolve"/"resolves"**, which takes *the case* as its object ("the Admin can read [the store] and **resolve** [the case]"). That is a resolution **workflow**, not a read. It was not approved.

2. **No functional requirement provides the surface — read *or* resolve.** No FR grants the Admin any capability over refused-recalculation cases:
   - `FR-16` grants Admin read of the **audit log** — but this store is explicitly a *different, separate* store (it is neither the audit log nor the FR-07 rollover log).
   - `FR-11`'s Admin dashboard is scoped to "Employees on approved leave today, and Pending request count" (line 360) — not refused-recalc cases.
   - `FR-04`/`FR-05`/`FR-06`/`FR-10` are the config CRUD FRs; none exposes a "view/resolve refused recalculations" surface.
   The store is referenced **only inside two config-FR consequences**, with **no FR granting a testable Admin read/resolve capability** over it. The PRD therefore now *requires* an Admin screen/endpoint/workflow that no requirement delivers — a dangling obligation.

**What is NOT a new-behavior problem (checked and cleared):**
- The FR-06 *mirror* consequence implies no new endpoint beyond the store: the recalc-on-policy-change capability is already granted by FR-06's prior consequence (line 213, "requires the Admin to choose explicitly whether existing balances are recalculated…").
- The FR-10 recalculation is already granted by FR-10's pre-existing consequences (lines 229–230, recalc of Pending / future-Approved on holiday change).
- The "extended to later Leave Years" and "per Employee + Leave Type" and "rest of operation proceeds" clauses match A3 exactly and add no capability.

**Recommended fix:** either (a) drop "and resolve/resolves" to match the approved read-only scope, or (b) add a functional requirement that actually grants the Admin a "view and resolve refused-recalculation cases" surface with testable consequences. Until one of these lands, the PRD is internally incomplete.

## 4. GLOSSARY DISCIPLINE — PASS (minor notes)

- **`Email Address`** and **`Full Name`** are **bolded at every occurrence**: Email Address (lines 88, 93, 191×2); Full Name (lines 88, 94, 190).
- **Defined before first use.** Both are defined in §3 (lines 93, 94). First body-section uses are FR-17 (lines 190–191), well after §3. Within §3 the Employee entry (line 88) references them before their own entries — normal glossary cross-referencing, not a use-before-definition in the body.
- **No alternative term is substituted** for these specific fields anywhere they are referenced; the exact bolded terms are used each time.
- Minor (not violations):
  - `"profile field(s)"` — pre-existing plural at line 189 ("edit their own **profile fields**") vs. amendment-added singular at line 190 ("the only **profile field** … is their **Full Name**"). This is a category term, not a synonym for a glossary entry; mild redundancy but no contradiction (189 governs *whose* profile, 190 governs *which* field).
  - `"identity"` — used descriptively in the new glossary prose ("It is an **identity**, not a contact channel", line 93; "the human-readable **identity** of an Employee", line 94) and pre-existing at lines 123, 135. Common-noun usage, not a defined-term synonym for Email Address / Full Name; acceptable.
  - Full Name's entry says it is "shown wherever an Employee is listed (`FR-19`)", but FR-19's consequence (line 387) says "identifies the **Employee** and their **Department**" without the term "Full Name." Cross-ref target is valid; wording is imprecise. FR-19 was outside the amendment's scope, so not a defect — noted only.

## 5. INTERNAL CONSISTENCY OF A5 — PASS (one residual, low severity, pre-existing)

- §1 Vision narrowed to "Every **Leave Request** state change is attributable to an actor and a moment" (line 22). Correct.
- All requirement-level attribution statements are already scoped to Leave Request transitions and remain consistent — and were correctly *not* touched:
  - FR-16 (line 338): "every **Leave Request** state transition".
  - DR-16 (line 489): "Every **Leave Request** state transition…".
  - NFR-19 (cited at §8 line 550 and DR-16 line 489): "every transition records who and when" — in context, Leave Request state transitions. Untouched per A5.
- **Residual:** SM-4's **title** "Every leave action is attributable" (line 617) uses the looser phrase "leave action," which now reads broader than the narrowed Vision. However, SM-4's measurable **target** is correctly scoped ("Audit Entry count equals state-transition count… each entry names an actor and a timestamp"), so **no testable requirement contradicts** the Vision. A5 was explicitly scoped to §1 only (and named FR-16/NFR-19 as untouched); SM-4 was not in scope, so this title looseness is **pre-existing, not amendment-introduced.** Low severity; worth a one-word tidy ("leave action" → "Leave Request state change") if the title is ever reopened.

## 6. INTERNAL CONSISTENCY OF A2 — PASS

- FR-07 (line 251) now reads: "It records its execution in **a separate append-only rollover log, not among Audit Entries**, because it transitions no **Leave Request** (§3, `SM-4`)." The old "Its Audit Entries record the actor SYSTEM (FR-16)." is gone.
- No residual rollover→Audit-Entry or rollover→SYSTEM language anywhere:
  - All five `SYSTEM` occurrences (lines 314, 342, 489, 655, 671) are the **managerless AUTO_APPROVED_NO_MANAGER auto-approval** actor — correctly retained and unaffected.
  - Glossary Audit Entry (line 115), FR-16 (line 342), DR-16 (line 489): all scoped to Leave Request transitions; none attributes the rollover to an Audit Entry.
- §11 idempotence entry closed (line 649: "*Idempotence is settled:* the rollover assigns derived values rather than accumulating them, so a second run … is a no-op"), and it repeats the "own append-only rollover log rather than among Audit Entries" framing consistently.

## 7. NO ASSUMPTIONS (§12 / SM-7) — PASS

- No live `[ASSUMPTION: …]` tag exists on any inference. The three `[ASSUMPTION` string hits (lines 16, 623, 660) are all **meta references in backticks** — §0 describing the convention, SM-7 defining the metric, §12 asserting the tag's absence. The self-referential sentence at line 660 necessarily contains the token it denies, which is expected.
- None of the amended passages introduced an assumption tag. §12's claim and SM-7 hold.

## 8. §11 "None. No open question blocks implementation" — PASS

- The amendment reopened nothing. §7.3 is now a "**Resolved.**" paragraph (line 538) consistent with the "None" claim (the seed value is fixed as a decision). §11's bullets are consistent with A2 (idempotence settled, line 649) and A4 (mark-read closed, line 651).
- **Pre-existing observation (out of amendment scope):** a live `[NOTE FOR PM]` remains at §7.4 line 542 (email-delivery deferral). §0 defines `[NOTE FOR PM]` as "Tensions that need a human decision," which is in mild latent tension with §11's "None" / §12's "no assumption remains." This marker predates the amendment (B2 targeted only §7.3), so it is **not** an amendment defect — flagged only for completeness.

## 9. Remaining `[NOTE FOR PM]` markers / §0 convention — PASS

- Exactly one live marker remains: §7.4 line 542. It is **pre-existing** and **outside** the amendment's approved scope; B2's target (§7.3) was correctly converted to "Resolved." with no marker left there.
- §0's description of the convention (line 16) **still matches reality**: the `[NOTE FOR PM]` convention is defined and has one live instance. No mismatch introduced.

## 10. Dangling cross-references — PASS

Every cross-reference in or around the amended text resolves to existing content:
- DR-7 new paragraph ↔ DR-7a (both present, 471/474); FR-10 (231) → DR-5, FR-06; FR-06 (214) → FR-10; DR-5 (466) → FR-06, FR-10; FR-07 (251) → (§3, SM-4); Email Address → FR-01/FR-04/FR-14; Full Name → FR-19/FR-17; FR-17 (191) → FR-04; §7.3 (538) → FR-06/FR-13; §11 (649/651) → FR-07/FR-14.
- **No section points at replaced text.** The old FR-07 "Audit Entries record actor SYSTEM" line is fully removed and nothing still references it.
- Minor (already noted under Check 4): Full Name → FR-19 is a valid target but FR-19's prose does not use the term. Not dangling.

---

## FAIL summary (most severe first)

1. **Check 3 — Ungranted Admin surface + wording beyond approval.** FR-10 line 231 "a durable store the Admin can **read and resolve**" and FR-06 line 214 "the durable store the Admin **reads and resolves**": (a) "resolve/resolves" exceeds the approved *"Admin-readable"* (read-only) scope of A3, introducing a resolution workflow; (b) **no functional requirement** grants the Admin any read or resolve capability over this new store (FR-16's audit-log read is a different store; FR-11's Admin dashboard does not cover it). The PRD now requires an Admin surface no FR provides.

All other checks (1, 2, 4, 5, 6, 7, 8, 9, 10) PASS. Residuals noted under Checks 4, 5, 8, 9 are pre-existing / out-of-scope and are **not** attributable to the amendment.
