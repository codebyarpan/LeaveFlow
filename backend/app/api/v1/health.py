"""The deployment probe.

Implements: api-contracts §4.10 (`GET /health`, anonymous), AC1, and the spine's
*Observability* row.

Anonymous by construction: no authorization dependency is declared. Story 1.4
introduces the role gate; this route must never acquire one, or a deployment
probe would need a credential to answer whether the deployment is alive.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Answer 200 while the process can serve requests.

    Liveness, not readiness: it deliberately does not touch the database. A probe
    that fails when PostgreSQL is briefly unreachable would have the orchestrator
    restart a healthy web process, which cannot help and can cascade.
    """
    return {"status": "ok"}
