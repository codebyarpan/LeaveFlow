---
title: "LeaveFlow PRD — Downstream Consumability Review"
status: draft
created: 2026-07-09
updated: 2026-07-09
reviewer: downstream-readiness assessment
---

# LeaveFlow PRD — Downstream Consumability Review

Scope of this review: can the PRD (`prd.md`) plus `addendum.md` be consumed, as written, by the workflows that depend on it — Architecture (Module 3), ERD (Module 4), API contracts, test plan, then epics and stories? The judgment is practical: what can a competent engineer build directly, and where are they forced to invent or wait.

This review reports gaps. It does not propose requirements, resolve open business questions, or fill in missing values. Where a value is missing, that absence is the finding.

## Readiness verdict per consumer

| Consumer | Verdict | One-line reason |
|---|---|---|
| ERD (Module 4) | **Amber** | Most entities are drawable, but Leave Type lacks the entitlement attribute FR-07 needs, Notification is omitted from the open-shape list, and the Leave Balance key is contingent on an unresolved open question. |
| API contracts | **Amber** | Most FRs yield an endpoint + authz rule; three do not (year-boundary rollover trigger, audit-read surface, notification mark-read). |
| Test plan | **Amber** | SM-1..SM-4 are implementable; SM-5 is only half-testable and is blocked by the same missing entitlement attribute; SM-6 is aspirational, not mechanically checkable. |
| Epics / stories | **Green (with one latent gap)** | §4 feature groupings and §7 phasing cut cleanly; no Phase 1 item depends on a later phase; the FR-13/FR-06/FR-08 relationship is a forward dependency, not a cycle. |

---

## 1. ERD readiness

A competent engineer could draw *most* of the diagram from the PRD alone, but not all of it, and one entity the PRD presents as settled is underdetermined.

### Entities the PRD implies, and their determinacy

| Entity | Attributes determined? | Cardinality determined? | Notes |
|---|---|---|---|
| **Employee** | Mostly | Yes | Department (exactly one), Manager (at most one, self-ref), role (enum of 3), joining date, active/deactivated, salted-hash credential (NFR-01). **Undetermined:** the credential/identity field itself is never named (email? username?). FR-01 says "exchange credentials" without saying what the login identifier is. |
| **Department** | Barely | Yes (1→many Employees) | Only a name is implied. Removal is guarded when Employees are assigned (FR-05). No other attribute is specified — thin but not contradictory. |
| **Manager** | N/A | N/A | Not a separate entity. Glossary fixes Manager as an Employee with Direct Reports. Correctly *not* a table. |
| **Leave Type** | **No — presented as settled, actually underdetermined** | Yes | See below. This is the material ERD gap. |
| **Leave Policy** | No | Unclear | Glossary calls it "the set of configured Leave Types." It is not clearly a distinct table vs. just the Leave Type collection. Left to inference. |
| **Company Holiday** | Yes | Yes (many per year) | Date + name, global (A-03). Fully determined. |
| **Leave Request** | Mostly | Yes | Applicant (Employee), Leave Type, contiguous date range, state (enum of 4), optional Supporting Document. **Undetermined:** whether the Leave Day count is stored or derived; whether Leave Year is stored on the row or computed; whether decision/created timestamps exist; date representation is deferred to Architecture (Open Q8 / addendum §3.1). |
| **Leave Balance** | Structure yes; key contingent | Composite key (Employee, Leave Type, Leave Year) | Three stored quantities (Accrued, Reserved, Consumed); Available derived, never stored (DR-3). **The Leave Year component of the key inherits A-09's uncertainty** — if the Leave Year is not the calendar year (Open Q1), the table is keyed wrongly. addendum §3.2 correctly flags this. |
| **Audit Entry** | Yes | Yes (many per Request) | Request, transition, actor, timestamp; append-only. Open shape: one table vs. per-transition (addendum §3.2). |
| **Notification** | **No — and not flagged** | Partially | Addressee (Employee), read/unread state, unread count derivable (FR-14). **Undetermined and unflagged:** whether it links to the Leave Request, whether it carries a type discriminator (submission vs. decision), the message body. Omitted from addendum §3.2's open-shape list — see below. |
| **Supporting Document** | No | Unclear (1↔1 or 1↔many?) | Stored outside web root, client filename not a path (NFR-05). FR-13 says "a Supporting Document" (singular) but never states whether a Request may carry more than one. Correctly listed as open in §3.2. |
| **Session / JWT** | Stateless implied | N/A | JWT presented per request (FR-02). No evidence a session is persisted; likely not an entity. |

### Is addendum §3.2's "shape still open" list complete?

**No.** §3.2 lists: Reporting relationship, Supporting document, Audit entry, Company holiday, Leave balance.

- It **omits Notification**, whose shape is genuinely open (link to Request? type discriminator?). This is a real ERD entity left both underspecified and unflagged.
- It **omits Leave Type**, which the PRD elsewhere treats as settled ("two configured attributes") but which is underdetermined (below).
- Conversely, **Company Holiday is listed as "open" but is actually well-determined** (date + name, global). Listing it as open while omitting Notification and the Leave Type entitlement gap is a misallocation of attention.

### What the PRD treats as settled but is actually underdetermined

**Leave Type — "two booleans" is not enough to build FR-07.** Glossary §3 and FR-06 both state Leave Type carries exactly two attributes: *carries-forward* (bool) and *requires-supporting-document* (bool). But FR-07 requires the system to compute an **Accrued** balance per Employee/Type/Year, with proration for mid-year joiners and carry-forward/lapse at the boundary. Accrual and proration are meaningless without a **per-type annual entitlement quantity** (how many days does EL grant per year? CL? FL?). That quantity is a Leave Type attribute and it appears **nowhere** in the PRD — not in the glossary, not in FR-06, not in FR-07, not in §5. So the answer to "two booleans or more" is: **more.** At minimum a Leave Type needs an annual-entitlement attribute; potentially also a display label (A-04) and, if Open Q2 resolves to a cap, a carry-forward-cap attribute. The PRD presents the two-boolean shape as closed; it is not.

**Leave Balance key** — structurally determined, but its meaning is contingent on Open Q1 (already flagged in §3.2 and §11).

---

## 2. API contract readiness

For most FRs the actor, object, and effect are clear enough to name an endpoint and its authorization rule. The exceptions are specific and namable.

**Derivable cleanly (actor / object / effect / authz all present):**
- FR-01 (public login), FR-04 (Admin CRUD Employee), FR-05 (Admin CRUD Department, remove guarded), FR-17 (Employee self-profile, field-level restrictions specified), FR-06 (Admin configures Leave Type — see caveat), FR-10 (Admin maintains Holiday), FR-08 (Employee submits Request), FR-09 (Manager approve/reject, applicant cancel — transition endpoints), FR-11 (role-scoped dashboard read), FR-18 (Manager reads reports' calendar), FR-15 (Manager/Admin CSV export). Authorization rules for these follow directly from FR-03 and the state-machine table.

**Cross-cutting rules, not endpoints (appropriate, noted for completeness):** FR-02 (JWT on every request), FR-03 (RBAC + data scoping), FR-12 (filter/pagination on list endpoints — though *which* endpoints count as "list endpoints" is left to inference).

**FRs where an endpoint + authz cannot be fully derived:**
- **FR-07 — the year-boundary rollover / accrual operation has no actor and no trigger.** The read side (Employee views own balance) is clear. But carry-forward/lapse at the Leave Year boundary, and initial proration on hire, are described as things that *happen* (UJ-3: "the year rolls over correctly") with **no actor named and no endpoint or job specified**. No role in the state table or FR set is granted a "run rollover" capability. An engineer cannot name this endpoint or its authz rule.
- **FR-16 — the audit *read* surface and its authorization are undefined.** FR-16 specifies audit *writes* as a side-effect of every transition (clear). But whether Audit Entries are *readable* through an API, and if so by whom (Admin only? the applicant? the Manager?), is never stated. No read endpoint or authz rule is derivable.
- **FR-14 — the mark-as-read action is implied, not stated.** "Reading a Notification decrements the unread count" implies a state change, but no explicit mark-read effect/endpoint is defined. GET list and unread-count are clear; the mutation is not.
- **FR-06 caveat** — actor/object/effect are clear (Admin configures Leave Type), but the **request-body schema cannot be fully specified** because the entitlement attribute (§1 above) is missing. The endpoint is namable; its payload is not fully determinable.
- **FR-13 caveat** — namable, but the document cardinality (one vs. many per Request) affects the endpoint shape and is unspecified.

---

## 3. Test plan readiness

**SM-1 (property test over randomized transition sequences) — implementable.** The state machine (§4.5 table) and the invariant (`Available = Accrued − Consumed − Reserved`, `Available ≥ 0`) are both fully specified, which is exactly what a property test needs. A generator emitting legal transition sequences plus the invariant assertion is buildable. It does **not** depend on the unresolved proration method: the invariant is arithmetic over transitions, so the test can seed an arbitrary Accrued value. Implementable as stated.

**SM-3 ("for every endpoint accepting a Leave Request identifier...") — implementable, but meta-dependent.** It is a parametrized/meta-test: enumerate every route with a Leave-Request-id path parameter and assert a non-report Manager gets the not-found response. Mechanically sound *once the API contract exists*. Its coverage is only as complete as the endpoint set, so it presupposes the API contract is derived first. Testable, with that ordering dependency.

**SM-5 ("a fourth Leave Type added through configuration... no schema migration") — only half testable, and blocked.**
- The behavioral half (add a 4th type, apply for it, reserve, approve) is testable **only if** the type can specify how much it grants — i.e., it is blocked by the missing entitlement attribute from §1. "Rolled over at the Leave Year boundary" cannot be exercised for a type whose accrual quantity is undefined. So as stated, SM-5 is not fully runnable against the PRD.
- "No schema migration" **is** verifiable against a schema (assert no migration artifact is produced / schema unchanged) — so yes, it is testable *given a schema*; it is not testable in the abstract without one, but the test plan will have a schema by the time it runs, so this clause is fine.
- "No code change" is **not** a runtime test — it is a property of the implementation effort, checkable only by diff/inspection, not by executing the system. Half of SM-5's assertion is a process check, not a test.

**SM-6 ("every non-obvious implementation choice cites the FR or DR it serves") — aspirational, not mechanically checkable.** "Non-obvious implementation choice" has no machine-enumerable denominator and no required citation format is defined, so there is nothing to check exhaustively against. The companion clause ("every FR traces to a decision in the brief/BRD/memlog") *is* mechanically checkable if traceability is structured, but the "every non-obvious choice cites..." half is a manual-review aspiration. It should be read as a discipline goal, not a pass/fail gate.

(For reference: SM-2 and SM-4 are cleanly implementable — SM-2's boundary cases and SM-4's audit-count-equals-transition-count are both fully specified.)

---

## 4. Story decomposition

**Can epics/stories be cut from §4 and §7 as written?** Yes. §4 groups the 18 FRs into eight behavioral features, each with testable consequences — those are natural epic boundaries. §7 supplies a three-phase build order with depth allocation. Stories are cuttable directly.

**Is §7 phasing consistent with the dependency order the FRs imply?** Yes — no Phase 1 item depends on a Phase 2 or 3 item.
- §7.1 correctly notes FR-06 and FR-10 are prerequisites (FR-08 cannot count Leave Days without holidays; FR-07 cannot roll over without type attributes). Verified: FR-08→{FR-06, FR-10, FR-07}, FR-09→FR-08, FR-16→transitions — all within Phase 1.
- Phase 2/3 items layer *onto* Phase 1 (dashboards, calendar, notifications, upload, export all consume Phase 1 data). FR-14 (P2) makes submit/approve *also* emit a Notification, but the P1 transitions function without it — additive, not a backward dependency.
- FR-03 (P1) depends on Manager assignment from FR-04 (P1). Consistent.

**FR-13 (P3) vs FR-06 (P1) vs FR-08 (P1) — is it circular or broken?**

**Verdict: not circular and not broken — it is a clean forward dependency, with one latent phasing gap that the PRD neither triggers nor rules out.**

- FR-13 (Phase 3) depends on FR-06 (Phase 1, the *requires-supporting-document* attribute) and on FR-08 (Phase 1, submission). Later-depends-on-earlier is correct dependency direction. Phase 1 does **not** depend on FR-13. No cycle.
- **Precision note on the task framing:** the rule "a request for a type requiring a document cannot be submitted without one" is stated in **FR-13's** consequences (line 282), **not** in FR-08. FR-08's own consequences (day count, over-balance refusal, two-year span, reserve-on-admission, concurrency) contain no document clause. So the enforcement rule lives in **Phase 3**, not Phase 1.
- **The latent gap:** FR-06 in Phase 1 can *express* a Leave Type with `requires-supporting-document = true`, but the ability to *satisfy* that requirement (upload) and the *enforcement* of it (block submission without a doc) both live in FR-13 in Phase 3. Therefore, during Phases 1–2, a document-requiring type would be **submittable without a document** (rule not yet enforced), and once FR-13 lands, such a type could not be submitted at all before Phase 3. Whether this actually bites depends on **which of the seed types EL/CL/FL, if any, has `requires-supporting-document = true` — a seed value the PRD never specifies.** If none require a document, Phase 1 is clean and FR-13 only matters for a hypothetical fourth type. If one does, there is an inconsistency window. The PRD does not close this because the seed attribute values are undefined. This is a gap to report, not a broken dependency.

---

## 5. Glossary discipline

§3 declares that introducing a synonym anywhere is a discipline violation. Several nouns drift in §4/§5/§10.

**Drift found (precise):**
- **"request" for "Leave Request"** — pervasive shorthand in §4.4–§4.7, §10, and the UJ narratives ("the request enters Pending," "a count of Pending requests," "reading a Notification"). The full term is defined; the short form is used constantly.
- **"days" for "Leave Days"** — "Reserved days," "reserved days become Consumed," "unused Accrued EL," "carried-forward days," "days requested against days available" (§4.4, §4.5, §7, §10). The glossary term is "Leave Day"; the bare "days" is used loosely throughout.
- **"team" / "reports" / "reportees" for "Direct Reports"** — "who else on the team" (§2.1, §4.6), "two of her other reports" (UJ-2), "reportees" (addendum §2.4). Glossary term is "Direct Report."
- **"rollover" / "roll over" for the Leave Year boundary process (Carry-Forward + Lapse)** — used in UJ-3, §7, FR-06, SM-5. The glossary defines *Carry-Forward* and *Lapse* but not the umbrella term "rollover," which is then used in normative FR/SM text.
- **"applicant" — used in normative text (FR-03, FR-09, FR-13, FR-14) but never defined in §3.** It is a transparent synonym for "the Employee who submitted the Leave Request," but it is an undefined domain noun by the section's own standard.
- **"Available balance" as a compound** — §4.4 and UJ-1 write "his Available balance," conflating the derived quantity *Available* with *Leave Balance*. Understandable, but not a glossary term.

**Checked and clean:**
- **"state" vs "status"** — the domain uses **"state"** consistently for Leave Requests (§4.5 "four states," FR-12 "state," NFR-12 "request state"). "status" appears only as document front-matter metadata (`status: draft`), never for a Leave Request. No drift here.
- Minor informal nouns ("queue," "away," "on approved leave") are used illustratively, not as normative domain terms.

Net: the "state/status" axis is disciplined; the drift is concentrated in **request/days/team-reports/rollover/applicant**.

---

## 6. What Architecture (Module 3) will be forced to decide

The useful split: what the PRD *deliberately hands off* (appropriate delegation) vs. what it *leaves undecided while presenting it as settled or by simply not addressing it* (abdication / gap the PRD should own).

### Appropriate delegation (technical-how, explicitly routed to Architecture)
1. **Reporting-relationship shape** — column-on-Employee vs. standalone relation (addendum §3.2). Load-bearing for DR-12/NFR-04, correctly delegated.
2. **Supporting-document storage mechanism and linkage** (§3.2, NFR-05). Appropriate.
3. **Audit Entry table strategy** — one table vs. per-transition (§3.2). Appropriate.
4. **Concurrency mechanism** — row lock / optimistic version / serializable / DB constraint (§3.3). PRD correctly states the invariant and test without prescribing the mechanism.
5. **Leave-day-function siting** so no layer bypasses it, including the frontend preview (§3.4). Appropriate.
6. **Date representation** — date-without-time vs. instant (Open Q8 / §3.1). Explicitly raised for Architecture to settle. Appropriate.

### Abdication / gaps the PRD does not own (Architecture forced to invent business content, not just mechanism)
7. **Leave Type annual-entitlement attribute** — the "two booleans" shape omits the per-type grant quantity that FR-07 accrual/proration requires (§1 above). Architecture would have to invent this data attribute to make FR-07 buildable. This is **business data dressed as a settled schema**, not technical-how. Abdication.
8. **Year-boundary rollover trigger and actor** — who or what fires carry-forward/lapse (scheduled job? Admin action?). The *mechanism* (job vs. endpoint) is legitimately Architecture's; but *whether an Admin is authorized to trigger it* is an authorization/business question the FR set never answers — no role is granted the capability. **Partial abdication.**
9. **Notification entity shape** — omitted from the §3.2 open list and underspecified (link to Request? type discriminator?). Architecture must invent it. Mild abdication.
10. **Audit read surface and its authorization** (FR-16) — who may read Audit Entries is undefined; Architecture/API must invent an authz rule. Abdication (authorization is a requirements concern, not technical-how).
11. **Employee credential/identity field** — email vs. username is never stated; Architecture picks. Minor.

### Correctly escalated as *open*, not abdicated (routed to the PM/sponsor, not delegated to Architecture)
- **Leave Year definition** (Open Q1 / A-09) — blocks the Leave Balance key; flagged must-answer-before-Day-3. Correctly left open, not silently defaulted.
- **Proration method + rounding** (Open Q3 / A-05) — collides with A-01; explicitly escalated, not resolved. If unanswered before implementation, it *becomes* a forced invention, but the PRD's stance (escalate) is correct.
- **Zero-working-day request** (Open Q6), **post-approval holiday recalculation** (Open Q7), **mid-year policy change effect** (Open Q5 / A-08) — each flagged with its consequence and escalated. Appropriate.

The distinction that matters for Module 3: items 1–6 are ready to be decided technically; items 7–11 are content the PRD should arguably have carried and did not, and the two highest-consequence open questions (Leave Year, proration) will block FR-07/Leave-Balance regardless of how Architecture is written — they are the PM's to close, not Architecture's to invent.

---

## Summary of the highest-impact gaps

1. **Leave Type has no entitlement/grant attribute.** "Two booleans" is presented as settled but is underdetermined; blocks FR-07 accrual/proration, the ERD, and SM-5. (§1, §2, §3, §6)
2. **Leave Year definition is open (Open Q1 / A-09)** and the Leave Balance composite key inherits the uncertainty; flagged must-answer-before-Day-3. (§1, §6)
3. **Year-boundary rollover has no actor or trigger** — no endpoint, job owner, or authz rule derivable for the operation FR-07 depends on. (§2, §6)
4. **Notification entity is omitted from the §3.2 open-shape list and underspecified** (link to Request, type). ERD must invent it. (§1)
5. **Audit read surface and its authorization are undefined** (FR-16) — who may read Audit Entries, through what endpoint, is never stated. (§2, §6)
