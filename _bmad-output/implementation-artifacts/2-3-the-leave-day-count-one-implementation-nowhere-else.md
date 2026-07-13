---
baseline_commit: 70147720d0e277acaf2ab0bd00415d30cdbaaec4
---

# Story 2.3: The Leave Day Count — One Implementation, Nowhere Else

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Employee,
I want a request to cost only the working days inside its range,
so that a weekend or a company holiday never comes out of my balance.

## Acceptance Criteria

**Literal ACs (from epics.md#Story 2.3):**

1. **(One pure function)** Given `domain/calendar.py`, when it is inspected, then it exposes exactly one function, `count_leave_days`, taking a date range and the holiday calendar and returning a whole number; **and** it imports no ORM, no web framework and performs no I/O (`AD-1`, `AD-2`, `NFR-08`, `DR-2`).
2. **(The canonical boundary case)** Given a Friday-to-Tuesday range spanning a Saturday, a Sunday, and a Monday that is a Company Holiday, when the count is computed, then it is `2` (`FR-08`, `SM-2`).
3. **(All-excluded range)** Given a range consisting only of weekend days and Company Holidays, when the count is computed, then it is `0` (`SM-2`).
4. **(Boundary edges)** Given a range that begins and ends on non-working days, and a single-day range, when each count is computed, then both are correct at the boundary (`SM-2`).
5. **(No database fixture)** Given `tests/domain/`, when the test suite runs, then these tests pass with **no database fixture** (`SM-2`, `NFR-15`, spine *Testing*).
6. **(The client never computes a day count)** Given the frontend source, when it is searched, then no module references a weekday or a Company Holiday — the client never computes a day count (`AD-2`).

**Derived ACs (implied, non-negotiable — the story must leave the system correct, not merely satisfy the literal ACs):**

7. **(Inclusive range, `date.weekday()` semantics)** The range `[start, end]` is **inclusive of both endpoints**. A day is a Working Day iff `d.weekday() < 5` (Mon–Fri) **and** `d` is not in the holiday calendar. Weekend = Saturday (`weekday()==5`) and Sunday (`weekday()==6`), for every Employee (PRD glossary *Working Day*, `DR-1`).
8. **(Whole-number return, `INTEGER` discipline)** `count_leave_days` returns a Python `int` — never a float, never `Decimal`. A Leave Day is a whole number and no fractional quantity is expressible (`DR-10`, spine *Conventions* "Leave quantities · INTEGER everywhere").
9. **(Deterministic, side-effect-free, holiday-set order-independent)** The function is a pure function of its arguments: same inputs → same output, no mutation of the passed calendar, no reliance on `today`/clock/timezone, and the result is independent of the order or duplication of the holiday collection.
10. **(Empty/inverted range is `0`, not an error)** A range where `end < start` yields `0` (the inclusive iteration is empty). Range *validity* — `start <= end`, contiguity, the zero-day-refusal — is enforced upstream at submission (Story 2.6), **not** in this pure counter. This function never raises on its inputs.
11. **(The frontend guard is enforced, not declared)** AC6 is realized as a **backend `pytest` guard** that scans `frontend/src/` and fails the build if the client acquires weekday-computation logic — because `pytest` is the build and there is no frontend test runner. The guard targets the JS weekday primitives (`getDay`/`getUTCDay`), **not** the English words "weekday"/"holiday" (which appear legitimately in rule-documenting comments and in the holidays *data* feature). See Dev Notes "The frontend guard — and the trap in it".

## Tasks / Subtasks

- [x] **Task 1 — The pure domain function `count_leave_days`** (AC: 1, 2, 3, 4, 7, 8, 9, 10)
  - [x] New file `backend/app/domain/calendar.py`. Module docstring names what it serves (`FR-08`, `DR-1`, `DR-2`, `AD-2`, `AD-18`, `NFR-08`) and states the load-bearing invariant: **this is the only module in the entire system that knows what a weekend or a Company Holiday is** (`AD-2`).
  - [x] Define exactly one **public** function:
    ```python
    def count_leave_days(
        start: datetime.date,
        end: datetime.date,
        holidays: Collection[datetime.date],
    ) -> int:
    ```
    Inclusive `[start, end]`. Build `holiday_set = set(holidays)` once for O(1) membership. Iterate day by day (`start` through `end` inclusive); a day counts iff `day.weekday() < 5 and day not in holiday_set`. Return the count as an `int`.
  - [x] **Weekend is `date.weekday()`, not `isoweekday()`.** `weekday()` returns Mon=0 … Sun=6, so `>= 5` is Sat/Sun. Do not use `isoweekday()` (Mon=1 … Sun=7) — the off-by-one would misclassify. Add a one-line comment fixing this.
  - [x] **Do not mutate `holidays`.** Copy into a local `set`. The caller (Story 2.5/2.6 service) passes a collection it still owns.
  - [x] **Iterate with `datetime.timedelta(days=1)`** from `start` while `<= end`. Do not use `range()` over ordinals unless you convert both ends via `.toordinal()`/`.fromordinal()` correctly — the `timedelta` loop is the clear idiom. An `end < start` range simply never enters the loop → returns `0` (AC10).
  - [x] **Exactly one function is *exposed*.** If a helper aids readability it must be `_`-prefixed (module-private) — but prefer inlining; the loop is short enough that no helper is needed. AC1 ("exposes exactly one function") is inspected, and Story 2.5 will add a *second* function to this same module (see forward reference) — keep this one minimal and self-contained.
  - [x] `from __future__ import annotations` is unnecessary; use `import datetime` and `from collections.abc import Collection`. **No import of `app.repositories`, `sqlalchemy`, `fastapi`, or anything I/O** — the import-linter "domain/ is pure" contract (already covering `app.domain.*`) fails the build otherwise.
- [x] **Task 2 — Pure-domain tests** (AC: 2, 3, 4, 5, 7, 8, 9, 10)
  - [x] New file `backend/tests/domain/test_calendar.py`. **No database fixture, no `import app.main`, no ORM** — this is the pure core (`tests/domain/conftest.py` deliberately defines no `db_connection`; reaching for one means the rule is in the wrong layer). Import only `from app.domain.calendar import count_leave_days` and `datetime`.
  - [x] **AC2 — the canonical case:** Fri → Tue inclusive, with the Saturday and Sunday between them, and the Monday supplied as a holiday. Assert `== 2` (only the Friday and the Tuesday count). Pick real dates and state them in the test (e.g. 2026-08-14 Fri … 2026-08-18 Tue; holiday = 2026-08-17 Mon). **Verify the weekday of each chosen date in the test's own comment** so the fixture cannot silently rot.
  - [x] **AC3 — all excluded:** a Sat+Sun range → `0`; a range that is only weekends and holidays → `0`.
  - [x] **AC4 — boundaries:** (a) a range that *starts* on a Sunday and *ends* on a Saturday, asserting the interior working days are counted and the non-working endpoints are not; (b) a single-day range on a Working Day → `1`; (c) a single-day range on a weekend → `0`; (d) a single-day range on a holiday → `0`.
  - [x] **AC7/AC8 — semantics:** assert Saturday and Sunday are both excluded (a full Mon–Sun week with no holidays → `5`); assert the return type is `int` (`isinstance(result, int)` and `not isinstance(result, bool)`).
  - [x] **AC9 — purity:** call twice with the same args → equal results; pass the holidays as a `list` with a **duplicate** and in **scrambled order** and assert the count matches the same holidays as a `set`; assert the passed `holidays` object is unchanged after the call (no mutation).
  - [x] **AC10 — inverted range:** `end < start` → `0`, no exception.
  - [x] **Empty holiday calendar:** a Mon–Fri range with `holidays=[]` (and with `holidays=set()`) → `5`. Exercise both an empty `list` and empty `set` to prove the `Collection` contract.
  - [x] Each test has a one-line docstring naming the AC it closes (house style — see `tests/domain/test_scoping.py`).
- [x] **Task 3 — The frontend day-count guard (backend-enforced)** (AC: 6, 11)
  - [x] New file `backend/tests/test_frontend_no_client_day_count.py` (a repo-wide static guard, sits beside `test_migrations_insert_nothing.py`/`test_vocabulary_literals.py` — the project's established "pytest scans a source tree" idiom).
  - [x] Resolve `FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"` (from `backend/tests/` up to repo root, then into `frontend/src`). Verify this path resolves to the real directory before writing the assertion.
  - [x] If `FRONTEND_SRC` does not exist, `pytest.skip("frontend/src not present in this checkout")` — mirror how integration tests skip when their dependency is absent. The monorepo has it; a backend-only checkout would not.
  - [x] Walk every `*.ts` and `*.tsx` file under `FRONTEND_SRC` (recursively; **exclude** `*.md`, `*.css`, and any `__tests__`/`node_modules`). For each, assert it contains **neither `getDay` nor `getUTCDay`** — the only JavaScript primitives that yield a day-of-week, and therefore the necessary precondition for the client to reimplement weekend logic. On failure, name the offending file and line and cite `AD-2`.
  - [x] **Do NOT grep for the words "weekday", "weekend", "Saturday", "Sunday", or "holiday".** They appear legitimately (see Dev Notes "the trap"): `src/features/README.md` and `src/api/client.ts` *document* the AD-2 rule in prose, and `src/features/holidays/` + `src/api/holidays.ts` handle holidays as **display data**. A word-based guard would fail on the very comments that enforce the rule and on Story 2.2's shipped feature. The guard is about *computation primitives*, not vocabulary.
  - [x] Module docstring explains the choice: AD-2 forbids the client from *computing* a day count; the count, its excluded dates, their reasons and the holiday names all arrive from the server's preview endpoint (Story 2.5). Forbidding `getDay`/`getUTCDay` is the precise, low-false-positive enforcement; holiday *data* rendering is allowed.
- [x] **Task 4 — Confirm the existing armed guards still pass** (AC: 1)
  - [x] `tests/test_architecture.py` (import-linter): the "domain/ is pure (AD-1)" contract already covers `app.domain.*` via `source_modules = ["app.domain"]` — **no contract change is needed**, but confirm `calendar.py` introduces no forbidden import (it must not import `sqlalchemy`, `fastapi`, `app.repositories`, etc.). A violation fails this test.
  - [x] `tests/test_scoped_getters.py`: scans `app.repositories` only, not `app.domain` — `count_leave_days` is **not** flagged (it lives in `domain/`, takes no `session`, returns no rows). No change.
  - [x] `tests/test_vocabulary_literals.py`: this story introduces **no new error code** (the zero-day-range *refusal* is Story 2.6's submission concern, not this pure counter). No change.
  - [x] No migration, no schema change, no `HEAD_REVISION` bump — this story touches no table.
- [x] **Task 5 — Prove it** (all ACs)
  - [x] Backend: from `backend/`, run `.venv/bin/python -m pytest` — all green. The domain tests (Task 2) run in **milliseconds with no DB**; the frontend guard (Task 3) runs against the working tree; the import-linter contracts run in-suite via `test_architecture.py`. Integration tests skip with a reason if the stack is down — that is expected and does not gate this story (it adds no integration surface).
  - [x] Frontend: from `frontend/`, run `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean. **This story adds no frontend code**; the frontend proof is that the existing build still passes and the new guard (Task 3) is green. No manual click-through applies (there is no new UI).
  - [x] State in Completion Notes: the exact backend pass count, that the domain tests ran DB-free, and that the frontend guard is armed and passing.

## Dev Notes

### What this story is — and what makes it different from 2.1/2.2

Stories 2.1 (leave types) and 2.2 (holidays) were CRUD stacks. **2.3 is not.** It adds one pure function to the functional core and one guard. There is no table, no migration, no endpoint, no repository, no service, no React screen. The value — and the entire risk — is in three places:

1. **Correctness at the boundaries** (`SM-2`): the count must be right for a weekend, a holiday, endpoints on non-working days, and a single day. This is one of the five correctness metrics of the whole product.
2. **Purity** (`AD-1`, `NFR-08`): `domain/calendar.py` imports no ORM, no web framework, does no I/O, and its tests touch no database. The import-linter contract already arms this; do not weaken it.
3. **The client never recomputes it** (`AD-2`): the reason the function exists *only* on the server is that a client copy would drift the instant the holiday calendar changed. The frontend guard makes that structural, not aspirational.

### The exact rule (DR-1, DR-2, glossary)

> **DR-1.** The **Leave Day** count of a date range is the number of **Working Days** it contains. Weekend days (Saturday, Sunday) and **Company Holidays** are excluded.
> **DR-2.** The calculation is a pure function of the date range and the holiday calendar. It has exactly one implementation, and every path that touches a **Leave Balance** calls it. A second implementation of weekend-or-holiday logic anywhere in the codebase is a defect.
> **Working Day** — A date that is neither a weekend day nor a **Company Holiday**. Saturday and Sunday are non-working days for every **Employee**.

So: `count_leave_days(start, end, holidays)` = `len([d for d in inclusive_range(start, end) if d.weekday() < 5 and d not in set(holidays)])`. The canonical worked example (PRD §Leave Requests, `SM-2`): *"A Friday-to-Tuesday request spanning a Saturday, a Sunday, and a Monday that is a Company Holiday costs **2** Leave Days."* — Friday + Tuesday count; Sat, Sun, and the holiday Monday do not. This is AC2, verbatim, and it is the single most important assertion in the story.

### Signature design decisions (the parts the AC leaves to you)

- **Two `date` params, inclusive.** `count_leave_days(start, end, holidays)`. The AC says "a date range"; the codebase has no `DateRange` value object and this story should not invent one. Two inclusive `datetime.date` endpoints is the clear, minimal shape. Inclusivity matches the domain: a one-day request over a single Working Day costs 1.
- **`holidays: Collection[datetime.date]`.** Accept any collection; copy into a `set` internally for O(1) membership and order-independence (AC9). Type it `Collection[datetime.date]` (from `collections.abc`), not `list` or `set` specifically — the caller (a service in Story 2.5/2.6 loading `company_holiday` rows) should not be forced into a concrete container. Holiday **names** are irrelevant to the *count* and are not a parameter here; names surface only in the preview breakdown (Story 2.5).
- **Returns `int` (DR-10).** A Leave Day is a whole number; `INTEGER` everywhere (spine *Conventions*). No float, no `Decimal`. `len(...)` already yields `int`.
- **Never raises on inputs (AC10).** `end < start` → `0`. Range *validity* (start ≤ end, contiguity, the zero-day-refusal at submission) belongs to Story 2.6's service, not to this pure counter. Keeping validation out of the core is what makes it reusable by preview, submit, and recalculation alike.
- **No clock, no timezone.** The function reads only its arguments. It must not call `date.today()` or anything time-dependent (AC9). `holiday_date` and the range are already `datetime.date` (AD-12) — pure calendar dates, no `TIMESTAMPTZ`, no tz math.

### The frontend guard — and the trap in it (AC6, AC11)

AC6 says: *"the frontend source … no module references a weekday or a Company Holiday."* Read literally against a `grep`, this AC **fails on the code that already enforces it**:

- `frontend/src/features/README.md` (line 10) literally says *"no module under `src/` may reference a weekday or a Company Holiday"* — it uses the forbidden words to state the rule.
- `frontend/src/api/client.ts` (line 8) carries the same AD-2 note in a comment.
- Story 2.2 shipped `frontend/src/features/holidays/HolidaysPage.tsx` and `frontend/src/api/holidays.ts`, which reference **holidays as display data** (a `Holiday` type, a list, a `<input type="date">`). That is allowed by AD-2: the client *renders* holidays the Admin manages; it never *computes a day count* from them.

So a word-based guard is wrong twice over. The correct guard enforces the *intent* — the client never computes a day count — by forbidding the **JavaScript weekday primitives** `getDay` / `getUTCDay` in `frontend/src/**/*.{ts,tsx}`. Those are the necessary precondition for reimplementing weekend logic; there is no way to compute "is this Saturday?" in JS without one. Holiday-set membership without a weekday check cannot produce a Leave Day count either, and the client only receives holidays as data. This makes the guard precise and false-positive-free, and it fits the project's house idiom exactly (`test_migrations_insert_nothing.py` AST-scans migrations; `test_vocabulary_literals.py` scans `app/`+`seed/` for stray literals; this scans `frontend/src` for the day-count primitive).

**Today the guard passes trivially** — the frontend has no `getDay`/`getUTCDay` (verified: `grep -rniE 'getday|getutcday' frontend/src` is empty). Like `test_scoped_getters.py`, its value is as an **armed guardrail**: the moment Story 2.5's preview screen (or any later work) is tempted to compute a count client-side, the build fails. That is the whole point of AD-2.

### Forward reference — the preview breakdown is Story 2.5's, in this same module

AD-2 also requires the preview endpoint to return *each excluded date with its reason (`WEEKEND`/`HOLIDAY`) and the holiday's name* (api-contracts §4.4):

```json
{ "leave_days": 2,
  "excluded_dates": [
    { "date": "2026-08-15", "reason": "WEEKEND" },
    { "date": "2026-08-17", "reason": "HOLIDAY", "name": "Independence Day (observed)" } ],
  "available_before": 6, "available_after": 4 }
```

That breakdown logic **also** knows about weekends and holidays, so by AD-2 it too must live in `domain/calendar.py` — **but it is Story 2.5's work, not this story's.** Story 2.3 ships **only** `count_leave_days` returning an `int` (the AC says "exactly one function … returning a whole number"). Story 2.5 will add a companion (e.g. a `describe_leave_days` / an excluded-dates function) to the same module, and the two may share a `_`-prefixed helper then. **Do not build the excluded-dates breakdown, the reasons enum, or any preview shape now.** This is a disclosed forward reference — the same discipline Story 2.2 used to defer the `200`-with-summary form to Story 2.11, and Story 2.1 used to defer `PATCH /leave-types`. Keep 2.3 to one function.

### Architecture compliance (guardrails — violating any of these fails `pytest`)

- **AD-1 / NFR-08 — `domain/` is pure.** `calendar.py` imports no ORM (`sqlalchemy`, `psycopg`, `alembic`), no web framework (`fastapi`, `starlette`, `httpx`, `requests`), no `app.repositories`, no `app.core`, and performs no I/O. Enforced by the import-linter "domain/ is pure (AD-1)" contract, which already covers `app.domain.*` (no contract edit needed) and fails `test_architecture.py` on violation. [Source: ARCHITECTURE-SPINE.md#AD-1; backend/pyproject.toml §importlinter contract 3]
- **AD-2 — the server is the sole authority on a Leave Day count.** Exactly one function knows what a weekend or a Company Holiday is; every day-count path calls it; the client obtains every count from the preview endpoint and references no weekday/holiday computation. [Source: ARCHITECTURE-SPINE.md#AD-2]
- **AD-18 — the count is frozen on the request (context, not this story's code).** At admission (Story 2.6) `leave_request.leave_days` is set once by *this* function and never recomputed by a read path. 2.3 provides the function; 2.6 does the freezing. Relevant so you understand *why* the function must be deterministic and side-effect-free. [Source: ARCHITECTURE-SPINE.md#AD-18]
- **AD-12 / DR-2a — dates are `DATE`, never instants.** Inputs are `datetime.date` (the range endpoints and every holiday), never `datetime.datetime`/`TIMESTAMPTZ`. No timezone arithmetic anywhere in the function. [Source: ARCHITECTURE-SPINE.md#AD-12]
- **DR-10 / Conventions — Leave quantities are `INTEGER`.** The return is a Python `int`. No float or `Decimal` in the domain, schema, or API. [Source: ARCHITECTURE-SPINE.md#Conventions ("Leave quantities · INTEGER everywhere"); erd.md §Leave Day]
- **Naming — `verb_noun`.** Domain functions are `verb_noun`: `count_leave_days` (the spine names this exact function as the example). Module `snake_case`: `calendar.py`. [Source: ARCHITECTURE-SPINE.md#Consistency Conventions]
- **Testing — `tests/domain/` runs with no database.** The new `test_calendar.py` defines/uses no `db_connection` fixture and imports no ORM. `tests/domain/conftest.py` deliberately defines none; pytest resolves fixtures upward only, so nothing under `tests/domain/` can reach the integration DB fixture — by design. [Source: ARCHITECTURE-SPINE.md#Testing; backend/tests/domain/conftest.py]

### Library / framework requirements (pinned — do NOT upgrade)

Python `3.13.*`; pytest `9.1.1`; import-linter `2.13`. **This story needs no runtime dependency beyond the standard library** (`datetime`, `collections.abc`). Frontend: no change (React `19.2.7`, Vite `8.1.4`, TypeScript `6.0.3` — the guard reads source, it adds nothing). [Source: backend/pyproject.toml; frontend/package.json; ARCHITECTURE-SPINE.md#Stack]

### File structure (what to create / edit)

**New (backend):**
- `backend/app/domain/calendar.py` — the `count_leave_days` pure function.
- `backend/tests/domain/test_calendar.py` — DB-free boundary tests.
- `backend/tests/test_frontend_no_client_day_count.py` — the AD-2 client guard.

**Edit:** none required. No migration, no `vocabulary.py`, no `main.py`, no router, no schema-snapshot test, no frontend file. (Confirm the existing import-linter and scoped-getter guards still pass — Task 4 — but they need no edits.)

Naming: module `snake_case` (`calendar.py`); domain function `verb_noun` (`count_leave_days`); test files `test_*.py`. `domain/` currently holds `__init__.py`, `errors.py`, `vocabulary.py`; `calendar.py` is the first *rule* module, and the reason `tests/domain/` was created empty in Story 1.1 ("so that the first domain rule has an unambiguous home for its tests"). [Source: ARCHITECTURE-SPINE.md#Source tree; backend/app/domain/; backend/tests/domain/conftest.py]

### Testing requirements

- **`tests/domain/` is DB-free (AC5, NFR-15, SM-2).** `test_calendar.py` imports only `datetime` and `count_leave_days`. No `import app.main`, no ORM, no fixture from `tests/integration/`. These run in milliseconds — that speed is the point (spine *Testing*). [Source: backend/tests/domain/conftest.py]
- **`pytest` is the build (no CI).** The import-linter contracts (`test_architecture.py`) and the new frontend guard run **inside** the suite; a purity break or a client `getDay` fails `pytest`, not a separate step. [Source: backend/tests/test_architecture.py; README.md#Tests]
- **Assert weekdays in the test's own comments.** A date-based fixture rots silently if 2026-08-14 is later mis-remembered as a Thursday. State the weekday of each chosen date inline so a wrong date fails the reader, not just the run.
- **Cover the `Collection` contract both ways.** Pass holidays as a `list` (with a duplicate, scrambled) and as a `set`, and assert equal results (AC9) — this proves the internal `set(holidays)` copy and order-independence.
- **No integration test is added.** This story has no endpoint, schema, or transaction. Do not create a `tests/integration/test_calendar.py`.

### Previous story intelligence (2.1, 2.2, and the 1.x domain tests)

- **The pure-core test idiom already exists — copy its shape.** `tests/domain/test_scoping.py` and `test_authorization.py` are DB-free, import from `app.domain`/`app.repositories.scoping`, use small structural fakes, and each test has a one-line docstring naming the AC. Mirror that style for `test_calendar.py`. [Source: backend/tests/domain/test_scoping.py]
- **AD-2 was already anticipated in the frontend.** `frontend/src/features/README.md` and `frontend/src/api/client.ts` already carry the "no weekday/holiday on the client" note (written in Story 1.1). This story *arms the enforcement* those comments describe. Do not delete or duplicate those notes. [Source: frontend/src/features/README.md:10; frontend/src/api/client.ts:8]
- **Frontend proof reality (1.5/1.6/1.8/2.1/2.2):** there is no frontend test runner; the proof is `npm run build` + `npm run lint` clean. This story adds no UI, so there is no click-through to declare — the frontend contribution is the *backend* guard plus an unchanged, still-green build.
- **Disclosed forward references are the house discipline.** 2.1 deferred `PATCH /leave-types`; 2.2 deferred the `200`-with-summary holiday endpoints to 2.11. 2.3 defers the preview excluded-dates breakdown to 2.5 — same pattern, same module. Ship exactly one function.

### Git intelligence

Head is `7014772 feat(story-2.1): Leave Types as Configuration`. **Story 2.2's work (the `company_holiday` stack) is implemented and marked `done` in sprint-status but is NOT yet committed** — its files show as untracked/modified in `git status` (`?? backend/alembic/versions/0004_company_holiday.py`, `?? backend/app/api/v1/holidays.py`, `?? backend/app/services/holidays.py`, `?? backend/app/repositories/holiday.py`, `?? frontend/src/features/holidays/`, plus modified `models.py`, `vocabulary.py`, `main.py`, `router.py`, tests, `App.tsx`, `api/index.ts`). This story is **independent of that tree** — `domain/calendar.py` imports nothing from the holiday stack, and its tests pass a plain `set[date]`, not `CompanyHoliday` rows (the service that loads real holiday rows and calls `count_leave_days` is Story 2.5/2.6). But for a clean, unambiguous baseline, **commit Story 2.2 first** (`feat(story-2.2): the company holiday calendar`) before starting 2.3 — same situation 2.2 recorded about 2.1. The `baseline_commit` in this file's front-matter is HEAD (`70147720…`); if 2.2 is committed first, that is fine — 2.3 adds only new files and depends on none of 2.2's. [Source: `git status`, `git log`]

### Project structure notes

No structural conflicts. `domain/calendar.py` is the module the spine's source tree already names ("`domain/` # PURE: calendar, proration, carry_forward, balance, vocabulary") and the module `AD-2`/`NFR-08` designate by name. `tests/domain/` was created empty in Story 1.1 precisely to host this. The two guard tests sit beside the existing repo-wide guards (`test_migrations_insert_nothing.py`, `test_vocabulary_literals.py`, `test_scoped_getters.py`). No new dependency, no CSS, no migration, no schema snapshot to bump.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: The Leave Day Count — One Implementation, Nowhere Else]
- [Source: _bmad-output/planning-artifacts/prds/prd-LeaveFlow-2026-07-09/prd.md#DR-1, #DR-2, #NFR-08, #SM-2, glossary (Working Day, Leave Day)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-1, #AD-2, #AD-12, #AD-18, #Conventions, #Testing, #Source tree, #Consistency Conventions]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md#4.4 (preview response shape — Story 2.5's, shown here only for the forward reference)]
- [Source: _bmad-output/planning-artifacts/module-4-erd/erd.md §Leave Day (whole number, DR-10), #COMPANY_HOLIDAY (holiday_date is a DATE, not a Working Day)]
- [Source: backend/pyproject.toml — [tool.importlinter] contract 3 "domain/ is pure", covers app.domain.*]
- [Source: backend/tests/domain/conftest.py — the DB-free contract for this test package]
- [Source: backend/tests/domain/test_scoping.py, test_authorization.py — the pure-core test idiom to mirror]
- [Source: backend/tests/test_migrations_insert_nothing.py, test_vocabulary_literals.py — the "pytest scans a source tree" guard idiom the frontend guard follows]
- [Source: frontend/src/features/README.md:10, frontend/src/api/client.ts:8 — the AD-2 client note this story arms]
- [Source: _bmad-output/implementation-artifacts/2-2-the-company-holiday-calendar.md — the immediately prior story; holidays as client display data, and the disclosed-forward-reference discipline]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4-8[1m]) — BMAD dev-story workflow.

### Debug Log References

- Verified the canonical fixture dates against the real calendar before writing any assertion (`python -c "datetime.date(2026,8,14).strftime('%A')"` → Friday, … 08-15 Saturday, 08-16 Sunday, 08-17 Monday, 08-18 Tuesday). The weekday of every chosen date is stated inline in `test_calendar.py` so the fixture cannot rot silently.
- Confirmed `FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"` resolves to the real directory (`/…/LeaveFlow/frontend/src`, `exists=True`) before writing the guard assertion.
- Ran `lint-imports` directly: **7 contracts kept, 0 broken**; the "domain/ is pure (AD-1)" contract covers the new `app.domain.calendar`. AST-confirmed `calendar.py` imports only `collections.abc` and `datetime` (no `sqlalchemy`, `fastapi`, `app.repositories`, `app.core`).
- Self-inflicted trap caught during authoring: an "innocent" negative case in the guard-the-guard test originally contained the literal token `getDay` inside a comment string, which `\bgetDay\b` correctly matched — replaced with a `toLocaleDateString()` example so the false-positive assertion is honest.

### Completion Notes List

Story 2.3 is a functional-core story, not a CRUD stack: **no table, no migration, no endpoint, no repository, no service, no React screen.** It ships exactly one pure function plus one armed guard. All 11 ACs (6 literal + 5 derived) satisfied.

- **AC1 / AC7–AC10 (one pure function):** `backend/app/domain/calendar.py` exposes exactly one public function, `count_leave_days(start, end, holidays) -> int`. Inclusive `[start, end]`; a day counts iff `day.weekday() < 5 and day not in set(holidays)`. Iterates with `datetime.timedelta(days=1)`; `weekday()` (Mon=0…Sun=6), never `isoweekday()`. Copies `holidays` into a local `set` (no mutation, order- and duplicate-independent). Reads no clock/timezone. Returns `len`-style `int`. `end < start` → `0`, never raises. Imports only `collections.abc` + `datetime`.
- **AC2 / SM-2 (canonical boundary):** Fri 2026-08-14 → Tue 2026-08-18 with Sat/Sun between and Mon 08-17 supplied as a holiday → **2**. The single most important assertion; passes.
- **AC3 (all-excluded):** a Sat–Sun range → 0; a Sat→Mon range with the Monday as a holiday → 0.
- **AC4 (boundary edges):** Sunday-start/Saturday-end range counts only the interior Mon–Fri (→5); single Working Day → 1; single weekend day → 0; single holiday → 0.
- **AC5 (no DB fixture):** `backend/tests/domain/test_calendar.py` imports only `datetime` + `count_leave_days`; **14 tests run in 0.01s with no `db_connection`** — `tests/domain/conftest.py` defines none and pytest resolves fixtures upward only.
- **AC6 / AC11 (client never computes a day count):** realized as backend guard `backend/tests/test_frontend_no_client_day_count.py` — scans every `frontend/src/**/*.{ts,tsx}` (excluding `node_modules`/`__tests__`) and fails on `getDay`/`getUTCDay`, the JS day-of-week primitives. It deliberately does **not** grep the words "weekday"/"holiday" (which appear legitimately in AD-2 rule-documenting prose and in Story 2.2's holidays *data* feature). Includes a guard-the-guard test proving the pattern fires on real primitives and not on innocent prose, plus a "did the scan read files" assertion. Passes trivially today (frontend has no `getDay`/`getUTCDay`) — its value is as an armed guardrail for Story 2.5's preview screen.
- **AC1 (guardrails unchanged):** `lint-imports` — 7 kept / 0 broken; `test_scoped_getters.py`, `test_vocabulary_literals.py`, `test_scope_matrix.py` unchanged and green. No migration, no schema change, no `HEAD_REVISION` bump, no new error code.

**Proof performed:**
- Backend: `.venv/bin/python -m pytest` — **250 passed, 1 warning** (starlette httpx deprecation, not spine-governed). The DB stack was up, so integration tests ran (0 skipped). The 14 domain tests ran **DB-free in 0.01s**; the frontend guard is **armed and passing** against the working tree; the import-linter contracts ran in-suite via `test_architecture.py`.
- Frontend: `npm run build` (`tsc -b && vite build`) — clean (80 modules, built in ~121ms); `npm run lint` (oxlint) — clean (exit 0, no warnings). **This story adds no frontend code**; the proof is the still-green build plus the new backend guard. No manual click-through applies — there is no new UI.

**Disclosed forward reference (house discipline, not deferred scope):** the preview excluded-dates breakdown (`{leave_days, excluded_dates:[{date, reason:WEEKEND|HOLIDAY, name}], available_before/after}`, api-contracts §4.4) also knows about weekends and holidays and so must live in this same module — but it is **Story 2.5's** companion function, not this story's. 2.3 ships only `count_leave_days` returning an `int`, exactly as AC1 specifies. Not built now: the excluded-dates function, the reasons enum, any preview shape.

### File List

**New (backend):**
- `backend/app/domain/calendar.py` — the `count_leave_days` pure function (the one leave-day count).
- `backend/tests/domain/test_calendar.py` — 14 DB-free boundary tests.
- `backend/tests/test_frontend_no_client_day_count.py` — the AD-2 client day-count guard.

**Modified:** none. No migration, no `vocabulary.py`, no `main.py`, no router, no schema-snapshot test, no frontend file. (Existing import-linter, scoped-getter, and vocabulary guards confirmed still green — no edits needed.)

### Review Findings

_Code review 2026-07-13 — adversarial layers: Blind Hunter + Edge Case Hunter + Acceptance Auditor, over all uncommitted changes (Story 2.3 + the still-uncommitted Story 2.2 stack). Acceptance Auditor verdict: **Story 2.3 faithfully implemented — all 11 ACs satisfied, no Critical/High/Medium AC violation.** The 2.2 stack re-confirms its own prior review; every actionable 2.2 item is already in `deferred-work.md`._

**Decision needed (unchecked — human call required):**

- [x] [Review][Decision→Patch] `count_leave_days` silently miscounts if handed a `datetime.datetime` (holidays never excluded) [backend/app/domain/calendar.py:58] — RESOLVED 2026-07-13 (chose option 1, patch now): added module-private `_as_date()` that narrows a `datetime` to its `date`, applied to `start`/`end` and every member of the holiday set. AC1 preserved (only `count_leave_days` is public; `_`-prefixed helpers are spec-sanctioned). Regression check: the canonical Fri→Tue-with-holiday case passed entirely as `datetime` now returns **2** (was 3 pre-fix); 250 backend tests pass, import-linter "domain is pure" still green. — `datetime.datetime` is a subclass of `date`, so a `datetime` argument type-checks and iterates fine, but `datetime(2026,8,17,0,0) not in {date(2026,8,17)}` is always `True` → **every holiday check silently passes, the function over-counts, and an employee is charged leave for a Company Holiday.** No caller exists today (grep of `count_leave_days` is empty; Stories 2.5/2.6 wire it), and AD-12 guarantees `DATE`-typed inputs (holiday rows come from a `DATE` column). So this is latent, not live — but it fires quietly the instant a future caller resolves a range from a `datetime`/`TIMESTAMP` source. **Ambiguous by intent:** the spec makes this function deliberately minimal (AC1 "exactly one function") and leans on AD-12 for type discipline. Options: (a) add a one-line `.date()` coercion of `start`/`end` (and normalize the holiday set) so the function is defensive-by-construction; (b) rely on AD-12 and address it at the Story 2.5 call site when the caller lands; (c) dismiss — AD-12 makes it unreachable. Recommend (a): the consequence is a silent leave over-charge and the coercion neither adds a public function nor breaks purity.

**Patch (unchecked — fixable now):**

- [x] [Review][Patch] A failed holiday delete leaves the stale row visible — the 404 is shown but the list is never reconciled [frontend/src/api/holidays.ts:70; frontend/src/features/holidays/HolidaysPage.tsx:95] — FIXED 2026-07-13: `useDeleteHoliday` now invalidates `HOLIDAYS_QUERY_KEY` `onSettled` (was `onSuccess`), so a 404 (row already deleted elsewhere) refetches and removes the ghost row; harmless on a network error. Frontend build + lint clean. — the applied 2.2 patch surfaces the delete error (good), but `useDeleteHoliday` invalidates the query only `onSuccess`. The one case that reaches `onError` most naturally is a `404` — the row was already deleted by another Admin — and that is exactly when a refetch would remove the ghost row. Instead the just-deleted-elsewhere row stays in the list with a "not found" line under it until a manual refresh. Unambiguous fix: invalidate `HOLIDAYS_QUERY_KEY` on settle (or in `handleDelete`'s `onError`) so a 404 reconciles the UI. Belongs to Story 2.2's frontend. Low severity.

**Deferred (re-confirmed — already logged in `deferred-work.md` from the 2.2 review; nothing new appended):**

- [x] [Review][Defer] Concurrent same-id `DELETE /holidays` → `StaleDataError` → raw 500 instead of 404 [backend/app/services/holidays.py:102] — narrow race; departments' delete shares the identical gap (no `StaleDataError` backstop), so a codebase-wide decision. Already logged.
- [x] [Review][Defer] Enveloped body validation — blank/whitespace `name` accepted, malformed `holiday_date` → raw 422 outside the `{code,message,details}` envelope [backend/app/api/v1/holidays.py:57] — pends the NFR-17 enveloping decision, shared by departments/leave_types. Already logged.
- [x] [Review][Defer] Holidays UI renders page 1 only — no pagination controls, so holidays past the first page are invisible/undeletable [frontend/src/api/holidays.ts:47] — shared with the departments/employees/leave-types pagination gap. Already logged.
- [x] [Review][Defer] The genuine-TOCTOU `IntegrityError` re-check branch has no test [backend/tests/integration/test_holidays.py] — test-coverage gap; the sequential duplicate test never enters the `except`. Already logged.
- [x] [Review][Defer] Test robustness — clamp test seeds fixed `2200-…` dates cleaned up only in `finally`, and `_unique_date` can collide under `pytest-xdist` [backend/tests/integration/test_holidays.py] — flaky-by-construction against a shared DB. Already logged.

_Dismissed as noise (8): `count_leave_days` unbounded day-by-day loop (spec explicitly defers range validity upstream; no caller; bounded by the `date` domain); `set(None)` raises (None violates the `Collection[date]` type contract; no caller); the AD-2 guard catches only `getDay`/`getUTCDay` and only `.ts`/`.tsx` (AC11 **explicitly** scopes the guard to those two primitives and that glob — Auditor-confirmed by-design, chosen to avoid false positives on 2.2's holiday *data* feature); `_to_response(holiday: object)` weak typing (deliberate, documented layering rule — api/ may not import the ORM model); `_count_date -> int` annotation vs `scalar()` `int|None` (cosmetic, test-only); `_date_is_listed` termination coupling to the echoed `page_size` (test-only fragility); `me.isError` collapses an Admin to the read-only view (identical Pattern A in every feature screen — a shared fix, not a 2.3 defect); `calendar.py` shadows stdlib `calendar` (no collision — absolute `app.domain.calendar` imports throughout, the spine names this exact module)._

### Change Log

- 2026-07-13 — Story 2.3 implemented: added pure `domain/calendar.py::count_leave_days` (FR-08, DR-1/DR-2, SM-2), 14 DB-free boundary tests, and the AD-2 backend guard forbidding `getDay`/`getUTCDay` in `frontend/src`. Backend 250 passed; frontend build + lint clean. Status ready-for-dev → in-progress → review.
- 2026-07-13 — Code review (all uncommitted changes, 2.3 + 2.2). 1 decision-needed (datetime coercion), 1 patch (holiday delete list-reconcile), 5 deferred (all re-confirmed, already in deferred-work.md), 8 dismissed. 2.3 verdict: faithful to spec.
- 2026-07-13 — Both review patches applied and verified: `_as_date()` datetime→date coercion in `calendar.py`; `useDeleteHoliday` invalidates `onSettled`. Backend 250 passed; frontend build + lint clean. Status review → done.
