# Editorial Review — PROSE

**Target:** `architecture.md` (LeaveFlow — Solution Architecture)
**Reviewer role:** Clinical copy-editor. Content is sacrosanct — this review changes only how ideas are expressed, never the ideas. No edits were applied to the source file.
**Date:** 2026-07-10
**Reader type:** humans (human-facing solution-architecture document; companion to a terse invariant contract)

## Verdict

Strong, confident, precise technical prose that mostly earns its own claims. The substantive defects are a single wrong cross-reference and pervasive casing drift on glossary terms; the rest are one superlative over-claim, a mixed British/American spelling seam, and two small filler phrases. The load-bearing mathematical claim in §6 (monotonicity) is stated **correctly and at exactly the right strength** — see the dedicated check below.

---

## Suggested fixes

| Original Text | Revised Text | Changes |
|---------------|--------------|---------|
| (§1) This turned out to be the deepest problem in the system, and §5 is about it. | This turned out to be the deepest problem in the system, and §6 is about it. | **Cross-reference error (highest priority).** The sentence closes the "year boundary" paragraph, and the year boundary is treated in **§6** ("The year boundary, and a hole in the requirements"). §5 is "The balance model." A manager tracing the reference lands on the wrong section. |
| (§4) PostgreSQL also permits the single strongest move in this architecture, and it costs nothing: | PostgreSQL also permits one of this architecture's strongest moves, and it costs nothing: | **Over-claim.** "the single strongest move" is an unfalsifiable superlative; the pessimistic row lock (`AD-3`) is at least as load-bearing to `SM-1`. Downgrading the uniqueness claim removes something a reviewer can challenge aloud while keeping the force. |
| (§6.1, §6.3, §7) "an employee stands at Accrued 12…"; "the manager **rejects** the request"; "the manager **approves** it"; "that employee's balance"; "an employee with no manager"; "named as a manager by an active employee" | Capitalize the glossary terms: "an **Employee** stands at…"; "the **Manager** rejects…"; "the **Manager** approves it"; "that **Employee's** balance"; "an **Employee** with no **Manager**"; "named as a **Manager** by an active **Employee**" | **Glossary-term casing drift (systematic).** The PRD fixes **Employee** and **Manager** as defined terms. The document capitalizes them in formal contexts ("A Manager may decide…", "independently per Employee and Leave Type") but lowercases them in narrative (§6.1 worked example, §6.3, §7). §6.3 even mixes both castings in one sentence: "independently per Employee and Leave Type … that employee's balance." Standardize to capitalized. Instances at lines 230, 234, 235, 264, 303. |
| (§6.1) "they stay reserved against their own leave year"; (§6.2) "running it twice against the same leave year"; (§6.3) "to *downstream* leave years" | "their own **Leave Year**"; "the same **Leave Year**"; "downstream **Leave Years**" | **Glossary-term casing drift.** "Leave Year" is a defined term and is lowercased everywhere it appears (lines 226, 251, 264), while sibling terms (Leave Type, Company Holiday, Cancellation Request, Leave Request, Audit Entry) are capitalized. Bring it in line. |
| (§6.3) "generalising a rule"; (§10) "`AD-19` generalises the rule"; (§6.3) "The PRD names the behaviour" | "generalizing"; "generalizes"; "behavior" | **Mixed spelling convention.** The document's baseline is American (organization, serialize, serialized, materialized, Authorization). "generalising / generalises / behaviour" are the only British spellings; normalize to -ize / -or. Lines 264, 266, 335. |
| (§8) `DR-16` and `SM-4` require **exactly one** audit entry per state transition | `DR-16` and `SM-4` require **exactly one** **Audit Entry** per state transition | **Glossary-term casing drift.** "audit entry" is lowercased here (line 307) but capitalized two sentences later ("defines an Audit Entry as…", line 309) and again in §10. Capitalize for consistency. Also line 309: "the rollover transitions no leave request" → "no **Leave Request**". |
| (§2) so LeaveFlow has no outbound integrations at all — a fact worth stating, because it is why the architecture needs no adapter layer, no message bus, and no retry semantics. | so LeaveFlow has no outbound integrations at all — which is why the architecture needs no adapter layer, no message bus, and no retry semantics. | **Throat-clearing.** "a fact worth stating, because it is why" narrates the act of stating instead of stating. "which is why" delivers the same causal link without the meta-commentary. |
| (§6.3) The PRD names the behaviour and no table. | The PRD names the behavior but not a table. | **Awkward zeugma + spelling.** "names the behaviour and no table" forces one verb across a positive and a negative object and reads as a stumble; "but not a table" is clean. (Also folds in the British→American spelling fix.) |

### Lower-priority / optional

| Original Text | Revised Text | Changes |
|---------------|--------------|---------|
| (§5.2) **The `CHECK` constraint is a backstop, not a gate.** This distinction is load-bearing. | **The `CHECK` constraint is a backstop, not a gate** — and the distinction is load-bearing. | Minor. "This distinction is load-bearing." as a standalone sentence restates that the prior sentence matters without adding content. Folding it in keeps the emphasis and drops the throat-clear. Optional — the emphasis may be intentional voice. |
| (§0) Requirement identifiers (`FR-nn`), domain rules (`DR-n`), non-functional requirements (`NFR-nn`) and success metrics (`SM-n`) are those of the [PRD] … and Module 1, used unchanged. | Consider adding business rules (`BR-nn`) and design decisions (`D-nn`) to the provenance list. | Query. The document later cites `BR-05` (§12) and `D-05` / `D-06` (§4) as upstream identifiers, but §0 declares provenance only for FR/DR/NFR/SM. A reader meeting `D-05` in §4 has not been told which family it belongs to. |

---

## Requirement-identifier audit

Every cited identifier was checked for consistent usage and formatting. **Result: internally consistent within each family; no defects.**

| Family | Format observed | Consistent? | Notes |
|--------|-----------------|-------------|-------|
| `FR-nn` | two-digit, zero-padded (FR-02 … FR-15) | Yes | — |
| `NFR-nn` | two-digit, zero-padded (NFR-01 … NFR-21) | Yes | — |
| `D-nn` | two-digit, zero-padded (D-05, D-06) | Yes | Not declared in §0 provenance (see query above). |
| `BR-nn` | two-digit, zero-padded (BR-05) | Yes | Single occurrence (§12). Not declared in §0 provenance. |
| `DR-n` | no zero-pad; letter suffixes lowercase (DR-1 … DR-16, DR-2a, DR-7a) | Yes | Suffix style (2a, 7a) is consistent. |
| `SM-n` | no zero-pad (SM-1 … SM-8) | Yes | — |
| `AD-nn` | no zero-pad (AD-1 … AD-22) | Yes | §0's "twenty-two … (`AD-1` … `AD-22`)" matches the maximum cited. Numbers AD-7/AD-14 are uncited in prose, which is expected (full set lives in the spine). |
| `UJ-n` | — | N/A | Never cited in this document; nothing to verify. |

**Formatting observation, not a defect:** zero-padding differs *between* families — FR/NFR/D/BR pad to two digits (FR-02), while AD/DR/SM do not (AD-2, DR-3). Each family is internally uniform and the split is presumably inherited from upstream numbering, so no change is recommended; noted only so the split is a known decision rather than an oversight.

---

## §6 monotonicity claim — dedicated strength check

The manager flagged this as the claim most likely to be questioned aloud and asked that it be "exactly as strong as it should be and no stronger." It is.

- The term used is **"monotonically non-decreasing"** (§6.2), which is precise. Because Approval leaves `Available` unchanged (a transfer Reserved→Consumed nets zero against `Available = Accrued − Consumed − Reserved`) and only Rejection/Cancellation move it — upward — the correct word is *non-decreasing*, not *increasing*. Had the text said "increasing," it would have been too strong. It does not.
- The claim is correctly **scoped** three ways: "Under leave-request transitions this is safe," "as year Y's pending requests resolve," and "carry-forward is only ever **topped up** — never clawed back." None of these overreaches.
- Critically, §6.3 **explicitly retracts the broader reading**: "The monotonicity argument above is **true only for leave-request transitions**, and the first draft … over-claimed it." It then names the two paths (`FR-10` holiday deletion, `FR-06` RECALCULATE) that *do* lower `available(Y)`, and routes them to `AD-19`. The document polices its own over-claim rather than leaving it standing.
- The worked arithmetic in the §6.1 table is sound (Available 12−8−3 = 1; the reject branch loses 3; the approve branch overstates by 3), so the motivating example does not overstate the danger either.

No wording change is warranted here. This is the strongest passage in the document.

---

## Things checked and found clean

- **Restatement of the prior sentence:** the prose is tight; no genuine sentence-level redundancy found. The "a number that is wrong, and believed" echo (§1 ↔ §6.1) is a deliberate, effective motif, not padding.
- **Earned jargon:** "functional core / imperative shell" (attributed to Bernhardt), "time-of-check-to-time-of-use," and "pessimistic row lock" are all either attributed or immediately unpacked by context.
- **Tense/voice:** consistent present tense for the design, past tense for historical decisions ("was rejected," "was chosen"). No drift.
- **Table vs. prose:** the existing tables (§4.1 version traps, §6.1 rule collision, §12 traceability) are the right call, and the §1 "four hard things" and §3 rejected-alternatives are correctly left as prose — a table there would kill the rhetorical build. No conversion recommended in either direction.
- **Hedging:** appropriately minimal. "Indian statute generally requires…" (§11) is a correct hedge, not a weak one. The only two filler phrases are handled above ("a fact worth stating," "This distinction is load-bearing").
- **Overlong sentences:** the TypeScript-pin sentence (§4.1) and the `leave_request.status` sentence (§9) are long but parse cleanly on one read; not flagged.
