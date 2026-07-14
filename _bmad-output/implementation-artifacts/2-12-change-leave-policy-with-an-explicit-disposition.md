---
baseline_commit: 83096b2037766b176e2db0cad9d9bfaf1facd5c2
---

<!--
  Story 2.12 — the LAST story of Epic 2.
  Built from: epics.md §Story 2.12 (L1339-1399), ARCHITECTURE-SPINE.md (AD-5, AD-6, AD-8, AD-9,
  AD-11, AD-17, AD-19, AD-20, AD-21), api-contracts.md §4.3 + §Error codes (L85), erd.md
  §POLICY_CHANGE (L147-155, L293-302), and the WORKING-TREE state of stories 2.9 / 2.10 / 2.11
  (all three still `review`, all three uncommitted — HEAD is 83096b2 feat(story-2.8)).
-->

# Story 2.12: Change Leave Policy with an Explicit Disposition

Status: review

## Story

As an Admin,
I want to be forced to choose what happens to existing balances when I change policy,
so that the system never silently decides on my behalf.

---

## Orientation: what this story actually is

FR-06's last clause comes due, and Epic 2 closes.

Story 2.1 shipped `POST /leave-types` and `GET /leave-types` and **deliberately shipped no edit
path** — 2-1's Dev Notes say so by name: *"Out of scope for this story (same resource, later):
`PATCH /leave-types/<id>` (requires `RECALCULATE`/`PRESERVE` disposition → `policy_change`) and
`GET /policy-changes`. Do not build them here."* This story is that edit path.

The shape:

- `PATCH /api/v1/leave-types/<id>` is **new** (2.1 shipped no update route, no update repo function,
  no update service command). Because it is new, **this story makes no breaking change** — unlike
  2.11, which had to break `POST`/`DELETE /holidays`. `POST /leave-types` stays `201`. Do not
  "helpfully" harmonize it.
- When the change would affect balances that already exist, the Admin **must** supply a
  `disposition` of `RECALCULATE` or `PRESERVE`. Without it: `400 POLICY_DISPOSITION_REQUIRED`, and
  **nothing is applied** — not the leave-type row, not the `policy_change` row.
- `PRESERVE` writes **no balance row at all**. Existing balances stay as accrued under their
  `entitlement_basis`; future accruals pick up the new value for free (see below).
- `RECALCULATE` re-derives `prorated_entitlement`, `carried_forward` and `accrued` from the new
  `annual_entitlement`, across **every materialized Leave Year**, per (Employee, Leave Type) pair —
  under exactly the AD-19 forward check that governs a holiday change. A pair it would drive
  negative is left **entirely unchanged**, flagged under AD-20, and the rest of the operation
  commits with a `200` summary.
- The `policy_change` row records what changed, from what, to what, under which disposition, and
  when. It carries **no actor column, by decision** (AD-20; PRD §1 promises attribution for Leave
  Request state changes only).

### PRESERVE is a no-op on balances — for `annual_entitlement`, and **only** for it

`run_rollover` re-prorates `Y+1` from `leave_type.annual_entitlement` at every boundary and writes
`entitlement_basis=leave_type.annual_entitlement` (`services/rollover.py:181-193`), and
`create_employee` / `create_leave_type` prorate from the live row. So *"only future accruals use the
new value"* (AC4) is delivered, **for an `annual_entitlement` change**, by updating the `leave_type`
row and stopping. Write no balance, call no recompute, touch nothing else.

**It does not generalize, and Landmine 3 is why.** `entitlement_basis` freezes the annual entitlement
on the row. **Nothing freezes the cap.** A PRESERVE'd `carry_forward_cap` change preserves nothing —
it plants a delayed 500 in someone else's transaction. Read Landmine 3 before you write the PRESERVE
branch.

### The whole story is one asymmetry

A **holiday** change moves `reserved`/`consumed` in **one** Leave Year (`Y = holiday_date.year` —
a request cannot span two Leave Years, DR-6). Everything above `Y` moves only through
`carried_forward`.

A **policy** change moves `prorated_entitlement` in **every materialized year, independently and
all at once**. Nothing about it is confined to one year, and `reserved`/`consumed` do not move at
all.

Almost every landmine below is a consequence of that single sentence. **The code that 2.11 and 2.10
built is correct for them and unsound for you in three specific places.** Read Landmines 1, 2 and 3
before writing a line.

---

## Acceptance Criteria

1. **Given** a database migrated by this story, **when** the schema is inspected, **then**
   `policy_change` exists carrying `leave_type_id`, the `attribute` changed, its `old_value` and
   `new_value`, the `disposition`, and `occurred_at`, with `CHECK (disposition IN
   ('RECALCULATE','PRESERVE'))`; **and** it carries **no actor column, by decision**, and it is not
   `audit_entry` (`AD-20`, `AD-8`).

2. **Given** a Leave Type change that would affect existing Leave Balances, **when** an Admin calls
   `PATCH /api/v1/leave-types/<id>` without a disposition, **then** the response is `400` with
   `POLICY_DISPOSITION_REQUIRED`, **and nothing is applied** (`FR-06`, api-contracts §4.3, L85).

3. **Given** an Admin supplying a disposition of `RECALCULATE` or `PRESERVE`, **when** the change is
   applied, **then** a `policy_change` row records the Leave Type, the attribute, its old and new
   values, the disposition and the moment; **and** it carries no actor column (`AD-20`).

4. **Given** the disposition `PRESERVE`, **when** the change is applied, **then** existing balances
   remain as accrued under `entitlement_basis`, and only future accruals use the new value
   (`FR-06`, `AD-5`).

5. **Given** the disposition `RECALCULATE`, **when** the change is applied, **then** `accrued`,
   `prorated_entitlement` and `carried_forward` are re-derived from `entitlement_basis` in one
   statement, `AD-19`'s forward check runs, and a pair it would drive negative is left unchanged and
   flagged under `AD-20`; **and** the same guard governs it as governs a holiday change (`FR-06`,
   `AD-19`). **The refusal is discovered by the forward check, never by an `AD-5` CHECK violation
   and never by a caught `ValueError`.**

6. **Given** a change to `carry_forward_cap` or `annual_entitlement`, **when** it commits, **then**
   `AD-6`'s carry-forward recomputation is triggered explicitly, because a policy change is not a
   balance change and would otherwise never fire (`AD-6`).

7. **Given** an authenticated Admin, **when** they call `GET /api/v1/policy-changes`, **then** they
   read the recorded changes and their dispositions (api-contracts §4.3).

8. **Given** an authenticated Employee or Manager, **when** they call `GET /api/v1/policy-changes`,
   **then** the response is `403` with code `ACTION_NOT_PERMITTED` (`G3`).

9. **Given** a fourth Leave Type created entirely through configuration, **when** it is applied for,
   reserved against, approved, and rolled over at the Leave Year boundary, **then** every step
   succeeds with no code change and no schema migration (`SM-5`).

10. **Given** the React application and an authenticated Admin editing a Leave Type, **when** the
    change would affect existing Leave Balances, **then** the form **requires** them to choose
    `RECALCULATE` or `PRESERVE` before it will submit, and states in plain language what each does
    to existing balances; **and** without this the Admin can create a Leave Type but never
    successfully edit one, because every edit returns `POLICY_DISPOSITION_REQUIRED` (`FR-06`,
    `NFR-16`, `NFR-17`).

11. **Given** the React application and an authenticated Admin who chose `RECALCULATE`, **when** the
    `200` summary returns, **then** the screen names every Employee-and-Leave-Type pair the forward
    check refused and left unchanged, exactly as a holiday edit does in Story 2.11 (`AD-19`,
    `AD-20`, `NFR-17`).

12. **Given** the React application and an authenticated Admin, **when** they open the Policy Changes
    screen, **then** they see each recorded change, its old and new value, and the disposition
    applied (api-contracts §4.3).

---

## 🚨 Landmines. Read all nine before writing a line.

### Landmine 1 — `project_forward`'s fixed-point break is **UNSOUND** for a policy change. It will ship green and 500 in production.

This is the single most important paragraph in this story.

```python
# backend/app/domain/recalculation.py:153-170 — the loop over years ABOVE Y
for year in years[1:]:
    carried = carry_forward_days(available=available, carries_forward=..., carry_forward_cap=...)

    if carried == year.carried_forward:
        break          # ⬅️ "this year's carry-forward is already correct, so its Available is
                       #     unchanged — and every later year derives from THIS one. Stop."

    available = year.prorated_entitlement + carried - year.consumed - year.reserved
    if available < 0:
        return ForwardProjection(refused=True, refused_year=year.leave_year, ...)
```

That reasoning is **airtight for a holiday change**, where the only thing that can move a later year
is its `carried_forward`. It is **false for you**, because a policy change moves every year's
`prorated_entitlement` *independently*. A year whose `carried_forward` does not move can still go
negative — through its own re-proration.

**The case that will actually happen.** Take a **non-carrying** Leave Type (`carries_forward=false`
— that is `CL` and `FL`, two of the three seeded types). `carry_forward_days` returns `0`
unconditionally, and the stored `carried_forward` is already `0`. So on the **first** iteration
`carried == year.carried_forward` → `0 == 0` → **`break`**. The loop exits before checking a single
later year. Lower `CL`'s `annual_entitlement` from 12 to 2 while an Employee has already *consumed*
8 days of `CL` next year, and:

- `project_forward` reports `refused=False`;
- the service applies;
- `set_accrual`'s `available >= 0` guard fires a **bare `ValueError`** → **raw 500**;
- **AC5 is violated**, and every one of 2.11's tests still passes.

A carrying type gets there too whenever the cap binds (available drops 40 → 35, cap 30, `carried`
stays 30 == stored 30 → `break`).

**The fix — extend `project_forward`, do not clone it.** Add a keyword-only
`new_prorated_by_year: dict[int, int] | None = None`. When it is `None` (the holiday path) behaviour
is byte-identical and 2.11's tests are untouched. When it is supplied (your path):

- year `Y` uses `new_prorated_by_year[Y]` in place of `years[0].prorated_entitlement`;
- each later year uses `new_prorated_by_year[y]` in place of `year.prorated_entitlement`;
- **the fixed-point `break` is skipped entirely** — every materialized year is checked, and every
  year lands in `carried_forward_by_year`.

Do **not** try to be clever and keep the break with a `and new_prorated == year.prorated_entitlement`
guard. Floor-rounded proration (`(annual * remaining_months) // 12`) means a year's prorated figure
can be *unchanged* while a later year's changes — `12→13` leaves a September joiner's first year at
`4` and moves every full year from `12` to `13`. The break becomes a non-transitive signal.
Materialized years are one per Leave Year since joining; walking all of them is free. **Walk them
all.**

### Landmine 2 — `recompute_carry_forward` **cannot** be your writer for later years. It preserves proration and it has the same unsound break.

```python
# backend/app/services/rollover.py:301-316
if carried == target.carried_forward:
    return                                   # ⬅️ same unsound fixed point, on the WRITE side

balances.set_accrual(
    session, ..., leave_year=target_year,
    prorated_entitlement=target.prorated_entitlement,   # ⬅️ PRESERVED — read off the row
    carried_forward=carried,
    entitlement_basis=target.entitlement_basis,         # ⬅️ PRESERVED
)
```

Its own docstring (`rollover.py:251-255`) hands you the job by name:

> *"`prorated_entitlement` and `entitlement_basis` are **PRESERVED**. This re-derives CARRY-FORWARD,
> not proration… Re-prorating here would quietly overwrite a policy figure this story has no
> business touching (**that is FR-06's recalculation, and it belongs to Story 2.12**)."*

So if you lean on `recompute_carry_forward` to propagate the change upward, **every year above `Y`
keeps its old `prorated_entitlement` and its old `entitlement_basis`** — the policy change silently
applies to one year only, and the rest are wrong and will be believed. Do not widen
`recompute_carry_forward`; the other four call sites depend on it preserving proration.

**The shape that works.** Your service writes **every** materialized year itself, ascending, through
`set_accrual`, using the numbers the projection already produced:

```python
# per pair, AFTER project_forward says refused=False:
for y in years:                                     # ascending; years[0] == the LOWEST materialized year
    balances.set_accrual(
        session, employee_id=..., leave_type_id=..., leave_year=y.leave_year,
        prorated_entitlement=new_prorated_by_year[y.leave_year],       # the NEW proration
        carried_forward=(y.carried_forward if y.leave_year == years[0].leave_year
                         else projection.carried_forward_by_year[y.leave_year]),
        entitlement_basis=new_annual_entitlement,                      # the NEW basis
    )

# AC6: AD-6's recomputation, triggered EXPLICITLY. It must be a NO-OP — the projection and the one
# implementation of the propagation agree by construction, and this call is what proves it.
rollover.recompute_carry_forward(
    session, employee_id=..., leave_type_id=..., leave_year=years[0].leave_year,
)
```

Assert the no-op in a test (re-read the rows before and after the call; they must be byte-identical).
That assertion is what makes AC6 a fact rather than a ceremony.

### Landmine 3 — **`PRESERVE` cannot preserve a `carry_forward_cap`.** Nothing freezes the cap, and the 500 lands in someone else's transaction weeks later.

`entitlement_basis` freezes the **annual entitlement** on the balance row — that is the whole reason
the column exists (erd.md L215: *"Without it, FR-06's RECALCULATE disposition has nothing to
recalculate from"*). **There is no `carry_forward_cap_basis`.** The cap is read **live**, from the
`leave_type` row, by every downstream trigger:

```python
# backend/app/services/rollover.py:265, :295-299 — recompute_carry_forward
leave_type = leave_type_repo.get_leave_type(session, leave_type_id)   # ⬅️ LIVE. Always the new cap.
carried = carry_forward_days(
    available=available,
    carries_forward=leave_type.carries_forward,
    carry_forward_cap=leave_type.carry_forward_cap,
)
# ...and `run_rollover` does the same at rollover.py:176-180. NEITHER has a forward check.
```

So if you take the disposition `PRESERVE` on a cap **decrease** and write nothing:

1. Admin lowers `EL`'s `carry_forward_cap` 30 → 5 with `PRESERVE`. Rows keep `carried_forward(Y+1) = 30`.
2. Weeks later, **an unrelated Manager rejects an unrelated year-`Y` request.** That fires
   `recompute_carry_forward` (`leave_requests.py:533`), which re-reads the **new** cap:
   `carried = min(5, available(Y)) = 5 ≠ 30` → `set_accrual` drops `accrued(Y+1)` by 25.
3. `Y+1` is already spent → `set_accrual`'s guard raises a **bare `ValueError`** → **raw 500 on the
   Manager's reject**. The three 2.10 hooks were wired on the premise that `available(Y)` only
   *rises*; an out-of-band cap change destroys that premise, and **none of those three paths has a
   forward check.**
4. The same change aborts the **entire `run_rollover` batch transaction** the next time it runs
   (`rollover.py:185`).

`carries_forward: true → false` is worse: it zeroes `carried_forward` in **every** later year the
next time any trigger fires, from a code path that cannot refuse.

**The resolution (and it makes AC6 literally true).** AC6 has **no disposition qualifier** — *"Given a
change to `carry_forward_cap` or `annual_entitlement`, when it commits, then AD-6's carry-forward
recomputation is triggered explicitly."* Neither does AD-6's rule (SPINE L101). So:

> **A change to `carry_forward_cap` or `carries_forward` runs AD-19's forward check and re-derives
> `carried_forward` under BOTH dispositions.** `PRESERVE` preserves what actually has a basis — the
> proration (`entitlement_basis`) — and nothing else. For a cap-only change, `PRESERVE` and
> `RECALCULATE` therefore do the same thing to balances, and differ only in what the `policy_change`
> row records. That is honest. Silently promising to preserve a number the next reject will
> overwrite, unguarded, is not.

The alternative — refusing `PRESERVE` for a cap change — needs an error code the API contract does
not define. Do not invent one. (Open Decision #1.)

### Landmine 4 — Start the walk at the **LOWEST** materialized year, never `date.today().year`.

`carried_forward(Y)` for the lowest materialized year is `0` — there is no year below it to carry
from — which is what anchors the chain. Start anywhere else and `carried_forward(start)` is a value
derived from the *old* policy in the year below, which you did not re-derive: the chain is built on
a stale number.

`_current_leave_year()` exists in `services/balance_reads.py:53` and `services/leave_requests.py:230`
and is **the wrong function here**. Stories 2.10 and 2.11 both recorded this trap for their own ACs;
you are the third to face it.

`_materialized_years(from_year=...)` walks *upward* from a year you give it and stops at the first
gap — it does not find the bottom. You need a new repository read that returns, for one Leave Type,
every Employee that has a balance row and their **first** materialized year, ordered by
`employee_id` (which is AD-3's lock order). See Task 3.

### Landmine 5 — the refusal must be **predicted**, not **caught**. AC5 says so in as many words.

Verbatim from `domain/recalculation.py:20-27` — all three of these are AC5 violations, *however
green the suite goes*:

```python
try: balances.set_accrual(...)          # ← caught, not predicted
except ValueError: flag(...)

try: session.flush()                    # ← the CHECK found it, not you
except IntegrityError: session.rollback(); flag(...)

with session.begin_nested(): ...        # ← a savepoint rolling back on a DB error is
                                        #   still the DB discovering the refusal
```

AD-19 requires the rest of the policy change to **COMMIT** while the refused pair is left untouched.
A refusal discovered by a database error has already poisoned the transaction. Project the whole
outcome purely, in memory, **before the first write for that pair**. Then `set_accrual` *cannot*
raise, because you already proved it won't.

**Prove the check is non-vacuous**, as 2.11 did: monkeypatch `project_forward` to always answer
"not refused", and assert the refusal scenario then produces an unhandled `ValueError` from
`set_accrual`'s guard. If that test passes without the patch and fails with it, your gate is load-
bearing. If nothing changes, your check is decoration.

### Landmine 6 — Zero `audit_entry` rows. Two suite-wide counters pin this exactly.

```python
# tests/integration/test_audit_entries.py:511
assert len(rows) == 14, "SM-4 is one audit row per state transition, counted one-to-one..."
assert by_type == {SUBJECT_LEAVE_REQUEST: 10, SUBJECT_CANCELLATION_REQUEST: 4}
```

A policy change transitions no Leave Request. There is **no `SUBJECT_POLICY_CHANGE` and no
`SUBJECT_LEAVE_TYPE`, and there must not be one** — echoing `services/rollover.py:34` ("There is no
`SUBJECT_ROLLOVER` and there must not be one") and 2.11's identical rule for holidays.
`policy_change` **is** the log, exactly as `rollover_run` and `admin_review_flag` are. Do not import
`audit_entry_repo` into any module you write; **its absence is the proof.**

### Landmine 7 — No ninth balance method. Do not touch `[tool.importlinter]`.

```python
# tests/test_balances_module_surface.py:48,57
assert _public_callables_defined_here() == set(_EXPECTED_PUBLIC_CALLABLES)   # the eight
assert len(_public_callables_defined_here()) == 8
```

`set_accrual` is all you need; it already computes `accrued` from its two parts and already carries
the `available >= 0` guard on its DO-UPDATE branch — the guard Story 2.10 added *for you*
(`deferred-work.md:43` assigns *"the DO-UPDATE lowering path and its per-pair refusal /
`admin_review` handling"* to this story). **If that guard ever fires, you have an AC5 bug.**
Orchestration goes in `services/`, never in `balances.py`. The seven import-linter contracts are
pinned byte-for-byte by `tests/test_architecture.py`; a new `services/` or `repositories/` module
needs **no** contract change, and touching that block is how you break 7/7.

### Landmine 8 — Four build guards will fail if you forget them. Two of them are new to this story.

| Guard | What you must do |
|---|---|
| `tests/test_scope_matrix.py:73` | **`PATCH /api/v1/leave-types/{leave_type_id}` has a path parameter → it WILL fail the build unless registered** as `frozenset({Scope.ALL})`. Note `GET /policy-changes` has **no** path parameter → it must stay **OUT** of the registry, or the reverse assertion (`test_no_registered_entry_names_a_route_the_app_does_not_expose`) fails. |
| `app/main.py` `CODE_TO_STATUS` | **`POLICY_DISPOSITION_REQUIRED: 400`.** Story 2.11 pointedly did not touch `main.py`; **you must.** It is the only `main.py` change — `CAUSE_POLICY_RECALCULATION` and the two dispositions are enumerated strings, not error codes, and map to no status. |
| `tests/test_scoped_getters.py:68` | `list_policy_changes` matches the `list_`+`session` net → add it to `EXEMPT` **with a rationale**, plus a "why exempt" docstring at the definition site. Ground: scope `all`, Admin role gate applied at the route before any row is read. **Do not rename it to dodge the matcher** — 2.9's review settled this: *a surface claim gets revised with a rationale, never routed around.* |
| `test_migrations_insert_nothing.py:121` · `test_migration_smoke.py:25` · `test_schema_1_2.py:50` | Append `"0011_policy_change.py"` to the hardcoded migration list; bump `HEAD_REVISION` to `"0011_policy_change"`; add `policy_change` to the expected table set. |

### Landmine 9 — `tests/test_vocabulary_literals.py` makes `Literal["RECALCULATE", "PRESERVE"]` **impossible** to write. Do not spend an hour discovering this.

The guard scans `backend/app` and `backend/seed` and flags **any** `ast.Constant` string equal to an
exported `vocabulary.__all__` value — **annotations included**. The only exempt file is
`domain/vocabulary.py` itself. So the moment `DISPOSITION_RECALCULATE = "RECALCULATE"` lands in
`__all__`:

```python
disposition: Literal["RECALCULATE", "PRESERVE"] | None = None   # ❌ fails the build, in api/ OR services/
disposition: Literal[vocabulary.DISPOSITION_RECALCULATE, ...]    # ❌ invalid typing (PEP 586 needs values)
```

**The way through — and it is the `PATCH /me` precedent this story already tells you to follow.**
Type the field as a plain `str | None` and **validate it in the service**, raising the typed
`DomainError`. `me.py:89` types `full_name: Any` for exactly this reason and validates in the service
(`INVALID_NAME` → 400). This one move solves three problems at once:

- the `Literal` guard (this landmine);
- an **invalid** disposition value (`"FOO"`), which as a `Literal` would yield a bare **422 outside
  the `{code, message, details}` envelope** (the NFR-17 hole Task 7 forbids) and as an unvalidated
  `str` would reach `CHECK (disposition IN (…))` and fire a **raw 500** (an AD-5 violation — the
  CHECK is a backstop, never a gate);
- the "was it supplied at all?" question, which is the same question with the same answer.

**Raise `POLICY_DISPOSITION_REQUIRED` (400) for both "absent" and "present but not one of the two."**
The API contract defines no second code and you must not invent one.

*(The migration's DDL is exempt — `alembic/versions/` is **not** scanned. `CheckConstraint("disposition
IN ('RECALCULATE','PRESERVE')")` in Task 1 is correct as written.)*

---

## Tasks / Subtasks

### Task 1 — `policy_change`: the model, migration `0011`, and its own grant (AC1)

- [x] `backend/alembic/versions/0011_policy_change.py`. `revision = "0011_policy_change"`,
      `down_revision = "0010_admin_review_flag"`. **Copy `0010_admin_review_flag.py`'s shape
      exactly**: re-declare the module-private `_quoted_role()` (do **not** import it — Alembic
      revisions are not a package), refuse `--sql` offline mode with the `_OFFLINE_REFUSAL`
      `RuntimeError`, and issue its **own** `GRANT INSERT, SELECT ON policy_change TO <role>` via
      `psycopg.sql.Identifier`. `0008` deliberately issued no `ALTER DEFAULT PRIVILEGES`, so
      **nothing is inherited: a table that adds itself adds its own grant.** This is the FOURTH
      append-only table.
- [x] Columns: `id` (uuidv7 PK), `leave_type_id` (FK → `leave_type.id`, NOT NULL), `attribute`
      (TEXT), `old_value` (TEXT), `new_value` (TEXT), `disposition` (TEXT), `occurred_at`
      (TIMESTAMPTZ). Plus `CheckConstraint("disposition IN ('RECALCULATE','PRESERVE')")` — AC1's
      one non-negotiable constraint.
- [x] `old_value` / `new_value` are **TEXT** (erd.md L151-152), because one column pair must carry an
      int (`annual_entitlement`), a nullable int (`carry_forward_cap`) and a bool
      (`carries_forward`). Stringify at the service boundary; `None` → the string `"null"`, so the
      column can stay NOT NULL and "cap removed" is distinguishable from "cap unset". **Decide and
      state it** (Open Decision #4).
- [x] `backend/app/repositories/models.py` → `PolicyChange`, byte-faithful to `0011`
      (`tests/integration/test_model_migration_agreement.py` runs `alembic check`).
- [x] **Column-name divergence, resolve it the way 2.11 did:** erd.md L154 says `changed_at`; AC1 and
      the epic say `occurred_at`. **The AC is binding** — the same clash 2.11 hit (`raised_at` vs
      `occurred_at`) and resolved in the AC's favour (`models.py:527-528`), and `audit_entry`,
      `rollover_run` and `admin_review_flag` all ship `occurred_at`. Use `occurred_at`; record the
      divergence.

### Task 2 — `domain/recalculation.py`: teach the projection about proration (AC5) ⚠️ **Landmine 1**

- [x] Add keyword-only `new_prorated_by_year: dict[int, int] | None = None` to `project_forward`.
      `None` → today's behaviour, byte-identical, holiday path untouched.
- [x] When supplied: substitute the new prorated figure at year `Y` **and** at every later year,
      **and skip the fixed-point `break` entirely** — check every materialized year's availability
      and record every year's `carried_forward`.
- [x] Docstring must say *why* the break is skipped: under a policy change a later year moves through
      its **own** re-proration, not only through `carried_forward`, so "this year's carry-forward
      didn't move" no longer implies "this year's Available didn't move". Keep the module pure
      (stdlib + `domain/carry_forward` only).
- [x] **Two existing docstrings become FALSE — revise them, don't leave them.** `recalculation.py:88-89`
      says *"An EMPTY map means the fixed point was reached immediately: nothing above `Y` moves"* (on
      the policy path an empty map means "there is only one materialized year"), and
      `recalculation.py:110-111` says `years[0]` is *"the edited Leave Year `Y`"* (on the policy path
      it is the **lowest materialized** year, and there is no single edited year). A stale docstring
      that contradicts the code is how the next story inherits a wrong mental model.
- [x] `tests/domain/test_recalculation.py` — no DB fixture. **The test that proves the fix is
      load-bearing:** a `carries_forward=False` type whose `annual_entitlement` drops, with a spent
      later year → `refused=True`, `refused_year=<the later year>`. Against today's code that test
      returns `refused=False`. Also: a carrying type where the cap binds at `Y` but a later year goes
      negative.

### Task 3 — Repositories: the leave-type write, the pair sweep, the policy-change store (AC1, AC3, AC5, AC7)

- [x] `repositories/leave_type.py` → `update_leave_type(session, *, leave_type_id, **fields) -> None`
      (a write; not a scoped-getter candidate).
- [x] `repositories/leave_balance.py` → the pair sweep. For one Leave Type, return each Employee that
      has a balance row **and their first materialized year**: `SELECT employee_id,
      MIN(leave_year) … WHERE leave_type_id = :id GROUP BY employee_id ORDER BY employee_id`
      (ascending `employee_id` **is** AD-3's lock order). This is a plain discovery read; the rows are
      then locked `FOR UPDATE` ascending by `_materialized_years`. Name it honestly (`list_…`) and
      **EXEMPT it with a rationale** — a system-wide sweep on the Admin's command, the third ground
      `list_requests_covering` was granted.
- [x] `repositories/policy_change.py` → `insert_policy_change(...)` (`flush()`, **never** `commit()`)
      and `list_policy_changes(session, *, limit, offset)` joining `leave_type` for its `code`.
      `ORDER BY occurred_at DESC, id DESC` — **the `id` tiebreak is load-bearing**: one PATCH can
      write several rows sharing one `occurred_at`. **No update method. No delete method.**

### Task 4 — `domain/vocabulary.py` + `main.py` (AC2, AC3, AC5)

- [x] `POLICY_DISPOSITION_REQUIRED = "POLICY_DISPOSITION_REQUIRED"` — the error code.
- [x] `CAUSE_POLICY_RECALCULATION = "POLICY_RECALCULATION"` — beside `CAUSE_HOLIDAY_RECALCULATION`,
      exactly where `vocabulary.py:244-245` and `models.py:524-525` already say it goes. **One cause
      for this whole story** (2.11 Open Decision #5 reserved it by name).
- [x] `DISPOSITION_RECALCULATE = "RECALCULATE"` and `DISPOSITION_PRESERVE = "PRESERVE"` — AD-21: every
      enumerated string that crosses the wire is declared once in `domain/` and appears as a literal
      nowhere else.
- [x] **All four into `__all__`.** Then `main.py`: `CODE_TO_STATUS` gains
      `vocabulary.POLICY_DISPOSITION_REQUIRED: 400` and nothing else. (`CAUSE_POLICY_RECALCULATION`
      and the two dispositions are enumerated strings, not error codes — they map to no status.)
- [x] ⚠️ **Landmine 9.** The disposition field is **not** a Pydantic `Literal` — it cannot be, and the
      build will tell you so. Type it `str | None` on the request model and **validate it in the
      service** against the two constants, raising `POLICY_DISPOSITION_REQUIRED` for both "absent"
      and "not one of the two". `api/` therefore never needs the values at all, and the
      `api/ → domain/` import that import-linter forbids never arises.

### Task 5 — `services/recalculation.py`: the policy engine (AC5, AC6) ⚠️ **Landmines 1, 2, 4, 5**

- [x] `recalculate_for_policy_change(session, *, leave_type_id, annual_entitlement, carries_forward,
      carry_forward_cap) -> RecalculationSummary` — a **sibling** of
      `recalculate_for_holiday_change` in the **same module**. Reuse `RefusedPair` and
      `RecalculationSummary` unchanged; do **not** define a second summary type (the API projection
      and the frontend types are already shaped around these).
- [x] Takes the caller's open `Session`, opens no transaction (AD-3). Called **after** the
      `leave_type` UPDATE is flushed, so the row it reads is the new policy — the same discipline
      `services/holidays.py` uses (`flush()` the calendar edit, *then* recalculate).
- [x] Per pair, in order: sweep the pairs → `_materialized_years(from_year=<the pair's FIRST year>)` →
      compute `new_prorated_by_year = {y: prorate_entitlement(new_annual, employee.joining_date, y)}`
      for every materialized year → `project_forward(..., new_prorated_by_year=...)` with
      `new_reserved=years[0].reserved` and `new_consumed=years[0].consumed` (**a policy change moves
      neither** — pass the row's current absolutes, unchanged) → **refused**: write the
      `admin_review_flag` with `CAUSE_POLICY_RECALCULATION`, append a `RefusedPair`, `continue`,
      touching nothing else for that pair → **not refused**: `set_accrual` for **every** materialized
      year ascending, then the explicit `recompute_carry_forward` (Landmine 2's code block).
- [x] `requests_recalculated` is **always `0`** on this path — a policy change touches no Leave
      Request and **must never call `set_leave_days`** (`leave_days` is a function of the calendar,
      not of entitlement; its docstring at `repositories/leave_request.py:285-300` names exactly one
      sanctioned caller, and it is not you). Do not widen that docstring.
- [x] Import no `audit_entry_repo`. Write no audit row.

### Task 6 — `services/leave_types.py`: the disposition gate and the one transaction (AC2, AC3, AC4, AC6) ⚠️ **Landmine 3**

- [x] `update_leave_type(...)`. **The gate:** compute which submitted attributes actually **change** a
      value, then ask whether any of them is balance-affecting. If yes **and** no valid disposition
      was supplied → raise `POLICY_DISPOSITION_REQUIRED` (400) **before any write**, via the typed
      `DomainError` factory (`_leave_type_code_in_use` at `leave_types.py:41` is the shape). Nothing
      is applied — not the leave-type row, not a `policy_change` row. `details` names the attributes
      that forced the choice (NFR-17).
- [x] **Balance-affecting = `annual_entitlement`, `carry_forward_cap`, `carries_forward`.** The first
      two are named by AD-19, AD-6, architecture §6.3 and AC6. `carries_forward` is Open Decision #1
      — **recommended: it triggers**, because `carry_forward_days` reads it *first* and flipping it to
      `false` zeroes `carried_forward` in every materialized year, which is precisely *"a change that
      would affect Leave Balances that already exist"* (FR-06's own words). Not balance-affecting:
      `name`, `code`, `requires_supporting_document`.
- [x] A submitted value **equal to the stored one** is not a change and must not trigger the gate.
      **But the gate does NOT depend on whether balance rows exist** — require the disposition for any
      balance-affecting change, always. A data-dependent gate would mean an Admin editing a Leave Type
      with no materialized balances gets **no `policy_change` row at all**, silently skipping AC3.
      (Open Decision #5.)
- [x] **The two dispositions do NOT map onto "write balances" / "don't". They map onto what has a
      basis to preserve** (Landmine 3):

      | Attribute changed | `PRESERVE` | `RECALCULATE` |
      |---|---|---|
      | `annual_entitlement` | balances untouched — `entitlement_basis` freezes it, and future accruals pick up the new value for free | re-derive `prorated_entitlement` + `entitlement_basis` + `carried_forward` in every materialized year, under the forward check |
      | `carry_forward_cap` · `carries_forward` | **re-derive `carried_forward` under the forward check anyway** — nothing freezes the cap, and the next unrelated reject would do it unguarded and 500 | same |

      So the forward-checked engine runs whenever a **cap or `carries_forward`** change is applied,
      under either disposition, and whenever `annual_entitlement` changes under `RECALCULATE`. It
      runs on **no other path**. That is AC6 read literally — it carries no disposition qualifier —
      and it is the only reading under which `PRESERVE` is not a lie.
- [x] One transaction (AD-3): UPDATE the `leave_type` row → `flush()` (so the engine reads the new
      policy) → call the engine **if the table above says to** → `insert_policy_change` (one row **per
      changed balance-affecting attribute**, Open Decision #3) → `commit()`.
- [x] Return a `LeaveTypeCommandResult { leave_type: LeaveTypeView, recalculation:
      RecalculationSummary }` — the `HolidayCommandResult` shape (`services/holidays.py:107-117`).
      A name-only edit returns an empty summary (`0, 0, []`), never `None`.
- [x] ⚠️ `annual_entitlement` has **no `Field(ge=0)`** (`deferred-work.md:44`). On create that was a
      curiosity; on a `PATCH … RECALCULATE` a negative value reaches `prorate_entitlement` and fires
      a raw 500 **on an Admin's edit**. Fix it (Open Decision #2).

### Task 7 — The endpoints (AC2, AC5, AC7, AC8)

- [x] `PATCH /api/v1/leave-types/{leave_type_id}` in the existing `api/v1/leave_types.py` (no
      `router.py` change). Admin-only via `require_role(authz.ROLE_ADMIN)`. Returns **`200`** with
      `LeaveTypeCommandResponse { leave_type, recalculation }`.
- [x] **Use `model_config = ConfigDict(extra="allow")` + `model_dump(exclude_unset=True)`** — the
      `PATCH /me` precedent (`api/v1/me.py:16-21, :89`). **Not `extra="forbid"`**: that raises
      `RequestValidationError` → a bare `422` *outside* the `{code, message, details}` envelope,
      breaking NFR-17. `exclude_unset` is also how the service learns which fields the PATCH actually
      touched, and how "cap set to null" stays distinguishable from "cap not submitted".
- [x] `disposition: str | None = None` — **not a `Literal`** (Landmine 9). The service validates it.
- [x] `POLICY_DISPOSITION_REQUIRED`'s `details` must be **actionable** (NFR-17): name the attributes
      that forced the choice, and the two values that are accepted.
- [x] **Reuse `RefusedPairResponse` and `RecalculationResponse` from `api/v1/holidays.py`** — do not
      redeclare them. `api/ → api/` is allowed by import-linter contract 2. A second copy is drift.
      Project with `_to_command_response(result: object)` typed `object`, the contract-2 idiom.
- [x] `api/v1/policy_changes.py` → `GET /policy-changes`, Admin-only, `Page[PolicyChangeResponse]`.
      Mirror `api/v1/admin_review_flags.py` exactly. **No new error code**: `require_role` already
      yields `403 ACTION_NOT_PERMITTED` (AC8, already mapped). Register in `router.py`.

### Task 8 — Frontend (AC10, AC11, AC12)

- [x] **Extract, don't clone.** `src/components/README.md`: *"a component used by exactly one feature
      lives with that feature until a second caller appears."* You **are** the second caller. Lift
      `HolidaysPage.tsx:209-257`'s refused-pair summary into
      `src/components/RecalculationSummaryPanel.tsx` taking `{ action: string; summary:
      RecalculationSummary }`, and have `HolidaysPage` consume it. `src/components/` is currently
      empty.
- [x] Same for the invalidation fan-out: `holidays.ts:106-120`'s
      `invalidateEverythingARecalculationMoves` is module-private. A policy change moves the same
      four keys **plus** `LEAVE_TYPES_QUERY_KEY` and the new `POLICY_CHANGES_QUERY_KEY`. Extract to a
      neutral `api/recalculation.ts` (mirroring the backend, where `RefusedPair` lives in
      `services/recalculation.py`, not in `services/holidays.py`) and move the
      `RecalculationSummary` / `RefusedPair` types there too. Update `api/index.ts` — features import
      from there, never from a file path. (`src/components/` currently holds only its `README.md`.)
- [x] `LeaveTypesPage.tsx` — add the edit form. `editingId` inline-edit is the `EmployeesPage.tsx:311`
      idiom. **AC10: the form will not submit without a disposition** when a balance-affecting field
      changed — a guard clause plus `disabled` on the submit button (there is no form library; state
      is held as strings and converted at submit). State in plain language what each option does:
      `RECALCULATE` re-derives every existing balance under the new policy; `PRESERVE` leaves existing
      balances as they were accrued and applies the new value only to future accruals.
- [x] `PolicyChangesPanel.tsx` — Pattern B (`if (!isAdmin) return null` + `enabled: isAdmin`), a near-
      clone of `ReviewFlagsPanel.tsx`: four states (loading / error / empty / list),
      `<ul className="emp-list">` rows showing leave-type code, attribute, `old → new`, disposition,
      `occurred_at`. **There is no router** — register one `<PolicyChangesPanel />` line in `App.tsx`
      beside `<ReviewFlagsPanel />`, with a house-style comment.
- [x] **Add no CSS.** `index.css` already has `.panel`, `.muted`, `.emp-list`, `.emp-row`,
      `.emp-summary`, `.emp-name`, `.emp-error`, `.emp-inactive`, `.emp-field`. There are no `<table>`
      styles in this app — every list is `<ul>/<li>`.
- [x] **Render every server figure as received.** The client computes no balance and no day count
      (AD-2). Nothing forbids it mechanically — `tests/test_frontend_no_client_day_count.py` greps
      only for `getDay`/`getUTCDay` — so do not be the first to break the rule that is currently only
      prose.

### Task 9 — Tests (AC1–AC12)

- [x] **Domain, no fixture** (`tests/domain/test_recalculation.py`): Task 2's two projection tests.
- [x] **AC2**: PATCH `annual_entitlement` with no disposition → `400 POLICY_DISPOSITION_REQUIRED`,
      **and assert the leave-type row and every balance row are byte-unchanged** ("nothing is
      applied" is half the AC). PATCH with `disposition="FOO"` → the same `400`, **not** a bare 422
      and **not** a raw 500 from the CHECK (Landmine 9). PATCH `name` only with no disposition →
      `200`, no `policy_change` row, no balance touched.
- [x] **AC4 (PRESERVE, `annual_entitlement`)**: balance rows byte-identical after the change; the
      `leave_type` row updated; then run the rollover and assert `Y+1` picks up the **new** value —
      that is what "only future accruals use the new value" means.
- [x] **AC4/AC6 (PRESERVE, `carry_forward_cap` — Landmine 3)**: lower the cap under `PRESERVE`, then
      **reject an unrelated year-`Y` request** and assert it returns cleanly and does **not** 500. The
      regression this pins is the delayed detonation: under the naive "PRESERVE writes nothing"
      reading, that reject fires `recompute_carry_forward`, re-reads the new cap, drops `accrued(Y+1)`
      into a spent year, and raises a bare `ValueError`. Write this test **first** — it fails against
      the naive implementation, which is the point.
- [x] **AC5 (RECALCULATE, the happy path)**: `accrued`, `prorated_entitlement`, `carried_forward` and
      `entitlement_basis` re-derived in **every** materialized year; `accrued = prorated + carried`
      holds everywhere.
- [x] **AC5 (the refusal)**: a pair driven negative in a **later** year is left **entirely** unchanged
      (every column, every year), one `admin_review_flag` row with `CAUSE_POLICY_RECALCULATION`
      appears, **the same Employee's other Leave Types still commit**, and the endpoint returns
      `200` + summary. **Include the non-carrying-type case from Landmine 1** — it is the one that
      today's code gets wrong.
- [x] **AC5 non-vacuity**: monkeypatch `project_forward` → "never refused"; the refusal scenario must
      then blow up in `set_accrual`'s guard. (Landmine 5.)
- [x] **AC6**: `recompute_carry_forward` after the apply loop is a **no-op** — rows byte-identical
      before and after.
- [x] **AC3**: one `policy_change` row per changed balance-affecting attribute, carrying old/new/
      disposition/moment; **assert the table has no actor column** (AC1's "by decision" is testable).
- [x] **AC1**: as the app role, `UPDATE` and `DELETE` on `policy_change` are both refused with
      `psycopg.errors.InsufficientPrivilege`; `INSERT`/`SELECT` succeed. (2.10/2.11 verified this
      live; do the same — use the `owner_engine` conftest fixture for cleanup, since the app role
      cannot delete these rows.)
- [x] **AC7/AC8**: Admin reads `GET /policy-changes`; Employee and Manager each get `403
      ACTION_NOT_PERMITTED`; both `401` without a token.
- [x] **AC9 (SM-5)**: create a fourth Leave Type through the API → apply for it → reserve → approve →
      **PATCH its policy** → roll it over — with no code change and no migration. This is the metric
      the whole epic is judged on; make it one end-to-end test that names SM-5.
- [x] **SM-4 stays 14.** Run `tests/integration/test_audit_entries.py` and confirm the count and the
      per-`subject_type` breakdown are untouched.
- [x] ⚠️ **There is no frontend test runner.** `package.json` has only `dev` / `build` (`tsc -b &&
      vite build`) / `lint` (`oxlint`); there is not a single `*.test.*` file in `frontend/`. AC10,
      AC11 and AC12 are verified by `build` + `lint` + your own manual exercise, and by nothing else.
      **Say so in the Dev Agent Record** rather than implying coverage that does not exist.

### Task 10 — The guard files (they will fail the build if you forget)

- [x] `tests/test_scope_matrix.py` → register `("PATCH", "/api/v1/leave-types/{leave_type_id}"):
      frozenset({Scope.ALL})`, with a comment in the house style. Do **not** register
      `GET /policy-changes` (no path parameter → out of the matrix by construction).
- [x] `tests/test_scoped_getters.py` → `EXEMPT` gains `list_policy_changes` (+ the sweep getter from
      Task 3), each with a rationale.
- [x] `tests/test_migrations_insert_nothing.py:121` → append `"0011_policy_change.py"`.
- [x] `tests/integration/test_migration_smoke.py:25` → `HEAD_REVISION = "0011_policy_change"`.
- [x] `tests/integration/test_schema_1_2.py:50` → add `policy_change` to the expected table set.
- [x] `pyproject.toml [tool.importlinter]` → **untouched.** `tests/test_architecture.py` pins all
      seven contracts byte-for-byte.

---

## Dev Notes

### The one-paragraph mental model

`PATCH /leave-types/<id>` is a normal admin edit with one extra question attached: *"and what about
the balances that already exist?"* The Admin must answer. `PRESERVE` means "nothing — just change the
policy going forward", and it writes no balance row because the rest of the system already reads the
live `leave_type` row when it accrues. `RECALCULATE` means "rewrite them all", and rewriting them all
is exactly the AD-19 operation Story 2.11 built — same forward check, same per-pair refusal, same
`admin_review_flag`, same `200` + summary — with one difference that changes the arithmetic
underneath: a policy change moves **`prorated_entitlement` in every materialized year at once**,
where a holiday change moved `reserved`/`consumed` in exactly one. Two fixed-point optimizations that
are correct for 2.11 are unsound for you.

### Reuse map — most of this already exists

| You need | It already exists | Do not |
|---|---|---|
| The forward check | `domain/recalculation.py::project_forward` | Clone it. **Extend** it (Landmine 1). |
| The clamp `min(cap, available)` | `domain/carry_forward.py::carry_forward_days` | Re-derive it. It also gives you 2.10's "NULL cap = uncapped" for free. |
| Proration | `domain/proration.py::prorate_entitlement(annual, joining_date, leave_year)` — **positional** | Re-derive the floor rule. |
| The balance write | `services/balances.py::set_accrual` (the only legal writer of the accrual triple) | Add a ninth method. |
| Lock + walk the years | `services/recalculation.py::_materialized_years` | Use `balances._lock` — it raises `LookupError` on a missing row, which is how the walk *ends*. |
| The refusal record | `repositories/admin_review_flag.py::insert_admin_review_flag` + the existing `GET /admin-review-flags` + `ReviewFlagsPanel` | Build a second flag store or a second screen. A `POLICY_RECALCULATION` flag simply appears in the existing one. |
| Carry-forward propagation | `services/rollover.py::recompute_carry_forward` — you are its **fourth** call site (the three: `_decide`, approve-CR, 2.11's holiday recalculation) | Make it re-prorate (Landmine 2). |
| `200` + summary | `RefusedPair` / `RecalculationSummary` (services) · `RefusedPairResponse` / `RecalculationResponse` (api/v1/holidays.py) · `RecalculationSummary` (frontend `api/holidays.ts`) | Declare a second copy of any of them. |
| The append-only migration | `0010_admin_review_flag.py` — `_quoted_role`, the `--sql` refusal, the `GRANT INSERT, SELECT` | Assume a default privilege is inherited. `0008` declined to grant one. |
| The Admin read screen | `ReviewFlagsPanel.tsx` (Pattern B) + `adminReviewFlags.ts` | Invent a table. There are no `<table>` styles. |

### What is already true, and must stay true

- **`available` is never a column** (DR-3). `accrued = prorated_entitlement + carried_forward` is a
  **non-deferrable** CHECK — the three move in one statement, which is why `set_accrual` exists and
  takes the two *parts*.
- **The CHECKs are a backstop, never a gate** (AD-5). Every refusal is decided in the service, before
  the write, and carries its numbers.
- **No branch tests a Leave Type by name or code** (AD-11 / SM-5). `carry_forward_days` is
  deliberately built so it *cannot* see a code. Keep it that way — SM-5's fourth Leave Type is
  AC9, and it is the metric the epic is graded on.
- **`is_active` gates authentication, not accrual** (2.10 Open Decision #3). A deactivated Employee's
  balances are recalculated like anyone else's.
- **`leave_days` is frozen on the request** (AD-18) and only AD-19's *holiday* recalculation may move
  it. You are not that.

### Gotchas this codebase has actually produced (2.4 → 2.11 reviews)

- `lock_balance`, never `_lock`, on any path where a missing row is legal (documented at
  `balances.py:311-316`; it broke a create hook once already).
- `date.today().year` is never the recalculation year. Three stories have now hit this.
- `adjust_reserved`/`adjust_consumed` take **absolute** values, not deltas — a silent corruption that
  no CHECK catches. **You should be calling neither**; if you are, re-read Landmine 2.
- A surface test gets **revised with a rationale**, never renamed around (2.9's review).
- The frontend is **not optional**. 2.10's Dev Notes quote the readiness report's line that *"Four
  stories in Epic 2 — 2.9, 2.10, 2.11, 2.12 — carry no frontend criterion at all."* That sentence was
  already stale for 2.11 and it is **stale for you**: epics.md gives this story **three** frontend
  ACs (10, 11, 12). Do not let a stale line talk you out of them.

### Project Structure Notes

```
backend/
  alembic/versions/0011_policy_change.py            NEW  (0010's shape; its OWN grant)
  app/domain/recalculation.py                       EDIT (new_prorated_by_year; skip the break)
  app/domain/vocabulary.py                          EDIT (+4 constants, +__all__)
  app/main.py                                       EDIT (CODE_TO_STATUS: +1 line, the ONLY change)
  app/repositories/models.py                        EDIT (+ PolicyChange)
  app/repositories/leave_type.py                    EDIT (+ update_leave_type)
  app/repositories/leave_balance.py                 EDIT (+ the pair sweep)
  app/repositories/policy_change.py                 NEW  (insert + list; NO update, NO delete)
  app/services/recalculation.py                     EDIT (+ recalculate_for_policy_change)
  app/services/leave_types.py                       EDIT (+ update_leave_type: the disposition gate)
  app/services/policy_changes.py                    NEW  (the read service; services/audit.py shape)
  app/api/v1/leave_types.py                         EDIT (+ PATCH, 200 + summary)
  app/api/v1/policy_changes.py                      NEW  (GET, Admin-only)
  app/api/v1/router.py                              EDIT (+1 include_router)
frontend/src/
  api/recalculation.ts                              NEW  (the extracted types + invalidation fan-out)
  api/holidays.ts                                   EDIT (consume the extraction)
  api/leaveTypes.ts                                 EDIT (+ useUpdateLeaveType)
  api/policyChanges.ts                              NEW
  api/index.ts                                      EDIT (re-export; the single public surface)
  components/RecalculationSummaryPanel.tsx          NEW  (lifted from HolidaysPage — 2nd caller)
  features/holidays/HolidaysPage.tsx                EDIT (consume the extraction)
  features/leaveTypes/LeaveTypesPage.tsx            EDIT (+ the edit form, + the summary)
  features/policyChanges/PolicyChangesPanel.tsx     NEW  (ReviewFlagsPanel's shape, Pattern B)
  App.tsx                                           EDIT (+1 line; there is no router)
```

**No change to:** `pyproject.toml` · `services/balances.py` · `services/rollover.py` ·
`domain/carry_forward.py` · `domain/proration.py` · `repositories/admin_review_flag.py` ·
`api/v1/admin_review_flags.py` · `seed/` (its `ON CONFLICT (code) DO NOTHING` never updates a Leave
Type, so a re-seed will not revert a policy change) · `index.css`.

### References

- Requirements — `_bmad-output/planning-artifacts/epics.md` L1339-1399 (Story 2.12); FR-06 (prd.md
  L207-220); SM-5 (prd.md L635); SM-4 (prd.md L631); NFR-16, NFR-17.
- Architecture — `ARCHITECTURE-SPINE.md`: AD-5 (L91), AD-6 (L97), AD-8 (L109), AD-9 (L115), AD-11
  (L127), AD-17 (L163), AD-18 (L169), AD-19 (L175), AD-20 (L181), AD-21 (L187). `architecture.md`
  §6.3 (L282-295) is the reasoning behind this exact path and names the trap: *"a policy change is
  not a balance change, so the recompute trigger as originally stated would never have fired at
  all."* Note §6.3 also writes *"lowering a Leave Type's `carry_forward_cap` or `annual_entitlement`
  **with the disposition RECALCULATE**"* — the **only** place a disposition qualifier is attached to
  the recomputation. AD-6 (L101) and AC6 attach none, and Landmine 3 is why the unqualified reading
  is the one that holds.
- API — `api-contracts.md` L142 (the §4.3 matrix rows), L149 (the disposition rule), L151 (`200` +
  summary for both recalculating endpoints), L85 (`POLICY_DISPOSITION_REQUIRED` → 400).
- ERD — `erd.md` L147-155 + L293-302 (`policy_change`), L215 (`entitlement_basis`: *"Without it,
  FR-06's RECALCULATE disposition has nothing to recalculate from"*), L283-291
  (`admin_review_flag`).
- ⚠️ **`ARCHITECTURE-SPINE.md` L317-321's ERD diagram is STALE** for `admin_review_flag` (it shows a
  polymorphic `subject_id` and a `resolved_at`, both contradicted by AD-20's own prose at L185,
  erd.md L283-291, and the shipped `0010`). Story 2.11 reported it and it has not been corrected.
  The `POLICY_CHANGE` node at L322-324 is *abbreviated*, not stale, and agrees with erd.md. **Build
  from AC1 and erd.md, not from that diagram.**

---

## Open Decisions

*Decide during dev; keep code and tests consistent; record the call in the Dev Agent Record.*

1. **⚠️ THE ONE GENUINELY UNDER-DETERMINED POINT — what `PRESERVE` means for a `carry_forward_cap` or
   `carries_forward` change (Landmine 3).** The spec assumes both dispositions are meaningful for
   every attribute. The schema does not support that: `entitlement_basis` freezes the annual
   entitlement, and **there is no cap basis** — every downstream trigger re-reads the cap live and
   re-derives `carried_forward` with no forward check. So "preserve" is unimplementable for the cap;
   the only question is whether the system does the re-derivation **now, guarded**, or lets an
   unrelated reject do it **later, unguarded, as a 500**.
   **Recommended: run the forward-checked recomputation on both dispositions for a cap or
   `carries_forward` change** (the Task 6 table). It makes AC6 literally true — AC6 carries no
   disposition qualifier — and it is the only reading under which `PRESERVE` is not a promise the
   system cannot keep. The residual honesty cost: for a **cap-only** change, `PRESERVE` and
   `RECALCULATE` do the same thing to balances and differ only in what `policy_change` records. Say
   that in the UI copy rather than hiding it. The alternative (refuse `PRESERVE` for those two
   attributes) needs an error code api-contracts does not define — **do not invent one.**

2. **Does `carries_forward` require a disposition at all?** AD-19, AD-6, architecture §6.3 and AC6
   enumerate only `annual_entitlement` and `carry_forward_cap`. But `carry_forward_days` reads
   `carries_forward` **first**, so flipping it `true → false` zeroes `carried_forward` in every
   materialized year — exactly *"a change that would affect Leave Balances that already exist"*
   (FR-06, prd.md L217). **Recommended: it triggers.** FR-06's condition is the gate; AD-19's list
   describes the recalculation *mechanism*.

3. **Where does `annual_entitlement >= 0` get enforced?** (`deferred-work.md:44` — a negative value
   reaches `prorate_entitlement` and fires a raw 500; this story makes it reachable **on an Admin's
   edit**.) Note the tension with Task 7's envelope rule: a Pydantic `Field(ge=0)` raises
   `RequestValidationError` → a bare `422`, which is the very thing `extra="forbid"` is rejected for.
   **Recommended: `Field(ge=0)` on the schema anyway, and be explicit about why the two differ** — a
   *malformed number* is a schema-level fault (422 is the honest code), whereas `extra="allow"` exists
   because PATCH semantics need "absent" ≠ "null" **and** because `FORBIDDEN_FIELD` is a *domain*
   rule about authority, not a shape. If you would rather have the envelope, validate in the service
   and reuse an existing 400 — but then say which one, and do not add a code.

4. **One `policy_change` row per changed attribute.** The table is singular (`attribute`,
   `old_value`, `new_value`), so a PATCH changing two attributes writes two rows sharing one
   `occurred_at` and one disposition. **Recommended: a row per changed *balance-affecting* attribute
   only** — `disposition` is NOT NULL with a two-value CHECK, and a `name` change has no disposition
   to record. (The alternative needs a nullable disposition, which AC1's CHECK forbids.)

5. **The gate must not be data-dependent.** FR-06 says *"balances that already exist"*, which tempts
   a gate that skips the disposition when a Leave Type has no materialized balance rows — and that
   Leave Type then gets **no `policy_change` row at all**, silently skipping AC3. **Recommended:
   always require the disposition for a balance-affecting change**, regardless of whether rows exist.
   It also removes a data-dependent branch from a command that is already hard enough.

6. **`old_value` / `new_value` are TEXT and must hold an int, a nullable int and a bool.**
   **Recommended:** stringify at the service boundary and render `None` as `"null"`, so the columns
   stay NOT NULL and "the cap was removed" stays distinguishable from "there was never a cap". The
   frontend renders them as received.

7. **Which year does a refusal name?** `admin_review_flag.leave_year` is NOT NULL. A policy refusal is
   discovered at a *specific* year — the one `ForwardProjection.refused_year` names. **Recommended:
   flag that year**, not the current one: it is the year the Admin has to go and look at.

8. **AC5 says the three quantities are "re-derived from `entitlement_basis`".** Read literally that is
   circular — the row's `entitlement_basis` is the **old** annual entitlement. The operative meaning:
   `entitlement_basis` is the column that *makes the re-derivation possible* (erd.md L215), and
   RECALCULATE re-derives from the **new** `annual_entitlement` and **overwrites** `entitlement_basis`
   with it, while PRESERVE leaves both alone. **Recommended: implement that, and record the reading**
   — do not leave a reviewer to wonder whether the AC was misread.

9. **Non-contiguous materialized years.** `_materialized_years` stops at the first gap. A skipped
   rollover (`--year 2027` without `--year 2026`) leaves a hole, and every year **above** the hole
   keeps its old proration and old basis forever, with no flag — a wrong balance that will be
   believed. Operator error, and the rest of the system already assumes contiguity.
   **Recommended: detect and flag it rather than silently truncating** — the sweep already knows each
   pair's `MAX(leave_year)`; if it exceeds the walk's last year, refuse the pair and flag it. If you
   judge that out of scope, log it to `deferred-work.md` by name.

10. **The pair sweep is a TOCTOU with concurrent Employee creation.** An Employee created between the
    sweep and the commit gets a balance row materialized under the *new* policy anyway (the create
    hook reads the live `leave_type` row), so the outcome is benign. Mirrors the concurrent-create
    materialization race 2.4's review already accepted. **Recommended: accept and note it.**

11. **⚠️ INHERITED, STILL LIVE — 2.11's Open Decision #8 (`deferred-work.md`, last section).**
    `reserve` and `consume_direct` lower `available(Y)` and recompute `carried_forward(Y+1)` **not at
    all**, so a post-rollover year-`Y` submission leaves `carried_forward(Y+1)` **overstated** —
    against AD-6's *"every event that can change its inputs"*. 2.10 wired the hook into only the three
    sites where `available(Y)` **rises**. 2.11 contained the blast radius and raised it rather than
    silently widening scope; the reviewer did not rule. **This is the last story of Epic 2 — if it is
    not fixed here it ships.** Your forward check contains it again (it runs over stored values, so a
    stale-high `carried_forward` is projected down and, if that drives a spent year negative, refused
    cleanly). **Recommended: still do not fix it inside this story's scope — but force the call.** The
    fix is one `recompute_carry_forward` call in `submit_leave_request` after `reserve`/`consume_direct`.
    Put it to the reviewer explicitly; if the answer is "not now", make sure it leaves Epic 2 as a
    named, owned item and not as an accident.

12. **Inherited for free, do not re-decide:** a NULL `carry_forward_cap` on a carrying type means
    **UNCAPPED** (2.10 Open Decision #2) — you get this by reusing `carry_forward_days`. **The live
    consequence:** a PATCH setting `carry_forward_cap` to `null` means *uncapped*, not *zero*, and it
    is a cap change, so it triggers the disposition and AC6's recomputation. Note that **raising** a
    cap (or removing it) is monotonic-up and safe; **lowering** it is Landmine 3. Test both.

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (1M context) — `claude-opus-4-8[1m]`.

### Debug Log References

Backend `pytest`: **505 passed** (baseline 469, +36). import-linter **7/7 kept** (`pyproject.toml`
`[tool.importlinter]` byte-for-byte untouched). `alembic upgrade head` → `downgrade -1` → `upgrade
head` idempotent; `alembic check` empty. `python -m seed` exit 0. Frontend `npm run build` + `npm run
lint` clean. SM-4's audit ledger still exactly **14** rows with its per-`subject_type` breakdown
(`test_audit_entries.py` untouched and passing).

**Two adversarial non-vacuity proofs were run, and both passed:**

1. **Landmine 1.** Restored `project_forward`'s old unconditional `break` → exactly the 3 new policy
   projection tests FAIL while all 13 holiday tests still PASS. That asymmetry *is* the landmine: the
   break is correct for a holiday change and silently wrong for a policy change.
2. **Landmine 3.** Replaced `_must_recalculate` with the naive `disposition == RECALCULATE` → the 2
   `PRESERVE`-cap tests FAIL (`12 != 5` — five phantom carry-forward days visible to the Employee).

### Completion Notes List

**All 12 ACs met. One defect is SHIPPED KNOWINGLY and raised — see "OPEN FOR THE REVIEWER" below; it
is not a hidden one.**

**Landmine 1 (the story's central claim) is REAL, and is closed.** `project_forward`'s fixed-point
`break` is keyed only on `carried_forward`, which is sound for a holiday change (only `carried_forward`
can move a later year) and **false** for a policy change (every year's `prorated_entitlement` moves
independently). A **non-carrying** type — CL and FL, two of the three seeded — has `carried == 0 ==
stored` and so breaks on its *first* iteration, never checking a later year. Verified end-to-end:
lower such a type's entitlement while a later year is spent and the pre-2.12 code answers
`refused=False` → `set_accrual`'s guard → bare `ValueError` → raw 500, with every 2.11 test green.
Fixed by a keyword-only `new_prorated_by_year`; `None` keeps the holiday path byte-identical (asserted
by its own test).

**Landmine 2 closed:** the service writes **every** materialized year itself through `set_accrual`,
then calls `recompute_carry_forward` **once** as AC6's explicit trigger, where it must be a provable
no-op. `test_the_explicit_recomputation_is_a_no_op` re-runs it over the freshly written rows and
asserts every column is byte-identical — which is what makes AC6 a fact rather than a ceremony.

**Landmine 3 — resolved as recommended, but the story's stated regression was WRONG, and the truth is
worse.** Open Decision #1 adopted: a `carry_forward_cap` / `carries_forward` change runs the
forward-checked recomputation under **both** dispositions. But the story claims this *prevents* the
delayed 500 on an unrelated Manager's reject. **It does not, and I proved it does not.** What it
actually buys, measured:

| pair | naive `PRESERVE` | forward-checked (shipped) |
|---|---|---|
| **can** absorb the new cap | stale `carried_forward` — the Employee sees **phantom days they cannot take**, until some unrelated transaction silently corrects it | re-derived immediately, guarded, correct ✅ |
| **cannot** absorb it | stale → later reject **RAW 500** | refused + flagged → later reject **still RAW 500** ⚠️ |

So the harm the fix removes is the **wrong balance** (PRD §1's "figure that will be believed"), not the
500. For a pair the forward check *refuses*, the 500 remains reachable — because AD-19's "leave it
entirely unchanged" is a **stable** resting place for a holiday change (no input to
`carry_forward_days` moved) but **not** for a cap change, which moves a live, global input for
everybody *including the pair we declined to touch*. Both behaviours are pinned by passing tests; the
second is pinned as an explicit bug report.

**AC5 landed as a PREDICTION, not a catch.** No `try/except IntegrityError`, no `except ValueError`, no
`begin_nested()` SAVEPOINT anywhere on the path — all three would ship green and violate AC5. Proved
non-vacuous exactly as 2.11 did: monkeypatch `project_forward` to always say "not refused" and the
refusal scenario walks into `set_accrual`'s guard with an unhandled `ValueError`. The check is
load-bearing; the CHECKs stay a backstop.

**Landmine 4** (start at the pair's LOWEST materialized year, never `date.today().year`) — a new
repository sweep returns `MIN(leave_year)` per Employee, ordered by `employee_id` (AD-3's lock order).
**Landmine 6** — ZERO audit rows; `audit_entry_repo` is not imported by any module this story wrote,
and its absence is the proof (the `rollover.py` idiom). SM-4 still counts exactly 14.
**Landmine 7** — no ninth balance method (surface test still pins 8); `[tool.importlinter]` untouched.
**Landmine 8** — all four build guards updated, including the two new ones (`main.py`'s `CODE_TO_STATUS`
gains `POLICY_DISPOSITION_REQUIRED: 400` — the story's only `main.py` change — and `PATCH
/leave-types/{leave_type_id}` is registered in the SM-3 scope matrix as `{Scope.ALL}`).
**Landmine 9** — confirmed the hard way: `Literal["RECALCULATE","PRESERVE"]` is genuinely unwritable
under `app/`. The disposition is typed `Any` and validated in the service (the `PATCH /me` precedent),
which turns an invalid value from a bare 422 *or* a raw CHECK 500 into a clean `400`.

**No breaking change.** `POST /leave-types` still returns `201 + LeaveTypeResponse`. Unlike 2.11 (which
had to move `POST`/`DELETE /holidays` off `201`/`204`), `PATCH` is a new route, so nothing was
harmonized for symmetry's sake.

**Frontend NOT cut** — epics gives this story three frontend ACs and the readiness report's
"2.9–2.12 carry no frontend criterion" line is stale. `src/components/` gets its first occupant:
`RecalculationSummaryPanel` is **lifted** out of `HolidaysPage` (this story is the second caller the
README was waiting for) rather than cloned, and the invalidation fan-out + the `RefusedPair` /
`RecalculationSummary` types move to a neutral `api/recalculation.ts` — mirroring the backend, where
they live in `services/recalculation.py` and not in `services/holidays.py`. `holidays.ts` re-exports
them, so no existing import broke. No CSS added.

⚠️ **There is no frontend test runner.** `package.json` has only `dev` / `build` / `lint`, and there is
not a single `*.test.*` file in `frontend/`. **AC10, AC11 and AC12 are verified by `tsc -b` + `vite
build` + `oxlint` and by my own reading of the code — and by nothing else.** No automated test asserts
that the form refuses to submit without a disposition. Stating this plainly rather than implying
coverage that does not exist.

**Open Decisions:** #1 adopted (with the correction above), #2, #3, #4, #5, #6, #7, #8, #10 and #12
adopted as recommended. **#9 (non-contiguous materialized years) NOT implemented** — logged to
`deferred-work.md` by name, as the story permits: it is operator error, and the rest of the system
(`recompute_carry_forward`, `run_rollover`) already stops at the first gap identically, so adding a
refusal here alone would be a half-guarantee. **#11 forced, and the call is: still not fixed** — see
below.

---

### ⚠️ OPEN FOR THE REVIEWER — three items, the first is new and the second is now out of runway

1. **A pair REFUSED during a cap DECREASE is left holding a carry-forward the new policy forbids, and
   the next unrelated `recompute_carry_forward` on it raises a bare `ValueError` → RAW 500 ON AN
   INNOCENT THIRD PARTY.** **This story creates the path** (2.1 shipped no edit path, so
   `carry_forward_cap` was immutable until now). Reproduction is pinned as a *passing* test —
   `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject` — which asserts the 500 so
   that the bug is known, owned and reproducible rather than discovered in production. **Not fixed
   here** because the fix lives in `services/rollover.recompute_carry_forward` (which this story's own
   Dev Notes list under "No change to") and is a **design** call, not a typo: when a balance cannot
   absorb a new cap, should the reject *refuse* (api-contracts defines no error code), *clamp*
   (arithmetic no requirement grants), or *skip-and-flag* (a fourth flag-writer)? Silently widening
   scope to answer that is exactly what 2.11 declined to do with its own #8. **This is the reviewer's
   call and it should not lapse.**

2. **2.11's Open Decision #8 is STILL LIVE and Epic 2 is now over.** `reserve`/`consume_direct` lower
   `available(Y)` and recompute `carried_forward(Y+1)` *not at all*, against AD-6's "every event that
   can change its inputs". 2.11 raised it; the reviewer did not rule. **2.12 was the last story with a
   claim on it, and it too declined to fix it silently** — the containment argument still holds (this
   story's forward check runs over *stored* values, so a stale-high carry-forward is projected down and
   refused cleanly rather than 500ing). The fix is one `recompute_carry_forward` call in
   `submit_leave_request`. **It ships unless Epic 3 picks it up.**

3. **`ARCHITECTURE-SPINE.md:317-321`'s ERD diagram is still STALE** for `admin_review_flag` (shows a
   polymorphic `subject_id` and a `resolved_at`, both contradicted by AD-20's own prose at :185,
   `erd.md:283-291`, and the shipped `0010`). Story 2.11 reported it; it has not been corrected. Built
   from AC1 and `erd.md`, not from that diagram. The `POLICY_CHANGE` node at :322-324 is *abbreviated*,
   not stale, and agrees with `erd.md`.

**Recorded divergence (as the story instructed):** `erd.md:154` names the column `changed_at`; AC1 and
the epic name it `occurred_at`. **The AC is binding** — the identical clash 2.11 hit (`raised_at`) and
resolved the same way, and `audit_entry`, `rollover_run` and `admin_review_flag` all already ship
`occurred_at`. Built as `occurred_at`.

### File List

**New — backend**
- `backend/alembic/versions/0011_policy_change.py` — the FOURTH append-only table, with its OWN `GRANT INSERT, SELECT`; `--sql` refused; `CHECK (disposition IN (…))`
- `backend/app/repositories/policy_change.py` — insert + list. NO update, NO delete
- `backend/app/services/policy_changes.py` — the read service (`services/audit.py` shape)
- `backend/app/api/v1/policy_changes.py` — `GET /policy-changes`, Admin-only
- `backend/tests/integration/test_policy_change.py` — 25 tests (AC1–AC9, SM-5)

**Modified — backend**
- `backend/app/domain/recalculation.py` — `new_prorated_by_year`; the fixed-point break is skipped on the policy path; two now-false docstrings revised
- `backend/app/domain/vocabulary.py` — `+4` constants (`CAUSE_POLICY_RECALCULATION`, `POLICY_DISPOSITION_REQUIRED`, `DISPOSITION_RECALCULATE`, `DISPOSITION_PRESERVE`) `+ __all__`
- `backend/app/main.py` — `CODE_TO_STATUS`: `POLICY_DISPOSITION_REQUIRED: 400`. The only change
- `backend/app/repositories/models.py` — `+ PolicyChange`
- `backend/app/repositories/leave_type.py` — `+ update_leave_type`
- `backend/app/repositories/leave_balance.py` — `+ list_pairs_for_leave_type` (the pair sweep, `MIN(leave_year)`)
- `backend/app/services/recalculation.py` — `+ recalculate_for_policy_change`; module docstring now covers both commands
- `backend/app/services/leave_types.py` — `+ update_leave_type` (the disposition gate, `_must_recalculate`, the one transaction), `+ LeaveTypeCommandResult`
- `backend/app/api/v1/leave_types.py` — `+ PATCH` (200 + summary), `+ LeaveTypeUpdateRequest`, `+ LeaveTypeCommandResponse`; `Field(ge=0)` on both entitlements
- `backend/app/api/v1/router.py` — `+1 include_router`
- `backend/tests/domain/test_recalculation.py` — `+4` projection tests (the load-bearing non-carrying case)
- `backend/tests/test_scope_matrix.py` — `+ PATCH /leave-types/{leave_type_id}` → `{Scope.ALL}`
- `backend/tests/test_scoped_getters.py` — `+ list_policy_changes`, `+ list_pairs_for_leave_type` (EXEMPT, each with a rationale)
- `backend/tests/test_migrations_insert_nothing.py` — `+ "0011_policy_change.py"`
- `backend/tests/integration/test_migration_smoke.py` — `HEAD_REVISION = "0011_policy_change"`
- `backend/tests/integration/test_schema_1_2.py` — `+ policy_change`

**New — frontend**
- `frontend/src/api/recalculation.ts` — the extracted `RefusedPair` / `RecalculationSummary` types + the invalidation fan-out (6 keys)
- `frontend/src/api/policyChanges.ts` — `usePolicyChanges` (read-only)
- `frontend/src/components/RecalculationSummaryPanel.tsx` — lifted from `HolidaysPage`; `src/components/`' first occupant
- `frontend/src/features/policyChanges/PolicyChangesPanel.tsx` — Admin read screen (Pattern B)

**Modified — frontend**
- `frontend/src/api/holidays.ts` — consumes the extraction; re-exports the moved types
- `frontend/src/api/leaveTypes.ts` — `+ useUpdateLeaveType`, `+ UpdateLeaveTypeInput`, `+ LeaveTypeCommandResult`
- `frontend/src/api/index.ts` — re-exports the new surface
- `frontend/src/features/holidays/HolidaysPage.tsx` — consumes `RecalculationSummaryPanel`
- `frontend/src/features/leaveTypes/LeaveTypesPage.tsx` — `+` the inline policy-edit form (AC10) and the summary (AC11)
- `frontend/src/App.tsx` — `+1` line: `<PolicyChangesPanel />`

**Modified — artifacts**
- `_bmad-output/implementation-artifacts/deferred-work.md` — 5 entries, the first being the reviewer item above
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

**Deliberately NOT changed:** `pyproject.toml` · `services/balances.py` · `services/rollover.py` ·
`domain/carry_forward.py` · `domain/proration.py` · `repositories/admin_review_flag.py` ·
`api/v1/admin_review_flags.py` · `seed/` · `index.css` · `tests/integration/test_audit_entries.py`.

## Change Log

| Date | Version | Description |
|---|---|---|
| 2026-07-14 | 0.1 | Story drafted — context engine pass. Status: ready-for-dev. |
| 2026-07-14 | 1.0 | Implemented. All 12 ACs met; 62 subtasks complete. `policy_change` (migration `0011`, the fourth append-only table, its own `GRANT INSERT, SELECT`, no actor column by decision); `project_forward` taught about proration and its unsound fixed-point break skipped on the policy path (Landmine 1, proved load-bearing); `recalculate_for_policy_change` writes every materialized year itself and triggers AD-6's recomputation as a provable no-op (Landmine 2); a cap/`carries_forward` change runs the forward-checked recomputation under BOTH dispositions (Landmine 3, Open Decision #1); `PATCH /leave-types/{id}` (200 + summary, no breaking change to `POST`) and `GET /policy-changes` (Admin-only); three frontend surfaces incl. the first shared component. backend pytest 505 passed; import-linter 7/7; frontend build+lint clean; seed exit 0. **Ships one KNOWN defect, pinned by a passing test and raised to the reviewer: a pair refused during a cap decrease still detonates a raw 500 in a later unrelated reject.** Status: review. |
