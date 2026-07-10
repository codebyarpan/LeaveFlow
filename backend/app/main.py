"""The composition root: builds the FastAPI application.

Implements: AD-1, NFR-17 (one error envelope), the spine's *Observability* row.

`main.py` sits outside the four layers on purpose. It is the only module allowed
to know about all of them at once, because wiring is not a layer — it is what
assembles the layers. The import-linter contracts in `pyproject.toml` constrain
`app.api`, `app.services`, `app.repositories` and `app.domain`; `app.main` names
none of them, so it may import `domain.errors` in order to bind that exception
class to its handler.

That is not a loophole. AC2 forbids `api/` from importing `domain/` so that a
*route* can never reach a domain rule directly, sidestepping `services/`. Binding
an exception class to a handler at startup is not a route reaching into the domain.
"""

from fastapi import FastAPI

from app.api.v1.errors import domain_error_handler
from app.api.v1.router import api_v1_router
from app.core.logging import configure_logging
from app.domain.errors import DomainError

configure_logging()

app = FastAPI(
    title="LeaveFlow",
    version="0.1.0",
    # api-contracts serves every path under this prefix. The Vite dev proxy
    # forwards `/api/v1` without rewriting it, so development and production
    # paths are identical.
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

app.include_router(api_v1_router, prefix="/api/v1")

# AC3 — exactly one handler for the whole typed-exception hierarchy. Registered
# against the base class, so every DomainError subclass a later story adds is
# mapped without touching this file. A second handler is a defect.
app.add_exception_handler(DomainError, domain_error_handler)
