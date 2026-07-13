"""The role→scope resolution is pure — the one DB-free surface Story 2.7 adds (AC4).

Implements the test side of: AC4/AC5 (an Employee is scoped `SELF`, a Manager `REPORTS`, an Admin
`ALL`, before any SQL predicate is composed). The transition commands and the scoped reads are thin
orchestration whose real correctness lives in the integration suite (`test_leave_request_decide.py`),
but `_scope_for_role` is a pure function of the role string alone, so it is unit-tested here with a
bare role value — no database, no fake actor object even. AD-10: this resolves WHICH scope; the scope
becomes a SQL predicate downstream, never a post-filter.
"""

from app.domain import vocabulary
from app.repositories.scoping import Scope
from app.services.leave_requests import _scope_for_role


def test_admin_resolves_to_all() -> None:
    """An Admin reads every request (`ALL`) — the widest scope, api-contracts §4.5."""
    assert _scope_for_role(vocabulary.ROLE_ADMIN) is Scope.ALL


def test_manager_resolves_to_reports() -> None:
    """A Manager reads their Direct Reports' requests (`REPORTS`) — not their own (AC4)."""
    assert _scope_for_role(vocabulary.ROLE_MANAGER) is Scope.REPORTS


def test_employee_resolves_to_self() -> None:
    """A plain Employee reads only their own requests (`SELF`)."""
    assert _scope_for_role(vocabulary.ROLE_EMPLOYEE) is Scope.SELF


def test_unknown_role_defaults_to_self() -> None:
    """Any role that is neither Admin nor Manager gets the narrowest scope (`SELF`).

    The default is the least-privileged scope on purpose: an unrecognized role must never widen a
    read. `role` is a DB-CHECK-constrained column (one of three values), so this branch is a
    defence-in-depth floor, not a reachable path — and it fails safe.
    """
    assert _scope_for_role("SOMETHING_ELSE") is Scope.SELF
