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

from app.api.v1.errors import CODE_TO_STATUS, domain_error_handler
from app.api.v1.router import api_v1_router
from app.core.logging import configure_logging
from app.domain import vocabulary
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

# AC3/AC8 — the `code -> status` map is populated HERE, the composition root, because
# `api/v1/errors.py` may import neither the vocabulary (AD-21 forbids the literal) nor
# `domain/` (contract 2). `main.py` sits outside every contract precisely so it can
# perform this one wiring. Story 1.2 writes the map's first two entries; both codes are
# 401 per api-contracts §2. Later stories add their codes here beside their vocabulary.
CODE_TO_STATUS.update(
    {
        vocabulary.AUTH_FAILED: 401,
        vocabulary.TOKEN_INVALID: 401,
        # Story 1.4 — the authorization statuses. 403 is reserved for "may see, may not
        # act" (the role gate); 404 is the byte-identical not-found the scope convention
        # raises for both a nonexistent and an out-of-scope identifier (api-contracts §1).
        vocabulary.ACTION_NOT_PERMITTED: 403,
        vocabulary.RESOURCE_NOT_FOUND: 404,
        # Story 1.5 — a non-empty Department cannot be deleted. The service counts first
        # and raises this typed refusal; the FK RESTRICT is only the backstop (AD-5).
        vocabulary.DEPARTMENT_NOT_EMPTY: 409,
        # Story 1.6 — the three Employee-management refusals. Each is a service gate that
        # raises before the write, so the database constraint behind it stays a backstop
        # (AD-5): 409 for a duplicate email (G2), 400 for a manager assignment that would
        # close a reporting cycle (AD-23/G7), 409 for deactivating or demoting below
        # MANAGER an Employee who still has active direct reports (AD-22/G8).
        vocabulary.EMAIL_ALREADY_IN_USE: 409,
        vocabulary.REPORTING_CYCLE: 400,
        vocabulary.EMPLOYEE_HAS_DIRECT_REPORTS: 409,
        # Story 1.8 / G5 — PATCH /me refuses any field other than full_name with 400
        # (the actor owns the resource; the domain refuses the content, not the access).
        vocabulary.FORBIDDEN_FIELD: 400,
        # Story 1.8 code review — PATCH /me refuses an unusable full_name value (null,
        # non-string, empty/whitespace) with 400, keeping the refusal inside the envelope.
        vocabulary.INVALID_NAME: 400,
        # Story 2.1 — POST /leave-types refuses a duplicate `code` with 409. The service
        # pre-checks and re-raises the UNIQUE (code) IntegrityError as this typed refusal,
        # so the constraint stays a backstop (AD-5), mirroring EMAIL_ALREADY_IN_USE.
        vocabulary.LEAVE_TYPE_CODE_IN_USE: 409,
        # Story 2.2 — POST /holidays refuses a duplicate `holiday_date` with 409. The service
        # pre-checks and re-raises the UNIQUE (holiday_date) IntegrityError as this typed
        # refusal, so the constraint stays a backstop (AD-5), mirroring LEAVE_TYPE_CODE_IN_USE.
        vocabulary.HOLIDAY_DATE_IN_USE: 409,
    }
)
