---
baseline_commit: a148f904b1da6826984b59a405e4014b7c3140b1
---

# Story 2.4: Leave Balances — Three Quantities, One Derived

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Employee,
I want my balance expressed as what I was granted, what is committed, and what is spent,
so that the number I act on is the number I can actually spend.

## Acceptance Criteria

**Literal ACs (from epics.md#Story 2.4):**

1. **(Schema)** Given a database migrated by this story, when the schema is inspected, then `leave_balance` carries `accrued`, `reserved`, `consumed`, `prorated_entitlement`, `carried_forward`, `entitlement_basis` and `leave_year`, all `INTEGER`; **and** it carries `CHECK (accrued - consumed - reserved >= 0)`, `CHECK (reserved >= 0 AND consumed >= 0)`, `CHECK (accrued = prorated_entitlement + carried_forward)` and `UNIQUE (employee_id, leave_type_id, leave_year)`, and **no `available` column** (`AD-5`, `DR-3`).
2. **(Proration, floored)** Given an Employee joining in September and a Leave Type with an Annual Entitlement of 12, when their balance is materialized, then `prorated_entitlement` is `4` — `12 × 4/12`, counting the joining month through December inclusive, rounded **down**; **and** a computed entitlement of `4.16` yields `4` — the rounding is never to nearest (`DR-9`, spine *Proration*).
3. **(Materialization on create)** Given an Admin creates an Employee, or creates a Leave Type, when the command commits, then a `leave_balance` row exists for that Employee and every Leave Type, for the current Leave Year; **and** a Leave Type created after the fact has a balance to be applied for, which is what `SM-5` requires.
4. **(One mutation module, exactly eight operations)** Given the module that owns balance mutation, when it is inspected, then it exposes exactly `reserve`, `consume_reserved`, `consume_direct`, `release_reserved`, `release_consumed`, `adjust_reserved`, `adjust_consumed` and `set_accrual`; **and** no route, repository, job or other service writes a balance column (`AD-17`).
5. **(Self balance read)** Given an authenticated Employee, when they call `GET /api/v1/balances`, then each Leave Type returns `available` as the primary figure with `reserved` and `consumed` alongside it; **and** `available` is derived as `accrued − consumed − reserved` and never read from a column (`FR-07`, `DR-3`).
6. **(Scoped balance read of another Employee)** Given a Manager or an Admin, when they call `GET /api/v1/employees/<id>/balances`, then a Manager sees only their Direct Reports, and an Admin sees anyone (`FR-03`, `AD-10`).
7. **(Employee dashboard)** Given the React application and an authenticated Employee, when they open their dashboard, then each Leave Type shows Available prominently, with Reserved disclosed alongside it (`FR-07`).

**Derived ACs (implied, non-negotiable — the story must leave the system correct, not merely satisfy the literal ACs):**

8. **(The eight methods are complete, not stubbed — the balance algebra is honest)** Each of the eight operations performs its real mutation under a row lock (`AD-3`) with the non-negativity refusal built in, and each is directly tested. `reserve(days)` and `consume_direct(days)` verify `available ≥ days` **from the row read under `SELECT … FOR UPDATE`, in this transaction**, and refuse an overspend with `400 INSUFFICIENT_BALANCE` naming `days_requested` and `days_available` (`AD-3`, `AD-5`, `NFR-17`) — never by letting a `CHECK` fire (a `CHECK` reaching a client is a defect and a 500). `consume_reserved` transfers Reserved→Consumed (`reserved -= days; consumed += days`), leaving `available` unchanged. `consume_direct` **never touches `reserved`** (`FR-09`'s managerless auto-approval consumes without ever reserving; a shared `consume` would decrement `reserved` from 0 and violate `CHECK (reserved >= 0)`). `release_reserved`/`release_consumed` decrement the respective column. `set_accrual` writes `accrued`, `prorated_entitlement`, `carried_forward` (and `entitlement_basis`) in **one statement** (the equality `CHECK` is non-deferrable). `adjust_reserved`/`adjust_consumed` re-derive their column, verifying `available ≥ 0` under the lock.
9. **(No unscoped balance getter — `leave_balance` is the first genuinely data-scoped resource)** Every repository read that could return another Employee's balance takes the `actor` and applies the scope as a **SQL predicate**, never a post-fetch filter (`AD-10`, `NFR-03`/`NFR-04`). `GET /employees/<id>/balances`: an Employee (role not granted) → `403 ACTION_NOT_PERMITTED` decided before any row read; a Manager naming a non-report `<id>` → `404 RESOURCE_NOT_FOUND`, **byte-identical** to a nonexistent id; an Admin → any. `GET /balances` is scope `self`, intrinsic to the token subject.
10. **(`available` is derived at the projection, never stored)** No column, model attribute, migration, response builder, or test asserts a stored `available`. It is computed as `accrued − consumed − reserved` in the `api/` projection at read time, from the three stored quantities (`DR-3`, `AD-5`).
11. **(Model↔migration byte-faithful; the migration inserts nothing)** The `LeaveBalance` model and `0005_leave_balance` migration agree to an empty `alembic check` diff (`tests/integration/test_model_migration_agreement.py`), and the migration contains **no DML** — no `leave_balance` row is inserted by a migration; rows are materialized only by the service hooks (`AD-11`, `tests/test_migrations_insert_nothing.py`). The migration-chain list and `HEAD_REVISION` are updated to include `0005`.
12. **(Leave Year is the calendar year, determined in the service)** `leave_year` is the calendar year 1 Jan–31 Dec (`DR-8`). "Current Leave Year" is `date.today().year`, computed in `services/` (the clock lives in the imperative shell, never in pure `domain/`); proration is a pure function of `(annual_entitlement, joining_date, leave_year)` and reads no clock (`AD-1`, `NFR-08`).

## Tasks / Subtasks

- [x] **Task 1 — The `leave_balance` schema: model + migration + guard updates** (AC: 1, 10, 11, 12)
  - [x] Add `class LeaveBalance(Base)` to [backend/app/repositories/models.py](../../backend/app/repositories/models.py), mirroring the `LeaveType`/`CompanyHoliday`/`Employee` idiom already in that file:
    - `__tablename__ = "leave_balance"` (snake_case singular).
    - `id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))` — the PostgreSQL 18 native primitive every table uses.
    - `employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employee.id"), nullable=False)` and `leave_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leave_type.id"), nullable=False)`.
    - The seven `INTEGER` columns exactly as named in AC1 — `leave_year`, `accrued`, `reserved`, `consumed`, `prorated_entitlement`, `carried_forward`, `entitlement_basis` — each `Mapped[int] = mapped_column(nullable=False)` (plain `INTEGER`, the `LeaveType.annual_entitlement` precedent; **never `NUMERIC`/float**, DR-10). Give `reserved` and `consumed` `server_default=text("0")` so a freshly materialized row defaults them to 0 and `set_accrual`'s insert need not name them — keeping `reserve`/`consume_*` the only paths that *change* them.
    - **No `available` column** — it is derived (DR-3, AD-5).
    - `__table_args__` (the `Employee.__table_args__` tuple form) carrying the three `CheckConstraint(...)` and the `UniqueConstraint(...)`, each with an explicit `name=` **byte-identical to the migration's**:
      - `CheckConstraint("accrued - consumed - reserved >= 0", name="leave_balance_available_nonneg_check")`
      - `CheckConstraint("reserved >= 0 AND consumed >= 0", name="leave_balance_reserved_consumed_nonneg_check")`
      - `CheckConstraint("accrued = prorated_entitlement + carried_forward", name="leave_balance_accrued_composition_check")`
      - `UniqueConstraint("employee_id", "leave_type_id", "leave_year", name="leave_balance_employee_type_year_key")`
    - Module docstring names the FRs/ADs it serves (SM-6): `FR-07`, `DR-3`, `AD-5`, `AD-17`. Add `UniqueConstraint` to the `from sqlalchemy import …` line (`CheckConstraint`, `ForeignKey`, `text` are already imported).
    - Relationships are **optional** and not required by any AC — do not add `relationship()` back-refs on `Employee`/`LeaveType` unless a query needs them (the reads join explicitly). Keep the model minimal.
  - [x] New migration [backend/alembic/versions/0005_leave_balance.py](../../backend/alembic/versions/0005_leave_balance.py), `revision = "0005_leave_balance"`, `down_revision = "0004_company_holiday"`. Mirror `0002_department_and_employee.py`'s `op.create_table` idiom: `sa.Uuid()` id with `server_default=sa.text("uuidv7()")`, `sa.Integer()` quantity columns, `sa.ForeignKeyConstraint(...)` for both FKs, `sa.PrimaryKeyConstraint("id")`, the three `sa.CheckConstraint("<sql>", name="…")` (names matching the model exactly), and `sa.UniqueConstraint("employee_id", "leave_type_id", "leave_year", name="leave_balance_employee_type_year_key")`. Add `op.create_index("ix_leave_balance_employee_type_year", "leave_balance", ["employee_id", "leave_type_id", "leave_year"], unique=False)` **only if** the `UNIQUE` constraint's implicit index does not already serve the `FOR UPDATE` lookup — the UNIQUE constraint on `(employee_id, leave_type_id, leave_year)` already creates a btree index that *is* the `FOR UPDATE` access path (ERD §4.4), so a second index is redundant; **do not add one.** `downgrade()` drops the table. **No `op.bulk_insert`, no `INSERT` — the migration inserts nothing** (AD-11).
  - [x] Update [backend/tests/test_migrations_insert_nothing.py](../../backend/tests/test_migrations_insert_nothing.py): add `"0005_leave_balance.py"` to the ordered-chain assertion list (the exact-list test). The DML-guard test auto-parametrizes over every migration — no edit there.
  - [x] Bump `HEAD_REVISION = "0005_leave_balance"` in [backend/tests/integration/test_migration_smoke.py](../../backend/tests/integration/test_migration_smoke.py) and add a `test_leave_balance_table_shipped_*` smoke asserting the columns + the three CHECKs + the UNIQUE from the live catalog, mirroring the existing `leave_type`/`company_holiday` smokes.
  - [x] Confirm `tests/integration/test_model_migration_agreement.py` (`alembic check`) emits an empty diff — the model and migration must be byte-faithful.
- [x] **Task 2 — Proration in the pure core** (AC: 2, 12)
  - [x] New file [backend/app/domain/proration.py](../../backend/app/domain/proration.py), modeled on [backend/app/domain/calendar.py](../../backend/app/domain/calendar.py) — stdlib-only, thoroughly docstringed, `int` return. Expose one public function:
    ```python
    def prorate_entitlement(
        annual_entitlement: int,
        joining_date: datetime.date,
        leave_year: int,
    ) -> int:
    ```
    - If `joining_date.year < leave_year` → the Employee was present the whole year → return `annual_entitlement` (proration reduces nothing; ERD §6 "Not a gap").
    - If `joining_date.year == leave_year` → `remaining_months = 13 - joining_date.month` (Jan→12, Sep→4, Dec→1), return `(annual_entitlement * remaining_months) // 12`. Integer floor division **is** floor for non-negative operands — that is the "rounded down, never to nearest" of DR-9 (`12*4//12 == 4`; `10*3//12 == 2`, i.e. `2.5` floored, never `3`).
    - If `joining_date.year > leave_year` → return `0` (defensive; an Employee has no entitlement for a year before they joined — unreachable via this story's materialization, which only creates current-year rows for existing Employees, but keep the function total).
    - **No clock, no I/O, no ORM import** — the "domain/ is pure (AD-1)" import-linter contract fails the build otherwise. `leave_year` is passed in; the function never calls `date.today()`.
  - [x] New DB-free test [backend/tests/domain/test_proration.py](../../backend/tests/domain/test_proration.py) (no `db_connection`, mirror `tests/domain/test_calendar.py`): the AC2 canonical case (Sep, 12 → 4); the floor cases (`10` Oct → `2`, i.e. `2.5`→`2`; `15` Sep → `5`, i.e. `5.0`→`5`); Jan → full; Dec → `annual//12`; a prior-year join → full `annual_entitlement`; `annual_entitlement == 0` → `0`. Each test's docstring names the AC it closes.
- [x] **Task 3 — The balance-mutation module (AD-17): exactly eight operations, the sole writer of a balance column** (AC: 4, 8, 10)
  - [x] New file [backend/app/services/balances.py](../../backend/app/services/balances.py) — the one module that mutates a `leave_balance` quantity. It exposes **exactly** these eight public callables and nothing else public (`_`-prefix any helper): `reserve`, `consume_reserved`, `consume_direct`, `release_reserved`, `release_consumed`, `adjust_reserved`, `adjust_consumed`, `set_accrual`. Module docstring: FR-07/FR-08/FR-09/FR-10, DR-3/DR-4, AD-3, AD-5, AD-17; and the load-bearing invariant — *no route, repository, job or other service writes a balance column; every mutation flows through here.*
  - [x] These operate **inside a caller-supplied transaction** — they take the open `Session` as a parameter and do **not** open their own (the calling command owns the single transaction, AD-3). Signature shape (finalize names as you implement): `reserve(session, *, employee_id, leave_type_id, leave_year, days) -> None`, etc. Each mutating method:
    1. Acquires the target row with `SELECT … FOR UPDATE` (via a repository locking getter — SQL lives in `repositories/`, AD-3/AD-1). If several rows are locked in one command, lock ascending `(employee_id, leave_type_id, leave_year)`.
    2. Computes the outcome from the **locked** row's quantities in this transaction (never from a value a preview returned earlier — AD-3's TOCTOU rule).
    3. For `reserve`/`consume_direct`: if `days > accrued - consumed - reserved`, raise `400 INSUFFICIENT_BALANCE` with `details={"days_requested": days, "days_available": available}` — the gate (AD-5), before any write. `consume_direct` never reads or writes `reserved`.
    4. Writes the new value(s). `set_accrual` writes `accrued`, `prorated_entitlement`, `carried_forward`, `entitlement_basis` in **one statement** (equality CHECK is non-deferrable) — see Task 4 for its upsert role.
  - [x] **`set_accrual` is the materializer (create-or-update).** Because AC4 fixes the module at *exactly* eight methods, there is no separate public "create balance row" function — materialization (Task 4) routes through `set_accrual`, which performs an upsert: `INSERT … ON CONFLICT (employee_id, leave_type_id, leave_year) DO UPDATE SET accrued = EXCLUDED.accrued, prorated_entitlement = EXCLUDED.prorated_entitlement, carried_forward = EXCLUDED.carried_forward, entitlement_basis = EXCLUDED.entitlement_basis` — one statement, satisfying the non-deferrable equality CHECK and re-derivable idempotently for Story 2.11/2.12's recalculation. On a fresh insert `reserved`/`consumed` fall to their `server_default` `0`; the DO-UPDATE branch leaves them untouched (recalculation re-derives accrual only, never touches committed/spent). `set_accrual` computes `accrued = prorated_entitlement + carried_forward` itself (its callers pass the two parts, never `accrued`).
  - [x] New repository [backend/app/repositories/leave_balance.py](../../backend/app/repositories/leave_balance.py): the locking getter (`SELECT … FOR UPDATE`) used by the mutation methods, the `set_accrual` upsert statement, and the **scoped** read getters (Task 5). Repository functions issue the SQL; the service module holds the arithmetic and the refusal.
  - [x] New integration tests [backend/tests/integration/test_balances_mutation.py](../../backend/tests/integration/test_balances_mutation.py) exercising **each** of the eight methods directly (materialize a row via `set_accrual`, then call the method, then assert the row): `reserve` reduces available and refuses an overspend with `INSUFFICIENT_BALANCE` (`details` names the numbers); `consume_reserved` moves reserved→consumed leaving available unchanged; `consume_direct` consumes and leaves `reserved == 0` (and refuses an overspend); `release_reserved`/`release_consumed` decrement; `adjust_*` re-derive with the non-negativity guard; `set_accrual` on a fresh key inserts (reserved/consumed 0) and on an existing key updates the accrual triple without disturbing reserved/consumed. **The SM-1 concurrent double-submit test is NOT in this story** — see Dev Notes "Scope boundary"; it lands in Story 2.6 where `reserve` is wired to submission.
  - [x] Declare `INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"` in [backend/app/domain/vocabulary.py](../../backend/app/domain/vocabulary.py) (add to `__all__`) and map it to `400` in [backend/app/main.py](../../backend/app/main.py)'s `CODE_TO_STATUS`. Its **raise site is this module's `reserve`/`consume_direct`** — and the codebase's discipline is to declare a code *with* its raise site (vocabulary.py's own docstring, re: `EMPLOYEE_HAS_PENDING_REQUESTS`). AD-5 names `INSUFFICIENT_BALANCE` as the balance module's typed refusal, so it belongs here, not in the later submission story that merely *calls* `reserve`. Follow the one-message-per-refusal `DomainError` factory pattern from `services/leave_types.py`.
- [x] **Task 4 — Materialize balance rows on Employee-create and Leave-Type-create** (AC: 3, 12)
  - [x] In [backend/app/services/employee.py](../../backend/app/services/employee.py) `create_employee`, after the employee INSERT+flush and **before** `session.commit()` (the same transaction, AD-3): load all Leave Types (ascending `id`) and for each call `balances.set_accrual(session, employee_id=created.id, leave_type_id=lt.id, leave_year=current_year, prorated_entitlement=prorate_entitlement(lt.annual_entitlement, joining_date, current_year), carried_forward=0, entitlement_basis=lt.annual_entitlement)`. `carried_forward` is `0` — a joiner's first Leave Year has nothing to carry (carry-forward derivation and the rollover are Story 2.10). `current_year = date.today().year`.
  - [x] In [backend/app/services/leave_types.py](../../backend/app/services/leave_types.py) `create_leave_type`, after the leave-type INSERT+flush and **before** `session.commit()`: load all Employees (ascending `id`) and for each call `balances.set_accrual(session, employee_id=emp.id, leave_type_id=leave_type.id, leave_year=current_year, prorated_entitlement=prorate_entitlement(leave_type.annual_entitlement, emp.joining_date, current_year), carried_forward=0, entitlement_basis=leave_type.annual_entitlement)`. This is the `SM-5` guarantee: a fourth Leave Type, added through the API, immediately has a balance every Employee can apply against — no migration, no code change.
  - [x] **Route balance writes only through `balances.set_accrual`** — never a raw INSERT/UPDATE of `leave_balance` in `employee.py`/`leave_types.py` (AD-17). The materialization loop runs inside the command's existing single transaction; a failure rolls back the whole create (an employee is never created without its balances, and vice versa).
  - [x] In [backend/seed/__main__.py](../../backend/seed/__main__.py): after the Admin employee and EL/CL/FL Leave Types are seeded, materialize the Admin's three balance rows the same way (through `balances.set_accrual`), so the seeded Admin has a viewable balance. Keep it inside the seed's transaction.
  - [x] Integration tests: `POST /employees` → a `leave_balance` row exists for the new Employee × every existing Leave Type, current year, with `prorated_entitlement` matching `prorate_entitlement(...)` and `accrued == prorated_entitlement` (carried_forward 0); `POST /leave-types` → a row exists for the new type × every existing Employee. Assert the row count equals `#employees × #leave_types` after a create.
- [x] **Task 5 — The two scoped read endpoints** (AC: 5, 6, 9, 10)
  - [x] Scoped read getters in [backend/app/repositories/leave_balance.py](../../backend/app/repositories/leave_balance.py) — each takes `actor` and applies the scope as a **SQL predicate** (the scoped-getter guard `tests/test_scoped_getters.py` requires an `actor` param on every `get_`/`list_` taking a `session`; `leave_balance` is genuinely Employee-derived, so it is **not** exempt). Use [backend/app/repositories/scoping.py](../../backend/app/repositories/scoping.py)'s `Scope` and `employee_scope_predicate(scope, actor)` (built against `Employee`): join `leave_balance → employee` and apply the predicate on the joined `Employee`. `scoping.py`'s docstring explicitly anticipates this — "Epic 2 extends it when a genuinely data-scoped resource arrives." Filter `leave_year == current_year`.
  - [x] New router [backend/app/api/v1/balances.py](../../backend/app/api/v1/balances.py), registered in [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py):
    - `GET /balances` — `Depends(get_current_employee)` (auth only, any role; scope `self` is intrinsic to the token, like `GET /me`). Service reads the caller's own current-year balances (scope `SELF`, `employee_id = current.id`). Returns each Leave Type's `available` (primary), `reserved`, `consumed`.
    - `GET /employees/{employee_id}/balances` — `require_role(authz.ROLE_MANAGER, authz.ROLE_ADMIN)` (an Employee → `403 ACTION_NOT_PERMITTED`, decided before any row read). The body resolves scope from the actor's role: Admin → `Scope.ALL`, Manager → `Scope.REPORTS`. **First resolve the target Employee under scope** (reuse the scoped `get_employee(session, actor, employee_id)` in `repositories/employee.py`, which returns `None` for nonexistent-OR-out-of-scope); `None` → `authz.not_found()` (`404 RESOURCE_NOT_FOUND`, byte-identical to a nonexistent id, AD-10). Then return that Employee's current-year balances.
  - [x] **`available` is computed in the projection**, never stored: the `_to_response(...)` builder (typed `object` — `api/` may not import the ORM model, the `leave_types.py`/`employees.py` precedent) computes `available = accrued - consumed - reserved` from the three stored quantities and returns `available`/`reserved`/`consumed` (snake_case, whole-day integers). Balances are a bounded set (one per Leave Type) — return a plain collection, **not** the `Page`/`items` pagination envelope.
  - [x] Register `("GET", "/api/v1/employees/{employee_id}/balances")` in [backend/tests/test_scope_matrix.py](../../backend/tests/test_scope_matrix.py)'s `_SCOPE_REGISTRY` as `frozenset({Scope.REPORTS, Scope.ALL})` — **the first multi-scope entry** (every Epic 1 entry is a single `{Scope.ALL}`); the module docstring already names this endpoint as a planned Epic 2 addition. `GET /balances` has no path parameter → it is out of the identifier-endpoint matrix (like `/me`).
  - [x] Integration tests [backend/tests/integration/test_balances_read.py](../../backend/tests/integration/test_balances_read.py): `GET /balances` returns the caller's own balances with `available == accrued - consumed - reserved` and no `accrued`/no `available`-column leakage; `GET /employees/<id>/balances` — Admin sees anyone; a Manager sees a direct report (`_reports_of` template from `tests/integration/test_manager_scope.py`) but gets `404` (not 403) for a non-report; an Employee gets `403 ACTION_NOT_PERMITTED`. Assert the 404 body is byte-identical between a non-report id and a nonexistent id.
- [x] **Task 6 — The Employee dashboard** (AC: 7)
  - [x] New API hook [frontend/src/api/balances.ts](../../frontend/src/api/balances.ts), mirroring `frontend/src/api/leaveTypes.ts`/`me.ts`: a `Balance` interface (`leave_type_code`/`leave_type_name`, `available`, `reserved`, `consumed`); `export const BALANCES_QUERY_KEY = ['balances'] as const`; `useBalances()` = `useQuery({ queryKey: BALANCES_QUERY_KEY, queryFn: () => apiFetch<Balance[]>('/balances') })` (the `useMe` self-fetch template — no params, the token identifies the caller). Export from the barrel [frontend/src/api/index.ts](../../frontend/src/api/index.ts) (features import from `../../api`, never a file path).
  - [x] New page `frontend/src/features/dashboard/DashboardPage.tsx`, mounted in `AppShell` in [frontend/src/App.tsx](../../frontend/src/App.tsx) (there is no router — App.tsx explicitly reserves the shell for "a dashboard … across Epics 2 and 3"). Mirror `LeaveTypesPage`'s `isPending`/`isError`/`data` branches and `.panel`/`.emp-list`/`.emp-row` layout. For each Leave Type render **Available prominently**, with **Reserved disclosed alongside** (Consumed may show too, but Available is the headline and Reserved is the required secondary — FR-07).
  - [x] **The client never computes a day count or a balance figure** (AD-2): `available`/`reserved`/`consumed` arrive from the server as-is and are rendered as-is — no arithmetic, no `getDay`/`getUTCDay`, no weekday/holiday logic. The `test_frontend_no_client_day_count.py` guard (Story 2.3) stays green.
  - [x] **Do not build the Manager/Admin "view another Employee's balances" screen** — `GET /employees/<id>/balances` ships and is tested here (AC6), but its UI consumer ("My Team", Story 3.2) is a disclosed forward reference. This story's frontend is the Employee's own dashboard (AC7).
- [x] **Task 7 — Prove it** (all ACs)
  - [x] Backend: from `backend/`, `.venv/bin/python -m pytest` — all green, including the new domain (DB-free), integration (real PostgreSQL), migration-chain, model-agreement, scope-matrix, and scoped-getter guards. Confirm `lint-imports` keeps every contract (proration + balances add no forbidden import; `domain/proration.py` imports stdlib only).
  - [x] Frontend: from `frontend/`, `npm run build` (`tsc -b && vite build`) and `npm run lint` (oxlint) — both clean. Manual click-through: an Employee opens the dashboard and sees Available (prominent) + Reserved per Leave Type.
  - [x] State in Completion Notes: the backend pass count, that proration tests ran DB-free, that the eight-method module was verified to expose exactly eight public callables, and the count of materialized rows after a create.

## Dev Notes

### What this story is — a full vertical slice with two upstream hooks

Unlike 2.3 (one pure function), 2.4 is a complete slice **plus** two retro-active hooks: it adds the `leave_balance` table, a pure proration function, the AD-17 balance-mutation module, the two scoped read endpoints, the Employee dashboard — **and** it wires balance-row materialization back into `create_employee` (Story 1.6) and `create_leave_type` (Story 2.1). Those two hooks are the part most easily missed: without them, AC3/`SM-5` fail and every later story that reads a balance finds no row.

The load-bearing invariants, in priority order:

1. **`available` is never stored** (DR-3, AD-5). Three quantities are stored (`accrued`, `reserved`, `consumed`); `available = accrued − consumed − reserved` is computed at the projection. A stored `available` column, attribute, or test is a defect.
2. **Exactly one module writes a balance column** (AD-17), exposing exactly eight operations. Materialization routes through `set_accrual`; nothing else — no route, repository, job, or other service — writes `accrued`/`reserved`/`consumed`/`prorated_entitlement`/`carried_forward`/`entitlement_basis`.
3. **The CHECK constraints are a backstop, never a gate** (AD-5). The service pre-checks under the row lock and raises `INSUFFICIENT_BALANCE` naming the numbers; a CHECK reaching a client is a defect and a 500.
4. **`leave_balance` is the first genuinely data-scoped resource** (AD-10). Its read getters take the `actor` and scope in SQL; a scope miss is `404`, byte-identical to a nonexistent id.

### Scope boundary — what 2.4 ships vs. what its methods' callers ship later

AC4 fixes the module at **exactly eight** operations; AD-5/AD-17/AD-3 fully specify their behavior. So 2.4 implements all eight as **complete, individually-tested primitives** — real arithmetic, the `SELECT … FOR UPDATE` lock, and the `INSUFFICIENT_BALANCE` refusal built in. It does **not** stub them: a `reserve` that merely does `reserved += days` without the pre-check is a latent 500-generator the instant Story 2.6 wires it, which is exactly the anti-pattern the review process catches.

What is genuinely deferred (disclosed forward references, the house discipline 2.1/2.2/2.3 used):

- **Which lifecycle transition calls which method** — submission→`reserve` (2.6), approval→`consume_reserved`/`consume_direct` (2.7), rejection/cancellation→`release_*` (2.7/2.8), recalculation→`adjust_*`/`set_accrual` (2.11/2.12), rollover→`set_accrual` (2.10). 2.4 provides the primitives; it wires none of them to a request.
- **The SM-1 concurrent double-submit integration test** — the ERD assigns it to `tests/integration/` at the *submission* path (Story 2.6). 2.4's `reserve` is built lock-correct so that test passes when it arrives; 2.4 tests each method single-transaction.
- **Carry-forward and the rollover** (AD-6, Story 2.10). 2.4 materializes only the current Leave Year with `carried_forward = 0`. `prorate_entitlement` returns full entitlement for a whole-year Employee, so `carried_forward = 0` here is correct, not a placeholder.
- **`adjust_*` semantics under recalculation** (AD-19, Stories 2.11/2.12): 2.4 implements them as re-derive-with-non-negativity-guard primitives and unit-tests them; the recalculation orchestration (per-pair refusal, `admin_review_flag` under AD-20) is the consuming story's. Keep the method surface stable.

### The materialization gap — resolved here (a design decision the planning docs left open)

The planning artifacts fix the columns, constraints, and the proration formula, and state that proration is "applied once, at the Employee's first materialized Leave Year" — but **no source states the exact trigger/mechanism** for INSERTing `leave_balance` rows. This story resolves it:

- **Trigger points:** `create_employee` (materialize the new Employee × every Leave Type) and `create_leave_type` (materialize the new Leave Type × every Employee), both for the current Leave Year, inside the command's existing single transaction. Plus the seed (the Admin's rows).
- **Mechanism:** through `balances.set_accrual` (the only writer of the accrual triple), implemented as an upsert so it serves both first-materialization and later recalculation — and so the module stays at exactly eight public methods (no separate "create row" function). On insert, `reserved`/`consumed` default to `0`; `entitlement_basis` records the `annual_entitlement` the row was accrued under (FR-06's RECALCULATE needs something to recalculate *from* — ERD §2.1). `carried_forward = 0` (first year).

### Architecture compliance (guardrails — violating any of these fails `pytest`)

- **AD-1 / NFR-08 — layering & `domain/` purity.** `domain/proration.py` imports stdlib only (no ORM, no framework, no `app.core`, no clock). `api/` imports `services/` + `api/` only — never `repositories/`/`domain/` (role literals via `authz.ROLE_*`, never `domain.vocabulary`). `services/` opens the one transaction; `repositories/` issues the SQL and the `FOR UPDATE` lock. Enforced by the import-linter contracts in `test_architecture.py`. [Source: ARCHITECTURE-SPINE.md#AD-1]
- **AD-3 — one transaction, `FOR UPDATE`, lock order.** READ COMMITTED. Exactly one transaction per command, opened in `services/`. A balance write acquires its row `SELECT … FOR UPDATE` first; the deciding `available` is read under that lock in that transaction (never a preview value). Multiple rows lock ascending `(employee_id, leave_type_id, leave_year)`; balance rows before request rows. [Source: ARCHITECTURE-SPINE.md#AD-3]
- **AD-5 — schema is the backstop, service is the gate.** The three CHECKs + UNIQUE are a backstop; the module pre-checks and raises `INSUFFICIENT_BALANCE` (naming `days_requested`/`days_available`). The equality CHECK is non-deferrable, so `accrued`/`prorated_entitlement`/`carried_forward` move in one statement (`set_accrual`). A CHECK reaching a client is a defect and a 500. [Source: ARCHITECTURE-SPINE.md#AD-5; erd.md#4.2]
- **AD-10 — scoped reads, 404 = out-of-scope.** No unscoped balance getter. Manager scope `employee.manager_id = actor.id`; a scope miss is `404 RESOURCE_NOT_FOUND`, byte-identical to a nonexistent id; `403 ACTION_NOT_PERMITTED` is only the role gate. [Source: ARCHITECTURE-SPINE.md#AD-10; api-contracts §1, §4.4]
- **AD-17 — one balance-mutation module, exactly eight operations.** `consume_direct` never touches `reserved`; `release_consumed` is BR-05's approved-cancellation path; `set_accrual` writes the accrual triple in one statement. Nothing else writes a balance column. [Source: ARCHITECTURE-SPINE.md#AD-17]
- **AD-11 — no DML in migrations.** `0005` creates the table and inserts nothing; rows come only from the service hooks. [Source: ARCHITECTURE-SPINE.md#Seeding; tests/test_migrations_insert_nothing.py]
- **AD-21 — vocabulary declared once.** `INSUFFICIENT_BALANCE` is declared in `domain/vocabulary.py` (its raise site is this module) and mapped in `main.py`; `tests/test_vocabulary_literals.py` fails if the literal appears elsewhere. [Source: vocabulary.py; api-contracts §2]
- **DR-8 / DR-9 / DR-10 — Leave Year is the calendar year; proration floors; quantities are INTEGER.** [Source: erd.md#2.1, §4.1; ARCHITECTURE-SPINE.md#Proration]

### API contract specifics (api-contracts §4.4)

- The two endpoints' scope table is binding; the **exact JSON body is not** — it lives in the Pydantic model / generated OpenAPI (§0/§5). What is fixed: `available` (primary), `reserved`, `consumed` per Leave Type; `available` derived, never stored; snake_case; dates `YYYY-MM-DD`; whole-day integers. `accrued` need not be surfaced (the contract names only the three). Balances are unpaginated.
- `GET /balances`: role any, scope self. `GET /employees/<id>/balances`: role Manager+Admin, scope reports(Manager)/all(Admin) — the first multi-scope endpoint. Every non-2xx carries `{code, message, details}`; 403 is always `ACTION_NOT_PERMITTED`; 404 carries `RESOURCE_NOT_FOUND`. [Source: api-contracts §4.4, §1, §2]

### Library / framework requirements (pinned — do NOT upgrade)

Python `3.13.*`; SQLAlchemy 2.x (`Mapped`/`mapped_column`); Alembic; pytest `9.1.1`; import-linter `2.13`; PostgreSQL 18 (`uuidv7()` native, `INSERT … ON CONFLICT`, `SELECT … FOR UPDATE` — the reason PostgreSQL, not SQLite, was chosen). Frontend: React `19.x`, Vite, TypeScript, TanStack Query — the dashboard adds a hook + a page, no new dependency. [Source: backend/pyproject.toml; frontend/package.json; ARCHITECTURE-SPINE.md#Stack]

### File structure (what to create / edit)

**New (backend):** `alembic/versions/0005_leave_balance.py`; `LeaveBalance` in `app/repositories/models.py`; `app/domain/proration.py`; `app/services/balances.py`; `app/repositories/leave_balance.py`; `app/api/v1/balances.py`; tests: `tests/domain/test_proration.py`, `tests/integration/test_balances_mutation.py`, `tests/integration/test_balances_read.py`.

**Edit (backend):** `app/repositories/models.py` (add model + `UniqueConstraint` import); `app/services/employee.py` (materialization hook); `app/services/leave_types.py` (materialization hook); `app/domain/vocabulary.py` (`INSUFFICIENT_BALANCE` + `__all__`); `app/main.py` (`CODE_TO_STATUS`); `app/api/v1/router.py` (register `balances`); `backend/seed/__main__.py` (Admin balances); `tests/test_migrations_insert_nothing.py` (chain list); `tests/integration/test_migration_smoke.py` (`HEAD_REVISION` + smoke); `tests/test_scope_matrix.py` (register the identifier endpoint).

**New (frontend):** `src/api/balances.ts`; `src/features/dashboard/DashboardPage.tsx`.
**Edit (frontend):** `src/api/index.ts` (barrel); `src/App.tsx` (mount the page).

Naming: model `PascalCase` (`LeaveBalance`); table/module `snake_case` (`leave_balance`, `balances.py`, `proration.py`); domain function `verb_noun` (`prorate_entitlement`); migration `NNNN_name`. [Source: ARCHITECTURE-SPINE.md#Consistency Conventions, #Source tree]

### Testing requirements

- **`tests/domain/test_proration.py` is DB-free** (SM-2/NFR-15): imports only `datetime` + `prorate_entitlement`, no `db_connection`, no ORM — mirror `test_calendar.py`. Proration is a hard rule and carries tests (NFR-15).
- **`tests/integration/` uses real PostgreSQL** for the eight mutation methods, materialization, and the scoped reads — `ON CONFLICT`, `FOR UPDATE`, and the CHECK backstops need a real database (SQLite lacks them). The SM-1 concurrent double-submit test is **not** here (Story 2.6).
- **Assert the negatives explicitly:** no `available` column in the live catalog; a `CHECK` violation is never surfaced to a client (the pre-check refuses first); the 404 body for a non-report is byte-identical to a nonexistent id.
- **`pytest` is the build (no CI).** The import-linter, scoped-getter, scope-matrix, migrations-insert-nothing, model-agreement, and frontend-day-count guards all run in-suite; a layering break, an unscoped getter, an unregistered identifier endpoint, or migration DML fails the run.

### Previous story intelligence (1.6, 2.1, 2.2, 2.3)

- **The transaction idiom is settled** — `with Session(get_engine(), expire_on_commit=False) as session: … session.commit()`, `expire_on_commit=False` so the route can project the returned row. `create_employee`/`create_leave_type` already follow it; the materialization loop slots in **before their `commit()`**, inside the same `try` so a materialization failure rolls the create back. [Source: services/employee.py `create_employee`; services/leave_types.py `create_leave_type`]
- **The typed-refusal-with-`IntegrityError`-backstop pattern** (`_email_already_in_use`, `_leave_type_code_in_use`) is the model for the `INSUFFICIENT_BALANCE` `DomainError` factory — one message stated at module level, `details` carrying the numbers. [Source: services/leave_types.py:36-46; services/employee.py]
- **The 404-vs-403 convention is built** — `authz.not_found()` (`404 RESOURCE_NOT_FOUND`) for scope-miss/nonexistent; `require_role` raises `403 ACTION_NOT_PERMITTED`. `repositories/employee.py`'s scoped `get_employee` returns `None` for nonexistent-OR-out-of-scope — reuse it to gate `GET /employees/<id>/balances`. [Source: services/authorization.py; repositories/employee.py]
- **The scoped-getter guard is armed** — a `get_`/`list_` on `session` without `actor` fails `test_scoped_getters.py` unless EXEMPT. Reference data (leave-types, holidays) is exempt; `leave_balance` is **not** — it is the first data-scoped resource the guard was built to protect. [Source: tests/test_scoped_getters.py; repositories/scoping.py]
- **Frontend proof is `npm run build` + `npm run lint`** (no test runner); the AD-2 client guard forbids `getDay`/`getUTCDay`. The dashboard renders server figures as-is. [Source: 2-3 story; test_frontend_no_client_day_count.py]
- **Disclosed forward references are the discipline** — 2.1 deferred `PATCH /leave-types`, 2.2 deferred holiday recalculation to 2.11, 2.3 deferred the preview breakdown to 2.5. 2.4 defers the method-to-transition wiring, SM-1, carry-forward/rollover, and the "My Team" balance view — while shipping every primitive those stories consume.

### Git intelligence

Head is `a148f90` (the `baseline_commit`), tree clean. The recent chain (`0002`→`0003_leave_type`→`0004_company_holiday`) is committed and migrated; `0005_leave_balance` chains off `0004`. Note the head commit's message ("add leave approval workflow") mislabels Story 2.3's content (the leave-day count) — the *code* on disk is 2.3 as reviewed (`domain/calendar.py` + guards), which is what matters for the baseline. No uncommitted work to fold in. [Source: `git log`, `git status`]

### Project structure notes

No structural conflicts. `domain/proration.py` is the module the spine's source tree names ("`domain/` # PURE: calendar, proration, carry_forward, balance, vocabulary"); `services/balances.py` is AD-17's single owner; the two read endpoints extend the existing `api/v1` router pattern; the dashboard is the shell `App.tsx` explicitly reserved for Epic 2/3. The one genuinely new idea — that `leave_balance` is the first data-scoped resource — is anticipated verbatim in `repositories/scoping.py`'s docstring.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4: Leave Balances — Three Quantities, One Derived]
- [Source: _bmad-output/planning-artifacts/epics.md — FR-07 (line 48), FR-10 (line 54), AD-3 (135), AD-5 (137), AD-6 (138), AD-10 (142), AD-17 (149), AD-18 (150), AD-19 (151), index list (196)]
- [Source: _bmad-output/planning-artifacts/module-4-erd/erd.md §2 LEAVE_BALANCE, §2.1 (columns + `entitlement_basis` provenance), §3 (cardinality), §4.1 (types), §4.2 (constraints), §4.4 (the UNIQUE index serves FOR UPDATE), §6 (full-year proration note)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/ARCHITECTURE-SPINE.md#AD-1, #AD-3, #AD-5, #AD-6, #AD-10, #AD-17, #AD-18, #AD-19, #Conventions (Proration, Seeding, Testing, Naming), #Capability Map FR-07]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/architecture.md §5.1–5.3 (balance mutation, concurrency sequence, backstop-not-gate), §6.2 (carry-forward), §10 (seeding)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-LeaveFlow-2026-07-10/api-contracts.md §1 (403/404, pagination, dates), §2 (error envelope, ACTION_NOT_PERMITTED/RESOURCE_NOT_FOUND), §4.4 (the two balance endpoints)]
- [Source: backend/app/repositories/models.py — LeaveType/CompanyHoliday/Employee model idiom; backend/alembic/versions/0002_department_and_employee.py — create_table + CHECK/UNIQUE idiom]
- [Source: backend/app/services/employee.py `create_employee`; backend/app/services/leave_types.py `create_leave_type` — the two materialization hook points]
- [Source: backend/app/domain/calendar.py — the pure-core module to mirror for proration; backend/app/domain/vocabulary.py — code declaration discipline]
- [Source: backend/app/repositories/scoping.py — Scope + employee_scope_predicate, docstring anticipating the first data-scoped resource; backend/tests/test_scoped_getters.py, test_scope_matrix.py — the armed guards to satisfy]
- [Source: backend/tests/integration/test_manager_scope.py `_reports_of` — the Manager→direct-reports test template; backend/tests/integration/test_migration_smoke.py, test_migrations_insert_nothing.py — migration guards to update]
- [Source: frontend/src/api/me.ts, leaveTypes.ts — the self-fetch hook template; frontend/src/App.tsx — the dashboard mount point]
- [Source: _bmad-output/implementation-artifacts/2-3-the-leave-day-count-one-implementation-nowhere-else.md — the immediately prior story; house style, disclosed-forward-reference discipline, the AD-2 client guard]

## Dev Agent Record

### Agent Model Used

Opus 4.8 (1M context) — `claude-opus-4-8[1m]`

### Debug Log References

- `alembic upgrade head` — applied `0005_leave_balance` to the live PostgreSQL 18 database (0004 → 0005).
- `pytest` (full backend suite): **292 passed, 1 warning** (the pre-existing starlette httpx-deprecation warning, not spine-governed). No skips — integration tests connected to the running `leaveflow-postgres-1`.
- `lint-imports`: **7 contracts kept, 0 broken** (the layered architecture, `api → services` only, `domain/` purity, etc. all held with the new modules).
- Frontend `npm run build` (`tsc -b && vite build`) — clean (82 modules); `npm run lint` (oxlint) — clean, exit 0.
- Two expected guard failures surfaced and were resolved as part of the change, not worked around:
  - `test_schema_1_2.py::test_exactly_the_expected_tables_exist` — updated the exact-table set to include `leave_balance`.
  - `test_employees.py` / `test_leave_types.py` teardown — the new create-hooks materialize `leave_balance` rows, so their fixtures now clear balances before the FK-guarded Employee/LeaveType delete.

### Completion Notes List

- **Backend pass count: 292 passed** (up from the prior baseline). New tests: `tests/domain/test_proration.py` (9, DB-free), `tests/test_balances_module_surface.py` (2, DB-free reflection), `tests/integration/test_balances_mutation.py` (13), `tests/integration/test_balances_read.py` (7), `tests/integration/test_balances_materialization.py` (2), plus a new `leave_balance` smoke in `test_migration_smoke.py`.
- **Proration tests ran DB-free** (SM-2/NFR-15): `tests/domain/test_proration.py` imports only `datetime` and `prorate_entitlement`, no `db_connection` — mirroring `test_calendar.py`. `domain/proration.py` is stdlib-only and reads no clock; the `domain/ is pure` import-linter contract held.
- **The eight-method module exposes exactly eight public callables** — verified by `tests/test_balances_module_surface.py`, which reflects over `services/balances.py` and asserts the public function set is exactly `{reserve, consume_reserved, consume_direct, release_reserved, release_consumed, adjust_reserved, adjust_consumed, set_accrual}`. Each is a complete, individually-tested primitive (real arithmetic, the `SELECT … FOR UPDATE` lock, the `INSUFFICIENT_BALANCE` refusal for `reserve`/`consume_direct`), not a stub.
- **Materialized-row count after a create**: a `POST /employees` materializes exactly `#leave_types` balance rows for the new Employee (asserted `== _total_leave_types()`); a `POST /leave-types` materializes exactly `#employees` rows for the new type (asserted `== _total_employees()`) — the SM-5 guarantee, with proration applied and `carried_forward = 0`.
- **`INSUFFICIENT_BALANCE` (400)** declared in `domain/vocabulary.py` with its raise site (`services/balances.py`) and mapped in `main.py`; the `leave_balance` CHECKs stay a backstop (AD-5) — the service pre-checks under the lock and refuses first, so no CHECK reaches a client as a 500.
- **`leave_balance` is the first genuinely data-scoped resource**: `repositories/leave_balance.list_balances` takes the `actor` and applies `employee_scope_predicate` in SQL; `GET /employees/{id}/balances` is registered as the **first multi-scope** entry (`{REPORTS, ALL}`) in `test_scope_matrix.py`. A Manager naming a non-report gets a **byte-identical 404** to a nonexistent id (asserted on the response bytes).
- **Two intentional, disclosed design decisions** (both correctness-first, documented in-code):
  1. **Reads split into `services/balance_reads.py`** rather than added to `services/balances.py` — so the mutation module stays at *exactly eight* public callables (AC4). The story's file list named only `services/balances.py`; splitting the reads is what makes AC4 literally testable.
  2. **`repositories/employee.get_employee` gained an optional `scope: Scope = Scope.ALL`** (backward-compatible; Admin callers unchanged) so the Manager balance endpoint can resolve the target under `Scope.REPORTS`. The existing `get_employee` was pinned to `Scope.ALL`; without this a Manager could resolve any Employee. The unpaginated materialization helpers `all_employees` / `all_leave_types` are named without a read-verb prefix (like `count_active_direct_reports`) because they feed a write-path materialization loop, not a scoped read.
- **Manual click-through note (honest):** the dashboard's build (`tsc` + `vite`) and lint are clean and the endpoint it consumes (`GET /balances`) is covered end-to-end by `test_balances_read.py` against real PostgreSQL (including `available` derivation proven by reserving days and watching it drop). A live browser click-through was **not** performed — the running Docker `web`/`api` images predate this change and would need a rebuild; the automated coverage exercises the same request path.
- **AD-2 held**: the dashboard renders server figures as-is; `test_frontend_no_client_day_count.py` stayed green (no `getDay`/`getUTCDay`).
- **Seed**: the Admin's balance rows are materialized through `balances.set_accrual` on a `Session` bound to the seed's connection (shares the single transaction; idempotent via the upsert) — `test_seed.py` stayed green across a double-seed.

### File List

**New — backend:**
- `backend/alembic/versions/0005_leave_balance.py`
- `backend/app/domain/proration.py`
- `backend/app/repositories/leave_balance.py`
- `backend/app/services/balances.py`
- `backend/app/services/balance_reads.py`
- `backend/app/api/v1/balances.py`
- `backend/tests/domain/test_proration.py`
- `backend/tests/test_balances_module_surface.py`
- `backend/tests/integration/test_balances_mutation.py`
- `backend/tests/integration/test_balances_read.py`
- `backend/tests/integration/test_balances_materialization.py`

**Modified — backend:**
- `backend/app/repositories/models.py` (add `LeaveBalance`; `UniqueConstraint` import)
- `backend/app/repositories/employee.py` (`all_employees`; `get_employee` optional `scope`)
- `backend/app/repositories/leave_type.py` (`all_leave_types`)
- `backend/app/services/employee.py` (materialization hook in `create_employee`)
- `backend/app/services/leave_types.py` (materialization hook in `create_leave_type`)
- `backend/app/domain/vocabulary.py` (`INSUFFICIENT_BALANCE` + `__all__`)
- `backend/app/main.py` (`CODE_TO_STATUS`: `INSUFFICIENT_BALANCE` → 400)
- `backend/app/api/v1/router.py` (register `balances` router)
- `backend/seed/__main__.py` (Admin balance materialization)
- `backend/tests/test_migrations_insert_nothing.py` (chain list + `0005`)
- `backend/tests/integration/test_migration_smoke.py` (`HEAD_REVISION` = `0005`; `leave_balance` smoke)
- `backend/tests/test_scope_matrix.py` (register `GET /employees/{id}/balances`, first multi-scope entry)
- `backend/tests/integration/test_schema_1_2.py` (expected-tables set + `leave_balance`)
- `backend/tests/integration/test_employees.py` (teardown clears `leave_balance`)
- `backend/tests/integration/test_leave_types.py` (teardown clears `leave_balance`)

**New — frontend:**
- `frontend/src/api/balances.ts`
- `frontend/src/features/dashboard/DashboardPage.tsx`

**Modified — frontend:**
- `frontend/src/api/index.ts` (barrel export of `useBalances` / `Balance` / `BALANCES_QUERY_KEY`)
- `frontend/src/App.tsx` (mount `DashboardPage` in the shell)
- `frontend/src/index.css` (`.balance-available` / `.balance-available-value` styles)

## Change Log

| Date       | Version | Description                                                                 | Author |
|------------|---------|-----------------------------------------------------------------------------|--------|
| 2026-07-13 | 0.1     | Story 2.4 implemented: `leave_balance` schema (`0005`), pure `prorate_entitlement`, the AD-17 eight-method balance-mutation module with `INSUFFICIENT_BALANCE`, materialization hooks into `create_employee`/`create_leave_type`/seed, the two scoped read endpoints (`GET /balances`, `GET /employees/{id}/balances`), and the Employee dashboard. Backend 292 passed; import-linter 7/7 kept; frontend build + lint clean. Status → review. | Amelia (Dev Agent) |

## Review Findings

_Code review 2026-07-13 (adversarial: Blind Hunter + Edge Case Hunter + Acceptance Auditor). Acceptance Auditor: all 12 ACs satisfied — no AC violations. 3 patch, 0 decision-needed (1 resolved → deferred), 5 deferred, 8 dismissed._

- [x] [Review][Defer] Concurrent Employee-create / Leave-Type-create leaves a permanently-missing balance row [backend/app/services/employee.py:214, backend/app/services/leave_types.py:105] — deferred, accepted as a known limitation: admin creates are rare and effectively serial, and the outcome (a later mutation 500) is recoverable by re-materializing. Under READ COMMITTED, concurrent `create_employee`/`create_leave_type` neither see the other's uncommitted row, so the `(employee, type, year)` balance is never materialized and the next `reserve`/`consume` hits `_lock` → `LookupError` → 500.
- [x] [Review][Patch] `lock_balance` omits `populate_existing=True`, so a `FOR UPDATE` re-select can return a stale identity-map row — defeating the TOCTOU guarantee the module advertises. Sibling locking loader `load_employee` (repositories/employee.py:230) already uses this exact option. [backend/app/repositories/leave_balance.py:54] — FIXED: added `.execution_options(populate_existing=True)`.
- [x] [Review][Patch] Five mutators (`reserve`, `consume_reserved`, `consume_direct`, `release_reserved`, `release_consumed`) do not guard `days < 0` — a negative arg inverts the operation, can drive a column below zero and fire a CHECK as a raw 500 (the very outcome the module exists to prevent). `adjust_reserved`/`adjust_consumed` already guard negativity; make the five consistent. [backend/app/services/balances.py:99] — FIXED: each raises `ValueError` on `days < 0` before the lock.
- [x] [Review][Patch] AC2's literal "4.16 → 4" example is not directly tested — existing cases prove flooring (2.5→2, 5.0→5) but not the named fractional example. Add `prorate_entitlement(25, <Nov date>, year) == 4` (25×2/12 = 4.16 → 4). [backend/tests/domain/test_proration.py] — FIXED: November-joiner 4.16→4 assertion added.
- [x] [Review][Defer] Year-rollover cliff [backend/app/services/balance_reads.py] — deferred, assigned to Story 2.10
- [x] [Review][Defer] `set_accrual` has no `available ≥ 0` guard on its DO-UPDATE (recalc) branch [backend/app/services/balances.py:267] — deferred, reachable only via Story 2.11/2.12 recalculation
- [x] [Review][Defer] Negative `annual_entitlement` → negative `accrued` → CHECK 500 on materialization [backend/app/api/v1/leave_types.py:50] — deferred, pre-existing (Story 2.1 leave-type schema missing `ge=0`)
- [x] [Review][Defer] No index leading with `leave_type_id` on `leave_balance` [backend/alembic/versions/0005_leave_balance.py] — deferred, negligible at scale
