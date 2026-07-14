---
baseline_commit: 83096b2037766b176e2db0cad9d9bfaf1facd5c2
---

<!--
  Story 2.11 — created 2026-07-14 by the create-story context engine.
  Sources: epics.md §Story 2.11 (L1286–1337), ARCHITECTURE-SPINE.md AD-18/AD-19/AD-20,
  architecture.md §6.3, api-contracts.md §2/§4.3, erd.md §ADMIN_REVIEW_FLAG/§4.4,
  implementation-readiness-report-2026-07-10.md F-7/F-10, deferred-work.md, stories 2.2/2.4/2.6/2.7/2.8/2.9/2.10.
-->

# Story 2.11: A Holiday Change Recalculates, and May Be Refused

Status: review

## Story

As an Admin,
I want a change to the holiday calendar to correct the requests it affects,
So that a day the organization declared a holiday is not still charged against someone's balance.

## Orientation: what this story actually is

`FR-10` comes due. Story 2.2 shipped the holiday calendar as plain CRUD and **wrote you a note in the code** saying so — `api/v1/holidays.py:24-31`:

> *"api-contracts fixes only non-2xx statuses; the success codes are this story's to choose … `201` create, `204` delete, `200` list … This is NOT the api-contracts §4.3 '200 with a summary' form: **that shape is Story 2.11's**, a consequence of AD-19's forward-checked recalculation, which needs `leave_request`/`leave_balance` (Stories 2.4/2.6) to exist. In Story 2.2 there is nothing to recalculate, so plain CRUD codes ship."*

They exist now. So this story turns two CRUD endpoints into the system's first **partially-refusable command**, and that is the whole of its difficulty.

Three things make it the hardest story in Epic 2:

1. **It is the first caller of `adjust_reserved` and `adjust_consumed`.** Both have existed since Story 2.4 with **zero production callers** — dead code, tested only in isolation. They take **absolute values, not deltas**, and they raise bare `ValueError` (a raw 500), not `DomainError`.

2. **It must refuse *per Employee-and-Leave-Type pair*, mid-transaction, and keep going.** Every other refusal in this codebase aborts the command (`INSUFFICIENT_BALANCE`, `TRANSITION_NOT_ALLOWED`). This one leaves the failing pair *entirely* untouched, writes a durable flag, and lets the rest of the operation commit — returning `200`, not an error.

3. **The refusal must be *predicted*, never *caught*.** AC5 is explicit: *"the refusal was discovered by the forward check, never by an `AD-5` `CHECK` violation."* Wrapping the write in `try/except IntegrityError` — or in `except ValueError` around `adjust_reserved` — **fails AC5 even though every test would go green.** The check is a pure forward projection that runs *before* the first write for that pair.

The governing sentence, from PRD §1 and quoted in the epic beneath AC8:

> *"a leave balance that is wrong is worse than a leave balance that is absent, because it will be believed."*

A refusal recorded where nobody looks is exactly that. Which is why this story does not end at the endpoint — it ends on the Admin's screen (AC8, AC9).

> ⚠️ **The frontend is NOT optional in this story, whatever Story 2.10 told you.**
> Story 2.10's Dev Notes quote the readiness report's line that *"Four stories in Epic 2 — 2.9, 2.10, 2.11, 2.12 — carry no frontend criterion at all."* That sentence is **stale for 2.11.** Finding **F-7** amended the epic and gave this story two frontend criteria — AC8 and AC9 — precisely because *"An Admin adds a holiday. The response is `200`. Three Employees' balances were silently left unchanged … The Admin is told nothing, and no screen exists to read the flags"* (readiness report L584–590). In 2.9 the Admin panel was genuinely optional (*"cut it first if Task 1 runs long"*). **Here it is an acceptance criterion.** Do not cut it.

And Story 2.2 named you, in its Dev Notes, as the owner of the endpoint change:

> *"**Story 2.11's author owns the change to these two endpoints and the React hooks that consume them.**"*

### The one derivation that collapses the problem

A Leave Request may not span two Leave Years (`DR-6`, enforced at submission as `SPANS_TWO_LEAVE_YEARS`). A holiday on date `D` can only fall inside a request whose range *contains* `D`. Therefore **every request affected by a holiday change has leave year `D.year`.**

There is exactly one edited Leave Year, `Y = holiday_date.year`, for every affected pair. You never have to reason about a set of source years — only about `Y` and the materialized years above it.

### The asymmetry — and why the forward check still runs **unconditionally on both paths**

The *direct* effect is asymmetric, and it tells you how to construct each refusal:

- **Deleting** a holiday makes a working day reappear → `leave_days` **rises** → `reserved`/`consumed` **rise** → `available(Y)` **falls** → `carried_forward(Y+1)` falls → `accrued(Y+1)` falls → a later year that is already spent **goes negative**. **This is how you construct the negative-available refusal (AC4/AC5). It is DELETE-only.**
- **Adding** a holiday makes a working day disappear → `leave_days` **falls** → `available(Y)` rises. It cannot drive `available(Y)` negative. **But it has its own refusal: only an ADD can reduce a request to zero working days** (Landmine 3, `CHECK (leave_days > 0)`). **That refusal is ADD-only.**

> 🚫 **Do not conclude from this that `POST /holidays` can skip the forward check.** It cannot, for two reasons:
>
> 1. **Zero-leave-days is an ADD-only refusal.** A POST absolutely can refuse.
> 2. **`carried_forward(Y+1)` may be stale-*high*, so even an ADD's recompute can *lower* `accrued(Y+1)`.** `AD-6` requires `carried_forward` be re-derived on *"every event that can change its inputs,"* but Story 2.10 wired `recompute_carry_forward` into only the **three sites where `available(Y)` rises** (reject, self-cancel, approve-CR — `rollover.py:229-235`). **`reserve` (submit) and `consume_direct` LOWER `available(Y)` and recompute nothing.** So if the rollover ran for `Y` and a year-`Y` request was submitted afterwards — which `run_rollover` permits, since it has no clock and only *warns* that rolling an open year is a mistake (`rollover.py:103-106`) — the stored `carried_forward(Y+1)` is **higher than `min(cap, available(Y))` is now.** `recompute_carry_forward` **assigns a derived value**; it does not only top up. So it will *lower* `accrued(Y+1)` on the next call — **including the one your ADD triggers** — and if `Y+1` is already spent, that is a negative balance and a raw 500.
>
> **Run `project_forward` on both paths, every time, and compare against the *stored* `carried_forward`, never against a pre-edit projection.** Task 2 does this correctly. Write an ADD-refusal test *and* a DELETE-refusal test (Task 8).
>
> The stale-high condition is a **pre-existing gap in 2.10, not a bug you introduce** — see Open Decision #8. Your forward check contains its blast radius; it does not fix it.

## Acceptance Criteria

**AC1 — `admin_review_flag` exists.**
Given a database migrated by this story, when the schema is inspected, then `admin_review_flag` carries the `employee_id` and `leave_type_id` pair it left unchanged, the `leave_year`, a `cause`, and `occurred_at`; and it is not `audit_entry`, and no endpoint updates or deletes a row in it (`AD-20`, `AD-8`).

**AC2 — A Pending request is recalculated.**
Given a Pending Leave Request whose date range contains the added or deleted holiday, when an Admin calls `POST /api/v1/holidays` or `DELETE /api/v1/holidays/<id>`, then that request's `leave_days` and its Reserved days are recalculated (`FR-10`, `AD-19`).

**AC3 — A future Approved request is recalculated; a past one never is.**
Given an Approved Leave Request whose dates lie wholly in the future, when the holiday calendar changes inside its range, then its `leave_days` and the applicant's balance are recalculated; and an Approved request whose dates have already passed is **never** recalculated (`AD-18`, `FR-10`).

**AC4 — The forward check refuses per pair, and the rest proceeds.**
Given a recalculation that would drive Available negative in the edited Leave Year or in any materialized later one, when the forward check runs inside the same transaction, then that **Employee and Leave Type pair** is left entirely unchanged, the same Employee's other Leave Types still proceed, and the rest of the operation succeeds; and the endpoint returns `200` with a summary rather than failing wholesale (`AD-19`, api-contracts §4.3).

**AC5 — A refusal is recorded, and was predicted.**
Given a refused recalculation, when it occurs, then a row is written to `admin_review_flag` carrying its cause and the Employee and Leave Type it left unchanged; and the refusal was discovered by the forward check, **never** by an `AD-5` `CHECK` violation (`AD-19`, `AD-20`).

**AC6 — An Admin reads the refusals.**
Given an authenticated Admin, when they call `GET /api/v1/admin-review-flags`, then they read the recorded refusals; and no endpoint clears a flag — `FR-10` grants the read and no requirement grants a resolve (`AD-20`).

**AC7 — Nobody else reads them.**
Given an authenticated Employee or Manager, when they call `GET /api/v1/admin-review-flags`, then the response is `403` with code `ACTION_NOT_PERMITTED` — only an Admin reads the recorded refusals (`FR-10`, `AD-20`, `G3`).

**AC8 — The Admin is never shown an unqualified success.**
Given the React application and an authenticated Admin who has just added or deleted a holiday, when the `200` summary returns, then the screen states how many Employee-and-Leave-Type pairs were recalculated and how many were **left unchanged**, naming each refused pair; and the Admin is never shown an unqualified success for an operation that partially refused (`FR-10`, `AD-19`, `NFR-17`).

**AC9 — The Review Flags screen.**
Given the React application and an authenticated Admin, when they open the Review Flags screen, then they see every recorded refusal with its cause, the Employee and Leave Type it left unchanged, and when it occurred; and no control clears a flag, because no requirement grants a resolve (`AD-20`).

---

## 🚨 Seven landmines. Read these before writing a line.

### Landmine 1 — `adjust_reserved` / `adjust_consumed` take **absolute** values, not deltas. You are their first caller.

Repo-wide, these two have **zero production callers**. They are not `reserve(days=3)`-shaped:

```python
# backend/app/services/balances.py:225 and :252 — note the kwarg names
def adjust_reserved(session, *, employee_id, leave_type_id, leave_year, reserved: int) -> None
def adjust_consumed(session, *, employee_id, leave_type_id, leave_year, consumed: int) -> None
```

`reserved=` is the **new total** for that `(employee, leave_type, year)` balance row — which aggregates **every** Pending request for that pair in that year, not just the ones this holiday touched. So you must compute:

```
new_reserved = balance.reserved + Σ(new_leave_days − old_leave_days) over the AFFECTED PENDING requests
new_consumed = balance.consumed + Σ(new_leave_days − old_leave_days) over the AFFECTED FUTURE-APPROVED requests
```

Passing the delta where an absolute is expected will zero out every unaffected request's reservation and the CHECK will not catch it, because a *smaller* `reserved` never violates `available >= 0`. **This is a silent data-corruption bug that ships green.**

Both raise **bare `ValueError`** (`balances.py:242`, `:269`), not `DomainError` — an uncaught 500. Your forward check must guarantee they never raise. See Landmine 4.

### Landmine 2 — `leave_days` and `reserved` must move in the same transaction, or you ship a latent 500 that is already written down.

`deferred-work.md:56`, deferred from the Story 2.7 review, describes your story by name:

> *"`consume_reserved`/`release_reserved` `ValueError` → raw 500 if `reserved` is moved out of band below `leave_days`. … then `approve` passes the `WHERE status = PENDING` guard, `consume_reserved(days)` finds `days > reserved` and raises `ValueError` (not a `DomainError`) → raw 500. **Latent — reachable only once an out-of-band reserved-adjust endpoint ships.**"*

**This story is that ship.** If you lower a Pending request's `reserved` without rewriting `leave_request.leave_days` to match, the next approve of that request explodes. Update **both**, always, in the same transaction.

There is no `leave_days` setter today. `repositories/leave_request.py:209` calls itself *"The ONE sanctioned mutation of a `leave_request` row (there is no free-form update/delete)."* You must add a **second**, narrowly-scoped one — `AD-18` explicitly permits exactly this and nothing more:

> *"Only `AD-19`'s recalculation may change it, and only for a Pending request, or an Approved request whose dates lie wholly in the future."*

**Revise that docstring** to name the second mutator and its one sanctioned caller. Do not silently contradict it, and do not smuggle the write in through a sibling module — Story 2.9's review established that a surface claim gets *revised*, never routed around.

### Landmine 3 — `CHECK (leave_days > 0)`. Adding a holiday can reduce a request to zero working days.

`models.py:326-329` carries `leave_request_leave_days_positive_check`. A one-working-day request on a Monday, and the Admin declares that Monday a holiday → the recalculated `leave_days` is `0` → your `UPDATE` fires the CHECK → **raw 500**, and AC5 is violated (the failure surfaced from a CHECK, not from the forward check).

This is reachable, cheap to hit, and the spec does not name it. Handle it **in the forward check**, as a refusal for that pair — see Open Decision #3.

⚠️ A `ZERO_LEAVE_DAYS` refusal **already exists** — `services/leave_requests.py:169` (`_zero_leave_days()`), raised at `:368-369` when a *submission* prices out at zero. **Do not reuse it here, and do not invent a second copy of it.** It is an **error code that aborts the command** — which is exactly what AC4 forbids: the holiday edit must still commit, and the pair must be *flagged*, not the request *refused*. Reuse the constant if you want it in the flag's context; never raise it from the recalculation path.

### Landmine 4 — The refusal must be **predicted**, not **caught**. AC5 says so in as many words.

> *"the refusal was discovered by the forward check, never by an `AD-5` `CHECK` violation."*

So the following are all **AC5 violations**, no matter how green the suite goes:

```python
# ❌ ALL WRONG.
try:
    balances.adjust_reserved(...)
except ValueError:                 # ← caught, not predicted
    flag(...)

try:
    session.flush()
except IntegrityError:             # ← the CHECK found it, not you
    session.rollback(); flag(...)

with session.begin_nested():       # ← a savepoint that rolls back on a DB error
    ...                            #    is still the DB discovering the refusal
```

The shape that satisfies AC5: for each pair, **project the entire outcome purely, in memory, before the first write for that pair.** If the projection says negative, write the flag and touch nothing else. If it says fine, apply — and now `adjust_*` and `set_accrual` *cannot* raise, because you already proved they won't.

That is also why `AD-5` calls the CHECKs a *"backstop, never a gate."* They stay a backstop here.

### Landmine 5 — Zero audit rows. Two suite-wide counters pin this exactly.

```python
# tests/integration/test_audit_entries.py:511
assert len(rows) == 14, (
    "SM-4 is one audit row per state transition, counted one-to-one. Expected 14 for the ..."
)
```

A recalculation is a **balance re-derivation, not a state transition**. `AD-8` reserves `audit_entry` for transitions; `AD-20` says flatly *"Neither table is `audit_entry`."* There is no `SUBJECT_HOLIDAY` in `domain/vocabulary.py` and — echoing `services/rollover.py:34`'s *"There is no `SUBJECT_ROLLOVER` and there must not be one"* — **there must not be one.**

Write **zero** `audit_entry` rows. Do not import `audit_entry_repo` into the recalculation service; its absence is the proof, exactly as `rollover.py` does it.

(Note the flip side: `admin_review_flag` is *not* an audit row and does not count against SM-4. Write as many as the refusals require.)

### Landmine 6 — `POST /holidays` `201`→`200` and `DELETE /holidays/<id>` `204`→`200` are **breaking changes**. Revise; do not route around.

api-contracts §4.3 is binding: *"these endpoints return `200` with a summary rather than failing wholesale."* AC4 and AC8 both name `200`. So:

| Endpoint | Was (Story 2.2) | Becomes (this story) |
| --- | --- | --- |
| `POST /api/v1/holidays` | `201` + `HolidayResponse` | `200` + the summary |
| `DELETE /api/v1/holidays/<id>` | `204`, empty body | `200` + the summary |

Blast radius you must fix, not delete:
- `tests/integration/test_holidays.py` — asserts `201` at **:177, :203, :333, :401** and `204` + `assert deleted.content == b""` at **:210-211**. Revise them.
- `frontend/src/api/holidays.ts` — `useCreateHoliday` returns `apiFetch<Holiday>`, `useDeleteHoliday` returns `apiFetch<void>` and `HolidaysPage.tsx:95` **discards the result**. Both must return the summary, and the page must render it (AC8).
- `api/v1/holidays.py:24-31` — the "G6 / this story's to choose" docstring block is now **stale prose**. Rewrite it.
- `frontend/src/api/holidays.ts:9-12` — states the same superseded contract (*"`201` create, `204` delete, `200` list. `apiFetch` decodes an empty `204` body to `undefined`"*). Rewrite it too; a stale comment on the client is how the next story re-learns this the hard way.

### Landmine 7 — Do not add a ninth balance method, and do not touch `[tool.importlinter]`.

```python
# tests/test_balances_module_surface.py:46-57 — reflection over services/balances.py
assert _public_callables_defined_here() == set(_EXPECTED_PUBLIC_CALLABLES)  # the eight
assert len(_public_callables_defined_here()) == 8
```

Every helper you are tempted to add to `balances.py` must be `_`-prefixed, or it fails the build. The orchestration belongs in a **new** module (`services/recalculation.py`), not in `balances.py`.

The seven import-linter contracts in `backend/pyproject.toml` already cover `app.domain`, `app.services`, `app.api` and `app.jobs`. `tests/test_architecture.py` pins all seven byte-for-byte. A new `domain/` module and a new `services/` module need **no contract change** — they are already governed. Touching that block is how you break 7/7.

---

## Tasks / Subtasks

### Task 1 — `admin_review_flag`: the model, migration `0010`, and its own grant (AC1)

- [x] Add `AdminReviewFlag` to `backend/app/repositories/models.py`, mirroring `RolloverRun`/`AuditEntry`:
  - `id` (`uuidv7()` server default, PK), `employee_id` (FK → `employee.id`, NOT NULL), `leave_type_id` (FK → `leave_type.id`, NOT NULL), `leave_year` (INT NOT NULL), `cause` (TEXT NOT NULL), `occurred_at` (`TIMESTAMPTZ` NOT NULL).
  - **No `resolved_at`, and no update/delete mutator.** ERD §ADMIN_REVIEW_FLAG: *"there is no `resolved_at` column and no endpoint clears a flag. A flag is a permanent record that a recalculation was refused."*
  - Column name is **`occurred_at`**, not the ERD's `raised_at` — see Open Decision #1.
  - 🚫 **`ARCHITECTURE-SPINE.md:317-321`'s ERD diagram is STALE. Do not build from it.** It shows `ADMIN_REVIEW_FLAG { text cause; uuid subject_id; timestamptz resolved_at }` — a single polymorphic `subject_id` and a `resolved_at`. Both are wrong: they contradict `AD-20`'s own prose in the same file (`:185`), `erd.md:283-291`, ERD GAP-4 (`erd.md:442-444`), and **AC1**, which requires the `employee_id` *and* `leave_type_id` **pair** and grants no resolve. Build from **AC1**. A `resolved_at` column would also silently justify the `UPDATE` grant that AC1 forbids.
- [x] Write `backend/alembic/versions/0010_admin_review_flag.py`, `down_revision = "0009_rollover_run"`. **Copy the shape of `0009`, not `0008`'s read-write loop:**
  - Re-declare `_quoted_role()` with `psycopg.sql.Identifier` (revisions are not a package — `0009`'s docstring explains why it is copied, not imported).
  - Refuse `--sql` offline mode with the same `RuntimeError` + sentence.
  - Issue exactly: `GRANT INSERT, SELECT ON admin_review_flag TO <app_role>` — **not `UPDATE`, not `DELETE`.** This is the third append-only table and it **inherits nothing**: `0008` deliberately declined `ALTER DEFAULT PRIVILEGES` precisely so each such table must grant for itself.
  - ⚠️ **`0008` defines two grant shapes — `_APPEND_ONLY_TABLES` (INSERT, SELECT) and `_READ_WRITE_TABLES` (all four verbs). This table is APPEND-ONLY, and that is a deliberate call, not a default.** The tempting argument for read-write is *"an Admin will want to resolve a flag."* **No requirement grants a resolve.** `FR-10` grants the Admin **only a read**; ERD §6 states the consequence outright — *"there is no `resolved_at` column and no endpoint clears a flag … The undefined behavior is gone because the behavior no longer exists."* AC1 says *"no endpoint updates or deletes a row in it."* Granting `UPDATE`/`DELETE` here would leave every test green and quietly destroy the guarantee, exactly as `0009`'s docstring warns about copying the wrong loop.
  - Do not re-issue `GRANT USAGE ON SCHEMA` / `ON ALL SEQUENCES` — `0008` did both.
- [x] Verify `alembic upgrade head` → `downgrade` → `upgrade` is idempotent and `alembic check` reports no drift (`tests/integration/test_model_migration_agreement.py`).
- [x] Confirm `tests/test_migrations_insert_nothing.py` still passes — `CREATE TABLE` + `GRANT` are schema/privilege, not data.

### Task 2 — `domain/recalculation.py`: the pure forward projection (AC4, AC5)

This is the heart of AC5, and it is DB-free and directly unit-testable — the same shape as `domain/carry_forward.py` (2.10) and `domain/proration.py` (2.4).

- [x] Create `backend/app/domain/recalculation.py`. It imports **no ORM, no web framework, no `app.core`** (import-linter contract 3/5). It may import `domain.carry_forward` and `domain.vocabulary`.
- [x] Model the inputs as frozen dataclasses, e.g.:

```python
@dataclass(frozen=True)
class YearBalance:
    """One materialized leave_balance year, as pure numbers."""
    leave_year: int
    prorated_entitlement: int
    carried_forward: int
    reserved: int
    consumed: int

@dataclass(frozen=True)
class ForwardProjection:
    refused: bool
    refused_year: int | None                  # the first year that would go negative
    carried_forward_by_year: dict[int, int]   # years > Y this recalculation must rewrite
```

- [x] Implement the projection, ascending from `Y`:

```python
def project_forward(
    *,
    years: Sequence[YearBalance],          # ascending, starting at Y, contiguous
    new_reserved: int,                     # the NEW absolute reserved for year Y
    new_consumed: int,                     # the NEW absolute consumed for year Y
    carries_forward: bool,
    carry_forward_cap: int | None,
) -> ForwardProjection:
```

  1. `available(Y) = (prorated + carried) − new_consumed − new_reserved`. If `< 0` → refused at `Y`.
  2. Walk each later materialized year in ascending order:
     `carried' = carry_forward_days(available=available(prev), carries_forward=…, carry_forward_cap=…)`
     `available = (prorated + carried') − consumed − reserved`. If `< 0` → refused at that year.
  3. **Stop at the fixed point:** if `carried' == that year's existing `carried_forward`, nothing downstream changes and every later year is already non-negative (it is committed and the CHECK holds). Return. This mirrors `services/rollover.recompute_carry_forward`'s stop condition exactly — it is the fixed point, not an optimization.
- [x] **Reuse `carry_forward.carry_forward_days` — do not re-derive `min(cap, available)`.** A second implementation of the carry-forward rule is the same class of defect `NFR-08` forbids for the day count. It is **keyword-only** (`carry_forward.py:27-32`).
- [x] ⚠️ **`carry_forward_days` clamps at `max(0, …)`** (`carry_forward.py:78-80`), so a negative year is **invisible in `carried'`** — it never returns a negative. You therefore **cannot** infer non-negativity from the carry-forward value. **Check `available` independently at every single year** (step 2 above does; do not "optimize" it away).
- [x] Unit-test in `backend/tests/domain/test_recalculation.py`, DB-free: an ADD can never refuse (monotonicity); a DELETE that eats a spent later year refuses **at that later year**, not at `Y`; the fixed point terminates; a lapsing type (`carries_forward=false`) propagates `0`; `carry_forward_cap=None` on a carrying type is uncapped (inherited from 2.10, Open Decision #2).

### Task 3 — Repositories: the overlap sweep, the `leave_days` mutator, and the flag store (AC1, AC2, AC3)

- [x] `backend/app/repositories/leave_request.py` — add the affected-request sweep:

```python
def list_requests_covering(
    session: Session, *, on_date: datetime.date, today: datetime.date
) -> list[LeaveRequest]:
```
  `WHERE start_date <= :on_date AND end_date >= :on_date` (this is exactly what `ix_leave_request_start_end` from migration `0006` indexes — **do not create a second index**), `AND (status = PENDING OR (status = APPROVED AND start_date > :today))`. `REJECTED`/`CANCELLED` hold no days and are never touched. Order deterministically by `(employee_id, leave_type_id, id)`.
  `today` is passed **in** — the clock lives in `services/`, never in `repositories/` or `domain/` (`AD-1`).
  ⚠️ This is a `list_` getter taking a `session`, so `tests/test_scoped_getters.py` **will net it.** Add it to `EXEMPT` with a why-exempt docstring — see Landmine notes in Task 9.

- [x] `backend/app/repositories/leave_request.py` — add the **second** sanctioned mutation:

```python
def set_leave_days(session: Session, *, request_id: uuid.UUID, leave_days: int) -> None:
```
  Guard `leave_days > 0` in the caller (Landmine 3), `flush()`, never `commit()`. **Revise `transition_status`'s "the ONE sanctioned mutation" docstring** (`leave_request.py:218`) to name this second one, its single caller, and `AD-18`'s narrow grant.

- [x] `backend/app/repositories/admin_review_flag.py` — new module, one table, two functions (the `rollover_run` / `audit_entry` shape):
  - `insert_admin_review_flag(session, *, employee_id, leave_type_id, leave_year, cause, occurred_at) -> None` — `flush()`, **never `commit()`**: the flag is written in the *same* transaction as the recalculation it records, so a rolled-back edit leaves no flag claiming it happened.
  - `list_admin_review_flags(session, *, limit, offset) -> tuple[list, int]` — **INNER JOIN** `employee` and `leave_type` to carry `full_name` and `code` (both FKs are NOT NULL, so unlike `audit_entry`'s SYSTEM rows there is nothing to outer-join for). `ORDER BY occurred_at DESC, id DESC` — the `id` tiebreak is not optional: one holiday edit writes several flags sharing a single `occurred_at`, and 2.9 proved a total order is required for a stable page walk.
  - **No update. No delete.** The absence is the point (AC6: *"no endpoint clears a flag"*).
  - ⚠️ Also nets `test_scoped_getters` → `EXEMPT` + why-exempt docstring.

- [x] **Do not add a "list balances from year Y" repo getter.** Loop `leave_balance_repo.lock_balance(...)` upward from `Y` until it returns `None` — years are materialized contiguously, and this is precisely what `rollover.recompute_carry_forward` already does. Reusing it avoids a third `EXEMPT` entry and keeps the ascending `(employee_id, leave_type_id, leave_year)` lock order `AD-3` requires.

### Task 4 — `services/recalculation.py`: the per-pair engine (AC2, AC3, AC4, AC5)

- [x] Create `backend/app/services/recalculation.py`. It takes the **caller's open `Session`** and opens no transaction of its own — the holiday command owns the one transaction (`AD-3`, `AD-19`: *"within the same transaction"*).
- [x] **Do not import `audit_entry` here.** Its absence is the proof of Landmine 5.
- [x] Public surface:

```python
@dataclass(frozen=True)
class RefusedPair:
    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_year: int
    cause: str

@dataclass(frozen=True)
class RecalculationSummary:
    requests_recalculated: int
    pairs_recalculated: int
    pairs_refused: list[RefusedPair]

def recalculate_for_holiday_change(
    session: Session, *, holiday_date: datetime.date
) -> RecalculationSummary:
```

- [x] Call it from `services/holidays.py` **after** the insert/delete has been flushed, so `holiday_repo.holidays_in_range` already reflects the new calendar. This is why the recalculation cannot be a separate transaction.
  - ⚠️ `holiday_repo.create_holiday` **does** `flush()` (`repositories/holiday.py:130`). **`holiday_repo.delete_holiday` does NOT** (`:142` is a bare `session.delete(holiday)`). Autoflush would probably save you when the recalculation issues its first `SELECT` — **do not rely on it.** Add an explicit `session.flush()` after the delete.
  - ⚠️ `delete_holiday(holiday_id)` returns `None` and the row is gone by the time you need its date. **Capture `holiday.holiday_date` off the loaded row *before* deleting it.**
- [x] Algorithm:
  1. `Y = holiday_date.year`; `today = datetime.date.today()` (the clock lives here, in `services/`).
  2. `rows = leave_request_repo.list_requests_covering(session, on_date=holiday_date, today=today)`.
  3. Group by `(employee_id, leave_type_id)`. Process pairs **sorted ascending by `(employee_id, leave_type_id)`** — a deterministic lock order (`AD-3`); a holiday edit locks every affected balance row and a nondeterministic order is how two concurrent edits deadlock.
  4. Per pair:
     - Recompute each request's `leave_days` with `calendar.count_leave_days(start, end, holiday_map.keys())`, sourcing the calendar from `holiday_repo.holidays_in_range(session, start, end)`. **`domain.calendar.count_leave_days` is the only code that knows what a weekend or a holiday is (`AD-2`, `NFR-08`) — do not hand-roll a second day count here.**
     - If any recalculated `leave_days == 0` → **refuse the pair** (Landmine 3, Open Decision #3).
     - `delta_reserved = Σ(new − old)` over the pair's PENDING rows; `delta_consumed = Σ(new − old)` over its future-APPROVED rows.
     - Lock year `Y` (`leave_balance_repo.lock_balance`), then walk upward collecting every materialized year into `YearBalance`s. Use `lock_balance` **directly**, never `balances._lock` — `_lock` raises `LookupError` on a missing row and the walk *ends* on a missing row (the documented trap at `balances.py:311-316`).
     - `project_forward(years=…, new_reserved=bal.reserved + delta_reserved, new_consumed=bal.consumed + delta_consumed, …)`.
     - **Refused** → `insert_admin_review_flag(...)` and `continue`. **Write nothing else for this pair.** The same Employee's other Leave Types keep going (AC4).
     - **Not refused** → `set_leave_days` for each changed request; `adjust_reserved(reserved=<absolute>)`; `adjust_consumed(consumed=<absolute>)`; then `rollover.recompute_carry_forward(session, employee_id=…, leave_type_id=…, leave_year=Y)` to propagate `carried_forward` forward to the fixed point.
  5. Return the summary.
- [x] **`leave_year=Y = holiday_date.year`. Never `date.today().year`.** A `_current_leave_year()` helper exists in `services/balance_reads.py:53` and `services/leave_requests.py:230` and is the wrong one — Story 2.10 recorded this exact trap for its own AC6 and the same reasoning applies verbatim: a year-`Y` request edited *during* year `Y+1` would recompute from the wrong year and the correction would never fire.
- [x] You become the **fourth** call site of `rollover.recompute_carry_forward` (2.10 wired the other three: reject, self-cancel, approve-CR) — and the **first where `available(Y) can fall`.** That is exactly the case its `set_accrual` guard was hardened for, and exactly why your forward check must run first.

### Task 5 — Wire the holiday endpoints: one transaction, `200` + summary (AC2, AC3, AC4) ⚠️ **the breaking change**

- [x] `services/holidays.py` — `create_holiday` and `delete_holiday` currently open their own sessions and return `CompanyHoliday` / `None`. Restructure so that, **inside the existing `with Session(...)` block and before `session.commit()`**, the flushed write is followed by `recalculation.recalculate_for_holiday_change(session, holiday_date=…)`. Both now return the holiday **and** its `RecalculationSummary`. Preserve `create_holiday`'s `IntegrityError` → `HOLIDAY_DATE_IN_USE` TOCTOU backstop and `delete_holiday`'s load-or-`not_found()` exactly as they are.
  - ⚠️ **In `create_holiday`, the recalculation call goes *inside* the existing `try:`** (`services/holidays.py:80-89`), between `holiday_repo.create_holiday(...)` and `session.commit()` — the `try` wraps both the flush and the commit. **Know the consequence:** any `IntegrityError` your recalculation raises now lands in that `except IntegrityError` handler, where `holiday_date_exists()` returns `False` after the rollback and the raw error is re-raised as a **500**. That is precisely the AC5 failure mode, surfacing as an unhelpful traceback pointing at the wrong cause. It is one more reason the forward check must make an `IntegrityError` **impossible** rather than catchable.
- [x] `api/v1/holidays.py` — `POST` becomes `200` (drop `status_code=HTTP_201_CREATED`), `DELETE` becomes `200` with a body. Both return a hand-projected summary model (contract 2 forbids `api/` importing `repositories/` or `domain/`; duck-type the view as `object`, the `audit_entries.py:82` precedent). Suggested wire shape:

```jsonc
{
  "holiday": { "id": "…", "holiday_date": "2026-12-25", "name": "Christmas" },
  "recalculation": {
    "requests_recalculated": 7,
    "pairs_recalculated": 5,
    "pairs_refused": [
      { "employee_id": "…", "employee_name": "Ada Lovelace",
        "leave_type_id": "…", "leave_type_code": "EL",
        "leave_year": 2026, "cause": "HOLIDAY_RECALCULATION" }
    ]
  }
}
```
- [x] Rewrite the now-stale `api/v1/holidays.py:24-31` docstring block: the `201`/`204` "this story's to choose" note is superseded; say so, and cite api-contracts §4.3.
- [x] Revise `tests/integration/test_holidays.py` — `201` at :177, :203, :333, :401 and `204` + empty body at :210-211 (Landmine 6). **Revise, do not delete.**

### Task 6 — `GET /api/v1/admin-review-flags` (AC6, AC7)

- [x] `services/audit.py` is the template. Create the read service (a plain `AdminReviewFlagView` frozen dataclass + a `list_admin_review_flags(actor, *, limit, offset)` that opens a **read-only** session and does **not** commit — the Story 2.5 precedent: *"a commit on a read path is how a 'read' quietly becomes a write"*).
- [x] `api/v1/admin_review_flags.py` — copy `api/v1/audit_entries.py` almost exactly:
  - `admin: Actor = Depends(require_role(authz.ROLE_ADMIN))` — the gate is a dependency, so a non-Admin is refused **before any row is read** (`G3`). That delivers AC7 with **no new error code**: `ACTION_NOT_PERMITTED` is already declared in `domain/vocabulary.py` and already mapped to `403` in `main.py`. **`main.py` is not touched by this story.**
  - `PageParams` / `Page[T]` for the bound (`NFR-11`). No filters — no AC names one.
  - **No `PATCH`, no `DELETE`, no resolve.** AC6: *"no endpoint clears a flag."*
- [x] Register the router in `api/v1/router.py` (one import + one `include_router`).
- [x] **Do not register it in `tests/test_scope_matrix.py`.** It has no path parameter, so it is outside the SM-3 matrix *by construction*; registering it trips `test_no_registered_entry_names_a_route_the_app_does_not_expose`. This is the `GET /audit-entries` precedent, stated at `api/v1/audit_entries.py:21-25`.
- [x] Add `CAUSE_HOLIDAY_RECALCULATION = "HOLIDAY_RECALCULATION"` to `domain/vocabulary.py` **and to `__all__`** (`test_vocabulary_literals.py` AST-forbids the bare literal anywhere else). It is a **response reason, not an error code** — it maps to no HTTP status, so `CODE_TO_STATUS` is untouched. The `EXCLUSION_WEEKEND`/`EXCLUSION_HOLIDAY` block (`vocabulary.py:125-135`) is the precedent; mirror its comment style. Story 2.12 will add `CAUSE_POLICY_RECALCULATION` beside it.

### Task 7 — Frontend: the summary and the Review Flags panel (AC8, AC9)

There is **no router** in this app. A screen is a `<section className="panel">` added to `AppShell` in `App.tsx` — one import, one JSX element (the Story 2.9 `AuditLogPanel` precedent, `App.tsx:24` + `:107`).

- [x] `frontend/src/api/adminReviewFlags.ts` — copy `api/auditEntries.ts` verbatim in shape: `ADMIN_REVIEW_FLAGS_QUERY_KEY = ['admin-review-flags'] as const`, `useAdminReviewFlags({ enabled })` → `apiFetch<Page<AdminReviewFlag>>('/admin-review-flags')`. **No mutation hook, no invalidation** — the table is append-only and nothing clears a flag (AC9). Say that in the header comment, as `auditEntries.ts:5-8` does.
- [x] Export both from the `api/index.ts` barrel (features import from `'../../api'`, never a file path).
- [x] `frontend/src/features/reviewFlags/ReviewFlagsPanel.tsx` — copy `features/audit/AuditLogPanel.tsx`:
  - `const me = useMe(); const isAdmin = me.data?.role === ADMIN_ROLE` with `const ADMIN_ROLE = 'ADMIN'` as a local module const; gate the fetch on `enabled: isAdmin`; `if (!isAdmin) return null` **after** all hook calls (oxlint `react/rules-of-hooks`).
  - Four states: loading / error / empty / list. Render each flag's employee name, leave type code, leave year, cause and `occurred_at` **exactly as the server sent them** — no parsing, no reformatting (`AD-2`).
  - **No clear/resolve button.** State in the header comment *why*: no requirement grants a resolve (`AD-20`).
- [x] `App.tsx` — import and render `<ReviewFlagsPanel />` next to `<AuditLogPanel />`, with the `{/* … */}` role-gate comment every other panel carries.
- [x] `frontend/src/api/holidays.ts` — retype `useCreateHoliday` and `useDeleteHoliday` to return the summary. Invalidate `HOLIDAYS_QUERY_KEY`, **`BALANCES_QUERY_KEY`, `LEAVE_REQUESTS_QUERY_KEY` and `ADMIN_REVIEW_FLAGS_QUERY_KEY`** — a recalculation moves all four. Keep `useDeleteHoliday`'s `onSettled` (its documented ghost-row reconcile).
- [x] `frontend/src/features/holidays/HolidaysPage.tsx` — **AC8 is the point of the story.** `handleDelete` at `:95` currently discards the mutation result; capture the summary into state and render, after both add and delete:
  - how many pairs were recalculated, **and** how many were left unchanged;
  - **each refused pair named** (employee + leave type), using `.emp-error` / `.emp-inactive` (`color: var(--down)`);
  - never an unqualified success when `pairs_refused.length > 0`.
- [x] **Add no CSS.** `index.css` already has `.panel`, `.muted`, `.emp-list`, `.emp-row`, `.emp-summary`, `.emp-name`, `.emp-error`, `.emp-inactive`. There are no `<table>` styles in this app — every list is `<ul>/<li>`.
- [x] Never call `getDay`/`getUTCDay` — `tests/test_frontend_no_client_day_count.py` scans `frontend/src/**` from the **backend pytest suite** and fails the build. (Naming a holiday, a date, a leave year or a count is fine; *computing* one is not.)

### Task 8 — Tests (AC1–AC9)

- [x] `tests/domain/test_recalculation.py` — DB-free, per Task 2.
- [x] `tests/integration/test_holiday_recalculation.py`:
  - **AC2** Pending request spanning the new holiday → `leave_days` falls, `reserved` falls, `available` rises.
  - **AC3** future Approved → recalculated; **past-dated Approved → byte-identical `leave_days`, `consumed` and balance row.** Assert the *absence* of change, not just the presence.
  - **AC4/AC5 — the negative-available refusal, built with a `DELETE`.** Set up a pair whose year `Y+1` is already spent, delete a holiday inside a year-`Y` request → the pair is left **entirely** unchanged (assert the balance row and every request row byte-for-byte), a flag appears, **and the same Employee's other Leave Type still recalculates**, and the response is `200`.
  - **AC4/AC5 — the ADD path also refuses.** Two tests, because the Orientation section explains that a POST is *not* a documented no-op: (a) the zero-leave-days refusal (below); (b) a **stale-high `carried_forward(Y+1)`** — roll year `Y`, then submit a year-`Y` request (which lowers `available(Y)` and recomputes nothing), spend `Y+1`, then **ADD** a holiday → the recompute would lower `accrued(Y+1)` below what is spent → the pair is refused and flagged, and the response is still `200`, **not a 500**.
  - **AC5 non-vacuity:** assert **no** `IntegrityError`/`CHECK` violation was involved. The sharpest form: temporarily disable the forward check and confirm the test fails with a *500 / CHECK violation* rather than a clean flag — proving the check, not the constraint, is what refuses. (Story 2.10 proved its AC6 tests non-vacuous this way; do the same.)
  - **Zero-leave-days**: a 1-working-day request + a holiday added on that day → the pair is refused and flagged, no `CHECK` fires.
  - **SM-4 unbroken**: a holiday edit that recalculates writes **zero** `audit_entry` rows; `test_audit_entries.py`'s `== 14` still passes.
  - **AC1 append-only, proven live**: connected as the app role, `UPDATE`/`DELETE` on `admin_review_flag` both raise `psycopg.errors.InsufficientPrivilege`; `INSERT`/`SELECT` succeed. (Story 2.9/2.10 verified their grants exactly this way — assert the refusal, don't just read the migration.)
  - **AC6/AC7**: Admin `GET /admin-review-flags` → `200`; Employee and Manager → `403 ACTION_NOT_PERMITTED`.
- [x] Revise `tests/integration/test_holidays.py` for the new status codes (Landmine 6).
- [x] Reuse the `owner_engine` conftest fixture (`tests/integration/conftest.py`, added by 2.9) for any cleanup of append-only tables — **the app role cannot delete `admin_review_flag` rows, and that *is* AC1.**

### Task 9 — The guard files that will fail the build if you forget them

- [x] `tests/test_scoped_getters.py` — add **`list_requests_covering`** and **`list_admin_review_flags`** to `EXEMPT`, each with a rationale comment there **and** a "why exempt" docstring at the definition. The honest rationales:
  - `list_requests_covering` — a **system-wide recalculation sweep**, not an actor-facing read. There is no actor whose scope could narrow it; narrowing it would silently skip the very Employees whose balances must be corrected. The gate is the **Admin role** on the holiday endpoint, applied before the sweep runs.
  - `list_admin_review_flags` — api-contracts scope is `all` and the gate is the **Admin role** (`require_role`, before any row is read, `G3`). The `employee_id` column names the *subject of a refusal*, not an owner whose scope should filter the Admin's read.
  - Do **not** dodge the net by renaming to a non-`list_`/`get_` verb. Story 2.9's review settled this: the surface test gets *revised with rationale*, never routed around.
- [x] `tests/test_vocabulary_literals.py` — `CAUSE_HOLIDAY_RECALCULATION` must be in `vocabulary.__all__`, and the bare string must appear nowhere else in `app/` or `seed/`.
- [x] `tests/test_balances_module_surface.py` — must still see **exactly eight**. If it doesn't, you put your helper in the wrong module.
- [x] `tests/test_architecture.py` — import-linter **7/7**. `pyproject.toml`'s `[tool.importlinter]` is **not** edited.
- [x] `tests/test_scope_matrix.py` — **unchanged.** `GET /admin-review-flags` has no path parameter.
- [x] `tests/test_migrations_insert_nothing.py` — `0010` inserts no rows.

---

## Dev Notes

### The one-paragraph mental model

An Admin adds or deletes a holiday. Inside that one transaction, after the row is flushed, you sweep every Leave Request whose range contains that date and which still holds days — every `PENDING`, plus every `APPROVED` that starts in the future. You group them by `(Employee, Leave Type)`, because that pair is the unit of refusal. For each pair you compute what the new numbers *would be*, purely, in memory — the new `leave_days` per request, the new `reserved`/`consumed` totals for year `Y = holiday_date.year`, and the knock-on `carried_forward` for every materialized year above it. If any of those years would go negative, you write **nothing** for that pair, drop a row in `admin_review_flag`, and move to the next pair. If they all hold, you write the new `leave_days`, set the new absolute `reserved`/`consumed`, and let `recompute_carry_forward` push the change forward to its fixed point. Then you commit once and return `200` with a summary that tells the Admin, honestly, how many pairs you fixed and how many you refused.

### Reuse map — nearly everything you need already exists

| You need | It already exists | Do **not** |
| --- | --- | --- |
| The day count | `domain/calendar.count_leave_days(start, end, holidays)` — takes a bare `Collection[date]` | write a second weekend/holiday rule (`AD-2`, `NFR-08`) |
| `min(cap, available)` | `domain/carry_forward.carry_forward_days(*, available, carries_forward, carry_forward_cap)` — **keyword-only**, and it clamps at `max(0, …)` | re-derive the clamp |
| Forward propagation of `carried_forward` | `services/rollover.recompute_carry_forward(session, employee_id, leave_type_id, leave_year)` — walks `Y+1…` to a fixed point, preserves `prorated_entitlement`/`entitlement_basis`, writes zero audit rows | write a second walk |
| Writing balance quantities | `balances.adjust_reserved` / `adjust_consumed` / `set_accrual` — the AD-17 eight | add a ninth method |
| The holidays in a range | `holiday_repo.holidays_in_range(session, start, end)` | query `company_holiday` yourself |
| Locking a balance row | `leave_balance_repo.lock_balance(...)` → `LeaveBalance | None` | use `balances._lock` (raises `LookupError` on the `None` you *expect*) |
| An Admin-only read endpoint | `api/v1/audit_entries.py` + `services/audit.py` | invent a new gate |
| An append-only table + grant | `alembic/versions/0009_rollover_run.py` | copy `0008`'s read-write loop |
| An Admin read-only panel | `features/audit/AuditLogPanel.tsx` | add CSS, add a router |
| The date-range index | `ix_leave_request_start_end` (migration `0006`) | create a second index |

### What is already true, and must stay true

- `available` is **never a column** (`DR-3`). It is `accrued − consumed − reserved`, derived.
- `CHECK (accrued = prorated_entitlement + carried_forward)` is **non-deferrable**, so those three always move in one statement — which is why `set_accrual` exists and why you never write `carried_forward` alone.
- `set_accrual`'s DO-UPDATE branch **now has** an `available >= 0` guard (added by 2.10, `balances.py:320-333`). `deferred-work.md:43` assigned *"the DO-UPDATE lowering path and its per-pair refusal / `admin_review` handling"* to **this story**. The guard is your backstop; your forward check is the gate. If the guard ever fires, you have an AC5 bug.
- `AD-18`: a read path **never** recomputes `leave_days`. This story is the sole exception the invariant names, and only for a Pending or wholly-future-Approved request.
- Six audit-write call sites exist (`leave_requests.py:412,540`; `cancellation.py:226,337,348,394`). You add **none**.
- The `leave_year` of a request is `start_date.year` — always, because `DR-6` forbids spanning two years. `leave_request` has no `leave_year` column, by decision (ERD §4.5).

### Gotchas this codebase has actually produced (2.4 / 2.6 / 2.7 / 2.8 / 2.9 / 2.10 reviews)

- A "read" that commits turns into a write. Read paths open a session and never `commit()` (2.5).
- A mutation's error must be a `DomainError`, not a `ValueError` or an `IntegrityError` reaching the client — that is a 500 and a defect (`AD-5`, `NFR-17`).
- `expire_on_commit=False` is the house session shape.
- A frozen surface test gets **revised with a rationale**, never deleted and never dodged via a sibling module (2.9).
- Pagination is page-1-only across the whole app — a known, accepted, app-wide deferral. Do not fix it here; do not let it block you.
- Concurrent same-id `DELETE /holidays/{id}` currently 500s instead of 404ing (`deferred-work.md:35`). Pre-existing, codebase-wide, **not this story's** to fix — but do not make it worse.

### Project Structure Notes

New files:
```
backend/alembic/versions/0010_admin_review_flag.py
backend/app/domain/recalculation.py
backend/app/repositories/admin_review_flag.py
backend/app/services/recalculation.py
backend/app/api/v1/admin_review_flags.py
backend/tests/domain/test_recalculation.py
backend/tests/integration/test_holiday_recalculation.py
frontend/src/api/adminReviewFlags.ts
frontend/src/features/reviewFlags/ReviewFlagsPanel.tsx
```
Modified:
```
backend/app/repositories/models.py            (+ AdminReviewFlag)
backend/app/repositories/leave_request.py     (+ list_requests_covering, + set_leave_days, revise transition_status docstring)
backend/app/domain/vocabulary.py              (+ CAUSE_HOLIDAY_RECALCULATION, + __all__)
backend/app/services/holidays.py              (recalculate inside the one transaction; return the summary)
backend/app/api/v1/holidays.py                (201→200, 204→200, + summary model, rewrite the stale docstring)
backend/app/api/v1/router.py                  (+ admin_review_flags)
backend/tests/test_scoped_getters.py          (+ 2 EXEMPT entries)
backend/tests/integration/test_holidays.py    (revise the status-code assertions)
frontend/src/App.tsx                          (+ ReviewFlagsPanel)
frontend/src/api/index.ts                     (+ barrel exports)
frontend/src/api/holidays.ts                  (summary return types, + invalidations)
frontend/src/features/holidays/HolidaysPage.tsx (render the summary — AC8)
```
**Untouched:** `backend/pyproject.toml` (`[tool.importlinter]`), `backend/app/main.py` (`CODE_TO_STATUS` — no new error code), `backend/tests/test_scope_matrix.py`, `backend/app/services/balances.py` (the eight stand).

⚠️ **Working-tree note:** Stories 2.9 and 2.10 are `review`, **not committed** (`git status` shows `0008`, `0009`, `services/rollover.py`, `domain/carry_forward.py`, `features/audit/` etc. as untracked/modified). You are building on top of unmerged work. `0010` follows `0009`; `recompute_carry_forward` is 2.10's and is not on `main`.

### References

- Requirements: `epics.md` §Story 2.11 (L1286–1337); `FR-10` (L54); `FR-06` (L46).
- Invariants: `ARCHITECTURE-SPINE.md` `AD-2` (L77), `AD-5` (L95), `AD-6` (L101), `AD-17` (L167), `AD-18` (L173), `AD-19` (L179), `AD-20` (L185), `AD-21` (L191).
- Rationale: `architecture.md` §6.3 (L285–295) — *why* `AD-19` and `AD-20` exist, and the exact failure they prevent (*"The Admin's holiday edit fails with a database error"*).
- Contract: `api-contracts.md` §4.3 (L145–153) — the endpoint table, the `200`-with-a-summary rule, and *"`/admin-review-flags` is **read-only**."*
- Data: `_bmad-output/planning-artifacts/module-4-erd/erd.md` (note: **not** under `architecture/`) — §ADMIN_REVIEW_FLAG (L283–291), §4.4 indexes (L374–380), §6 GAP-4 (L442–444): *"The undefined behavior is gone because the behavior no longer exists."*
- Readiness: `implementation-readiness-report-2026-07-10.md` F-7 (L584–590), F-10 (L696–700) — the two findings that *added* AC1, AC8 and AC9 to this story.
- Deferred work now due: `deferred-work.md:43` (the `set_accrual` DO-UPDATE refusal path — *"belong to Story 2.11/2.12"*), `deferred-work.md:56` (the out-of-band `reserved` 500 — *"reachable only once an out-of-band reserved-adjust endpoint ships"*).

---

## Open Decisions (decide during dev; keep code and tests consistent, and record the call in the Dev Agent Record)

1. **`occurred_at` vs `raised_at`.** The AC says `occurred_at`; ERD §ADMIN_REVIEW_FLAG says `raised_at`. **Recommended: `occurred_at`** — the acceptance criterion is binding, and it matches `audit_entry.occurred_at` and `rollover_run.occurred_at`. Note the ERD divergence in the Dev Agent Record rather than silently picking one.

2. **`leave_year` on the flag.** The AC names it; the ERD's attribute table omits it. **Recommended: include it** (the AC is binding, and a flag that cannot say *which year* it refused is not actionable).

3. **A request recalculated to zero working days** (Landmine 3). The spec does not name this case. **Recommended: refuse the pair and flag it**, leaving the request and balance entirely unchanged — it reuses `AD-19`'s existing "leave unchanged, flag, proceed" mechanic and never fires the `leave_days > 0` CHECK. The alternative — auto-cancelling the request and releasing its days — invents a state transition no requirement grants, and would need an `audit_entry` row (breaking the SM-4 count's premise). Refuse-and-flag is conservative and reversible; the Admin sees it and can act. **This is the one genuinely under-determined point in the story — call it out for the reviewer.**

4. **The in-progress Approved request** (started, not yet finished: `start_date <= today <= end_date`). `AD-18` grants recalculation only to a request *"whose dates lie wholly in the future"* and forbids it for one *"whose dates have already passed."* In-progress is neither. **Recommended: do not recalculate it** — recalculate iff `start_date > today`, the literal reading of the only grant `AD-18` makes. (Note this differs from 2.8's cancellation rule, which keys on `end_date < today`. The two rules are genuinely different questions; do not reuse `is_wholly_past` here without thinking.)

5. **One `cause` value or several.** ERD: *"`cause` — Which refusal raised it: a holiday recalculation, or a policy recalculation."* That distinguishes the *source*, not the reason. **Recommended: a single `HOLIDAY_RECALCULATION` for every refusal this story raises** (negative-available and zero-leave-days alike), with `POLICY_RECALCULATION` reserved for 2.12. If you decide the zero-leave-days case deserves its own value, say so explicitly — it widens a vocabulary 2.12 also consumes.

6. **`carry_forward_cap IS NULL` on a carrying Leave Type** — inherited from Story 2.10 Open Decision #2, which read it as **uncapped**. You reuse `carry_forward_days`, so you inherit the behaviour for free. Do not re-decide it here; just don't contradict it.

7. **Summary body shape.** Not fixed by api-contracts (§4.3 says only *"a summary"*). The shape in Task 5 is a recommendation. Whatever you choose must let AC8 name each refused pair *by Employee and Leave Type*, which means the endpoint must return **names/codes, not bare UUIDs** (the `CancellationRequest` response carries `employee_name` + `leave_type_code` for exactly this reason).

8. **⚠️ A pre-existing gap you should NOT silently fix, but MUST report: `reserve` and `consume_direct` never re-derive `carried_forward`.**
   `AD-6` requires `carried_forward` be recomputed on *"**every** event that can change its inputs."* Story 2.10 wired `recompute_carry_forward` into only the **three sites where `available(Y)` rises** (reject, self-cancel, approve-CR). **Submission lowers `available(Y)` and recomputes nothing** — so after a rollover, a year-`Y` submission leaves `carried_forward(Y+1)` **overstated**. That is a balance that is wrong and will be believed, and it is reachable whenever the rollover runs against a year that is still open (which `run_rollover` warns about but does not refuse — it has no clock).
   **Recommended: do not expand scope to fix it here** — no AC of this story covers it, and the fix belongs beside 2.10's `DR-7a` hook. **But do all three of these:** (a) make your forward check unconditional so this story never 500s because of it; (b) add an entry to `deferred-work.md` naming it; (c) **raise it explicitly in the Dev Agent Record for the reviewer.** If the reviewer judges it in scope, the fix is one more `recompute_carry_forward` call in `submit_leave_request` — but that is the reviewer's call, not a silent widening of this story.

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (1M context) — `claude-opus-4-8[1m]`

### Debug Log References

- `alembic upgrade head` → `downgrade -1` → `upgrade head` — idempotent; `alembic check` reports **no drift** (model ↔ `0010` agree byte-for-byte).
- **AC1 verified LIVE as the app role** (`leaveflow_app`), not read off the migration: `UPDATE` and `DELETE` on `admin_review_flag` both refused with `psycopg.errors.InsufficientPrivilege`; `INSERT`/`SELECT` succeed.
- **AC5 proved NON-VACUOUS** (`test_the_forward_check_is_what_refuses_not_the_constraint`): with `project_forward` monkeypatched to always answer "not refused", the DELETE-refusal scenario walks into the write it was meant to prevent and `set_accrual`'s `available >= 0` guard fires an unhandled `ValueError` — a raw 500. The check is load-bearing, and the backstop really is only a backstop.
- Backend **pytest 469 passed** (from 436), 0 skipped, 0 failed. **import-linter 7/7 kept.** Frontend **build + lint (oxlint) clean.** `python -m seed` exit 0.
- Untouched, as required: `backend/pyproject.toml` (`[tool.importlinter]`), `backend/app/main.py` (`CODE_TO_STATUS` — no new error code), `backend/tests/test_scope_matrix.py`, `backend/app/services/balances.py` (the AD-17 eight stand; the surface test still pins exactly 8).

### Completion Notes List

**All 9 ACs met. No deviations.** The `git diff` on `services/balances.py` is Story 2.10's uncommitted work, not this story's — no ninth balance method was added.

**The shape that delivers AC5.** `domain/recalculation.project_forward` is a pure, DB-free projection of the *entire* per-pair outcome — year `Y` plus every materialized year above it — run **before the first write for that pair**. So the refusal is *predicted*, never *caught*: there is no `try/except IntegrityError`, no `except ValueError` around `adjust_reserved`, and no `begin_nested()` SAVEPOINT anywhere in the recalculation path (all three would have been AC5 violations that shipped green). Once the projection says "not refused", `adjust_reserved`/`adjust_consumed`/`set_accrual` **cannot** raise — which is what keeps AD-5's CHECKs a backstop rather than a gate.

**The seven landmines, each handled:**
1. **Absolute, not delta.** `adjust_reserved`/`adjust_consumed` are passed `balance.reserved + Σ(new − old)` — the row's current total plus the deltas over the *affected* requests — never the delta. (A delta would have zeroed every unaffected request's reservation, and no CHECK would have caught it: a *smaller* `reserved` never violates `available >= 0`.)
2. **`leave_days` and `reserved` move together**, in the same transaction — closing the latent 500 `deferred-work.md:56` predicted by name. Added `set_leave_days` as the **second** sanctioned `leave_request` mutator (AD-18 names exactly this exception), and **revised** `transition_status`'s "the ONE sanctioned mutation" docstring plus the module docstring to say so. The two are disjoint: one moves `status` and never `leave_days`; the other the reverse.
3. **`CHECK (leave_days > 0)`** — the ADD-only zero-working-days case is refused **in the forward check** and flagged; it never reaches the CHECK. It deliberately does **not** raise `ZERO_LEAVE_DAYS` (an error code that *aborts* — exactly what AC4 forbids).
4. **Predicted, not caught** — see above.
5. **Zero audit rows.** `audit_entry_repo` is not imported by `services/recalculation.py`, and its absence is the proof (the `rollover.py` idiom). `test_audit_entries.py`'s `== 14` still passes; a dedicated test measures the audit count across both a clean recalculation *and* a refused one.
6. **The breaking change shipped as a revision, not a route-around.** `POST /holidays` 201→200 and `DELETE /holidays/<id>` 204→200+summary; the 5 assertions in `test_holidays.py` were **revised** (with a rationale in the module docstring), both React hooks retyped, and the two now-stale docstrings (`api/v1/holidays.py`, `api/holidays.ts`) rewritten.
7. **No ninth balance method, `[tool.importlinter]` untouched.** Orchestration lives in the new `services/recalculation.py`; the 8-method surface test and the 7 contracts both still pass.

**Both refusal paths are real, and both are tested.** The DELETE refusal (negative Available in an already-spent later year) *and* two ADD refusals — the zero-working-days case, and the **stale-high `carried_forward(Y+1)`** case, which proves a POST is not a documented no-op and yields a clean `200` + flag rather than a 500.

**Open Decisions — all adopted as recommended:**
1. `occurred_at`, not the ERD's `raised_at` (the AC is binding; it matches `audit_entry`/`rollover_run`). **ERD divergence noted here rather than silently resolved.**
2. `leave_year` **included** on the flag (the AC names it; a flag that cannot say which year it refused is not actionable).
3. A request recalculated to **zero working days → refuse the pair and flag it.** *This is the one genuinely under-determined point in the story and is called out for the reviewer.* Auto-cancelling would invent a state transition no requirement grants and would need an audit row (breaking SM-4's premise). The consequence — such a request keeps its stale `leave_days` forever with no first-class way to resolve it — is now logged in `deferred-work.md`.
4. **In-progress Approved requests are NOT recalculated.** `list_requests_covering` keys on `start_date > today`, the literal reading of AD-18's only grant. Deliberately *not* Story 2.8's `is_wholly_past` (`end_date < today`) — reusing it would have silently recalculated leave somebody is currently taking.
5. A **single** `CAUSE_HOLIDAY_RECALCULATION` for every refusal this story raises (negative-available and zero-days alike). `CAUSE_POLICY_RECALCULATION` is left for 2.12.
6. `carry_forward_cap IS NULL` on a carrying type = **uncapped** — inherited for free by reusing `carry_forward_days`, not re-decided.
7. Summary shape as recommended, carrying **names and codes, not bare UUIDs** (AC8 requires the screen to *name* each refused pair).

**⚠️ RAISED FOR THE REVIEWER — Open Decision #8, a pre-existing gap I did NOT silently fix.**
`AD-6` requires `carried_forward` be recomputed on *"every event that can change its inputs"*, but Story 2.10 wired `recompute_carry_forward` into only the **three sites where `available(Y)` rises**. **`reserve` (submission) and `consume_direct` LOWER `available(Y)` and recompute nothing** — so after a rollover, a year-`Y` submission leaves `carried_forward(Y+1)` **overstated**. That is a balance that is wrong and will be believed, and it is reachable whenever the rollover runs against a still-open year (which `run_rollover` warns about but does not refuse — it has no clock).

I did the three things the story asked instead of widening scope: **(a)** the forward check runs **unconditionally on both paths**, so this story never 500s because of it (and `test_an_ADD_refuses_when_carried_forward_is_STALE_HIGH` pins that); **(b)** it is written up in `deferred-work.md`; **(c)** it is raised here. **The fix is one more `recompute_carry_forward` call in `submit_leave_request` — but that is the reviewer's call, not a silent widening of this story.**

**Also flagged:** `ARCHITECTURE-SPINE.md:317-321`'s ERD diagram is **STALE** — it shows `ADMIN_REVIEW_FLAG { text cause; uuid subject_id; timestamptz resolved_at }`, a single polymorphic `subject_id` and a `resolved_at`. Both contradict AD-20's own prose in the same file (`:185`), `erd.md:283-291`, ERD GAP-4, and **AC1**. I built from AC1 (the `employee_id` + `leave_type_id` **pair**, and **no** `resolved_at` — which would have silently justified the `UPDATE` grant AC1 forbids). The diagram should be corrected.

### File List

**New**
```
backend/alembic/versions/0010_admin_review_flag.py
backend/app/domain/recalculation.py
backend/app/repositories/admin_review_flag.py
backend/app/services/recalculation.py
backend/app/services/admin_review_flags.py
backend/app/api/v1/admin_review_flags.py
backend/tests/domain/test_recalculation.py
backend/tests/integration/test_holiday_recalculation.py
frontend/src/api/adminReviewFlags.ts
frontend/src/features/reviewFlags/ReviewFlagsPanel.tsx
```

**Modified**
```
backend/app/repositories/models.py                    (+ AdminReviewFlag)
backend/app/repositories/leave_request.py             (+ list_requests_covering, + set_leave_days, revised transition_status + module docstrings)
backend/app/domain/vocabulary.py                      (+ CAUSE_HOLIDAY_RECALCULATION, + __all__)
backend/app/services/holidays.py                      (recalculate inside the one transaction; + HolidayView/HolidayCommandResult)
backend/app/api/v1/holidays.py                        (201→200, 204→200, + summary models, rewrote the stale docstring)
backend/app/api/v1/router.py                          (+ admin_review_flags)
backend/tests/test_scoped_getters.py                  (+ 2 EXEMPT entries, with rationales)
backend/tests/test_migrations_insert_nothing.py       (+ 0010 in the ordered chain)
backend/tests/integration/test_holidays.py            (revised the status-code + body assertions)
backend/tests/integration/test_leave_request_submit.py (revised the leave_request mutation-surface assertion)
backend/tests/integration/test_schema_1_2.py          (+ admin_review_flag)
backend/tests/integration/test_migration_smoke.py     (HEAD_REVISION → 0010_admin_review_flag)
frontend/src/App.tsx                                  (+ ReviewFlagsPanel)
frontend/src/api/index.ts                             (+ barrel exports)
frontend/src/api/holidays.ts                          (summary return types, + 4 invalidations)
frontend/src/features/holidays/HolidaysPage.tsx       (render the summary — AC8)
_bmad-output/implementation-artifacts/deferred-work.md (+ 4 entries, incl. Open Decision #8)
```

---

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-14 | Story created — context engine analysis; status `ready-for-dev`. |
| 2026-07-14 | Implemented. All 9 ACs met, no deviations. `admin_review_flag` (migration `0010`, the third append-only table with its own `GRANT INSERT, SELECT` — AC1 verified live as the app role). Pure `domain/recalculation.project_forward` delivers AC5: the refusal is **predicted**, never caught. Per-pair engine in `services/recalculation.py` (zero audit rows — SM-4's `== 14` intact). Breaking change shipped: `POST /holidays` 201→200, `DELETE /holidays/<id>` 204→200 + summary; the affected tests and React hooks **revised**, not deleted. `GET /admin-review-flags` (Admin-only, no new error code, `main.py` untouched). Frontend: AC8 summary on the Holidays screen + AC9 Review Flags panel. Backend pytest 469 passed (from 436); import-linter 7/7; frontend build + lint clean; seed exit 0. Open Decision #8 (a pre-existing 2.10 carry-forward gap) contained, logged in `deferred-work.md`, and **raised for the reviewer rather than silently fixed**. Status → `review`. |
</content>
</invoke>
