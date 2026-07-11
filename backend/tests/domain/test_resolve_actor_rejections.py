"""`resolve_actor` refuses every malformed token with the one `TOKEN_INVALID` (AC2-5, AD-14).

Implements the test side of: AD-14 — the token path's three-plus rejection reasons all
leave through a single `DomainError(TOKEN_INVALID)`, disclosing nothing. These are
*structural* assertions about the translation and the short-circuit, so they need no
database: `decode_token` is stubbed to drive each branch, the engine is unbound
(`Session(None)`), and the repository getter is stubbed — the same DB-free idiom
`test_authenticate_no_shortcircuit.py` uses.

The end-to-end proof that a real signature, a real expiry and a real DB row behave this
way lives in `tests/integration/test_me.py`; here we prove the service's own branching.
"""

import uuid

import jwt
import pytest

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.services import auth


def test_a_jwt_error_becomes_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC3/AC4: any `jwt.PyJWTError` from decoding is translated to `TOKEN_INVALID`.

    Driven with `InvalidSignatureError` (a tampered token's failure) — the base
    `PyJWTError` is what `resolve_actor` catches, so the expired case (`ExpiredSignatureError`)
    funnels through the same branch. The DB is never reached: decoding fails first.
    """

    def raise_bad_signature(token: str) -> dict:
        raise jwt.InvalidSignatureError("signature verification failed")

    monkeypatch.setattr(auth.security, "decode_token", raise_bad_signature)

    with pytest.raises(DomainError) as raised:
        auth.resolve_actor("tampered.or.expired")

    assert raised.value.code == vocabulary.TOKEN_INVALID


def test_a_missing_subject_becomes_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2/AC5: a validly-decoded token with no `sub` is rejected without a DB load."""
    monkeypatch.setattr(auth.security, "decode_token", lambda token: {"role": vocabulary.ROLE_ADMIN})

    def unreachable(session, employee_id):  # type: ignore[no-untyped-def]
        raise AssertionError("a missing subject must be rejected before any DB load")

    monkeypatch.setattr(auth.employee_repo, "get_by_id_with_department", unreachable)

    with pytest.raises(DomainError) as raised:
        auth.resolve_actor("no.sub.here")

    assert raised.value.code == vocabulary.TOKEN_INVALID


def test_a_malformed_subject_becomes_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: a `sub` that is not a UUID is a rejected token, not a 500 — and loads nothing."""
    monkeypatch.setattr(
        auth.security, "decode_token", lambda token: {"sub": "not-a-uuid", "role": vocabulary.ROLE_ADMIN}
    )

    def unreachable(session, employee_id):  # type: ignore[no-untyped-def]
        raise AssertionError("a malformed subject must be rejected before any DB load")

    monkeypatch.setattr(auth.employee_repo, "get_by_id_with_department", unreachable)

    with pytest.raises(DomainError) as raised:
        auth.resolve_actor("bad.sub.token")

    assert raised.value.code == vocabulary.TOKEN_INVALID


def test_a_nonexistent_subject_becomes_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: a validly-signed token whose subject names no row is rejected.

    `get_engine` returns `None` so `Session(None)` is created bindless — nothing here
    opens a connection — and the getter returns `None` to model the absent row.
    """
    subject = str(uuid.uuid4())
    monkeypatch.setattr(
        auth.security, "decode_token", lambda token: {"sub": subject, "role": vocabulary.ROLE_ADMIN}
    )
    monkeypatch.setattr(auth, "get_engine", lambda: None)
    monkeypatch.setattr(
        auth.employee_repo, "get_by_id_with_department", lambda session, employee_id: None
    )

    with pytest.raises(DomainError) as raised:
        auth.resolve_actor("valid.but.orphaned")

    assert raised.value.code == vocabulary.TOKEN_INVALID
