"""The single `api/v1` router. Every v1 route is reachable only through here.

Implements: AD-1, and the base path `/api/v1` that api-contracts assumes throughout.

Routers are aggregated here rather than attached to the app directly in `main.py`,
so that the set of v1 routes is one readable list rather than a scatter of
`include_router` calls across the composition root.
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    balances,
    cancellation_requests,
    departments,
    employees,
    health,
    holidays,
    leave_requests,
    leave_types,
    me,
)

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(me.router)
api_v1_router.include_router(departments.router)
api_v1_router.include_router(employees.router)
api_v1_router.include_router(leave_types.router)
api_v1_router.include_router(holidays.router)
api_v1_router.include_router(balances.router)
api_v1_router.include_router(leave_requests.router)
api_v1_router.include_router(cancellation_requests.router)
