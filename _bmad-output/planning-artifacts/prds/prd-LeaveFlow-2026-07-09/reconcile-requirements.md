---
title: "LeaveFlow — Source-to-PRD Reconciliation"
status: report-only
created: 2026-07-09
scope: "Compare Module 1 registers (FR/NFR/BR/D/A/Constraints) against prd.md + addendum.md. Report only; no fixes, no new requirements."
---

# Reconciliation: Module 1 registers vs. PRD

**Inputs compared**

- SOURCE: `module-1-business-analysis/functional-requirements.md`, `non-functional-requirements.md`, `assumptions-and-constraints.md`
- DERIVED: `prds/prd-LeaveFlow-2026-07-09/prd.md`, `addendum.md`

**Headline verdict.** The PRD is a high-fidelity derivation. No business rule, engineering decision, or surviving assumption was strengthened, weakened, dropped, or renumbered. No fabricated NFR/BR/D/A citation was found. All gaps below are cosmetic or negative-scope (not-required items), none with a consequence for any FR or DR.

---

## 1. NFR coverage (Module 1 has 21 NFRs; PRD §8 restates a subset)

### 1.1 NFRs NOT restated in PRD §8

PRD §8 restates 20 of 21: NFR-01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21.

**The single NFR not restated in §8's list is NFR-19 (Attribution).** This is not an omission:

- The §8 header explicitly calls it out: *"NFR-19 (every transition records who and when), cited by DR-16, is among those not restated here."*
- Its content is carried in **DR-16** (§5.5): *"NFR-09 and NFR-19 add append-only enforcement and actor attribution … naming actor and timestamp."*
- It is exercised by **SM-4** (each Audit Entry names an actor and a timestamp; one-to-one with transitions).
- DR-16's citation of NFR-19 is therefore backed, not orphaned.

**Consequence for any FR/DR: none.** NFR-19's substance (who + when on every transition) is fully present in DR-16 and FR-16, and tested by SM-4. The omission from the §8 enumeration is deliberate and self-documented.

### 1.2 "Explicitly Not Required" list vs. PRD §6 Non-Goals

Module 1 not-required set: high availability, horizontal scalability, multi-tenancy, i18n/l10n, WCAG, rate limiting, disaster recovery/backup, penetration testing, performance under concurrent load beyond a handful of users.

PRD §6 final bullet names explicitly: **high availability, horizontal scalability, internationalization, formal WCAG conformance** ("Explicitly not required by Module 1's NFR set, and not pursued").

| Not-required item | Carried into PRD §6? | FR/DR consequence of omission |
|---|---|---|
| High availability | Yes (§6 final bullet) | — |
| Horizontal scalability | Yes (§6 final bullet) | — |
| Internationalization/localization | Yes (§6 final bullet) | — |
| WCAG conformance | Yes (§6 final bullet) | — |
| Multi-tenancy | Yes — covered as "Model more than one organization. Single-tenant (A-07)" | None (single-tenant is affirmed, not just omitted) |
| Rate limiting | **Not restated** | None — negative scope; no FR/DR depends on it |
| Disaster recovery / backup | **Not restated** | None — negative scope; no FR/DR depends on it |
| Penetration testing | **Not restated** | None — negative scope; no FR/DR depends on it |
| Performance under concurrent load beyond a handful | **Not restated** | None — NFR-10's "order of magnitude, not contractual" framing already scopes performance down |

**Assessment.** Four not-required items (rate limiting, DR/backup, pen testing, load-beyond-handful) are not individually named in §6. They are negative-scope declarations; dropping them from the Non-Goals restatement costs only the "reads as a decision rather than an oversight" benefit Module 1 intended. **No FR or DR has a dependency on any of them, so no functional consequence.** §6's phrase "Explicitly not required by Module 1's NFR set" gestures at the whole register.

---

## 2. Business Rules BR-01..BR-06

| BR | Module 1 text | PRD corresponding text | Verdict |
|---|---|---|---|
| **BR-01** | "Three leave types exist: EL (Earned Leave), CL (Casual Leave), FL." | §3 Glossary "Three exist: EL (Earned Leave), CL (Casual Leave), FL (Floater Leave)"; FR-06 "Three Leave Types exist at initialization: EL, CL, FL"; DR-7 cites BR-01. | **Faithful.** FL expanded to "Floater Leave" but tagged `[ASSUMPTION: A-04]`, not asserted as confirmed — so BR-01 is not strengthened. |
| **BR-02** | "An employee joining mid-year receives a prorated leave balance." | DR-9 "An Employee joining mid-Leave-Year receives a Prorated Accrued balance. (BR-02)"; FR-07 consequence cites BR-02. | **Faithful.** |
| **BR-03** | "At year end, EL carries forward. CL and FL lapse." | DR-7 "EL carries forward; CL and FL lapse. (BR-01, BR-03)"; FR-07 consequence; UJ-3. | **Faithful.** |
| **BR-04** | "Leave spanning two calendar years may not be one application. The employee submits one application per calendar year." | DR-6 "A Leave Request may not span two Leave Years. The Employee submits one request per Leave Year. (BR-04 …)"; FR-08 consequence. | **Faithful in substance.** Terminology generalized from "calendar year" to "Leave Year," with DR-6/DR-8 making the boundary A-09-dependent. Mild circularity (Module 1 used BR-04's "calendar year" wording as *evidence for* A-09; the PRD now derives BR-04's boundary *from* A-09), but no strengthening or weakening — under A-09 the two are equated. Noted, not a defect. |
| **BR-05** | "Cancelling approved leave restores the deducted balance. *(Retained as policy clarification only. No role is authorized … not reachable … documented because it will matter if the permission is ever granted.)*" | FR-09 Notes: "BR-05 … is retained in Module 1 as policy but is unreachable under the permissions the specification grants … The rule is preserved, not deleted, so that a future reader can see the contradiction and its resolution." DR-14 "resolving the BR-05 contradiction"; addendum §1.4. | **Faithful — retained-but-unreachable framing preserved exactly.** The PRD does not delete the rule; it reproduces Module 1's framing (documented policy, not reachable under defined permissions, resolved by D-07). |
| **BR-06** | "No restriction applies when multiple employees from the same team request the same dates." | DR-15 "Overlapping leave … permitted without restriction. The system informs; it never blocks. (BR-06)"; FR-18; §4.6 description. | **Faithful.** |

**All six present. None strengthened, weakened, or dropped. BR-05's deliberate retained-but-unreachable framing is preserved.**

---

## 3. Engineering Decisions D-01..D-07

| D | Module 1 | PRD / addendum location | Verdict |
|---|---|---|---|
| **D-01** | Balance deducted on approval; pending reserve; three quantities. | DR-3, DR-4 (both cite D-01); §4.4 description. | Present. |
| **D-02** | Only working days deducted (weekends + holidays excluded). | DR-1, DR-2 (cite D-02); NFR-08. | Present. |
| **D-03** | Authorization data-scoped, not role-checked. | DR-12 (cites D-03); NFR-04. | Present. |
| **D-04** | Leave policy is configuration, not code. | DR-11 (cites D-04); NFR-14. | Present. |
| **D-05** | FastAPI backend (selected from offered set). | §9 "FastAPI for the backend (D-05)". | Present. |
| **D-06** | React frontend (selected from offered set). | §9 "React for the frontend (D-06)". | Present. |
| **D-07** | Cancellation of approved leave out of scope. | DR-14; FR-09 Notes; §7.4; addendum §1.4. | Present. |

**All seven present somewhere in PRD or addendum. None silently abandoned.**

---

## 4. Assumptions A-01..A-09 and the A-05 withdrawal

### 4.1 A-05 withdrawal assessment — VERDICT: SOUND

Module 1 A-05: *"Leave accrues in some form, since BR-02 confirms proration. Whether monthly or as an annual grant is unstated."* Consequence: *"Proration is computed against the wrong entitlement model."*

PRD §12: A-05 withdrawn on grounds that *"entitlement accrues in some form"* names an unknown without choosing a value, so it cannot be wrong; content moved to Open Question 3; identifier retired, not reused.

**The withdrawal is sound, and no real assumption was lost:**

- **Structurally it was an open question, not an assumption.** An assumption commits to a falsifiable value. A-05's two clauses are (a) "accrues in some form" — nearly entailed by BR-02, which already confirms proration and thus presupposes an entitlement to prorate, so it asserts almost nothing new; and (b) "monthly or annual is unstated" — which *explicitly declines to choose*. The consequence Module 1 attached ("proration against the wrong model") only bites if you *guess* the model — which A-05 refuses to do. A named-but-unchosen unknown with a consequence-only-if-guessed is the definition of an open question.
- **The content is preserved and sharpened, not dropped.** Open Question 3 captures the same gap more precisely: *"No source document states how many Leave Days a Leave Type grants per Leave Year … Nor is the Proration method or its rounding rule stated."* OQ3 also surfaces a collision A-05 never noted (the common monthly-accrual/round-to-half-day convention cannot be expressed because A-01 forbids fractional days). So the migration is a net gain in fidelity.
- **The consequence survives.** OQ3 states "there is nothing to prorate and nothing to roll over until a granted quantity exists" and is marked the **blocking** question — a stronger statement of A-05's "wrong entitlement model" risk.
- **No numbering damage.** §12 explicitly retires the A-05 identifier without reuse "so that Module 1's numbering still resolves." No downstream A-nn was shifted.

### 4.2 Every other A-nn survives with its "if wrong" consequence

PRD §12 carries A-01, A-02, A-03, A-04, A-06, A-07, A-08, A-09 (8 items) + A-05 documented as withdrawn = all nine Module 1 identifiers accounted for. No renumbering.

| A | "If wrong" — Module 1 vs. PRD §12 | Verdict |
|---|---|---|
| A-01 | M1: decimal balances / fractional day-count / schema change. PRD: "balances become fractional, day-count returns decimals, schema changes." | Intact. |
| A-02 | M1: alternate-Saturday patterns miscount every request. PRD: same, "that spans one." | Intact. |
| A-03 | M1: multi-location calendars unrepresentable; balances differ by office. PRD: "multi-location calendars are unrepresentable in the data model." | Intact (drops the secondary "balances differ by office" clause; core preserved). |
| A-04 | M1: "Nothing structural." PRD: "display text only; nothing structural." | Intact. |
| A-06 | M1: state machine missing states. PRD: "the state machine is missing states" (+ cross-ref to OQ8 for zero-approver case). | Intact. |
| A-07 | M1: nothing in data model scoped to an organization. PRD: identical. | Intact. |
| A-08 | M1: reconfiguring a leave type silently invalidates existing balances. PRD: "reconfiguring a Leave Type silently invalidates balances already accrued." | Intact. |
| A-09 | M1: balance table keyed wrongly; carry-forward + proration fire at wrong boundary; every balance affected. PRD: "every balance in the system is wrong … carry-forward and lapse fire at the wrong boundary and the balance table is keyed incorrectly." Highest-consequence flag preserved. | Intact (PRD writes "lapse" where M1 wrote "proration" as the second example — same meaning: boundary fires wrong). |

**No assumption lost, no consequence dropped, no renumbering.**

---

## 5. Constraints (Module 1 → PRD §9)

| Module 1 constraint | PRD §9 | Verdict |
|---|---|---|
| **Manager-imposed — Time budget:** Seven days. | "Seven days total. Days 3–5 the only days allocated to application code." | Carried. |
| **Manager-imposed — Process:** BMAD lifecycle + artifacts; Days 3–5 only for code. | "The BMAD lifecycle is followed and its artifacts produced. Process artifacts take precedence over feature count." | Carried (adds precedence rule, consistent with M1). |
| **Manager-imposed — Technology options:** bounded set offered; selection was engineer's. | "Technology was selected from a bounded set of offered options." + "Chosen, and defensible" block (D-05, D-06). | Carried. |
| **Spec-imposed — Roles:** exactly three, no additions. | "Exactly three roles. No additions." | Carried. |
| **Spec-imposed — Scope:** 18 FRs (16 enumerated + FR-17/FR-18); unnamed features out of scope. | "Eighteen functional requirements as a coverage floor." | Carried, with a framing shift (see note). |
| **Spec-imposed — Authorization model:** Manager authority to direct reports only. | "A Manager's authority extends to Direct Reports only." | Carried. |
| **Spec-imposed — Policy ownership:** Admin manages/configures leave types and policies. | "The Admin owns Leave Policy configuration and holds no approval authority." | Carried (adds "no approval authority" from FR-03; faithful). |
| **Spec-imposed — Delivery form:** web-based application. | "Web-based delivery." | Carried. |

**All constraints carried.** One framing note: §9 restates the scope constraint as a "coverage **floor**" (minimum-to-deliver), whereas Module 1's constraint is also a **ceiling** ("Features not named in the specification are out of scope"). The ceiling half is not lost — it lives in §6 Non-Goals, the §9 guardrail ("A requirement that cannot be stated with a testable consequence…"), and addendum §1.5 (encashment rejected as invented scope) — but the single-line §9 restatement emphasizes floor over ceiling. Cosmetic; no requirement affected.

---

## 6. Fabricated citations (PRD cites something absent from Module 1)

Systematic check of every register reference in prd.md and addendum.md:

- **NFRs cited by PRD:** all fall within NFR-01..NFR-21 (explicitly: 04, 05, 07, 08, 09, 14, 19, plus the §8 enumeration 01–18, 20, 21). No NFR-22+ or otherwise nonexistent NFR is cited. **No fabrication.**
- **NFR-19 specifically:** exists in Module 1 (§Auditability). DR-16's citation of it is valid.
- **Business rules cited:** BR-01..BR-06 only. All exist. **No fabrication.**
- **Engineering decisions cited:** D-01..D-07 only. All exist. **No fabrication.**
- **Assumptions cited:** A-01, A-02, A-03, A-04, A-06, A-07, A-08, A-09, plus A-05 referenced as withdrawn. No A-10+ cited (Module 1 itself notes any earlier A-10 is obsolete). **No fabrication.**
- **FRs cited:** FR-01..FR-18 only, matching Module 1's set exactly. **No fabrication.**

---

## Summary of findings

- **NFR coverage:** 20/21 restated in §8; only NFR-19 absent from the list, and that absence is self-documented, backed by DR-16, and tested by SM-4 — no FR/DR consequence.
- **Not-required list:** rate limiting, disaster recovery/backup, penetration testing, and load-beyond-handful are not individually named in §6 (HA, horizontal scalability, i18n, WCAG are; multi-tenancy is covered via single-tenant + A-07). All negative scope; no FR/DR consequence.
- **BR-01..BR-06:** all present and faithful; BR-05's retained-but-unreachable framing preserved.
- **D-01..D-07:** all seven present; none abandoned.
- **A-05 withdrawal:** SOUND — it was structurally an open question, its content is preserved and sharpened in Open Question 3, its consequence survives, and the identifier is retired without renumbering.
- **A-01..A-09 (minus A-05):** all survive with "if wrong" intact; no renumbering.
- **Constraints:** all carried; only a cosmetic floor-vs-ceiling framing note on the scope line.
- **Fabricated citations:** none found across NFR/BR/D/A/FR references.
