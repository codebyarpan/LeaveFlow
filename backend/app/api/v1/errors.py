"""The error envelope, and the one place a domain refusal becomes an HTTP status.

Implements: AC3, NFR-17 (every non-2xx response carries `{code, message, details}`),
AD-1, AD-21.

--- Why nothing here imports `app.domain.errors` ---

AC2 requires that `api/` import neither `repositories/` nor `domain/`, and that a
violation fail the build. Contract 2 in `pyproject.toml` enforces it. So this module
cannot name `DomainError`, even though it exists to serve it.

Instead the handler is *structurally* typed: `DomainErrorLike` describes the shape a
domain exception presents — `code`, `message`, `details` — without importing the
class. `main.py`, which sits outside the layers, performs the binding:

    app.add_exception_handler(DomainError, domain_error_handler)

The layer boundary is preserved and the handler stays type-checked. Do not "simplify"
this by importing `DomainError` here; `pytest` will fail, and it will be right to.
"""

from typing import Any, Protocol, runtime_checkable

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


@runtime_checkable
class DomainErrorLike(Protocol):
    """The shape `api/` needs from a domain exception, named without importing it."""

    code: str
    message: str
    details: dict[str, Any]


class ErrorEnvelope(BaseModel):
    """The body of every non-2xx response (api-contracts §2, NFR-17)."""

    code: str = Field(description="Machine-readable. Declared once in domain/ (AD-21).")
    message: str = Field(description="Human-readable.")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="The numbers a refusal must state.",
    )


# AC3 — the single `code -> status` map. One dict, consulted once, by one handler.
#
# Empty in Story 1.1, and deliberately so: this story implements no FR and creates
# no enumerated value, so it has no code to map. Story 1.2 adds `AUTH_FAILED` (401)
# and `TOKEN_INVALID` (401) alongside their vocabulary entries; api-contracts §2
# fixes the status for all twenty codes.
#
# Keys must come from `domain/vocabulary.py` (AD-21), never from a literal typed
# here — and since contract 2 forbids this module from importing `domain/`, the map
# is POPULATED FROM `main.py`, the same place the handler is bound:
#
#     CODE_TO_STATUS.update({vocabulary.AUTH_FAILED: 401, ...})
#
# `main.py` sits outside every contract precisely so it can perform this wiring.
# Do not type a code literal here, and do not import the vocabulary here; either
# one fails the build, and it will be right to.
CODE_TO_STATUS: dict[str, int] = {}

# A code that reaches the handler unmapped is a programming error, not a client
# error, and 500 says so honestly. The alternative — defaulting to 400 — would let a
# forgotten map entry masquerade as a well-formed refusal of the client's request.
DEFAULT_ERROR_STATUS = 500


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map a domain exception to `{code, message, details}` and to a status code.

    Registered once, in `main.py`, against `DomainError` itself — so every subclass a
    later story introduces is handled here without a second handler being written.

    The `exc: Exception` signature is Starlette's, not a widening on our part. The
    narrowing back to `DomainErrorLike` is what the `isinstance` check below performs.
    """
    if not isinstance(exc, DomainErrorLike):
        # Starlette only routes registered exception types here, so this is
        # unreachable in practice. Re-raise rather than fabricate an envelope
        # around an exception whose shape we cannot read.
        raise exc

    envelope = ErrorEnvelope(code=exc.code, message=exc.message, details=exc.details)

    return JSONResponse(
        status_code=CODE_TO_STATUS.get(exc.code, DEFAULT_ERROR_STATUS),
        # mode="json", not the default: `details` carries whatever the refusal must
        # state, and a leave system states dates. Python-mode `model_dump()` leaves
        # `date`/`Decimal` intact, and Starlette's json.dumps raises TypeError on
        # them — turning a clean refusal into an unenveloped 500.
        content=envelope.model_dump(mode="json"),
    )
