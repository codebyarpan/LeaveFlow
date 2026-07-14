"""Carry-forward — the days a Leave Type carries into the next Leave Year.

Implements: FR-07 (carry-forward and lapse), DR-7 ("unused Accrued days" means AVAILABLE —
`accrued − consumed − reserved`), AD-6 (`carried_forward(Y+1) = min(carry_forward_cap,
available(Y))`, written by ASSIGNMENT and never by increment, which is what makes the rollover
idempotent by construction), DR-11 / AD-11 (Annual Entitlement, Carry-Forward and the Cap are
ATTRIBUTES of a Leave Type, stored as data and read at runtime — no cap value and no entitlement
value is fixed in code), AD-1 / NFR-08.

Like `domain/proration.py` and `domain/calendar.py`, this is a pure module: standard library only,
no ORM, no clock, no I/O. The import-linter "domain/ is pure" contract fails the build on a
violation, and its tests (`tests/domain/test_carry_forward.py`) run with no fixture (NFR-15, AC9).

--- Why this function cannot see a Leave Type ---

AC4 requires that lapse "was decided by reading the attribute, not by testing the Leave Type's
name — EL carries forward, CL and FL lapse". The cheapest way to make that unfalsifiable is to
give the function no way to know the name: it takes `carries_forward` and `carry_forward_cap` as
bare values, never a `LeaveType`. There is no `code` in scope to branch on, so a future edit
cannot quietly reintroduce `if code == "EL"` — it would have to change the signature first, and
that is a change a reviewer sees. This is also exactly what SM-5 rests on: a fourth Leave Type
created through `POST /leave-types` rolls over with no code change, because there is no code here
that knows how many Leave Types there are or what they are called.
"""


def carry_forward_days(
    *,
    available: int,
    carries_forward: bool,
    carry_forward_cap: int | None,
) -> int:
    """The days a Leave Type carries into the next Leave Year (DR-7, AD-6).

    Reads the ATTRIBUTE, never the Leave Type's code (AD-11, DR-11): `carries_forward` first, and
    only then the cap. A lapsing type carries nothing, whatever its cap says — the cap is
    meaningless when `carries_forward` is false (ERD §"Not a gap"), which is why it is nullable.

    The rules, in order:

    1. `carries_forward is False` → **0**. The days lapse, and the cap is NEVER consulted. This is
       AC4: a lapsing type with a cap of 30 sitting right there still carries 0.
    2. `carry_forward_cap is None` on a CARRYING type → **`available`**. Uncapped — no ceiling.
       This is the specification's one genuinely under-determined point (Story 2.10, Open Decision
       #2): the ERD explains the column's nullability only for LAPSING types, and AD-6's `min(cap,
       available)` is undefined for NULL. Resolved as "no ceiling", which is what `min()` degenerates
       to; the alternative reading (NULL means zero) would make a carrying type silently lapse
       everything — a wrong balance that would be believed. Distinct from a cap of `0`, which is a
       real configuration meaning "carries, ceiling zero" and correctly yields 0.
    3. Otherwise → **`min(carry_forward_cap, available)`**. The excess above the cap LAPSES (AC3).
       `min`, never `+=`: carry-forward is a DERIVED figure re-assigned from its inputs, not a
       quantity moved between years. That is the whole of AD-6, and the whole of why a re-run
       changes nothing.

    `available` cannot be negative in practice — `leave_balance`'s `accrued - consumed - reserved
    >= 0` CHECK guarantees it — but the result is clamped at 0 anyway, so the function is TOTAL and
    never returns a value that would fire a CHECK downstream in `set_accrual`.

    Args:
        available: `accrued − consumed − reserved` for the CLOSING Leave Year `Y` (DR-7 —
            "measured whenever the value is computed, not at the boundary alone"). Reserved days
            held by a still-Pending request are NOT available and so do not carry (DR-7a); when
            that request is later rejected or cancelled, `available(Y)` rises and this function is
            simply evaluated again, topping the carry-forward up.
        carries_forward: The Leave Type's `carries_forward` attribute. Read FIRST.
        carry_forward_cap: The Leave Type's `carry_forward_cap`, or `None` for no ceiling.

    Returns:
        The whole number of Leave Days carrying into `Y + 1` (DR-10 — an ``int``, never a float),
        never negative.
    """
    if not carries_forward:
        # The days lapse. The cap is not consulted — it is meaningless here (AC4, ERD).
        return 0

    if carry_forward_cap is None:
        # Uncapped: no ceiling to apply (Open Decision #2).
        return max(0, available)

    return max(0, min(carry_forward_cap, available))
