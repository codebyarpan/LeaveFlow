"""The forward projection, DB-free — the heart of AC5 (Story 2.11).

Implements the test side of: AC4 (a recalculation that would drive Available negative in the edited
Leave Year OR in any materialized later one is REFUSED for that pair) and AC5 (the refusal was
discovered by the FORWARD CHECK, never by an AD-5 `CHECK` violation).

--- Why these tests take no fixture ---

`domain/recalculation.py` is pure: no ORM, no session, no clock, no I/O (import-linter contract
"domain/ is pure" fails the build on a violation). So the entire refusal decision — the thing AC5
says must be PREDICTED rather than CAUGHT — is decidable here, with plain numbers and no database.
That is the point: if the refusal could only be tested through PostgreSQL, it would be the database
discovering it, which is precisely what AC5 forbids.

The projection mirrors `services/rollover.recompute_carry_forward`'s walk exactly — the same
ascending propagation and the same fixed-point stop — because the projection must predict what that
function will actually write. The two agreeing is what makes `adjust_reserved`/`adjust_consumed`/
`set_accrual` unable to raise: the check already proved they won't.
"""

from app.domain.recalculation import YearBalance, project_forward


def _year(
    leave_year: int,
    *,
    prorated: int,
    carried: int = 0,
    reserved: int = 0,
    consumed: int = 0,
) -> YearBalance:
    """One materialized balance year as pure numbers — a terse builder for the cases below."""
    return YearBalance(
        leave_year=leave_year,
        prorated_entitlement=prorated,
        carried_forward=carried,
        reserved=reserved,
        consumed=consumed,
    )


class TestTheEditedYear:
    """`available(Y) = (prorated + carried) − new_consumed − new_reserved`, checked first."""

    def test_a_recalculation_that_fits_is_not_refused(self) -> None:
        """The ordinary case: the new totals sit inside the year's accrual. Nothing is refused."""
        projection = project_forward(
            years=[_year(2026, prorated=20, reserved=5)],
            new_reserved=3,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is False
        assert projection.refused_year is None

    def test_a_recalculation_that_overdraws_the_edited_year_is_refused_at_Y(self) -> None:
        """A DELETE raises `leave_days`, so `reserved` rises and `available(Y)` can go NEGATIVE.

        This is the refusal in its simplest form, and it is DELETE-only: accrued is 20, and the
        recalculated reservation is 21. The forward check sees `available(Y) = −1` and refuses —
        BEFORE `adjust_reserved` is ever called, which is why that function's bare `ValueError`
        (a raw 500) is unreachable from this story's path.
        """
        projection = project_forward(
            years=[_year(2026, prorated=20, reserved=18)],
            new_reserved=21,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is True
        assert projection.refused_year == 2026

    def test_available_is_computed_from_BOTH_new_totals(self) -> None:
        """`reserved` and `consumed` both count against the same accrual — 10 + 11 > 20."""
        projection = project_forward(
            years=[_year(2026, prorated=20)],
            new_reserved=10,
            new_consumed=11,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is True
        assert projection.refused_year == 2026

    def test_exactly_zero_available_is_NOT_refused(self) -> None:
        """The CHECK is `available >= 0`, so spending the year to exactly nothing is legal.

        A boundary worth pinning: an off-by-one here would refuse a perfectly valid recalculation
        and flag a pair that needed no attention.
        """
        projection = project_forward(
            years=[_year(2026, prorated=20, carried=5)],
            new_reserved=25,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is False


class TestTheLaterYears:
    """The knock-on: `available(Y)` falls → `carried_forward(Y+1)` falls → a SPENT year goes negative."""

    def test_a_delete_that_eats_a_spent_later_year_refuses_AT_THAT_LATER_YEAR(self) -> None:
        """The refusal AC4 names, and it does NOT surface at `Y`.

        Year 2026 still has room (accrued 20, new reserved 18 → available 2). But 2027 was
        materialized with `carried_forward = 10` and has already CONSUMED 12 of its
        `10 + 5 = 15` accrued. Re-deriving carry-forward from the new `available(2026) = 2` drops
        `carried_forward(2027)` to 2, so `accrued(2027)` falls to 7 — below the 12 already spent.
        `available(2027) = −5`.

        The year the refusal is REPORTED at matters: an implementation that only checked `Y` would
        sail past this and hand `set_accrual` an accrual that fires the non-negativity CHECK as a
        raw 500 — AC5's exact failure mode.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, carried=0, reserved=18),
                _year(2027, prorated=5, carried=10, consumed=12),
            ],
            new_reserved=18,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is True
        assert projection.refused_year == 2027

    def test_an_ADD_can_refuse_TOO_when_carried_forward_is_stale_high(self) -> None:
        """An ADD lowers `reserved` and RAISES `available(Y)` — and can STILL refuse. Not a no-op.

        This is the trap the story's Orientation section calls out. `reserve`/`consume_direct` lower
        `available(Y)` and recompute NOTHING (Story 2.10 wired the top-up only into the three sites
        where `available(Y)` RISES). So a year-`Y` request submitted AFTER the rollover ran leaves
        `carried_forward(Y+1)` STALE-HIGH — higher than `min(cap, available(Y))` is now.

        `carry_forward_days` ASSIGNS a derived value; it does not only top up. So the recompute this
        ADD triggers will LOWER `accrued(Y+1)` — and if `Y+1` is already spent, that is a negative
        balance and a raw 500.

        Here: `available(2026)` after the ADD is `20 − 15 = 5`, but 2027 stores a stale
        `carried_forward = 12` and has consumed 14 of its `12 + 3 = 15`. The re-derivation drops
        carry-forward to 5, `accrued(2027)` to 8, and `available(2027)` to −6. REFUSED — on a POST.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, carried=0, reserved=15),
                _year(2027, prorated=3, carried=12, consumed=14),
            ],
            # The ADD lowered the reservation from 18 to 15 — available(2026) ROSE.
            new_reserved=15,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is True
        assert projection.refused_year == 2027

    def test_the_walk_stops_at_the_FIXED_POINT(self) -> None:
        """When the re-derived carry-forward already equals the stored one, nothing downstream moves.

        `available(2026) = 20 − 12 = 8`, and 2027 already stores `carried_forward = 8`. So the walk
        stops there: no later year can have moved either (every one derives from this one), and each
        is already non-negative because it is committed and the CHECK holds.

        This mirrors `rollover.recompute_carry_forward`'s stop condition exactly. It is the fixed
        point, not an optimization — and `carried_forward_by_year` is empty because there is nothing
        to rewrite.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, carried=0, reserved=12),
                _year(2027, prorated=10, carried=8),
            ],
            new_reserved=12,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is False
        assert projection.carried_forward_by_year == {}

    def test_the_years_that_must_be_rewritten_are_reported(self) -> None:
        """A change that DOES propagate names every year it rewrites, in ascending order.

        `available(2026)` becomes `20 − 4 = 16` → `carried_forward(2027)` becomes 16 (was 2);
        `available(2027)` becomes `10 + 16 = 26` → `carried_forward(2028)` becomes 26 (was 1).
        Both years are rewritten, and the projection says so — the same two writes
        `recompute_carry_forward` will actually perform.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, carried=0, reserved=4),
                _year(2027, prorated=10, carried=2),
                _year(2028, prorated=10, carried=1),
            ],
            new_reserved=4,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is False
        assert projection.carried_forward_by_year == {2027: 16, 2028: 26}


class TestTheLeaveTypeAttributes:
    """Carry-forward is read from the ATTRIBUTES, through `carry_forward_days` — never re-derived."""

    def test_a_lapsing_type_propagates_zero(self) -> None:
        """`carries_forward = False` → the days lapse, and the cap is never consulted (AC4 of 2.10).

        2027 stores a stale `carried_forward = 6` from somewhere; a lapsing type re-derives it to 0,
        which LOWERS `accrued(2027)` from 16 to 10 — still above the 4 consumed, so it holds.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, reserved=5),
                _year(2027, prorated=10, carried=6, consumed=4),
            ],
            new_reserved=5,
            new_consumed=0,
            carries_forward=False,
            carry_forward_cap=30,
        )

        assert projection.refused is False
        assert projection.carried_forward_by_year == {2027: 0}

    def test_a_null_cap_on_a_carrying_type_is_UNCAPPED(self) -> None:
        """Inherited from Story 2.10, Open Decision #2 — and inherited for FREE, by reuse.

        A `NULL` `carry_forward_cap` on a CARRYING type means no ceiling, not zero. This story does
        not re-decide that; it calls `carry_forward_days`, so it cannot contradict it. All 15 of
        `available(2026)` carries.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, reserved=5),
                _year(2027, prorated=10, carried=0),
            ],
            new_reserved=5,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=None,
        )

        assert projection.refused is False
        assert projection.carried_forward_by_year == {2027: 15}

    def test_the_cap_clamps_what_carries(self) -> None:
        """`min(cap, available)` — the excess above the cap lapses. Cap 6 against 15 available."""
        projection = project_forward(
            years=[
                _year(2026, prorated=20, reserved=5),
                _year(2027, prorated=10, carried=0),
            ],
            new_reserved=5,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=6,
        )

        assert projection.carried_forward_by_year == {2027: 6}


class TestTheClampIsNotAProxyForNonNegativity:
    """`carry_forward_days` clamps at `max(0, …)`, so a negative year is INVISIBLE in the carry."""

    def test_a_negative_later_year_is_caught_even_though_the_carry_reads_zero(self) -> None:
        """The trap Task 2 names: you CANNOT infer non-negativity from the carry-forward value.

        `available(2026)` is driven to 0 exactly. `carry_forward_days` therefore returns 0 — a
        perfectly innocent-looking number, clamped, never negative. But 2027 stored
        `carried_forward = 9` and has consumed 12 of its `9 + 5 = 14`; dropping the carry to 0 puts
        `accrued(2027)` at 5, below the 12 spent → `available(2027) = −7`.

        An implementation that "optimized away" the per-year `available` check and trusted the
        clamped carry would sail straight past this into a CHECK violation. So the check runs at
        EVERY year, independently.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=20, carried=0, reserved=20),
                _year(2027, prorated=5, carried=9, consumed=12),
            ],
            new_reserved=20,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is True
        assert projection.refused_year == 2027


class TestAPolicyChangeReProratesEveryYear:
    """Story 2.12, Landmine 1: `new_prorated_by_year` — and why the fixed-point `break` is UNSOUND.

    A HOLIDAY change moves `reserved`/`consumed` in exactly ONE Leave Year, and everything above `Y`
    moves only through `carried_forward`. That is what licenses the `break` above: "this year's
    carry-forward is already correct, so its Available is unchanged, and every later year derives
    from THIS one."

    A POLICY change breaks that premise. It moves `prorated_entitlement` in EVERY materialized year,
    INDEPENDENTLY and all at once. A year whose `carried_forward` does not move can STILL go
    negative — through its own re-proration. So when `new_prorated_by_year` is supplied, the break is
    skipped entirely and every materialized year is checked.

    When it is `None` the behaviour is byte-identical and the holiday path (every test above) is
    untouched.
    """

    def test_a_non_carrying_type_checks_every_later_year_despite_a_zero_carry(self) -> None:
        """THE test. Against the pre-2.12 code this returns `refused=False` — and 500s in production.

        A NON-CARRYING Leave Type (`carries_forward=False` — that is CL and FL, two of the three
        seeded types). `carry_forward_days` returns 0 unconditionally, and the stored
        `carried_forward` is already 0. So on the FIRST iteration `carried == year.carried_forward`
        → `0 == 0` → the old code `break`s, having checked not one later year.

        Here CL's `annual_entitlement` drops 12 → 2 while the Employee has already CONSUMED 8 days
        of CL in the later year. Re-prorated, 2027's accrual falls to 2 against 8 spent →
        `available(2027) = −6`. The projection MUST see it: otherwise `set_accrual`'s `available >=
        0` guard fires a bare `ValueError` → a raw 500, and AC5 is violated with every one of 2.11's
        tests still green.

        Note `Y` itself SURVIVES — `available(2026) = 2 − 0 = 2` — which is what makes this the
        landmine rather than an ordinary refusal: a check that only looked at `Y` would wave it
        through, and so does the fixed-point break that never reaches 2027.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=12, carried=0),
                _year(2027, prorated=12, carried=0, consumed=8),
            ],
            # A policy change moves NEITHER: the row's current absolutes, passed unchanged.
            new_reserved=0,
            new_consumed=0,
            carries_forward=False,
            carry_forward_cap=None,
            # The new proration, in EVERY materialized year — 12 → 2.
            new_prorated_by_year={2026: 2, 2027: 2},
        )

        assert projection.refused is True
        assert projection.refused_year == 2027

    def test_a_carrying_type_whose_cap_binds_at_Y_still_checks_the_year_above(self) -> None:
        """The same unsoundness, reached by a CARRYING type: the cap pins `carried` at the stored value.

        `available(2026)` falls from 40 to 35 under the new (lower) proration. The cap is 30, so
        `carried_forward(2027)` is `min(30, 35) = 30` — EXACTLY what 2027 already stores. The old
        break fires on that equality and never looks at 2027 at all.

        But 2027's OWN proration also dropped (40 → 5), and 2027 has 32 days consumed:
        `accrued(2027) = 5 + 30 = 35`, and `35 − 32 = 3`… still fine. Push the consumption to 36 and
        it is not: `35 − 36 = −1`. The year moved through its own re-proration, not through its
        carry-forward, which is the case the holiday path cannot produce and this one produces every
        time.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=40, carried=0, consumed=5),
                _year(2027, prorated=40, carried=30, consumed=36),
            ],
            new_reserved=0,
            new_consumed=5,
            carries_forward=True,
            carry_forward_cap=30,
            new_prorated_by_year={2026: 40, 2027: 5},
        )

        assert projection.refused is True
        assert projection.refused_year == 2027

    def test_every_materialized_year_lands_in_the_map_when_not_refused(self) -> None:
        """No break ⇒ no early exit ⇒ EVERY year above `Y` is recorded, even an unchanged one.

        The service writes `carried_forward` for every materialized year from this map (Landmine 2:
        `recompute_carry_forward` cannot be the writer, because it PRESERVES proration). A year the
        old break would have skipped must still appear here, carrying the value it must be written
        to — otherwise the service has nothing to write for it and silently leaves it on the old
        policy.

        2027's carry is unchanged at 10 (`min(30, 10)`), which is exactly where the old code
        stopped. 2028 must still be reached.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=10, carried=0),
                _year(2027, prorated=10, carried=10),
                _year(2028, prorated=10, carried=20),
            ],
            new_reserved=0,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
            # Proration unchanged at Y, so `available(2026)` is 10 and 2027's carry stays 10.
            new_prorated_by_year={2026: 10, 2027: 10, 2028: 10},
        )

        assert projection.refused is False
        assert projection.carried_forward_by_year == {2027: 10, 2028: 20}

    def test_the_holiday_path_is_byte_identical_when_the_map_is_absent(self) -> None:
        """`new_prorated_by_year=None` ⇒ today's behaviour exactly: the break still fires.

        The guarantee that Story 2.11's tests are untouched, asserted rather than assumed. These are
        the same numbers as the case above; with no map the walk stops at 2027's fixed point and
        2028 never enters the result.
        """
        projection = project_forward(
            years=[
                _year(2026, prorated=10, carried=0),
                _year(2027, prorated=10, carried=10),
                _year(2028, prorated=10, carried=20),
            ],
            new_reserved=0,
            new_consumed=0,
            carries_forward=True,
            carry_forward_cap=30,
        )

        assert projection.refused is False
        assert projection.carried_forward_by_year == {}
