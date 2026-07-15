"""The Leave Year rollover — close `Y`, open `Y + 1`, and re-derive carry-forward (Story 2.10).

Implements: FR-07 (carry-forward, lapse, idempotence), AD-6 (`carried_forward(Y+1) =
min(carry_forward_cap, available(Y))`, written by ASSIGNMENT and recomputed on EVERY event that can
change its inputs, propagating forward through every materialized later year), AD-7 (the rollover is
a CLI entrypoint, not a scheduler inside the server and not an endpoint), AD-8 (it writes to
`rollover_run` and NEVER to `audit_entry`), AD-3 (one transaction, the caller's), AD-17 (every
balance write goes through `services/balances.set_accrual` and nothing else), DR-7/DR-7a. SM-5, SM-6.

--- The one-paragraph mental model ---

Carry-forward is NOT a quantity you move. It is a DERIVED figure you re-ASSIGN whenever its inputs
change, and its only input is `available(Y)`. The rollover is therefore not a transfer; it is the
first EVALUATION of `carried_forward(Y+1) = min(cap, available(Y))`. Everything follows from that:

  * **Idempotence (AC5) is free.** Assigning a derived value twice assigns the same value. There is
    no "has this run already?" check anywhere in this module, and there must not be one — a guard
    would be a confession that the arithmetic accumulates. If you ever write `carried_forward += …`,
    you have written the bug this design exists to prevent.
  * **DR-7a (AC6) is not a special case.** It is the SAME formula fired again, later, when
    `available(Y)` moves — which is why `recompute_carry_forward` below is a public function that
    Stories 2.7 and 2.8 call from inside their own transactions, and not something the job owns.
  * **Approve does not fire it**, because approve does not move `available(Y)`: `consume_reserved`
    shifts Reserved → Consumed and leaves Available unchanged. That is what makes carry-forward
    impossible to claw back (AC6's second clause) — a decision, not an accident of arithmetic.

--- This module writes ZERO `audit_entry` rows (AC8) ---

`audit_entry_repo` is deliberately NOT imported here, and its absence is the proof. A balance
re-derivation is not a state transition: the rollover transitions no Leave Request, so it writes
none. `SM-4`'s one-to-one count of audit rows against transitions must stay LITERALLY true, and
`rollover_run` exists as a separate table for exactly that reason (AD-8 — "had rollover rows been
written into `audit_entry`, SM-4 would have been false the day it was written"). There is no
`SUBJECT_ROLLOVER` and there must not be one.

--- Why there is no public reader for `available(Y)` ---

`balances._available()` is private, and `balance_reads.get_balance` demands an `actor` and a `Scope`
this job has no business holding — a cron job is not a person. So the rows are read with
`leave_balance_repo.lock_balance(...)` and `available` is computed inline. No getter is added to make
this feel tidier; the read is a write-path lock, which is precisely what `lock_balance` is for.
"""

import datetime
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.carry_forward import carry_forward_days
from app.domain.proration import prorate_entitlement
from app.domain.recalculation import YearBalance, project_forward
from app.repositories import admin_review_flag as admin_review_flag_repo
from app.repositories import employee as employee_repo
from app.repositories import leave_balance as leave_balance_repo
from app.repositories import leave_type as leave_type_repo
from app.repositories import rollover_run as rollover_run_repo
from app.repositories.engine import get_engine
from app.services import balances

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RolloverSummary:
    """What one run did — for the CLI to log. Not persisted; `rollover_run` stores only the fact."""

    leave_year: int
    next_leave_year: int
    employees: int
    leave_types: int
    balances_written: int
    missing_source_rows: int
    refused_pairs: int


def _now() -> datetime.datetime:
    """The current instant (UTC), from the shell clock (AD-1) — a `rollover_run`'s `occurred_at`.

    Private to this service, exactly like `leave_requests._now` and `cancellation._now`: there is no
    shared clock module in this codebase, deliberately. Timezone-AWARE — `occurred_at` is a
    `TIMESTAMPTZ`, and a naive datetime against it is a defect, not a nit.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def _available(balance) -> int:  # type: ignore[no-untyped-def]
    """`available = accrued − consumed − reserved`, from the three STORED quantities (DR-3, DR-7).

    Computed here rather than imported: `balances._available` is private, and reaching past a leading
    underscore to save three characters is how a module surface stops meaning anything.
    """
    return balance.accrued - balance.consumed - balance.reserved


def run_rollover(leave_year: int) -> RolloverSummary:
    """Close Leave Year `leave_year` and open `leave_year + 1`. The CLI's one call (AD-7).

    `--year Y` CLOSES `Y` and MATERIALIZES `Y + 1` (Open Decision #1). So `--year 2026` reads 2026's
    balances, writes 2027's, and appends `rollover_run(leave_year=2026)` — the ERD calls that column
    "The Leave Year rolled", and the year you rolled is the year you closed. Every acceptance
    criterion is phrased `available(Y) → carried_forward(Y+1)`; this is that, and a reader never has
    to guess which end `--year` names.

    **`leave_year` must be a CLOSED Leave Year, and the SCHEDULER owns that precondition.** This job
    has no clock (AC9 forbids one: the year is an argument precisely so a test needs no clock
    manipulation), so it cannot police the calendar and does not try. Rolling a year that is still
    open is not refused here — but it is a mistake, because subsequent activity in that year will
    LOWER `available(Y)`, and the next run at the real boundary would then lower
    `carried_forward(Y+1)`. A pair whose `Y + 1` year is already too spent to absorb the lowered
    accrual is REFUSED per pair — written not at all, flagged for Admin review with
    `CAUSE_ROLLOVER_RECALCULATION`, counted in the summary — and the batch continues (code review
    2026-07-15). Before that guard, `set_accrual`'s `available >= 0` gate raised its guarded
    `ValueError` here and one such pair aborted the ENTIRE org-wide transaction, which made a legal
    AC5 re-run dangerous exactly when a prior refusal had left a stale pair behind. The right fix is
    still to roll a year that is over.

    ONE transaction (AD-3), for every Employee × every Leave Type:

      1. Read the year-`Y` balance row under `FOR UPDATE` (`lock_balance`); `available(Y) =
         accrued − consumed − reserved`. A MISSING row is treated as `available(Y) = 0` and `Y + 1`
         is materialized anyway (Open Decision #4) — Story 2.4's concurrent-create hole can leave a
         pair with no row at all, and healing the pair going forward beats propagating the gap. It
         is logged, because an operator should know a row was missing even though the job coped.
      2. `carried = carry_forward_days(available, carries_forward, carry_forward_cap)` — the pure
         function, which never sees the Leave Type's CODE (AC4).
      3. `prorated = prorate_entitlement(annual_entitlement, joining_date, Y + 1)`. For anyone who
         joined before `Y + 1` this is the full entitlement; proration applies once, at the first
         materialized year.
      4. `set_accrual(..., leave_year=Y + 1, ...)` — the ONE writer of a balance column (AD-17). Its
         `ON CONFLICT DO UPDATE` is what makes a re-run a no-op (AC5): it ASSIGNS the derived value.
         `reserved`/`consumed` on the `Y + 1` row are neither read nor written, so a re-run changes
         nothing even after somebody has already booked leave in `Y + 1`.

    Then ONE `rollover_run` row, in the SAME transaction: if the transaction rolls back, the run did
    not happen and there is no row saying it did (AD-8's "because" clause). And ZERO `audit_entry`
    rows (AC8).

    Deactivated Employees are rolled over like anyone else (Open Decision #3): `is_active` gates
    AUTHENTICATION, not accrual, and a reactivated Employee with a hole in their balance history is
    a support ticket.

    Returns a `RolloverSummary` for the CLI to log. Not persisted — `rollover_run` records the fact
    of the run, not its statistics.
    """
    next_leave_year = leave_year + 1
    balances_written = 0
    missing_source_rows = 0
    refused_pairs = 0
    # ONE instant for the whole run: every flag this batch writes and the `rollover_run` row record
    # the same atomic fact, so they carry the same `occurred_at` (the cancellation.py principle).
    occurred_at = _now()

    with Session(get_engine(), expire_on_commit=False) as session:
        # The two unpaginated `all_` helpers Story 2.4 built for exactly this kind of write-path
        # loop. Both order by `id`, so the balance rows are locked in a deterministic order.
        employees = employee_repo.all_employees(session)
        leave_types = leave_type_repo.all_leave_types(session)

        for employee in employees:
            for leave_type in leave_types:
                source = leave_balance_repo.lock_balance(
                    session,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    leave_year=leave_year,
                )

                if source is None:
                    # Open Decision #4: a pair with no year-`Y` row (2.4's concurrent-create hole).
                    # Treat as `available(Y) = 0` and materialize `Y + 1` anyway — that HEALS the
                    # pair instead of propagating the hole forward. Do not raise, do not skip.
                    missing_source_rows += 1
                    logger.warning(
                        "No leave_balance row for (employee=%s, leave_type=%s, year=%d); "
                        "treating available as 0 and materializing %d anyway.",
                        employee.id,
                        leave_type.id,
                        leave_year,
                        next_leave_year,
                    )
                    available = 0
                else:
                    available = _available(source)

                carried = carry_forward_days(
                    available=available,
                    carries_forward=leave_type.carries_forward,
                    carry_forward_cap=leave_type.carry_forward_cap,
                )
                prorated = prorate_entitlement(
                    leave_type.annual_entitlement, employee.joining_date, next_leave_year
                )

                # THE BATCH'S FORWARD CHECK (code review 2026-07-15). On a RE-RUN the `Y + 1` row
                # already exists and may be spent; assigning a LOWERED accrual (a prior refusal
                # left `Y`'s figures stale, or activity in a still-open `Y` shrank `available`)
                # would fire `set_accrual`'s `available >= 0` gate — a `ValueError` that used to
                # abort this whole org-wide transaction on one pair. Same disposition as
                # `recompute_carry_forward` below: write NOTHING for the pair, tell an Admin once,
                # and keep going. Locking `Y + 1` here follows AD-3's ascending order (`Y` is
                # already held above).
                target = leave_balance_repo.lock_balance(
                    session,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    leave_year=next_leave_year,
                )
                if target is not None and prorated + carried < target.consumed + target.reserved:
                    refused_pairs += 1
                    logger.warning(
                        "Rollover REFUSED for (employee=%s, leave_type=%s): assigning "
                        "accrued=%d to %d would drive available below its %d consumed + %d "
                        "reserved. Flagging for Admin review; the pair is left untouched and "
                        "the batch continues.",
                        employee.id,
                        leave_type.id,
                        prorated + carried,
                        next_leave_year,
                        target.consumed,
                        target.reserved,
                    )
                    if not admin_review_flag_repo.flag_exists(
                        session,
                        employee_id=employee.id,
                        leave_type_id=leave_type.id,
                        leave_year=leave_year,
                        cause=vocabulary.CAUSE_ROLLOVER_RECALCULATION,
                    ):
                        admin_review_flag_repo.insert_admin_review_flag(
                            session,
                            employee_id=employee.id,
                            leave_type_id=leave_type.id,
                            leave_year=leave_year,
                            cause=vocabulary.CAUSE_ROLLOVER_RECALCULATION,
                            occurred_at=occurred_at,
                        )
                    continue

                balances.set_accrual(
                    session,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    leave_year=next_leave_year,
                    prorated_entitlement=prorated,
                    carried_forward=carried,
                    entitlement_basis=leave_type.annual_entitlement,
                )
                balances_written += 1

        # The log of the EXECUTION — one row, same transaction, no `UNIQUE (leave_year)` so a legal
        # second run appends a second row rather than raising.
        rollover_run_repo.insert_rollover_run(
            session, leave_year=leave_year, occurred_at=occurred_at
        )

        session.commit()

    return RolloverSummary(
        leave_year=leave_year,
        next_leave_year=next_leave_year,
        employees=len(employees),
        leave_types=len(leave_types),
        balances_written=balances_written,
        missing_source_rows=missing_source_rows,
        refused_pairs=refused_pairs,
    )


def materialized_years(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    from_year: int,
) -> list[YearBalance]:
    """Lock year `from_year` and every materialized year above it, ascending (AD-3).

    Balance years are materialized CONTIGUOUSLY, so the first year with no row ends the walk — the
    same shape `recompute_carry_forward` below relies on, which is what keeps the projection and the
    write loop agreeing about which years exist.

    🚨 THE ONE COPY. This lived as `recalculation._materialized_years` until Story 3.4's Task 11 made
    `recompute_carry_forward` forward-checked and needed the identical walk to build its projection.
    It moved HERE rather than being duplicated because `recalculation.py` already imports this module
    (`services/recalculation.py:80`) and the reverse edge would be a CIRCULAR import. Two copies of a
    walk whose agreement is load-bearing is precisely the drift AD-6 cannot survive.

    `leave_balance_repo.lock_balance` is called DIRECTLY, never `balances._lock`: `_lock` raises
    `LookupError` on a missing row, and a missing row is exactly how this walk ENDS. It takes each row
    `FOR UPDATE`, ascending by `leave_year` — the lock order AD-3 requires.

    A missing row for `from_year` ITSELF is a programming error, not a client one, and is raised
    loudly rather than silently skipped.
    """
    years: list[YearBalance] = []
    year = from_year
    while True:
        balance = leave_balance_repo.lock_balance(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=year,
        )
        if balance is None:
            break
        years.append(
            YearBalance(
                leave_year=balance.leave_year,
                prorated_entitlement=balance.prorated_entitlement,
                carried_forward=balance.carried_forward,
                reserved=balance.reserved,
                consumed=balance.consumed,
            )
        )
        year += 1

    if not years:
        raise LookupError(
            f"no leave_balance row for (employee={employee_id}, leave_type={leave_type_id}, "
            f"year={from_year}) — the walk cannot start"
        )
    return years


def recompute_carry_forward(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    cause: str,
    occurred_at: datetime.datetime,
) -> bool:
    """Re-derive carry-forward FORWARD from `leave_year`, on an OPEN session (DR-7a, AD-6, AC6).

    Returns `True` when the walk was applied, `False` when it was REFUSED and flagged. **It never
    raises on a balance it cannot reconcile, and it never refuses the caller's command.**

    **This is the DR-7a top-up, and it is the half of Story 2.10 that does not live in the job.**
    The rollover runs once, in January. A year-`Y` Pending request rejected in February must top up
    `carried_forward(Y+1)` THEN — so Stories 2.7 and 2.8 call this from inside their own open
    transactions, right after the balance mutator that raised `available(Y)` and before their
    `commit()`. The release and the top-up are ONE atomic fact.

    Called from FOUR sites. Three RAISE `available(Y)`, and one — added by Story 3.4's Task 11 —
    LOWERS it:

      * reject a Pending request       (`leave_requests._decide` → `release_reserved`)
      * applicant cancels own Pending  (`leave_requests._decide` → `release_reserved`)
      * Admin approves a Cancellation  (`cancellation.approve_cancellation_request` →
                                        `release_consumed`)
      * 🆕 SUBMIT a request            (`leave_requests.submit_leave_request` → `reserve` /
                                        `consume_direct`) — the AD-6 hole, closed below.

    And deliberately NOT from approve (`consume_reserved` leaves `available` UNCHANGED, so
    carry-forward is already correct and is never clawed back — AC6) nor from a rejected Cancellation
    Request (the Leave Request is untouched).

    ---------------------------------------------------------------------------------------------
    🚨 THE FORWARD CHECK (Story 3.4, Task 11 — the AD-6 forcing point five stories deferred)
    ---------------------------------------------------------------------------------------------
    AD-6 requires `carried_forward` be re-derived on "every event that can change its inputs", and its
    only input is `available(Y)`. Story 2.10 wired this into the three sites where `available(Y)`
    RISES. **Submission LOWERS it and recomputed nothing** — so once the rollover had run for `Y`, a
    later year-`Y` submission left the stored `carried_forward(Y+1)` HIGHER than `min(cap,
    available(Y))` now is: a balance that is wrong and will be believed.

    ⚠️ The one-line fix `deferred-work.md:67,75` prescribes — "just add a fourth call in submit" — is
    UNSAFE, and adding the call without the guard below would have shipped a NEW raw 500 on the
    application's most-trafficked write path. The three old callers only ever RAISE `carried_forward`,
    so the walk could only ever raise `accrued`. Submit is the opposite direction: it LOWERS
    `carried_forward(Y+1)`, hence `accrued(Y+1)`, and if `Y+1` is already substantially spent that
    drives `accrued < consumed + reserved` → `set_accrual`'s bare `ValueError` (`balances.py:328`) →
    and there is NO `ValueError` handler in `app/main.py` or `api/v1/errors.py` → **raw 500 on the
    submitting Employee.**

    So the walk is now PROJECTED PURELY, with `domain.recalculation.project_forward` — the same pure
    function Story 2.11 built for exactly this — BEFORE the first write. On refusal this writes NO
    balance row and appends ONE `admin_review_flag` carrying the caller's `cause`, and the caller's
    command COMMITS regardless.

    **Refusing the submission itself was never an option**: no error code exists for "your leave is
    fine but a carry-forward artifact in a LATER year cannot be reconciled", and inventing one to
    refuse an Employee's leave over it would be indefensible. The submission commits; the balance the
    system cannot reconcile is surfaced to an Admin — which is precisely the mechanism Story 2.11
    built `admin_review_flag` to be, and it already has a read endpoint and a frontend panel.

    **This closes a SECOND live defect** (`deferred-work.md:74`, Story 2.12's shipped bug): a pair
    the policy change refused keeps a STALE cap, and the next INNOCENT reject of an unrelated
    request for that pair walked into the same unguarded `set_accrual` and 500'd. That bug's THIRD
    face — the same stale pair aborting a whole `run_rollover` batch on a legal AC5 re-run — is NOT
    closed here, because `run_rollover`'s loop writes through `set_accrual` directly and never calls
    this function; it has its OWN per-pair forward check (code review 2026-07-15), applying the same
    write-nothing-flag-and-continue disposition.
    `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject` is the canary that
    pinned the reject-path bug, and it is REPLACED (not deleted quietly) by
    `test_a_refused_pair_with_a_stale_cap_is_flagged_not_500` — `deferred-work.md:74` said so in
    advance: *"if that test ever fails, someone fixed the bug."*

    Writing NOTHING on refusal is what makes this safe to put on the submit path: the worst case is a
    balance that stays as it was and an Admin who is told, never an Employee who cannot submit leave.

    **The propagation loop.** AD-6: "Recomputation propagates forward through every materialized
    later year." Raising `carried_forward(Y+1)` raises `available(Y+1)`, which can raise
    `carried_forward(Y+2)` — and a request may stay Pending across more than one boundary (the ERD
    puts no bound on it). So this walks `y = Y+1, Y+2, …` while a balance row EXISTS for that year,
    re-deriving each from the year below it, and stops at the first year with no row.

    **The existence of the `Y + 1` row is the "did the rollover run?" signal.** `rollover_run` is
    never queried to decide this — which is why that table needs no getter (Open Decision #5). If no
    `Y + 1` row exists the rollover has not run, there is nothing to top up, the loop does zero
    iterations, and the hook costs one indexed lookup.

    **`prorated_entitlement` and `entitlement_basis` are PRESERVED.** This re-derives CARRY-FORWARD,
    not proration: each later year's existing figures are read off its row and passed back to
    `set_accrual` unchanged, and only `carried_forward` moves. Re-prorating here would quietly
    overwrite a policy figure this story has no business touching (that is FR-06's recalculation,
    and it belongs to Story 2.12).

    Lock order (AD-3): balance rows are locked ascending by `(employee_id, leave_type_id,
    leave_year)`. `Y` is already locked by the mutator that just ran; this walks `Y+1`, `Y+2`, …
    upward. Never backwards.

    Writes ZERO `audit_entry` rows (AC8, Landmine 4): a balance re-derivation is not a state
    transition, and `SM-4`'s exact-count ledger — which this very code path is exercised by — must
    stay true. Takes the caller's `Session` and opens no transaction of its own (AD-3).
    """
    leave_type = leave_type_repo.get_leave_type(session, leave_type_id)
    if leave_type is None:
        # Unreachable through the four call sites (the Leave Request holds a valid FK), and not a
        # client error if it ever happened — so it is loud rather than silently a no-op.
        raise LookupError(f"no leave_type row for id={leave_type_id}")

    # ---- THE FORWARD CHECK — pure, and BEFORE the first write (Story 3.4, Task 11) --------------
    # `years[0]` is `leave_year` itself, and its `reserved`/`consumed` are read straight off the row:
    # the mutator that just ran (`reserve`, `consume_direct`, `release_reserved`, `release_consumed`)
    # has already flushed its change, so these ARE the new absolute totals `project_forward` wants.
    # `new_prorated_by_year` stays `None` — this re-derives CARRY-FORWARD, never proration (that is
    # FR-06's job and belongs to Story 2.12), so the fixed-point break stays enabled and the
    # projection agrees with the write loop below by construction.
    years = materialized_years(
        session,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        from_year=leave_year,
    )
    projection = project_forward(
        years=years,
        new_reserved=years[0].reserved,
        new_consumed=years[0].consumed,
        carries_forward=leave_type.carries_forward,
        carry_forward_cap=leave_type.carry_forward_cap,
    )

    if projection.refused:
        # The arithmetic cannot be made consistent. Write NO balance, tell an Admin, and let the
        # caller's transition COMMIT. One flag per refusal, carrying the cause the CALLER named — a
        # submission and a reject are different events and an Admin triaging the queue needs to know
        # which one she is looking at.
        logger.warning(
            "Carry-forward recomputation REFUSED for (employee=%s, leave_type=%s, year=%s): "
            "available would go negative in %s. Flagging for Admin review (cause=%s); the balance is "
            "left untouched and the caller's transition still commits.",
            employee_id,
            leave_type_id,
            leave_year,
            projection.refused_year,
            cause,
        )
        # Dedupe (code review 2026-07-15): the register has no resolved state, so every retry of
        # the SAME refused event — an Employee re-submitting against an unreconcilable pair —
        # would append another identical row forever. One standing flag per (pair, year, cause)
        # says everything N copies would; a DIFFERENT cause still writes its own row, because a
        # submission and a reject are different events.
        if not admin_review_flag_repo.flag_exists(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=leave_year,
            cause=cause,
        ):
            admin_review_flag_repo.insert_admin_review_flag(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                cause=cause,
                occurred_at=occurred_at,
            )
        return False

    year = leave_year
    while True:
        target_year = year + 1

        target = leave_balance_repo.lock_balance(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=target_year,
        )
        if target is None:
            # No row for `target_year` — the rollover has not opened it. Nothing to top up, and
            # nothing beyond it can exist either (years are materialized in order). Done.
            return True

        source = leave_balance_repo.lock_balance(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=year,
        )
        # A missing source year is the same Open Decision #4 hole `run_rollover` heals: available 0.
        available = 0 if source is None else _available(source)

        carried = carry_forward_days(
            available=available,
            carries_forward=leave_type.carries_forward,
            carry_forward_cap=leave_type.carry_forward_cap,
        )

        if carried == target.carried_forward:
            # Already correct — and every later year derives from THIS one, so nothing above can
            # have moved either. Stop; the walk is not just an optimization, it is the fixed point.
            return True

        # Only `carried_forward` moves. The other two accrual figures are read off the row and
        # passed straight back, because this is not a re-proration.
        balances.set_accrual(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=target_year,
            prorated_entitlement=target.prorated_entitlement,
            carried_forward=carried,
            entitlement_basis=target.entitlement_basis,
        )

        year = target_year
