"""Typed domain exceptions.

Implements: AC3, AD-21 (`code` is the canonical vocabulary), NFR-17 (one envelope),
AD-1 (`domain/` is pure).

Stdlib only. No Pydantic, no HTTP, no ORM — that is what lets `services/` raise
these without importing a web framework, and what lets `domain/` stay a package
with no way to reach a database.

A `DomainError` carries no status code. It cannot: `domain/` must never learn what
an HTTP status is. The `code -> status` mapping lives in `api/v1/errors.py`, on the
far side of the layer boundary, and is applied once when the exception surfaces.
"""

from typing import Any


class DomainError(Exception):
    """A refusal the domain can state in its own terms.

    `code` is machine-readable and declared exactly once in `domain/vocabulary.py`
    (AD-21). `message` is human-readable. `details` carries the numbers a refusal
    must state — `INSUFFICIENT_BALANCE` names `days_requested` and `days_available`,
    for instance, because "not enough balance" is not an actionable answer.

    Subclass per code as the codes arrive. The single handler registered in
    `main.py` binds to this base class, so a subclass needs no new handler.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        # A mutable default would be shared across every instance ever raised.
        self.details: dict[str, Any] = {} if details is None else details

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"
