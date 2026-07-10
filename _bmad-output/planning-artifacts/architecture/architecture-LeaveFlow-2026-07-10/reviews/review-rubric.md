---
title: "Architecture-Spine Review Gate — LeaveFlow"
target: ../ARCHITECTURE-SPINE.md
reviewer: rubric-walker (hard marker)
altitude: feature (governs FR-01..FR-20; no parent spine)
project: greenfield
date: 2026-07-10
verdict: PASS WITH FINDINGS
---

# Rubric Review — ARCHITECTURE-SPINE.md (LeaveFlow)

**Overall: PASS WITH FINDINGS.** This is a strong, unusually disciplined spine. Sixteen ADs
fix the real divergence points across all twenty FRs, the schema-level backstops are genuine
(not aspirational), the operational envelope is largely decided, and the named stack is
verified-current (independently re-confirmed below). Two things keep it from a clean pass:
**AD-6's safety proof is unsound as written** (carry-forward is not monotonic; three paths
drive it down), and the spine is **silent on observability/health-checking**. Neither is fatal;
the CHECK-constraint backstop preserves data integrity even where AD-6's proof fails.

Scoring key: PASS / WEAK / FAIL per checklist item.

---

## 1. Fixes the real divergence points for epics/stories, misses none — **PASS**

The sixteen ADs enumerate the divergence points an epic team would otherwise each resolve
differently: layering and dependency direction (AD-1), single day-count authority (AD-2),
transaction + lock-order protocol (AD-3), guarded conditional update / first-committed-wins
(AD-4), schema-level balance invariants (AD-5), carry-forward derivation (AD-6), out-of-process
rollover (AD-7), audit scope (AD-8), append-only enforcement by DB grant (AD-9),
authorization-as-SQL-predicate + 404 (AD-10), leave-type-is-data-vs-status-is-code (AD-11),
date-vs-instant typing (AD-12), cancellation-as-entity (AD-13), client-renders/server-enforces
+ pinned auth libs (AD-14), opaque document storage (AD-15), notification shape (AD-16). The
Consistency Conventions table and the Capability→Architecture Map close the remaining seams
(naming, error envelope, pagination, IDs, quantity typing, indexing, testing split).

The proration formula (DR-9: monthly, remaining-months, round-down) has no dedicated AD, but
AD-1's "any function that computes a leave quantity lives in `domain/`" plus the PRD's precise
DR-9 statement single-source it, so epics cannot diverge on it. Not a miss.

Minor: the *trigger* for materializing a `leave_balance` row (rollover creates next-year rows;
proration creates joiner rows) is implied rather than stated as an invariant. Epic-level detail;
acceptable.

## 2. Every AD's Rule is ENFORCEABLE and prevents its stated "Prevents" — **PASS**

Most rules are mechanically checkable and map cleanly to their Prevents:
- AD-3/AD-4/AD-5/AD-9/AD-12/AD-14/AD-15 are checkable in schema, migrations, grants, or the
  dependency manifest — the strongest tier. AD-9 in particular ("role granted INSERT/SELECT,
  not UPDATE/DELETE") makes NFR-09 hold against code not yet written — exactly what an invariant
  should do.
- AD-4's `UPDATE ... WHERE status = :from`, rowcount 0 ⇒ refuse is textbook-enforceable and
  genuinely *is* FR-09's first-committed-wins.
- AD-10's byte-identical-404 is testable (SM-3) and prevents the enumeration/existence-disclosure
  leak it names.

Two clauses are review-criteria rather than fully mechanical, but neither is load-bearing enough
to sink the item:
- AD-1's "Any function that computes a leave quantity lives in `domain/`" — the import-direction
  half is enforceable by an import-linter; "computes a leave quantity" is a code-review judgment.
- AD-2's "No frontend module references a weekday or a holiday" — grep-able in practice, though
  "knows what a weekend is" is fuzzy at the edges.

Verdict PASS: the enforceable core carries each Prevents.

## 3. Nothing under Deferred could let two units diverge — **PASS (with two notes)**

Walking each bullet:
- *Attribute-level schema/index tuning* → Module 4 ERD owns it. Safe: the invariant columns are
  fixed here; the rest converge on a single downstream owner. **Note:** the spine leans on an
  ERD that does not yet exist — coordination risk is low but non-zero.
- *Per-endpoint schemas* → generated OpenAPI is source of truth; base path, error envelope,
  pagination bound fixed. Safe (naming/date/error conventions prevent field-shape drift). The
  "OpenAPI is the source of truth" is mildly circular at planning time (it is generated *from*
  code), but the fixed conventions cover the gap.
- *React state below page level / styling / component library* → worst case is inconsistent UX,
  not a correctness/invariant divergence. Safe to defer once AD-2/AD-14 hold.
- *Expiry of a long-Pending request* → **this is really an open question, not a clean deferral.**
  It directly feeds AD-6: a still-Pending 2026 request when 2028 is materialized forces
  carry-forward recomputation across two open years. The spine flags it with a revisit trigger,
  which is honest, but it is a live dependency of AD-6 rather than an independently-pushdownable
  detail. Acceptable, tracked.
- *Seed value of `requires_supporting_document`* → a data value, not structure; the column exists.
  Safe. The FR-06/FR-13 phase-gap it references is a PRD-acknowledged behavioral gap, not a
  spine divergence.
- *CI/CD, backup/DR, rate limiting, HA, scaling, i18n, WCAG* → explicitly out of Module 1's NFR
  set; named, not silent. Safe. (Backup being *named* here is what keeps item 7 from failing.)
- *Email/PDF/charts* → PRD non-goals; adding email later is an adapter behind `services/`, not a
  spine change. Safe.
- *Multi-tenancy* → not deferred so much as *decided closed* (no org column anywhere; second org
  = second deployment). This is the one item that could genuinely diverge units, and the spine
  slams it shut. Correct.

## 4. Named technology is verified-current — **PASS**

The memlog documents a dated web-verification pass (2026-07-10, PyPI/npm/release pages). I
independently re-confirmed the three most load-bearing / most-falsifiable claims:
- **SQLAlchemy 2.1 is still beta** (2.1.0b3, 2026-06-27); **2.0.51 is the latest stable** — the
  spine's pin-to-2.0 rationale is correct.
- **TypeScript 7 went GA 2026-07-08** (the Go-native rewrite) — exactly "two days old" relative to
  the run, matching the spine verbatim; pinning 6.0.3 for a 3-day budget is defensible.
- **PostgreSQL 18 ships native `uuidv7()`** — the Identifiers convention is real, not aspirational.

The security-library reasoning is correct from established fact: passlib's last release is 1.7.4
(2020-10) and it breaks against modern bcrypt; python-jose has a stale/CVE history — so AD-14's
choice of `pwdlib`/`PyJWT` is sound. The remaining forward-dated pins (FastAPI 0.139.0, psycopg
3.3.4, React 19.2.7, Vite 8.1.4, TanStack Query 5.101.2, Alembic 1.18.5, pytest 9.1.1) are
internally consistent and documented-as-verified; I did not re-fetch each, but the three spot
checks all landed exactly, which lends the batch credibility. PASS.

## 5. Greenfield: leans on a starter sensibly, or justifies not — **WEAK**

The *decision* is sound and well-reasoned — but it lives in the **memlog, not the spine.** The
memlog records: hand-roll the skeleton on plain SQLAlchemy 2.0 + Pydantic as separate layers;
borrow only the official `fastapi/full-stack-fastapi-template`'s docker-compose and Alembic
wiring as reference; reject adopting it as-is because **SQLModel fuses the Pydantic API schema to
the SQLAlchemy table, which breaks AD-1's functional-core rule** (plus it ships email recovery,
Traefik, Playwright — all excluded). That is exactly the right call and it is load-bearing: it is
*the* reason AD-1 is even achievable.

Yet the spine's Structural Seed shows the source tree and deployment without ever stating the
starter decision. A reader of the spine alone cannot tell whether to scaffold from the template —
and if someone did, SQLModel would silently violate AD-1. A one-line note in Structural Seed
("skeleton hand-rolled; not from full-stack-fastapi-template, whose SQLModel would violate AD-1")
would close this. WEAK: correct decision, under-surfaced where it governs.

## 6. Covers the driving spec's capabilities (FR-01..FR-20) — **PASS**

The `binds` frontmatter and the Capability→Architecture Map both enumerate FR-01 through FR-20,
each mapped to a code location and its governing ADs. Spot-checks are coherent (FR-11 dashboards →
AD-10 + AD-16 for the derived unread count; FR-15 CSV → AD-10; FR-13 upload → AD-10 + AD-15).
Complete, no gaps.

## 7. Every structural dimension is decided/deferred/open — no whole dimension SILENT — **WEAK**

Operational/environmental envelope audit:
- Deployment — **decided** (Docker Compose: proxy/web/api/postgres/documents-volume/scheduler).
- Environments — **decided** (local dev + one deployed).
- Infra/provider — **decided** (self-hosted Compose; minimal but appropriate for one-org scope).
- Migrations — **decided** (Alembic owns schema; `alembic upgrade head`; runs as owner role).
- Seeding — **decided** (seed command inserts EL/CL/FL; one data value deferred to PM).
- Backup/DR — **deferred, and named** (not silent — good).
- Rollover operations — **decided** (AD-7; `rollover_run` append-only log gives it a run record).
- Secrets/config — **decided** (pydantic-settings from env; `.env.example` committed).

**Silent dimension: observability.** There is no mention anywhere of application logging, metrics,
error monitoring, or a **health-check endpoint** — for a deployment that includes a reverse proxy
routing to an `api` service and an out-of-process batch job, "is the api up?" and "did last night's
rollover succeed?" are operational questions with no answer in the spine. The Deferred section
names CI/CD, backup/DR, rate limiting, HA, scaling, i18n, WCAG — but *not* observability or health
checks, so this dimension is neither decided nor explicitly deferred; it is simply absent. It is
outside Module 1's NFR set, so a one-line Deferred bullet ("structured logging, health checks, and
metrics — not required by Module 1's NFRs; no seam reserved") would resolve it exactly as the other
out-of-scope operational items were resolved. As written, it is the one whole dimension left
SILENT. WEAK.

## 8. SEED masquerading as INVARIANT (or vice versa)? — **PASS (minor)**

Most ADs earn their place as genuine invariants that prevent a named divergence and could *not*
simply be read off compliant code (AD-1, AD-5, AD-9, AD-10, AD-11, AD-13, AD-15 are clear).

Two carry column-level seed detail inside an invariant:
- **AD-8** enumerates `audit_entry`'s columns. The *invariants* (one row per transition and nothing
  else; `actor_id` NULL iff SYSTEM; rollover writes a *separate* table) justify the AD; the full
  column list is descriptive seed that also appears in the ERD.
- **AD-16** enumerates the notification's columns. The *invariants* (unread = `COUNT WHERE read_at
  IS NULL`, never stored; written in the causing transaction so it exists iff the transition
  committed; idempotent PATCH by addressee only) justify it; the column roster is seed.

Neither is a masquerade — each has a real invariant core — but both fold Structural-Seed/ERD detail
into an INVARIANT block, which ties into the terseness finding (item 10). No inversion the other
way (the CHECK constraints are correctly invariants in AD-5, not buried in the ERD). PASS, minor.

## 9. Mermaid diagram validity (all 5 blocks) — **PASS**

Each block checked for render-blocking syntax:
1. **`graph TD`** (layering) — quoted node labels with `<br>` and `·`, thick `==>` edges, and
   dotted labelled `A -. forbidden .-> R` links. All valid. **Renders.**
2. **`graph LR`** (deployment) — cylinder `DB[("postgres:18")]`, subroutine
   `VOL[["..."]]`, labelled `-->|"..."|` edges, and `subgraph deployment["..."]`. The
   bracketed-quoted subgraph title (with an `=` inside the quotes) is valid in current Mermaid
   (v10+). All node shapes valid. **Renders.**
3. **`erDiagram`** — relationship lines with labels, self-relationship
   `EMPLOYEE ||--o{ EMPLOYEE : manages` (valid), attribute blocks with free-form types
   (`int`/`date`/`text`/`uuid`). **Renders.**
4. **`stateDiagram-v2`** (Leave Request) — `[*]` start/end, `-->` with `: label` (commas in labels
   fine). **Renders.**
5. **`stateDiagram-v2`** (Cancellation Request) — same constructs. **Renders.**

No syntax errors found in any block. The only mild version-sensitivity is the bracketed-quoted
`subgraph` title in block 2; given the 2026 tooling target it renders. PASS.

## 10. Terse enough? Rationale that belongs in the memlog — **WEAK**

The spine carries more rationale than a maximally-terse spine should; every instance below is
already in `.memlog.md`, so it is duplication of justification into the governing document:
- **Design Paradigm, 2nd paragraph** ("The paradigm is chosen to make DR-2 structural rather than
  aspirational… can only be expressed in a package that has no way to reach a database…") — pure
  rationale.
- **AD-6's Rule** embeds a *proof sketch* ("approval transfers Reserved to Consumed… therefore
  monotonically non-decreasing… idempotent by construction"). This is rationale — and, per the
  stress test below, it is *unsound* rationale, which is worse than merely misplaced.
- **AD-8 and AD-16** each end with meta-commentary that "the PRD is to be amended" — process/rationale
  that belongs in the memlog's open-questions, not in an invariant.
- **AD-8** "`actor_id` is deliberately not a NOT NULL foreign key, because SYSTEM must be
  expressible" — rationale.
- **Stack** section's pin justifications, and the **ERD note** on `entitlement_basis` provenance —
  rationale.

None of this makes the spine unusable, and some readers will value it — but the item asks for
decision-density, and these are rationale carriers. WEAK.

---

## Stress test — AD-6 "carry-forward is derived": is the safety argument SOUND? — **NO**

**Claim under test.** AD-6 asserts: *approval transfers Reserved→Consumed and leaves `available`
unchanged; only release raises it; therefore `available(Y)` is monotonically non-decreasing as
year Y's Pending requests resolve, so carry-forward is only ever topped up and never clawed back*
— and hence no downward recompute can trip a later year's CHECK.

**Result: the argument is UNSOUND.** It is true only for the narrow universe it names ("as year Y's
Pending requests resolve" via approve/reject/cancel). It is FALSE as the general guarantee the
surrounding text claims ("never clawed back"). `available(Y)` can decrease — and therefore
`carried_forward(Y+1)` can decrease — via at least three paths the proof omits:

**Path A — Holiday recalculation (FR-10) that ADDS a working day.** Deleting a Company Holiday
that falls inside a still-Pending (DR-7a permits Pending to persist across the boundary) or a
future-Approved year-Y request *raises* that request's Leave Day count, raising `reserved`
(Pending) or `consumed` (Approved). Both lower `available(Y) = accrued − consumed − reserved`.
The proof only ever considered `reserved` *leaving* via resolution; FR-10 can *increase* it in
place. `available(Y)` goes DOWN. Monotonicity broken.

**Path B — Admin lowers `carry_forward_cap` mid-year (FR-06).** `carried_forward(Y+1) = min(cap,
available(Y))`. Lowering the cap lowers the result directly. Worse: AD-6's stated recompute
*trigger* is "whenever year Y's **balance** changes" — but a cap change is a change to the
`leave_type`, **not** to year Y's balance, so by the literal rule the recompute **does not fire**,
and `carried_forward(Y+1)` silently desyncs from its own defining formula until the next rollover
run. So Path B breaks the guarantee in two ways: if the FR-06 recalc path *does* propagate, the
value goes DOWN; if it does not, the stored value violates the AD-6 identity
`carried_forward = min(cap, available(Y))` and nothing detects it (AD-5's CHECK only enforces
`accrued = prorated + carried_forward`, not the min-with-cap identity).

**Path C — Admin lowers `Annual Entitlement` with recalculation (FR-06).** Recalculating an
existing balance under a lower entitlement lowers `prorated_entitlement`, hence `accrued(Y)`,
hence `available(Y)`. DOWN again.

**Path D — Cancellation after the boundary (FR-09/BR-05): actually SAFE.** Cancelling an Approved
year-Y request *releases* Consumed days, *raising* `available(Y)` — the safe direction, and it
only tops carry-forward up. Moreover AD-13/FR-09 refuse cancellation of leave "whose dates have
passed," and a year-Y request evaluated in year Y+1 is past-dated, so this path is largely
foreclosed anyway. This is the one vector in the prompt that does **not** break the guarantee.

**Does it actually corrupt data / violate a later year's CHECK?** No — because AD-5 saves it, not
because AD-6's proof holds. When a downward recompute of `carried_forward(Y+1)` lowers
`accrued(Y+1)` below `consumed(Y+1) + reserved(Y+1)` (i.e. year Y+1 already spent the
carried-forward days), the `CHECK (accrued − consumed − reserved >= 0)` fires and **aborts the
transaction.** FR-10 already codifies this as a *refusal* for the holiday path; FR-06 does not
explicitly state the refusal behavior for the entitlement/cap path, so there it manifests as a raw
CHECK abort. Either way, integrity is preserved.

**Net finding.** The *mechanism* (derive, assign-not-increment, propagate, backstopped by the CHECK)
is fine and data stays consistent. But:
1. AD-6's headline safety argument — monotonicity ⇒ never-clawed-back ⇒ no later-year CHECK risk —
   is **false**. Carry-forward *can* go down.
2. The real safety net is AD-5's CHECK constraint, which means a holiday edit or a policy change in
   year Y can be **refused because of a *different* year's (Y+1) consumption** — a cross-year
   coupling the spine's "never clawed back" language explicitly denies and never surfaces to the
   epic teams who will implement FR-06 and FR-10.
3. The cap-change trigger gap (Path B) is a latent inconsistency: `carried_forward` can sit out of
   sync with `min(cap, available(Y))` between rollover runs.

**Recommended fix (for the architect, not applied here):** restate AD-6's justification as
"downward recompute is *possible* under holiday recalculation and mid-year policy change; the
`CHECK` backstop refuses any recompute that would drive a materialized later year negative"
— and either (a) broaden the recompute trigger to include `leave_type` cap/entitlement changes, or
(b) explicitly route all such changes through FR-06's recalc-or-leave choice with the same
refuse-on-negative semantics FR-10 already has. Drop the "monotonically non-decreasing /
never clawed back" claim; it is the unsound part.

Verdict on the AD itself: **WEAK** — sound machinery, unsound stated proof, one latent
trigger gap.

---

## Findings, most-severe-first

1. **AD-6 — safety proof is unsound.** "`available(Y)` is monotonically non-decreasing… never
   clawed back" is false: FR-10 holiday-deletion and FR-06 cap/entitlement reductions all drive
   carry-forward DOWN. Data integrity survives only via AD-5's CHECK (which converts the situation
   into a cross-year *refusal* the spine denies can occur); the cap-change recompute trigger also
   has a staleness gap. *Mechanism WEAK, stated proof FAIL.*
2. **Item 7 — observability is the one SILENT dimension.** No logging, metrics, health-check, or
   error-monitoring anywhere, and it is not even listed under Deferred. One Deferred bullet fixes it.
3. **Item 5 / AD-1 — the starter decision lives only in the memlog.** The load-bearing choice to
   hand-roll (not adopt full-stack-fastapi-template, whose SQLModel would violate AD-1) never
   appears in the spine's Structural Seed, where a scaffolder would look.
4. **Item 10 — rationale carried in the spine.** Design-Paradigm ¶2, AD-6's proof sketch, and the
   AD-8/AD-16 "PRD is to be amended" meta-notes are justification that belongs in the memlog.
5. **Item 3 (note) — "expiry of a long-Pending request" is an open question, not a clean deferral.**
   It is a live input to AD-6's cross-year propagation; correctly flagged but mis-filed as Deferred.

## Passing outright
Items 1, 2, 4, 6, 9 — PASS. Divergence coverage, enforceability, FR coverage, and all five Mermaid
diagrams (verified render-valid) are solid; the stack is verified-current (three claims
independently re-confirmed against live sources on 2026-07-10).
