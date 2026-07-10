---
title: "Reconciliation Review — Addendum §3 + Module 1 vs ARCHITECTURE-SPINE"
target: "../ARCHITECTURE-SPINE.md"
reviewer: "reconciliation reviewer"
created: 2026-07-10
status: complete
---

# Reconciliation Review — what did NOT land in the spine

**Scope of this review.** For each obligation in the input set, I record: the *source locus*, the *exact obligation*, *coverage* (fully / partially / not at all), and whether the residual needs an **AD** or is **below altitude**. The single most important pass is the addendum's §3 itemized handoff, walked item by item.

**Headline.** The addendum §3 handoff lands in the spine essentially in full — every §3 item is either decided by an AD, recorded as a convention, or consciously deferred. There are **no high-severity silent drops in §3**. The residual gaps sit one layer down, at the NFR / open-question altitude: a bound-but-ungoverned NFR, two open questions the spine resolves-by-schema without acknowledging, and a handful of below-altitude citation nits.

---

## A. Addendum §3 — "Bound for Architecture and the ERD" (the primary pass)

| Item | Obligation | Where it lands | Coverage |
| --- | --- | --- | --- |
| **3.1** Leave date is a `DATE`, not an instant (`DR-2a`) | Store/compare leave dates as calendar dates; prevent midnight-boundary off-by-one | **AD-12 `[ADOPTED]`** + "Dates and instants" convention | **Fully** |
| **3.2** Reporting relationship — attribute vs relation; scope in-query (`DR-12`, `NFR-04`); reassignment immediate for Pending | Decide the shape so authz is a query predicate | **AD-10** decides it as a column predicate `employee.manager_id = :actor_id`, "evaluated at request time, so a reassignment takes effect on the next decision" | **Fully** |
| **3.2** Supporting document — linkage + storage (`NFR-05`) | Outside web root, client filenames never trusted as paths | **AD-15** | **Fully** |
| **3.2** Audit entry — one table vs specialized; append-only (`NFR-09`) | Decide table shape | **AD-8** decides one table; **AD-9** enforces append-only | **Fully** |
| **3.2** Company holiday — date + name, global (`A-03`) | Model it | ERD `COMPANY_HOLIDAY { holiday_date, name }`; one-deployment-one-org | **Fully** |
| **3.2** Leave balance — keyed per employee/type/**Leave Year** (`DR-3`) | Safe key | **AD-5** `UNIQUE (employee_id, leave_type_id, leave_year)` | **Fully** |
| **3.2** Leave type — four Admin-configured attributes (Annual Entitlement, carries-forward, Carry-Forward Cap, requires-supporting-document); balance needs an accrual basis, not a total | Represent all four + the accrual basis | `carry_forward_cap` in **AD-6**; `requires_supporting_document` in **Deferred**; accrual basis via `leave_balance.entitlement_basis` + `prorated_entitlement`. **Annual Entitlement** as a `leave_type` column is *implied* (via `entitlement_basis` provenance) but not explicitly named — consciously pushed to Module 4 ERD by the "Attribute-level schema… Module 4's ERD owns it" Deferred line | **Fully** (attribute enumeration consciously deferred to ERD, not dropped) |
| **3.2** Notification — link, type discriminator, read-state | Decide the shape | **AD-16** (recipient, `kind` ∈ {SUBMITTED, APPROVED, REJECTED}, nullable `read_at`, `created_at`) | **Fully** |
| **3.2** Cancellation Request — separate entity, own lifecycle, Admin-decided, target stays Approved, writes audit for both (`DR-14`, `DR-16`, `SM-4`) | Model as entity | **AD-13 `[ADOPTED]`** | **Fully** |
| **3.2** Audit entry must express a non-human actor (`SYSTEM` / `AUTO_APPROVED_NO_MANAGER`); FK-to-Employee cannot | Nullable/typed actor | **AD-8**: `actor_type` (EMPLOYEE\|SYSTEM), nullable `actor_id` NULL iff SYSTEM; "deliberately not a NOT NULL foreign key" | **Fully** (the specific reason string `AUTO_APPROVED_NO_MANAGER` is a domain constant, below altitude — appears in lifecycle diagram) |
| **3.2a** Rollover — system-triggered, `SYSTEM` actor; **idempotence** the open item | Choose siting + make idempotent | **AD-7** (CLI outside web process) + **AD-6** ("idempotent by construction: re-running… writes the same derived values") | **Fully** — *and* the idempotence question is explicitly answered. **Conscious deviation:** AD-8 routes rollover writes to a separate `rollover_run` table, NOT `audit_entry`; §3.2a said rollover writes "Audit Entries naming `SYSTEM`". Spine resolves this against the PRD glossary + SM-4 and **flags the PRD for amendment**. Handled, not dropped. |
| **3.2a** Audit read surface — Admin alone (`FR-16`, `DR-13`); endpoint shape open | Site the endpoint | Capability map: `api/v1/audit (Admin only)`, governed by AD-8/9/10 | **Fully** |
| **3.2a** `FR-14` mark-read mutation implied, not stated — "still an absence" | Resolve the absence | **AD-16**: idempotent `PATCH`, addressee-only; "FR-14 carries no requirement for this mutation; the PRD is to be amended" | **Fully** — absence closed and PRD amendment flagged |
| **3.3** Concurrency — atomic reserve/consume/release (`NFR-07`), `Available ≥ 0` (`DR-5`); mechanism is Architecture's | Choose a mechanism | **AD-3** (one txn, `SELECT … FOR UPDATE`, lock order) + **AD-4** (guarded conditional update) + **AD-5** (CHECK constraints) | **Fully** |
| **3.4** Leave-day function — one pure impl, called by every path incl. the frontend preview; "admits no exception for the preview" | Site so no layer bypasses; frontend calls it | **AD-2**: `domain.calendar.count_leave_days` is the sole knower of weekend/holiday; client gets counts from the preview endpoint; "No frontend module references a weekday or a holiday" | **Fully** |

**§3 verdict: nothing silently dropped.** Every itemized handoff is decided, converted to a convention, or consciously deferred. Two §3 items the addendum still called "absences/open" (rollover→audit and mark-read) are *closed* by the spine with an explicit "PRD is to be amended" note — the spine is ahead of the addendum, not behind it.

---

## B. NFR-01 … NFR-21 (the full 21, not just the PRD subset)

| NFR | Obligation | Coverage | Verdict |
| --- | --- | --- | --- |
| **01** Credential storage (bcrypt/Argon2, no plaintext) | **AD-14** ("hashed with bcrypt or Argon2 via `pwdlib`"; `passlib` rejected); Stack pins pwdlib/bcrypt | **Fully** |
| **02** Token lifetime — access tokens **expire**, hours if no refresh | AD-14 **lists NFR-02 in its Binds** but its rule body governs only Bearer transport, server-side check, hashing, and `PyJWT` — it says **nothing about token expiry or lifetime**. FR-02's own acceptance ("an expired token is refused") likewise leans on an unstated `exp`. | **Partially — bound but ungoverned.** The lifetime *value* is config (below altitude), but "tokens carry an `exp` and are rejected when expired" is a security invariant. **Needs a one-clause addition to AD-14** (or a convention line). |
| **03** Authz enforced server-side | **AD-14** + **AD-10** | **Fully** |
| **04** Data scoping in the query | **AD-10** ("as a predicate *in the SQL*, never as a filter over retrieved rows") | **Fully** |
| **05** Upload validation / outside web root / authorized-only / filenames-not-paths | **AD-15** | **Fully** |
| **06** Transport TLS in any deployed env | Deployment diagram: `proxy — TLS termination`, `HTTPS · Bearer JWT`. No invariant, no AD cite. | **Below altitude** — adequately covered structurally by the proxy in the deployment seed. |
| **07** Balance ops atomic | **AD-3** (binds NFR-07) | **Fully** |
| **08** Leave-day calc = single pure function | **AD-2** (binds NFR-08) | **Fully** |
| **09** Audit append-only | **AD-9** (role granted INSERT/SELECT, not UPDATE/DELETE) | **Fully** — strongest possible form |
| **10** Interactive response ~500 ms | Not mentioned. | **Below altitude** — a soft target ("an order of magnitude, not contractual"); the NFR-12 indexing conventions serve it. No seam needed. |
| **11** Bounded result sets / pagination | "Pagination" convention (server-side max page size) | **Fully** |
| **12** Indexed access paths (employee, manager, dept, leave year, status) | "Indexing" convention, verbatim | **Fully** |
| **13** Layered structure; policy in service layer not routes/DB | The entire Design Paradigm + **AD-1** embody it (refined into pure `domain/` + `services/` shell). Not cited by the string "NFR-13". | **Fully** (substance); citation nit only |
| **14** Policy as configuration | **AD-11** (binds NFR-14) | **Fully** |
| **15** Tests for the hard rules | **AD-7** (binds NFR-15) + "Testing" convention (`tests/domain` no DB) | **Fully** |
| **16** Role-appropriate interface | **AD-14** ("never the only thing preventing an action") | **Fully** |
| **17** Errors actionable (name the numbers) | "Error shape" convention (`INSUFFICIENT_BALANCE`, `SPANS_TWO_LEAVE_YEARS`) | **Fully** |
| **18** Responsive layout (desktop + tablet) | Not named; Deferred defers "styling and component library" wholesale. | **Below altitude** — folded into deferred styling. |
| **19** Attribution — who + when per transition | **AD-8** (`actor_type`, `actor_id`, `occurred_at`). Not cited by the string "NFR-19". | **Fully** (substance); citation nit only |
| **20** Config environment-supplied | "Configuration" convention (`pydantic-settings`, `.env` uncommitted) | **Fully** |
| **21** Reproducible setup | Structural Seed (`docker compose up` → `alembic upgrade head` → seed) | **Fully** |

**NFR verdict.** 19 of 21 fully governed. **NFR-02 is the one substantive gap** (bound but ungoverned). NFR-06/10/18 are legitimately below altitude. NFR-13/19 are covered in substance but not cited by number — a traceability nit given the spine's own SM-6 "every module names the FR/DR it implements" ethos.

---

## C. Constraints + Engineering Decisions D-01 … D-07

| ID | Obligation | Coverage |
| --- | --- | --- |
| **D-01** Deduct on approval; pending reserve; three quantities | **AD-3/AD-5/AD-6** + lifecycle diagram | **Fully** |
| **D-02** Only working days deducted | **AD-2** | **Fully** |
| **D-03** Authorization data-scoped | **AD-10** | **Fully** |
| **D-04** Policy is configuration | **AD-11** | **Fully** |
| **D-05** FastAPI | Stack + Deferred rationale ("why D-05 chose FastAPI") | **Fully** |
| **D-06** React | Stack | **Fully** |
| **D-07** ~~Approved-leave cancellation out of scope~~ **REVERSED by PRD** | The spine correctly follows the **reversal, not the stale D-07**: **AD-13** models a Cancellation Request entity; the Leave Request lifecycle has `Approved → Cancelled` via an Admin-approved Cancellation Request; `BR-05` is bound and reachable. `Approved` is **not** terminal. | **Fully — follows the PRD reversal.** Confirmed the spine does not carry the stale D-07 position anywhere. |

**Constraints.** Three-roles / single-approval (`A-06`) — lifecycle has exactly one Manager step, no escalation; consistent. Single-tenant (`A-07`) — multi-tenancy Deferred, one deployment = one org. Mid-year policy-change hazard (`A-08`) — **actively handled** by `entitlement_basis` provenance ("something to recalculate from"). All consistent.

---

## D. Brief success criteria

| Criterion | Coverage |
| --- | --- |
| Requirements covered; every decision traces to a document / defensible aloud | "Traceability" convention (SM-6: every module names its FR/DR) + Capability→Architecture map. **Fully.** |
| Correct where hard: balances across proration/carry-forward/year boundary; day count excludes weekends+holidays; authz scoped to direct reports; every action audited | **AD-6** (carry-forward derived + idempotent), **AD-2** (day count), **AD-10** (scope), **AD-8** (audit). **Fully.** |
| Assumptions/open questions visible | Deferred section surfaces several. **Partially** — see §F: proration rounding, accrual method, holiday-recalc scope, and the confirmed leave-year boundary are not all surfaced. |

---

## E. BR-01 … BR-06

| BR | Coverage |
| --- | --- |
| **01** Three types EL/CL/FL | **AD-11** + `seed/` inserts EL, CL, FL as data. **Fully.** |
| **02** Mid-year joiner prorated | `domain/proration`, `prorated_entitlement`. **Fully** (but see §F-M2 on accrual method). |
| **03** EL carries forward; CL/FL lapse | **AD-6** derives carry-forward from `leave_type.carry_forward_cap` (lapse = cap 0), configured per AD-11. **Fully** (behaviour is data, not code). |
| **04** No request spans two leave years | Surfaced via `SPANS_TWO_LEAVE_YEARS` error; enforced in the `domain`/`services` submit path; boundary type fixed by AD-12. **Fully** (the refusal is modelled; the *boundary date* is below altitude — see F-L1). |
| **05** Cancelling approved leave restores balance | **AD-13** ("only an approved Cancellation Request moves it to Cancelled, releasing its Consumed days"); binds BR-05. **Fully — now reachable.** |
| **06** No restriction on concurrent same-date leave | Honoured by absence of any blocking constraint; `FR-18` Department Leave Calendar (capability map, AD-10) is the informational overlap surface. **Fully** (the "inline on the approval screen" placement from addendum §2.4 is UX, below altitude). |

---

## F. Findings, ranked

### High severity
**None.** No addendum §3 item was silently dropped.

### Medium

**F-M1 — NFR-02 token expiry is bound but ungoverned.**
- *Locus:* NFR-02; FR-02 acceptance ("an expired token is refused").
- *Obligation:* access tokens expire (lifetime in hours if no refresh mechanism).
- *Coverage:* **Partial.** AD-14 lists NFR-02 in its Binds, but the rule body governs only Bearer transport, server-side enforcement, hashing, and `PyJWT` — token *expiry* is never stated.
- *Disposition:* **Needs an AD clause.** Add one sentence to AD-14 (tokens carry an `exp`; verified on every request; no refresh in scope) or a "Token lifetime" convention. The value is config/below-altitude; the *existence of expiry* is a security invariant and the spine already names PyJWT, so this is a small, natural addition.

**F-M2 — Proration accrual method (A-05) is silently resolved, and the rounding rule (FR-07 Open / addendum Open Q3) is neither decided nor deferred.**
- *Locus:* A-05 ("whether monthly or an annual grant is unstated"); FR-07 **Open** ("the proration method and its rounding"); addendum §2.2 + §3.2 (`DR-9` "monthly against remaining months"; the rounding collision with `A-01`).
- *Obligation (two parts):* (a) settle the accrual model; (b) choose a rounding rule, because — per §2.2 — the industry-default half-day rounding **cannot be expressed** under the integer constraint, "so a different rule must be chosen deliberately."
- *Coverage:* **Partial / not surfaced.** (a) The spine's **AD-5** identity `CHECK (accrued = prorated_entitlement + carried_forward)` and its "accrued as a year-start fixed quantity" model **silently resolve A-05 to one-time-proration-at-join** and foreclose continuous monthly accrual — there is a `jobs/rollover` but no monthly-accrual job seam. That is a defensible decision, but it is made by schema identity without being acknowledged as resolving an open assumption. (b) The **rounding rule is absent** from both the ADs and the Deferred list, even though the "Leave quantities INTEGER everywhere (DR-10)" convention makes a deliberate integer-rounding rule mandatory.
- *Disposition:* **Below altitude for the rule value, but needs surfacing.** Make the accrual-model resolution explicit (a line noting proration is computed once at join, not accrued monthly — which is what AD-5 already assumes), and add a Deferred entry for the proration rounding rule (product decision, blocks `domain/proration`).

**F-M3 — Holiday-recalculation scope for already-approved leave is named but not resolved.**
- *Locus:* assumptions-and-constraints Open Questions — "Recalculation after a late-declared holiday… Not recalculating is the defensible position… remains a proposal"; FR-10 capability ("Holiday management and **recalculation**"); AD-3 Prevents ("deadlock between submission, decision, **holiday recalculation**, and the rollover job").
- *Obligation:* decide whether a holiday declared *after* approval recalculates the already-Consumed leave.
- *Coverage:* **Partial.** The spine *provisions the locking* for a holiday-recalculation command (AD-3) and lists it as an FR-10 capability, i.e. it assumes recalculation exists as a balance-writing command — but it never states its **scope** (Pending-only vs. also Approved/Consumed). The open question the source flagged is left unanswered while the machinery for it is reserved.
- *Disposition:* **Below altitude to fully resolve (product proposal), but the scope should be stated** since the spine already reserves the lock ordering for it. One Deferred line, or a scope note on the FR-10 row.

### Low / below altitude (record so absence reads as decision)

- **F-L1 — Leave-year = calendar year (A-09).** The highest-consequence *confirmed* assumption (addendum §3.2: "confirmed as the calendar year… it was the highest-consequence open risk"). The spine keys by `leave_year` (satisfying the architectural need — a safe partition key) but never pins the boundary to 1 Jan–31 Dec. **Below altitude** (the boundary is a domain constant used by `domain/calendar` and `domain/carry_forward`), and abstracting it is arguably good design — but a one-line convention would record the confirmed fact.
- **F-L2 — NFR-06 TLS.** Present only in the deployment diagram (proxy termination), no invariant. Below altitude / structural.
- **F-L3 — NFR-10 (~500 ms).** Absent. Below altitude (soft target; served by NFR-12 indexing).
- **F-L4 — NFR-13 & NFR-19 citations.** Substance fully covered (paradigm+AD-1; AD-8) but not cited by number. Traceability nit against the spine's own SM-6 ethos.
- **F-L5 — NFR-18 responsive layout.** Folded into wholesale-deferred styling. Below altitude.
- **F-L6 — FR-05 department-removal guard.** "A department cannot be removed while employees are assigned" is not noted, though FR-04's analogous "deactivation guards in services" is. Minor asymmetry; below altitude (a services-layer FK guard).
- **F-L7 — Encashment non-goal + EL-above-cap forfeiture (Open Q2).** AD-6's `min(cap, available)` implements exactly the silent-forfeiture-above-cap behaviour that addendum §2.2 flagged as a possible statutory exposure (EL above the cap "generally required to be encashed rather than forfeited"). Encashment is a PRD Non-Goal (§1.5), yet the spine's Deferred non-goals list (email/PDF/charts) omits it. Below altitude (product/legal), but a Deferred line would close the loop where the behaviour technically lands.

### Conscious deviations (handled — listed for completeness, not gaps)
- **AD-8:** rollover writes `rollover_run`, not `audit_entry` — contradicts addendum §3.2a's "Audit Entries naming SYSTEM"; spine flags PRD amendment.
- **AD-16:** mark-read decided though "FR-14 carries no requirement"; spine flags PRD amendment.

---

## G. Verdict

The spine is a faithful projection of the addendum §3 handoff — **no §3 obligation was silently dropped**, and two items the addendum still logged as open ("absences") are closed with explicit PRD-amendment notes. D-07's reversal is correctly followed. The residual is a short tail of NFR/open-question partials, of which only **NFR-02 (F-M1)** clearly warrants an AD edit; **F-M2** and **F-M3** warrant a Deferred entry / explicit acknowledgement rather than new machinery; the rest are legitimately below altitude.
