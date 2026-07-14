"""Rollover Run persistence — an INSERT, and nothing else (AD-8, AD-9).

Implements: AC1/AC8 of Story 2.10. One repository module per table (the rule Story 2.9 fixed), and
this table's entire surface is a single `INSERT`. There is NO update method and NO delete method,
for the same reason `repositories/audit_entry.py` has none: `rollover_run` is append-only, and
migration `0009` grants the application role `INSERT` and `SELECT` on it and NEITHER `UPDATE` NOR
`DELETE`. The GRANT is the guarantee; this method surface is what stops a well-meaning future story
from writing the update method in the first place.

--- And no GETTER, deliberately (Open Decision #5) ---

No acceptance criterion asks to READ this table. A `list_rollover_runs` would immediately drag in
the scoped-getter guard (`tests/test_scoped_getters.py` nets every `list_`/`get_` that takes a
`session`), which would need an exemption and a why-exempt docstring — all for a read nobody
requested. The one question the application asks about the rollover — "has year `Y` been rolled?" —
is answered WITHOUT this table: `services/rollover.recompute_carry_forward` asks whether the `Y + 1`
balance row exists, which it must read anyway. If a read surface is ever wanted, it is a clean
follow-up story with an endpoint, a scope-matrix row and a getter that earns its exemption.

`insert_rollover_run` `flush`es but does NOT `commit()`: the row is written in the SAME transaction
as every `set_accrual` the run performs, so a rolled-back run leaves no row claiming it happened
(AD-8's "because" clause — the same one Story 2.9 proved for `audit_entry`). The service commits,
once.
"""

import datetime

from sqlalchemy.orm import Session

from app.repositories.models import RolloverRun


def insert_rollover_run(
    session: Session,
    *,
    leave_year: int,
    occurred_at: datetime.datetime,
) -> None:
    """Append one row recording that the rollover ran for `leave_year` (AD-8).

    `leave_year` is the year the run CLOSED (`Y`), never the year it opened (`Y + 1`) — the ERD
    calls the column "The Leave Year rolled". `occurred_at` is a timezone-aware instant from the
    service's shell clock (AD-1); a naive datetime is a defect, not a nit, against a `TIMESTAMPTZ`.

    No `actor` column: the actor is always SYSTEM, and the ERD declines to add a column to say so.

    A second run against the same year appends a SECOND row, and that is correct — the table logs
    executions, not years, and carries no `UNIQUE (leave_year)`. Idempotence (AC5) is a property of
    the balances (`set_accrual` assigns a derived value rather than accumulating one), never of this
    log. Flushes, never commits: the caller owns the transaction (AD-3).
    """
    session.add(RolloverRun(leave_year=leave_year, occurred_at=occurred_at))
    session.flush()
