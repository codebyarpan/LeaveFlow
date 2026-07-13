"""Leave Type reads, the create, and the duplicate-code pre-check the service gates on.

Implements: FR-06 (Leave Types are created and listed as data, AD-11), NFR-11 (the list is
page-bounded — this issues the `LIMIT`/`OFFSET` the `api/` layer computes), AD-5 (the
`code_exists` gate that keeps a duplicate `code` a typed 409, not the `UNIQUE`'s raw 500).

--- Why the getters here take no `actor` (and are EXEMPT from the scoped-getter rule) ---

`tests/test_scoped_getters.py` reflects over every `get_`/`list_`/`find_`/`fetch_` function
that takes a `session`, requiring the AD-10 `actor` parameter so no getter returns *another
Employee's data* unscoped. `list_leave_types` and `get_leave_type` match that net by name,
but fall genuinely OUTSIDE the rule: a Leave Type is organization-wide reference data
(`{code, name, entitlement, ...}`), not Employee-derived, and its api-contracts scope is
`all` — any authenticated role reads the whole list, there is no per-row predicate to apply.
So they are added to that test's EXEMPT registry with a rationale, exactly as Story 1.5 did
for departments (Trap 1), rather than given a misleading unused `actor` param.

`code_exists` is named with neither a read-verb prefix nor a row return — it answers a
`bool` — precisely so it is correctly NOT a scoped-getter candidate.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.models import LeaveType


def list_leave_types(
    session: Session, limit: int, offset: int
) -> tuple[list[LeaveType], int]:
    """Return one page of Leave Types AND the full count, in the same call (AC3, AC4, AC9).

    The page and the total travel together — one `SELECT ... LIMIT/OFFSET` for the rows and
    one `SELECT count(*)` for the total — so the `api/` layer assembles the whole `Page`
    envelope from a single repository round-trip. Ordered by `code, id` so pages are
    deterministic: without a stable `ORDER BY`, `LIMIT/OFFSET` may repeat or skip a row
    across pages as the planner's row order shifts.

    Scope is `all` (api-contracts §4.3): every row is returned to any authenticated role, so
    there is no actor and no predicate here — this getter is EXEMPT from the scoped-getter
    rule for the reason the module docstring states.
    """
    rows = list(
        session.scalars(
            select(LeaveType).order_by(LeaveType.code, LeaveType.id).limit(limit).offset(offset)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(LeaveType)) or 0
    return rows, total


def get_leave_type(session: Session, leave_type_id: uuid.UUID) -> LeaveType | None:
    """Return the Leave Type with this id, or `None` if there is none.

    Keyed by the primary key, so at most one row matches. EXEMPT from the scoped-getter rule
    (scope `all`, reference data — see the module docstring), mirroring `get_department`.
    """
    return session.get(LeaveType, leave_type_id)


def code_exists(session: Session, code: str) -> bool:
    """Does a Leave Type already carry this `code`? The service's pre-write duplicate gate.

    Named with neither a read-verb prefix nor a row return (it answers a `bool`), so it is
    correctly not a scoped-getter candidate — the guardrail governs row-returning getters.
    The `UNIQUE (code)` constraint remains the AD-5 backstop; this is the gate that keeps a
    duplicate a typed 409 rather than the constraint's raw 500 (mirrors `_email_conflicts`).
    """
    return (
        session.scalar(select(LeaveType.id).where(LeaveType.code == code).limit(1))
        is not None
    )


def create_leave_type(
    session: Session,
    *,
    code: str,
    name: str,
    annual_entitlement: int,
    carries_forward: bool,
    carry_forward_cap: int | None,
    requires_supporting_document: bool,
) -> LeaveType:
    """Insert a new Leave Type and return it (AC3).

    A write, governed by the role gate rather than the scope contract, so it is not a
    guardrail candidate. `flush` assigns the server-default `id` so the caller can project
    it into the response before the surrounding transaction commits; it does NOT commit —
    the service owns the transaction.
    """
    leave_type = LeaveType(
        code=code,
        name=name,
        annual_entitlement=annual_entitlement,
        carries_forward=carries_forward,
        carry_forward_cap=carry_forward_cap,
        requires_supporting_document=requires_supporting_document,
    )
    session.add(leave_type)
    session.flush()
    return leave_type
