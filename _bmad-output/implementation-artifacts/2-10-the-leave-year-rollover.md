---
baseline_commit: 83096b2
baseline_note: Story 2.9 is `review`, not `done`, and its work is UNCOMMITTED on `main`. Your working tree already contains the owner/app role split, migration `0008_audit_read_surface`, and `GET /api/v1/audit-entries`. Build on it; do not re-derive it.
---

# Story 2.10: The Leave Year Rollover

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Admin,
I want unused Earned Leave to carry forward and lapsing types to lapse at the year boundary,
So that the organization begins each Leave Year with balances that are right.

Implements `FR-07` (carry-forward, lapse, idempotence). *(Citation added by readiness finding F-2, which observed that `FR-07`'s substance lands here while only Story 2.4 cited it — leaving `SM-8`'s per-requirement delivery tracker under-reporting the product's central correctness claim.)*

---

## Orientation: what this story actually is

**This is the first story with no HTTP surface at all.** No endpoint, no router registration, no React screen, no new error code, no new scope-matrix row. The readiness report blesses this explicitly: *"Four stories in Epic 2 — 2.9, 2.10, 2.11, 2.12 — carry no frontend criterion at all. (2.10 is the rollover CLI and correctly has none.)"* If you find yourself writing a route, stop — you have left the story.

It does five things:

1. **Creates `rollover_run`** — the second append-only table (`AD-8`), with the same least-privilege grant `audit_entry` got in 2.9 (`AD-9`). Migration `0009`. *(AC1)*
2. **Ships the CLI job** `python -m app.jobs.rollover --year YYYY` — no scheduler inside FastAPI, no endpoint, directly callable from a test with no server and no clock. `app/jobs/__init__.py` already exists and reserves the module by name. *(AC2, AC9)*
3. **Derives carry-forward, and lapses the rest** — `carried_forward(Y+1) = min(cap, available(Y))` for a type whose `carries_forward` is true, by **assignment**, which is what makes a re-run a no-op. Everything else lapses, decided by **reading the attribute, never by testing the code**. *(AC3, AC4, AC5, AC7)*
4. **Retro-fits the `DR-7a` top-up** into the three existing release paths, so a Pending year-`Y` request rejected *after* the boundary raises `available(Y)` and tops up `carried_forward(Y+1)`. **This is the hard part, and it is not in `jobs/` at all** — it is a hook into code Stories 2.7 and 2.8 already shipped. *(AC6)*
5. **Writes to `rollover_run` and never to `audit_entry`** — because the rollover transitions no Leave Request, and `SM-4`'s one-to-one count must stay literally true. *(AC8)*

**It also silently fixes a live bug.** Story 2.4's code review deferred this, assigned to you by name:

> **Year-rollover cliff — reads go empty and mutations 500 once the calendar year turns.** Balances are materialized only for `date.today().year` at create time; both reads (`balance_reads._current_leave_year`) and mutations hardcode the current year. An Employee whose rows were materialized in a prior year has no current-year row, so `GET /balances` returns empty and any `reserve`/`consume` hits `_lock` → `LookupError` → 500. **The rollover that materializes next-year rows is assigned to Story 2.10**; nothing in 2.4 degrades gracefully in the interim.

So the job is not merely bookkeeping. It is the thing that keeps the application working on 1 January.

---

## Acceptance Criteria

> Verbatim from [epics.md](_bmad-output/planning-artifacts/epics.md#L1237-L1284) §"Story 2.10: The Leave Year Rollover" (lines 1237–1284). BDD blocks numbered AC1–AC9 for task traceability.

**AC1 — `rollover_run` is a table, and append-only is a grant**

**Given** a database migrated by this story
**When** the schema is inspected
**Then** `rollover_run` carries `leave_year` and `occurred_at`, and is append-only
**And** the application's database role is granted `INSERT` and `SELECT` on it and **neither `UPDATE` nor `DELETE`**, with migrations running as the owner (`AD-8`, `AD-9`, `NFR-09`)

**AC2 — a CLI entrypoint, not a scheduler**

**Given** the rollover
**When** it is invoked
**Then** it is the CLI entrypoint `python -m app.jobs.rollover --year YYYY`, called by an external scheduler
**And** no scheduler is registered inside the FastAPI application, and no endpoint triggers it (`AD-7`)

**AC3 — carry-forward is derived and capped**

**Given** a Leave Year `Y` and a Leave Type whose `carries_forward` is true
**When** the rollover runs
**Then** `carried_forward(Y+1) = min(carry_forward_cap, available(Y))`, written by assignment rather than by increment
**And** the excess above the cap lapses (`FR-07`, `AD-6`, `DR-7`)

**AC4 — lapse is decided by the attribute, never by the name**

**Given** a Leave Type whose `carries_forward` is false
**When** the rollover runs
**Then** its unused days lapse
**And** the behaviour was decided by reading the attribute, not by testing the Leave Type's name — `EL` carries forward, `CL` and `FL` lapse (`FR-07`, `DR-11`, `AD-11`)

**AC5 — idempotence, by construction**

**Given** the rollover has already run for a Leave Year
**When** it runs again against the same year
**Then** nothing changes, because it assigns a derived value rather than accumulating one (`AD-6`)

**AC6 — `DR-7a`: Reserved days survive the boundary, and top up when released**

**Given** a Pending request holding Reserved days in Leave Year `Y` across the boundary
**When** it is later rejected or cancelled
**Then** its days do not lapse at the boundary, `available(Y)` rises, and `carried_forward(Y+1)` is recomputed and tops up
**And** approval leaves `available(Y)` unchanged, so carry-forward is never clawed back (`DR-7a`, `AD-6`)

**AC7 — `SM-5`: a fourth Leave Type rolls over with no code change**

**Given** a fourth Leave Type created through `POST /leave-types` with `carries_forward` true
**When** the rollover runs
**Then** its unused days carry forward, with no code change and no schema migration between creating it and rolling it over (`SM-5`)

**AC8 — the rollover is not an Audit Entry**

**Given** the rollover
**When** it records its execution
**Then** it writes to `rollover_run` and never to `audit_entry`, because it transitions no Leave Request and `SM-4`'s one-to-one count must stay true (`AD-8`)

**AC9 — testable with no server and no clock**

**Given** a test
**When** it calls the rollover
**Then** it runs with no server and no clock manipulation (`AD-7`, `NFR-15`)

---

## 🚨 Five landmines. Read these before writing a line.

### Landmine 1 — You cannot write `carried_forward` on its own. The CHECK is not deferrable.

`leave_balance` carries `CHECK (accrued = prorated_entitlement + carried_forward)`, and it is **not deferrable** (`AD-5`). An `UPDATE leave_balance SET carried_forward = 5` fires it mid-statement. The three columns move together or not at all.

The one function that moves them together is [`services/balances.set_accrual`](backend/app/services/balances.py#L277), which computes `accrued` itself from the two parts:

```python
def set_accrual(
    session: Session, *, employee_id: uuid.UUID, leave_type_id: uuid.UUID, leave_year: int,
    prorated_entitlement: int, carried_forward: int, entitlement_basis: int,
) -> None:
    """Materialize or recompute the accrual triple (create-or-update), in ONE statement (AD-17)."""
    accrued = prorated_entitlement + carried_forward
    leave_balance_repo.upsert_accrual(session, ...)   # INSERT … ON CONFLICT DO UPDATE
```

**Resolution: the rollover writes balances through `set_accrual` and through nothing else.** Do not add a ninth balance method — [`tests/test_balances_module_surface.py`](backend/tests/test_balances_module_surface.py) asserts the public surface is **exactly** the eight `AD-17` names and `len(...) == 8`; a ninth fails the build. Do not write a balance column from `jobs/` or from a repository. `set_accrual`'s `ON CONFLICT DO UPDATE` is *also* what gives you AC5 for free: assignment, not accumulation.

### Landmine 2 — `set_accrual`'s DO-UPDATE branch has no `available ≥ 0` guard, and you are the first caller to reach it.

Story 2.4's code review deferred this on an explicit premise that **you are about to invalidate**:

> **`set_accrual` has no `available ≥ 0` guard on its DO-UPDATE branch.** On a recalculation that lowers `accrued` below existing `consumed + reserved`, the `accrued - consumed - reserved >= 0` CHECK fires as a raw 500. `adjust_reserved`/`adjust_consumed` guard this; `set_accrual` does not. **Not reachable in Story 2.4 (materialization is fresh inserts, `reserved=consumed=0`)**; the DO-UPDATE lowering path … belong[s] to Story 2.11/2.12.

Every 2.4 caller inserted a *fresh* row. **You are the first caller that upserts onto a row that may already carry `reserved`/`consumed`** — on an idempotent re-run (AC5) and on every `DR-7a` top-up (AC6).

You are safe **only while `carried_forward` never decreases** — `min(cap, available(Y))` where `available(Y)` only rises (approve leaves it unchanged; reject/cancel raise it). Raising `carried_forward` raises `accrued`, and the CHECK is a floor. On that path it cannot fire.

**Two paths make `carried_forward(Y+1)` *fall*, and both fire the CHECK as a raw 500 if anything is already reserved or consumed in `Y+1`:**
1. **A re-run after an Admin lowered `leave_type.annual_entitlement`** — `prorated_entitlement(Y+1)` drops, so `accrued(Y+1)` drops. That path is `FR-06`'s policy recalculation and belongs to **Story 2.12** (`policy_change`, explicit disposition). Do **not** build a disposition here.
2. **A run against a year that is not yet closed.** `run_rollover(Y)` takes `Y` as a free `int` — AC9 forbids a clock, so nothing stops an operator rolling the *current* year. Roll `--year 2026` in July 2026, then let somebody submit or approve a 2026 request (perfectly legal — only *past* date ranges are refused). `available(2026)` **falls**, and the next run at the real boundary **lowers** `carried_forward(2027)`.

**Resolution — do both:**
- **(a) Add the `available ≥ 0` pre-check to `set_accrual`, and raise the guarded `ValueError` that `adjust_reserved` / `adjust_consumed` already raise.** This is **mandatory**, not a preference. It converts a raw 500 into the codebase's existing guarded failure. No ninth method — you are hardening one of the eight.
  > ⚠️ **The obvious implementation is a trap.** Do **not** reach for the module's own [`_lock()`](backend/app/services/balances.py#L62) helper: it **raises `LookupError` on a missing row**, and `set_accrual` is the *materializer* — its dominant path is a fresh `INSERT` where no row exists. Wiring `_lock` into it breaks **every** existing caller: [`services/employee.py`](backend/app/services/employee.py)'s create hook, [`services/leave_types.py`](backend/app/services/leave_types.py)'s create hook, and `seed/__main__.py`. Call [`leave_balance_repo.lock_balance(...)`](backend/app/repositories/leave_balance.py#L37) directly — it returns `LeaveBalance | None` — and **skip the guard when it returns `None`** (a fresh insert has `reserved = consumed = 0` and cannot violate the floor).
- **(b) State in `run_rollover`'s docstring that `Y` must be a *closed* Leave Year**, and that the scheduler owns that precondition. The job does not police the calendar (it has no clock, by AC9), so it must say what it assumes.

### Landmine 3 — Migration 0008 left you an instruction. Obey it literally.

[`alembic/versions/0008_audit_read_surface.py`](backend/alembic/versions/0008_audit_read_surface.py#L96-L104) contains this note, addressed to this story by name:

> **NOTE — no `ALTER DEFAULT PRIVILEGES`.** It is the obvious way to keep future tables working automatically, and it is wrong here: it would blanket-grant UPDATE and DELETE to every table the owner creates from now on, **INCLUDING Story 2.10's `rollover_run`, which AD-9 requires to be append-only for the same reason `audit_entry` is**. A migration that adds a table must add its grant, deliberately. That is a feature.

So there is **no** inherited grant. Migration `0009` must issue its own, and exactly one shape of it:

```sql
GRANT INSERT, SELECT ON rollover_run TO <app_role>;   -- not UPDATE. not DELETE. This line is AC1.
```

Two ways to get this wrong, both silent:
- **Forget the grant entirely** → the app role has *zero* privilege on the table and the job dies with `InsufficientPrivilege` the first time it runs. (Loud, at least.)
- **Copy 0008's `_READ_WRITE_TABLES` loop** → you grant `UPDATE, DELETE`, AC1 is false, every test still passes, and `NFR-09` is destroyed without a single red mark. **This is the failure mode that matters.**

Copy 0008's `_APPEND_ONLY_TABLES` loop, its `psycopg.sql.SQL/Identifier` quoting, its `_quoted_role()` helper, and its refusal to run in `--sql` offline mode. `0009` chains off `0008` (`down_revision = "0008_audit_read_surface"`).

### Landmine 4 — The rollover must write **zero** audit rows. Two suite-wide tests count them exactly.

AC8 is not a style preference; it is load-bearing for `SM-4`. Story 2.9 shipped a ledger test that pins an **exact total and an exact per-`subject_type` breakdown**:

```python
# tests/integration/test_audit_entries.py:511
assert len(rows) == 14, (
    "SM-4 is one audit row per state transition, counted one-to-one. …")
assert by_type == {
    vocabulary.SUBJECT_LEAVE_REQUEST: 10,
    vocabulary.SUBJECT_CANCELLATION_REQUEST: 4,
}, f"the per-subject_type breakdown is wrong: {by_type}"
```

and [`test_leave_request_decide.py:669`](backend/tests/integration/test_leave_request_decide.py#L669) asserts `_audit_count(request_id)` goes `1 → 2` across a reject and **stays 2** on the refused second reject.

**Your `DR-7a` hook lands inside `_decide` and inside `approve_cancellation_request` — the exact code paths those two tests exercise.** An audit row written by the recompute takes the ledger from 14 to 17 and the decide count from 2 to 3.

**Resolution: the carry-forward recompute writes no `audit_entry` row, and the rollover job writes none either.** There is no `SUBJECT_ROLLOVER` and there must not be one. A balance re-derivation is not a state transition. Story 2.9's Dev Notes say it outright: *"`rollover_run` is Story 2.10's table and is deliberately not part of the audit trail — AD-8 keeps it separate exactly so SM-4's one-to-one count against transitions stays literally true. Do not read it, do not create it, do not fold it into this endpoint."*

### Landmine 5 — Do not touch `[tool.importlinter]`. It is already correct.

`app/jobs/` **already exists** ([`app/jobs/__init__.py`](backend/app/jobs/__init__.py), docstring only) and contract 7 already covers it and is already green:

```toml
[[tool.importlinter.contracts]]
name = "jobs/ never imports api/ (AD-1)"
type = "forbidden"
source_modules = ["app.jobs"]
forbidden_modules = ["app.api"]
```

`app.jobs` is deliberately **absent** from contract 1's `layers` list, so `jobs → services → repositories → domain` is permitted as written. **No `pyproject.toml` change is needed, and any change will fail the build**: [`tests/test_architecture.py:46`](backend/tests/test_architecture.py#L46) pins all seven contracts byte-for-byte in an `expected` dict and asserts `set(contracts) == set(expected), "a contract was added, renamed or lost"`.

Contract 7's comment says the job *"orchestrates through `services/` like any other entrypoint."* Honour that: **`jobs/rollover.py` is a thin CLI shell over `services/rollover.py`.** It parses `--year`, calls one service function, maps exceptions to an exit code. No SQL, no session management, no business rule.

---

## Tasks / Subtasks

> Order matters. Task 1 gives you the table; Task 2 gives you the pure arithmetic you can test with no database; Task 3 is the job's transaction; Task 4 is the CLI shell; **Task 5 is the retro-fit into 2.7/2.8 and is the one most likely to be skipped** — AC6 is not satisfied by the job alone. Task 6 is the test suite. Task 7 is the guard files that will fail the build if you forget them.

### Task 1 — `rollover_run`: the table, the model, the migration, and the grant (AC1)

- [x] Add the `RolloverRun` model to [`backend/app/repositories/models.py`](backend/app/repositories/models.py), next to `AuditEntry`. Columns, per [erd.md §ROLLOVER_RUN](_bmad-output/planning-artifacts/module-4-erd/erd.md#L274-L281) — and **nothing more**:

  | Column | Type | Null | Note |
  | --- | --- | --- | --- |
  | `id` | `uuid` PK | no | `uuidv7()` default, same as every other table |
  | `leave_year` | `INTEGER` | no | The Leave Year **rolled** (the closing year `Y`, not `Y+1`) |
  | `occurred_at` | `TIMESTAMPTZ` | no | The moment. **No `actor` column** — ERD: *"Actor is always `SYSTEM`; no column is needed to say so."* |

  **No `UNIQUE (leave_year)`.** The ERD names none. `rollover_run` is a log of *executions*; a second run against the same year appends a second row and that is correct. Idempotence (AC5) is a property of the **balances**, not of the log. Do not invent a constraint to make the log look tidy — you would turn a legal second run into an `IntegrityError`.

- [x] Write `backend/alembic/versions/0009_rollover_run.py`, with `down_revision = "0008_audit_read_surface"`.
  - [x] `op.create_table("rollover_run", ...)` — schema only. **No `INSERT`.** [`tests/test_migrations_insert_nothing.py`](backend/tests/test_migrations_insert_nothing.py)'s `_DataMutationVisitor` fails the build on any `INSERT` / `UPDATE … SET` / `DELETE FROM` / `bulk_insert` / `insert()` inside a migration (`AD-11`).
  - [x] Refuse `--sql` offline mode, exactly as 0008 does (it needs a live connection to resolve the role name):
    ```python
    if context.is_offline_mode():
        raise RuntimeError(_OFFLINE_REFUSAL)
    ```
  - [x] Issue the grant — **`INSERT, SELECT`, and nothing else** (Landmine 3):
    ```python
    op.execute(
        sql.SQL("GRANT INSERT, SELECT ON {table} TO {role}")
        .format(table=sql.Identifier("rollover_run"), role=role).as_string()
    )
    ```
    **Exactly that. Nothing else.** No `GRANT USAGE ON SCHEMA` (0008 issued it), no `GRANT ... ON ALL SEQUENCES` (0008 issued it, and `uuidv7()` uses no sequence anyway). Copying either is the copy-paste noise Landmine 3 is about.
  - [x] **`_quoted_role()` is module-private to 0008 and cannot be imported across revisions** — Alembic revisions are not a package. **Re-declare it in 0009**, which means re-declaring its imports too: `from alembic import context`, `from psycopg import sql`, `from app.core.settings import get_settings` (0008 reads `get_settings().app_db_user`). "Reuse 0008's pattern" means *copy the shape*, not `from ... import`.
  - [x] `downgrade()` drops the table. The role itself is 0008's to drop, not yours.
- [x] Verify `alembic upgrade head` → `downgrade -1` → `upgrade head` is clean and idempotent, and that `alembic check` produces an empty diff. [`tests/integration/test_model_migration_agreement.py`](backend/tests/integration/test_model_migration_agreement.py) runs `alembic check` **inside the suite** — a model without its migration fails `pytest`.

### Task 2 — `domain/carry_forward.py`: the pure arithmetic (AC3, AC4)

- [x] Create `backend/app/domain/carry_forward.py`. One pure function, stdlib only, no ORM, no clock, no I/O (`AD-1`, contract 3 forbids `sqlalchemy`/`psycopg`/`fastapi` in `app.domain`). Model it on [`domain/proration.py`](backend/app/domain/proration.py).

  ```python
  def carry_forward_days(
      *, available: int, carries_forward: bool, carry_forward_cap: int | None
  ) -> int:
      """The days a Leave Type carries into the next Leave Year (DR-7, AD-6).

      Reads the ATTRIBUTE, never the Leave Type's code (AD-11, DR-11): `carries_forward` first,
      and only then the cap. A lapsing type carries nothing, whatever its cap says — the cap is
      meaningless when `carries_forward` is false (ERD §"Not a gap"), which is why it is nullable.
      """
  ```

  Rules, in order:
  1. `carries_forward is False` → **`0`**. The days lapse. Never consult the cap. (AC4)
  2. `carry_forward_cap is None` → **`available`**. Uncapped. (See Open Decision #2 — this is the one genuinely under-determined point in the story, and this is the reading you are to implement.)
  3. otherwise → **`min(carry_forward_cap, available)`**. The excess lapses. (AC3)
  4. `available` is never negative (`AD-5`'s CHECK guarantees it), but clamp at `0` anyway — a `max(0, ...)` costs nothing and makes the function total.

- [x] **The function must not receive a Leave Type code, and must not have one in scope.** AC4's *"decided by reading the attribute, not by testing the Leave Type's name"* is a code-review criterion, and the cheapest way to make it unfalsifiable is to give the function no way to know the name. Pass `carries_forward` and `carry_forward_cap`, never the `LeaveType`.
- [x] Tests in `backend/tests/domain/test_carry_forward.py` — **no database fixture** (`NFR-15`). `tests/domain/conftest.py` defines no fixtures at all, deliberately, and pytest cannot reach the integration one. Cover: carrying under the cap; carrying over the cap (excess lapses); cap exactly equal to available; lapsing type with a cap set (still `0` — this is the AC4 test); lapsing type with a NULL cap; carrying type with a NULL cap (uncapped); `available == 0`.

### Task 3 — `services/rollover.py`: the job's transaction (AC3, AC4, AC5, AC7, AC8)

- [x] Create `backend/app/services/rollover.py`. Two public functions:

  ```python
  def run_rollover(leave_year: int) -> RolloverSummary:
      """Close Leave Year `Y` and open `Y+1`. The CLI's one call (AD-7)."""

  def recompute_carry_forward(
      session: Session, *, employee_id: uuid.UUID, leave_type_id: uuid.UUID, leave_year: int
  ) -> None:
      """Re-derive carry-forward FORWARD from `leave_year`, on an OPEN session (DR-7a, AD-6).
      Task 5's hook. Takes the caller's session; opens no transaction of its own (AD-3)."""
  ```

- [x] **`run_rollover(Y)` semantics, pinned:** `--year Y` **closes** `Y` and **materializes** `Y+1`. `rollover_run.leave_year = Y` — the ERD says the column is *"The Leave Year rolled"*, and the year you rolled is the one you closed. Every AC is phrased `available(Y)` → `carried_forward(Y+1)`. Be consistent; a reader must never have to guess which end `--year` names.

- [x] The transaction. One `Session(get_engine(), expire_on_commit=False)`, one `commit()` at the end, matching the house pattern at [`services/leave_requests.py:480`](backend/app/services/leave_requests.py#L480).

- [x] **There is no shared clock module, and `_now()` is not in scope.** Each service defines its own privately ([`leave_requests.py:239`](backend/app/services/leave_requests.py#L239), [`cancellation.py:140`](backend/app/services/cancellation.py#L140)), both `datetime.datetime.now(datetime.timezone.utc)`. Define the same private `_now()` in `services/rollover.py`. `occurred_at` is `TIMESTAMPTZ` — **a naive datetime is a defect**, not a nit.

- [x] **There is no public reader for `available(Y)`, and you must not invent one.** `balances._available()` is private; `balance_reads.get_balance` demands an `actor` and a `Scope` the job has no business holding (a cron job is not a person). **Read the row with `leave_balance_repo.lock_balance(...)` and compute `accrued − consumed − reserved` inline.** Do not import `balances._available`, do not reach into `balance_reads`, and do not add a getter to make this feel tidier.

  For each `(employee, leave_type)` pair — reuse [`repositories/employee.all_employees`](backend/app/repositories/employee.py#L159) and [`repositories/leave_type.all_leave_types`](backend/app/repositories/leave_type.py#L54), the two unpaginated helpers Story 2.4 built for exactly this kind of write-path loop:

  1. `lock_balance(session, employee_id=…, leave_type_id=…, leave_year=Y)`. It returns `LeaveBalance | None` — it does **not** raise. `available(Y) = accrued − consumed − reserved`.
  2. `carried = carry_forward_days(available=..., carries_forward=lt.carries_forward, carry_forward_cap=lt.carry_forward_cap)` — Task 2's pure function.
  3. `prorated = prorate_entitlement(lt.annual_entitlement, employee.joining_date, Y + 1)` — [`domain/proration.py`](backend/app/domain/proration.py). For anyone who joined before `Y+1` this returns the full `annual_entitlement`; proration applies once, at the first materialized year.
  4. `balances.set_accrual(session, employee_id=…, leave_type_id=…, leave_year=Y + 1, prorated_entitlement=prorated, carried_forward=carried, entitlement_basis=lt.annual_entitlement)`.

  **Do not read or write `reserved`/`consumed` on the `Y+1` row.** `set_accrual`'s DO-UPDATE branch leaves them untouched, which is precisely what makes a re-run a no-op even after somebody has already booked leave in `Y+1`.

- [x] **The missing-year-`Y`-row case.** Story 2.4 left a hole: a concurrent Employee-create / Leave-Type-create can leave a pair with no balance row at all. Your loop will meet it. **Treat a missing year-`Y` row as `available(Y) = 0`, and still materialize `Y+1`.** That heals the year-rollover cliff for that pair instead of propagating the hole forward. Do not raise, do not skip. (Open Decision #4.)

- [x] Insert exactly one `rollover_run` row — `leave_year=Y`, `occurred_at=_now()` — in the **same transaction** as every `set_accrual`. If the transaction rolls back, the run did not happen and there is no row saying it did (`AD-8`'s "because" clause, the same one 2.9 proved for `audit_entry`).
- [x] **Zero `audit_entry` rows** (Landmine 4). Do not import `audit_entry_repo` in this module. Its absence is the proof.
- [x] Add `backend/app/repositories/rollover_run.py` with **one** public function, `insert_rollover_run(session, *, leave_year, occurred_at) -> None` — `add()` + `flush()`, never `commit()`. One repository module per table (2.9's rule). **Give it no getter.** No AC asks to read the table, and a `list_rollover_runs` would drag in the scoped-getter exemption dance for nothing (Open Decision #5).

### Task 4 — `app/jobs/rollover.py`: the CLI shell (AC2, AC9)

- [x] Create `backend/app/jobs/rollover.py`. Copy the shape of [`backend/seed/__main__.py`](backend/seed/__main__.py) — `configure_logging()`, `main() -> int`, typed exceptions → `logger.error` → `return 1`, `sys.exit(main())` under `if __name__ == "__main__":`. Seed's module docstring already declares the two are mirrors: *"Mirrors the shape of `python -m app.jobs.rollover`, the other CLI entrypoint the spine calls for (AD-7)."*
- [x] Seed takes no arguments, so **`argparse` is new**. Add exactly one required option, `--year`, typed `int`. Reject a year that is absurd (a four-digit sanity range is enough) with a legible message and exit `1`, not a traceback.
- [x] Catch `OperationalError` ("is the stack up?") and `ValidationError` ("your `.env` is incomplete") the way seed does, and return `1`. An *unanticipated* exception still tracebacks — that is a bug here, not an operator error.
- [x] `main()` calls `services.rollover.run_rollover(year)` and **nothing else**. No SQL in this file. No `Session`. Log the summary it returns.
- [x] **Never call `date.today()` to default the year.** `--year` is required. AC9's "no clock manipulation" is satisfied by making the year an argument — a test passes `2026` and no clock is mocked anywhere. (`AD-1`: the clock lives in the shell, and here the shell is the operator.)
- [x] Confirm no scheduler exists in [`app/main.py`](backend/app/main.py) and that you added none. No `@app.on_event`, no `APScheduler`, no `BackgroundTasks`. No router. (AC2)

### Task 5 — The `DR-7a` retro-fit into Stories 2.7 and 2.8 (AC6) ⚠️ **the one that gets skipped**

**AC6 is not satisfied by the job.** The rollover runs once, in January. A year-`Y` Pending request rejected in February must top up `carried_forward(Y+1)` *then* — and the code that rejects it shipped in Story 2.7 and knows nothing about carry-forward.

**There are exactly three sites where `available(Y)` rises.** Hook all three, and only these three:

| Site | File | Mutator | Hook? |
| --- | --- | --- | --- |
| Reject a Pending request | [`services/leave_requests.py:553`](backend/app/services/leave_requests.py#L553) (via `_decide`) | `release_reserved` | **YES** |
| Applicant cancels own Pending request | [`services/leave_requests.py:575`](backend/app/services/leave_requests.py#L575) (via `_decide`) | `release_reserved` | **YES** |
| Admin approves a Cancellation Request | [`services/cancellation.py:307`](backend/app/services/cancellation.py#L307) | `release_consumed` | **YES** |
| **Approve** a Pending request | `services/leave_requests.py` (via `_decide`) | `consume_reserved` | **NO — AC6 forbids it** |
| **Reject** a Cancellation Request | `services/cancellation.py` | *(none)* | **NO — the LR is untouched** |

- [x] **Approve must not recompute.** `consume_reserved` moves `reserved → consumed` and leaves `available` **unchanged** by construction, so the derived carry-forward is already correct. AC6: *"approval leaves `available(Y)` unchanged, so carry-forward is never clawed back."* A recompute wired into `_decide` unconditionally fires on approve too — technically a no-op today, but it makes the clawback-safety an accident of arithmetic rather than a decision. Wire it **conditionally**: add a keyword-only `recompute_carry_forward: bool = False` to `_decide`, and pass `True` from `reject_leave_request` and `cancel_leave_request` only.
- [x] Call `rollover.recompute_carry_forward(session, ...)` **after** the balance mutator and **before** `session.commit()`, on the caller's open session. Same transaction: the release and the top-up are one atomic fact.

- [x] 🚨 **Pass `leave_year=row.start_date.year`. There is a wrong helper sitting right next to you.** [`services/leave_requests.py:229`](backend/app/services/leave_requests.py#L229) defines `_current_leave_year()` → `date.today().year`, and it is *already imported into the module you are editing*. It is the natural-looking thing to reach for and it is **wrong**: it silently breaks AC6 in **exactly AC6's motivating scenario** — a year-`Y` request rejected during year `Y+1` would recompute forward from `Y+1` instead of `Y`, and the top-up that the entire story exists to deliver would never fire. The mutator two lines above you already uses `row.start_date.year` ([`leave_requests.py:498`](backend/app/services/leave_requests.py#L498), [`cancellation.py:311`](backend/app/services/cancellation.py#L311)). **Use the same value it did.** A request never spans two Leave Years (`DR-6`), so `start_date.year` *is* the request's Leave Year, unambiguously.
- [x] **`recompute_carry_forward` propagates forward through every materialized later year** (`AD-6`: *"Recomputation propagates forward through every materialized later year"*). Loop `y = Y+1, Y+2, …` **while a balance row exists** for `(employee, leave_type, y)`; for each, re-derive `carried_forward(y)` from `available(y-1)` and `set_accrual` it. Stop at the first year with no row. Raising `carried_forward(Y+1)` raises `available(Y+1)`, which can raise `carried_forward(Y+2)` — a two-boundary-old Pending request is legal (`erd.md §7`: no bound on how long a request may stay Pending).
- [x] **The existence of the `Y+1` balance row is your "did the rollover run?" signal.** Do **not** query `rollover_run` to decide whether to recompute. If no `Y+1` row exists, the rollover has not run and there is nothing to top up — the loop does zero iterations and the hook costs one indexed lookup. This is why `rollover_run` needs no getter (Landmine 4's corollary, and Open Decision #5).
- [x] **Preserve `prorated_entitlement` and `entitlement_basis` on the recompute.** You are re-deriving *carry-forward*, not re-prorating. Read the existing `y` row, pass its `prorated_entitlement` and `entitlement_basis` back to `set_accrual` unchanged, and change only `carried_forward`. Re-running proration here would quietly overwrite a policy figure this story has no business touching.
- [x] **Lock order.** `AD-3` locks balance rows ascending by `(employee_id, leave_type_id, leave_year)`. You touch `Y` (already locked by the mutator) then `Y+1`, then `Y+2` — ascending, which is the sanctioned order. Do not walk backwards.
- [x] **Zero audit rows** (Landmine 4). The recompute writes none.

### Task 6 — Tests (AC1–AC9)

> 🚨 **The year under test is not free. Roll `date.today().year`.**
> Story 2.4's create hooks materialize balances for **`date.today().year` and no other year** ([`services/employee.py`](backend/app/services/employee.py), [`services/leave_types.py`](backend/app/services/leave_types.py), `seed`). So in an integration test the *only* year that has balance rows is the current calendar year. A test that hardcodes `run_rollover(2026)` is correct only while today is 2026: on 1 January 2027 every `carried_forward` assertion in this file **silently degrades into a test of Open Decision #4's missing-row path and passes against zeroes**. Use `run_rollover(datetime.date.today().year)` and derive `Y + 1` from it. This is not clock manipulation (AC9 forbids *mocking* a clock, not reading one in a test to pick a fixture year) — it is the coupling that makes the fixtures exist at all.

- [x] `backend/tests/domain/test_carry_forward.py` — DB-free, per Task 2. (AC3, AC4, AC9)
- [x] **AC2 — the guard, not an eyeball.** Every other invariant in this codebase has a mechanical test (`test_architecture`, `test_scope_matrix`, `test_scoped_getters`, `test_migrations_insert_nothing`); AC2's "no scheduler, no endpoint" currently has none. Add one: assert no route in `app.routes` has `rollover` in its path, and that `app.router.on_startup` and `app.router.on_shutdown` are **empty**. Two asserts. Without it, AC2 is enforced by nothing but your good intentions, and the next story that adds a startup hook will never know it broke it.
- [x] `backend/tests/integration/test_rollover.py` — build a `_World` fixture on the house pattern ([`test_audit_entries.py:86`](backend/tests/integration/test_audit_entries.py#L86)): `db_connection` + `owner_engine`, a Department, Employees, and Leave Types created through `leave_types_service.create_leave_type(...)` so Story 2.4's hook materializes the balances for you. **Your teardown must delete `rollover_run` rows through `owner_engine`** — the app role cannot delete them, and a test that tries gets `InsufficientPrivilege`, which is the guarantee working, not a bug.
  - [x] **AC3** — carrying type, `available(Y)` above the cap → `carried_forward(Y+1) == cap`, and the excess is gone. Then a second world where `available(Y)` is below the cap → `carried_forward(Y+1) == available(Y)`.
  - [x] **AC4** — a `carries_forward=False` type **with a cap set** → `carried_forward(Y+1) == 0`. The cap being set is the point: it proves the attribute decided, not the cap and not the code.
  - [x] **AC5 — idempotence.** Run the rollover, snapshot every `leave_balance` row (all six columns), run it **again** against the same year, and assert the rows are **byte-identical**. Assert `rollover_run` now has **two** rows (a run happened twice; the log is honest about that) while the balances did not move. This is the assertion that proves "assignment, not accumulation".
  - [x] **AC6 — the `DR-7a` top-up.** The story's centrepiece. Submit a Pending request in year `Y` (reserving days) → run the rollover for `Y` → assert `carried_forward(Y+1)` reflects the *reduced* `available(Y)` (the reserved days are **not** carried, and have **not** lapsed) → then **reject** it → assert `available(Y)` rose **and** `carried_forward(Y+1)` topped up to match. Then a second case: submit, roll over, **approve** → assert `carried_forward(Y+1)` is **unchanged** (no clawback). Then a third: an Approved request cancelled via an approved Cancellation Request (`release_consumed`) → assert the top-up fires there too.
  - [x] **AC7 — `SM-5`.** Create a **fourth** Leave Type through the live `POST /api/v1/leave-types` endpoint (not a direct insert — the AC says "created through `POST /leave-types`") with `carries_forward=true` and a cap. Run the rollover. Assert its unused days carried forward. **No code change, no migration** between the two. This is a success-metric test; make its name say `sm_5`.
  - [x] **AC8 — no audit rows.** Snapshot `SELECT count(*) FROM audit_entry` before and after a rollover run and assert it is **unchanged**. Then assert `rollover_run` gained its row. Two asserts, one test, and it is the only thing standing between you and a silently broken `SM-4`.
  - [x] **AC1 — the grant is real.** Connect as the **app** role (`get_engine()`) and prove `UPDATE rollover_run` and `DELETE FROM rollover_run` are both refused with `psycopg.errors.InsufficientPrivilege`. Assert `INSERT` and `SELECT` succeed. Copy 2.9's test for `audit_entry` verbatim in shape — it is the only test that actually verifies AC1, because a schema inspection cannot see a missing grant.
  - [x] **AC9 — no server, no clock.** Every test above calls `run_rollover(2026)` **directly** as a Python function. No `TestClient` for the job, no `freezegun`, no monkeypatched `date.today`. If you needed to mock a clock, the year is not a parameter and AC2 is wrong.
- [x] Confirm the full backend suite still passes. Baseline is **405 passed** (Story 2.9). Confirm `lint_imports()` still reports **7/7** contracts.

### Task 7 — The guard files that will fail the build if you forget them

These are not optional and they are not tests you are writing — they are existing guards that pin facts you are about to change.

- [x] [`tests/test_migrations_insert_nothing.py`](backend/tests/test_migrations_insert_nothing.py) — `test_the_migration_history_is_the_expected_ordered_chain` asserts the **exact ordered filename list**. Append `0009_rollover_run.py`.
- [x] [`tests/integration/test_migration_smoke.py`](backend/tests/integration/test_migration_smoke.py) — bump `HEAD_REVISION` (line 22) to `0009_rollover_run`. It is load-bearing twice: it also drives `test_alembic_version_exists_and_is_stamped_at_head`, so this is not a cosmetic constant. Add a column-set smoke assertion for `rollover_run` — the per-table smokes assert an **exact set**, so it must be `{"id", "leave_year", "occurred_at"}`. **The ERD table lists no `id`** (it lists only the two attributes); every table in this codebase has a `uuidv7()` primary key and `rollover_run` is no exception. A dev who transcribes the ERD literally writes a two-element set and fails the build.
- [x] [`tests/integration/test_schema_1_2.py`](backend/tests/integration/test_schema_1_2.py) — add `rollover_run` to the expected-tables set.
- [x] [`tests/integration/conftest.py`](backend/tests/integration/conftest.py) — no change expected, but confirm `owner_engine` is what your teardown uses.
- [x] **`app/domain/vocabulary.py`** — you should need **no new constant**. There is no new status, no new reason, no new subject type, no new error code. If you find yourself adding one, re-read AC8 and Landmine 4 first. *(If you do add one: it must live in `vocabulary.py` and its `__all__`, or [`tests/test_vocabulary_literals.py`](backend/tests/test_vocabulary_literals.py) fails the build — its scan covers `app/jobs/`.)*
- [x] **`pyproject.toml`** — no change (Landmine 5).
- [x] **`app/api/v1/router.py`** — no change. No endpoint.
- [x] **Frontend** — no change. Confirm you touched nothing under `frontend/`.

---

## Dev Notes

### The one-paragraph mental model

Carry-forward is **not a quantity you move**. It is a **derived figure you re-assign** whenever its inputs change — and its only input is `available(Y)`. The rollover is therefore not a transfer; it is the first *evaluation* of `carried_forward(Y+1) = min(cap, available(Y))`. Everything follows from that. Idempotence is free, because assigning a derived value twice assigns the same value. `DR-7a` is not a special case, it is the **same formula fired again** when `available(Y)` moves. Approve doesn't fire it because approve doesn't move `available(Y)`. And the whole thing lives in `set_accrual` because the `accrued = prorated + carried` CHECK forbids writing `carried_forward` alone. If you catch yourself writing `carried_forward += ...`, you have written the bug this design exists to prevent.

### Reuse map — everything you need already exists

| Need | Reuse (exact) | Source |
| --- | --- | --- |
| Write the accrual triple | `services.balances.set_accrual(session, *, employee_id, leave_type_id, leave_year, prorated_entitlement, carried_forward, entitlement_basis)` | [balances.py:277](backend/app/services/balances.py#L277) |
| Read a balance under lock | `repositories.leave_balance.lock_balance(session, *, employee_id, leave_type_id, leave_year)` — takes no `actor`, so it is not a scoped-getter candidate | [leave_balance.py:37](backend/app/repositories/leave_balance.py#L37) |
| Proration for `Y+1` | `domain.proration.prorate_entitlement(annual_entitlement, joining_date, leave_year)` — pure, no clock | [proration.py](backend/app/domain/proration.py) |
| Every employee | `repositories.employee.all_employees(session)` — unpaginated, no read-verb prefix, built for write-path loops | [employee.py:159](backend/app/repositories/employee.py#L159) |
| Every leave type | `repositories.leave_type.all_leave_types(session)` | [leave_type.py:54](backend/app/repositories/leave_type.py#L54) |
| The engine (app role) | `repositories.engine.get_engine()` | [engine.py](backend/app/repositories/engine.py) |
| CLI shell shape | `seed/__main__.py` — `configure_logging()`, `main() -> int`, typed-exception → `logger.error` → `1` | [seed/\_\_main\_\_.py](backend/seed/__main__.py) |
| Migration grant + role quoting | `0008_audit_read_surface.py` — `_quoted_role()`, `psycopg.sql.Identifier`, offline refusal | [0008](backend/alembic/versions/0008_audit_read_surface.py) |
| Append-only refusal test | 2.9's `InsufficientPrivilege` test for `audit_entry` | [test_audit_entries.py](backend/tests/integration/test_audit_entries.py) |
| Integration `_World` fixture | `test_audit_entries.py:86` | [test_audit_entries.py:86](backend/tests/integration/test_audit_entries.py#L86) |

**You should be adding seven files (four source, one migration, two test) and editing eight.** If your file list is much longer, you have reinvented something above.

### What is already true, and must stay true

- **The app role exists and the engine already uses it.** Story 2.9 shipped `leaveflow_app` (NOSUPERUSER), `settings.app_database_url` vs `settings.database_url`, `engine.get_engine()` → app role, `alembic/env.py` → owner. **There is deliberately no `get_owner_engine()`** and you must not add one: 2.9's engine docstring says *"the application has no legitimate use for one, and offering it would put the bypass one import away."* The rollover is an application job. It runs as the app role. That is why the grant in Task 1 is load-bearing rather than ceremonial.
- **`services/balances.py` exposes exactly eight public callables** and a test enforces the count. `set_accrual` is one of them and is the only one you need.
- **Balance mutators never open a transaction.** They take the caller's `Session` (`AD-3`). `recompute_carry_forward` follows the same rule — it is called from inside 2.7's and 2.8's open transactions.
- **Repositories `flush()`, never `commit()`.** The service commits, once.
- **`flush()` assigns the `uuidv7()` id**, so the same transaction can reference a row it just inserted.
- **One repository module per table.** A `repositories/rollover.py` sitting beside `repositories/rollover_run.py` is the kind of "route around the guard" move 2.9 explicitly forbade.

### Gotchas this codebase has actually produced (from the 2.4 / 2.6 / 2.7 / 2.8 / 2.9 reviews)

- **The equality CHECK is not deferrable.** It has already bitten. Write the triple in one statement or watch it fire mid-transaction.
- **`_lock` raises `LookupError` on a missing row → a raw 500.** Your loop *will* meet pairs with no year-`Y` row (2.4's concurrent-create hole). Handle it (Task 3) rather than discovering it.
- **`occurred_at` ties are real.** Two rows written from one `_now()` share a timestamp exactly. If you ever order `rollover_run`, order by `occurred_at DESC, id DESC`. (You have no getter, so you probably never will — but the teardown query is not exempt from reality.)
- **Integration tests skip loudly, they do not silently pass.** If the app role cannot connect, `conftest` skips with the fix (`alembic upgrade head`). Do not "fix" a skip by weakening a grant.
- **`alembic check` runs inside `pytest`.** Model and migration ship in the same commit or the suite is red.
- **The suite is the build.** No CI, no ruff, no mypy. `pytest` from `backend/` with the venv is the whole gate — and `lint_imports()` runs inside it.

### Project Structure Notes

**New files (4):**
- `backend/app/domain/carry_forward.py` — the pure `carry_forward_days`. No ORM, no clock.
- `backend/app/services/rollover.py` — `run_rollover(year)` and `recompute_carry_forward(session, …)`.
- `backend/app/repositories/rollover_run.py` — `insert_rollover_run` and nothing else.
- `backend/app/jobs/rollover.py` — the argparse CLI shell. (`app/jobs/__init__.py` already exists.)
- `backend/alembic/versions/0009_rollover_run.py` — table + `GRANT INSERT, SELECT`.
- `backend/tests/domain/test_carry_forward.py`, `backend/tests/integration/test_rollover.py`.

**Modified files (expected):**
- `backend/app/repositories/models.py` — `RolloverRun`.
- `backend/app/services/leave_requests.py` — the conditional `DR-7a` hook in `_decide` + the two callers.
- `backend/app/services/cancellation.py` — the `DR-7a` hook after `release_consumed`.
- `backend/app/services/balances.py` — Landmine 2's mandatory `available ≥ 0` guard on `set_accrual`. No new public function. **This changes shared behaviour for three existing callers** — `services/employee.py`'s create hook, `services/leave_types.py`'s create hook, and `seed/__main__.py` — so re-run `tests/integration/test_balances_materialization.py` and the seed before you call it done.
- `backend/tests/test_migrations_insert_nothing.py`, `backend/tests/integration/test_migration_smoke.py`, `backend/tests/integration/test_schema_1_2.py` — the guards.

**Untouched, deliberately:** `app/api/**` (no endpoint), `app/main.py` (no scheduler), `frontend/**` (no criterion), `pyproject.toml` (contracts are correct), `app/domain/vocabulary.py` (no new enumerated string).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#L1237-L1284] — Story 2.10's nine acceptance criteria, verbatim above.
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-6] — *"`carried_forward(Y+1) = min(leave_type.carry_forward_cap, available(Y))`, computed from year Y's live balance and written by assignment, never by increment. It is recomputed on **every** event that can change its inputs… Recomputation propagates forward through every materialized later year. Under request transitions alone, approval transfers Reserved to Consumed and leaves Available unchanged, so `available(Y)` only rises and carry-forward only tops up. The rollover assigns derived values and is therefore idempotent by construction."*
- [Source: ARCHITECTURE-SPINE.md#AD-7] — *"The rollover is a CLI entrypoint, `python -m app.jobs.rollover --year YYYY`, invoked by an external scheduler. No scheduler is registered inside the FastAPI application. The job is directly callable from a test with no running server and no clock manipulation."*
- [Source: ARCHITECTURE-SPINE.md#AD-8] — *"The rollover writes to `rollover_run`, a separate append-only table."* And architecture.md: *"Had rollover rows been written into `audit_entry`, **`SM-4` would have been false the day it was written**."*
- [Source: ARCHITECTURE-SPINE.md#AD-9] — *"The application's database role is granted `INSERT` and `SELECT` on `audit_entry` **and `rollover_run`**, and is granted neither `UPDATE` nor `DELETE`. Alembic migrations run under the owner role."*
- [Source: ARCHITECTURE-SPINE.md#AD-17] — *"`set_accrual` writes `accrued`, `prorated_entitlement` and `carried_forward` in one statement (AD-5). No route, repository, job, or other service writes these columns."*
- [Source: prds/prd-LeaveFlow-2026-07-09/prd.md#DR-7] — *"**'Unused Accrued days' means Available** — `Accrued − Consumed − Reserved` — measured whenever the value is computed, not at the boundary alone. Because a Pending Leave Request's Reserved days survive the boundary (`DR-7a`), Carry-Forward is recomputed whenever the closing Leave Year's balance changes. It may therefore *increase* after the boundary, when such a request is rejected or cancelled. No Leave Request state transition ever decreases it."*
- [Source: prd.md#DR-7a] — *"Reserved days held by a Pending Leave Request do not lapse at the Leave Year boundary. They remain reserved against the Leave Year the request belongs to until it is approved, rejected, or cancelled."*
- [Source: prd.md#DR-8] — *"The Leave Year is the calendar year, 1 January to 31 December."* (Not configurable. Formerly assumption `A-09`.)
- [Source: prd.md#DR-11] — *"Annual Entitlement, Carry-Forward, Carry-Forward Cap… are attributes of a Leave Type, stored as data and read at runtime. No cap value and no entitlement value is fixed in code."*
- [Source: prd.md#SM-5] — *"a fourth Leave Type is added through configuration, is applied for, reserved, approved, and rolled over at the Leave Year boundary, with no code change and no schema migration."*
- [Source: module-4-erd/erd.md#L274-L281] — `ROLLOVER_RUN`: `leave_year` (*"The Leave Year rolled"*), `occurred_at` (*"The moment. Actor is always `SYSTEM`; no column is needed to say so."*). *"Separate from `audit_entry` so that `SM-4`'s one-to-one count against transitions stays literally true."*
- [Source: erd.md#L458-L460] — *"`carry_forward_cap` on a lapsing Leave Type — Meaningless when `carries_forward` is false, and nullable for that reason. `DR-7` reads the `carries_forward` attribute first; the cap is never consulted for CL or FL."*
- [Source: module-1-business-analysis/non-functional-requirements.md#NFR-15] — *"Proration, carry-forward, the year boundary, the weekend-and-holiday day count, and the authorization scope are unit-tested."*
- [Source: implementation-readiness-report-2026-07-10.md#L554] — *"(2.10 is the rollover CLI and correctly has none.)"* — the frontend criterion is absent by design, not by omission.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — the year-rollover cliff, assigned to this story; and the ungated `set_accrual` DO-UPDATE branch (Landmine 2).

---

## Open Decisions (decide during dev; keep consistent across code and tests, and record the call in the Dev Agent Record)

**#1 — `--year Y` closes `Y` and opens `Y+1`.** The ACs all read `available(Y) → carried_forward(Y+1)`, and the ERD calls the column *"the Leave Year rolled"* — the year you rolled is the year you closed. So `--year 2026` reads 2026's balances and materializes 2027's, and writes `rollover_run(leave_year=2026)`. **Recommendation: adopt as written.** The architecture's example (`--year 2027`, invoked by cron) is ambiguous in isolation; do not let it talk you into the other reading. Say which you chose in a docstring, once, plainly.

**#2 — A NULL `carry_forward_cap` on a type whose `carries_forward` is true means uncapped.** This is **the one genuinely under-determined point in the specification.** The ERD says the cap is *"meaningless when `carries_forward` is false"* and is nullable for that reason; no document says what a NULL cap means on a type that *does* carry. `AD-6`'s `min(cap, available)` is simply undefined for NULL. **Recommendation: treat NULL as no ceiling (`carried_forward = available`).** It is the reading `min()` degenerates to, and the alternative (NULL means zero) would make a carrying type silently lapse everything — a wrong balance that will be believed, which is the exact failure PRD §1 exists to prevent. Seed's EL has a cap of 30, so no seeded type exercises this. **Flag it in the Dev Agent Record so a reviewer sees the call was made deliberately.**

**#3 — Deactivated Employees are rolled over like anyone else.** Their balances are still their record, `is_active` gates *authentication*, not accrual, and a reactivated Employee with a hole in their balance history is a support ticket. **Recommendation: iterate every Employee, active or not.** Cheap, and the alternative needs a rule nobody wrote.

**#4 — A pair with no year-`Y` balance row is materialized with `carried_forward = 0`, not skipped.** 2.4's concurrent-create hole can leave one. Treating missing as `available(Y) = 0` heals the pair going forward instead of propagating the gap. **Recommendation: adopt.** Log a warning naming the pair — an operator should know a row was missing, even though the job did the right thing.

**#5 — No endpoint, and no getter on `rollover_run`.** No AC asks to read the table. Adding `GET /rollover-runs` would pull in the scope matrix, `require_role`, an api-contracts entry, and the scoped-getter exemption — all for a read nobody requested. **Recommendation: ship none.** The `DR-7a` hook decides "has the rollover run?" by asking whether the `Y+1` balance row exists, which it needs to read anyway. If a reviewer wants the read surface, it is a clean follow-up story.

**#6 — `rollover_run` gets no `UNIQUE (leave_year)`.** A second run is legal (AC5 requires it to be a no-op, not an error) and appends a second row. The log records executions, not years. **Recommendation: no constraint.** Assert the two-row outcome in the idempotence test so the decision is visible.

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (1M context) — `claude-opus-4-8[1m]`.

### Debug Log References

- Backend suite: **436 passed** (baseline 405, +31 new), 0 skipped, 0 regressions. `lint_imports` **7/7 contracts kept** (contract 7 "jobs/ never imports api/" green as written — no `pyproject.toml` change).
- Migration verified `upgrade head` → `downgrade -1` → `upgrade head`, clean and idempotent. `alembic check` reports an empty diff (model ⇄ migration agree).
- CLI driven end-to-end against the live stack: `python -m app.jobs.rollover --year 2026` → exit 0, *"Leave Year 2026 closed, 2027 opened. 280 balance rows written (40 Employees × 7 Leave Types); 117 had no 2026 row and were materialized from zero."* Exit codes: success `0`, absurd `--year 20226` → `1` (legible message, no traceback), missing `--year` → `2` (argparse).
- **Real-database idempotence**: ran the rollover a second time against the same year and snapshotted all six quantity columns of every one of the **443** `leave_balance` rows — **byte-identical**, with `rollover_run` at 2 rows. Manual verification artifacts (the 2027 rows and the run log) were then deleted as the owner, leaving the dev database as found.
- **The AC6 tests were proven non-vacuous**: with the DR-7a hook temporarily disabled, the three top-up tests FAIL and `test_ac6_approval_never_claws_back_the_carry_forward` still passes (correctly — approve must not recompute). The hook is demonstrably load-bearing, not decorative.
- `python -m seed` re-run after the `set_accrual` change → exit 0 (it is one of the three existing callers the guard newly touches).

### Completion Notes List

**All nine ACs satisfied. No deviations.** Seven files added (four source, one migration, two test — plus the AC2 guard, eight in total), eight edited. No endpoint, no scheduler, no React screen, no new error code, no new vocabulary constant, no `pyproject.toml` change, no frontend file touched.

**The five landmines, each handled as instructed:**

1. **The non-deferrable CHECK.** Every balance write goes through `balances.set_accrual` and nothing else. No ninth balance method — `tests/test_balances_module_surface.py` still asserts exactly eight public names and passes.
2. **`set_accrual`'s ungated DO-UPDATE branch.** The `available >= 0` pre-check is added and raises the same guarded `ValueError` as `adjust_reserved`/`adjust_consumed`. It reads the row with `leave_balance_repo.lock_balance(...)` **directly** and skips the guard on `None` — the documented trap (`_lock` raises `LookupError` on the fresh-insert path and would break all three create hooks) was avoided; the seed and the materialization tests both re-run green.
3. **The grant.** `0009` issues exactly `GRANT INSERT, SELECT ON rollover_run` and nothing else — 0008's `_APPEND_ONLY_TABLES` shape, not its `_READ_WRITE_TABLES` loop, and no `GRANT USAGE`/`ON ALL SEQUENCES` re-issue. `_quoted_role()` re-declared (revisions are not a package), `--sql` offline mode refused. The grant is verified live: as the app role, `UPDATE` and `DELETE` on `rollover_run` are both refused with `psycopg.errors.InsufficientPrivilege`, and `INSERT`/`SELECT` succeed.
4. **Zero audit rows.** `services/rollover.py` does not import `audit_entry_repo` at all. SM-4's ledger still counts exactly **14** rows with its per-`subject_type` breakdown intact, and the decide count still goes 1 → 2 and stays 2. A dedicated test asserts a reject that *does* top up writes exactly one audit row (the transition) and none for the recompute.
5. **`[tool.importlinter]` untouched** — confirmed unmodified in git; the "rollover" string in that file is the contract-7 comment a previous story wrote in anticipation. All 7 contracts pinned byte-for-byte and green.

**Task 5 (the retro-fit) is where the story actually lives.** The `DR-7a` top-up is wired into exactly the three sites where `available(Y)` rises — reject and self-cancel (via `_decide`'s `release_reserved`) and approve-cancellation (via `release_consumed`) — and deliberately **not** into approve. `_decide` takes a keyword-only `recompute_carry_forward: bool = False` so approve's no-clawback guarantee is a *decision the code states*, not an accident of arithmetic. The hook passes `leave_year=row.start_date.year`, never the `_current_leave_year()` helper sitting in the same module, which would have broken AC6 in AC6's own motivating scenario.

**`recompute_carry_forward` propagates forward and stops at a fixed point.** It walks `y = Y+1, Y+2, …` while a balance row exists, re-deriving each year from the one below it, and returns early once a year's `carried_forward` is already correct — because every later year derives from that one, nothing above it can have moved either. It preserves `prorated_entitlement` and `entitlement_basis` (this re-derives carry-forward, not proration) and uses the existence of the `Y+1` row — never a `rollover_run` query — as the "has the rollover run?" signal, which is what lets that table ship with no getter.

**The six Open Decisions, all adopted as recommended:**

- **#1** — `--year Y` **closes** `Y` and opens `Y+1`; `rollover_run.leave_year = Y`. Stated plainly in `run_rollover`'s docstring and in the CLI's `--help`.
- **#2 (the flagged one)** — **a NULL `carry_forward_cap` on a carrying type means UNCAPPED.** This is the specification's one genuinely under-determined point, and the call was made deliberately: it is what `min()` degenerates to with no ceiling, and the alternative (NULL means zero) would make a carrying type silently lapse *everything* — a wrong balance that would be believed, which is the exact failure PRD §1 exists to prevent. It is distinct from a cap of `0`, which is a real configuration meaning "carries, ceiling zero"; both are covered by separate DB-free tests. No seeded type exercises this (EL's cap is 30), so it is reachable only through a Leave Type an Admin configures. **A reviewer should confirm this reading.**
- **#3** — deactivated Employees roll over like anyone else (`is_active` gates authentication, not accrual).
- **#4** — a pair with no year-`Y` row is treated as `available(Y) = 0` and `Y+1` is materialized anyway, with a warning naming the pair. This fired **117 times** on the real dev database, healing pairs that Story 2.4's concurrent-create hole had left without rows — the job did the right thing and said so.
- **#5** — no endpoint and no getter on `rollover_run`. A new mechanical guard (`tests/test_rollover_has_no_http_surface.py`) asserts no route mentions the rollover and that `on_startup`/`on_shutdown` are **empty**, so AC2 is now enforced by the build rather than by good intentions — it will fail the *next* story that adds a startup hook.
- **#6** — no `UNIQUE (leave_year)`. The idempotence test asserts the two-row outcome so the decision is visible, and the migration smoke asserts the *absence* of the constraint.

**It also heals the live year-rollover cliff** that Story 2.4's review deferred to this story by name: an Employee whose rows were materialized in a prior year now gets `Y+1` rows, so reads no longer go empty and `reserve`/`consume` no longer 500 once the calendar turns.

**Operator note:** the rollover is invoked by an external scheduler — `python -m app.jobs.rollover --year YYYY`, naming the year to **close**. It must be a year that is over; the job has no clock (AC9) and does not police the calendar.

### File List

**Added (8):**

- `backend/app/domain/carry_forward.py`
- `backend/app/services/rollover.py`
- `backend/app/repositories/rollover_run.py`
- `backend/app/jobs/rollover.py`
- `backend/alembic/versions/0009_rollover_run.py`
- `backend/tests/domain/test_carry_forward.py`
- `backend/tests/integration/test_rollover.py`
- `backend/tests/test_rollover_has_no_http_surface.py`

**Modified (8):**

- `backend/app/repositories/models.py` — the `RolloverRun` model.
- `backend/app/services/balances.py` — Landmine 2's mandatory `available >= 0` guard on `set_accrual`. No new public function.
- `backend/app/services/leave_requests.py` — the conditional `DR-7a` hook in `_decide`, passed `True` from `reject_leave_request` and `cancel_leave_request` only.
- `backend/app/services/cancellation.py` — the `DR-7a` hook after `release_consumed`.
- `backend/tests/test_migrations_insert_nothing.py` — `0009_rollover_run.py` appended to the ordered chain.
- `backend/tests/integration/test_migration_smoke.py` — `HEAD_REVISION` bumped to `0009_rollover_run`; `rollover_run` column-set smoke added (exactly `{id, leave_year, occurred_at}`, plus the asserted *absence* of `UNIQUE (leave_year)`).
- `backend/tests/integration/test_schema_1_2.py` — `rollover_run` added to the expected-tables set.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status.

---

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-14 | Story created. Ultimate context engine analysis completed — comprehensive developer guide created. |
| 2026-07-14 | Implemented Story 2.10. `rollover_run` table + migration `0009` with its own `GRANT INSERT, SELECT` (verified live: `UPDATE`/`DELETE` refused as the app role). Pure `domain/carry_forward.py` (never sees a Leave Type code — AC4 unfalsifiable). `services/rollover.py` — one transaction, all writes through `set_accrual`, zero audit rows. `app/jobs/rollover.py` argparse CLI (`--year` required, so no clock is ever mocked). `DR-7a` retro-fit into Stories 2.7 and 2.8 at the three sites where `available(Y)` rises, and deliberately not into approve. Mandatory `available >= 0` guard added to `set_accrual`'s DO-UPDATE branch. New mechanical AC2 guard (no route, no startup/shutdown hook). Heals Story 2.4's deferred year-rollover cliff. Backend pytest **436 passed** (from 405); import-linter **7/7**; migration up/down/up idempotent; `alembic check` empty; seed exit 0. Open Decision #2 (NULL cap on a carrying type = **uncapped**) flagged for reviewer confirmation. |
