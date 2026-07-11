"""The reporting-cycle detection logic, proven DB-free over a plain `parent_of` dict.

Implements the unit side of AC7 (`AD-23`, `G7`): `services.employee._would_close_cycle` is
the gate that refuses a manager assignment which would close a cycle. Extracted as a pure
function over a `parent_of` callable, so every cycle shape is provable here without paying
for a PostgreSQL round-trip per shape (Task 7). The integration test still drives the two
canonical shapes (self, A→B→A) end to end through the real database.
"""

import uuid

from app.services.employee import _would_close_cycle


def _id() -> uuid.UUID:
    """A fresh, deterministic-free id. `uuid4` is fine here — these ids are compared, not
    persisted, so the workflow's `Math.random`/`uuid` constraints do not apply to a test."""
    return uuid.uuid4()


def _parent_of(chain: dict[uuid.UUID, uuid.UUID | None]):
    """Build a `parent_of` callable from an explicit id→manager_id map (a missing key ⇒ None)."""
    return lambda employee_id: chain.get(employee_id)


def test_assigning_self_as_manager_closes_a_cycle() -> None:
    """The self-loop (`manager_id == id`) is a cycle, caught on the walk's first step."""
    e = _id()
    assert _would_close_cycle(e, e, _parent_of({})) is True


def test_a_to_b_to_a_closes_a_cycle() -> None:
    """Assigning B as A's manager, where B already reports to A, closes A→B→A."""
    a, b = _id(), _id()
    # B currently reports to A. Now we propose A's manager = B.
    assert _would_close_cycle(a, b, _parent_of({b: a})) is True


def test_a_manager_with_no_chain_is_no_cycle() -> None:
    """Assigning a top-of-chain manager (who reports to no one) closes nothing."""
    a, b = _id(), _id()
    assert _would_close_cycle(a, b, _parent_of({b: None})) is False


def test_a_long_acyclic_chain_is_no_cycle() -> None:
    """A deep chain that never reaches the target is not a cycle."""
    a, b, c, d = _id(), _id(), _id(), _id()
    # Proposed: a's manager = b; b→c→d→None. `a` is nowhere in that chain.
    assert _would_close_cycle(a, b, _parent_of({b: c, c: d})) is False


def test_a_preexisting_unrelated_cycle_terminates_without_looping() -> None:
    """A corrupt pre-existing cycle NOT involving the target terminates (the `visited` guard).

    If the data already held B→C→B (a cycle the DB should never permit), a naive walk would
    loop forever. The `visited` set makes the function return `False` — no cycle *through the
    target* — rather than hang. Defensive, not a normal path.
    """
    a, b, c = _id(), _id(), _id()
    assert _would_close_cycle(a, b, _parent_of({b: c, c: b})) is False
