# Editorial Review — Structure

**Document:** `architecture.md` (LeaveFlow — Solution Architecture)
**Review type:** Structural (cuts, merges, reorderings). Run before prose copy-edit.
**Reviewer role:** Structural editor.
**Date:** 2026-07-10

---

## Document Summary
- **Purpose:** Explain *why* LeaveFlow is built the way it is — the reasoning, rejected alternatives, and diagrams that the binding spine (`ARCHITECTURE-SPINE.md`) deliberately omits.
- **Audience:** The assigning manager who evaluates the trainee's work, and a technical interlocutor in a defend-it-aloud discussion.
- **Reader type:** humans (comprehension aids preserved).
- **Structure model:** Explanation (Conceptual) — abstract → concrete, scaffolding. Chosen over Pyramid because the document's job is to *build* an argument a fresh reader can follow, not to lead with a verdict.
- **Current length:** ~2,600 words across 13 top-level sections (§0–§12).

### Framing note that governs every recommendation below
This document's companion carries the invariants with **no rationale**, so rationale is this document's entire reason to exist. The skill's default "brevity is clarity" bias is therefore **overridden**: nothing here is cut *merely* for being rationale. Every CUT/CONDENSE below is justified by true redundancy, misordering, or burial — not by length. The document is, on the whole, unusually well built. The recommendations are targeted, not a teardown.

---

## Recommendations

### 1. [MOVE] — §10 "Defects found in the upstream documents" up to immediately after §8, before §9 Operations
**Rationale:** For a manager grading a trainee, "I audited your PRD and found four defects" is the strongest competence signal in the whole artifact — and it currently sits at position 11 of 13, *behind* Operations housekeeping (CLI jobs, `.env` handling, seed data). The analytical sections that surface the defects run §5 (balance) → §6 (year boundary) → §7 (authz) → §8 (audit); §10 is their culmination and should land there, while it is still hot, before the low-stakes tail (§9 Operations, §11 Risks, §12 Traceability). Placing it right after §8 also means every defect it lists has already been explained, so the move incurs **zero comprehension debt** — unlike a full promotion to the top, which would force the reader to meet `DR-7`/`FR-07` before they are defined.
**Also do:** add a one-line teaser to §1 so the achievement is signalled early — e.g. after the "four places" framing: *"This stage also found four defects in the upstream documents; §10 collects them."* This front-loads the signal without the comprehension cost.
**Impact:** reorder only; +~15 words for the teaser.
**Comprehension note:** Improves it — the reader hits the payoff at peak context instead of after the plumbing.

### 2. [MOVE] — §6.4 "Lifecycles" up to open §5 (as the balance model's first subsection, before "5.1 Three quantities")
**Rationale:** The lifecycle state machines *define the vocabulary the rest of the document has already been spending.* By §6.4 the reader has, for two full sections, been reading `SET status = CANCELLED WHERE id = r AND status = PENDING` (§5.2), "the manager **rejects** the request… Reserved drops to 0" (§6.1), and "**Approval** is a transfer from Reserved to Consumed" (§6.2). The states Pending/Approved/Rejected/Cancelled, the reserve→consume→release transitions, and the Cancellation-Request-as-separate-entity concept (`DR-14`, `AD-13`) are all *foundations* — they belong before the balance algebra that manipulates them, not appended to the end of the year-boundary argument. This is textbook missing-scaffolding: the diagram that anchors the mental model arrives after the model has been used.
**Bonus:** removing §6.4 lets §6 end on §6.3's genuine punch ("that employee's balance is left entirely untouched, a flag is raised, and the rest of the operation proceeds") instead of trailing off into two state diagrams.
**Impact:** reorder only.
**Comprehension note:** Significant improvement — front-loads the mental model per the skill's "overview before details" principle.

### 3. [FIX / QUESTION] — §1 broken forward-reference: "and §5 is about it"
**Quote:** > "The year boundary is where leave systems break. … This turned out to be the deepest problem in the system, **and §5 is about it.**"
**Rationale:** The year boundary is **§6** ("The year boundary, and a hole in the requirements"). §5 is "The balance model." In a document that may be defended aloud, a reader (or evaluator) who follows the pointer lands in the wrong section, on the single problem the author calls the deepest. This is a correctness defect, not a style nit. Change "§5" → "§6".
**Impact:** 1 character; disproportionate credibility cost if left.
**Comprehension note:** Pure fix.

### 4. [MOVE / CONDENSE] — Reconcile §1's "four hard problems" with the body's delivery order, and add section pointers
**Rationale:** §1 promises four hard problems in order — (1) balance is three numbers, (2) day count is not date subtraction, (3) authority from a relationship, (4) the year boundary. The body delivers them out of that order (balance → §5, day-count → threaded through §3–§4, authority → §7, year-boundary → §6), and only the fourth carries a pointer (the broken one from Rec 3). Give each of the four a correct trailing pointer:
- "A balance is three numbers…" → §5
- "A day count is not a date subtraction…" → §3–§4 (where the functional core makes the single implementation *structural*)
- "Authority comes from a relationship…" → §7
- "The year boundary…" → §6
This turns §1 into a working table of contents for the argument and removes the friction of the promised-vs-delivered order mismatch. No prose reordering of the body is required if the pointers are added.
**Impact:** +~8 words; large navigation gain.
**Comprehension note:** Improves scanning and defensibility.

### 5. [CONDENSE] — §10's restated detail down to an index; keep the consolidation, cut the verbatim recap
**Rationale:** Three of §10's four items re-narrate material the body already carries in full:
- §10.1 (`FR-07` vs glossary/`SM-4`) restates §8.
- §10.3 (`FR-10` too narrow, no store) restates §6.3.
- §10.4 (`DR-7`/`DR-7a` don't compose) restates §6 — it literally ends "**§6 above.**"
Only §10.2 (`FR-14` mark-read has no requirement) is *new* — it appears nowhere else, which is itself a small burial worth noting.
The consolidation earns its place (a single "PRD edits required" ledger is valuable to the evaluator and to upstream tracking), so **do not cut the section** — but reduce items 1/3/4 to one-line pointers ("Resolved by `AD-8`; see §8") rather than re-explaining the mechanism. Let the body own the detail and §10 own the list.
**Impact:** ~60–80 words.
**Comprehension note:** None lost — the detail remains in-body; this removes duplication, not information.

### 6. [CUT] — Closing italic footer duplicates §0
**Quote (footer):** > "*Companion artifacts: `ARCHITECTURE-SPINE.md` is the binding contract; `api-contracts.md` is the API surface; `.memlog.md` is the append-only decision log; `reviews/` holds the six independent reviews that shaped the spine.*"
**Quote (§0):** > "Its companion, `ARCHITECTURE-SPINE.md`, states **what** must be true… The append-only decision log for the run is `.memlog.md`. The six independent reviews that shaped the final spine are in `reviews/`."
**Rationale:** The footer re-describes three of the four artifacts §0 already introduced. The only genuinely new pointer is `api-contracts.md`. Either cut the footer entirely and add `api-contracts.md` to §0's inventory, or reduce the footer to a bare link list without re-describing each file. One source of truth for "what the companion files are."
**Impact:** ~40 words.
**Comprehension note:** None — §0 does the orienting job better and earlier.

### 7. [QUESTION] — §8 title "a second contradiction" vs §6 title "a hole in the requirements"
**Rationale:** "§8. Audit, and a **second** contradiction" implies a numbered first. The prior finding (§6) is framed as a "**hole**"/gap, not a contradiction; §10 also mixes "gap," "contradiction," and "too narrow." If the author intends a running tally of upstream findings, make the labels consistent (e.g. "first/second defect"); if not, drop "second" to avoid an antecedent the reader must go hunting for. Author's call — this is terminology, not structure.
**Impact:** negligible words; consistency gain.
**Comprehension note:** Minor.

### 8. [PRESERVE] — §6.1 → §6.2 → §6.3 build order; the worked example; §5.1's `consume_direct` bug; §11 legal-forfeiture risk
**Rationale (explicit keeps, since a brevity-first pass would be tempted to trim these):**
- **§6's internal order is correct** for a fresh reader: collision (with the concrete Accrued 12 / Consumed 8 / Reserved 3 example and the two-rule failure table) → resolution (`min(cap, available)`, derived-not-accumulated, monotonicity, idempotence-for-free) → where the argument breaks (`FR-10`/`FR-06`, `AD-19`/`AD-20`). Problem → solution → limits is exactly right; do not reorder. The only change §6 needs is losing §6.4 to §5 (Rec 2).
- **The worked numeric example in §6.1** is the comprehension anchor for the hardest idea in the document. Keep in full.
- **§5.1's adversarial-review bug** ("a single shared `consume(days)`… **crashes on the first managerless auto-approval**") is a live defensibility asset; keep.
- **§11's first risk** (earned leave above cap forfeited vs Indian statute requiring encashment) is a compliance flag that reads as maturity; keep where it is.
**Impact:** 0 words (cost of *not* cutting ~250 words a length-first editor might have removed).
**Comprehension note:** These are the load-bearing rationale the spine cannot carry.

### 9. [QUESTION] — §12 Traceability is a partial duplicate of the spine's map
**Rationale:** §12 explicitly reproduces "the load-bearing rows" of the spine's *Capability → Architecture Map*. It is the weakest-earning section (a reference lookup that lives authoritatively elsewhere). It is defensible as an at-a-glance for an evaluator who won't open the spine — so keep it — but if length ever becomes a constraint, this is the first candidate to reduce to a pure pointer. Flagging, not cutting.
**Impact:** potential ~130 words if ever cut; recommend keep.
**Comprehension note:** Mild convenience for the evaluator; low risk if trimmed.

---

## Answers to the specific questions posed

- **Section ordering:** Sound at the top level (Explanation model: context → paradigm → tech → balance → year boundary → authz → audit → ops → risks → traceability). Two ordering faults: (a) §6.4 Lifecycles is scaffolding placed *after* the sections that use it — move to open §5 (Rec 2); (b) §10 lands after Operations housekeeping instead of after the analysis that earns it — move to after §8 (Rec 1). §1's promised order of the four problems isn't mirrored by delivery and lacks pointers (Rec 4).
- **Redundancy across sections:** Two true redundancies — §10 items 1/3/4 restate §8/§6.3/§6 (Rec 5), and the footer restates §0 (Rec 6). The re-derivation of "approval leaves Available unchanged" in §6.2 is legitimate reinforcement in service of the monotonicity proof, **not** redundancy — keep it.
- **Does every section earn its place?** Yes, with one soft exception: §12 Traceability partly duplicates the spine (Rec 9). Everything else pulls weight; nothing should be cut wholesale.
- **Is §6's argument built in the right order for a fresh reader?** Yes — collision → resolution → breakage is the correct pedagogical build, and the worked example is well placed. The one flaw is that its *vocabulary* (the lifecycles) is defined at the end (§6.4) instead of before §5 uses it. Fix by moving §6.4 up (Rec 2), not by touching §6.1–§6.3.
- **Is §10 placed where it lands hardest?** No. It is buried at position 11, behind Operations. Hardest landing is immediately after §8 (last defect-surfacing section), plus a one-line teaser in §1 (Rec 1).
- **Anything important buried?** (i) The deepest-problem pointer is not just buried but *wrong* — it points to §5 instead of §6 (Rec 3). (ii) The four-defects headline (Rec 1). (iii) The lifecycle mental model (Rec 2). (iv) §10.2's `FR-14` finding exists *only* in §10 — the sole defect with no in-body home; worth a sentence in §9 Operations or §7 where notifications live.

---

## Summary
- **Total recommendations:** 9 (2 MOVE, 1 FIX, 2 CONDENSE, 1 CUT, 2 QUESTION, 1 PRESERVE + Rec 4 hybrid move/condense).
- **Estimated reduction:** ~140–180 words net (mostly de-duplication in §10 and the footer); the two highest-value changes (Recs 1 and 2) are **reorderings that cost nothing**. This is deliberately a low-cut review — the document's rationale is its purpose.
- **Meets length target:** No target specified; reduction is incidental, not the goal.
- **Comprehension trade-offs:** None. Every recommendation improves or preserves comprehension; no cut sacrifices reader understanding for brevity. The two moves (§10, §6.4) are net comprehension *gains*.
