"""Leave Request persistence: the create, the pending count, the scoped reads, the AD-4 transition.

Implements: AC3/AC5 (`insert_leave_request` persists the row the submission command composed under
the balance lock — the `PENDING` managed path or the `APPROVED` managerless auto-approval; Story
2.6), the deactivation guard input (`count_pending_for_employee`, Story 1.6 made executable in 2.6),
and Story 2.7's transition half: `get_leave_request`/`list_leave_requests` (the FR-03-scoped reads a
Manager decides from) and `transition_status` (the single sanctioned AD-4 guarded conditional
UPDATE). SM-6.

--- The mutation surface: an INSERT and TWO narrow, disjoint writes; no free-form update ---

Through Story 2.6 this module exposed only an INSERT and a COUNT. Story 2.7 added the lifecycle
transitions (approve/reject/cancel) as `transition_status` — a single `UPDATE … SET status = :to
WHERE id = :id AND status = :from` (AD-4), guarded (it matches a row only in the required `from`
state) and conditional (a lost race matches zero rows → a clean 409, not a silent overwrite).

Story 2.11 adds the SECOND, and AD-18 names it as the one exception it admits: `set_leave_days`,
the recalculation of a request's frozen `leave_days` when the holiday calendar changes under it
("Only AD-19's recalculation may change it, and only for a Pending request, or an Approved request
whose dates lie wholly in the future"). Its ONE sanctioned caller is
`services/recalculation.recalculate_for_holiday_change`.

The two are DISJOINT — `transition_status` moves `status` and never `leave_days`; `set_leave_days`
moves `leave_days` and never `status` — and together they remain the whole mutation surface: there
is still no free-form `update_leave_request` and no `delete_leave_request`. The `audit_entry` table
stays STRICTLY append-only — INSERT only, forever (AD-8) — a distinction Story 2.7's revision of the
2.6 surface test pins down, and one a recalculation does not disturb: it writes ZERO audit rows,
because a balance re-derivation is not a state transition.

--- Why `count_pending_for_employee` is named `count_`, not `get_`/`list_` ---

`tests/test_scoped_getters.py` reflects over every `get_`/`list_`/`find_`/`fetch_` function taking
a `session`, requiring the AD-10 `actor` parameter. `count_pending_for_employee` is named `count_`,
returns an `int`, and takes the target `employee_id` the deactivation guard already holds — so it is
correctly NOT a scoped-getter candidate (mirroring `count_active_direct_reports`). `get_leave_request`
and `list_leave_requests`, by contrast, ARE scoped getters: a Leave Request belongs to an Employee,
so each takes the `actor` and applies `employee_scope_predicate` in SQL (the `leave_balance` reads'
precedent). `transition_status` is a write governed by the command's transaction, not a getter.
"""

import datetime
import uuid

from sqlalchemy import Row, and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.repositories.models import Employee, LeaveRequest, LeaveType
from app.repositories.scoping import Scope, employee_scope_predicate


def insert_leave_request(
    session: Session,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start_date: datetime.date,
    end_date: datetime.date,
    leave_days: int,
    status: str,
) -> LeaveRequest:
    """Insert a Leave Request row and return it, with its server-default id assigned (AC3, AC5).

    `flush` assigns the `uuidv7()` `id` so the submission command can write the matching
    `audit_entry` (`subject_id = <this id>`) in the SAME transaction (AD-8) and the route can
    project it. It does NOT commit — the service owns the one transaction (AD-3). `status` is a
    `vocabulary.STATUS_*` constant the caller chose (`PENDING` for a managed applicant, `APPROVED`
    for the managerless auto-approval); `leave_days` is the frozen `count_leave_days` figure
    (AD-18).

    A write, governed by the command's transaction rather than the scope contract, so it is not a
    scoped-getter candidate — mirroring `create_holiday`/`create_leave_type`.
    """
    request = LeaveRequest(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        start_date=start_date,
        end_date=end_date,
        leave_days=leave_days,
        status=status,
    )
    session.add(request)
    session.flush()
    return request


def count_pending_for_employee(session: Session, employee_id: uuid.UUID) -> int:
    """Count the Employee's `PENDING` Leave Requests — the deactivation guard's input (AC7).

    The executable form of Story 1.6's withheld `EMPLOYEE_HAS_PENDING_REQUESTS` guard: an Employee
    holding a Pending request cannot be deactivated (AD-22), because there would be no possible
    approver for a request already reserving days. Only `PENDING` counts — an `APPROVED`/`REJECTED`
    /`CANCELLED` request is settled and does not block deactivation.

    Named `count_`, returning an `int`, so it is correctly not a scoped-getter candidate (mirrors
    `count_active_direct_reports`): the caller is the deactivation service, which already holds the
    authorized target `employee_id` and needs no per-row scoping.
    """
    return (
        session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == vocabulary.STATUS_PENDING,
            )
        )
        or 0
    )


# The projected columns every scoped read returns — the request's own fields plus the applicant's
# name and the Leave Type's code/name (Open Decision #2). One join to `employee` serves BOTH the
# scope predicate AND the applicant name; one join to `leave_type` carries the human-readable
# labels, so the Manager queue and the by-id read need no second round-trip. Plain columns (not the
# ORM entity) travel out, so nothing is a detached instance after the read session closes.
_READ_COLUMNS = (
    LeaveRequest.id,
    LeaveRequest.employee_id,
    Employee.full_name,
    LeaveRequest.leave_type_id,
    LeaveType.code,
    LeaveType.name,
    LeaveRequest.start_date,
    LeaveRequest.end_date,
    LeaveRequest.leave_days,
    LeaveRequest.status,
)


def get_leave_request(
    session: Session,
    actor: Employee,
    request_id: uuid.UUID,
    scope: Scope,
) -> Row | None:  # type: ignore[type-arg]
    """Return one Leave Request by id, SCOPED to `actor`, or `None` (AC5, AC7).

    The exact shape of `employee.get_employee` / `leave_balance.get_balance`: join
    `leave_request → employee` and apply `employee_scope_predicate(scope, actor)` in the `WHERE`
    alongside `LeaveRequest.id == request_id`. `None` for a nonexistent id OR an out-of-scope one
    (a non-report Manager, a non-owner Employee) — the service turns both into a byte-identical
    `404` (AD-10). A `get_` getter taking a `session`, so `test_scoped_getters.py` requires the
    `actor`, which it takes.

    A plain non-locking `SELECT` — NOT `with_for_update()`. The AD-4 guarded `UPDATE`
    (`transition_status`) locks the request row itself, and the transition performs that UPDATE
    BEFORE any balance mutation (the lock-order note in the 2.7 Dev Notes); locking here would add
    a redundant lock a lost race would then have to queue behind twice. This read only authorizes.
    Returns the `_READ_COLUMNS` projection — the request's own fields plus the applicant name and
    Leave Type code/name — so the transition commands read `employee_id`/`leave_type_id`/
    `leave_days`/`start_date` off it and the by-id read projects the full view.
    """
    return session.execute(
        select(*_READ_COLUMNS)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(
            LeaveRequest.id == request_id,
            employee_scope_predicate(scope, actor),
        )
    ).first()


def list_leave_requests(
    session: Session,
    actor: Employee,
    *,
    scope: Scope,
    status: str | None,
    statuses: tuple[str, ...] | None = None,
    leave_type_id: uuid.UUID | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of Leave Requests AND the full count, SCOPED to `actor` (AC4).

    Joins `leave_request → employee` and applies `employee_scope_predicate(scope, actor)` in the
    `WHERE`, so an out-of-scope request is never retrieved — the scope is a SQL predicate, never a
    Python-side filter (AD-10, NFR-04). `scope` is resolved by the caller from the actor's role
    (`SELF`/`REPORTS`/`ALL`). Each optional filter is applied ONLY when not `None` and is ANDed
    BESIDE the scope predicate, never in place of it — a filter narrows, it never widens (FR-12,
    AC4). `status` is Story 2.7's; `leave_type_id`/`date_from`/`date_to` are Story 3.1's;
    `statuses` is Story 3.3's — the app's first status-SET predicate (`status IN (...)`, the
    calendar's fixed `PENDING+APPROVED`). `status` and `statuses` compose by AND like every
    other filter here (callers pass one or the other). `status`/`statuses` are LOCAL columns,
    like every predicate below. The date range selects by OVERLAP — a request is included iff its range intersects `[date_from,
    date_to]` (`end_date >= date_from AND start_date <= date_to`, each side optional) — because a
    request straddling a Leave Year edge IS leave taken in that window, and containment semantics
    would silently drop it (Story 3.1 Open Decision #1; Story 4.2's CSV export inherits this).
    Every filter predicate is on a LOCAL `leave_request` column — never a joined column — so the
    page query and the count query (which joins only `Employee`) stay in agreement and `total`
    never lies. The page and total travel together (the `list_employees` shape) so the service
    assembles the whole `Page` envelope from one repository round-trip.

    Ordered by `LeaveRequest.id.desc()`: the primary key is UUIDv7, which is time-ordered by
    construction, so descending id is newest-first — the order a Manager's queue and an Employee's
    history both want, with no `created_at` column to sort on (ERD §4.5). `total` recomputes the
    same conditions (the LeaveType join is unneeded for a count, so it is omitted).
    Returns `(_READ_COLUMNS` rows, total)`, a `get_`/`list_` getter taking the `actor`.

    `limit`/`offset` are OPTIONAL since Story 4.2 (Open Decision #1): the CSV export reads ALL
    matching rows — `MAX_PAGE_SIZE` is an API-layer clamp on list endpoints, and routing the
    export through it would silently truncate at 100 rows (Landmine 1). Passing `None` applies no
    `LIMIT`/`OFFSET`; the list endpoints keep passing both from the clamped `PageParams`. One
    function, one WHERE clause — filter/scope parity between screen and export by construction.
    """
    if status is not None and statuses is not None:
        # Loud, not silent (code review 2026-07-15): ANDing the two filters together yields a
        # contradiction-by-AND — an empty result that looks like "no matching requests" instead of
        # the programming error it is. Callers pass one or the other; this enforces it.
        raise ValueError("pass `status` or `statuses`, not both")
    predicate = employee_scope_predicate(scope, actor)
    conditions = [predicate]
    if status is not None:
        conditions.append(LeaveRequest.status == status)
    if statuses is not None:
        conditions.append(LeaveRequest.status.in_(statuses))
    if leave_type_id is not None:
        conditions.append(LeaveRequest.leave_type_id == leave_type_id)
    if date_from is not None:
        conditions.append(LeaveRequest.end_date >= date_from)
    if date_to is not None:
        conditions.append(LeaveRequest.start_date <= date_to)

    query = (
        select(*_READ_COLUMNS)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(*conditions)
        .order_by(LeaveRequest.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)
    rows = list(session.execute(query).all())
    total = (
        session.scalar(
            select(func.count())
            .select_from(LeaveRequest)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*conditions)
        )
        or 0
    )
    return rows, total


def list_requests_covering(
    session: Session, *, on_date: datetime.date, today: datetime.date
) -> list[LeaveRequest]:
    """Every Leave Request still HOLDING DAYS whose range contains `on_date` (AC2, AC3, Story 2.11).

    The holiday-change recalculation's affected-request sweep (AD-19). `start_date <= :on_date AND
    end_date >= :on_date` is exactly what `ix_leave_request_start_end` (migration `0006`) indexes,
    so no second index is created for it.

    WHICH REQUESTS HOLD DAYS, and why the others are never touched:

      * `PENDING` — holds Reserved days. Recalculated (AC2).
      * `APPROVED` AND `start_date > today` — holds Consumed days, and its dates lie WHOLLY IN THE
        FUTURE. Recalculated (AC3).
      * `APPROVED` and already started or past — NEVER recalculated. AD-18 grants recalculation only
        to a request "whose dates lie wholly in the future" and forbids it for one "whose dates have
        already passed"; an IN-PROGRESS request (`start_date <= today <= end_date`) is neither, and
        the literal reading of the only grant AD-18 makes is `start_date > today` (Open Decision #4).
        Note this is deliberately NOT Story 2.8's `is_wholly_past` predicate (`end_date < today`) —
        the two rules answer genuinely different questions, and reusing that one here would silently
        recalculate leave somebody is currently taking.
      * `REJECTED` / `CANCELLED` — settled, holding no days at all. Nothing to recalculate.

    `today` is passed IN, never read from a clock here: the clock lives in `services/`, never in
    `repositories/` or `domain/` (AD-1). That is also what lets the tests fix "today" without
    mocking one.

    WHY THIS GETTER IS EXEMPT FROM THE SCOPED-GETTER CONTRACT (`tests/test_scoped_getters.py`):
    it is a SYSTEM-WIDE RECALCULATION SWEEP, not an actor-facing read. There is no actor whose scope
    could narrow it — narrowing it would silently SKIP the very Employees whose balances must be
    corrected, which is the bug AD-19 exists to prevent. The gate is the ADMIN ROLE on the holiday
    endpoint, applied before the sweep ever runs. It is registered in that test's EXEMPT frozenset
    with this rationale, rather than dodged by renaming it to a non-`list_` verb — Story 2.9's review
    settled that a surface claim gets revised with a rationale, never routed around.

    Returns whole ORM rows (not the `_READ_COLUMNS` projection): the recalculation must READ each
    row's dates and `leave_days` and then WRITE a new `leave_days` through `set_leave_days`. Ordered
    by `(employee_id, leave_type_id, id)` so the service's pair grouping — and therefore its balance
    LOCK ORDER — is deterministic (AD-3): a holiday edit locks every affected balance row, and a
    nondeterministic order is how two concurrent edits deadlock.
    """
    return list(
        session.scalars(
            select(LeaveRequest)
            .where(
                LeaveRequest.start_date <= on_date,
                LeaveRequest.end_date >= on_date,
                or_(
                    LeaveRequest.status == vocabulary.STATUS_PENDING,
                    and_(
                        LeaveRequest.status == vocabulary.STATUS_APPROVED,
                        LeaveRequest.start_date > today,
                    ),
                ),
            )
            .order_by(
                LeaveRequest.employee_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.id,
            )
        ).all()
    )


def set_leave_days(
    session: Session, *, request_id: uuid.UUID, leave_days: int
) -> None:
    """Re-derive a request's frozen `leave_days` — the SECOND sanctioned mutation (AD-18, AD-19).

    AD-18 freezes `leave_days` at submission and names EXACTLY ONE exception, which this is:

        "Only AD-19's recalculation may change it, and only for a Pending request, or an Approved
        request whose dates lie wholly in the future."

    So this has ONE sanctioned caller — `services/recalculation.recalculate_for_holiday_change` —
    and the eligibility rule is enforced by `list_requests_covering`'s `WHERE`, which is the only
    thing that ever feeds it a `request_id`. A read path NEVER recomputes `leave_days` (AD-18); this
    is a write, in the recalculation's own transaction.

    ⚠️ `leave_days` and the balance's `reserved`/`consumed` MUST move in the SAME transaction. This
    is `deferred-work.md:56`, written down from the Story 2.7 review and describing this story by
    name: lower a Pending request's `reserved` without rewriting its `leave_days` to match, and the
    next `approve` passes the `WHERE status = PENDING` guard, then `consume_reserved(days)` finds
    `days > reserved` and raises a bare `ValueError` — a raw 500. The caller writes both, always.

    ⚠️ `CHECK (leave_days > 0)` is a BACKSTOP, not this function's gate (AD-5). Adding a holiday can
    price a one-working-day request down to ZERO working days, and firing that CHECK here would be a
    raw 500 AND an AC5 violation (the failure discovered by a constraint, not by the forward check).
    The caller REFUSES the pair before calling this — see `services/recalculation.py`. The assertion
    below is a loud programming-error guard for a caller that skipped that check; it is not the
    story's refusal path, and it is unreachable from the one sanctioned caller.

    `flush()`, never `commit()`: the holiday command owns the one transaction (AD-3).
    """
    if leave_days <= 0:
        raise ValueError(
            f"set_leave_days({leave_days}) is not positive — the CHECK (leave_days > 0) backstop "
            "would fire as a raw 500. A request recalculated to zero working days must be REFUSED "
            "by the forward check and flagged (AD-19), never written (AC5)."
        )

    session.execute(
        update(LeaveRequest)
        .where(LeaveRequest.id == request_id)
        .values(leave_days=leave_days)
        .execution_options(synchronize_session=False)
    )
    session.flush()


def transition_status(
    session: Session,
    *,
    request_id: uuid.UUID,
    from_status: str,
    to_status: str,
) -> int:
    """The AD-4 guarded conditional transition — `UPDATE … WHERE id = :id AND status = :from`.

    The ONE sanctioned mutation of a `leave_request` row's STATUS (there is no free-form
    update/delete). Since Story 2.11 it is no longer the only mutation this module offers: AD-18's
    single named exception — AD-19's recalculation of `leave_days`, for a Pending request or an
    Approved one whose dates lie wholly in the future — is `set_leave_days` above, whose one
    sanctioned caller is `services/recalculation.recalculate_for_holiday_change`. The two are
    disjoint: this one moves `status` and never `leave_days`; that one moves `leave_days` and never
    `status`. There is still no free-form update, and no delete, of a `leave_request` row.

    It matches the row only while it is still in `from_status`, so a lost race — a concurrent
    transition that already moved the row — matches ZERO rows. Returns `result.rowcount`: `1` on a
    clean transition, `0` when the guard failed. The service raises `409 TRANSITION_NOT_ALLOWED` on
    a `0` and lets the whole transaction roll back (nothing else has been written — the guarded
    UPDATE runs BEFORE the balance mutation, the 2.7 lock-order note). `:from`/`:to` are
    `vocabulary.STATUS_*` constants the command passes (AD-21), never bare literals.

    `synchronize_session=False`: the command does not reuse a stale ORM object's `status` after the
    UPDATE — it holds the row locked by the UPDATE itself and proceeds to the balance mutation — so
    no identity-map synchronization is needed. A write governed by the command's transaction, not a
    scoped getter; `flush` is implicit in `execute`, and the service owns the `commit`.
    """
    result = session.execute(
        update(LeaveRequest)
        .where(
            LeaveRequest.id == request_id,
            LeaveRequest.status == from_status,
        )
        .values(status=to_status)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount
