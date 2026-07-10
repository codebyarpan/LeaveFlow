"""The login endpoint: `POST /api/v1/auth/login`.

Implements: FR-01, api-contracts §4.1 (`POST /auth/login`, anonymous), AC3, AC8.

--- What this module may import, and what it may not ---

The route imports `services/` and nothing lower. It names neither `repositories/` nor
`domain/` — contract 2 fails the build if it does. So it cannot construct a
`DomainError`, and does not need to: `services.auth.authenticate` raises the
`AUTH_FAILED` refusal, and `main.py`'s single handler renders it as the envelope with
status 401. The route's whole job is to accept the credentials, hand them to the
service, and shape the success response.

Anonymous by construction: no authorization dependency is declared, and none may be —
this is the endpoint that *hands out* the credential every other endpoint will check
(Story 1.4). A login behind a login is a bootstrap that never boots.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import auth as auth_service

router = APIRouter()


class LoginRequest(BaseModel):
    """The credentials a login presents (api-contracts §4.1).

    `email` is a plain string, not a validated email type: a syntactically odd email
    belonging to no Employee must fail as an ordinary `AUTH_FAILED` (AC4), not as a 422
    that would disclose the request even reached format validation. The service treats
    every non-matching credential identically.
    """

    email: str
    password: str


class LoginResponse(BaseModel):
    """The token a successful login returns (api-contracts §4.1).

    `token_type` is the constant `"bearer"` — the scheme Story 1.3's `Authorization:
    Bearer <token>` header uses. It is a protocol constant, not an enumerated domain
    value, so it is not part of `domain/vocabulary.py`.
    """

    access_token: str
    token_type: str = "bearer"


@router.post("/auth/login", tags=["auth"])
def login(request: LoginRequest) -> LoginResponse:
    """Exchange credentials for a session token (AC3), or refuse with 401 `AUTH_FAILED`.

    On success: 200 with the signed JWT. On any failure — unknown email, wrong password,
    deactivated Employee — `authenticate` raises `AUTH_FAILED`, which surfaces as the
    401 envelope. The route writes no failure branch of its own; there is one to write.
    """
    employee = auth_service.authenticate(request.email, request.password)
    token = auth_service.issue_token(employee)
    return LoginResponse(access_token=token)
