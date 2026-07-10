---
title: "LeaveFlow PRD — Open-Item Load Review"
status: review
created: 2026-07-09
reviewer: open-items audit
scope: "Deduplication and reclassification of §11 Open Questions, §12 Assumptions Index, and [NOTE FOR PM] callouts"
---

# LeaveFlow PRD — Open-Item Load Review

## 0. Hard boundary of this review

The open-item count may be reduced **only** by:
- **(a) deduplication** — two items that are the same item, one copy removed; or
- **(b) reclassification** — an item filed in the wrong category, moved to its correct home.

It may **not** be reduced by **invention** (deciding an open question) or **suppression** (deleting a genuine unknown). Every removal below preserves its item's content in exactly one surviving home. Where an item cannot be removed by (a) or (b), it is left and said so.

## 1. Baseline inventory (measured, not assumed)

The task brief states "10 [ASSUMPTION] tags, 6 [NOTE FOR PM] callouts, 10 Open Questions, and A-01..A-09." Two of those figures do not survive a grep of `prd.md`:

| Item class | Brief's count | Actual | Detail |
|---|---|---|---|
| Inline `[ASSUMPTION: A-xx]` tags | 10 | **7** | A-01, A-02, A-03, A-04, A-06, A-07, A-09. **A-05 and A-08 carry no inline tag** — they appear inline only as `A-05`/`A-08` references inside Open Questions 3 and 5. |
| `[NOTE FOR PM]` callouts | 6 | **5** | Lines 82, 201, 230, 231, 452. The 6th grep hit is the legend sentence at line 16 ("Tensions… are marked `[NOTE FOR PM]`"), not a callout. |
| Open Questions (§11) | 10 | 10 | OQ1–OQ10. Correct. |
| Assumptions Index (§12) | A-01..A-09 | 9 | Correct. No A-10 (register declares A-10 obsolete). |

Working **open-item load N = 9 assumptions + 5 NOTE FOR PM + 10 Open Questions = 24.**
(In the brief's stated figures that would be 26; the 2-item gap is the miscount above, not real items.)

---

## 2. Duplicates (item 1)

The test applied throughout: an **assumption + open-question pair is legitimate** (keep both) when the assumption *picks a value* so build can proceed, and the OQ preserves a *live consequence* that the chosen value does not neutralize. It is a **duplicate** (remove one) when either the "assumption" picks no value (it is an OQ in disguise) or the OQ carries no live consequence the assumption has not already absorbed.

### 2.1 A-05 vs Open Question 3 (proration) — **DUPLICATE. Remove A-05.**

- **A-05** (§12): *"Entitlement accrues in some form; the specification does not state whether monthly or annually granted."*
- **OQ3** (§11): *"Does entitlement accrue monthly or is it granted annually, and how is a fractional result rounded?"*

A-05 **picks no value**. It asserts only "accrual exists in some form" — which `BR-02` already confirms — and then states the real content as an *absence*: "whether monthly or annually is unstated." You cannot key a schema or write proration code from "some form." An assumption that decides nothing is not an assumption; it is an open question wearing an assumption's tag. Its substantive content is identical to OQ3.

This is confirmed by the Module 1 register itself (line 96): *"The FL and accrual entries previously asserted content that BR-01, BR-03, and BR-02 already confirm; both have been narrowed to the genuine uncertainty."* A-05 was narrowed down until nothing decidable remained — i.e., until it became an open question — but was left in the assumptions table.

**Resolution:** A-05 collapses into OQ3 under both (a) and (b) — same item, and miscategorized. Remove A-05 from §12. The unknown is not suppressed; it survives in full as OQ3, which remains a genuine blocker (§6). Assumptions index 9 → 8.

### 2.2 A-09 vs Open Question 1 (leave year) — **LEGITIMATE PAIR. Keep both.**

- **A-09**: assumes a *specific value* — calendar year, 1 Jan–31 Dec — so the balance table can be keyed and Day-3 work can start.
- **OQ1**: carries a *live, high-consequence alternative* — the April–March financial year — under which "CL and FL lapse on 31 March, carry-forward evaluates at a different boundary, `BR-04` bites on different dates, and the balance table is keyed wrongly."

This is the archetypal legitimate pair. Delete A-09 and you cannot build; delete OQ1 and you have suppressed a genuine unknown (forbidden). The two do different jobs — A-09 is the build-enabling default, OQ1 is the escalation — and the PRD already cross-links them (§12 A-09 → OQ1; `DR-8` → A-09). **Not a duplicate. Keep both.** This pair is the yardstick for the other three.

### 2.3 A-04 vs Open Question 4 (FL name) — **DUPLICATE. Remove OQ4.**

- **A-04**: picks a value (FL = Floater Leave) and absorbs the entire consequence — *"nothing structural depends on the label; only display text changes if it is wrong."*
- **OQ4**: *"What does FL stand for? Research indicates Floater Leave. Cosmetic: display text only. Confirm when convenient."*

The mirror image of 2.2. Here the **assumption is genuine** and the **OQ is the redundant copy**. OQ4 restates A-04's value, A-04's consequence, and adds only "confirm when convenient" — but §12 already exists to surface every assumption for confirmation ("Every `[ASSUMPTION]`… surfaced for confirmation"). Unlike OQ1, OQ4 carries **no live divergent consequence**: there is no alternative expansion of "FL" that changes the build. The assumption has fully closed the item for every purpose except a courtesy confirmation that §12 already schedules.

**Resolution:** OQ4 is a duplicate of A-04 under (a). Remove OQ4 from §11. Nothing suppressed — A-04 and its §12 entry still route FL-name confirmation to the sponsor. Open Questions 10 → 9.

### 2.4 A-08 vs Open Question 5 (mid-year policy change) — **LEGITIMATE PAIR. Keep both.**

- **A-08**: assumes a value — *"Leave Policy is not changed mid-Leave-Year in practice."* This is load-bearing: it **licenses an omission**. Because the change is assumed not to occur, the developer builds no reconfiguration-recalculation path.
- **OQ5**: *"What happens to already-accrued balances when the Admin changes a Leave Policy mid-year? `FR-06` allows the change; nothing defines its effect."*

Distinguish this sharply from 2.1. A-08 is **not** empty — it decides something (don't build the recalc path) and that decision has teeth. OQ5 is the genuine question of what the behavior *should* be if the assumption fails. This is exactly the dual treatment the PRD applies to A-09/OQ1 and defends as correct: assume it away to proceed, *and* escalate it because the assumption is load-bearing. **Not a duplicate. Keep both.**

### 2.5 Duplicates summary

| Pair | Verdict | Action | Basis |
|---|---|---|---|
| A-05 / OQ3 | Duplicate (A-05 is an OQ in disguise) | Remove **A-05** | (a)+(b) |
| A-09 / OQ1 | Legitimate pair | Keep both | — |
| A-04 / OQ4 | Duplicate (OQ4 has no live consequence) | Remove **OQ4** | (a) |
| A-08 / OQ5 | Legitimate pair | Keep both | — |

Note the pleasing symmetry: in one duplicate the *assumption* is the fake (A-05), in the other the *open question* is the fake (OQ4); in each case exactly one item is removed and the unknown survives in its proper home.

---

## 3. Misclassified (item 2)

### 3.1 OQ8 (leave date: date vs UTC timestamp) — **MISCLASSIFIED. Reclassify to Architecture. Remove from §11.**

The PRD tells on itself. OQ8 (line 555): *"Not a domain rule and not treated as one here — it is a representation decision, raised for Architecture (Module 3) to settle explicitly rather than by default."* And the addendum already carries it as `§3.1 — A leave date is a date, not an instant`, complete with the answer: *"Architecture should choose a date type without a time component and state the choice."*

So OQ8 is (i) not a product unknown routed to the sponsor — unlike OQ1/OQ3 it does not ask the assigning manager anything; (ii) an architecture representation decision; and (iii) one whose correct answer is already known and recorded. Filing it in §11 double-books it against addendum §3.1 and mislabels a settled technical decision as an open product question.

**Resolution:** reclassification (b). Remove from §11; its home is addendum §3.1, where it already lives. Not suppressed. Open Questions 9 → 8.

### 3.2 OQ9 (are NFRs evaluated at all?) — **MISCLASSIFIED. Dissolve.**

OQ9 conflates two things:
- A **product/requirements risk**: "all 21 NFRs are engineer-proposed, none confirmed by the assigning manager." This is genuine — but it is **already stated in §8** ("All twenty-one are engineer-proposed and none are confirmed… a fact that is itself a risk"). A risk belongs stated as a risk, not posed as an open question.
- A **process question**: "*If the evaluation is a technical discussion rather than a checklist*, NFR-03/04/07/08 are the likeliest to be probed." That is the same question as OQ10 (evaluation mode).

OQ9 therefore adds nothing to §11 that is not already in §8 (the risk half) or OQ10 (the process half).

**Resolution:** reclassification + dedup. The requirements risk stays in §8 (nothing suppressed — the NFR-unconfirmed fact is preserved there, and §8 should stop pointing to §11 as its "record"); the process half merges into OQ10. Remove OQ9 from §11. Open Questions 8 → 7.

### 3.3 OQ10 (what is the evaluation mode?) — **MISCLASSIFIED. Reclassify to the project plan. Remove from §11.**

*"Requirements checklist, technical discussion, or both. It determines where the remaining hours should go."* This is a question about how the **deliverable will be assessed** and **how to spend the schedule** — a project/process concern of the seven-day learning plan, not a product-specification unknown. It changes nothing about what LeaveFlow is or does. A PRD's open questions are product/domain unknowns (OQ1 leave year, OQ3 proration); "how will my work be graded and where do I spend my last hours" belongs in the project plan / run memlog.

**Resolution:** reclassification (b) to the project plan. Not suppressed — it is a real question, moved to where scheduling decisions live. Open Questions 7 → 6.

### 3.4 OQ2 (EL carry-forward cap + encashment) — open question, risk, or non-goal? **CANNOT be removed. Leave it.**

OQ2 tangles three strands:
1. **A genuine product open question** — "Is carried-forward EL capped, and what happens to the excess?" `DR-7` discards non-carrying-forward days and is silent on an EL cap. This is unresolved, unlike anything else in the document, and is a peer of OQ1/OQ3 in kind (a policy value that changes balances).
2. **A capability already declared a Non-Goal** — encashment (§6). That strand is *already* correctly filed elsewhere.
3. **A compliance risk** — "the system may be non-compliant depending on the state of operation." This has a risk flavor rather than a question flavor.

Test against the boundary:
- Is it a **duplicate**? No. Strand 1 (the cap) is stated nowhere else. §6 holds only strand 2 (encashment non-goal), which is a *different* item.
- Is it **reclassifiable to disappearance**? No. You could move the compliance-exposure *framing* to a risk register, but the underlying product question — cap yes/no, and forfeit-vs-encash on the excess — remains an open question that must be asked. Removing it would be **suppression of a genuine unknown**, which the boundary forbids.

**Resolution: leave OQ2 in §11.** It is precisely the kind of item the boundary protects: a real unresolved product decision with a legal shadow, not a duplicate and not a misfile that vanishes. (The PRD's handling — non-goal for encashment in §6, escalate the exposure in OQ2 — is already correct.)

---

## 4. Contradictions (item 3)

### 4.1 A-01 (no fractional days) vs OQ3 (industry rounds to nearest half-day) — **coherently handled. No change.**

- `A-01`: a Leave Day is always whole; a fractional Leave Day cannot be expressed.
- OQ3 / FR-07 note / addendum §2.2: the common Indian proration convention rounds to the **nearest half-day** — which `A-01` makes **inexpressible** in this system.

This is a real tension, and the PRD handles it coherently rather than papering over it. It does **not** adopt nearest-half rounding. It states, in three consistent places (FR-07 note line 230, OQ3 line 545, addendum §2.2 line 89), that the industry default *cannot be expressed under A-01*, and defers to OQ3 the choice of a **whole-day-compatible** rounding rule ("Some rounding rule must be chosen"). `A-01` remains authoritative; the industry rule is recorded as counter-evidence, not adopted — exactly the §0 discipline ("Where a decision was made against known counter-evidence, the counter-evidence is stated alongside the decision").

The one residual sharp edge, which the PRD *does* surface: when the sponsor answers OQ3, the answer must be a whole-day rule; if they answer "nearest half-day," that reply collides head-on with `A-01` and one must yield. The PRD flags this ("nearest-half is not expressible here"), so the collision is visible, not buried. **Coherent. No open item to remove or add.**

### 4.2 BR-05 vs DR-14 (approved-leave cancellation) — resolved contradiction, not an open item.

`BR-05` ("cancelling approved leave restores the balance") contradicts `DR-14` (Approved is terminal). The PRD resolves it explicitly (FR-09 note line 275, `D-07`, addendum §1.4): scope is narrowed to what the specification authorizes, `BR-05` is preserved as documented-but-unreachable policy. A resolved and documented contradiction — noted here for completeness; it is not part of the open-item load.

No assumption contradicts another. A-02/A-03/A-07 are each consistent with the DRs and FRs that cite them.

---

## 5. Assumptions Index roundtrip (item 4)

`SM-7` claims a clean two-way roundtrip: *"every `[ASSUMPTION]` inline in this document appears in §12, and every §12 entry appears inline."* Measured:

**Direction inline → index: HOLDS.** All 7 inline tags (A-01, A-02, A-03, A-04, A-06, A-07, A-09) have a §12 entry.

**Direction index → inline: FAILS for two entries.**

| §12 entry | Claimed inline home | Reality |
|---|---|---|
| **A-05** | "§4.4 `FR-07`, `DR-9`, Open Question 3" | **No inline `[ASSUMPTION: A-05]` tag exists.** At §4.4 the FR-07 note is a `[NOTE FOR PM]` that cites `A-01`, not A-05. A-05's only inline appearance as an identified item is the `A-05` reference in **OQ3**. (Resolved by §2.1: A-05 is removed as a misfiled OQ.) |
| **A-08** | "§4.3, Open Question 5" | **No inline `[ASSUMPTION: A-08]` tag exists.** §4.3 (FR-06) carries the FL-name note, not a policy-reconfiguration assumption. A-08's only inline appearance is the `A-08` reference in **OQ5**. |

So `SM-7`'s roundtrip is only half-true as written. After the §2.1 removal of A-05, the sole remaining break is **A-08**, which is a genuine assumption (§2.4) but has no inline anchor. 

**Recommended fix (not a count change):** add an inline `[ASSUMPTION: A-08 — Leave Policy is not changed mid-Leave-Year in practice.]` at §4.3 `FR-06`, where policy reconfiguration is permitted. That closes the roundtrip and makes `SM-7` true.

---

## 6. Genuine implementation blockers (item 5)

A **Day-3 blocker** = an unknown without which a developer cannot key the schema or write a Phase-1 (correctness-core) code path. Test each open item against that, and against whether an assumption already provides a build-time bridge.

**Ranked:**

1. **OQ3 (proration model + rounding) — TRUE HARD BLOCKER, strongest of all.** `FR-07` proration is Phase-1 core. There is **no assumption that picks a value**: A-05 is empty ("some form"), so nothing bridges it (this is the §2.1 finding from the other direction). A developer reaching proration on Day 3 has literally nothing to implement — the mid-year joiner's Accrued balance is undefined until monthly-vs-annual *and* an A-01-compatible rounding rule are chosen. **No escape hatch.**

2. **OQ1 (leave year) — HIGHEST CONSEQUENCE, but bridged.** Keys the balance table, the rollover boundary, and `BR-04`'s span check. But `A-09` **does** pick a value (calendar year), and the Module 1 register explicitly states A-09 unblocks the data model ("Nothing now blocks the data model… the leave-year boundary by assumption A-09"). So you *can* write line 1 on the calendar-year assumption. The blocker is not "can't start" — it is "building on the wrong answer means rebuilding **every** balance" (§12). It blocks **confidence and commitment**, not the first keystroke.

3. **OQ8 (date representation) — Day-3-critical, but its answer is already known.** The day-count function (`DR-1`/`DR-2`) is Phase-1 core, and whether dates are stored as `date` or UTC timestamp determines its correctness (off-by-one at midnight). This must be settled *before* writing that function — arguably more Day-3-proximate than OQ1. But it is **not an open unknown**: the answer is known and recorded (date type, no time component — addendum §3.1). A developer following the addendum is not blocked. It is a decision-to-apply, not a question-to-ask — which is exactly why §3.1 reclassifies it out of §11.

**Non-blockers (workable default or out of the Day-3 path):**
- **OQ6** (zero-working-day request): a branch in `FR-08`; pick a default (refuse), low consequence, trivially changed. Minor.
- **OQ7** (recalc after late holiday): a defensible default ("don't recalculate") is proposed and near-adopted (Module 1). Not blocking.
- **OQ5** (mid-year policy change): `A-08` licenses omitting the path entirely. Not blocking.
- **OQ2** (EL cap/encashment): bites only at the **year-boundary rollover**, not Day-3 core; encashment is a Non-Goal; DR-7's "carry all unused EL" is a runnable default. High production/compliance consequence, but not a Day-3 code blocker.
- **OQ4, OQ9, OQ10**: not product-code items at all.

**Verdict on the PRD's claim ("OQ1 and OQ3 are the blockers"):**
- **Essentially right, but mis-weighted.** OQ3 is the *true hard* blocker — no assumption covers it, so it stops the first line of proration code. OQ1 is the *highest-consequence* item but is **bridged by A-09**, so it does not stop Day-3 from starting; it threatens catastrophic rework if wrong. The PRD slightly overstates OQ1's "can't start without it" character (its own A-09 contradicts that) and slightly understates that OQ3 is the one with no escape hatch.
- **The sleeper the ranking omits:** OQ8 touches the Phase-1 correctness core (the day-count function) and must be settled before it is written — but because its answer is already known and docketed for Architecture, it is a "record and apply," not an open blocker. It deserves a line in the developer's Day-3 checklist even though it is not an open question.

**Blocker list, honest ranking:**
1. **OQ3** — hard blocker, no bridge (proration undefined).
2. **OQ1** — highest consequence, bridged by A-09 (build on calendar year, confirm before real data or face total rebuild).
3. **OQ8** — Day-3-critical decision for the day-count function, but answer already known (date type, no time) — record and apply, not ask.

---

## 7. Proposed net reduction

All five removals are by (a) or (b); each item's content survives in exactly one home; nothing is invented or suppressed.

| # | Item | Operation | Basis | Survives as |
|---|---|---|---|---|
| 1 | **A-05** | Merge into OQ3 | Dedup + reclass — A-05 picks no value; it *is* OQ3 | OQ3 (§11) |
| 2 | **OQ4** | Fold into A-04 | Dedup — no live consequence beyond A-04 | A-04 (§12) |
| 3 | **OQ8** | Reclassify to Architecture | Reclass — representation decision, known answer | Addendum §3.1 (already there) |
| 4 | **OQ9** | Dissolve | Reclass (risk→§8) + dedup (process→OQ10) | §8 risk statement + OQ10 |
| 5 | **OQ10** | Reclassify to project plan | Reclass — assessment/process concern | Seven-day plan / memlog |

**Counts:**
- Open Questions: **10 → 6** (remove OQ4, OQ8, OQ9, OQ10; retain OQ1, OQ2, OQ3, OQ5, OQ6, OQ7).
- Assumptions Index: **9 → 8** (remove A-05; retain A-01, A-02, A-03, A-04, A-06, A-07, A-08, A-09).
- NOTE FOR PM callouts: **5 → 5** (none are duplicates or misfiled; all preserved).

**Open-item load: 24 → 19 (net −5).** (In the brief's stated base of 26, likewise −5 → 21; the difference between 24 and 26 is the miscount corrected in §1, not real items.)

**Items examined and deliberately left (irreducible by (a) or (b)):** OQ1, OQ2, OQ3, OQ5, OQ6, OQ7, and assumptions A-01/02/03/04/06/07/08/09 — each a genuine unknown or a value-picking assumption, none a duplicate or a disappearing misfile.

**Non-count fixes recommended:** (i) add an inline `[ASSUMPTION: A-08]` tag at §4.3 `FR-06` to close the §5 roundtrip break; (ii) once OQ9 leaves §11, adjust §8 so it no longer cites §11 as the "record" of the NFR-unconfirmed risk (§8 becomes that record).
