"""The Department Leave Calendar read — a Manager's reports' PENDING+APPROVED overlap (Story 3.3).

Implements: FR-18 (a Manager sees their Direct Reports' Approved AND Pending leave across a
date range — the overlap visible at the moment of decision, UJ-2), AD-10 (the REPORTS scope is
a SQL predicate bound to the actor's id at call time; an out-of-scope row is never retrieved),
AD-18 (every row's `leave_days` is the STORED figure — this module reuses the one
`_READ_COLUMNS` mapper and recomputes nothing), BR-06/DR-15 (the calendar INFORMS and never
blocks: it is a read with no reach into the decide path, which gains no overlap awareness from
this story). SM-6.

--- The two decisions this module embodies ---

1. Scope is hardcoded `Scope.REPORTS` (Open Decision #2, the `services/team.py` precedent):
   api-contracts §4.9 grants `/calendar` to the Manager ALONE (the Admin is refused 403 by the
   route's gate, alongside the Employee — an Admin reads any request via `GET /leave-requests`,
   scope ALL). Route-gate + hardcoded scope is belt-and-braces: a future change to either
   cannot silently widen the read. `Scope` lives in `repositories/`, which import-linter
   contract 2 forbids `api/` from importing — so the decision lives here, not in the route.

2. The status set is FIXED server-side (Open Decision #4): FR-18 defines the calendar as
   "Approved and Pending" — leave that is, or may become, an absence. Cancelled and Rejected
   leave is deliberately NOT on it (contrast FR-20's history, which includes them); a client
   wanting other slices has `GET /leave-requests`. Fixing the set here also keeps every status
   name out of `api/` entirely.

Read-only, deliberately (the `services/team.py` shape): one read session, opened, queried,
closed, never committed. The REPORTS predicate carries no `is_active` filter (the 3.2 decision,
inherited as Open Decision #3): a deactivated report's approved absence is still a fact about
the team's dates. And `manager_id == actor.id` can never match the Manager's own row — FR-18
says Direct Reports; the Manager's own leave does not appear.
"""

import datetime

from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.repositories import leave_request as leave_request_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee
from app.repositories.scoping import Scope
from app.services.leave_requests import LeaveRequestView, row_to_view

# The calendar's fixed status set (Open Decision #4): the two states that mean "away or maybe
# away". The client cannot widen or narrow it — no status query param exists on the route.
CALENDAR_STATUSES: tuple[str, str] = (
    vocabulary.STATUS_PENDING,
    vocabulary.STATUS_APPROVED,
)


def list_calendar(
    *,
    date_from: datetime.date | None,
    date_to: datetime.date | None,
    limit: int,
    offset: int,
    actor: Employee,
) -> tuple[list[LeaveRequestView], int]:
    """Return one page of the actor's reports' PENDING+APPROVED overlap AND the total (FR-18).

    A thin pass-through to the one existing leave-request list read: `Scope.REPORTS` hardcoded
    (Open Decision #2), `statuses=CALENDAR_STATUSES` (Story 3.3's status-SET predicate), and
    the SETTLED 3.1 overlap window forwarded verbatim (`end_date >= date_from AND start_date <=
    date_to`, each side optional — an absent side applies no predicate, so a range straddling
    Dec 31 works by construction; an inverted range is an empty intersection, not an error).
    Rows map through the one `row_to_view` mapper, so `leave_days` is the stored figure (AD-18).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        rows, total = leave_request_repo.list_leave_requests(
            session,
            actor,
            scope=Scope.REPORTS,
            status=None,
            statuses=CALENDAR_STATUSES,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
        return [row_to_view(row) for row in rows], total
