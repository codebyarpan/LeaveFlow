---
title: "LeaveFlow — FR Integrity Audit (PRD vs Module 1 BRD)"
type: forensic-review
created: 2026-07-09
auditor: requirement-integrity-audit
scope: FR-01..FR-18 carry-over, UJ/DR/SM/A cross-reference resolution
---

# FR Integrity Audit

**Claim under test:** the PRD carries FR-01 through FR-18 over from the Module 1 BRD "verbatim" / "unchanged in meaning," only regrouping them by behavior.

**Sources compared:**
- PRD: `prds/prd-LeaveFlow-2026-07-09/prd.md`
- Upstream: `module-1-business-analysis/functional-requirements.md`
- Cross-check: `module-1-business-analysis/brd.md`, `module-1-business-analysis/stakeholder-analysis.md`

---

## 1. Presence, grouping, non-duplication

All 18 FRs are present in the PRD exactly once. They are distributed across §4.1–§4.8 out of numeric order, as the PRD declares (§4 intro, line 115).

| PRD section | FRs housed |
|---|---|
| §4.1 Identity and Access | FR-01, FR-02, FR-03 |
| §4.2 Organization Administration | FR-04, FR-05, FR-17 |
| §4.3 Leave Policy Configuration | FR-06, FR-10 |
| §4.4 Leave Balances | FR-07 |
| §4.5 Leave Request Lifecycle | FR-08, FR-09, FR-13, FR-16 |
| §4.6 Visibility and Decision Support | FR-11, FR-18, FR-12 |
| §4.7 Notifications | FR-14 |
| §4.8 Reporting and Export | FR-15 |

Total = 3+3+2+1+4+3+1+1 = **18. No FR missing. No FR duplicated.**
Cross-check against §7 phase plan: Phase 1 (12) + Phase 2 (4) + Phase 3 (2) = 18, each FR listed once. Consistent.

---

## 2. Meaning preservation, FR by FR

Legend: **PRESERVED** = meaning intact. **NARROWED (declared)** = scope reduced, reduction stated in the PRD. **NARROWED (silent)** = scope reduced without declaration. **RETITLED** = heading changed.

### FR-01 User Authentication — PRESERVED
- M1: "A user authenticates with credentials and receives a session. Unauthenticated requests to protected resources are refused." Acceptance: valid establishes session; invalid rejected without disclosing account existence; passwords never stored recoverably.
- PRD (§4.1): "An **Employee** can exchange credentials for an authenticated session." Consequences: correct pair returns token/incorrect does not; failed auth does not disclose account existence (body/status/timing); no stored representation permits recovery.
- Verdict: identical meaning. M1 "user" → PRD "Employee" is a vocabulary tightening consistent with the glossary (every account-holder is an Employee).

### FR-02 JWT-Based Authorization — PRESERVED
- M1: JWT on each request; no/expired/tampered token refused; valid token identifies user and role.
- PRD (§4.1): token presented per request; no-token/expired/bad-signature rejected, including payload altered to change subject or role.
- Verdict: identical.

### FR-03 Role-Based Access Control — PRESERVED
- M1: three roles; Manager acts only on own direct reports (relationship, not role, is checked); Admin may view all requests, no approval authority.
- PRD (§4.1): grants exactly one role; scopes Manager to Direct Reports; non-report request returns same response as nonexistent; Admin reads all, decides none; enforced at API boundary.
- Verdict: identical, and elaborated with testable consequences. No drift.

### FR-04 Employee Management — PRESERVED
- M1: Admin CRUD + deactivate employees/managers, including reporting relationship; record carries department and manager; deactivation preserves historical leave records.
- PRD (§4.2): Admin create/read/update/deactivate including Department, role, joining date, Manager; deactivation preserves Leave Requests, Balances, Audit Entries; deactivated cannot authenticate.
- Verdict: preserved. PRD adds detail (role, joining date, cannot-authenticate) consistent with M1; no removal.

### FR-05 Department Management — PRESERVED
- M1: Admin CRUD + remove departments; cannot remove while employees assigned.
- PRD (§4.2): same; refusal "names the obstruction."
- Verdict: identical.

### FR-06 Leave Type Management — PRESERVED
- M1: Admin configures leave types/policies; EL/CL/FL; EL carries forward, CL/FL lapse; config not code; 4th type no code change. Open: FL name, EL cap, accrual.
- PRD (§4.3): same; three types at init; carries-forward + requires-document as data; 4th type works end-to-end without code/schema change; no name-branching. FL-name assumption A-04 carried as `[NOTE FOR PM]`.
- Verdict: preserved; open items carried forward, not resolved.

### FR-07 Leave Balance Tracking — PRESERVED
- M1: balance per type/year; accrued/reserved/consumed, available = accrued − consumed − reserved; partitioned by leave year (A-09); mid-year joiner prorated; carry-forward/lapse per FR-06. Open: proration method/rounding.
- PRD (§4.4): identical three-quantity model; invariant after every transition; never negative; proration (BR-02); carry-forward/lapse (BR-03); Available primary with Reserved disclosed. Proration `[NOTE FOR PM]` retained.
- Verdict: preserved; open items retained, not resolved.

### FR-08 Leave Request Workflow — PRESERVED
- M1: submit range against type; compute leave days, reserve; only working days, weekends/holidays excluded; Fri–Tue with a holiday = 2 days; may not span two calendar years; over-available refused at submission.
- PRD (§4.5): identical, plus the Fri–Tue-2-days example verbatim, plus "two concurrent submissions cannot both succeed" (consistent with NFR-07). Zero-working-day range flagged Out of Scope / §11.
- Verdict: preserved; PRD adds a consequence, removes nothing.

### FR-09 Approval and Rejection — PRESERVED
- M1: Manager approves/rejects pending from direct report; approval → consume, rejection → release; employee cancels own pending; no overlap restriction (BR-06); D-07 — approved-leave cancellation not supported; BR-05 retained as policy only.
- PRD (§4.5): identical state machine; Approved terminal; Admin cannot decide; each transition writes one Audit Entry; BR-05/D-07 note carried verbatim in substance.
- Verdict: preserved. D-07 provenance and the BR-05 contradiction-resolution are both carried through.

### FR-10 Holiday Management — PRESERVED
- M1: Admin maintains holiday calendar; holidays are input to leave-day calc (FR-08); a holiday excluded from any leave-day count spanning it; global (assumption).
- PRD (§4.3): holiday = date + name; not a Working Day, not counted by FR-08; global, not scoped (A-03).
- Verdict: preserved.

### FR-11 Dashboard — **RETITLED + NARROWED (DECLARED)**
- M1 title: "Dashboard Analytics." M1: "Each role sees a dashboard appropriate to its permissions." **Open — scope undefined:** "'Dashboard analytics' spans anything from summary cards to charts with date-range filtering. Not testable as written; the assigning manager must define it."
- PRD title: "Dashboard." PRD (§4.6): per-role summary cards (Employee: per-type Available/Reserved/Consumed + pending count; Manager: pending-decision count + reports on approved leave next 7 days; Admin: org totals). Every figure authorized per FR-03.
- **Narrowing:** charts/trend-lines/date-range analytics moved to `[NON-GOAL for MVP]`.
- **Is it declared?** YES, three times: §4.6 FR-11 Notes ("The specification's phrase 'dashboard analytics' is broader than what is built here; this is a deliberate narrowing…"), §7.4 ("The specification's 'dashboard analytics' is read narrowly, and the narrowing is declared rather than assumed"), and §7.2 (summary cards only). The retitle from "Analytics" to "Dashboard" is the visible marker of the narrowing.
- Verdict: meaning changed (scope reduced), but the change is **openly declared, not silent.** The PRD also resolves the M1 "not testable as written" gap by supplying testable consequences — a strengthening, not a silent addition of unstated scope.

### FR-12 Search, Filtering, and Pagination — PRESERVED
- M1: collection endpoints support search/filter/pagination; bounded page size; filters compose; respect caller scope (Manager sees only direct reports).
- PRD (§4.6): server-enforced max page size; filters compose (type/state/date); filtering never widens authorization (FR-03).
- Verdict: preserved. (Minor: M1 says "search, filtering, and pagination"; PRD consequences emphasize filtering + pagination; "search" is not separately elaborated but the heading and scope are retained — not a meaning change.)

### FR-13 Supporting Document Upload — **RETITLED; scope drift on document visibility (see Finding B)**
- M1 title: "File Upload for Leave Documents." M1: employee uploads supporting document where the type requires one; associated with request and **"retrievable by those authorized to view that request"**; file type/size validated.
- PRD title: "Supporting Document Upload." PRD (§4.5): cannot submit required-doc type without a doc; type/size validated before storage; document **"retrievable by its applicant and by that applicant's Manager, and by no other Employee."**
- **Retitle:** cosmetic; "Supporting Document" is the glossary term. Meaning of the upload itself preserved. The retitle is **not declared** anywhere (unlike FR-11/14/15) but is inconsequential.
- **Scope drift (Finding B):** M1 scopes retrieval to "those authorized to view that request." Per FR-03, an **Admin** may read every Leave Request, so under M1 an Admin is authorized to retrieve the document. The PRD restricts retrieval to applicant + Manager and "no other Employee." Whether this silently excludes the Admin turns on whether an Admin counts as "Employee" (the glossary defines Admin as a role and does not explicitly state an Admin is an Employee; a Manager is explicitly an Employee). This is an unresolved narrowing/ambiguity introduced by the PRD's rewording, and it is **not declared.**
- Verdict: upload meaning preserved; **document-visibility scope silently altered/ambiguous vs M1.**

### FR-14 In-App Notifications — **RETITLED + NARROWED (DECLARED)**
- M1 title: "Email or In-App Notifications." M1: users notified of relevant events (submission → manager, decision → employee). **Open — scope undefined:** "The specification permits either email or in-app delivery… must be settled by the assigning manager."
- PRD title: "In-App Notifications." PRD (§4.7): in-app only; one Notification to Manager on submission, one to applicant on decision; readable only by addressee; unread count.
- **Narrowing:** email delivery dropped.
- **Is it declared?** YES, three times: §4.7 Notes (full trade-off: "in-app-only notification is therefore a known departure… Email delivery is deferred, not deemed unnecessary"), §6 Non-Goals ("Send email. See FR-14"), and §7.4 (with a `[NOTE FOR PM]` flagging it as the deferral most likely to be challenged).
- Verdict: meaning changed (delivery channel narrowed), but **openly declared with counter-evidence stated.** Resolves the M1 open question by decision, transparently.

### FR-15 Reports and Export — **NARROWED (DECLARED); title unchanged**
- M1 title: "Reports and Export." M1: Managers export team reports, Admins export org-wide; content respects caller scope. **Open:** "Whether CSV suffices or PDF is required. PDF generation is materially more work."
- PRD (§4.8): Manager exports Direct Reports, Admin exports org-wide; **"Export format is CSV."** PDF `[NON-GOAL for MVP]`.
- **Is it declared?** YES: §4.8 Notes ("The specification permits 'CSV or PDF.' CSV alone is chosen; PDF… a material cost") and §7.4.
- Verdict: meaning changed (format narrowed from CSV-or-PDF to CSV), **openly declared.** Resolves M1 open question by decision.

### FR-16 Audit Logs — PRESERVED
- M1: every leave state transition recorded; entry = request + transition + acting user + timestamp; append-only, not modified/deleted by app logic.
- PRD (§4.5): identical; entry count = transition count.
- Verdict: identical.

### FR-17 Personal Profile Management — PRESERVED; **provenance note dropped (Finding C)**
- M1: employee views/updates own profile; may update only own; entitlement/authorization/structure fields (role, department, manager, joining date, balances) not editable by owner.
- PRD (§4.2): employee edits own fields and no other's; role/Department/Manager/joining date/any Balance quantity not editable via profile endpoint.
- Verdict: meaning identical. **However** — M1 (functional-requirements.md line 13, and brd.md §4/§5) explicitly records that FR-17 is **derived** from a permission the specification grants in a role definition but omits from its enumerated requirements list ("specified capabilities, not invented ones"). The PRD carries the requirement but **does not preserve this provenance note** anywhere; §0 states only that identifiers FR-01–FR-18 are "carried over unchanged."

### FR-18 Department Leave Calendar — PRESERVED; **provenance note dropped (Finding C)**
- M1: Manager views team leave calendar so coverage is visible before decision; shows approved + pending for own direct reports (FR-03); informational, BR-06 no restriction, never blocks.
- PRD (§4.6): shows Approved + Pending visually distinguished; only viewing Manager's Direct Reports; on the approval screen for the request's dates; never prevents approval (BR-06).
- Verdict: meaning identical, elaborated. **Same provenance omission as FR-17** — M1 marks FR-18 as derived from role permissions, not enumerated; the PRD does not restate that derivation.

---

## 3. Targeted scope checks requested

- **FR-11 retitle + narrowing to summary cards:** DECLARED (not silent). See FR-11 above. Declared in §4.6 Notes, §7.2, §7.4.
- **FR-13 "File Upload for Leave Documents" → "Supporting Document Upload":** retitle is cosmetic and undeclared but harmless; the **document-visibility scope change (Admin retrieval) is silent** — Finding B.
- **FR-14 "Email or In-App" → "In-App":** DECLARED narrowing. §4.7 Notes, §6, §7.4.
- **FR-15 CSV-or-PDF → CSV:** DECLARED narrowing. §4.8 Notes, §7.4.
- **FR-17 / FR-18 DERIVED provenance:** the PRD does **NOT** preserve the "derived from role permissions, not in the enumerated spec list" provenance that M1 states for FR-17 and FR-18. **Should it?** For strict traceability integrity, yes — a downstream reader of the PRD alone cannot tell that two of the eighteen were engineer-surfaced capabilities rather than enumerated spec requirements. The omission does not change the requirements' meaning, but it drops a traceability fact that Module 1 deliberately recorded. Finding C.

---

## 4. Role-to-FR traceability matrix — does it still hold?

Module 1 matrix (functional-requirements.md §Traceability):

| Role | M1 Requirements | Holds against PRD text? |
|---|---|---|
| Admin | FR-04, FR-05, FR-06, FR-10, FR-11, FR-15, read-only FR-08 | Holds. PRD §4 gives Admin exactly these; FR-03 grants read-all of requests (= read-only FR-08). |
| Manager | FR-09, FR-11, FR-12, FR-14, FR-15, FR-18, read of direct reports (FR-03) | Holds. All actors match PRD. |
| Employee | FR-07, FR-08, FR-13, FR-14, FR-17, cancel-pending (FR-09) | Holds. FR-14 addressee-on-decision = applicant/Employee; matches. |
| All roles | FR-01, FR-02, FR-03, FR-12, FR-17 | Holds. |
| System | FR-16 | Holds. |

**No FR's actor is changed by the PRD in a way that contradicts the matrix, with one documented discrepancy:**

- **FR-11 / Employee (Finding D):** The M1 matrix lists FR-11 under **Admin and Manager only — not Employee.** The PRD's FR-11 (§4.6) explicitly gives the **Employee a dashboard** ("The Employee dashboard presents… Available, Reserved, Consumed; plus a count of Pending requests"), and UJ-1 depends on Rahul's own dashboard. So against the PRD text the M1 matrix is **incomplete for FR-11** (Employee actor missing). Note: this is a **pre-existing Module 1 internal inconsistency** — M1's own FR-11 body says "Each role sees a dashboard," which already contradicts its matrix. The PRD is faithful to the M1 FR-11 **text**; it is the M1 **matrix** that never included the Employee. Not a PRD-introduced drift, but the matrix no longer traces cleanly and is flagged.

---

## 5. Cross-reference resolution and ID-sequence integrity

### FR references (every FR-xx mentioned must exist)
Every FR reference in the PRD (in §2.3 UJ realizations, §4 consequences, §5 DRs, §7 phases, §10 SMs) points to an FR within FR-01..FR-18. **No dangling FR reference. No reference to FR-19+.** Sequence FR-01..FR-18 complete: no gap, no duplicate.

### UJ-1..UJ-3
Defined §2.3. Referenced in §4.1 (UJ-2), §4.2/§4.3/§4.8 (UJ-3), §4.4 (UJ-1), §4.5 (UJ-1, UJ-2), §4.6 (UJ-2), §4.7 (UJ-1, UJ-2). All three exist; no UJ-4 referenced. **All resolve; sequence complete, no gap/dup.**

### DR-1..DR-16
Defined §5.1–§5.5: §5.1 {DR-1, DR-2}, §5.2 {DR-3, DR-4, DR-5}, §5.3 {DR-6, DR-7, DR-8}, §5.4 {DR-9, DR-10, DR-11}, §5.5 {DR-12, DR-13, DR-14, DR-15, DR-16}. Sixteen, contiguous. Referenced in §10 SMs, §7.4, Open Questions, §12. Every DR reference resolves. **Sequence complete, no gap/dup.**

### SM-1..SM-8 (+ SM-C1..SM-C3)
Defined §10: SM-1..SM-4 (Primary), SM-5..SM-8 (Secondary), SM-C1..SM-C3 (Counter-metrics). All eight SMs + three counters present and contiguous. SM-8 referenced in §10 intro; SM-C1 references SM-8/SM-1..SM-4. **All resolve; no gap/dup.**

### A-01..A-09
Defined §12 Assumptions Index, contiguous A-01..A-09 (nine). Referenced: A-01 (§3, DR-10, FR-08), A-02 (§3, DR-1), A-03 (§3, FR-10, DR15-adjacent), A-04 (§4.3, FR-06), A-05 (§4.4, DR-9, OQ3), A-06 (§2.2), A-07 (§2.2, §6), A-08 (§4.3, OQ5), A-09 (§3, DR-8, OQ1). Every A-reference resolves to an index entry. **Sequence complete, no gap/dup.**

- **Minor self-consistency note (SM-7):** SM-7 targets bidirectional inline↔index consistency ("every [ASSUMPTION] inline appears in §12, and every §12 entry appears inline"). Inline `[ASSUMPTION: A-xx — …]` tags exist for A-01, A-02, A-03, A-04, A-06, A-07, A-09. **A-05 and A-08 appear in §12 and are referenced in prose/Open Questions but are not carried as inline `[ASSUMPTION: …]` blocks.** This does not break cross-reference resolution (both resolve), but it is a technical miss against SM-7's own stated bidirectional target. Tangential to FR integrity; recorded for completeness.

### NFR references
- **NFR-19 (Finding E, minor):** DR-16 (§5.5) cites "`NFR-09, NFR-19`." §8 lists NFR-01..NFR-18, NFR-20, NFR-21 (20 of a stated 21) and explicitly says it is a **subset**, "the full register lives in Module 1." So NFR-19 is not resolvable **within the PRD**, but the PRD discloses that the NFR register is intentionally partial. Not a true dangling reference given the disclaimer, but a reader cannot resolve NFR-19 without Module 1. All other NFR references (NFR-04, 05, 07, 08, 09, 14) resolve within §8.
- D-01..D-07 and BR-01..BR-06 references all resolve to Module 1 origins as cited; no dangling decision/rule reference.

---

## 6. Findings summary

| ID | Severity | Finding |
|---|---|---|
| A | Informational | The PRD's actual claim (§0 line 14, §4 line 115) is narrower than "verbatim": it claims **identifiers** are carried over unchanged and FRs are **regrouped by behavior** — it does not claim textual verbatim. Under that literal claim, integrity holds. |
| B | **Material** | **FR-13 document-visibility scope silently narrowed/ambiguous.** M1 = retrievable by "those authorized to view that request" (includes Admin via FR-03 read-all). PRD = applicant + Manager + "no other Employee," which silently excludes/leaves-ambiguous Admin retrieval. Undeclared. |
| C | Moderate | **FR-17 and FR-18 provenance dropped.** M1 records both as derived from role-definition permissions, not from the enumerated spec list. The PRD preserves the requirements but not this traceability fact. |
| D | Moderate | **Role-to-FR matrix no longer traces cleanly for FR-11.** PRD gives the Employee a dashboard; M1 matrix lists FR-11 under Admin/Manager only. (Pre-existing M1 self-inconsistency — M1 FR-11 body already says "each role"; PRD follows the body, not the matrix.) |
| E | Minor | **NFR-19** cited by DR-16 is not resolvable within the PRD (§8 is a declared subset; full register in Module 1). |
| F | Minor | **FR-11/FR-13/FR-14 retitled.** FR-11 ("Analytics"→"Dashboard") and FR-14 ("Email or In-App"→"In-App") retitles are declared as part of declared narrowings. **FR-13 retitle ("File Upload…"→"Supporting Document Upload") is undeclared** but cosmetic. |
| G | Minor | **SM-7 self-consistency:** A-05 and A-08 are in §12 but lack inline `[ASSUMPTION:]` tags, against SM-7's bidirectional target. |

### Declared vs silent scope changes
- **Declared (transparent) narrowings:** FR-11 (summary cards only), FR-14 (in-app only), FR-15 (CSV only). All three resolve M1 open questions **by explicit decision with the trade-off and counter-evidence stated** — the opposite of silent.
- **Silent / undeclared changes:** FR-13 document-visibility scope (Finding B); FR-13 retitle (Finding F, harmless); FR-17/FR-18 provenance omission (Finding C).

---

## 7. Verdict on the "unchanged in meaning" claim

**The claim holds for 14 of 18 FRs verbatim-in-meaning (FR-01–FR-10, FR-12, FR-16, FR-17*, FR-18*).**

Four FRs had their scope **changed**, not merely regrouped:
- FR-11, FR-14, FR-15 — scope **narrowed, but openly declared** in the PRD (§4 Notes + §6/§7.4). These are transparent decisions, not silent drift; the PRD explicitly says the specification's language is "broader than what is built here."
- FR-13 — upload meaning preserved, but **document-visibility scope silently narrowed/ambiguous** vs M1 (Admin retrieval). This is the **one genuinely silent scope change.**

Two additional integrity gaps: **FR-17/FR-18 lost their "derived, not enumerated" provenance** (Finding C), and the **role-to-FR matrix no longer traces cleanly for FR-11** (Finding D).

**Net:** The precise claim the PRD actually makes — "identifiers FR-01–FR-18 carried over unchanged, regrouped by behavior" — **holds**. The stronger claim "verbatim / unchanged in meaning" is **substantially but not fully true**: three meaning-changes are declared (so not deceptive), one meaning-change (FR-13 doc visibility) is silent, and two provenance/traceability facts were dropped. **No FR is missing, none is duplicated, and there are no dangling FR/UJ/DR/SM/A cross-references** (NFR-19 is the only unresolved reference, and it is disclosed as living in Module 1). All ID sequences (FR-01..18, UJ-1..3, DR-1..16, SM-1..8, A-01..09) are contiguous with no gaps or duplicates.
