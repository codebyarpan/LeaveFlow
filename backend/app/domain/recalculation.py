"""The forward projection — what a recalculation WOULD do, computed before it does anything.

Implements: AD-19 (a recalculation that would drive Available negative in the edited Leave Year or
in any materialized later one leaves that Employee × Leave Type pair ENTIRELY unchanged), AD-6 (the
carry-forward propagation this projects), AD-5 (the schema CHECKs are a BACKSTOP, never a gate),
AD-1 / NFR-08. AC4, AC5.

--- Why this module exists at all: AC5 says PREDICTED, never CAUGHT ---

    "the refusal was discovered by the forward check, never by an AD-5 CHECK violation."

Every other refusal in this codebase may be discovered late and still be correct, because it ABORTS
the command — `INSUFFICIENT_BALANCE` and `TRANSITION_NOT_ALLOWED` roll the whole transaction back.
This one may not: AD-19 requires the rest of the holiday edit to COMMIT while the refused pair is
left untouched. A refusal discovered by a database error has already poisoned the transaction, and
the only ways back are a rollback (which discards the pairs that succeeded) or a SAVEPOINT (which is
still the database doing the discovering). So the following are all AC5 violations, however green
the suite goes:

    try: balances.adjust_reserved(...)      # ← caught, not predicted
    except ValueError: flag(...)

    try: session.flush()                    # ← the CHECK found it, not you
    except IntegrityError: session.rollback(); flag(...)

    with session.begin_nested(): ...        # ← a savepoint rolling back on a DB error is
                                            #   still the DB discovering the refusal

The shape that satisfies AC5 is this module: project the ENTIRE outcome purely, in memory, BEFORE
the first write for that pair. If the projection says negative, the service writes the flag and
touches nothing else. If it says fine, the service applies — and now `adjust_reserved`,
`adjust_consumed` and `set_accrual` CANNOT raise their guarded `ValueError`s, because the check
already proved they won't. That is also what keeps AD-5's CHECKs a backstop rather than a gate.

--- Purity is the mechanism, not the decoration ---

Standard library and `domain/carry_forward` only: no ORM, no session, no clock, no I/O. The
import-linter "domain/ is pure" contract fails the build on a violation, and the tests
(`tests/domain/test_recalculation.py`) run with no fixture. A check that needed a database could not
run before the writes; a check that runs before the writes cannot need a database.

--- The one derivation that collapses the problem ---

A Leave Request may not span two Leave Years (DR-6, enforced at submission as
`SPANS_TWO_LEAVE_YEARS`), and a holiday on date `D` can only fall inside a request whose range
CONTAINS `D`. Therefore every request affected by a holiday change has leave year `D.year`. There is
exactly ONE edited Leave Year `Y` per pair — never a set of source years — and this function reasons
only about `Y` and the materialized years above it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.carry_forward import carry_forward_days


@dataclass(frozen=True)
class YearBalance:
    """One materialized `leave_balance` year, as pure numbers (DR-3).

    `accrued` is deliberately ABSENT: it is not an independent quantity but the non-deferrable
    `CHECK (accrued = prorated_entitlement + carried_forward)` restated, and carrying it here would
    invite a projection that moved one without the other — the exact inconsistency `set_accrual`
    exists to prevent. `available` is absent for the same reason (DR-3: it is never a column, always
    `accrued − consumed − reserved`).

    Frozen: a balance year is a value, and the projection never mutates its inputs.
    """

    leave_year: int
    prorated_entitlement: int
    carried_forward: int
    reserved: int
    consumed: int


@dataclass(frozen=True)
class ForwardProjection:
    """What the recalculation WOULD do to one (Employee, Leave Type) pair — the whole outcome.

    `refused` and `refused_year` carry the AC4/AC5 verdict: the FIRST year whose Available would go
    negative. `refused_year` is `None` iff `refused` is `False`.

    `carried_forward_by_year` names every year ABOVE `Y` this recalculation must rewrite, and the
    value it must be rewritten to. The two paths read it differently, and the difference is Story
    2.12's Landmine 2:

      * THE HOLIDAY PATH (`new_prorated_by_year is None`). The service does not write from this map
        — it calls `rollover.recompute_carry_forward`, which is the one implementation of the
        forward propagation (AD-6) — but the two agree by construction, and that agreement is what
        makes the projection predictive rather than merely advisory. An EMPTY map means the fixed
        point was reached immediately: nothing above `Y` moves.
      * THE POLICY PATH (`new_prorated_by_year` supplied). `recompute_carry_forward` PRESERVES
        `prorated_entitlement` and `entitlement_basis` — by design, and its own docstring hands the
        re-proration to Story 2.12 by name — so it CANNOT be the writer here. The service writes
        every materialized year itself, through `set_accrual`, and this map is where it reads each
        year's `carried_forward` from. There is no fixed-point break on that path, so EVERY year
        above `Y` appears here, including one whose value did not change. An empty map therefore
        means only that there IS no year above `Y`.
    """

    refused: bool
    refused_year: int | None
    carried_forward_by_year: dict[int, int]


def project_forward(
    *,
    years: Sequence[YearBalance],
    new_reserved: int,
    new_consumed: int,
    carries_forward: bool,
    carry_forward_cap: int | None,
    new_prorated_by_year: dict[int, int] | None = None,
) -> ForwardProjection:
    """Project the recalculation forward from `Y`, and say whether it would go negative (AC4, AC5).

    A pure function of its arguments: same inputs → same output, no clock, no I/O, no mutation.

    Serves BOTH recalculating commands. A HOLIDAY change (Story 2.11) leaves `new_prorated_by_year`
    at `None` and this behaves exactly as it always has. A POLICY change (Story 2.12) supplies it,
    and the walk changes in the two ways Landmine 1 requires — see that argument's note below.

    Args:
        years: The pair's materialized balance years, ASCENDING and CONTIGUOUS. `years[0]` is the
            year the walk STARTS at: the edited Leave Year `Y` on the holiday path, and the LOWEST
            materialized year on the policy path (where there is no single edited year, and where
            starting anywhere else would build the chain on a `carried_forward` derived from the OLD
            policy in the year below — Landmine 4). The service builds this by locking that year and
            walking upward until a year has no row — years are materialized in order, so the first
            gap is the end (the same walk `rollover.recompute_carry_forward` performs).
        new_reserved: The NEW ABSOLUTE Reserved total for `years[0]` — not a delta. It aggregates
            EVERY Pending request for the pair in that year, not only the ones this holiday touched.
            A POLICY change moves neither Reserved nor Consumed, so it passes the row's CURRENT
            absolute, unchanged.
        new_consumed: The NEW ABSOLUTE Consumed total for `years[0]` — likewise absolute, and
            likewise unchanged by a policy change.
        carries_forward: The Leave Type's attribute, read as data (AD-11, DR-11). On the policy path
            this is the NEW value — the caller has already flushed the `leave_type` UPDATE.
        carry_forward_cap: The Leave Type's cap, or `None` for no ceiling (Story 2.10, Open
            Decision #2 — a NULL cap on a CARRYING type is UNCAPPED, and this story inherits that
            for free by reusing `carry_forward_days` rather than re-deriving the clamp). On the
            policy path this too is the NEW value.
        new_prorated_by_year: THE POLICY PATH (Story 2.12, Landmine 1). `None` on the holiday path,
            where behaviour is byte-identical to before. When SUPPLIED it must name EVERY year in
            `years`, mapping each to its re-prorated entitlement under the new
            `annual_entitlement` — and it changes the walk in two ways:

              1. each year's `prorated_entitlement` is read from the MAP rather than off the row;
              2. THE FIXED-POINT `break` BELOW IS SKIPPED ENTIRELY.

            (2) is the whole reason this parameter exists. The break's reasoning — "this year's
            carry-forward is already correct, so its Available is unchanged, and every later year
            derives from THIS one" — is airtight for a holiday change, where the ONLY thing that can
            move a later year is its `carried_forward`. It is FALSE for a policy change, which moves
            `prorated_entitlement` in every materialized year INDEPENDENTLY: a year whose
            `carried_forward` does not move can still go negative through its OWN re-proration.

            The case that actually happens: a NON-CARRYING type (`carries_forward=False` — CL and
            FL, two of the three seeded types) has `carry_forward_days() == 0` and a stored
            `carried_forward` of `0`, so `carried == year.carried_forward` on the FIRST iteration
            and the walk would exit before checking a single later year. Drop such a type's
            entitlement while a later year is already spent, and the projection would answer
            "not refused" while `set_accrual`'s `available >= 0` guard fires a bare `ValueError` —
            a raw 500, and an AC5 violation, with every one of Story 2.11's tests still green. A
            carrying type reaches the same place whenever the cap binds.

            Nor can the break be kept behind a `new_prorated == year.prorated_entitlement` guard:
            floor-rounded proration means a year's figure can be UNCHANGED while a later year's
            moves (`12 → 13` leaves a September joiner's first year at `4` and moves every full year
            from `12` to `13`), so the equality is not transitive up the chain. Materialized years
            are one per Leave Year since joining; walking all of them is free. Walk them all.

    Returns:
        A `ForwardProjection`. `refused=True` names the FIRST year that would go negative and the
        service leaves the pair entirely alone; `refused=False` guarantees that
        `adjust_reserved`/`adjust_consumed`/`set_accrual` cannot raise on this pair.
    """
    carried_forward_by_year: dict[int, int] = {}
    # The policy path is exactly "a map was supplied". Bound once, read twice below, so the two
    # divergences (the substitution and the skipped break) are visibly the SAME condition.
    re_prorating = new_prorated_by_year is not None

    def _prorated(year: YearBalance) -> int:
        """This year's prorated entitlement: the NEW figure on the policy path, the stored one else.

        A `KeyError` here is a caller bug, not a data condition — the policy path must supply every
        materialized year — and it is left to raise loudly rather than silently falling back to the
        stored value, which would apply the new policy to some years and the old to others.
        """
        if new_prorated_by_year is None:
            return year.prorated_entitlement
        return new_prorated_by_year[year.leave_year]

    # ---- The starting year `years[0]` ----------------------------------------------------------
    # `available = accrued − consumed − reserved` (DR-3), with `accrued = prorated + carried` (the
    # non-deferrable equality CHECK). This is where a holiday DELETE refuses: the holiday's removal
    # makes a working day reappear, `leave_days` rises, `reserved`/`consumed` rise, and Available
    # can fall below zero. A POLICY change refuses here when the new proration alone no longer
    # covers what this year has already spent and reserved.
    #
    # `carried_forward` is read off the ROW even on the policy path, and correctly: on the holiday
    # path this is `Y`, whose carry was derived from a year below that this edit does not touch; on
    # the policy path this is the LOWEST materialized year, whose `carried_forward` is provably `0`
    # (there is no year below it to carry from). Either way there is nothing above it to re-derive
    # it from.
    edited = years[0]
    available = (
        _prorated(edited)
        + edited.carried_forward
        - new_consumed
        - new_reserved
    )
    if available < 0:
        return ForwardProjection(
            refused=True,
            refused_year=edited.leave_year,
            carried_forward_by_year={},
        )

    # ---- Every materialized year above it, ascending ------------------------------------------
    # AD-6: "Recomputation propagates forward through every materialized later year." Lowering
    # `available(Y)` lowers `carried_forward(Y+1)`, which lowers `available(Y+1)`, which can lower
    # `carried_forward(Y+2)` — and a year that is ALREADY SPENT goes negative. That is the refusal
    # AC4 names, and it does not necessarily surface at `Y`.
    for year in years[1:]:
        carried = carry_forward_days(
            available=available,
            carries_forward=carries_forward,
            carry_forward_cap=carry_forward_cap,
        )

        if carried == year.carried_forward and not re_prorating:
            # THE FIXED POINT — and it is SOUND ONLY ON THE HOLIDAY PATH. This year's carry-forward
            # is already correct, so its Available is unchanged — and it is committed, so the
            # `available >= 0` CHECK already holds for it. Every later year derives from THIS one,
            # so nothing above can have moved either. Stop. This mirrors
            # `rollover.recompute_carry_forward`'s stop condition exactly; it is the fixed point,
            # not an optimization.
            #
            # On the POLICY path the premise is false — a later year moves through its own
            # re-proration, not only through `carried_forward` — so "this year's carry-forward
            # didn't move" no longer implies "this year's Available didn't move", and the walk must
            # continue. See `new_prorated_by_year` in the docstring; this guard is Landmine 1.
            break

        available = (
            _prorated(year) + carried - year.consumed - year.reserved
        )
        if available < 0:
            # ⚠️ This check CANNOT be inferred from `carried`. `carry_forward_days` clamps at
            # `max(0, …)`, so it NEVER returns a negative — a year driven under water reports a
            # perfectly innocent `0`. Availability must be tested independently, at every single
            # year, and that is what this line is.
            return ForwardProjection(
                refused=True,
                refused_year=year.leave_year,
                carried_forward_by_year={},
            )

        carried_forward_by_year[year.leave_year] = carried

    return ForwardProjection(
        refused=False,
        refused_year=None,
        carried_forward_by_year=carried_forward_by_year,
    )
