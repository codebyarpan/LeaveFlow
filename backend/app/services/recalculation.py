"""The recalculations — per (Employee, Leave Type) pair, and either of them may REFUSE (2.11, 2.12).

TWO commands live here, and they are siblings on purpose:

  * `recalculate_for_holiday_change` (Story 2.11) — the holiday calendar moved, so the Leave Requests
    it covers are re-counted and the balances behind them re-derived.
  * `recalculate_for_policy_change`  (Story 2.12) — a Leave Type's policy moved, so every materialized
    balance for that type is re-prorated. FR-06's `RECALCULATE` disposition.

They share the forward check, the per-pair refusal, the `admin_review_flag`, the `RefusedPair` /
`RecalculationSummary` shapes and the `200`-with-a-summary contract. They differ in ONE thing, and
almost every trap in the second is a consequence of it — see `recalculate_for_policy_change`'s
docstring for the three places 2.11's own code is correct for it and UNSOUND for 2.12.

Implements: FR-10 (a change to the holiday calendar corrects the requests it affects), FR-06 (a
policy change re-derives, or preserves, the balances that already exist — the Admin must say which),
AD-19 (the recalculation runs inside the SAME transaction as the write that triggered it, is
FORWARD-CHECKED, and a pair it would drive negative is left ENTIRELY unchanged and FLAGGED while the
rest of the operation commits), AD-18 (`leave_days` is frozen at submission; the HOLIDAY
recalculation is the ONE exception that invariant names — the policy recalculation is NOT, and
touches no Leave Request), AD-20 (a refusal is recorded in `admin_review_flag`, which is NOT
`audit_entry`), AD-17 (every balance write goes through `services/balances` and nothing else), AD-3
(one transaction, the caller's), AD-2 / NFR-08 (the day count has ONE implementation and it is
`domain/calendar`). 2.11 AC2–AC5; 2.12 AC5, AC6. SM-6.

--- The one-paragraph mental model ---

An Admin adds or deletes a holiday, or edits a Leave Type's policy. Inside that ONE transaction,
after the row is flushed, this sweeps what the change affects and groups it by (Employee, Leave
Type), because THAT PAIR IS THE UNIT OF REFUSAL. For each pair it computes what the new numbers WOULD
be — purely, in memory — and only then writes. If the projection says any year would go negative, it
writes NOTHING for that pair, drops a row in `admin_review_flag`, and moves to the next pair. The
same Employee's other Leave Types keep going, and the edit still commits.

--- This is the system's first PARTIALLY-REFUSABLE command, and that is the whole difficulty ---

Every other refusal in this codebase ABORTS the command: `INSUFFICIENT_BALANCE`,
`TRANSITION_NOT_ALLOWED`, `HOLIDAY_DATE_IN_USE` all roll the whole transaction back. This one may
not. AD-19 requires the failing pair to be left alone WHILE THE REST COMMITS, and the endpoint to
return `200` with a summary rather than an error.

That is why the refusal must be PREDICTED and never CAUGHT (AC5: "the refusal was discovered by the
forward check, never by an AD-5 CHECK violation"). A refusal discovered by a database error has
already poisoned the transaction, and every way back — a rollback, an `except IntegrityError`, an
`except ValueError` around `adjust_reserved`, a rolled-back `begin_nested()` SAVEPOINT — either
discards the pairs that succeeded or is still the DATABASE doing the discovering. So the decision is
made by `domain/recalculation.project_forward`, purely, BEFORE the first write for that pair. Once it
says "not refused", `adjust_reserved`, `adjust_consumed` and `set_accrual` CANNOT raise their guarded
`ValueError`s — the check already proved they won't. AD-5's CHECKs stay a backstop, never a gate.

--- This module writes ZERO `audit_entry` rows (Landmine 5) ---

`audit_entry_repo` is deliberately NOT imported here, and its absence is the proof — exactly as
`services/rollover.py` does it. A recalculation is a BALANCE RE-DERIVATION, not a state transition:
no Leave Request changes status, so no audit row is written. SM-4's one-to-one count of audit rows
against transitions (`tests/integration/test_audit_entries.py` pins it at exactly 14) must stay
LITERALLY true through a holiday edit. There is no `SUBJECT_HOLIDAY` in `domain/vocabulary.py` and,
echoing `rollover.py`'s "there is no `SUBJECT_ROLLOVER` and there must not be one", there must not be
one. `admin_review_flag` is not an audit row and does not count against SM-4 — write as many as the
refusals require.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.calendar import count_leave_days
from app.domain.proration import prorate_entitlement
from app.domain.recalculation import YearBalance, project_forward
from app.repositories import admin_review_flag as admin_review_flag_repo
from app.repositories import employee as employee_repo
from app.repositories import holiday as holiday_repo
from app.repositories import leave_balance as leave_balance_repo
from app.repositories import leave_request as leave_request_repo
from app.repositories import leave_type as leave_type_repo
from app.repositories.models import LeaveRequest
from app.services import balances, rollover


@dataclass(frozen=True)
class RefusedPair:
    """One (Employee, Leave Type) pair the recalculation left ENTIRELY unchanged (AC4, AC8).

    Carries NAMES, not bare UUIDs, because AC8 requires the Admin's screen to NAME each refused pair
    and a pair of opaque ids is not actionable (the `CancellationRequest` response carries
    `employee_name` + `leave_type_code` for exactly this reason). `cause` is a `vocabulary.CAUSE_*`
    constant, never a bare literal (AD-21).
    """

    employee_id: uuid.UUID
    employee_name: str
    leave_type_id: uuid.UUID
    leave_type_code: str
    leave_year: int
    cause: str


@dataclass(frozen=True)
class RecalculationSummary:
    """What one holiday change did — and, honestly, what it DECLINED to do (AC4, AC8).

    The summary the endpoint returns with its `200`. `pairs_refused` is the half that matters: AC8
    forbids showing the Admin an unqualified success for an operation that partially refused, and
    PRD §1's governing sentence is why — "a leave balance that is wrong is worse than a leave balance
    that is absent, because it will be believed". A refusal recorded where nobody looks is exactly
    that, which is why this travels to the screen rather than only into `admin_review_flag`.
    """

    requests_recalculated: int
    pairs_recalculated: int
    pairs_refused: list[RefusedPair]


def _now() -> datetime.datetime:
    """The current instant (UTC), from the shell clock (AD-1) — an `admin_review_flag`'s moment.

    Private to this service, exactly like `leave_requests._now`, `cancellation._now` and
    `rollover._now`: there is no shared clock module in this codebase, deliberately. Timezone-AWARE —
    `occurred_at` is a `TIMESTAMPTZ`, and a naive datetime against it is a defect, not a nit.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def _today() -> datetime.date:
    """Today, from the shell clock (AD-1). The clock lives HERE, in `services/`.

    Passed DOWN into `list_requests_covering` so that `repositories/` and `domain/` stay clock-free
    and the whole eligibility rule (AC3: a future Approved request is recalculated, a past one never
    is) is testable without mocking a clock.
    """
    return datetime.date.today()


def _recount(session: Session, request: LeaveRequest) -> int:
    """Recount one request's Leave Days against the CURRENT holiday calendar (AD-2, NFR-08).

    `domain.calendar.count_leave_days` is the ONLY code in the system that knows what a weekend or a
    Company Holiday is. A second weekend/holiday rule here would be, by DR-2, a defect — so the
    holidays are read from the repository and handed straight to the one counter.

    The calendar this reads ALREADY reflects the edit: the holiday command flushes its INSERT/DELETE
    before calling into this module, which is precisely why the recalculation cannot be a separate
    transaction.
    """
    holidays = holiday_repo.holidays_in_range(
        session, request.start_date, request.end_date
    )
    return count_leave_days(
        request.start_date,
        request.end_date,
        [holiday.holiday_date for holiday in holidays],
    )


def _materialized_years(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    from_year: int,
) -> list[YearBalance]:
    """Lock year `from_year` and every materialized year above it, ascending (AD-3).

    Balance years are materialized CONTIGUOUSLY, so the first year with no row is the end of the
    walk — which is exactly what `rollover.recompute_carry_forward` relies on, and reusing that shape
    keeps the two in agreement about which years exist.

    `leave_balance_repo.lock_balance` is called DIRECTLY, never `balances._lock`: `_lock` raises
    `LookupError` on a missing row, and a missing row is precisely how this walk ENDS (the documented
    trap at `balances.py:311-316`). It takes each row `FOR UPDATE`, ascending by `leave_year` — the
    lock order AD-3 requires, and the reason the caller processes pairs in a deterministic order too.

    A missing row for `from_year` itself is a different matter and is a PROGRAMMING ERROR, not a
    client one — for BOTH callers, on different grounds:

      * the HOLIDAY path passes `Y = holiday_date.year`, and a Leave Request cannot exist for a pair
        with no balance row in its own Leave Year (`reserve`/`consume_direct` would have raised at
        submission);
      * the POLICY path passes the pair's `MIN(leave_year)`, read from a balance row that the sweep
        just found — so the row it names exists by construction.

    Either way it is raised loudly rather than silently skipped.

    `from_year` means something different to each caller, and the difference is Story 2.12's Landmine
    4: on the holiday path it is the EDITED year `Y`; on the policy path it is the pair's LOWEST
    materialized year, whose `carried_forward` is provably `0` and is what anchors the forward chain.
    Neither is ever `date.today().year`.

    🚨 THE BODY MOVED (Story 3.4, Task 11). `rollover.materialized_years` is now the ONE
    implementation, because `rollover.recompute_carry_forward` became forward-checked and needs the
    identical walk to build its projection — and `rollover` cannot import THIS module (that edge is
    already pointed the other way, `:80`, so it would be circular). This stays as a named delegation
    rather than a call-site rename purely to keep the two caller-specific notes above, which are about
    what `from_year` MEANS on each path and belong with the callers that pass it.

    The agreement between the projection and the write loop is load-bearing for AD-6; two copies of
    this walk is exactly the drift that would break it silently.
    """
    return rollover.materialized_years(
        session,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        from_year=from_year,
    )


def recalculate_for_holiday_change(
    session: Session, *, holiday_date: datetime.date
) -> RecalculationSummary:
    """Recalculate every request the holiday change affects, refusing per pair (AC2–AC5).

    Takes the CALLER'S open `Session` and opens no transaction of its own — the holiday command owns
    the ONE transaction (AD-3, and AD-19's "within the same transaction"). It must be called AFTER
    the holiday INSERT/DELETE has been flushed, so the calendar it reads is the new one.

    THE DERIVATION THAT COLLAPSES THE PROBLEM: a Leave Request may not span two Leave Years (DR-6),
    and a holiday on date `D` can only fall inside a request whose range CONTAINS `D`. Therefore
    every affected request has leave year `D.year`. There is exactly ONE edited Leave Year
    `Y = holiday_date.year`, and never a set of source years to reason about.

    ⚠️ `Y` is `holiday_date.year`, and NEVER `date.today().year`. A `_current_leave_year()` helper
    exists in `services/balance_reads.py` and `services/leave_requests.py` and is THE WRONG ONE here:
    a year-`Y` request edited during year `Y+1` would recompute from the wrong year and the
    correction would never fire. Story 2.10 recorded this exact trap for its own AC6.

    Per pair, in order:

      1. Recount every affected request against the new calendar (`domain/calendar`, the one counter).
      2. If any request prices out at ZERO working days → REFUSE the pair. `CHECK (leave_days > 0)`
         would otherwise fire as a raw 500, and AC5 forbids discovering a refusal that way. This
         refusal is ADD-ONLY (only a new holiday can remove a request's last working day).
      3. Project the whole outcome forward, purely (`domain/recalculation.project_forward`) — year
         `Y` and every materialized year above it. This refusal is where a DELETE lands (more days
         charged → Available falls → a later spent year goes negative), and it ALSO catches an ADD
         whose recompute LOWERS a stale-high `carried_forward` — see Open Decision #8.
      4. REFUSED → write the flag, write NOTHING else for this pair, and continue to the next. The
         same Employee's other Leave Types still proceed and the holiday edit still commits (AC4).
      5. NOT REFUSED → write the new `leave_days` AND the new absolute `reserved`/`consumed`
         (Landmine 2: they must move together, or the next approve of that request raises a bare
         `ValueError` — a raw 500 `deferred-work.md:56` predicted by name), then propagate
         `carried_forward` forward to its fixed point.

    Returns the summary the endpoint reports (AC8). Writes ZERO `audit_entry` rows (Landmine 5).
    """
    leave_year = holiday_date.year
    today = _today()
    occurred_at = _now()

    affected = leave_request_repo.list_requests_covering(
        session, on_date=holiday_date, today=today
    )

    # Group by the UNIT OF REFUSAL. `list_requests_covering` already orders by
    # `(employee_id, leave_type_id, id)`, and a dict preserves insertion order — so the pairs are
    # processed in a DETERMINISTIC order, which is the balance-row LOCK order (AD-3). A holiday edit
    # locks every affected balance row, and a nondeterministic order is how two concurrent edits
    # deadlock.
    pairs: dict[tuple[uuid.UUID, uuid.UUID], list[LeaveRequest]] = {}
    for request in affected:
        pairs.setdefault((request.employee_id, request.leave_type_id), []).append(
            request
        )

    requests_recalculated = 0
    pairs_recalculated = 0
    pairs_refused: list[RefusedPair] = []

    for (employee_id, leave_type_id), requests in pairs.items():
        # ---- 1. Recount, purely. Nothing is written in this block. -----------------------------
        recounted = [(request, _recount(session, request)) for request in requests]
        changed = [
            (request, new_days)
            for request, new_days in recounted
            if new_days != request.leave_days
        ]

        if not changed:
            # The holiday fell on a day this pair's requests never charged for — a Saturday or a
            # Sunday, which `count_leave_days` excludes before it ever consults the calendar
            # (weekend precedence). Nothing to correct, so nothing is written and no flag is raised:
            # a no-op edit must not rewrite a balance row.
            continue

        # ---- 2. The zero-working-days refusal (Landmine 3, Open Decision #3) -------------------
        # ADD-only: a one-working-day request on a Monday, and the Admin declares that Monday a
        # holiday. Refuse the pair and FLAG it, leaving the request and the balance entirely
        # unchanged. The alternative — auto-cancelling the request and releasing its days — invents
        # a state transition no requirement grants, and would need an `audit_entry` row (breaking
        # SM-4's premise). Note this deliberately does NOT raise `ZERO_LEAVE_DAYS`: that is an ERROR
        # CODE that ABORTS a submission, and AC4 requires this edit to COMMIT.
        prices_out_to_zero = any(new_days == 0 for _request, new_days in changed)

        # ---- 3. The forward check (AC5) — PURE, and BEFORE the first write for this pair --------
        leave_type = leave_type_repo.get_leave_type(session, leave_type_id)
        if leave_type is None:
            # Unreachable — the Leave Request holds a valid FK — and not a client error if it ever
            # happened, so it is loud rather than silently a no-op (the `recompute_carry_forward`
            # precedent).
            raise LookupError(f"no leave_type row for id={leave_type_id}")

        years = _materialized_years(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            from_year=leave_year,
        )
        edited = years[0]

        # ⚠️ `adjust_reserved`/`adjust_consumed` take ABSOLUTE values, not deltas (Landmine 1). The
        # new total aggregates EVERY Pending (resp. future-Approved) request for this pair in this
        # year — not only the ones this holiday touched — so it is the row's CURRENT total plus the
        # sum of the deltas over the affected requests. Passing a delta where an absolute is expected
        # would zero out every unaffected request's reservation, and no CHECK would catch it (a
        # SMALLER `reserved` never violates `available >= 0`). That is a silent data-corruption bug
        # that ships green.
        delta_reserved = sum(
            new_days - request.leave_days
            for request, new_days in changed
            if request.status == vocabulary.STATUS_PENDING
        )
        delta_consumed = sum(
            new_days - request.leave_days
            for request, new_days in changed
            if request.status == vocabulary.STATUS_APPROVED
        )
        new_reserved = edited.reserved + delta_reserved
        new_consumed = edited.consumed + delta_consumed

        projection = project_forward(
            years=years,
            new_reserved=new_reserved,
            new_consumed=new_consumed,
            carries_forward=leave_type.carries_forward,
            carry_forward_cap=leave_type.carry_forward_cap,
        )

        # ---- 4. REFUSED → flag the pair, write nothing else, keep going (AC4, AC5) --------------
        if prices_out_to_zero or projection.refused:
            employee = employee_repo.load_employee(session, employee_id)
            if employee is None:
                # Unreachable for the same reason as the Leave Type above: the request holds the FK.
                raise LookupError(f"no employee row for id={employee_id}")

            admin_review_flag_repo.insert_admin_review_flag(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                cause=vocabulary.CAUSE_HOLIDAY_RECALCULATION,
                occurred_at=occurred_at,
            )
            pairs_refused.append(
                RefusedPair(
                    employee_id=employee_id,
                    employee_name=employee.full_name,
                    leave_type_id=leave_type_id,
                    leave_type_code=leave_type.code,
                    leave_year=leave_year,
                    cause=vocabulary.CAUSE_HOLIDAY_RECALCULATION,
                )
            )
            continue

        # ---- 5. NOT REFUSED → apply. Nothing below can raise; the projection proved it. ---------
        # `leave_days` and the balance quantities move TOGETHER, in this one transaction (Landmine 2,
        # `deferred-work.md:56`): lower a Pending request's `reserved` without rewriting its
        # `leave_days` to match and the next approve of it explodes with a bare `ValueError` — a raw
        # 500 that was written down as "reachable only once an out-of-band reserved-adjust endpoint
        # ships". This story is that ship.
        for request, new_days in changed:
            leave_request_repo.set_leave_days(
                session, request_id=request.id, leave_days=new_days
            )
            requests_recalculated += 1

        # ABSOLUTE values (Landmine 1). Both mutators re-check `available >= 0` under the row lock
        # and raise a guarded `ValueError` on a violation — they CANNOT fire here, because
        # `project_forward` already proved the final state is non-negative, and every intermediate
        # state is too: a DELETE raises both quantities (so the intermediate, holding the OLD lower
        # `consumed`, is above the final), and an ADD lowers both (so the intermediate is above the
        # pre-edit Available, which is non-negative by the CHECK). If one of these ever raises, there
        # is an AC5 bug in the projection — the guard is the backstop, the projection is the gate.
        if delta_reserved:
            balances.adjust_reserved(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                reserved=new_reserved,
            )
        if delta_consumed:
            balances.adjust_consumed(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                consumed=new_consumed,
            )

        # Propagate `carried_forward` forward through every materialized later year, to the fixed
        # point (AD-6). This path already ran its OWN `project_forward` above and only reaches here
        # when the projection PASSED, so `recompute_carry_forward`'s internal forward check (Story
        # 3.4, Task 11) is a second look at an answer already known — it cannot refuse here, and the
        # `cause` below is therefore unreachable in practice. It is passed honestly all the same:
        # a flag stamped with the wrong reason is worse than one that never fires.
        rollover.recompute_carry_forward(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=leave_year,
            cause=vocabulary.CAUSE_HOLIDAY_RECALCULATION,
            occurred_at=occurred_at,
        )
        pairs_recalculated += 1

    return RecalculationSummary(
        requests_recalculated=requests_recalculated,
        pairs_recalculated=pairs_recalculated,
        pairs_refused=pairs_refused,
    )


def recalculate_for_policy_change(
    session: Session,
    *,
    leave_type_id: uuid.UUID,
    annual_entitlement: int,
    carries_forward: bool,
    carry_forward_cap: int | None,
) -> RecalculationSummary:
    """Re-derive every materialized balance for one Leave Type under its NEW policy (2.12, AC5, AC6).

    The SIBLING of `recalculate_for_holiday_change` above — same forward check, same per-pair
    refusal, same `admin_review_flag`, same `200` + summary. It reuses `RefusedPair` and
    `RecalculationSummary` unchanged; a second summary type would fork the API projection and the
    frontend types that are already shaped around these.

    Takes the CALLER'S open `Session` and opens no transaction of its own (AD-3). It MUST be called
    AFTER the `leave_type` UPDATE has been flushed — the caller passes the NEW attribute values in,
    and the recomputation this triggers reads the new row — exactly the discipline
    `services/holidays.py` uses (flush the calendar edit, THEN recalculate).

    --- The one asymmetry, and every landmine is downstream of it ---

    A HOLIDAY change moves `reserved`/`consumed` in exactly ONE Leave Year (`Y = holiday_date.year`;
    a request cannot span two, DR-6), and everything above `Y` moves only through `carried_forward`.

    A POLICY change moves `prorated_entitlement` in EVERY materialized year, INDEPENDENTLY and all at
    once — and moves `reserved`/`consumed` NOT AT ALL. Nothing about it is confined to one year.
    Three consequences, each of which would ship green and be wrong:

      1. `project_forward`'s fixed-point `break` is UNSOUND here, so this passes
         `new_prorated_by_year` and the projection skips it (Landmine 1, and the reason that
         parameter exists).
      2. `rollover.recompute_carry_forward` CANNOT be the writer for the later years: it PRESERVES
         `prorated_entitlement` and `entitlement_basis` by design — its own docstring hands the
         re-proration to this story by name — so leaning on it would apply the new policy to ONE year
         and leave every year above it on the old one, wrong and believed. So this writes EVERY
         materialized year itself, ascending, through `set_accrual`, from the numbers the projection
         already produced. `recompute_carry_forward` is then called ONCE, as AC6's explicit trigger,
         where it must be a provable NO-OP (Landmine 2 — and a test asserts the rows are
         byte-identical across that call, which is what makes AC6 a fact rather than a ceremony).
      3. The walk starts at the pair's LOWEST materialized year — never `date.today().year`, and
         never `_current_leave_year()`. That year's `carried_forward` is provably `0`, and that zero
         is what anchors the chain (Landmine 4).

    Per pair, in order:

      1. Compute `new_prorated_by_year` for EVERY materialized year — `prorate_entitlement(new
         annual, employee.joining_date, y)`, the one implementation of the floor rule.
      2. Project the whole outcome forward, PURELY, before the first write for that pair
         (`domain/recalculation.project_forward`). `new_reserved`/`new_consumed` are the row's
         CURRENT absolutes, passed unchanged — a policy change moves neither.
      3. REFUSED → write the flag with `CAUSE_POLICY_RECALCULATION`, write NOTHING else for this
         pair, and continue. The same Employee's other Leave Types and every other Employee still
         proceed, and the policy change still commits (AD-19, AC5).
      4. NOT REFUSED → `set_accrual` for every materialized year ascending, then the explicit
         `recompute_carry_forward` (AC6).

    `requests_recalculated` is ALWAYS `0` on this path, and that is not a stub. A policy change
    touches no Leave Request: `leave_days` is a function of the CALENDAR, not of entitlement (AD-18),
    and `set_leave_days`'s docstring names exactly one sanctioned caller — the holiday recalculation
    above. This is not it, and that docstring is not to be widened.

    Writes ZERO `audit_entry` rows (Landmine 6). `audit_entry_repo` is not imported by this module at
    all, and its absence is the proof — the `services/rollover.py` idiom. SM-4's exact-count ledger
    (14 rows, with its per-`subject_type` breakdown) must stay literally true through a policy edit.

    Returns the summary the endpoint answers `200` with (AC5, AC11).
    """
    occurred_at = _now()

    leave_type = leave_type_repo.get_leave_type(session, leave_type_id)
    if leave_type is None:
        # Unreachable — the caller loaded and updated this row moments ago — and not a client error
        # if it ever happened, so it is loud rather than silently a no-op (the
        # `recompute_carry_forward` precedent).
        raise LookupError(f"no leave_type row for id={leave_type_id}")

    # The PAIRS. Every Employee holding a balance in this Leave Type, with the FIRST year they hold
    # one — ascending by `employee_id`, which IS the balance-row lock order (AD-3), so two concurrent
    # policy edits cannot deadlock against each other.
    #
    # A pair created BETWEEN this sweep and the commit is a benign TOCTOU (Open Decision #10): the
    # `create_employee` hook reads the LIVE `leave_type` row, so a new Employee's balance is
    # materialized under the NEW policy anyway. It mirrors the concurrent-create materialization race
    # Story 2.4's review already accepted.
    pairs = leave_balance_repo.list_pairs_for_leave_type(
        session, leave_type_id=leave_type_id
    )

    pairs_recalculated = 0
    pairs_refused: list[RefusedPair] = []

    for employee_id, first_leave_year in pairs:
        employee = employee_repo.load_employee(session, employee_id)
        if employee is None:
            # Unreachable — the balance row holds the FK — and loud rather than a silent skip.
            raise LookupError(f"no employee row for id={employee_id}")

        # Lock the pair's rows FOR UPDATE, ascending, from the LOWEST materialized year (Landmine 4).
        years = _materialized_years(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            from_year=first_leave_year,
        )

        # ---- The NEW proration, in EVERY materialized year (Landmine 1) -----------------------
        # `prorate_entitlement` is POSITIONAL, and it is the ONE implementation of the floor rule
        # (DR-9). Each year is prorated INDEPENDENTLY against the Employee's own `joining_date`: a
        # mid-year joiner's first year is reduced, every later year is not, and a floor-rounded
        # change can move one while leaving another still — which is precisely why the projection may
        # not shortcut on "this year's figure did not move".
        new_prorated_by_year = {
            year.leave_year: prorate_entitlement(
                annual_entitlement, employee.joining_date, year.leave_year
            )
            for year in years
        }

        # ---- The forward check (AC5) — PURE, and BEFORE the first write for this pair ----------
        # `new_reserved`/`new_consumed` are the LOWEST year's CURRENT absolutes, unchanged: a policy
        # change moves neither quantity. (`adjust_reserved`/`adjust_consumed` are therefore NOT
        # called anywhere below — they take absolutes and this story has no absolute to give them.)
        projection = project_forward(
            years=years,
            new_reserved=years[0].reserved,
            new_consumed=years[0].consumed,
            carries_forward=carries_forward,
            carry_forward_cap=carry_forward_cap,
            new_prorated_by_year=new_prorated_by_year,
        )

        # ---- REFUSED → flag the pair, write nothing else, keep going (AC5) ----------------------
        # The flag names `projection.refused_year` — the year the refusal was DISCOVERED at, which is
        # the year the Admin has to go and look at, and is NOT necessarily the lowest one (Open
        # Decision #7). `refused_year` is non-`None` whenever `refused` is `True`, by the
        # projection's own contract.
        if projection.refused:
            refused_year = projection.refused_year
            assert refused_year is not None  # the projection's contract; narrows the type
            admin_review_flag_repo.insert_admin_review_flag(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=refused_year,
                cause=vocabulary.CAUSE_POLICY_RECALCULATION,
                occurred_at=occurred_at,
            )
            pairs_refused.append(
                RefusedPair(
                    employee_id=employee_id,
                    employee_name=employee.full_name,
                    leave_type_id=leave_type_id,
                    leave_type_code=leave_type.code,
                    leave_year=refused_year,
                    cause=vocabulary.CAUSE_POLICY_RECALCULATION,
                )
            )
            continue

        # ---- NOT REFUSED → apply. Nothing below can raise; the projection proved it. ------------
        # EVERY materialized year, ascending, through `set_accrual` — the sole legal writer of the
        # accrual triple (AD-17), which computes `accrued` from its two parts and satisfies the
        # non-deferrable equality CHECK in one statement. No ninth balance method (Landmine 7).
        #
        # `carried_forward`: the LOWEST year keeps the value on its row (it is provably 0 — there is
        # no year below to carry from — and nothing this change does can move it); every year above
        # takes the value the projection computed for it. `entitlement_basis` is OVERWRITTEN with the
        # new `annual_entitlement` in every year: that column is what makes a re-derivation possible
        # at all (erd.md L215 — "without it, FR-06's RECALCULATE disposition has nothing to
        # recalculate from"), so RECALCULATE re-derives FROM the new annual entitlement and writes it
        # as the new basis (Open Decision #8; AC5's "re-derived from `entitlement_basis`" read
        # literally is circular, and this is the operative meaning).
        #
        # `set_accrual`'s `available >= 0` guard CANNOT fire here — `project_forward` already proved
        # the final state of every year is non-negative. If it ever does, there is an AC5 bug in the
        # projection: the guard is the backstop, the projection is the gate.
        for year in years:
            balances.set_accrual(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=year.leave_year,
                prorated_entitlement=new_prorated_by_year[year.leave_year],
                carried_forward=(
                    year.carried_forward
                    if year.leave_year == years[0].leave_year
                    else projection.carried_forward_by_year[year.leave_year]
                ),
                entitlement_basis=annual_entitlement,
            )

        # AC6: AD-6's carry-forward recomputation, triggered EXPLICITLY — "because a policy change is
        # not a balance change and would otherwise never fire" (architecture §6.3). It runs from the
        # lowest materialized year, propagating upward, and it MUST BE A NO-OP: the projection and
        # `recompute_carry_forward` are the one propagation rule evaluated twice, and they agree by
        # construction. A test asserts the rows are byte-identical across this call, which is what
        # turns AC6 from a ceremony into a proof that the loop above wrote what AD-6 requires.
        rollover.recompute_carry_forward(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=years[0].leave_year,
            cause=vocabulary.CAUSE_POLICY_RECALCULATION,
            occurred_at=occurred_at,
        )
        pairs_recalculated += 1

    return RecalculationSummary(
        # ALWAYS 0 — a policy change touches no Leave Request (AD-18). Not a stub; see the docstring.
        requests_recalculated=0,
        pairs_recalculated=pairs_recalculated,
        pairs_refused=pairs_refused,
    )
