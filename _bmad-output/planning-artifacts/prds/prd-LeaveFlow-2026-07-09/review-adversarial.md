---
title: "LeaveFlow PRD — Adversarial Review"
status: draft
created: 2026-07-09
reviewer: hostile evaluator
---

# Adversarial Review: LeaveFlow PRD

This document sets its own bar: intellectual honesty, assumptions surfaced, trade-offs named, nothing invented. That is the bar I will hold it to, because holding a document to the standard it advertises is the most damaging way to read it — every place the performance and the substance diverge is a self-inflicted wound. I am not grading whether LeaveFlow is a reasonable trainee project. It is. I am grading whether this PRD is as honest as it keeps telling me it is. It is not, and the gap is instructive.

The single finding that organizes all the others: **the document mistakes disclosure for discharge.** Its operating move, repeated on every page, is to name a weakness, tag it with virtue-language ("stated plainly," "recorded rather than hidden," "declared rather than assumed," "deferred, not deemed unnecessary"), and then proceed exactly as if naming it had resolved it. Confession is scored as if it were correction. That is not honesty. Honesty is a property of what you build on; announcing that you have been honest is a rhetorical act, and it clusters — this is the tell — precisely around the decisions the author is least sure of.

---

## 1. Self-congratulation: performance of rigor substituting for rigor

The prose is soaked in its own integrity. A partial inventory, all verbatim:

- FR-14: "**The trade-off, stated plainly:**" — a document that were stating plainly would simply state the trade-off. Prefixing it with "stated plainly" is not plain speech; it is a label instructing the reader to admire the plainness. You do not narrate your own candor while being candid.
- FR-14 / addendum 1.1: "Email delivery is **deferred, not deemed unnecessary.**" / "Deferred, not deemed unnecessary." (stated twice, once in each document, identically.)
- FR-09: "The rule is **preserved, not deleted**, so that a future reader can see the contradiction and its resolution."
- FR-11 note: "named as a stretch item in §7, **not silently dropped**."
- §7.4: "the narrowing is **declared rather than assumed.**"
- Addendum 1.1 heading: "**Consequence recorded rather than hidden.**"
- §11 preamble: "These are open. **Nothing below is resolved in the next sentence.**"
- SM-7: "**Assumptions are visible, not buried.**"
- SM-C1: "the shortfall is **declared rather than concealed.**"
- §2.2 / addendum 1.5: "surface the exposure where a human decides, **not to quietly build a feature nobody asked for.**"

Every one of these is the same construction: *X, not the-bad-thing-I-could-have-done-instead.* The rhetorical function is defensive — it pre-empts the reviewer's criticism by voicing it first, which converts a substantive weakness into a display of process maturity and invites me to grade the author's self-awareness in place of the decision. It is the argumentative equivalent of a witness who keeps saying "to be honest with you." The more often it appears, the less I believe it, and it appears most densely exactly where the underlying call is weakest (email, analytics, the leave year, the NFRs).

The document even indicts itself. **SM-C3** declares: "Length is not rigor. An artifact that restates the specification back to itself has produced nothing." This appears on line 535 of a ~580-line PRD accompanied by a ~160-line addendum and a running memlog, a corpus that restates the Module 1 BRD's requirements, restates them again in §5 as "Domain Rules," restates the assumptions inline and again in §12, and restates the FL research across a PRD note *and* a full addendum section for a fact it concludes is "display text only." Either SM-C3 is insincere or it is a standard the author set and then walked straight past. Both readings cost the document.

**Verdict on the virtue: unearned.** Not because the decisions are bad — several are fine — but because announcing honesty is not the same act as being honest, and this document cannot stop announcing.

---

## 2. Is the scope cut honest? Two OR-cuts, one sleight of hand

The three narrowings are not equal, and lumping them together under one "seven-day budget" banner is itself the dishonesty.

**FR-14 (email-or-in-app → in-app): genuinely authorized.** The specification says "email **or** in-app notifications." Choosing in-app satisfies the text. This cut is defensible on the words, and I will not pretend otherwise. What is *not* honest is the framing: the PRD presents it as an independent merits judgment while conceding "in industry practice email is table-stakes." It is not a merits judgment. It is the cheaper branch, chosen for cost, wearing a merits costume. Fine — but say *that*.

**FR-15 (CSV-or-PDF → CSV): genuinely authorized.** Same OR, same reasoning. Defensible on the text.

**FR-11 (analytics → cards): NOT authorized, and the document knows it.** Here there is no OR. The specification says "dashboard analytics" — a single term, not a menu. The PRD narrows it to summary cards and then admits, in its own note (line 315): "The specification's phrase 'dashboard analytics' is **broader than what is built here**; this is a deliberate narrowing." That is not reading an OR. That is the author granting themselves a permission the specification did not give, and then labeling the self-grant "a deliberate narrowing" so it reads like an authorized choice rather than a unilateral reduction. The defense offered — "the specification supplied no acceptance criteria for it" — is an argument that the requirement was *underspecified*, not an argument that cards *satisfy* it. Those are different claims, and the document quietly swaps one for the other.

Worse, inspect what the cards actually are. FR-11's Employee dashboard "presents, per Leave Type: Available, Reserved, and Consumed; plus a count of Pending requests." Those are the exact three quantities FR-07 already maintains, plus a count. The "dashboard" is FR-07's balance readout relabeled and moved to another screen. There is no analytics in it — no trend, no aggregation over time, no derived insight. So the honest sentence is: *the specification asked for analytics and this PRD delivers none, having decided the requirement was too vague to be binding.* The pattern across all three cuts — the cheaper branch every time, the same budget cited every time — reveals that the budget is the actual driver and the OR/underspecification arguments are post-hoc cover. Addendum 1.2 even protests that the FR-11 cut rests "**on its merits rather than only on budget**," which is the tell of a decision that was, in fact, only on budget.

Would an evaluator reading the original spec conclude the requirements were met? For FR-14 and FR-15, yes — the OR carries them. For FR-11, a domain-literate evaluator sees "analytics" in the spec and summary cards in the build and concludes analytics were not delivered. The PRD's own note hands that evaluator the ammunition.

---

## 3. The phasing: a soft deletion dressed as a build order

§7 insists the phasing is "a *build order and a depth allocation*, not a set of deletions" and that "every FR in the specification appears." Read the schedule against the clock and this claim collapses.

- Budget: **three days**, Days 3–5. The document itself concedes "Eighteen functional requirements do not fit three days at equal depth."
- **Phase 1** is twelve FRs and contains the entire correctness core: auth, JWT, data-scoped RBAC, employees, departments, profiles, leave-type config, holidays, the three-quantity balance *with proration, carry-forward and lapse*, the four-state lifecycle with atomic reserve/consume/release, and audit entries. This is not a day of work. On an honest estimate it is most or all of three days by itself.
- **Phase 2** adds four more FRs (dashboards, calendar, filtering/pagination, notifications).
- **Phase 3**, scheduled dead last, is FR-13 (document upload — storage outside the web root, type/size validation, retrieval authorization) and FR-15 (CSV export). These are precisely the two items with real infrastructure cost, and they sit at the back of a queue the document admits will not fit.

Scheduling the most-omittable, highest-friction items last in a budget you have stated is over-subscribed is not "depth allocation." It is arranging for them to be the things that do not get built, while preserving the sentence "every FR appears" for the review. The label on §7.3 — "**completes specification coverage**" — is aspirational grammar; nothing about Days 3–5 makes it load-bearing.

And the document has already written the alibi. **SM-8** demands 100% coverage. **SM-C1** pre-authorizes missing it: "when the two compete for the last hours of the implementation budget, correctness wins, and the shortfall is declared rather than concealed." So the plan simultaneously promises full coverage (§7: every FR appears; SM-8: all eighteen delivered) *and* builds in permission to fail full coverage (SM-C1). That is having it both ways. A phasing that names its last phase "in scope" while giving it the squeezed tail of an admittedly-insufficient budget, and separately pre-drafts the excuse for its non-delivery, is a soft deletion with deniability. **Say it plainly, since the document likes that word: Phase 3 is the part most likely not to exist, and the PRD is structured so that its absence can be reported as an honesty rather than a miss.**

---

## 4. Testability: consequences that restate the requirement or cannot be tested

The document's own guardrail (§9): "A requirement that cannot be stated with a testable consequence is a requirement that is not yet understood." Several "consequences" fail this on the document's own terms.

**FR-06, "No branch in the codebase tests a Leave Type by name to decide Carry-Forward or Lapse behavior."** How would you test this? It is a negative existential over source code, not a behavioral consequence. You cannot write a runtime test that observes the *absence* of a name-branch; you can only grep or eyeball the source, which is code inspection, not a test. And it is trivially defeated in the letter while violated in spirit: a `switch (type.id)` or `if type.code == "EL"` passes "no branch tests by *name*" while hard-coding behavior per type exactly as forbidden. The bullet directly above it — "Creating a fourth Leave Type through configuration ... rolled over ... with no code change and no schema migration" — *is* the genuine behavioral test (and it is restated as SM-5). The "no branch" line adds nothing testable; it is design intent costumed as a testable consequence, and a brittle costume at that.

**FR-11, "Every figure on a dashboard is derived from data the viewing role is authorized to read (`FR-03`)."** This is not a consequence of FR-11 at all. It is a restatement of FR-03 with a cross-reference. To "test" it you would test FR-03's scoping. As written it is unfalsifiable in FR-11's own terms — what payload would prove a figure was "derived from authorized data" rather than merely showing an authorized number? The other FR-11 consequences are thin but testable (field presence, a seven-day window, an org-wide count); this one is filler that borrows another requirement's teeth.

**FR-11 generally.** Its unique testable content reduces to "the same numbers from FR-07 and FR-18 also appear on a screen." That is a re-presentation, not a new behavior. The note concedes the hard part (analytics) "supplied no acceptance criteria" — i.e., the original requirement was untestable, and the resolution was to delete the untestable part rather than make it testable. That is the reverse of the §9 guardrail: the requirement was not understood, so the response was to shrink it until the remainder was easy, not to understand it.

**FR-01, "indistinguishable in body, status, and timing class."** "Timing class" is undefined and, as written, untestable — what is a timing *class*, and what test distinguishes one? Constant-time auth against user enumeration is a real property, but it requires a specific mechanism (a dummy-hash comparison on the unknown-user path) that the PRD asserts the *outcome* of without acknowledging exists. An evaluator probing this in technical discussion would ask "how do you test timing indistinguishability?" and the PRD has no answer on the page. A rigorous-sounding claim that is hard to test and easy to get silently wrong.

**FR-13, "validated for file type and size ... a file failing either check is rejected."** No type set and no size threshold are given, so "fails either check" has no defined pass/fail line — untestable until the criteria exist, and the PRD supplies none. The adjacent "cannot be submitted without one" is a straight restatement of the requirement.

The genuinely well-formed ones deserve credit and get it: FR-16's "Audit Entry count equals state-transition count," FR-08's concurrency and day-count boundary cases, FR-05's department-removal refusal, FR-12's server-enforced page cap. The rubric is met where the behavior is simple and observable. It fails exactly where the requirement is a screen (FR-11) or a design ideal (FR-06's no-name-branch) — which is to say, where the author most wanted a testable-sounding sentence and did not have a testable behavior.

---

## 5. The counter-metrics: guarding temptations that are already off the table

A real counter-metric names something *genuinely tempting to optimize* and *not already prevented*, with a trip-wire. Measured against that, the three here are mostly rhetoric.

**SM-C1 (coverage % read in isolation).** This is the closest to real — with eighteen FRs and three days there is authentic pressure to ship shallow-but-complete. But it prescribes no measurement; it merely re-states, for the fourth time, the priority ordering already in §10's preamble, in the §9 guardrail, and in the primary/secondary split ("correctness wins"). And as noted in §3 above, its actual function is to pre-license a coverage miss. A counter-metric that doubles as an alibi for failing the metric it counterbalances is not a guard rail; it is a trap door.

**SM-C2 (dashboard and report richness).** "Charts are the cheapest way to look finished." But the document has *already* scoped charts out entirely — FR-11 is cards, FR-15 is CSV. This counter-metric warns against a temptation the scope has eliminated. It costs nothing to declare because the thing it forbids is not buildable within the plan. Worse, it doubles as retroactive justification for the §2/§3 cuts: "we removed charts, and note that adding charts would have been a counter-metric anyway." Self-serving, and free.

**SM-C3 (volume of documentation).** "Length is not rigor." Declared, as covered in §1, inside one of the longest artifacts the process will produce, which restates itself repeatedly. It guards against a temptation the document has already yielded to. A counter-metric you are actively violating on the page where you declare it is not a discipline; it is a wish.

None of the three names a live temptation with a measurable trip-wire that the plan has not already foreclosed. The temptations that *are* live and unguarded go unnamed — for instance, "test count inflated by assertions that merely restate the requirement" (see §4), or "a green SM-1 that proves arithmetic while the balance is wrong" (see §7). The document counters the temptations it has already beaten and stays silent on the ones it is exposed to.

---

## 6. The unanswered foundation: sixteen rules on an admitted guess

Open Question 1 (is the Leave Year the calendar year?) is flagged as the highest-consequence unknown in the document. A-09's own "if wrong" clause: "**every balance in the system is wrong.**" The PRD says it "must be asked before Day 3 code begins" and its own research (addendum 2.2) puts calendar-year and April–March financial-year as a genuine coin-flip decided by company policy, not statute.

And then the PRD builds on it anyway. DR-6, DR-7, DR-8, the FR-07 balance table, BR-04's one-request-per-year rule, and the entire year-boundary behavior are all specified on top of A-09 — sixteen domain rules resting on a foundation the document rates 50/50. The defense is that it is flagged. But flagging is not mitigating, and here the flagging is itself dishonest in form: **DR-8 states the guess as fact** — "The Leave Year is the calendar year" — a flat declarative sentence, with the uncertainty demoted to a trailing parenthetical ("assumption, not confirmation"). That is the precise inversion of "surfacing." Surfacing an unknown means the unknown governs the prose; asserting it as a rule and appending a hedge means the *certainty* governs the prose and the hedge is a footnote you can point to later. The document does the second thing while claiming the first.

Hold this against the §9 guardrail again: "A requirement that cannot be stated with a testable consequence is a requirement that is not yet understood." By the document's own admission the leave-year boundary is not understood — it is a coin-flip. Yet it is stated, as DR-8, as a settled rule. The standard says: do not specify what you do not understand. The document specifies it and hedges it, which is the compromise the standard exists to forbid.

What its own honesty demanded instead — and I am criticizing form, not resolving the business question — is that DR-8 should not have been written in the declarative. An unconfirmed boundary is not a rule; stating it as one and captioning it "assumption" is the same disclosure-as-discharge move that runs through the whole document. The same critique applies wholesale to §8's NFRs: "All twenty-one are engineer-proposed and none are confirmed," per Open Question 9 "everything downstream that cites an NFR rests on unconfirmed ground" — and then NFR-04, -07, -08 are cited as binding constraints throughout. Name it, then lean your full weight on it. That is the method, and the method is to treat a confession as a foundation.

---

## 7. Quietly gotten wrong, or asserted without support

**7.1 — The flagship metric does not defend the vision's central claim.** The vision's load-bearing sentence, stated twice: "a leave balance that is wrong is worse than a leave balance that is absent, because it will be believed." The metric erected to defend it, **SM-1**, tests that "`Available = Accrued − Consumed − Reserved` and `Available ≥ 0` after every transition." But that is *internal arithmetic consistency*, not correctness. A balance keyed to the wrong Leave Year (the A-09 coin-flip), prorated by an unspecified method (Open Question 3), and carried forward against an unconfirmed cap (Open Question 2) will satisfy SM-1 perfectly and still be wrong — the three inputs are wrong, but the subtraction is flawless. **SM-1 proves the machine subtracts correctly; it does not prove the numbers it subtracts are right.** So the document's proudest metric defends a weaker claim than its vision makes, and the gap is exactly the space occupied by its three biggest open questions. A believed-because-wrong balance — the precise failure the product exists to prevent — passes SM-1 green. This is the most consequential thing the document has quietly gotten wrong.

**7.2 — The "correctness core" contains admitted-undecided behavior.** §7.1 calls Phase 1 "the correctness core," "not defensible without these," and funds it first. But its centerpiece day-count function has undecided behavior by the document's own §11: Open Question 6 (a request of zero Working Days — "undecided," flagged in FR-08) and Open Question 7 (a holiday declared inside an already-Approved range — "an open question, not an adopted simplification"). And SM-2, which celebrates the day-count function, even lists "a range consisting entirely of non-Working Days" as a test case — a case whose *correct answer the document has not decided.* You cannot write a passing test for behavior you have declared undecided. So either SM-2's last case has a secretly-chosen answer (in which case Open Question 6 is not open) or it cannot be tested as claimed. A correctness core with undecided correctness is a contradiction the label papers over.

**7.3 — The single-implementation absolute is already contradicted by the addendum.** DR-2 / NFR-08: "It has exactly one implementation, and every path that touches a Leave Balance calls it. A second implementation ... anywhere in the codebase is a defect." Addendum 3.4 then concedes "the most likely place for [a second implementation] to appear is the frontend, computing a preview of the day count ... The preview must call the same source of truth **or accept that it is an estimate.**" So the PRD states an absolute the addendum immediately relaxes into a permission for a second, estimated computation. One of the two documents is wrong; they cannot both hold. The absolute reads better in the PRD; the concession is where the real design is.

**7.4 — Data-model properties asserted before the data model exists.** §2.2, A-07: "**Nothing in the data model is scoped to an organization.**" §3, A-09 caption and addendum 3.2: the leave-balance table's keying is stated as fact. Yet addendum 3.2 lists these same entities under "**Entities whose shape is still open**." The PRD asserts properties of a schema that Module 4 has not built and that the addendum admits is undecided. Asserting the conclusion of downstream work as an established fact upstream is the invention the document claims to abstain from.

**7.5 — The audit trail is oversold.** Vision: "an audit trail that survives the conversation." What FR-16/NFR-09 actually guarantee: "**No application code path** updates or deletes one" (line 295), "Zero **application code paths** update or delete one" (SM-4). The guarantee is scoped to the application. It says nothing about direct database access, an admin with a console, or a migration. "Survives the conversation" implies survives an adversary; the requirement only survives the app. The vision's rhetoric writes a check the requirement does not cash.

**7.6 — Traceability asserted, not shown, and unverifiable here.** SM-6 promises "every FR ... traces to a decision recorded in the brief, the BRD, or the run memlog." The D-xx, BR-xx, and NFR-xx citations are sprinkled confidently throughout, but they point at Module 1 artifacts not present in this PRD. From this document alone none of them can be verified; the entire traceability edifice — one of the four things the document is proudest of — rests on sources the evaluator may never see, asserted as if shown.

**7.7 — Effort inversely proportional to stated consequence.** FR-06's note and addendum 2.1 spend roughly four paragraphs establishing that FL means "Floater Leave," concluding A-04: "display text only; nothing structural." Open Question 4 agrees: "Cosmetic." Meanwhile Open Question 3 (proration method — "Every mid-year joiner's balance depends on the answer") and Open Question 1 (the leave year — "every balance is wrong") are each disposed of in a paragraph and then *built upon*. The document lavishes certainty-manufacturing prose on the decision it calls inconsequential and moves briskly past the two it calls catastrophic. That is the signature of a document optimizing for the appearance of diligence: the cheap, safe question gets the visible work.

---

## Closing

The engineering instincts underneath this PRD are largely sound — reserve/consume/release, data-scoped authorization, a single day-count function, append-only audit, policy-as-data. If it were quiet about its virtues I would have fewer complaints. But it is not quiet. It narrates its own honesty on nearly every page, and that narration is where it fails its own test, because the narration is doing the work the substance should do. It confesses the leave-year risk and builds sixteen rules on it. It confesses the NFRs are unconfirmed and constrains the whole spec by them. It confesses email and analytics are cut and dresses two budget-driven reductions — one of them unauthorized by the spec — as principled narrowings. It writes a metric that proves the arithmetic and claims it defends correctness. And it declares, on a page it is busy contradicting, that length is not rigor.

The most damning sentence to hand back to it is its own: *a requirement that cannot be stated with a testable consequence is a requirement that is not yet understood.* By that standard the leave-year boundary, the proration method, and "dashboard analytics" are not understood — and the document specifies all three anyway, then points to the footnotes where it said so. Disclosure is not discharge. Naming the bluff is not the same as not bluffing.
