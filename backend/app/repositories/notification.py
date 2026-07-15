"""Notification persistence — the write the transitions ride, and the addressee's three reads.

Implements: AC2/AC3/AC4 (`insert_notification`, called INSIDE the submit and decide transactions —
never opening one of its own), AC5 (`list_notifications`, `count_unread` — both addressee-scoped in
the SQL), AC6 (`get_notification` + `mark_read`, the idempotent guarded UPDATE) of Story 3.4. FR-14,
AD-16, AD-10, NFR-04.

One repository module per table (the rule Story 2.9 fixed). These functions are NOT added to
`repositories/leave_request.py` or `repositories/audit_entry.py`: `test_leave_request_submit.py`
hard-pins both of those surfaces BY NAME, so an addition there fails the build. A new table getting
a new module is legitimate, not an evasion of that pin.

--- There is no delete method, and the grant agrees ---

`0012` grants the application role `SELECT, INSERT, UPDATE` on `notification` and NOT `DELETE`: no
requirement deletes a Notification, and a delivered notification is a fact that happened. But note
what this table is NOT — it is not append-only either, and it is the first such table since `0008`.
`read_at` is genuinely mutable, which is why `UPDATE` is granted where `audit_entry`, `rollover_run`,
`admin_review_flag` and `policy_change` all deliberately withhold it (AD-9's append-only list is
exactly `audit_entry` and `rollover_run`; `notification` is not on it).

--- Why the scope predicate is a direct column compare, not `employee_scope_predicate` ---

Open Decision #3, decided and recorded here so it does not read as an oversight. The shared helper
`scoping.employee_scope_predicate(scope, actor)` predicates over the **`Employee`** table
(`Employee.id == actor.id` for `SELF`). A Notification's owner column is its own
`recipient_employee_id`, so reusing that helper would mean JOINING `employee` purely to reuse a
helper — a join with no other purpose, on a read that is otherwise single-table.
`Notification.recipient_employee_id == actor.id` is the honest predicate. It is applied IN THE SQL,
never as a post-filter over retrieved rows (NFR-04, AD-10), which is the property that actually
matters; the helper is a convenience for tables scoped THROUGH an Employee row, and this one is not.

There is exactly ONE scope for a Notification — `self`, intrinsic to the addressee — and it is
decided in `services/notifications.py`, never here and never in `api/`. Consequently these getters
take no `scope` parameter: there is no second scope to pass.

--- These getters are NOT exemptible, and that is the tell ---

`notification` HAS an Employee-owner column, so AD-10 applies with full force and
`tests/test_scoped_getters.py`'s `EXEMPT` frozenset must NOT grow for this story. Every `get_`/`list_`
here takes a parameter literally named `actor` and applies the predicate in the SQL. (`count_unread`
is outside that test's `_READ_VERB_PREFIXES` — `get_`/`list_`/`find_`/`fetch_` — by its `count_`
prefix, the `count_pending_for_employee` precedent; it applies the scope predicate anyway, for
correctness rather than to satisfy a guard.)
"""

import datetime
import uuid

from sqlalchemy import Row, func, select, update
from sqlalchemy.orm import Session

from app.repositories.models import Employee, Notification

# Plain COLUMNS, never the ORM entity: a `Row` of columns is already detached, so nothing lazy-loads
# or expires once the read session closes (the `list_audit_entries` / `list_policy_changes` shape).
#
# The MINIMAL shape (Open Decision #5): no AC requires a Notification to CARRY the Leave Request's
# details — AC7 asks only that a count is visible and that opening one marks it read. Keeping it to
# this table's own columns also keeps the read a SINGLE-TABLE query with NO JOIN, which sidesteps
# 3.1's Landmine 3 outright: a projection or filter over a JOINED column makes the page query and the
# count query disagree, and then `total` lies. A richer shape is a widening no requirement grants; a
# later story that wants the request inline can add it deliberately.
_READ_COLUMNS = (
    Notification.id,
    Notification.kind,
    Notification.leave_request_id,
    Notification.read_at,
    Notification.created_at,
)


def insert_notification(
    session: Session,
    *,
    recipient_employee_id: uuid.UUID,
    leave_request_id: uuid.UUID,
    kind: str,
    created_at: datetime.datetime,
) -> None:
    """Append one Notification, in the CALLER'S transaction (AC2, AC3, AC4; AD-16).

    `flush()`, and deliberately NOT `commit()` — this is the whole of AD-16's third clause: "the
    service that performs a transition is the service that writes its Notification, INSIDE that
    transition's transaction, so one exists IF AND ONLY IF the transition committed." The two
    callers are `submit_leave_request` and `_decide` (both in `services/leave_requests.py`), each of
    which already owns exactly one transaction (AD-3) and commits it. A rolled-back submission —
    `INSUFFICIENT_BALANCE`, say — therefore leaves NO notification claiming it happened, and a 409'd
    approve leaves none either. Opening a transaction here, or committing here, would break that
    biconditional in both directions.

    `kind` is a `vocabulary.NOTIFICATION_*` constant the caller passes (AD-21), never a bare literal;
    the `CHECK (kind IN (...))` on the table is the AD-5 BACKSTOP, never the gate. `created_at` is a
    timezone-aware instant from the service's shell clock (AD-1) — a naive datetime against a
    `TIMESTAMPTZ` is a defect, not a nit. `read_at` is left unset (NULL), which IS the unread state.

    `recipient_employee_id` is NOT NULL, and the caller must have decided WHO before calling: on
    submit the recipient is the applicant's Manager (or, managerless, the applicant themselves — AC4);
    on decide it is `row.employee_id`, the APPLICANT, never the deciding Manager. This function
    deliberately does not guess.

    Returns `None`. There is no update and no delete method here; `mark_read` below is the ONLY other
    mutation, and it moves `read_at` alone.
    """
    session.add(
        Notification(
            recipient_employee_id=recipient_employee_id,
            leave_request_id=leave_request_id,
            kind=kind,
            created_at=created_at,
        )
    )
    session.flush()


def list_notifications(
    session: Session, actor: Employee, *, limit: int, offset: int
) -> tuple[list[Row], int]:  # type: ignore[type-arg]
    """Return one page of the ACTOR'S OWN Notifications, newest first, AND their full count (AC5).

    Scoped to the addressee IN THE SQL (`recipient_employee_id == actor.id`, the direct column
    compare the module docstring defends) — never a post-filter (NFR-04, AD-10). There is one scope,
    `self`, and no parameter offers another: a Notification addressed to someone else is not a row
    this Employee may see, whatever their role. A Manager and an Admin read this endpoint exactly as
    an Employee does — role `any`, scope `self` (api-contracts §4.8) — and a Manager is in fact the
    PRIMARY recipient, since `REQUEST_SUBMITTED` is addressed to them.

    ORDER BY `created_at DESC, id DESC` — AND THE `id` TIEBREAK IS LOAD-BEARING, not decoration.
    `created_at DESC` alone is not a TOTAL order: rows can share an instant (they are written from one
    `_now()` reading inside one transaction, and nothing stops two transactions committing within the
    same clock tick), and PostgreSQL may then return tied rows in either order between two queries — a
    paginated read would show one row twice and skip another. `id` is a UUIDv7, time-ordered by
    construction, so it breaks the tie deterministically and in the right direction. Stories 2.9 and
    2.11 each found this the hard way; this is the same trap a third time, and it is cheap to not fall
    into.

    `total` counts the SAME predicate, over the same single table — no join exists to make the page
    query and the count query disagree (Open Decision #5). Returns `(rows, total)` so the service
    assembles the `Page` envelope from ONE round-trip.
    """
    scoped = Notification.recipient_employee_id == actor.id

    rows = list(
        session.execute(
            select(*_READ_COLUMNS)
            .where(scoped)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = (
        session.scalar(
            select(func.count()).select_from(Notification).where(scoped)
        )
        or 0
    )
    return rows, total


def count_unread(session: Session, actor: Employee) -> int:
    """Return the actor's unread count — `COUNT(*) WHERE read_at IS NULL`, DERIVED (AC5, AD-16).

    NEVER STORED. AD-16 is explicit: "the unread count is `COUNT(*) WHERE read_at IS NULL` and is
    never stored." There is no counter column on `employee`, no cached total, and no denormalized
    tally to drift out of step with the rows it claims to count — the count is a query, every time,
    and it is exactly the set the PARTIAL index `ix_notification_recipient_unread` covers
    (`recipient_employee_id WHERE read_at IS NULL`). The index and this query were designed as one
    thing: that is why the index is partial rather than a plain index on the recipient.

    Scoped to the addressee in the SQL, like every read here. The `count_` prefix puts this function
    outside `test_scoped_getters.py`'s `_READ_VERB_PREFIXES` (`get_`/`list_`/`find_`/`fetch_`) — the
    `count_pending_for_employee` precedent — so the guard does not require the `actor` parameter of
    it. It takes one anyway and predicates on it, because the scope is a correctness requirement, not
    a test-passing ritual: an unread count that counted someone else's notifications would be a
    cross-Employee disclosure in a single integer.
    """
    return (
        session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_employee_id == actor.id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def get_notification(
    session: Session, actor: Employee, notification_id: uuid.UUID
) -> Row | None:  # type: ignore[type-arg]
    """Locate ONE Notification by id, SCOPED to the addressee — or `None` (AC6, AD-10).

    The single-row scoped getter `mark_notification_read` needs to tell "not yours / nonexistent"
    (⇒ 404) apart from "already read" (⇒ 200, idempotent). That distinction is the whole reason this
    function exists: the guarded UPDATE below returns a rowcount of 0 for BOTH cases, and they must
    NOT get the same answer (Landmine 3).

    A miss — a nonexistent id OR a Notification addressed to somebody else — returns `None`, and the
    service raises the one byte-identical `404 RESOURCE_NOT_FOUND` for either (AD-10: a scope miss and
    a nonexistent id are indistinguishable down to the bytes, so no one can probe what exists).

    🚨 NOT a 403. This inverts the app's habit and it is deliberate: api-contracts §4.8 grants all
    three notification endpoints to Role `any`, so the role gate ADMITS EVERY authenticated caller —
    and by the G3 settlement (`api-contracts.md:37-44`), once the role gate admits, the scope
    predicate runs and a miss is a 404. 403 `ACTION_NOT_PERMITTED` is reserved for "denied by role
    grant, decided BEFORE any row is read", which cannot happen on an endpoint no role is denied.
    Every other read in this app has a role gate and 3.2/3.3 both shipped Manager-only inversions, so
    the muscle memory here points exactly the wrong way.

    Being a `get_`, this IS caught by `test_scoped_getters.py`'s `_READ_VERB_PREFIXES` and takes the
    parameter literally named `actor` — and correctly so: `notification` has an owner column, so it is
    NOT exemptible and the `EXEMPT` frozenset must not grow for it.
    """
    return session.execute(
        select(*_READ_COLUMNS).where(
            Notification.id == notification_id,
            Notification.recipient_employee_id == actor.id,
        )
    ).first()


def mark_read(
    session: Session,
    *,
    notification_id: uuid.UUID,
    recipient_employee_id: uuid.UUID,
    read_at: datetime.datetime,
) -> int:
    """The guarded conditional UPDATE that marks a Notification read — returns `rowcount` (AC6).

    `UPDATE notification SET read_at = :now WHERE id = :id AND recipient_employee_id = :actor AND
    read_at IS NULL`. The `transition_status` idiom (`repositories/leave_request.py`): the predicate
    carries the guard, so the write is decided by the database in one statement rather than by a
    read-then-write the next transaction could interleave with.

    The recipient predicate is repeated HERE and not merely trusted from the caller's prior
    `get_notification`: between that SELECT and this UPDATE the row is not locked, and defence in
    depth costs one clause. It also makes this function safe on its own terms — it cannot mark
    somebody else's Notification read, whatever a caller passes.

    🚨 A `rowcount` of 0 is NOT AD-4's `409 TRANSITION_NOT_ALLOWED`, and this is the one place in the
    codebase where a guarded UPDATE's zero rowcount does not mean a lost race. It has TWO causes here
    and they get DIFFERENT answers:

      - ALREADY READ (`read_at IS NOT NULL`) ⇒ **SUCCESS, 200.** That is precisely what "idempotent"
        means (AC6: "marked read and the count decrements ONCE"). A second `PATCH` is a no-op that
        succeeds; it is not a conflict, and the count does not move again.
      - NOT YOURS / NONEXISTENT ⇒ **404** — but the SERVICE has already ruled that out by locating the
        row under the actor's scope with `get_notification` BEFORE calling this. So by the time this
        function runs, a 0 can only mean "already read".

    That ordering is what disambiguates the two, and it is why `get_notification` exists. Every other
    guarded UPDATE in this codebase reads a zero rowcount as a 409; this one must not, and a reviewer
    who does not see this stated will read it as a bug. (Inherited caveat, awareness only: the clean
    behaviour of a guarded UPDATE under a lost race depends on READ COMMITTED — `deferred-work.md:57`.
    Not this story's to fix.)

    `synchronize_session=False`: no stale ORM object's `read_at` is reused after this UPDATE — the
    service returns nothing from the row — so no identity-map synchronization is needed. `flush` is
    implicit in `execute`; the SERVICE owns the `commit`.
    """
    result = session.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.recipient_employee_id == recipient_employee_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=read_at)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount
