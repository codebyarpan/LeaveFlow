---
title: "Reconciliation — amended PRD vs Module 4 ERD"
reviewer: reconciliation
date: 2026-07-10
prd: ../prds/prd-LeaveFlow-2026-07-09/prd.md
erd: ../module-4-erd/erd.md
---

# Reconciliation: amended PRD → Module 4 ERD

**Verdict.** The ERD *schema* (tables, columns, constraints, grants) survives all seven amendments unchanged — every structural check is CLEAN. What the amendments break is the ERD's **provenance and gap narrative**: the amended PRD now *supplies* `email`/`full_name` (Glossary + FR-17/FR-04) and the PM has now *decided* the attribution question, so the ERD's "no source document names these" and "routed upstream, PM to decide" prose is now false. Five prose findings (2 CONTRADICTION, 3 STALE); no schema change required.

The seven amendments in scope: A1 (DR-7 "unused = Available", recomputed), A2 (FR-07 rollover → separate log), A3 (FR-10/FR-06 refusal per Employee+Leave Type into a durable Admin-readable/resolvable store; DR-5 names Leave Policy change), A4 (FR-14 mark-read), A5 (Vision narrowed to Leave-Request state changes; no holiday-change entity, no policy_change actor), B1 (Email Address + Full Name are Glossary terms; Full Name sole Employee-editable field, Email Address Admin-maintained), B2 (EL/CL/FL seed requires-supporting-document FALSE).

---

## 1. §2.1 EMPLOYEE provenance for `email` and `full_name` — **CONTRADICTION**

The ERD §2.1 EMPLOYEE table says `email` = "**No source document names the identifier**; email is a project decision of 2026-07-10", `full_name` = "**No source document names any profile attribute**; project decision of 2026-07-10", and closes: "`email` and `full_name` are the only two attributes in this model that no source document supplies."

The amended PRD now **supplies both** as Glossary terms and via FRs:
- **Email Address** (Glossary §3): "The unique identifier an **Employee** exchanges as their credential under `FR-01`. Maintained by the **Admin** (`FR-04`); not editable by the Employee who owns it."
- **Full Name** (Glossary §3): "The human-readable identity of an **Employee**, shown wherever an Employee is listed (`FR-19`). The only profile field its owner may edit (`FR-17`)."
- FR-17: "The only profile field an **Employee** may edit is their **Full Name**"; "The **Email Address** is maintained by the **Admin** under `FR-04`."

The provenance note is now false. It should say:
- `email` → **PRD §3 Glossary "Email Address"** + `FR-01` (credential) + `FR-04` (Admin-maintained). No longer an unsourced project decision.
- `full_name` → **PRD §3 Glossary "Full Name"** + `FR-17` (sole editable field) + `FR-19` (displayed).
- Delete the closing sentence "the only two attributes … that no source document supplies." Every attribute in the model is now sourced; there is no longer any unsourced attribute.

The **column values are correct and unchanged** — only the provenance prose is stale/contradicted.

## 2. §6 GAP-1 and GAP-2 "[RESOLVED by project decision]" — **CONTRADICTION**

GAP-1 states: "**No document in the chain — brief, BRD, functional requirements, NFRs, assumptions register, PRD, addendum — ever names what the identity is. Verified by search.**" GAP-2 states `FR-17` "never says what remains" editable.

Both factual premises are now directly contradicted by the amended PRD: the **Glossary names Email Address as the credential identifier** and **names Full Name as the sole editable profile field**, and FR-17 states the same. The "verified by search / no document names it" assertion is no longer true.

The gaps are not merely resolved by a bare project decision — they are now **closed by the PRD itself as source of record**. GAP-1/GAP-2 should be re-marked (e.g. "[RESOLVED — now named in PRD §3 Glossary + FR-17/FR-04]") and their bodies must:
- drop the "no document ever names it / verified by search" claims;
- cite the Glossary "Email Address" and "Full Name" terms plus FR-17 (editable surface = Full Name) and FR-04 (Admin maintains Email Address) as the source of record.

Note: GAP-1's downstream reasoning ("An Admin may change an Employee's email through FR-04's update; the Employee may not, because FR-17's editable surface is `full_name` alone"; "identity, not a contact channel; LeaveFlow sends no email") **matches the amended Glossary exactly** and stays correct — only the "unsourced" premise is contradicted.

## 3. §6 GAP-3 (and the `POLICY_CHANGE` "GAP-3 — no actor" callout, and §6 intro) — **STALE**

GAP-3 is marked "[RAISED UPSTREAM — PRD amendment 5]" and argues a tension with "the PRD's own Vision, which promises that '**every state change is attributable to an actor and a moment**'", concluding "the defect is recorded as the fifth entry in the Architecture Spine's *Upstream Amendments Required*, and **the decision belongs to the PM**."

The PM has now decided (A5). The Vision is narrowed — §1 now reads "**Every Leave Request state change is attributable to an actor and a moment.**" FR-16 and NFR-19 were deliberately **not** widened; no holiday-change entity was added; `policy_change.actor` was **not** added.

Consequences for the ERD:
- GAP-3's quoted Vision text is now a **misquote** (it quotes the pre-amendment, unqualified Vision). The tension it describes **no longer exists** — the Vision now scopes attribution to Leave-Request state changes exactly as FR-16/NFR-19 deliver.
- The decision it says "belongs to the PM" **has been made**. GAP-3 should be re-marked "[RESOLVED — PRD amendment 5 applied]".
- The ERD schema is **correct by decision, not by omission**: `policy_change` has no actor and there is no holiday-change table *because the PM affirmatively decided against them*. But the ERD's current framing ("It records no actor, **because no requirement asks for one**"; `POLICY_CHANGE` callout "**GAP-3 — no actor. Nothing in any source rule records who changed the policy**") reads as an unresolved omission awaiting a decision. That framing is now stale and should be restated as a ratified decision.
- §6 intro line "one is routed upstream as a PRD amendment" is likewise stale — that amendment is now applied, not merely routed.

So: the ERD **does** correctly reflect that `policy_change` has no actor, and the schema is right — but the *narrative* still presents it as by-omission rather than by-decision.

## 4. `rollover_run` vs amended FR-07 — **CLEAN (agree)**

Amended FR-07: the rollover "records its execution in a **separate append-only rollover log, not among Audit Entries**, because it transitions no Leave Request." The ERD already models exactly this: `ROLLOVER_RUN` is a standalone entity ("records job executions, not domain objects"); the modelling-rule table states "`audit_entry` … holds transitions only. The rollover writes elsewhere"; and §4.3 grants the app role `INSERT`/`SELECT` but **neither `UPDATE` nor `DELETE`** on `rollover_run`, making it append-only. Fully consistent — no change.

## 5. `admin_review_flag` vs amended FR-10 and FR-06 — **CLEAN (agree), no missing column**

Amended FR-10/FR-06 require: refusal **per Employee and Leave Type**; leave that Employee+Leave Type's Requests and Balances unchanged; record the case in a **durable store the Admin can read and resolve**; the rest of the operation proceeds for unaffected Employees; the same store/guard serves both the holiday recalculation (FR-10) and the policy recalculation (FR-06).

The schema supports all of it:
- **Per Employee AND Leave Type** — `employee_id` + `leave_type_id` columns; §2.1 states "`AD-19` refuses per Employee and Leave Type, so the pair is the subject."
- **Durable, readable, resolvable** — it is a table (durable); `raised_at`/`resolved_at` (nullable) carry resolution state; Admin reads via RBAC.
- **One shared store for both triggers** — the `cause` column discriminates "a holiday recalculation, or a policy recalculation," matching FR-10's "same guard … under FR-06."
- **Rest proceeds** — the flag records only the affected (Employee, Leave Type) subject as a row; nothing in the schema blocks other Employees' balances from updating.

**No missing column.** In particular, no `leave_year` column is needed: the amended text makes the refusal unit the (Employee, Leave Type) **pair** ("refused for the affected Employee and Leave Type"), covering later Leave Years without per-year granularity. GAP-4 ("what *resolving* a flag *does* is undefined") still stands — the amended PRD adds the verb "resolve" but does not define its effect (retry vs. acknowledge); `resolved_at` being nullable keeps the schema unaffected. (See finding 10 for a traceability nit: `admin_review_flag` should now also cite `FR-06`.)

## 6. `leave_type.requires_supporting_document` vs amended FR-06 seed consequence — **CLEAN (agree); the seed value IS stated**

Amended FR-06: "At initialization, EL, CL and FL are seeded with *requires-supporting-document* **false** … An Admin may set the attribute true for any Leave Type at any time." The ERD §2.1 states the column is "**Seeded false for EL, CL and FL**" (source `FR-06`, `FR-13`, spine *Seeding*). Value matches; the seed value is explicitly stated. Minor: the annotation "by project decision" is now slightly dated (the seed is now a normative FR-06 consequence, not merely a project decision), but `FR-06` is already cited — no substantive change required.

## 7. `notification.read_at` and mark-read semantics vs amended FR-14 — **CLEAN (agree)**

Amended FR-14: "An addressee can mark a **Notification** read. Marking read is **idempotent**, and **only the addressee** may do it." The ERD supports both:
- **Idempotent mark-read** — `read_at` (nullable) *is* the read-state; a `SET read_at = now() WHERE id = ? AND read_at IS NULL` transition is naturally idempotent (a second call matches no row; unread count `COUNT(*) WHERE read_at IS NULL` is unchanged).
- **Addressee only** — `recipient_employee_id` ("Readable only by its addressee," `FR-14`) is the addressee identity the service scopes the mutation to.

`notification` already traces `FR-14` in §5. Optional nit: the `read_at` attribute-source cell lists `FR-11, AD-16` and could add `FR-14` now that mark-read is an explicit FR-14 consequence — not a contradiction.

## 8. `leave_balance.carried_forward` / `entitlement_basis` vs amended DR-7 — **CLEAN (agree)**

Amended DR-7: "unused Accrued days" **means Available** (`Accrued − Consumed − Reserved`); Carry-Forward is **recomputed whenever the closing Leave Year's balance changes**, may **increase** after the boundary (when a Pending request is later rejected/cancelled), and **no Leave Request transition ever decreases it**.

The ERD's `carried_forward` = "The carried portion of `accrued`. **Derived, never accumulated.**" This matches DR-7's new normative reading precisely — "recomputed from Available, not accumulated" is exactly "derived, never accumulated" (`AD-6` carry-forward recomputation; PRD §11: "the rollover assigns derived values rather than accumulating them"). The `accrued = prorated_entitlement + carried_forward` non-deferrable CHECK moves all three columns together when a recomputation changes the carried portion — consistent with a value that may rise after the boundary. `entitlement_basis` is unaffected by DR-7 (it serves FR-06's RECALCULATE disposition, not carry-forward). No change.

## 9. §7 "Known limitation — Pending-request lifetime" vs amended PRD — **CLEAN (still accurate)**

The ERD §7 (no bound on Pending lifetime; `DR-7a` keeps Reserved days alive across the boundary; `AD-6`/`AD-19` correct for any number of open years; a "performance characteristic, not a correctness defect") is **reinforced**, not broken, by the amendments. Amended DR-7 now states explicitly that a Pending request's Reserved days survive the boundary and that Carry-Forward is recomputed when the closing year's balance changes — the exact interaction §7 relies on. The non-bound remains a project decision (not a PRD "open question"; PRD §11 = "None"), so §7's framing holds. No change.

## 10. §5 Traceability — **STALE (two rows need updating)**

- **`admin_review_flag` → currently `FR-10, AD-19, AD-20`.** Amended FR-06 adds the "mirror consequence" routing **policy-recalculation** refusals to "the durable store the Admin reads and resolves" (the same store), and FR-10 confirms "the same guard governs a recalculation triggered by a **Leave Policy change under `FR-06`**." The `admin_review_flag.cause` column already enumerates "a policy recalculation," so this entity now realizes an `FR-06` consequence. **Add `FR-06`** to the `admin_review_flag` row (and to the §2.1 `cause` source cell, currently `FR-10, AD-19`). Optionally cite `DR-5`, which now names the Leave Policy change trigger.
- **`employee` → currently `FR-01, FR-03, FR-04, FR-17, FR-19, DR-12, D-03, AD-10, AD-14, AD-22`.** The FR coverage is already present, but with B1 the **naming source of record** for `email` and `full_name` is now the **PRD §3 Glossary** ("Email Address", "Full Name"). **Add `PRD §3 Glossary`** to the `employee` row (consistent with how `department_id` already cites "PRD §3 glossary" in §2.1), and update the §2.1 EMPLOYEE `email`/`full_name` source cells from "project decision — see §6 GAP-1/GAP-2" to the Glossary + FR references (see finding 1).

## 11. Anything else — findings folded above

Nothing new beyond the items above. Cross-references worth recording:
- **§6 intro** ("Two were answered by project decision; **one is routed upstream as a PRD amendment**; one remains …") is stale — the routed amendment (GAP-3) is now applied; folded into finding 3.
- **Email Address as Admin-maintained (FR-04) and non-reusable** — ERD §4.2 (`UNIQUE (email)`, "deactivated Employee's row … their email persist indefinitely and the address is never reusable") and GAP-1 both **already** match the amended Glossary ("Maintained by the Admin (FR-04); not editable by the Employee"). CLEAN.
- **DR-5 now names the Leave Policy change trigger** — the ERD's `CHECK (accrued - consumed - reserved >= 0)` enforces the invariant regardless of trigger; consistent, no change (traceability nit captured in finding 10).

---

### Summary table

| # | ERD locus | PRD amendment | Status |
|---|---|---|---|
| 1 | §2.1 EMPLOYEE `email`/`full_name` provenance | B1 | **CONTRADICTION** |
| 2 | §6 GAP-1 / GAP-2 "no source names it, verified by search" | B1 | **CONTRADICTION** |
| 3 | §6 GAP-3 + `POLICY_CHANGE` callout + §6 intro | A5 | **STALE** |
| 4 | `rollover_run` | A2 | CLEAN |
| 5 | `admin_review_flag` schema | A3 | CLEAN (no missing column) |
| 6 | `leave_type.requires_supporting_document` | B2 | CLEAN |
| 7 | `notification.read_at` mark-read | A4 | CLEAN |
| 8 | `leave_balance.carried_forward` | A1 | CLEAN |
| 9 | §7 Pending-request lifetime | A1 | CLEAN |
| 10 | §5 traceability (`admin_review_flag`, `employee`) | A3 / B1 | **STALE** |
| 11 | §6 intro + cross-refs | A5 | folded into #3 |

**Bottom line:** no schema change is warranted; the required edits are all to the ERD's provenance/gap prose (§2.1 notes, §6 GAP-1/2/3, §6 intro) and two §5 traceability rows.
