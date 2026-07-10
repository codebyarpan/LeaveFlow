---
title: "LeaveFlow PRD §5 — Domain-Rule Traceability Audit"
status: review
created: 2026-07-09
scope: "Verifies DR-1..DR-16 against Module 1 BRD, assumptions register, NFR set, FR spec, brief, and addendum"
---

# DR Traceability Audit — PRD §5 vs. Module 1 sources

**Claim under test.** PRD §5 asserts it "introduces no new rules — it consolidates rules
established in the Module 1 BRD and assumptions register." Each DR cites an origin. This audit
checks, for each DR, that (1) the cited source exists, (2) it says what the DR says, (3) the DR
has not silently strengthened / weakened / broadened it, and (4) no DR is a new rule wearing a
citation.

**Verdict up front.** No DR is UNSOURCED (a fabricated citation or a genuinely new rule), and no
DR is MISCITED to a source that does not exist. Every cited BR / D / A / NFR / FR is real and
substantively on point. **One DR — DR-5 — has DRIFTED (broadened).** Several others carry minor
elaborations documented in the notes; they remain within faithful bounds.

**Counts.** FAITHFUL 15 · DRIFTED 1 (DR-5) · UNSOURCED 0 · MISCITED 0.

---

## Audit table

| DR | PRD text (condensed) | Cited | Source verbatim | Assessment | Class |
|----|----------------------|-------|-----------------|------------|-------|
| DR-1 | Leave Day count = Working Days in range; weekends & Company Holidays excluded. | D-02 | D-02: "**Only working days are deducted.** Weekends and company holidays are excluded." | Exact restatement. (Weekend/holiday definitions themselves rest on A-02/A-03, disclosed elsewhere.) | FAITHFUL |
| DR-2 | Pure function of range + holiday calendar; exactly one implementation; every balance path calls it; a second implementation is a defect. | D-02, NFR-08 | NFR-08: "The leave-day calculation is a single pure function. One implementation, directly unit-tested, called by every path that touches a balance. Duplicating the weekend-and-holiday logic anywhere is a defect." | Verbatim match, including "a second implementation is a defect" = "Duplicating … is a defect." | FAITHFUL |
| DR-3 | Balance = 3 stored (Accrued, Reserved, Consumed) + derived Available = Accrued − Consumed − Reserved; Available never stored. | D-01 | D-01: "Balance is deducted on approval; pending requests reserve days … Implies three quantities — accrued, reserved, consumed." Formula per brief/BRD glossary: "Available `accrued − consumed − reserved`." | Three-quantity model and formula trace to D-01 + glossary. "Available is never stored" is a design elaboration not literally in D-01, but a direct consequence of "derived." | FAITHFUL (minor elaboration) |
| DR-4 | Submit reserves; approve consumes; reject & cancel release. | D-01 | D-01: "Balance is deducted on approval; pending requests reserve days." Release-on-reject/cancel per addendum state machine + FR-09: "Rejection releases the reservation … cancel their own pending request, releasing the reservation." | Reserve/consume = D-01 exactly. Release-on-reject/cancel is really FR-09 + the (proposed) addendum state machine, but D-01 is the model's origin. Not new. | FAITHFUL (release effects also FR-09) |
| DR-5 | `Available ≥ 0` is an invariant; holds after every transition, incl. concurrent; reserve/consume/release atomic. | NFR-07 | NFR-07: "Balance operations are atomic. Reserving, consuming, and releasing leave days occur within a transaction. A concurrent double submission **must not produce a negative or double-counted balance**." | Atomicity + concurrency non-negativity = NFR-07 exactly. **But NFR-07 scopes non-negativity to "a concurrent double submission."** DR-5 promotes this to a **universal invariant "holds after every transition."** The universal `Available ≥ 0` claim's true home is FR-08 ("A request whose day-count exceeds available leave is refused at submission") — **which is not cited.** | **DRIFTED** (broadened; universal-invariant basis FR-08 uncited) |
| DR-6 | A Leave Request may not span two Leave Years; one request per Leave Year. | BR-04 | BR-04: "Leave spanning two **calendar years** may not be one application. The employee submits one application per **calendar year**." | Substance faithful, but BR-04 (a *confirmed* rule) says "calendar year"; DR-6 re-anchors it to the *assumed* "Leave Year" (A-09). Disclosed by the §5.3 note on DR-8: "Every rule in this subsection inherits its uncertainty." | FAITHFUL (term re-anchored calendar→Leave Year; disclosed) |
| DR-7 | At boundary, carries-forward=true → carried forward; false → Lapse; EL forwards, CL & FL lapse. | BR-01, BR-03 | BR-03: "At year end, EL carries forward. CL and FL lapse." BR-01: "Three leave types exist: EL, CL, FL." | Concrete claim (EL/CL/FL) = BR-03 exactly. The *attribute-driven generalization* ("any type whose carries-forward attribute is true") originates in D-04/NFR-14 (cited at DR-11), not BR-03. Not a new rule. | FAITHFUL (attribute generalization is D-04) |
| DR-8 | The Leave Year is the calendar year. | A-09 (assumption) | A-09: "The leave year is the calendar year, 1 January to 31 December." | Exact, and correctly tagged as an assumption, not a confirmation. | FAITHFUL |
| DR-9 | Mid-Leave-Year joiner receives Prorated Accrued balance. | BR-02 | BR-02: "An employee joining mid-year receives a prorated leave balance." | Exact restatement ("Accrued" is the balance component proration targets). | FAITHFUL |
| DR-10 | A Leave Day is a whole number; fractional leave not expressible. | A-01 | A-01: "Half-day leave is out of scope … Balances become decimal … the day-count function returns fractions [if wrong]." | Faithful restatement of the assumption; correctly tagged A-01. | FAITHFUL |
| DR-11 | Carry-Forward & Supporting-Document reqs are Leave-Type attributes, stored as data, read at runtime; adding a Leave Type requires no code change. | D-04, NFR-14 | NFR-14: "Leave type behaviour (carry-forward, lapse, document requirement) is data the Admin configures. Adding a leave type requires no code change." D-04: "Leave policy is configuration, not code … adding a leave type requires no code change." | Verbatim on both attributes and the no-code-change claim. | FAITHFUL |
| DR-12 | Manager authority derives from Direct Report relationship, not role; data-scoped; scope applied in query. | D-03, NFR-04 | D-03: "Authorization is data-scoped, not role-checked … the reporting relationship must be established." NFR-04: "Data scoping is enforced in the query … not filtered after retrieval." | Exact match to both. | FAITHFUL |
| DR-13 | Admin may read every Leave Request and decide none. | FR-03, specification | FR-03 (Mod 1): "An Admin may view all leave requests but is **not granted approval authority** by the specification." Brief/spec role: Admin "view all leave requests" (no approve/reject). | "Read every" = "view all"; "decide none" = "not granted approval authority." Standard RBAC reading; PRD FR-03 consequence states it identically. "Specification" cite is external but corroborated in the brief. | FAITHFUL |
| DR-14 | Approved is terminal; no role may cancel approved leave, so no such transition. | D-07 (resolving BR-05) | D-07: "Cancellation of approved leave is out of scope … No approved-cancellation transition is implemented." Addendum: "**`Approved` is a terminal state.**" BR-05 retained as unreachable policy. | Faithful; "terminal" is verbatim addendum; D-07 supplies the no-transition; BR-05 contradiction handling matches. | FAITHFUL |
| DR-15 | Overlapping leave among Direct Reports permitted without restriction; system informs, never blocks. | BR-06 | BR-06: "No restriction applies when multiple employees from the same team request the same dates." | Core normative claim (permitted, never blocks) = BR-06 exactly. "The system informs" describes the Department Leave Calendar (FR-18), an addition of description, not of rule. | FAITHFUL (informs = FR-18) |
| DR-16 | Every transition writes **exactly one** append-only Audit Entry naming actor + timestamp. | FR-16, NFR-09, NFR-19 | FR-16 (Mod 1): "Every leave state transition is recorded. An audit entry captures the request, the transition, the acting user, and the timestamp. Entries are append-only." NFR-09: "append-only." NFR-19: "Every leave state transition records who caused it and when." | Faithful; "exactly one" tightens FR-16's "every transition is recorded" into a strict 1-to-1 cardinality — a mild strengthening (≥1 → exactly 1), not a new rule; PRD FR-16 states it as a testable consequence. | FAITHFUL (minor tightening) |

---

## Special-attention findings (as requested)

- **DR-2 ("a second implementation is a defect").** Faithful. This is NFR-08 nearly verbatim
  ("Duplicating the weekend-and-holiday logic anywhere is a defect"), reinforced by D-02.

- **DR-5 (atomicity + `Available ≥ 0` invariant) — the one real drift.** NFR-07 guarantees
  atomicity and that *a concurrent double submission* "must not produce a negative or
  double-counted balance." DR-5 restates that faithfully **and then broadens it** into a universal
  invariant: "`Available ≥ 0` … holds after **every** transition." That universal non-negativity
  is a real system rule — but its source is **FR-08's submission-time refusal** ("A request whose
  day-count exceeds available leave is refused at submission"), which DR-5 does **not** cite. As
  written, an atomicity NFR is made to carry a correctness invariant it does not, on its own,
  establish. Recommendation for the reader: DR-5 should additionally cite FR-08 (and PRD FR-07's
  "no sequence of transitions produces a negative Available balance") for the invariant clause.
  Not a fabricated rule; a broadened one with an incomplete citation.

- **DR-11 ("adding a leave type requires no code change").** Faithful. Stated verbatim in **both**
  D-04 and NFR-14; carry-forward and supporting-document as data attributes is verbatim NFR-14.

- **DR-13 ("Admin decides none").** Faithful. FR-03 (Mod 1) says the Admin is "not granted
  approval authority by the specification"; the spec's role list gives Admin view-only. "Decides
  none" is the RBAC equivalent of "authority not granted," and PRD FR-03's own consequence states
  it identically.

- **DR-14 ("Approved terminal").** Faithful. "`Approved` is a terminal state" is verbatim in the
  addendum; D-07 supplies "no approved-cancellation transition is implemented"; the BR-05
  contradiction is handled exactly as the sources handle it (retained, unreachable).

- **DR-16 ("exactly one audit entry per transition").** Faithful, with a mild tightening. Module 1
  FR-16 says "every transition is recorded" (≥1) and "append-only" (no deletion); "**exactly** one"
  (a strict 1-to-1, excluding duplicates) is first made explicit in the PRD. It is a reasonable
  reading of "record a transition," is not a new rule, and PRD FR-16/ SM-4 restate it as a
  testable consequence. Worth noting only because it is the kind of quiet cardinality tightening
  the audit was asked to watch for.

## Minor elaborations that stay within faithful bounds

- **DR-3 — "Available is never stored."** Not in D-01; a direct and standard consequence of
  Available being *derived*. Elaboration, not a new rule.
- **DR-4 — release on reject/cancel.** D-01 establishes reserve-on-submit / consume-on-approve;
  the release-on-reject/cancel legs come from FR-09 and the (proposed) addendum state machine.
  Substance unchanged.
- **DR-6 — "calendar year" → "Leave Year."** BR-04 is a *confirmed* rule about *calendar* years;
  DR-6 re-expresses it in the *assumed* "Leave Year" term (A-09). If A-09 is wrong (e.g. an
  April–March cycle), the confirmed BR-04 and DR-6 diverge. This inheritance is disclosed by the
  §5.3 note on DR-8 ("Every rule in this subsection inherits its uncertainty"), so it is a
  disclosed re-anchoring rather than a hidden one. DR-6 itself, however, carries only "(BR-04)"
  with no A-09 tag — unlike DR-8 — so a reader skimming DR-6 alone would take a boundary that
  depends on an assumption to be a confirmed fact.
- **DR-7 — attribute generalization.** The concrete "EL forwards, CL & FL lapse" = BR-03 exactly;
  the generalized "any type whose carries-forward attribute is true" originates in D-04/NFR-14
  (cited at DR-11), not in BR-01/BR-03.
- **DR-15 — "the system informs."** The no-block rule = BR-06; the "informs" behaviour is the
  Department Leave Calendar (FR-18). Descriptive addition, not a rule change.

## Bottom line on the central claim

PRD §5's claim to "introduce no new rules" holds. Every DR traces to a real, on-point source;
none invents a rule and dresses it in a citation. The single substantive deviation is **DR-5**,
which broadens NFR-07's concurrency-scoped non-negativity into a universal `Available ≥ 0`
invariant while citing only NFR-07 — the invariant's real basis (FR-08) is uncited. The remaining
sixteen-minus-one are faithful, with a handful of disclosed or minor elaborations noted above.
