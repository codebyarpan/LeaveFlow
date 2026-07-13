"""The balance-mutation module — exactly eight operations, the sole writer of a balance column.

Implements: FR-07 (available with reserved/consumed alongside), FR-08/FR-09/FR-10 (the
lifecycle transitions later stories wire to these primitives), DR-3/DR-4 (available is derived,
never stored), AD-3 (each operation runs inside the CALLER'S single transaction and decides
from the row read under `SELECT … FOR UPDATE`), AD-5 (the schema CHECKs are a BACKSTOP; this
module is the GATE — `reserve`/`consume_direct` pre-check and raise `INSUFFICIENT_BALANCE`
before any write, so a CHECK never reaches a client as a 500), AD-17 (this is the ONE module
that mutates a `leave_balance` quantity — no route, repository, job or other service writes
`accrued`/`reserved`/`consumed`/`prorated_entitlement`/`carried_forward`/`entitlement_basis`;
every mutation flows through here). SM-6.

--- Exactly eight public operations (AC4) ---

This module exposes EXACTLY: `reserve`, `consume_reserved`, `consume_direct`,
`release_reserved`, `release_consumed`, `adjust_reserved`, `adjust_consumed`, `set_accrual` —
and nothing else public (helpers are `_`-prefixed). Reads live in `services/balance_reads.py`
so this module stays exactly the eight mutators (`tests/test_balances_module_surface.py` fails
the build if a ninth public callable appears here).

--- The transaction is the caller's (AD-3) ---

Every mutator takes the open `Session` and does NOT open or commit its own: the calling command
owns the one transaction. Each mutator acquires its row with the repository's `lock_balance`
(`SELECT … FOR UPDATE`), computes the outcome from the LOCKED row in this transaction (never a
value a preview returned earlier — AD-3's TOCTOU rule), and writes. `set_accrual` is the
materializer: an upsert (create-or-update) that keeps this module at exactly eight methods —
there is no separate public "create balance row" function.

The `INSUFFICIENT_BALANCE` factory mirrors `services/leave_types.py`'s typed-refusal shape:
one message at module level, `details` carrying the numbers (AD-5, NFR-17).
"""

import uuid

from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import leave_balance as leave_balance_repo
from app.repositories.models import LeaveBalance

# One message per refusal, stated once at module level — the `services/leave_types.py` idiom.
# `details` names the numbers because "not enough balance" is not an actionable answer (NFR-17).
_INSUFFICIENT_BALANCE_MESSAGE = "The requested days exceed the available balance."


def _insufficient_balance(days_requested: int, days_available: int) -> DomainError:
    """Build the `400 INSUFFICIENT_BALANCE` refusal, naming the numbers (AD-5, NFR-17).

    Raised by `reserve`/`consume_direct` when `days > available`, decided under the row lock
    BEFORE any write, so the `leave_balance` non-negativity CHECK stays a backstop and never
    surfaces as a raw 500.
    """
    return DomainError(
        code=vocabulary.INSUFFICIENT_BALANCE,
        message=_INSUFFICIENT_BALANCE_MESSAGE,
        details={"days_requested": days_requested, "days_available": days_available},
    )


def _lock(
    session: Session,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
) -> LeaveBalance:
    """Acquire the target balance row `FOR UPDATE`, or fail loud on a materialization gap.

    Every existing Employee×Leave-Type pair has a materialized current-year row (Story 2.4's
    create hooks), so a missing row is a programming error — an operation on a balance that was
    never materialized — not a client error. A `LookupError` surfaces it as a 500 legibly,
    rather than an `AttributeError` on `None`.
    """
    balance = leave_balance_repo.lock_balance(
        session,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        leave_year=leave_year,
    )
    if balance is None:
        raise LookupError(
            "no leave_balance row for "
            f"(employee={employee_id}, leave_type={leave_type_id}, year={leave_year}); "
            "it must be materialized (Story 2.4 create hooks) before it is mutated"
        )
    return balance


def _available(balance: LeaveBalance) -> int:
    """`available = accrued − consumed − reserved`, from the three STORED quantities (DR-3).

    Never a stored column — computed here from the locked row so `reserve`/`consume_direct`
    gate against the truth in THIS transaction.
    """
    return balance.accrued - balance.consumed - balance.reserved


def reserve(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    days: int,
) -> None:
    """Commit `days` to a Pending request: `reserved += days` (FR-08 submission, Story 2.6).

    The GATE (AD-5): if `days > available` (read from the locked row in this transaction),
    raise `400 INSUFFICIENT_BALANCE` naming the numbers — before any write, so the CHECK never
    fires. `available` is unchanged in net only for a transfer; a reserve REDUCES available.
    """
    if days < 0:
        raise ValueError(f"reserve({days}) is negative")
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    available = _available(balance)
    if days > available:
        raise _insufficient_balance(days_requested=days, days_available=available)
    balance.reserved += days
    session.flush()


def consume_reserved(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    days: int,
) -> None:
    """Transfer Reserved→Consumed on approval: `reserved -= days; consumed += days` (Story 2.7).

    `available` is unchanged (the days were already committed at submission). The caller
    approves exactly what was reserved, so `days ≤ reserved` by construction; a violation is a
    caller bug, guarded here (a `ValueError`) rather than left to fire the `reserved >= 0`
    CHECK as a raw 500.
    """
    if days < 0:
        raise ValueError(f"consume_reserved({days}) is negative")
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    if days > balance.reserved:
        raise ValueError(
            f"consume_reserved({days}) exceeds reserved ({balance.reserved}) — the approval "
            "consumes more than was reserved at submission; a caller invariant is broken"
        )
    balance.reserved -= days
    balance.consumed += days
    session.flush()


def consume_direct(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    days: int,
) -> None:
    """Consume WITHOUT reserving first: `consumed += days` (FR-09 managerless auto-approval).

    NEVER touches `reserved` — a managerless Employee's request is auto-approved and consumes
    directly, never having reserved; a shared `consume` would decrement `reserved` from 0 and
    violate `CHECK (reserved >= 0)`. The GATE (AD-5): if `days > available`, raise `400
    INSUFFICIENT_BALANCE` before the write.
    """
    if days < 0:
        raise ValueError(f"consume_direct({days}) is negative")
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    available = _available(balance)
    if days > available:
        raise _insufficient_balance(days_requested=days, days_available=available)
    balance.consumed += days
    session.flush()


def release_reserved(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    days: int,
) -> None:
    """Release a reservation on rejection/cancellation of a Pending request: `reserved -= days`.

    (Story 2.7/2.8.) `days ≤ reserved` by construction (a request cannot release more than it
    reserved); a violation is guarded (a `ValueError`) rather than left to fire the
    `reserved >= 0` CHECK.
    """
    if days < 0:
        raise ValueError(f"release_reserved({days}) is negative")
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    if days > balance.reserved:
        raise ValueError(
            f"release_reserved({days}) exceeds reserved ({balance.reserved})"
        )
    balance.reserved -= days
    session.flush()


def release_consumed(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    days: int,
) -> None:
    """Return consumed days on an approved-leave cancellation: `consumed -= days` (BR-05, 2.8).

    `days ≤ consumed` by construction; a violation is guarded (a `ValueError`) rather than left
    to fire the `consumed >= 0` CHECK.
    """
    if days < 0:
        raise ValueError(f"release_consumed({days}) is negative")
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    if days > balance.consumed:
        raise ValueError(
            f"release_consumed({days}) exceeds consumed ({balance.consumed})"
        )
    balance.consumed -= days
    session.flush()


def adjust_reserved(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    reserved: int,
) -> None:
    """Re-derive Reserved to an absolute value under recalculation (AD-19, Stories 2.11/2.12).

    Sets `reserved` to the recomputed absolute figure, verifying under the lock that the result
    is non-negative AND leaves `available ≥ 0` — a violation is guarded (a `ValueError`) rather
    than left to fire a CHECK. The recalculation ORCHESTRATION (per-pair refusal, `admin_review_
    flag`) is the consuming story's; this is the re-derive-with-guard primitive it calls.
    """
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    if reserved < 0:
        raise ValueError(f"adjust_reserved({reserved}) is negative")
    if balance.accrued - balance.consumed - reserved < 0:
        raise ValueError(
            f"adjust_reserved({reserved}) would make available negative "
            f"(accrued={balance.accrued}, consumed={balance.consumed})"
        )
    balance.reserved = reserved
    session.flush()


def adjust_consumed(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    consumed: int,
) -> None:
    """Re-derive Consumed to an absolute value under recalculation (AD-19, Stories 2.11/2.12).

    Sets `consumed` to the recomputed absolute figure, verifying under the lock that the result
    is non-negative AND leaves `available ≥ 0` — a violation is guarded (a `ValueError`).
    """
    balance = _lock(session, employee_id, leave_type_id, leave_year)
    if consumed < 0:
        raise ValueError(f"adjust_consumed({consumed}) is negative")
    if balance.accrued - consumed - balance.reserved < 0:
        raise ValueError(
            f"adjust_consumed({consumed}) would make available negative "
            f"(accrued={balance.accrued}, reserved={balance.reserved})"
        )
    balance.consumed = consumed
    session.flush()


def set_accrual(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    prorated_entitlement: int,
    carried_forward: int,
    entitlement_basis: int,
) -> None:
    """Materialize or recompute the accrual triple (create-or-update), in ONE statement (AD-17).

    The MATERIALIZER: because AC4 fixes the module at exactly eight methods, there is no
    separate "create balance row" function — the create hooks (Story 2.4) and later
    recalculation (2.11/2.12) both route through here. Computes `accrued = prorated_entitlement
    + carried_forward` itself (callers pass the two PARTS, never `accrued`) and upserts. On a
    fresh insert `reserved`/`consumed` fall to their `server_default` 0; the DO-UPDATE branch
    leaves them untouched (recalculation re-derives accrual only, never committed/spent). The
    single statement satisfies the non-deferrable `accrued = prorated_entitlement +
    carried_forward` equality CHECK and is idempotently re-derivable.
    """
    accrued = prorated_entitlement + carried_forward
    leave_balance_repo.upsert_accrual(
        session,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        leave_year=leave_year,
        accrued=accrued,
        prorated_entitlement=prorated_entitlement,
        carried_forward=carried_forward,
        entitlement_basis=entitlement_basis,
    )
