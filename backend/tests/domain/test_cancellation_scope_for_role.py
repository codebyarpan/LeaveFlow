"""The Cancellation Request role→scope resolution is pure and TWO-WAY (Story 2.8, AC5).

Implements the test side of: AC5's scope grant (api-contracts §4.6 gives `GET /cancellation-requests`
scope `self, all` ONLY — an Admin sees every filing, everyone else only their own). This is the
TWO-WAY idiom, deliberately NOT `leave_requests._scope_for_role`'s three-way: a Manager is NOT
`REPORTS` here — they see their OWN filings as an applicant (`SELF`). `cancellation._scope_for_role`
is a pure function of the role string alone, so it is unit-tested here with a bare role value — no
database, no fake actor. AD-10: this resolves WHICH scope; the scope becomes a SQL predicate
downstream, never a post-filter.
"""

from app.domain import vocabulary
from app.repositories.scoping import Scope
from app.services.cancellation import _scope_for_role


def test_admin_resolves_to_all() -> None:
    """An Admin sees every Cancellation Request (`ALL`) — api-contracts §4.6."""
    assert _scope_for_role(vocabulary.ROLE_ADMIN) is Scope.ALL


def test_manager_resolves_to_self_not_reports() -> None:
    """A Manager is `SELF`, NOT `REPORTS`: they see only their own filings as an applicant (AC5).

    This is the whole point of the two-way resolver — a Manager decides Leave Requests but NOT
    Cancellation Requests (an Admin does), so their scope over Cancellation Requests is their own
    filings, never their reports'.
    """
    assert _scope_for_role(vocabulary.ROLE_MANAGER) is Scope.SELF


def test_employee_resolves_to_self() -> None:
    """A plain Employee sees only their own Cancellation Requests (`SELF`)."""
    assert _scope_for_role(vocabulary.ROLE_EMPLOYEE) is Scope.SELF


def test_unknown_role_defaults_to_self() -> None:
    """Any role that is not Admin gets the narrowest scope (`SELF`) — an unknown role never widens."""
    assert _scope_for_role("SOMETHING_ELSE") is Scope.SELF
