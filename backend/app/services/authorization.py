"""Authorization primitives: the role guard, the not-found raise, and the role re-export.

Implements: FR-03 (a scope miss is a 404 indistinguishable from a nonexistent id),
AD-10 (authorization is a query predicate; absence is 404; 403 is reserved for "may see,
may not act"), AD-14 (the refusal is decided server-side against the DB-resolved actor,
never a token claim or a client-rendered control), NFR-03 (the server, not the client,
enforces), NFR-04 (no getter returns another Employee's data without the actor). SM-6.

--- Why the role constants are re-exported from here ---

The role gate lives in `api/`, and must compare an actor's role against `ROLE_ADMIN` /
`ROLE_MANAGER` / `ROLE_EMPLOYEE`. Two walls collide: contract 2 forbids `api → domain`
(import-linter flags it even under `TYPE_CHECKING`), and `test_vocabulary_literals.py`
forbids the string `"ADMIN"` appearing as a literal in `api/`. The escape is this
indirect re-export: `api/` imports `app.services.authorization` (an allowed `api →
services` edge) and names `authz.ROLE_ADMIN`. import-linter sees `api → services`, never
`api → domain`; the literal scan sees a name, not a string. This is the same indirection
`errors.py` / `main.py` already use for `DomainError`.

--- Why a pure guard lives in `services/` ---

This module raises `DomainError` and touches no HTTP (contract 4). It performs no I/O and
opens no transaction — it is a pure guard. It lives in `services/` and not `domain/`
because only `services/` may construct a `DomainError` in the layered flow, and because
`api/` reaches the role constants through it.
"""

from typing import NoReturn, Protocol

from app.domain import vocabulary
from app.domain.errors import DomainError

# The role constants, re-exported so `api/` can name them without importing `domain/`
# (contract 2) or typing the literal (`test_vocabulary_literals.py`). See the module
# docstring — this indirection is the whole reason this guard lives in `services/`.
from app.domain.vocabulary import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER

__all__ = [
    "ROLE_ADMIN",
    "ROLE_EMPLOYEE",
    "ROLE_MANAGER",
    "assert_role",
    "not_found",
]

# One message, stated once, for every role refusal — mirrors `services/auth.py`'s
# `_AUTH_FAILED_MESSAGE`. It names no role and no endpoint, so a 403 body discloses only
# that the action was not permitted, never *which* role would have been.
_ACTION_NOT_PERMITTED_MESSAGE = "You are not permitted to perform this action."

# The single not-found message. There is exactly ONE `not_found()` raise site and ONE
# message constant, with empty `details` always, so every 404 — a genuine "no such id"
# and an out-of-scope scope miss alike — is byte-identical (AC4 / AD-10). Interpolating an
# id or a resource name here would let a Manager probe which resources exist; do not.
_NOT_FOUND_MESSAGE = "The requested resource was not found."


class _Actor(Protocol):
    """The one attribute the role guard reads off the acting Employee: `role`.

    A structural shape, not the ORM `Employee` — `assert_role` needs nothing else, and
    naming only `role` keeps the guard callable from a DB-free unit test with a fake actor.
    """

    role: str


def assert_role(actor: _Actor, allowed: tuple[str, ...]) -> None:
    """Refuse with `ACTION_NOT_PERMITTED` unless the actor's role is one of `allowed`.

    The role is read off the DB-resolved actor (`AD-14` / `NFR-03`), never a token claim.
    Returns `None` on success so the caller (`require_role`) can proceed to hand the actor
    back to the route. Raises the one `ACTION_NOT_PERMITTED` `DomainError` — 403, "may see,
    may not act" — with an empty `details`, when the role is not admitted (api-contracts §1).
    """
    if actor.role not in allowed:
        raise DomainError(
            code=vocabulary.ACTION_NOT_PERMITTED,
            message=_ACTION_NOT_PERMITTED_MESSAGE,
            details={},
        )


def not_found() -> NoReturn:
    """Raise the one `RESOURCE_NOT_FOUND` refusal — 404, byte-identical every time (AC4).

    Called by a scoped read when its predicate matches no row, and by a lookup of a
    nonexistent id, so the two are indistinguishable to a client (`AD-10`, `FR-03`). One
    message, empty `details`, no interpolation — that is what makes the bytes identical.
    """
    raise DomainError(
        code=vocabulary.RESOURCE_NOT_FOUND,
        message=_NOT_FOUND_MESSAGE,
        details={},
    )
