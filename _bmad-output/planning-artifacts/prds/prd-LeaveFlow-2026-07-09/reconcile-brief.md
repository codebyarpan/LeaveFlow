---
title: "Reconciliation — Brief vs PRD (LeaveFlow)"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Reconciliation: SOURCE brief vs DERIVED PRD

**SOURCE**
- `briefs/brief-LeaveFlow-2026-07-09/brief.md`
- `briefs/brief-LeaveFlow-2026-07-09/addendum.md`

**DERIVED**
- `prds/prd-LeaveFlow-2026-07-09/prd.md`
- `prds/prd-LeaveFlow-2026-07-09/addendum.md`

This is a report only. It proposes no requirements, rules, or resolutions. Where the
PRD delegates brief content to Module 1 (BRD / assumptions register), that is noted —
the PRD explicitly builds on Module 1 and does not duplicate it, so "absent from the
PRD" is not always "lost from the project."

---

## 1. DROPPED CONTENT

### 1.1 The epistemic categories are flattened, not reproduced

The brief's spine is five labelled buckets that separate claims by provenance:
**Confirmed Requirements** ("fixed and non-negotiable"), **Confirmed Business Rules**
("Settled, and not assumptions"), **Engineering Decisions** ("a defensible position
rather than a discovered fact, and each could have gone another way"), **Documented
Assumptions** ("Positions taken in the absence of guidance"), and **Open Questions**
("Questions to be asked, not guessed at").

The PRD does not reproduce these headings. It carries the *identifiers* (`BR-`, `D-`,
`A-`, and inline `[ASSUMPTION]` / `[NOTE FOR PM]`) and points to Module 1 as the home
of "the register of business rules, engineering decisions, and assumptions" (§0). What
is dropped is the brief's explicit *meta-commentary on epistemic status* — the prose
that tells a reader that a business rule was "established by clarification" and is not
an assumption, that an engineering decision "could have gone another way," that an
assumption is "recorded so it can be corrected rather than discovered."

**Does the absence matter?** Partially. The distinctions survive as prefix codes, and
the PRD's §5 preserves origin tags on every rule. But the brief's central value —
intellectual honesty about *how firmly* each claim is held — is legible in the brief at
a glance and is legible in the PRD only to a reader who already knows what the prefixes
mean. The framing that makes provenance self-evident is gone from the derived document.

### 1.2 The memlog's role is reduced to a passing mention

Brief addendum, Process Note:
> "The `.memlog.md` alongside this file records the decisions, overrides, and
> corrections made while producing this brief — including three instances of
> AI-proposed reasoning corrected by human or adversarial review. It is the seed of the
> Module 10 prompt improvement log and the record of AI mistakes and corrections, and
> it cannot be reconstructed later. It should not be discarded when the brief is
> finalised."

The PRD mentions `.memlog.md` twice, both times as a mere artifact pointer:
- §10 SM-6: "recorded in the brief, the BRD, or the run memlog."
- Closing line: "`.memlog.md` is the append-only decision log."

**Dropped:** (a) the memlog's stated *role* as the seed of the Module 10 prompt
improvement log and the record of AI mistakes and corrections; (b) the explicit claim
that it "cannot be reconstructed later" and "should not be discarded"; (c) the count —
**"three instances of AI-proposed reasoning corrected by human or adversarial review."**

**Does the absence matter?** Yes, mildly, and specifically for the learning path. The
reconciliation brief asked about this directly. The PRD's own addendum in fact *shows*
corrections happening (§1.2: "The distinction was surfaced by adversarial review, not
by the author"; the A-05 withdrawal in §12; the cancellation-contradiction resolution),
but it never names them as instances of AI reasoning corrected by review, never counts
them, and never ties them to the Module 10 deliverable. The record the brief said must
be preserved is neither preserved nor described in the derived artifacts.

### 1.3 The "system is the vehicle, not the destination" purpose statement

Brief Executive Summary:
> "the system is the vehicle rather than the destination. The assignment's stated
> objective is to learn the complete AI-first software engineering lifecycle using BMAD
> — 'to transform a business idea into production-ready software using AI agents rather
> than using AI only as a code generator.'"

The PRD retains the *stance* — §9: "LeaveFlow's purpose is to practise the full
lifecycle, not to ship into a market"; §7/§10: coverage is "a floor," "a necessary
condition, not a sufficient one"; §9 and §7 carry the seven-day / Days-3–5 plan. What is
dropped is the specific articulation of the objective as **AI-first lifecycle learning
— "AI agents rather than AI only as a code generator."** The "why this project exists"
is reduced from a stated learning objective to a generic "practise the lifecycle."

**Does the absence matter?** Low. The operational consequence (process artifacts over
feature count) is fully carried into §9. The lost material is framing, not requirement.

### 1.4 The "process artifacts over feature count" stance — RETAINED

Verbatim in PRD §9: "Process artifacts take precedence over feature count wherever the
two compete for time." Also operationalized as counter-metrics SM-C1..SM-C3. Not
dropped; recorded here to confirm.

### 1.5 The evaluation-mode uncertainty as the strategic hedge — diluted

Brief Executive Summary frames the unknown evaluation mode as the driver of the whole
strategy:
> "The evaluation mode remains unknown — it may be a checklist review, a technical
> discussion, or both — and under that uncertainty the strategy is to cover the
> explicitly given requirements while keeping the implementation clean enough to explain
> and defend."

The PRD keeps the *fact* of the unknown (§8: "whether any [NFR] will be evaluated is
unknown"; §11 reclassifies "what is the evaluation mode?" to the project plan) and
aligns NFR funding to "the ones a technical discussion would probe." But the brief's use
of that uncertainty as the *organizing rationale* for the entire coverage-plus-clean-
implementation strategy is diluted into scattered mentions.

**Does the absence matter?** Low-to-moderate. The strategy it justified is intact; the
justification is thinner.

### 1.6 Tone / voice — largely PRESERVED

The brief's essayistic, values-driven register survives strongly: §1 Vision, the
"a leave balance that is wrong is worse than absent, because it will be believed" motif
(brief Success Criteria spirit → PRD §1), and SM-6/SM-7 nearly quote the brief's closing
values ("Assumptions and open questions are visible rather than buried. A reader who
disagrees with a decision can find where it was made and on what basis."). Recorded to
confirm this qualitative material was *not* silently discarded.

### 1.7 Two enumerated role permissions have no dedicated home

Brief Confirmed Requirements lists, among Manager/Employee permissions:
- Manager: **"view team members"**
- Employee: **"view leave history"**

Neither surfaces as a dedicated FR or glossary term in the PRD. "View leave history"
folds loosely into FR-12 (filtering/pagination on list endpoints); "view team members"
is adjacent to FR-18 (Department Leave Calendar) and the Manager dashboard, but a plain
team roster is never named. The brief also lists Employee "cancel pending leave
requests" (→ FR-09, present) and "upload supporting documents when required" (→ FR-13,
present).

**Does the absence matter?** Low, but it is a genuine traceability soft spot: two
specification-level permissions are not individually traceable to a PRD requirement.
The PRD's own SM-6 (bidirectional traceability) would flag these. Flagged as absences;
not resolved here.

### 1.8 Module 1 deliverable enumeration — dropped (appropriately)

Brief addendum Process Note enumerates Module 1's other required outputs (problem
statement, BRD, stakeholder analysis, functional/non-functional specs, assumptions-and-
constraints register). The PRD references Module 1 as existing but does not enumerate
these. Appropriate — that is Module 1's scope, not the PRD's. Absence does not matter.

---

## 2. DISTORTED CONTENT

### 2.1 FL: open question restated as a glossary fact

**Brief** (Open Questions): "Outstanding: the expanded name of **FL** ..." — and brief
addendum OQ 1: "What does **FL** stand for? Its rules are confirmed (it lapses at year
end); only its expanded name is unknown."

**PRD** (§3 Glossary, line 93): "Three exist: **EL** (Earned Leave), **CL** (Casual
Leave), **FL** (Floater Leave)." UJ-3 (line 78): "Casual and **Floater Leave** lapse."

The glossary and a user journey state the expansion as settled vocabulary. The force is
softened elsewhere — FR-06 carries `[ASSUMPTION: A-04 — FL denotes Floater Leave]` and
§11 reclassifies it to "an assumption with a probable answer and no structural
consequence." So the PRD does not *hide* that this is unconfirmed, but it does promote an
open question to default-glossary status. See also §4 below.

### 2.2 "Balances hold across proration, carry-forward, year boundaries" — restated with
a reversal of confidence

**Brief** Success Criteria: "The system is correct where correctness is hard: balances
hold across proration, carry-forward, and year boundaries."

**PRD** SM-1 restates this as the primary metric but then explicitly limits its own
force: "It tests that the arithmetic is *consistent*, not that the balance is *right*. A
balance accrued against the wrong Leave Year (Open Question 1), or prorated by a rule
nobody has specified (Open Question 3), satisfies SM-1 completely while being exactly the
wrong-but-believed balance §1 exists to prevent."

This is not a distortion in the dishonest sense — it is the PRD being *more* candid than
the brief. But the meaning has changed in force: the brief asserts balances *will hold*
across proration and carry-forward; the PRD asserts they can only be shown *consistent*,
not *correct*, because the inputs are gated on unresolved open questions. The brief's
confident success criterion is downgraded to a partially-unachievable target. Quoted
both above so the shift is visible.

### 2.3 No other material distortions found

The three-quantity balance model, the reserve/consume/release transitions, the state
machine, the leave-day calculation (Fri–Tue spanning weekend + holiday = 2 days), the
data-scoped authorization, and BR-06 (no overlap restriction) are all restated in the
PRD with force and meaning intact.

---

## 3. CONTRADICTIONS

No hard contradictions found — nothing the PRD asserts that the brief denies, or vice
versa.

Near-misses examined and cleared:
- **"Eighteen functional requirements."** The brief's Confirmed Requirements prose lists
  16 items, yet the brief repeatedly says "eighteen." The PRD reconciles this rather than
  contradicting it: FR-17 (profile) and FR-18 (calendar) are noted as "derived in Module
  1 from a permission... rather than taken from the specification's enumerated list"
  (FR-17 note, FR-18 note). Consistent.
- **FR-11 dashboard reduced to summary cards.** Not a contradiction: the brief lists
  "dashboard analytics" scope as an *open question*, and the PRD openly declares the
  reduction unauthorized and escalates it (Open Question 4). Honest, not conflicting.
- **FL naming** (see §2.1) is a shift in force, not a contradiction — the PRD still tags
  it as an assumption.

---

## 4. PROPOSALS TREATED AS DECISIONS

### 4.1 PROMOTED — "which balance quantity the employee sees"

**Brief** addendum (Three-Quantity Balance Model): "Most systems display available
prominently and disclose the pending reservation alongside it. **Proposal, not a
decision.**" And brief addendum "Deferred, to resolve in design rather than by asking:
Which balance quantity the Employee sees when they 'view leave balance.'"

**PRD** hardens this into a testable requirement — FR-07 consequence: "An Employee
viewing their balance sees **Available** as the primary figure, with **Reserved**
disclosed alongside it." PRD addendum §2.3 further grounds it in comparables research and
treats the deferred question as resolved.

**Assessment:** A proposal the brief explicitly labelled "not a decision" is now an
acceptance criterion. Note the nuance: the brief said this item was to be "resolved in
design rather than by asking," so *resolving* it downstream is consistent with the
brief's instruction — but the brief did not authorize the *specific* resolution, and the
PRD presents it as settled requirement rather than as a design choice made under that
license. This is the clearest proposal-to-requirement promotion.

### 4.2 SEMI-PROMOTED — FL = "Floater Leave"

Covered in §2.1. Brief open question; PRD default glossary term. Mitigated by the A-04
assumption tag and §11 reclassification, so it is promoted to a *documented assumption*
rather than to a hard fact.

### 4.3 CORRECTLY KEPT AS PROPOSALS / OPEN — no column created (confirm)

The brief was emphatic that certain items are "proposals only, and nobody has confirmed
they exist... listed so the ERD author knows they were considered, not so that columns
are created for them." The PRD honours this for each:

- **Cap on carried-forward days.** Not modelled as a column. FR-07 NOTE FOR PM and Open
  Question 2 keep it open; §6 and §7.4 keep encashment/cap out of scope. Correct.
- **Accrual method (monthly accrual vs annual grant).** Not decided. Absorbed into Open
  Question 3 ("does leave accrue through the year, or is it granted annually?"). Correct.
- **Late-declared-holiday recalculation of approved requests.** Kept open (Open Question
  7); brief's "not recalculating is... a proposal rather than a decision" is preserved.
- **Zero-working-day request validity.** Kept open (Open Question 6; FR-08 Out of Scope).
- **Reporting relationship as attribute vs relation.** Left open (PRD addendum §3.2).

These confirm the PRD did *not* over-promote the brief's flagged proposals — with the two
exceptions in §4.1 and §4.2.

### 4.4 PRD-ADDED specificity not present in the brief

FR-18 requires the Department Leave Calendar be "presented on the approval screen for
the dates of the Leave Request under decision." The brief lists Holiday, Supporting
Document, Audit Entry, and Reporting Relationship as entities but never specifies calendar
*placement*. The PRD grounds this in its own comparables research (addendum §2.4), not in
the brief. Minor: a new requirement-level detail originating in the PRD, not a distortion
of brief content. Recorded for completeness.

---

## 5. DECISIONS TREATED AS PROPOSALS

No material reverse demotions found. Each brief Confirmed Rule and Engineering Decision
retains at least its brief-level firmness in the PRD:

- **BR-05** (cancelling approved leave restores balance) — brief keeps it as a confirmed
  rule that is documented-but-unreachable under D-07; PRD FR-09 note treats it identically
  ("retained... as policy but is unreachable"). Not demoted.
- **D-01/D-02/D-03/D-07** (deduct-on-approval + reserve; working-days-only; data-scoped
  authorization; approved-cancellation out of scope) — all carried into DR-3/4, DR-1,
  DR-12, DR-14 as firm invariants. Not demoted.
- **D-05/D-06** (FastAPI, React) — PRD §9 "Chosen, and defensible." Not demoted.
- **A-09** (leave year = calendar year) was already an *assumption* in the brief, not a
  decision; PRD keeps it an assumption. No status change.

If anything, the PRD *hardens* several brief decisions into testable DR-invariants rather
than softening them.

---

## 6. BRIEF SUCCESS CRITERIA vs PRD SUCCESS METRICS (SM-1..SM-8, SM-C1..C3)

### The brief's stated success criteria (quoted in full)

> "**The requirements are covered, and every lifecycle stage has produced its artifact**
> — such that any decision in the codebase can be traced to a document, and any decision
> in a document can be defended aloud.
>
> **The system is correct where correctness is hard:** balances hold across proration,
> carry-forward, and year boundaries; the day count excludes weekends and holidays;
> authorization scopes managers to their own direct reports; and every leave action
> leaves an audit trail.
>
> **Assumptions and open questions are visible rather than buried.** A reader who
> disagrees with a decision can find where it was made and on what basis."

Plus the Executive Summary's definition: "The measure of success is a coherent system
whose every stage is documented and defensible."

### Mapping

| Brief criterion | PRD metric | Verdict |
|---|---|---|
| Requirements covered | SM-8 (all 18 FRs delivered, each with a passing test) | Covered |
| "every lifecycle stage has produced its artifact" | *(none)* | **NOT MEASURED** |
| Decision traceable to a document / defensible aloud | SM-6 (bidirectional traceability) | Covered (traceability); "defended aloud" partial |
| Balances hold across proration/carry-forward/year boundary | SM-1 (with explicit self-limitation) | Partially — consistency only, see §2.2 |
| Day count excludes weekends/holidays | SM-2 | Covered |
| Authorization scopes managers to direct reports | SM-3 | Covered |
| Every leave action leaves an audit trail | SM-4 | Covered |
| Assumptions/open questions visible not buried | SM-7 (near-verbatim) | Covered |
| "correctness over feature count" (Exec Summary / stance) | SM-C1, SM-C2, SM-C3 | Covered |

### The gap that matters most

**The brief's primary success definition has two halves; the PRD's SM set measures only
one.** The brief says success is "The requirements are covered, **and every lifecycle
stage has produced its artifact**" — and the Executive Summary makes artifact-completeness
*the* measure: "a coherent system whose every stage is documented and defensible," where
the seven-day plan's Days 1, 2, 6, 7 exist precisely to produce a BRD, PRD, ERD,
architecture and flow diagrams, API contracts, a test plan, a code review report, a
prompt library, and a retrospective.

No SM measures whether those artifacts exist. SM-8 counts *functional-requirement*
delivery; SM-6 checks *decision traceability*; none checks *lifecycle-artifact
completeness*. For a project whose brief states the artifacts (not the features) are the
point, the metric set measures the floor (feature coverage) and the correctness core
thoroughly, but omits the ceiling the brief named as success.

**Does the absence matter?** Yes — it is the single most consequential SM gap. It is
also arguably outside the PRD's remit (artifact-tracking belongs to the BMAD process /
project plan, not a product requirements document), which is likely why it fell through.
But the reconciliation records it as missing: the PRD's SM set does **not** fully measure
what the brief said success means, because the brief's own headline criterion — every
lifecycle stage documented — has no corresponding metric anywhere in the derived
documents. Stated as an absence; not resolved here.

### Secondary observations

- SM-5 ("policy is data") and the SM-C counter-metrics have no explicit antecedent in the
  brief's Success Criteria paragraphs, but they faithfully operationalize the brief's
  Engineering Decisions (D-04) and its "process over feature count" stance. Additions
  that serve the brief, not departures from it.
- SM-1's honest self-limitation (§2.2) means the brief criterion "balances hold across
  proration, carry-forward" is only partially testable and the PRD says so — the
  correctness of proration and leave-year inputs is gated on Open Questions 1 and 3 and
  no green suite closes that gap. The success criterion is retained but flagged as not
  fully achievable under current unknowns.

---

## Summary of the most consequential items

1. **Success-criteria gap (§6):** the brief's headline measure — "every lifecycle stage
   has produced its artifact" — has no Success Metric. SM-1..SM-8 measure feature
   coverage and correctness-core, not artifact completeness. Biggest gap.
2. **Proposal promoted (§4.1):** "which balance quantity the employee sees" — labelled
   "Proposal, not a decision" and "deferred to design" in the brief — is now FR-07
   acceptance criteria.
3. **Memlog role dropped (§1.2):** the memlog's stated role (seed of the Module 10 prompt
   log; record of AI mistakes/corrections; "cannot be reconstructed"; the count of *three*
   AI-reasoning corrections) is not carried into the PRD.
4. **Epistemic categories flattened (§1.1):** the brief's Confirmed/Decided/Assumed/Open
   provenance framing survives only as prefix codes and a Module-1 pointer.
5. **FL name (§2.1 / §4.2):** an open question ("expanded name of FL") is rendered as
   glossary vocabulary ("Floater Leave"), mitigated by the A-04 assumption tag.
6. **Two role permissions untraced (§1.7):** Manager "view team members" and Employee
   "view leave history" have no dedicated FR.

No hard contradictions; no brief decision demoted to a proposal.
