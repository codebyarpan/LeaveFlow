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

from app.domain.carry_forward import carry_forward_days
from app.domain.proration import prorate_entitlement
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
    `carried_forward(Y+1)`. `set_accrual`'s `available >= 0` gate turns the worst case (days already
    booked in `Y + 1`) into a guarded `ValueError` rather than a raw CHECK violation, but the right
    fix is to roll a year that is over.

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
            session, leave_year=leave_year, occurred_at=_now()
        )

        session.commit()

    return RolloverSummary(
        leave_year=leave_year,
        next_leave_year=next_leave_year,
        employees=len(employees),
        leave_types=len(leave_types),
        balances_written=balances_written,
        missing_source_rows=missing_source_rows,
    )


def recompute_carry_forward(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
) -> None:
    """Re-derive carry-forward FORWARD from `leave_year`, on an OPEN session (DR-7a, AD-6, AC6).

    **This is the DR-7a top-up, and it is the half of Story 2.10 that does not live in the job.**
    The rollover runs once, in January. A year-`Y` Pending request rejected in February must top up
    `carried_forward(Y+1)` THEN — so Stories 2.7 and 2.8 call this from inside their own open
    transactions, right after the balance mutator that raised `available(Y)` and before their
    `commit()`. The release and the top-up are ONE atomic fact.

    Called from exactly three sites — the three where `available(Y)` RISES:

      * reject a Pending request       (`leave_requests._decide` → `release_reserved`)
      * applicant cancels own Pending  (`leave_requests._decide` → `release_reserved`)
      * Admin approves a Cancellation  (`cancellation.approve_cancellation_request` →
                                        `release_consumed`)

    And deliberately NOT from approve (`consume_reserved` leaves `available` UNCHANGED, so
    carry-forward is already correct and is never clawed back — AC6) nor from a rejected Cancellation
    Request (the Leave Request is untouched).

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
        # Unreachable through the three call sites (the Leave Request holds a valid FK), and not a
        # client error if it ever happened — so it is loud rather than silently a no-op.
        raise LookupError(f"no leave_type row for id={leave_type_id}")

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
            return

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
            return

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
