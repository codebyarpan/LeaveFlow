---
baseline_commit: a148f904b1da6826984b59a405e4014b7c3140b1
---

# Story 2.5: See What a Request Will Cost Before Committing to It

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Employee,
I want to see the day count and my projected balance before I submit,
so that I understand what the request costs, and why it costs less than the calendar span suggests.

## Acceptance Criteria

**Literal ACs (from epics.md#Story 2.5):**

1. **(The preview endpoint)** Given an authenticated Employee and a date range, when they call `POST /api/v1/leave-requests/preview`, then the response carries `leave_days`, `available_before` and `available_after`; **and** `excluded_dates` names each excluded date with a `reason` of `WEEKEND` or `HOLIDAY`, and a `HOLIDAY` carries its `name` (`FR-08`, api-contracts §4.5).
2. **(One source of the day count)** Given the client, when it needs a day count anywhere, then it obtains it from this endpoint and from no other source (`AD-2`).
3. **(Advisory, never load-bearing)** Given a preview response, when a request is later submitted, then the previewed value is advisory only and never decides admission (`AD-3`).
4. **(The named exclusion on screen — `UJ-1`)** Given the React application and an Employee selecting a range containing a Company Holiday, when the preview returns, then the day count resolves to a number smaller than the number of dates picked, and the excluded holiday is **named on screen** rather than silently netted out (`UJ-1`).

**Derived ACs (implied, non-negotiable — the story must leave the system correct, not merely satisfy the literal ACs):**

5. **(The breakdown is complete and consistent with the count)** `excluded_dates` enumerates **every** non-Working Day in the inclusive range `[start, end]` — every weekend day and every Company Holiday. The invariant `leave_days + len(excluded_dates) == span` holds for every input, where `span = (end - start).days + 1` for `end >= start` and `0` otherwise. A weekend day that is **also** a Company Holiday is reported **once**, as `WEEKEND` (weekend precedence) — byte-for-byte matching `count_leave_days`' short-circuit (`day.weekday() < 5 and day not in holiday_set`), so the breakdown and the count can never disagree on which days were excluded.
6. **(The weekend-and-holiday rule stays in one pure module — `DR-2`/`AD-2`)** The breakdown is produced by a new pure function in [backend/app/domain/calendar.py](../../backend/app/domain/calendar.py) — the same module that owns `count_leave_days` and is the **only** code in the system that knows what a weekend or a Company Holiday is. It imports stdlib and `domain/vocabulary` only — no ORM, no framework, no clock, no I/O — so the `domain/ is pure` (AD-1) import-linter contract holds and its tests run DB-free. A second weekend-or-holiday implementation anywhere is a `DR-2` defect.
7. **(The reason vocabulary is declared once — `AD-21`)** `WEEKEND` and `HOLIDAY` are enumerated strings, so they are declared **exactly once** in [backend/app/domain/vocabulary.py](../../backend/app/domain/vocabulary.py) (added to `__all__`) and appear as a literal nowhere else under `app/`/`seed/` — `tests/test_vocabulary_literals.py` fails the build otherwise. `domain/calendar.py` and every other module reference the constants; tests import them.
8. **(`available_before`/`available_after` are DERIVED at the projection, never stored — `DR-3`/`AD-5`)** The preview reads the three **stored** balance quantities (`accrued`, `reserved`, `consumed`); the `api/` projection derives `available_before = accrued − consumed − reserved` and `available_after = available_before − leave_days`. No column, model attribute, or lower layer computes or stores an `available` figure — identical to Story 2.4's `GET /balances` projection.
9. **(The preview is READ-ONLY — `AD-3`)** The preview acquires **no** `SELECT … FOR UPDATE` lock, writes **no** balance column, opens no write transaction, and creates no `leave_request` row (that table does not yet exist; it arrives in Story 2.6). The balance row is byte-identical before and after a preview call — a preview can be issued any number of times with no side effect. Admission is decided only at submission, against the row read under lock (`AD-3`), never against a previewed number.
10. **(Scope `self`; a missing balance is a byte-identical 404)** The balance read is genuinely data-scoped (`leave_balance`, Story 2.4's first data-scoped resource): the repository getter takes the `actor` and applies the scope as a SQL predicate (`Scope.SELF`, intrinsic to the token subject, like `GET /balances`). A `leave_type_id` that names no Leave Type — or for which the caller has no materialized current-year balance — yields `404 RESOURCE_NOT_FOUND` through `authz.not_found()`, byte-identical to any other not-found. No/invalid token is `401 TOKEN_INVALID`.
11. **(Preview never refuses an overspend)** A range whose `leave_days` exceeds `available_before` returns `200` with a **negative** `available_after` — the honest projection of "you would be over by N". The preview raises **no** `INSUFFICIENT_BALANCE`: that refusal is the submission path's (Story 2.6), decided under lock. `INSUFFICIENT_BALANCE` is neither raised nor imported here.
12. **(The client computes nothing — `AD-2`)** The React preview screen uses `<input type="date">` for range selection and renders the server's `leave_days`, `excluded_dates` (each named) and `available_before`/`available_after` **as-is**. It contains no `getDay`/`getUTCDay`, no weekday arithmetic, no holiday-set logic — `tests/test_frontend_no_client_day_count.py` (Story 2.3, armed) stays green.

## Tasks / Subtasks

- [x] **Task 1 — The exclusion-reason vocabulary** (AC: 1, 7)
  - [x] In [backend/app/domain/vocabulary.py](../../backend/app/domain/vocabulary.py) declare the two exclusion reasons and add them to `__all__`, following the file's one-block-per-feature docstring idiom (a short paragraph naming Story 2.5, api-contracts §4.5, `FR-08`/`AD-2`, and that these are **response reasons**, not error codes — they map to no HTTP status, so `main.py`'s `CODE_TO_STATUS` is untouched):
    - `EXCLUSION_WEEKEND = "WEEKEND"`
    - `EXCLUSION_HOLIDAY = "HOLIDAY"`
  - [x] Note in the docstring paragraph **why they belong here**: they are enumerated strings that travel on the wire (`excluded_dates[].reason`), and `AD-21` admits no enumerated literal outside this file. The instant they land in `__all__`, `test_vocabulary_literals.py` begins enforcing them — so `domain/calendar.py` (Task 2) and any test must reference `vocabulary.EXCLUSION_WEEKEND`/`_HOLIDAY`, never the bare string.
- [x] **Task 2 — The excluded-dates breakdown in the pure core** (AC: 5, 6, 7)
  - [x] Extend [backend/app/domain/calendar.py](../../backend/app/domain/calendar.py) — do **not** create a second module (DR-2: the weekend/holiday rule lives in exactly one place, and that place is this module). Add:
    - A frozen dataclass `ExcludedDate` with `date: datetime.date`, `reason: str` (one of `vocabulary.EXCLUSION_WEEKEND`/`_HOLIDAY`), and `name: str | None` (the holiday name when `reason == HOLIDAY`, else `None`). `from dataclasses import dataclass`; keep it stdlib-pure.
    - A public function:
      ```python
      def excluded_dates(
          start: datetime.date,
          end: datetime.date,
          holidays: Mapping[datetime.date, str],
      ) -> list[ExcludedDate]:
      ```
      `holidays` is a `date → name` mapping (the count takes a bare `Collection[date]`; the breakdown needs the **names**, which is exactly what api-contracts §4.5 shows a `HOLIDAY` carrying). Import `Mapping` from `collections.abc`.
    - Iterate `[start, end]` inclusively (the identical `while day <= end: … day += timedelta(days=1)` loop `count_leave_days` uses). For each day, in this order: **weekend first** — `if day.weekday() < 5` is a weekday, so `else` (Sat/Sun) → append `ExcludedDate(day, EXCLUSION_WEEKEND, None)`; a weekday that **is** in `holidays` → append `ExcludedDate(day, EXCLUSION_HOLIDAY, holidays[day])`; a weekday not in `holidays` is a Working Day → **not appended**. Weekend-first is what makes a holiday-on-a-weekend report once, as `WEEKEND`, matching `count_leave_days`' `weekday() < 5 and day not in holiday_set` short-circuit (which never even consults the holiday set on a weekend).
    - Apply the same `_as_date(...)` normalization `count_leave_days` uses to both endpoints **and** to every key of `holidays` (a `datetime` key would never match a `date` day — the same silent-miss trap the module already guards). Copy `holidays` into a local `{_as_date(k): v for k, v in holidays.items()}` so the caller is never mutated and membership is order/duplicate-independent.
    - Docstring: pure function of its arguments (AD-2), never raises on its inputs (an inverted `end < start` yields `[]`, the empty iteration — mirroring `count_leave_days` returning 0), and the load-bearing invariant **`count_leave_days(start, end, holidays.keys()) + len(excluded_dates(start, end, holidays)) == span`**. State that range *validity* (start ≤ end, the zero-day and cross-year refusals) is enforced upstream at submission (Story 2.6), never here — so the same pure pair serves preview, submission and recalculation.
  - [x] Update the module docstring's Story-2.5 sentence (it already forward-references "the preview breakdown (Story 2.5)") to note the breakdown now lives here alongside the count.
  - [x] New DB-free test [backend/tests/domain/test_excluded_dates.py](../../backend/tests/domain/test_excluded_dates.py) (no `db_connection`, imports only `datetime` + `excluded_dates`/`ExcludedDate`/`vocabulary`, mirror `tests/domain/test_calendar.py`): a weekend-only span (two weekend days, both `WEEKEND`, `name is None`); a span with a **named** holiday (the `HOLIDAY` entry carries the exact name); a holiday **falling on a Saturday** → reported once as `WEEKEND` (precedence); an all-Working-Day span → `[]`; an inverted range (`end < start`) → `[]`; and a **property-style consistency assertion** across a mixed span: `count_leave_days(start, end, holidays.keys()) + len(excluded_dates(start, end, holidays)) == (end - start).days + 1`. Each test's docstring names the AC it closes.
- [x] **Task 3 — Repository reads: holidays-in-range and the caller's single-type balance** (AC: 1, 8, 10)
  - [x] In [backend/app/repositories/holiday.py](../../backend/app/repositories/holiday.py) add `holidays_in_range(session, start, end) -> list[CompanyHoliday]` — the holidays whose `holiday_date` falls in `[start, end]` inclusive, ordered by `holiday_date, id`. Named with **no** `get_`/`list_`/`find_`/`fetch_` prefix (like `holiday_date_exists`), so it is correctly **not** a scoped-getter candidate; a Company Holiday is organization-wide reference data (scope `all`), so there is no `actor` and no predicate. Extend the module docstring's exemption paragraph to name it. The preview passes the range so the query returns only the relevant rows (not the whole calendar) — but semantics are identical either way (holidays outside the range never match a day in the loop).
  - [x] In [backend/app/repositories/leave_balance.py](../../backend/app/repositories/leave_balance.py) add a **non-locking** scoped read `get_balance(session, actor, *, employee_id, leave_type_id, leave_year, scope) -> Row[tuple[int, int, int]] | None` returning `(accrued, reserved, consumed)` for one `(employee, leave_type, year)`, or `None` when the pair has no row (an unknown `leave_type_id`, or no materialized balance). It **joins `leave_balance → employee`** and applies `employee_scope_predicate(scope, actor)` exactly as `list_balances` does — `get_balance` matches the scoped-getter net by name and **is** genuinely data-scoped (a balance belongs to an Employee), so it takes the `actor` and scopes in SQL; it is **not** exempt. It does **not** join `leave_type` for a `code`/`name` (the preview does not surface them) and it does **not** `with_for_update()` — the preview reads, never decides admission (AD-3, AC9). Docstring: contrast it with `lock_balance` (the write-path `FOR UPDATE` primitive) — this is the advisory read.
- [x] **Task 4 — The preview service** (AC: 1, 3, 5, 8, 9, 10, 11)
  - [x] New file [backend/app/services/leave_requests.py](../../backend/app/services/leave_requests.py) — the first `leave_request` service (the spine's `services/leave_request`; use the plural file name to match `api/v1/leave_requests.py` and the codebase's `leave_types`/`balances` idiom). Module docstring: FR-08, AD-2, AD-3 (**this command is read-only — it opens a read session, acquires no lock, writes nothing**), and that it is the sole caller-facing entry to `domain.calendar`'s count + breakdown for the preview.
  - [x] A service view dataclass `PreviewView` (frozen) with `leave_days: int`, `excluded_dates: list[ExcludedDate]` (the domain type — `services/` may import `domain/`), and the three stored quantities `accrued: int`, `reserved: int`, `consumed: int`. `available_before`/`available_after` are **not** here — they are derived at the `api/` projection (AC8, the `BalanceView` precedent in `services/balance_reads.py`).
  - [x] `preview_leave_request(actor, *, leave_type_id, start, end) -> PreviewView`:
    1. `current_year = datetime.date.today().year` — the clock in the shell (AD-1/DR-8), never in `domain/`. Mirror `services/balance_reads.py`'s `_current_leave_year()`.
    2. Open one **read** `with Session(get_engine(), expire_on_commit=False) as session:` (no `commit()`; nothing is written).
    3. `row = leave_balance_repo.get_balance(session, actor, employee_id=actor.id, leave_type_id=leave_type_id, leave_year=current_year, scope=Scope.SELF)`; `if row is None: authz.not_found()` (AC10 — an unknown `leave_type_id` or unmaterialized balance is a byte-identical 404).
    4. `holidays = holiday_repo.holidays_in_range(session, start, end)`; build `holiday_map = {h.holiday_date: h.name for h in holidays}`.
    5. `leave_days = calendar.count_leave_days(start, end, holiday_map.keys())` and `excluded = calendar.excluded_dates(start, end, holiday_map)` — the **single** day-count authority (AD-2). Return `PreviewView(leave_days=leave_days, excluded_dates=excluded, accrued=row.accrued, reserved=row.reserved, consumed=row.consumed)`.
  - [x] **No `INSUFFICIENT_BALANCE`, no lock, no write** (AC9, AC11). Do not import `services/balances.py`. Range validity is not checked here (AC5) — `count_leave_days`/`excluded_dates` are total; a start-after-end preview returns `leave_days == 0`, `excluded == []`. Submission (2.6) owns `INVALID_DATE_RANGE`/`ZERO_LEAVE_DAYS`/`SPANS_TWO_LEAVE_YEARS`/`PAST_DATE_RANGE`. State this scope boundary in a docstring line.
- [x] **Task 5 — The `POST /leave-requests/preview` endpoint** (AC: 1, 2, 8, 10, 11)
  - [x] New router [backend/app/api/v1/leave_requests.py](../../backend/app/api/v1/leave_requests.py), registered in [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py) (add `leave_requests` to the `from app.api.v1 import (...)` tuple and an `include_router(leave_requests.router)` line, keeping the list's ordering). Module docstring mirrors `balances.py`: what it may import (`services/` + `api/` dependencies only — never `repositories/`/`domain/`), that scope `self` is intrinsic to the token so the guard is `get_current_employee` (not `require_role`), and **why `available_*` is computed HERE** (DR-3/AD-5, the same projection `balances.py` documents).
  - [x] `POST /leave-requests/preview`, `caller: Actor = Depends(get_current_employee)` — any authenticated role; scope `self`. Request model `PreviewRequest(BaseModel)`: `leave_type_id: uuid.UUID`, `start_date: datetime.date`, `end_date: datetime.date` (FastAPI parses `YYYY-MM-DD` → `date`; api-contracts §1 date convention). The exact request JSON is the Pydantic model's (api-contracts fixes only the **response**, §4.5) — snake_case, whole-day fields.
  - [x] Response model `PreviewResponse(BaseModel)`: `leave_days: int`, `excluded_dates: list[ExcludedDateResponse]`, `available_before: int`, `available_after: int`, where `ExcludedDateResponse(BaseModel)` is `date: datetime.date`, `reason: str`, `name: str | None = None` (a `WEEKEND` entry serializes `name: null`; a `HOLIDAY` carries it — matching the §4.5 example). Order: `excluded_dates` chronological (the domain function already yields them in range order).
  - [x] The projection derives `available` HERE (AC8), from the `PreviewView`'s three stored quantities, exactly as `balances.py::_to_response` does — type the view param as `object` (`api/` may not import the service dataclass or the ORM, the `leave_types`/`employees`/`balances` precedent): `available_before = view.accrued - view.consumed - view.reserved`; `available_after = available_before - view.leave_days`. Map each `view.excluded_dates` item (duck-typed `object` — read `.date`/`.reason`/`.name`, never importing `domain.calendar.ExcludedDate`) into an `ExcludedDateResponse`. `available_after` may be **negative** (AC11) — do not clamp it. Return `200`.
- [x] **Task 6 — The frontend preview panel** (AC: 4, 12)
  - [x] New API hook [frontend/src/api/leaveRequests.ts](../../frontend/src/api/leaveRequests.ts): a `usePreviewLeaveRequest()` built on `useMutation` (NOT `useQuery` — a preview is a `POST` with a body, run on demand when the Employee asks, not auto-fetched). Types: `PreviewLeaveInput { leave_type_id: string; start_date: string; end_date: string }`; `ExcludedDate { date: string; reason: string; name: string | null }`; `LeaveRequestPreview { leave_days: number; excluded_dates: ExcludedDate[]; available_before: number; available_after: number }`. `mutationFn: (input) => apiFetch<LeaveRequestPreview>('/leave-requests/preview', { method: 'POST', body: JSON.stringify(input) })` — follow the `apiFetch` call shape used by `useCreateLeaveType`/`useCreateHoliday`. Export from the barrel [frontend/src/api/index.ts](../../frontend/src/api/index.ts).
  - [x] New page `frontend/src/features/leave/RequestPreviewPanel.tsx`, mounted in `AppShell` in [frontend/src/App.tsx](../../frontend/src/App.tsx) (a new `features/leave/` dir — Story 2.6 extends it into full submission; leaving the preview here keeps that seam clean). A form: a Leave Type `<select>` populated from `useLeaveTypes()` (`.items`, value = `leave_type.id`); two `<input type="date">` for start/end; a "Preview" button that calls `mutate({ leave_type_id, start_date, end_date })`. On success render, **prominently**, `leave_days`, then `available_before → available_after`, then the `excluded_dates` list with **each holiday named** (`{ex.reason === 'HOLIDAY' ? ex.name : 'Weekend'}` beside `ex.date`) — this is `UJ-1`: the count is visibly smaller than the picked span and the excluded holiday is on screen, not silently netted out. On error, render `error.message` in `.emp-error` (branch on nothing role-specific; a 404 for a bad type shows its message). Mirror `LeaveTypesPage`'s `.panel`/`.emp-create`/`.emp-fields`/`.emp-field`/`.emp-error` layout and its `isPending`/`isError` handling.
  - [x] **The client computes nothing (AC12, AD-2):** the reason strings and `name` are matched/displayed as received; `leave_days`, `available_before`, `available_after` are rendered as-is (no arithmetic — the server already derived `available_after`). No `getDay`/`getUTCDay`, no weekday/holiday logic. Matching `reason === 'HOLIDAY'` is a display branch on a server-provided string (the `'HOLIDAY'` literal is the frontend's single home for it, restated once here as `LeaveTypesPage` restates its codes — the vocabulary guard scans `app/`/`seed/`, not `frontend/`). The AD-2 guard stays green.
  - [x] `frontend/src/index.css`: reuse existing classes; add only what the preview result needs (e.g. a `.preview-result` / `.preview-days` emphasis), mirroring the `.balance-available` additions Story 2.4 made.
- [x] **Task 7 — Prove it** (all ACs)
  - [x] New integration test [backend/tests/integration/test_leave_request_preview.py](../../backend/tests/integration/test_leave_request_preview.py) (real PostgreSQL, mirror `tests/integration/test_balances_read.py` fixtures): 
    - **Happy path** — seed a Company Holiday inside a weekday span, `POST /leave-requests/preview` for the caller's own Leave Type → `200`; `leave_days` equals the Working-Day count; `excluded_dates` contains the weekend days as `WEEKEND` (`name` null) and the holiday as `HOLIDAY` with its **name**; `available_before == accrued - consumed - reserved`; `available_after == available_before - leave_days`. Import the reasons from `vocabulary` (never literal, AC7).
    - **Advisory / read-only (AC9)** — capture the caller's balance row (`accrued/reserved/consumed`) before and after the preview and assert it is **unchanged**; assert `reserved` stays `0` (no reservation happened).
    - **Overspend not refused (AC11)** — a span whose `leave_days > available_before` returns `200` with `available_after < 0` and **no** `INSUFFICIENT_BALANCE`.
    - **Unknown Leave Type (AC10)** — a random `leave_type_id` → `404 RESOURCE_NOT_FOUND`, body byte-identical to another not-found; **no token** → `401 TOKEN_INVALID`.
    - **Weekend-only span** — a Saturday→Sunday range → `leave_days == 0`, both days `WEEKEND`, `available_after == available_before`.
  - [x] Backend: from `backend/`, `.venv/bin/python -m pytest` — all green, including the new domain (DB-free) and integration tests, and the **existing** guards: `test_vocabulary_literals.py` (now enforcing `WEEKEND`/`HOLIDAY`), `test_scoped_getters.py` (the new `get_balance` carries `actor`; `holidays_in_range` is correctly not a candidate), `test_frontend_no_client_day_count.py`, and `lint-imports` (7 contracts kept — `domain/calendar.py` still imports stdlib + `domain/vocabulary` only; `api/leave_requests.py` imports `services/`/`api/` only). No scope-matrix entry is required — `POST /leave-requests/preview` has no `{id}` path parameter and scope is `self`, so it is outside `test_scope_matrix.py`'s identifier matrix (like `/balances` and `/me`).
  - [x] Frontend: from `frontend/`, `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean. Manual click-through: an Employee picks a Leave Type and a range spanning a weekend and a holiday, clicks Preview, and sees a `leave_days` smaller than the picked span with the holiday **named**.
  - [x] State in Completion Notes: the backend pass count, that the breakdown tests ran DB-free, that the `count + excluded == span` invariant is asserted, and that the balance row is provably unchanged by a preview (AD-3).

### Review Findings

_Code review 2026-07-13 (adversarial: Blind Hunter + Edge Case Hunter + Acceptance Auditor). All 12 ACs SATISFIED — the four load-bearing invariants (AD-2, AD-3, DR-3/AD-5, AD-21) and the `count + len(excluded) == span` consistency invariant all hold in code. 1 decision-needed, 2 patch, 4 dismissed as noise/by-design._

**Patches:**

- [x] [Review][Patch] Unbounded preview date range — no span cap [backend/app/api/v1/leave_requests.py:436] — `PreviewRequest` places no upper bound on `[start_date, end_date]`, and the preview path is deliberately "total and permissive" (validity deferred to 2.6). A valid range like `0001-01-01 → 9999-12-31` drives ~3.65M day-by-day iterations in `count_leave_days` + `excluded_dates`, allocates ~1M+ `ExcludedDate`/`ExcludedDateResponse` objects, and serializes a multi-hundred-MB JSON — a CPU/memory exhaustion vector reachable by any authenticated Employee. **Resolution (2026-07-13): patch now.** Add a defensive max-span guard (~366 days, the tightest bound that never rejects a legitimate single-leave-year preview) via a `model_validator` on `PreviewRequest` → 422, the same framework input-validation category that already rejects a bad UUID/unparseable date here. No new domain error code, no `CODE_TO_STATUS` entry, no vocabulary change. Range *validity* (incl. the cross-year refusal) remains Story 2.6's.
- [x] [Review][Patch] Stale preview persists after the form is edited [frontend/src/features/leave/RequestPreviewPanel.tsx:48] — `onChange` handlers only `setForm(...)`; the result block renders `preview.data` unconditionally, so after a user previews and then edits the leave type or a date without re-clicking Preview, the panel keeps showing the previous `leave_days`/balance/excluded-dates, which no longer match the visible inputs. For a "see the cost before committing" feature the shown cost must track the current form. Fix: `preview.reset()` on any form-field change (or gate the result render on inputs being unchanged since the last submit).
- [x] [Review][Patch] Leave-type select has no loading/empty/error state [frontend/src/features/leave/RequestPreviewPanel.tsx:52] — when `useLeaveTypes` is loading, errored, or returns no items, the `<select>` shows only the placeholder and `handlePreview` returns silently, leaving a form that can never be submitted with no explanation. Fix: render an explicit loading/empty/error message (mirroring the `isPending`/`isError` handling already used for the preview mutation).

**Dismissed (by-design / spec-sanctioned):**

- Preview reads the current-year balance for a non-current-year range — **by-design**: Dev Notes "Scope boundary" states the preview reads the current-year balance advisorily and "Do not attempt to resolve a per-date-range Leave Year here"; submission (2.6) refuses cross-year spans.
- Inverted / zero-working-day range returns 200 with `leave_days: 0` — **by-design per AC5**: the preview is total and permissive; `INVALID_DATE_RANGE` is the submission path's (2.6).
- `_current_leave_year()` duplicated from `services/balance_reads.py` — spec Task 4 explicitly says "Mirror `services/balance_reads.py`'s `_current_leave_year()`".
- `ExcludedDateResponse` serializes `name: null` for WEEKEND entries — a superset of api-contracts §4.5 that Task 5 and the integration test (`"name": None`) explicitly bless.

## Dev Notes

### What this story is — a thin, read-only slice over primitives Stories 2.3 and 2.4 already shipped

2.5 adds **no schema, no migration, no balance mutation, no new error code**. It is the read-only preview endpoint that composes what already exists: the pure day count (`domain/calendar.count_leave_days`, Story 2.3) and the stored balance quantities (`leave_balance`, Story 2.4). The genuinely new code is small and precisely bounded:

1. A **pure breakdown function** (`excluded_dates`) added *inside* `domain/calendar.py` — because DR-2 admits exactly one module that knows weekends and holidays, and it is that module.
2. Two **reads** — a range query for holidays and a non-locking scoped read for the caller's single-type balance.
3. A **read-only service** and a **`POST` endpoint** whose `available_*` figures are derived at the `api/` projection, mirroring `GET /balances` byte-for-byte.
4. A **frontend preview panel** that renders server figures and computes nothing.

The load-bearing invariants, in priority order:

1. **AD-2 — one day-count authority.** `domain/calendar` is the only place weekend-and-holiday logic exists. The preview returns the count and the breakdown; the client renders them. `excluded_dates` lives in that module, not a new one, and not in the service.
2. **AD-3 — the preview is advisory and side-effect-free.** No lock, no write, no reservation. The number it returns never decides admission — submission re-reads the balance under `SELECT … FOR UPDATE` and decides there (Story 2.6). This is why the preview uses `get_balance` (a plain read), never `lock_balance`.
3. **DR-3 / AD-5 — `available` is derived at the projection.** The service returns `accrued`/`reserved`/`consumed`; the `api/` layer computes `available_before` and `available_after`. Never a stored/lower-layer `available`.
4. **AD-21 — the reason vocabulary is declared once.** `WEEKEND`/`HOLIDAY` live in `domain/vocabulary.py`; every other reference imports them.

### The consistency invariant — the one thing a reviewer will check first

`excluded_dates` and `count_leave_days` must never disagree. They iterate the **same** inclusive range with the **same** weekend/holiday rule, so:

```
count_leave_days(start, end, H.keys()) + len(excluded_dates(start, end, H)) == span
```

for every `(start, end, H)`, where `span = (end - start).days + 1` when `end >= start`, else `0`. The **weekend-first** ordering in `excluded_dates` is what preserves this: `count_leave_days` excludes a day when `weekday() >= 5 OR day in holidays`, and short-circuits so a weekend day is *never* tested against the holiday set. Reporting a holiday-on-a-weekend as `HOLIDAY` would double-book the reason and, worse, would let a future reader think two different rules were applied. Report it as `WEEKEND`. The DB-free test asserts the invariant directly on a mixed span.

### Why `available_before`/`available_after` are computed in `api/`, not the service

Story 2.4 made the rule explicit and enforced it: `available` is **derived at the `api/` projection** from the three stored quantities, nowhere else (DR-3, AD-5, its AC10). `GET /balances` returns `available` computed in `balances.py::_to_response`. This story is the same shape: the service hands up `accrued`/`reserved`/`consumed` (+ `leave_days`, a domain number), and `api/v1/leave_requests.py` derives `available_before = accrued − consumed − reserved` and `available_after = available_before − leave_days`. Putting the subtraction in the service would create a **second** place that computes an availability figure — exactly the drift AD-5 exists to prevent. Keep both derivations in the projection.

### Scope boundary — what 2.5 ships vs. what 2.6 owns

Disclosed forward references (the house discipline 2.1–2.4 used):

- **Range validation and its refusals** — `INVALID_DATE_RANGE`, `ZERO_LEAVE_DAYS`, `SPANS_TWO_LEAVE_YEARS`, `PAST_DATE_RANGE`. The preview is total and permissive (AC5): a start-after-end range previews as `0` days, a zero-Working-Day range previews as `0`. Submission (2.6) enforces validity under lock. The preview does not pre-empt those refusals — it is advisory.
- **`INSUFFICIENT_BALANCE`** — declared and raised by `services/balances.py` (Story 2.4). The preview never raises it (AC11); it shows a negative `available_after` instead. 2.6 wires `reserve` to submission, where the refusal fires under lock.
- **The `leave_request` table and `POST /leave-requests`** — Story 2.6. This story creates no table and no request row; `preview` is a computation, not a persisted draft.
- **The current-Leave-Year balance** — the preview reads the caller's **current-year** balance (`date.today().year`), consistent with the whole epic operating on the current Leave Year (2.4). A range whose dates fall in a future Leave Year still previews against the current-year balance (advisory); submission refuses a cross-year span outright (`SPANS_TWO_LEAVE_YEARS`, 2.6), and next-year balances are the rollover's (2.10). Do not attempt to resolve a per-date-range Leave Year here.

### Architecture compliance (guardrails — violating any of these fails `pytest`)

- **AD-1 / NFR-08 — layering & `domain/` purity.** `domain/calendar.py` imports stdlib + `domain/vocabulary` only (vocabulary imports nothing, so purity holds); no ORM, no framework, no clock. `api/leave_requests.py` imports `services/` + `api/` dependencies only — never `repositories/`/`domain/` (so it duck-types the view as `object` and cannot import `ExcludedDate`). `services/` opens the one (read) session; `repositories/` issues the SQL. Enforced by the import-linter contracts. [Source: ARCHITECTURE-SPINE.md#AD-1]
- **AD-2 — the server is the sole authority on a Leave Day count.** One function knows weekends and holidays; the preview returns count + reasoned/named breakdown + projected Available; no frontend module references a weekday or holiday. `excluded_dates` extends that one function's module. [Source: ARCHITECTURE-SPINE.md#AD-2 (lines 73–77)]
- **AD-3 — preview is advisory; the deciding read is under lock at submission.** "A value returned earlier by the preview endpoint is never load-bearing." The preview acquires no lock and writes nothing. [Source: ARCHITECTURE-SPINE.md#AD-3 (lines 79–83); api-contracts §4.5 "advisory only"]
- **AD-5 / DR-3 — `available` derived at the projection, never stored.** The three stored quantities travel up; `available_before`/`available_after` are computed in `api/`. [Source: ARCHITECTURE-SPINE.md#AD-5; Story 2.4 AC10]
- **AD-10 — scoped read, 404 = out-of-scope/absent.** `get_balance` takes the `actor` and scopes in SQL (`Scope.SELF` here); an unknown `leave_type_id` or unmaterialized balance is `404 RESOURCE_NOT_FOUND` via `authz.not_found()`, byte-identical. [Source: ARCHITECTURE-SPINE.md#AD-10; api-contracts §1, §2]
- **AD-21 — vocabulary declared once.** `WEEKEND`/`HOLIDAY` in `domain/vocabulary.py`, `__all__`-listed; `test_vocabulary_literals.py` fails on a literal elsewhere. [Source: vocabulary.py; ARCHITECTURE-SPINE.md#AD-21]
- **DR-1 / DR-2 — one weekend-and-holiday rule.** A day is a Working Day iff weekday and not a holiday; the rule exists in exactly one module. [Source: ARCHITECTURE-SPINE.md#AD-2 binds DR-1/DR-2]

### API contract specifics (api-contracts §4.5)

- `POST /leave-requests/preview`: role **any**, scope **self**, realizes `FR-08`/`AD-2`. It is the **only** way a client obtains a day count. The **response** shape is fixed (§4.5): `leave_days`, `excluded_dates[]` each `{date, reason}` with a `HOLIDAY` adding `name`, `available_before`, `available_after`. The **request** shape is the Pydantic model's (like `/balances`, the contract fixes the response, not the request body). snake_case; dates `YYYY-MM-DD`; whole-day integers. The value is **advisory only**; admission is decided against the locked row at submission (`AD-3`). [Source: api-contracts.md §4.5 (lines 164–191)]
- Every non-2xx carries `{code, message, details}` (NFR-17); `404` carries `RESOURCE_NOT_FOUND`, `401` carries `TOKEN_INVALID` — both already wired. No new `CODE_TO_STATUS` entry (the two new vocabulary strings are response reasons, not error codes). [Source: api-contracts §2; app/main.py `CODE_TO_STATUS`]

### Library / framework requirements (pinned — do NOT upgrade)

Python `3.13.*`; SQLAlchemy 2.x (`Mapped`/`mapped_column`, `select`, `Row`); pytest `9.1.1`; import-linter `2.13`; PostgreSQL 18. No new backend dependency — the preview is a `SELECT`-only composition of existing modules. Frontend: React `19.x`, Vite, TypeScript, TanStack Query (`useMutation` for the on-demand `POST`) — no new dependency. [Source: backend/pyproject.toml; frontend/package.json; ARCHITECTURE-SPINE.md#Stack]

### File structure (what to create / edit)

**New (backend):** `app/api/v1/leave_requests.py`; `app/services/leave_requests.py`; tests: `tests/domain/test_excluded_dates.py`, `tests/integration/test_leave_request_preview.py`.

**Edit (backend):** `app/domain/calendar.py` (add `ExcludedDate` + `excluded_dates`); `app/domain/vocabulary.py` (`EXCLUSION_WEEKEND`/`EXCLUSION_HOLIDAY` + `__all__`); `app/repositories/holiday.py` (`holidays_in_range`); `app/repositories/leave_balance.py` (`get_balance`, non-locking scoped read); `app/api/v1/router.py` (register `leave_requests`).

**New (frontend):** `src/api/leaveRequests.ts`; `src/features/leave/RequestPreviewPanel.tsx`.
**Edit (frontend):** `src/api/index.ts` (barrel); `src/App.tsx` (mount the panel); `src/index.css` (preview-result styles).

Naming: service/router file `leave_requests.py` (plural, matching `leave_types`/`balances`); domain function `verb_noun`-ish (`excluded_dates`, a noun-returning pure query, alongside `count_leave_days`); frozen dataclass `PascalCase` (`ExcludedDate`). [Source: ARCHITECTURE-SPINE.md#Consistency Conventions, #Source tree — `services/leave_request`, `domain/calendar`]

### Testing requirements

- **`tests/domain/test_excluded_dates.py` is DB-free** (SM-2/NFR-15): imports only `datetime` + the pure function + `vocabulary`, no `db_connection` — mirror `test_calendar.py`/`test_proration.py`. It carries the `count + excluded == span` invariant, the weekend-precedence case, and the named-holiday case.
- **`tests/integration/` uses real PostgreSQL** for the endpoint — it needs a materialized `leave_balance` row (Story 2.4's create hooks) and a seeded `company_holiday`. Reuse the `test_balances_read.py` fixture shape.
- **Assert the negatives explicitly:** the balance row is **byte-unchanged** after a preview (AD-3, AC9); an overspend does **not** raise `INSUFFICIENT_BALANCE` (AC11); the 404 for an unknown type is byte-identical to any other not-found (AC10); the reasons are asserted via `vocabulary.EXCLUSION_*`, never a literal (AC7).
- **`pytest` is the build (no CI).** The vocabulary-literals, scoped-getter, frontend-day-count, and import-linter guards all run in-suite; a planted `"WEEKEND"` literal, an unscoped `get_balance`, a client `getDay`, or a layering break fails the run.

### Previous story intelligence (2.1, 2.2, 2.3, 2.4)

- **The read-session idiom is settled** — `with Session(get_engine(), expire_on_commit=False) as session: …` and **no `commit()`** for a pure read (see `services/balance_reads.py::list_own_balances`, `services/holidays.py::list_holidays`). The preview is a read; do not open a write transaction. [Source: services/balance_reads.py; services/holidays.py]
- **`available` derivation is a solved, enforced pattern** — copy `api/v1/balances.py::_to_response` (view typed `object`, `available` computed at the projection). Do not re-solve it in the service. [Source: api/v1/balances.py:58–72]
- **The scoped-getter guard is armed** — a `get_`/`list_`/`find_`/`fetch_` on `session` without `actor` fails `test_scoped_getters.py` unless EXEMPT. `get_balance` takes `actor` (data-scoped, like `list_balances`); `holidays_in_range` is named without a read-verb prefix (like `holiday_date_exists`/`all_leave_types`) so it is correctly not a candidate. [Source: tests/test_scoped_getters.py; repositories/leave_balance.py `list_balances`; repositories/holiday.py `holidays_in_range` sibling `holiday_date_exists`]
- **The vocabulary-literals guard enforces `__all__`** — the moment `EXCLUSION_WEEKEND`/`_HOLIDAY` land in `__all__`, any bare `"WEEKEND"`/`"HOLIDAY"` under `app/`/`seed/` fails. `domain/calendar.py` references the constants; tests import them. Prose/docstrings are skipped (the guard walks the AST). [Source: tests/test_vocabulary_literals.py; domain/vocabulary.py]
- **Frontend proof is `npm run build` + `npm run lint`** (no test runner); the AD-2 client guard forbids `getDay`/`getUTCDay`. The panel renders server figures as-is; the on-demand `POST` is a `useMutation`, not a `useQuery`. [Source: 2-4 story; test_frontend_no_client_day_count.py; api/leaveTypes.ts `useCreateLeaveType` for the `apiFetch` POST shape]
- **Disclosed forward references are the discipline** — 2.3 explicitly deferred "the preview breakdown to 2.5"; `domain/calendar.py`'s docstring already names Story 2.5. This story closes that reference and defers submission/refusals/persistence to 2.6. [Source: domain/calendar.py docstring; 2-3, 2-4 stories]

### Git intelligence

Head is `a148f90` (the `baseline_commit`), tree carries Story 2.4's uncommitted work (the `leave_balance` slice — `0005`, `domain/proration.py`, `services/balances.py`/`balance_reads.py`, `api/v1/balances.py`, the dashboard). 2.5 builds directly on that: it reads the `leave_balance` rows 2.4 materializes and the `count_leave_days` 2.3 shipped. No migration is added — verify the `leave_balance` table and the materialization hooks are present (they are, per 2.4's File List) before writing the integration test. [Source: `git log`, `git status`; 2-4 story File List]

### Project structure notes

No structural conflicts. `excluded_dates` extends the module the spine names (`domain/calendar`); `services/leave_requests.py` is the spine's `services/leave_request`; the endpoint extends the existing `api/v1` router; the preview panel is the first tenant of a `features/leave/` dir that Story 2.6 extends into submission. The one new idea — a `date → name` mapping into the pure breakdown — is anticipated by `count_leave_days`' own docstring ("Holiday *names* … surface only in the preview breakdown (Story 2.5)").

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5: See What a Request Will Cost Before Committing to It (lines 1020–1043)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-2 (73–77), #AD-3 (79–83), #AD-5 (91–94), #AD-1, #AD-10, #AD-21, #Capability Map FR-08 (391)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md §4.5 (164–191 — the endpoint, the response shape, "advisory only"), §1 (dates, 403/404), §2 (error envelope, RESOURCE_NOT_FOUND)]
- [Source: backend/app/domain/calendar.py — `count_leave_days`, `_as_date`, the inclusive-range loop and purity contract to extend; the docstring's "preview breakdown (Story 2.5)" forward reference]
- [Source: backend/app/domain/vocabulary.py — the one-block-per-feature declaration idiom and `__all__`; backend/tests/test_vocabulary_literals.py — the AST literal guard]
- [Source: backend/app/repositories/leave_balance.py — `list_balances` (the scoped-read + `employee_scope_predicate` template for `get_balance`), `lock_balance` (the write-path primitive `get_balance` must NOT mirror — no `FOR UPDATE`)]
- [Source: backend/app/repositories/holiday.py — `list_holidays`/`holiday_date_exists` (the reference-data getter + exemption idiom for `holidays_in_range`)]
- [Source: backend/app/services/balance_reads.py — the read-session, `_current_leave_year()`, and `BalanceView` (the `PreviewView` template)]
- [Source: backend/app/api/v1/balances.py — the `available`-at-projection `_to_response`, the `object`-typed view, the `get_current_employee` any-role/self-scope guard, the module docstring's import rules]
- [Source: backend/app/api/v1/router.py — the router registration point; backend/app/services/authorization.py — `not_found()` (the byte-identical 404)]
- [Source: backend/tests/integration/test_balances_read.py — the integration fixture shape (materialized balances + scoped reads); backend/tests/domain/test_calendar.py, test_proration.py — the DB-free domain-test template]
- [Source: frontend/src/api/leaveTypes.ts — `useCreateLeaveType` (the `apiFetch` POST/`useMutation` shape) and the barrel export; frontend/src/api/balances.ts — the typed-hook idiom]
- [Source: frontend/src/features/leaveTypes/LeaveTypesPage.tsx — the form/`.emp-create`/`.emp-field`/`.emp-error` layout, the useLeaveTypes select source, the "restate a wire string once on the frontend" idiom; frontend/src/App.tsx — the AppShell mount point]
- [Source: _bmad-output/implementation-artifacts/2-4-leave-balances-three-quantities-one-derived.md — the immediately prior story; the `available`-derivation rule, the scoped-getter discipline, disclosed-forward-reference house style]

## Dev Agent Record

### Agent Model Used

Opus 4.8 (1M context) — `claude-opus-4-8[1m]`

### Debug Log References

- Full backend suite: `backend/.venv/bin/python -m pytest` → **309 passed** (baseline 292 + 17 new: 8 DB-free domain, 6 integration, plus the armed guards now enforcing WEEKEND/HOLIDAY and the new `get_balance`).
- One RED→GREEN correction during Task 7: `test_frontend_no_client_day_count.py` is a line-based scan (not AST), so the preview panel's docstring naming the two day-of-week primitives verbatim tripped it. Reworded the comment to "day-of-week primitive"; the guard is green. No functional code changed.
- Import-linter: **7 contracts kept, 0 broken** (`domain/calendar.py` still imports stdlib + `domain/vocabulary` only; `api/leave_requests.py` imports `services/`/`api/` only).
- Frontend: `npm run build` (tsc -b && vite build) and `npm run lint` (oxlint) both clean.

### Completion Notes List

Story 2.5 is a thin, **read-only** slice — no schema, no migration, no balance mutation, no new error code — composing the primitives Stories 2.3 (`count_leave_days`) and 2.4 (`leave_balance`) already shipped.

- **The pure breakdown lives in the one module (DR-2/AD-2).** `excluded_dates` + the frozen `ExcludedDate` dataclass were added *inside* `domain/calendar.py`, not a second module. It walks the same inclusive range with the same weekend-first rule as `count_leave_days`, so a holiday-on-a-weekend reports **once, as `WEEKEND`** — byte-for-byte the count's `weekday() < 5 and day not in holiday_set` short-circuit.
- **The consistency invariant is asserted directly.** `count_leave_days(...) + len(excluded_dates(...)) == span` is a DB-free property test on a mixed span, and is re-asserted on the wire in the integration happy path.
- **DB-free domain tests.** `tests/domain/test_excluded_dates.py` imports only `datetime` + the pure function + `vocabulary` (no `db_connection`) — weekend-only, named-holiday, weekend-precedence, all-working, inverted range, the invariant, a `datetime` key, and non-mutation of the caller's mapping.
- **The preview is provably side-effect-free (AD-3, AC9).** The integration test captures the balance row `(accrued, reserved, consumed)` before and after **three** consecutive previews and asserts it is **byte-unchanged**, with `reserved` still 0. `get_balance` issues a plain `SELECT` (no `FOR UPDATE`); the service opens a read session and never commits.
- **`available_*` derived at the projection (DR-3/AD-5).** The service hands up the three stored quantities; `api/v1/leave_requests.py::_to_response` derives `available_before = accrued − consumed − reserved` and `available_after = available_before − leave_days`, duck-typing the view as `object` (no `domain/`/ORM import). An overspend returns **200 with a negative, unclamped `available_after`** and no `INSUFFICIENT_BALANCE` (AC11).
- **Scope `self`, byte-identical 404 (AC10).** `get_balance` takes the `actor` and applies `employee_scope_predicate(Scope.SELF, actor)`; an unknown `leave_type_id` (or unmaterialized balance) is `404 RESOURCE_NOT_FOUND` via `authz.not_found()`, byte-identical to another not-found. No/invalid token is `401 TOKEN_INVALID`.
- **The client computes nothing (AC12/AD-2).** The panel renders `leave_days`/`available_*`/`excluded_dates` as-is; `reason === 'HOLIDAY'` is a display branch on a server string. No day-of-week primitive — the frontend guard stays green. The on-demand `POST` is a `useMutation`, not a `useQuery`.
- **Guards armed, not just passed:** vocabulary-literals now enforces `WEEKEND`/`HOLIDAY`; `test_scoped_getters` accepts `get_balance` (carries `actor`) and correctly ignores `holidays_in_range` (no read-verb prefix). No scope-matrix entry needed — the endpoint has no `{id}` path param and scope is `self`.
- **Manual click-through** was not run in this non-interactive session; the end-to-end integration test (real PostgreSQL + real router) exercises the identical happy path — Fri→Wed over a weekend and a **named** holiday, `leave_days` (3) smaller than the picked span (6), the holiday named on the wire.

### File List

**New (backend):**
- `backend/app/api/v1/leave_requests.py` — the `POST /leave-requests/preview` router; derives `available_*` at the projection.
- `backend/app/services/leave_requests.py` — the read-only preview service (`PreviewView`, `preview_leave_request`).
- `backend/tests/domain/test_excluded_dates.py` — DB-free breakdown tests incl. the consistency invariant.
- `backend/tests/integration/test_leave_request_preview.py` — end-to-end preview tests (real PostgreSQL).

**Edit (backend):**
- `backend/app/domain/vocabulary.py` — `EXCLUSION_WEEKEND`/`EXCLUSION_HOLIDAY` + `__all__`.
- `backend/app/domain/calendar.py` — `ExcludedDate` dataclass + `excluded_dates` function; module/count docstrings updated.
- `backend/app/repositories/holiday.py` — `holidays_in_range`; docstring exemption note.
- `backend/app/repositories/leave_balance.py` — non-locking scoped `get_balance`; docstring updated.
- `backend/app/api/v1/router.py` — register `leave_requests` router.

**New (frontend):**
- `frontend/src/api/leaveRequests.ts` — `usePreviewLeaveRequest` (`useMutation`) + types.
- `frontend/src/features/leave/RequestPreviewPanel.tsx` — the preview panel.

**Edit (frontend):**
- `frontend/src/api/index.ts` — barrel exports.
- `frontend/src/App.tsx` — mount `RequestPreviewPanel` in `AppShell`.
- `frontend/src/index.css` — `.preview-result`/`.preview-days`/`.preview-excluded` styles.

## Change Log

| Date       | Change                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------ |
| 2026-07-13 | Story 2.5 implemented: read-only `POST /leave-requests/preview`. Pure `excluded_dates` breakdown added to `domain/calendar.py` (WEEKEND/HOLIDAY vocabulary); non-locking scoped `get_balance` + `holidays_in_range` reads; read-only preview service; `available_*` derived at the api projection; frontend preview panel. No schema/migration/error-code. Backend pytest 309 passed; import-linter 7/7 kept; frontend build + lint clean. Status → review. |
| 2026-07-13 | Code review: all 12 ACs satisfied, invariants hold. 3 patches applied — (1) 366-day preview span cap (`PreviewRequest` `model_validator` → 422, resource guard, no new error code); (2) `preview.reset()` on form-field change (no stale cost shown); (3) loading/empty/error state on the Leave Type select. New span-cap test added. Backend pytest 310 passed; frontend build + lint clean. 4 findings dismissed as by-design/spec-sanctioned. Status → done. |
