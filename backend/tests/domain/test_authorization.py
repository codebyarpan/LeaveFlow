"""`services/authorization` — the role guard raises/returns, and the 404 is byte-identical.

Implements the test side of: AC3 (403 `ACTION_NOT_PERMITTED` for "may see, may not act"),
AC4 (a scope miss and a nonexistent id are indistinguishable down to the bytes), AC5 (the
refusal is decided against the actor, never a client claim). DB-free: `assert_role` and
`not_found` are pure guards, driven with a structural fake actor and no database — the
same idiom `test_resolve_actor_rejections.py` uses to prove branching without I/O.

The end-to-end proof that a real token gets a real 403 at the boundary lives in
`tests/integration/test_role_gate.py`; here we prove the guard's own behaviour and the
byte-identity property at the handler seam.
"""

import asyncio

# Importing `app.main` runs its `CODE_TO_STATUS.update(...)` at import, wiring
# `ACTION_NOT_PERMITTED`→403 and `RESOURCE_NOT_FOUND`→404. Without it `CODE_TO_STATUS`
# is the empty `{}` from `errors.py` and the mapping/byte-identity tests below render 500
# — so this module must populate the map itself rather than relying on another test file
# importing `app.main` first (collection-order coupling). This import opens no DB
# connection, so the DB-free property of `tests/domain/` is preserved. Same reason
# `tests/integration/test_role_gate.py` imports `app.main`.
import app.main  # noqa: F401
from app.api.v1.errors import CODE_TO_STATUS, domain_error_handler
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.services import authorization as authz


class _FakeActor:
    """A structural stand-in for the acting Employee — only the `role` the guard reads."""

    def __init__(self, role: str) -> None:
        self.role = role


def test_assert_role_returns_for_an_allowed_role() -> None:
    """AC3: a caller whose role is in `allowed` passes — the guard returns `None`, no raise."""
    actor = _FakeActor(vocabulary.ROLE_ADMIN)

    assert authz.assert_role(actor, (vocabulary.ROLE_ADMIN,)) is None


def test_assert_role_admits_any_role_in_the_allowed_tuple() -> None:
    """A multi-role gate admits every role it names — MANAGER passes a MANAGER/ADMIN gate."""
    actor = _FakeActor(vocabulary.ROLE_MANAGER)

    assert (
        authz.assert_role(actor, (vocabulary.ROLE_MANAGER, vocabulary.ROLE_ADMIN)) is None
    )


def test_assert_role_raises_action_not_permitted_for_a_disallowed_role() -> None:
    """AC3: a role not in `allowed` is refused with `ACTION_NOT_PERMITTED` and empty details.

    The message names no role and no endpoint — a 403 body discloses only that the action
    was refused, never which role would have been admitted.
    """
    actor = _FakeActor(vocabulary.ROLE_EMPLOYEE)

    try:
        authz.assert_role(actor, (vocabulary.ROLE_ADMIN,))
    except DomainError as raised:
        assert raised.code == vocabulary.ACTION_NOT_PERMITTED
        assert raised.details == {}
        assert vocabulary.ROLE_ADMIN not in raised.message
        assert vocabulary.ROLE_EMPLOYEE not in raised.message
    else:  # pragma: no cover - the guard must raise
        raise AssertionError("a disallowed role must raise ACTION_NOT_PERMITTED")


def test_not_found_raises_resource_not_found_with_empty_details() -> None:
    """AC4: the single not-found raise carries `RESOURCE_NOT_FOUND` and an empty `details`."""
    try:
        authz.not_found()
    except DomainError as raised:
        assert raised.code == vocabulary.RESOURCE_NOT_FOUND
        assert raised.details == {}
    else:  # pragma: no cover - not_found never returns
        raise AssertionError("not_found() must raise")


def _render(exc: DomainError):
    """Drive a `DomainError` through the real handler and return the `JSONResponse`.

    The handler is `async`; there is no event loop in a sync test, so `asyncio.run` drives
    it. `request=None` is safe — `domain_error_handler` reads only the exception. This is
    the same handler `main.py` binds, so the bytes here are the bytes a client receives.
    """
    return asyncio.run(domain_error_handler(None, exc))  # type: ignore[arg-type]


def test_resource_not_found_maps_to_404() -> None:
    """AC4: `RESOURCE_NOT_FOUND` renders as a 404 through the wired `CODE_TO_STATUS` map."""
    assert CODE_TO_STATUS[vocabulary.RESOURCE_NOT_FOUND] == 404

    try:
        authz.not_found()
    except DomainError as raised:
        response = _render(raised)
    else:  # pragma: no cover - not_found never returns
        raise AssertionError("not_found() must raise")

    assert response.status_code == 404


def test_action_not_permitted_maps_to_403() -> None:
    """AC3: `ACTION_NOT_PERMITTED` renders as a 403 through the wired `CODE_TO_STATUS` map."""
    assert CODE_TO_STATUS[vocabulary.ACTION_NOT_PERMITTED] == 403

    actor = _FakeActor(vocabulary.ROLE_EMPLOYEE)
    try:
        authz.assert_role(actor, (vocabulary.ROLE_ADMIN,))
    except DomainError as raised:
        response = _render(raised)
    else:  # pragma: no cover - the guard must raise
        raise AssertionError("a disallowed role must raise ACTION_NOT_PERMITTED")

    assert response.status_code == 403


def test_a_nonexistent_id_and_a_scope_miss_are_byte_identical() -> None:
    """AC4 (the sharp one): both framings of a 404 are indistinguishable down to the bytes.

    There is one `not_found()` raise site, so a "no such id" and an out-of-scope "scope
    miss" both leave through it with the same code, message and empty details. Rendered
    through the same handler, the two `JSONResponse` bodies must be byte-identical and both
    404 — or a Manager could probe which resources exist (AD-10). Compares raw
    `response.body`, so key order or whitespace drift is caught.
    """

    # Framing one: the caller named an identifier that exists for nobody.
    def a_nonexistent_identifier() -> None:
        authz.not_found()

    # Framing two: the caller named an identifier that exists but is outside their scope,
    # so the scoped predicate matched no row.
    def an_out_of_scope_identifier() -> None:
        authz.not_found()

    try:
        a_nonexistent_identifier()
    except DomainError as raised:
        nonexistent = _render(raised)

    try:
        an_out_of_scope_identifier()
    except DomainError as raised:
        scope_miss = _render(raised)

    assert nonexistent.status_code == scope_miss.status_code == 404
    assert nonexistent.body == scope_miss.body
