"""The login lookup never short-circuits on a missing row (AC5, GAP-1, ERD §4.2).

Implements the test side of: AC5 — "the login path executes exactly one password hash
comparison, against a constant fallback hash, before returning `AUTH_FAILED`", and "a
test asserting the verification function was invoked passes identically on the
unknown-email path and the wrong-password path".

--- Why this is a domain test with NO database ---

This is a *structural* assertion, not a wall-clock timing one — a timing test would be
flaky rather than probative (the story says so). It proves the SHAPE of the code: that
`verify_password` is invoked exactly once whether or not a row was found. So it needs no
PostgreSQL. The repository getter is stubbed and the engine is replaced with `None`
(`Session(None)` is a valid bindless session — nothing here ever executes SQL), which is
also why it lives under `tests/domain/`, where no `db_connection` fixture is reachable.

If this test ever needed a real database to run, that would mean `authenticate` had
grown a query the fallback path skips — which is exactly the short-circuit AC5 forbids.
"""

import types

import pytest

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.services import auth


class _VerifySpy:
    """Counts calls to the password verifier and always reports a mismatch.

    Always `False`: the point is to drive both failure paths (unknown email, wrong
    password) to the same single raise, and count that the verifier ran once on each.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, password: str, hashed: str) -> bool:
        self.calls += 1
        return False


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> _VerifySpy:
    """Replace the real verifier with a counting spy, and unbind the engine.

    `get_engine` returns `None` so `Session(None)` is created bindless — the stubbed
    getter never touches it, so no connection is ever opened. Fully DB-free.
    """
    counter = _VerifySpy()
    monkeypatch.setattr(auth.security, "verify_password", counter)
    monkeypatch.setattr(auth, "get_engine", lambda: None)
    return counter


def test_unknown_email_runs_exactly_one_verification(spy: _VerifySpy, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: no row found → one verification against the fallback hash → `AUTH_FAILED`.

    The verifier must run once even though there is no row: skipping it is the
    short-circuit AC5 exists to forbid, and it would make the unknown-email path
    measurably faster than the wrong-password path.
    """
    monkeypatch.setattr(auth.employee_repo, "get_by_email", lambda session, email: None)

    with pytest.raises(DomainError) as raised:
        auth.authenticate("nobody@example.com", "irrelevant")

    assert raised.value.code == vocabulary.AUTH_FAILED
    assert spy.calls == 1


def test_wrong_password_runs_exactly_one_verification(spy: _VerifySpy, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: row found, wrong password → one verification against the stored hash → `AUTH_FAILED`.

    The same single call count as the unknown-email path. That the two paths invoke the
    verifier the same number of times is the structural property that makes them
    indistinguishable — the thing AC5 asserts.
    """
    stub_employee = types.SimpleNamespace(
        id="stub", role=vocabulary.ROLE_EMPLOYEE, password_hash="$2b$12$stub", is_active=True
    )
    monkeypatch.setattr(auth.employee_repo, "get_by_email", lambda session, email: stub_employee)

    with pytest.raises(DomainError) as raised:
        auth.authenticate("someone@example.com", "wrong-password")

    assert raised.value.code == vocabulary.AUTH_FAILED
    assert spy.calls == 1


def test_the_two_failure_paths_invoke_the_verifier_the_same_number_of_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5, stated directly: unknown-email and wrong-password call the verifier equally.

    Both paths are driven in one test so the equality is asserted, not merely implied by
    two separate counts that a reader has to compare by eye.
    """
    monkeypatch.setattr(auth, "get_engine", lambda: None)

    unknown_spy = _VerifySpy()
    monkeypatch.setattr(auth.security, "verify_password", unknown_spy)
    monkeypatch.setattr(auth.employee_repo, "get_by_email", lambda session, email: None)
    with pytest.raises(DomainError):
        auth.authenticate("nobody@example.com", "pw")

    wrong_spy = _VerifySpy()
    monkeypatch.setattr(auth.security, "verify_password", wrong_spy)
    stub_employee = types.SimpleNamespace(
        id="stub", role=vocabulary.ROLE_EMPLOYEE, password_hash="$2b$12$stub", is_active=True
    )
    monkeypatch.setattr(auth.employee_repo, "get_by_email", lambda session, email: stub_employee)
    with pytest.raises(DomainError):
        auth.authenticate("someone@example.com", "pw")

    assert unknown_spy.calls == wrong_spy.calls == 1
