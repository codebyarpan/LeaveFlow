---
title: "Data-Integrity & Concurrency Review — LeaveFlow Architecture Spine"
lens: data-integrity / concurrency
target: ../ARCHITECTURE-SPINE.md
reviewer: database-engineering lens (adversarial)
date: 2026-07-10
verdict: REVISE — one critical carry-forward/CHECK-abort defect and four high-severity under-specifications before this spine is safe to build from
---

# Data-Integrity & Concurrency Review — ARCHITECTURE-SPINE.md

**Scope.** This review interrogates the balance-mutation protocol (AD-3), the schema
invariants (AD-5), carry-forward derivation (AD-6), rollover (AD-7), audit (AD-8/AD-9),
and the identifier / type conventions, against the product's central claim: *a leave
balance that is wrong is worse than one that is absent, because it will be believed.*
The bar is therefore correctness under concurrency and under the recalculation paths the
PRD admits (FR-06, FR-08, FR-09, FR-10), not merely under the happy path.

**One-line verdict.** The single-command mutation protocol is sound in outline, but
AD-6's monotonicity claim is false and produces a *balance-corrupting or transaction-
aborting* interaction with FR-10 and FR-06; four further paths (isolation level,
holiday-recalc lock order, the CHECK-as-refusal path, and the rollover's unlocked source
year) are under-specified enough that a correct implementation is not guaranteed by the
spine as written.

---

## Severity summary

| # | Finding | Severity | Interrogation point |
|---|---------|----------|---------------------|
| F1 | AD-6 monotonicity is false; FR-10 holiday-delete and FR-06 recalc claw back `carried_forward(Y+1)`, driving a downstream year's CHECK to abort (or silently lowering a believed balance) | **Critical** | 4 |
| F2 | Isolation level never pinned; the admission check that reads `available` is not stated to be evaluated from the FOR-UPDATE-locked row → SM-1 not guaranteed | **High** | 2 |
| F3 | Lock order is a partial order (request-row order unspecified); holiday recalc must read requests to find balances, forcing either a TOCTOU or a lock-inversion deadlock with approval | **High** | 1 |
| F4 | The `>= 0` CHECK is used as the overspend gate; it fires as an IntegrityError (500), not the well-formed `INSUFFICIENT_BALANCE` refusal FR-08/NFR-17 require | **High** | 3 |
| F5 | Rollover reads `available(Y)` but AD-3 only mandates FOR UPDATE on the row it *writes* (`Y+1`); the source year Y is unlocked → concurrent year-Y resolution races the read | **High** | 6 |
| F6 | `accrued = prorated_entitlement + carried_forward` CHECK is non-deferrable; any write to one addend must write `accrued` in the *same statement* — not stated | **Medium** | 5 |
| F7 | AD-8 never says the audit INSERT is inside the transition's transaction (AD-16 says it for notifications); `actor_id` should be a *nullable FK*, not "no FK" | **Medium** | 7 |
| F8 | `prorated_entitlement` is misleadingly named for the full-year (non-joiner) case | **Low** | 5 |
| F9 | UUIDv7 is acceptable; note the timing side-channel and the ORDER-BY requirement for the lock protocol | **Low** | 8 |

---

## F1 — AD-6's monotonicity claim is false, and the failure aborts an unrelated year *(Critical)*

**Point 4.** AD-6 asserts: "Approval transfers Reserved to Consumed and leaves `available`
unchanged; only release raises it. `available(Y)` is therefore monotonically non-decreasing
as year Y's Pending requests resolve, so carry-forward is only ever topped up and never
clawed back."

This reasons only about *transition* of a request through its lifecycle. It ignores the two
recalculation paths the PRD explicitly admits, both of which change balance quantities
**without a lifecycle transition**:

### (a) FR-10 holiday deletion raises `reserved(Y)` after the boundary → available(Y) goes DOWN

FR-10 (§4.3): "Adding or **deleting** a Company Holiday inside the date range of a **Pending**
Leave Request recalculates that request's Leave Day count and its Reserved days." Deleting a
holiday turns an excluded date back into a Working Day, so the day count *increases*, so
`reserved` *increases*, so `available` *decreases*. AD-6's "only release raises it" is not the
whole story: recalculation can lower it.

**Concrete trace (integers throughout, EL, `carry_forward_cap = 5`):**

Year 2026, employee E, EL balance at 31-Dec close:
- `accrued=12`, `consumed=10`, `reserved=1`, so `available(2026) = 12 − 10 − 1 = 1`.
- The `reserved=1` is a still-Pending 2026 request R over **30–31 Dec 2026**, where 31 Dec is a
  Company Holiday → count = 1 (only 30 Dec).

Rollover runs 1 Jan 2027 and writes, by assignment:
- `carried_forward(2027) = min(5, available(2026)) = min(5, 1) = 1`
- `prorated_entitlement(2027) = 12` (full-year employee)
- `accrued(2027) = 12 + 1 = 13` (CHECK `accrued = prorated + carried` holds).

E then spends 2027: `consumed(2027) + reserved(2027) = 13`, so `available(2027) = 0`.

Now, in **Feb 2027**, the Admin **deletes the 31-Dec-2026 holiday** (it was entered by mistake).
FR-10 recalculates the still-Pending R: 31 Dec is now a Working Day → count = 2 →
`reserved(2026): 1 → 2` → `available(2026) = 12 − 10 − 2 = 0`.

AD-6 requires: "recomputed whenever year Y's balance changes, **propagating forward through
every materialized later year**." So the same transaction must recompute:
- `carried_forward(2027) = min(5, available(2026)=0) = 0`
- `accrued(2027) = 12 + 0 = 12`

But 2027 already has `consumed + reserved = 13`. The row-level CHECK
`accrued − consumed − reserved >= 0` evaluates `12 − 13 = −1 < 0`.

**The Admin's holiday-deletion transaction ABORTS with an IntegrityError (SQLSTATE 23514).**

Note precisely what fails: FR-10 *already* has a refusal guard — "A recalculation never
produces a negative Available balance; where it would, it is refused... flagged for Admin
review." But that guard inspects the **recalculated year (2026)**, whose available went
`1 → 0` — *not negative*. The guard passes. The negativity materializes one year downstream
(2027) through the carry-forward propagation, which FR-10's guard never examines. The Admin
gets a 500, not a clean "refused and flagged."

**And the silent variant is worse.** If 2027 were *not yet* consumed, the propagation would
succeed and silently drop E's `carried_forward(2027)` from 1 to 0 — E's 2027 `available`
falls by 1 with no transition, no notification, no action by E. That is exactly the
"wrong balance that is believed" the product exists to prevent, produced by an Admin editing
a holiday.

### (b) FR-06 mid-year recalculation lowers `accrued(Y)` or `carried_forward(Y+1)` → same abort

FR-06 lets an Admin lower `annual_entitlement` or `carry_forward_cap` and choose "recalculate
existing balances." Lowering the cap: `carried_forward(2027) = min(3, available(2026))` drops;
`accrued(2027)` drops; if 2027 is consumed at the old accrued, CHECK aborts. Lowering
`annual_entitlement` recomputes `prorated_entitlement` and `accrued` down directly; if the
current year is already consumed near the old entitlement, the *current* year's CHECK aborts.
AD-6 does not mention FR-06 as a source of downward movement at all.

### (c) Cross-boundary cancellation — the one case AD-6 survives

A Cancellation Request against a 2026 Approved request, approved after the boundary, releases
`consumed(2026)`, which *raises* `available(2026)` — a top-up, which AD-6 permits. Moreover
AD-13 refuses cancellation of leave "whose dates have passed," and 2026-dated leave viewed in
2027 is past, so this path is largely blocked anyway. So (c) does **not** break the
downward-monotonicity claim — but it does confirm that a *closed, rolled-over* year's
`available` is still mutable and re-triggers propagation, reinforcing that "year Y is finished
at rollover" is untrue.

### Why this matters beyond the abort

AD-6 leans its headline conclusion ("the rollover is idempotent by construction") partly on
monotonicity. In fact **idempotence does not need monotonicity** — writing
`carried_forward = min(cap, available(Y))` *by assignment* is idempotent in either direction.
So the idempotence conclusion survives, but the "never clawed back" claim is simply false, and
the clawback has real teeth: it can abort a legitimate Admin action or silently lower a
believed balance.

### Fix (AD-6 text)

1. **Delete** the sentence "`available(Y)` is therefore monotonically non-decreasing... so
   carry-forward is only ever topped up and never clawed back." Replace with: "`available(Y)`
   can both rise (release) and **fall** (FR-10 holiday deletion raising `reserved`; FR-06
   recalculation lowering `accrued`). Carry-forward is therefore re-derived in both
   directions."
2. **Re-base the idempotence claim** on assignment-not-increment alone: "Because
   `carried_forward` is written by assignment from the live `available(Y)`, re-running the
   rollover writes the same value; idempotence does not depend on monotonicity."
3. **Extend FR-10/FR-06's refusal guard across the propagation chain.** Add to AD-6: "Any
   recomputation that changes `available(Y)` must, in the same transaction, re-derive
   `carried_forward` and `accrued` for every materialized later year and **pre-check** each
   against `accrued − consumed − reserved >= 0`. If any later year would go negative, the
   whole recomputation is **refused** (typed domain error, transaction rolled back, flagged
   for Admin review) — it must never be allowed to surface as a CHECK IntegrityError." This
   makes FR-10's promise ("refused, not aborted") true across years, not only for the directly
   edited year.

---

## F2 — Isolation level is never pinned, and the admission check is not stated to run under the lock *(High)*

**Point 2.** The spine names no isolation level, so it inherits PostgreSQL's default
**READ COMMITTED**. That is *acceptable here* — but only because `SELECT ... FOR UPDATE`
under READ COMMITTED re-reads the latest committed version of the locked row (the EvalPlanQual
re-check) and re-applies the predicate. The safety of SM-1 therefore rests entirely on the
admission decision being computed **from the row after it is locked**, in the same
transaction. The spine does not say this.

### Double-submit trace (SM-1) — works *only* if the check is under the lock

E's EL: `accrued=10, consumed=0, reserved=7` → `available = 3`. Two concurrent submissions,
2 days each:

- **T1** `SELECT ... FOR UPDATE balance(E)` → `reserved=7, available=3`. Check `2 <= 3` ✔.
  `UPDATE reserved = 9`. Commit. (`available` now 1.)
- **T2** `SELECT ... FOR UPDATE balance(E)` → **blocks** on T1's lock. After T1 commits, READ
  COMMITTED re-reads the row: `reserved=9, available=1`. Check `2 <= 1` ✘ → refuse.

Correct — because both decisions read `available` *from the FOR-UPDATE-locked row, after
acquiring the lock*. Now the failure mode the spine leaves open:

### The TOCTOU the spine permits

AD-2's preview endpoint returns "the projected Available balance" — a read **outside any
lock** (correct for preview). AD-3 says only that a command "first acquires that row with
`SELECT ... FOR UPDATE`" before it *writes*. It does **not** say the `available >= days`
*decision* is evaluated from that locked read. An implementer can legitimately: (1) call a
read-only repository getter / reuse the preview's `available`, (2) decide "3 >= 2, admit",
(3) then `SELECT ... FOR UPDATE` and `UPDATE reserved`. Under that shape both T1 and T2 read
`available=3` before either locks, both admit, `reserved` becomes 11, `available = −1`. Now
only the AD-5 CHECK stops the negative — and it stops it by *aborting* one transaction with a
500 (see F4), not by a clean refusal. SM-1's "cannot both succeed" holds arithmetically but
the second failure is a 500, and the "double-counted" clause is only saved by the schema, not
by the protocol the spine describes.

The same applies to the **managerless auto-approve** path (submit → Approved, consume
immediately): the `available` check "still applies" (FR-08) and must be evaluated under the
FOR-UPDATE lock on the balance row before `UPDATE consumed`.

### Fix (AD-3 text + a new convention line)

1. Add to AD-3: "The refusal decision itself — every read of `available` used to admit or
   refuse a command that mutates a balance — is computed from the balance row **after** it is
   locked with `SELECT ... FOR UPDATE`, within the same transaction. `available` read outside
   a lock (the preview endpoint, dashboards) is advisory only and is never the basis of a
   write decision."
2. Pin the isolation level explicitly in the Consistency Conventions: "Transactions run at
   **READ COMMITTED** (PostgreSQL default). This is sufficient *because* every balance
   decision is serialized through `SELECT ... FOR UPDATE` on the balance row and re-evaluated
   after the lock is granted; no correctness claim depends on a repeatable snapshot across
   statements." (If any multi-row read-modify-write is later found that is *not* funnelled
   through a single locked row — e.g. the FR-04 deactivation guard reading Pending requests
   then deactivating — that path needs either its own lock or `REPEATABLE READ`; flag it.)

---

## F3 — The lock order is a partial order; holiday recalc breaks it *(High)*

**Point 1.** AD-3 defines only: (a) balances before requests, (b) balances ascending by
`(employee_id, leave_type_id, leave_year)`. It says **nothing about the order among request
rows**. That is a genuine gap, and it interacts badly with the one path that must lock many
request rows.

### The four paths, checked

- **Submission** — locks 1 balance (FOR UPDATE), inserts 1 request. Order fine.
- **Approval** — must lock balance before request (AD-3). To know *which* balance, it must
  first read the request (plain SELECT, no lock) for `(employee, type, year)`, then
  `FOR UPDATE` the balance, then the guarded `UPDATE` on the request. Order preserved. Fine.
- **Rollover** — balances only, ascending. Fine (but see F5 for the *source*-year gap).
- **Holiday recalculation (FR-10)** — the problem child. It must **read requests first** to
  discover which balances are affected (it has a holiday date, not an employee). Then it must
  update both request rows (day count) and balance rows (reserved/consumed).

### Deadlock 1 — request-row order is unspecified

Any command locking ≥ 2 request rows can deadlock with another such command, because AD-3
imposes no order on request rows. Two concurrent holiday edits (Admin A adds a holiday, Admin
B deletes another; nothing in the spine serializes FR-10) over an overlapping request set,
one locking requests in date order and the other in id order, deadlock classically. AD-3's
"prevents deadlock between submission, decision, holiday recalculation, and the rollover job"
is therefore **not proven** for holiday-recalc-vs-holiday-recalc.

### Deadlock 2 — the read-then-lock dilemma inverts the lock order

To avoid acting on stale request state, the natural instinct is to `SELECT ... FOR UPDATE` the
affected requests first (freeze them), then lock balances. That locks **requests before
balances** — the exact inverse of AD-3 — and deadlocks against approval:

- **Approval (T1):** `FOR UPDATE balance(E)` (held) → wants guarded `UPDATE request R`.
- **Holiday recalc (T2):** `FOR UPDATE request R` (held) → wants `FOR UPDATE balance(E)`.
- Cycle → PostgreSQL aborts one with `deadlock detected` (SQLSTATE 40P01), surfaced as a 500
  unless a retry loop exists (none is specified).

So AD-3's own "balance before request" rule *forbids* the clean freeze, forcing holiday recalc
back to a plain (unlocked) read of requests — which reintroduces a TOCTOU:

### The TOCTOU that follows from obeying AD-3

Holiday recalc reads (plain SELECT, READ COMMITTED snapshot) the Pending/future-Approved
requests intersecting the holiday. Request R (Pending, E) is in the set. Before holiday recalc
locks `balance(E)`, approval of R commits: `R → Approved`, its days move `reserved → consumed`.
Holiday recalc, still believing R is Pending, computes a **reserved** delta and applies it to
`reserved(E)`.

**Concrete:** holiday *added* inside R's range, R's count `3 → 2`, delta `−1`. E has
`reserved = 0` after R's approval (R's days are now in `consumed`). Holiday recalc does
`reserved = 0 − 1 = −1` → CHECK `reserved >= 0` **aborts** — or, if some other Pending request
left `reserved = 1`, it silently sets `reserved = 0` while `consumed` still carries R's old
count of 3 (should be 2): **`consumed` over-counts by 1, `available` understated by 1, forever.**
A silent wrong balance produced by an Admin adding a holiday.

### Fix (AD-3 text)

1. Add a total order for request rows: "Where several request rows are locked, they are locked
   in ascending `id`." (Any deterministic key; `id` is uuidv7 and monotone-enough — see F9 on
   the ORDER-BY requirement.)
2. Resolve the read-then-lock dilemma explicitly: "A command that must read request rows to
   discover which balances to lock (holiday recalculation) reads them **without a lock**, locks
   the affected balance rows in `(employee_id, leave_type_id, leave_year)` order, and then
   **re-reads each affected request's status under that lock** and branches on the *current*
   status (adjusting `reserved` for Pending, `consumed` for Approved). A request whose status
   changed since the unlocked read is re-evaluated or skipped; it is never adjusted against a
   stale status."
3. State that FR-10 recalculation is **serialized** (single-flight) per organization, or that
   two concurrent recalcs lock requests in the same total order, closing Deadlock 1.

---

## F4 — The `>= 0` CHECK is being used as the overspend gate; it produces a 500, not a refusal *(High)*

**Point 3.** `CHECK (accrued − consumed − reserved >= 0)` fires as a PostgreSQL IntegrityError
(SQLSTATE 23514), which the `api/` handler can only map to a generic 500-class error. It
carries no "days requested" and no "days available." But FR-08 and NFR-17 require the
overspend refusal to **state days requested and days available** — the spine's own error
convention names `INSUFFICIENT_BALANCE` as carrying exactly those two numbers in `details`.
Those numbers can only come from a **domain pre-check inside the lock**, never from the CHECK.

AD-5 gestures at this ("Application code is never the only thing standing between the system
and a negative balance") — i.e. the CHECK is a *backstop*. But "backstop" is **implied, not
stated**, and the spine never says the service *must* pre-check and raise the typed
`INSUFFICIENT_BALANCE` before the UPDATE can trip the CHECK. An implementer who reads AD-5 as
"the CHECK enforces non-negativity" can legitimately rely on catching the IntegrityError — at
which point:

- the user gets a 500, violating NFR-17;
- worse, in PostgreSQL a constraint violation **aborts the whole transaction** — you cannot
  catch it and continue in the same transaction to craft a nice error; you must roll back and
  you have already lost the `available` value you would need to report.

**Concrete:** E has `available = 1`, submits 3 days. Correct behavior: pre-check `3 > 1` under
the lock → raise `INSUFFICIENT_BALANCE(requested=3, available=1)` → HTTP 4xx with both numbers.
CHECK-reliant behavior: `UPDATE reserved += 3` → `1 − 3 = −2` → 23514 → transaction aborted →
generic 500, no numbers. Same divergence for the managerless auto-approve consume path.

### Fix (AD-5 text)

Add: "The `accrued − consumed − reserved >= 0` CHECK is a **backstop against a service bug,
not the overspend gate**. Every command that would reduce `available` first performs a domain
pre-check against the FOR-UPDATE-locked row and, on failure, raises the typed
`INSUFFICIENT_BALANCE(requested, available)` refusal (NFR-17) *before* issuing the UPDATE. A
CHECK IntegrityError reaching the error handler is a bug to be fixed, never a user-facing
refusal path." (This is the balance-mutation analogue of AD-4's guarded-UPDATE-vs-read-then-
write discipline, and should be stated with the same force.)

---

## F5 — Rollover reads `available(Y)` but AD-3 only locks the row it *writes* *(High)*

**Point 6.** Rollover computes `carried_forward(Y+1) = min(cap, available(Y))` — it **reads**
year Y and **writes** year Y+1. AD-3's rule is that a command "that writes any `leave_balance`
quantity first acquires **that row**" — i.e. the row it writes (`Y+1`). By the letter of AD-3,
the **source** year-Y row is only *read*, so it is not required to be locked. That is a race.

**Concrete:** 1 Jan 2027, rollover processes E's EL. It reads `available(2026) = 1` (one
Pending 2026 request R still reserving 1 day; `accrued=12, consumed=10, reserved=1`). Before
rollover commits `carried_forward(2027)`, R is **rejected** in a concurrent transaction:
`reserved: 1 → 0`, `available(2026): 1 → 2`. Rollover, holding a stale read, writes
`carried_forward(2027) = min(5, 1) = 1`. The correct derived value is now
`min(5, 2) = 2`. The rollover's output no longer equals the value its own rule would produce
from the *live* year-Y balance — the "idempotent by construction" claim holds only per-snapshot,
not against the concurrent state.

The fix is cheap and already compatible with AD-3's ascending order: for a given
`(employee, type)`, years Y and Y+1 are **consecutive** in `(employee_id, leave_type_id,
leave_year)` order, so locking both is in-order and deadlock-free.

Also note the tail this exposes: because of DR-7a (a Pending year-Y request keeps its
`reserved` across the boundary) and AD-6's propagation rule, **every** post-boundary
resolution of a year-Y Pending request (reject/cancel/approve) must now also lock and re-derive
`accrued(Y+1)`, `accrued(Y+2)`… A "simple rejection" becomes a multi-year balance write that
can itself trip F1's downstream CHECK. The spine does not flag that a lifecycle transition on
year Y can cascade writes into later years.

### Fix (AD-3 / AD-6 text)

1. AD-3: "A rollover or recomputation that reads year Y to derive year Y+1 acquires **both**
   the source (Y) and target (Y+1) rows with `SELECT ... FOR UPDATE`, in ascending
   `(employee_id, leave_type_id, leave_year)` order, so the read of `available(Y)` and the
   write of `Y+1` are atomic against a concurrent year-Y transition."
2. AD-6: state that a post-boundary transition on a year-Y balance re-derives and locks every
   materialized later year (and is subject to F1's refusal-on-downstream-negative rule).

---

## F6 — `accrued = prorated_entitlement + carried_forward` is a non-deferrable CHECK; the write must be one statement *(Medium)*

**Point 5.** PostgreSQL CHECK constraints are **not deferrable** — each is evaluated per row at
the end of *each statement*. Therefore a rollover (or FR-06 recalc) that sets
`carried_forward` in one `UPDATE` and `accrued` in a **later** `UPDATE` within the same
transaction violates `CHECK (accrued = prorated_entitlement + carried_forward)` at the first
statement's boundary and aborts. AD-6 says `carried_forward` is "written by assignment" but
never says `accrued` (and `prorated_entitlement`, when FR-06 changes it) must move in the
**same statement**.

**Concrete:** rollover does `UPDATE leave_balance SET carried_forward = 2 WHERE ...` for a row
where `accrued = 12, prorated_entitlement = 12, carried_forward = 0`. End of statement:
`12 = 12 + 2`? No → 23514 abort, before the intended second statement `SET accrued = 14` ever
runs.

### Fix (AD-5 or AD-6 text)

Add: "Because the `accrued = prorated_entitlement + carried_forward` CHECK is non-deferrable,
any write to `carried_forward` or `prorated_entitlement` sets `accrued` in the **same UPDATE
statement**, so the row satisfies the identity at every statement boundary. FR-06
recalculation writes `entitlement_basis`, `prorated_entitlement`, and `accrued` together in one
statement likewise."

---

## F7 — Audit: same-transaction insert is unstated; `actor_id` should be a nullable FK *(Medium)*

**Point 7.** Two distinct issues.

**(a) The audit INSERT is not stated to be inside the transition's transaction.** AD-16 is
explicit for notifications ("written inside the same transaction as the transition, so one
exists if and only if that transition committed"). AD-8 makes no equivalent statement for
`audit_entry`. SM-4's one-to-one count (audit rows == transitions) is only true if the audit
INSERT commits atomically with the transition: if it were a separate transaction, a rolled-back
transition (e.g. AD-4's guarded UPDATE affecting zero rows, or F1/F4's downstream abort) could
leave a committed audit row for a transition that never happened, or a committed transition
with no audit row. The polymorphic design (no FK on `subject_id`) makes this *worse*, because
there is no referential constraint to catch an orphan audit row pointing at a subject whose
transition rolled back.

**(b) `actor_id` "not a foreign key" conflates two things.** AD-8 says `actor_id` "is
deliberately not a `NOT NULL` foreign key, because SYSTEM must be expressible." But a
**nullable FK** expresses SYSTEM perfectly (NULL = SYSTEM) *and* enforces that a non-NULL
`actor_id` references a real employee. Dropping the FK entirely buys nothing and permits an
audit row attributed to a nonexistent actor. The `actor_type`/`actor_id` relationship
(`actor_id IS NULL ⇔ actor_type = 'SYSTEM'`) is already a legitimate CHECK and should be
named as one.

### Fix (AD-8 text)

1. Add: "The `audit_entry` INSERT executes inside the same transaction as the transition it
   records, so SM-4's one-to-one count holds under rollback — an audit row exists **iff** its
   transition committed." (Mirror AD-16's wording.)
2. Change: "`actor_id` is a **nullable foreign key to `employee`**, NULL iff `actor_type =
   'SYSTEM'` — a CHECK enforces the equivalence. Nullable, not absent: SYSTEM is expressible
   *and* a non-NULL actor is guaranteed to reference a real employee."
3. Note that `subject_id` referential integrity rests on (a) same-transaction insert and (b)
   subjects being never physically deleted (FR-04 deactivation, requests never deleted); a
   `subject_type` CHECK restricting values to the known subject tables is cheap insurance.

---

## F8 — `prorated_entitlement` is misleadingly named *(Low)*

**Point 5, second half.** For a full-year (non-joiner) employee, proration does not apply, so
`prorated_entitlement = annual_entitlement`. The column name implies the value is *always* a
reduced figure, when in the common case it is the full entitlement. It is semantically "the
entitlement portion of `accrued`, after proration where applicable," and it coexists with
`entitlement_basis` (the annual figure the row accrued under). This is defensible but invites a
reader to assume the column exists only for joiners.

### Fix (Structural Seed note)

Rename to `entitlement_portion` (or `accrued_entitlement`), or add one line to the
`leave_balance` note: "`prorated_entitlement` holds the entitlement component of `accrued`; for
a full-year employee it equals `entitlement_basis` (no reduction), for a mid-year joiner it is
the FR-07 prorated figure." Confirm it equals the *pre-carry-forward* entitlement so the CHECK
identity `accrued = prorated_entitlement + carried_forward` is exact.

---

## F9 — UUIDv7 is acceptable; two caveats *(Low)*

**Point 8.** UUIDv7 primary keys are fine here.

- **Timing side-channel:** v7 embeds a millisecond Unix timestamp, so an ID leaks its row's
  creation instant. This is immaterial — authorized readers already see `created_at` /
  `occurred_at`, and no unauthorized reader obtains an ID (AD-10 returns 404 for out-of-scope
  resources). Worth one sentence stating the acceptance.
- **Enumeration resistance for AD-10:** v7 has ~74 random bits (vs v4's 122). Still
  computationally infeasible to guess, so AD-10's "404 is byte-identical to nonexistent" claim
  holds. Note it, don't change it.
- **DEFAULT interaction — the real one:** using `uuidv7()` as a column DEFAULT is fine, but the
  lock protocol's "ascending `(employee_id, leave_type_id, leave_year)`" and F3's "ascending
  `id`" orders must be realized with an explicit `ORDER BY ... FOR UPDATE` (PostgreSQL applies
  the locking clause after the sort, acquiring locks in sorted order) **or** by explicitly
  locking rows one at a time in the sorted order in the service. A `FOR UPDATE` over an
  *unordered* result set (e.g. iterating a Python result and locking per-row) does **not**
  honor the intended order and reopens the deadlock F3 is meant to close. This belongs in the
  AD-3 fix.

### Fix

Add to the Identifiers convention: "Multi-row `FOR UPDATE` acquires locks via an explicit
`ORDER BY` on the lock-order key (PostgreSQL locks post-sort); per-row locking without that
`ORDER BY` is forbidden." One sentence acknowledging the v7 timing leak as accepted.

---

## Closing assessment

The spine's *single-command, single-employee* mutation protocol (AD-3 + AD-4 + AD-5) is
fundamentally sound: one transaction, `FOR UPDATE` the balance, guarded conditional UPDATE for
transitions, schema CHECKs as backstop. Under READ COMMITTED that correctly serializes the
double-submit **provided** F2 and F4 are made explicit.

Where the design is not yet safe is the **multi-year and multi-row** surface the PRD forces on
it: carry-forward propagation (AD-6) against FR-10/FR-06 recalculation is the critical defect
(F1) — it can abort an Admin action on an unrelated year or silently lower a believed balance,
which is the precise failure the product exists to prevent. Holiday recalculation (F3) and the
rollover's source-year read (F5) are the two paths where AD-3's lock order is incomplete or
mis-scoped. F4 and F2 are about making the difference between "a CHECK caught it" and "the
service refused it cleanly" explicit — the difference between a 500 and NFR-17.

None of these requires a paradigm change; all are text changes to AD-3, AD-5, AD-6, and AD-8.
But F1 in particular is a design hole, not a wording nit: the propagation rule and the
refusal-on-negative guard were written for different years and do not compose.
