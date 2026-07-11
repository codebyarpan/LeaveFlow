"""Authentication: exchange credentials for an Employee, then an Employee for a token.

Implements: FR-01 (login), FR-04 / AD-22 (a deactivated Employee cannot authenticate),
AD-3 (one transaction per command, opened here), AD-14 (the token), and the AC4/AC5/AC8
guarantee that failure discloses nothing — not by discipline, but by construction.

--- The single raise site (AC4, AC5, AC8) ---

Every way login can fail — unknown email, wrong password, deactivated Employee — leaves
through the *same* `raise DomainError(AUTH_FAILED, ...)`, with the same message and the
same empty `details`. There is exactly one such statement in this module. "Byte-identical
response" is therefore true by construction: the handler renders one envelope from one
exception, so the unknown-email and wrong-password bodies cannot drift apart without
someone adding a second raise — which review would catch.

--- Why the hash comparison always runs, and its result is sometimes discarded (AC5) ---

When no row is found, the code still runs one real bcrypt verification, against a
constant fallback hash, and throws the result away. Without it, the unknown-email path
would return measurably faster (no hashing) than the wrong-password path, and the timing
would disclose which emails belong to accounts. The fallback's preimage is in the source
(`core.security.FALLBACK_HASH`), so a `True` from it must never decide anything — here it
is discarded before the unconditional raise.

--- Why `is_active` is checked AFTER the hash comparison (AC7, AD-22) ---

If deactivation were checked first, a deactivated account would fail *before* hashing and
so respond faster than an active account with a wrong password — the same disclosure AC5
closes for unknown emails, reopened for deactivated ones. Checking it after the hash
comparison keeps the deactivated path timing-indistinguishable from every other failure.
"""

import uuid
from typing import NoReturn

import jwt
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import employee as employee_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee

# One message, stated once, for every failure mode. Referenced by the single raise site
# below — so the body a client sees is identical whether the email was unknown, the
# password wrong, or the account deactivated. It says nothing that distinguishes them.
_AUTH_FAILED_MESSAGE = "The email or password is incorrect."

# The token path's counterpart to `_AUTH_FAILED_MESSAGE`. One sentence, stated once, for
# every rejection `resolve_actor` can make — absent, expired, tampered, malformed subject,
# or a subject that names no row. AD-14: failure discloses nothing, so the reason a token
# was rejected never reaches the client. Byte-identity across reasons is the property.
_TOKEN_INVALID_MESSAGE = "The session token is missing or invalid."


def authenticate(email: str, password: str) -> Employee:
    """Return the Employee these credentials belong to, or refuse with `AUTH_FAILED`.

    Refuses identically for an unknown email, a wrong password and a deactivated
    Employee (AC4, AC5, AC7). Opens one connection for the command (AD-3); the read is
    the whole of the work, but this is the transaction idiom the write commands copy.

    `expire_on_commit=False` is set so the returned `Employee` stays usable after the
    `with` block closes — `issue_token` reads `.id`/`.role` on it once the session is
    gone. It works today without the flag (a read never commits, so nothing expires), but
    the write commands that COPY this idiom WILL commit, and the default
    `expire_on_commit=True` would then expire those attributes and raise
    `DetachedInstanceError` on the caller's next access. Setting it here makes the copied
    pattern commit-safe by construction rather than leaving a trap for the first writer.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        found = employee_repo.get_by_email(session, email)

        # AC5: one bcrypt comparison runs on EVERY path. On the unknown-email path it
        # runs against the constant fallback and the result is discarded — the raise
        # below is unconditional there. `verify_password` is invoked exactly once in
        # both branches, which is the structural property AC5's spy test asserts.
        if found is None:
            security.verify_password(password, security.FALLBACK_HASH)
            raise DomainError(code=vocabulary.AUTH_FAILED, message=_AUTH_FAILED_MESSAGE)

        password_matches = security.verify_password(password, found.password_hash)

        # AC7/AD-22: deactivation is checked AFTER the hash comparison, so a deactivated
        # account is not distinguishable from a wrong password by timing.
        if not password_matches or not found.is_active:
            raise DomainError(code=vocabulary.AUTH_FAILED, message=_AUTH_FAILED_MESSAGE)

        return found


def resolve_actor(token: str) -> Employee:
    """Verify a Bearer token and return the Employee it belongs to (AD-14, FR-17).

    This is the ONLY legal home for the JWT-error → domain-error translation and the
    actor lookup. `core.security.decode_token` cannot raise `DomainError` (it is a leaf,
    contract 6, and knows no error code), and the `api/` Bearer dependency cannot either
    (contract 2 forbids it importing `domain/` or `repositories/`). So both the catch and
    the load land here, the one layer allowed to import `jwt`, `core`, `domain` and
    `repositories` — but never `fastapi` (contract 4).

    Order (AD-14's three rejection cases plus the two malformed-subject variants):

    1. Decode and verify signature + `exp`. `decode_token` lets `jwt.PyJWTError` subclasses
       propagate — `InvalidSignatureError` (tampered) and `ExpiredSignatureError`
       (expired). We catch the base `PyJWTError`, never bare `Exception`, so a genuine bug
       still surfaces as a 500 rather than being masked as a rejected token.
    2. Read `sub` and parse it to a `UUID`. A signed token can still carry a missing or
       non-UUID subject; that is a rejected token, not a 500.
    3. Load the Employee by that subject. A validly-signed token for a since-deleted (or
       never-existing) subject is rejected.

    The caller's role is `employee.role` FROM THIS ROW (AD-14 / NFR-03) — `claims["role"]`
    is never read to make a decision. Nothing the client sent beyond `sub` is trusted.

    Every rejection leaves through the one `reject()` below, so the `TOKEN_INVALID`
    envelope is byte-identical across all five reasons — the same discipline login's
    single `AUTH_FAILED` raise site keeps.

    🚫 It does NOT check `is_active`. `AD-14` enumerates exactly three rejection cases and
    a deactivated-but-authenticated token is none of them; that decision is deliberately
    left open (G4) and is not this story's to make. Do not add the check here.
    """

    def reject() -> NoReturn:
        raise DomainError(code=vocabulary.TOKEN_INVALID, message=_TOKEN_INVALID_MESSAGE)

    try:
        claims = security.decode_token(token)
    except jwt.PyJWTError:
        reject()

    subject = claims.get("sub")
    if not subject:
        reject()

    try:
        subject_id = uuid.UUID(subject)
    except (ValueError, TypeError, AttributeError):
        # ValueError: a well-formed string that is not a UUID. TypeError/AttributeError:
        # a `sub` that is not a string at all (a forged token could carry any JSON value).
        reject()

    # AD-3: one connection for the read. `expire_on_commit=False` mirrors login's idiom so
    # the returned row — and its eager-loaded `department` — stay usable after the block.
    with Session(get_engine(), expire_on_commit=False) as session:
        employee = employee_repo.get_by_id_with_department(session, subject_id)

    if employee is None:
        reject()

    return employee


def issue_token(employee: Employee) -> str:
    """Sign the session token for an already-authenticated Employee (AC3, AD-14).

    `str(employee.id)` — the JWT `sub` claim must be a string, and `employee.id` is a
    UUID. `core.security` owns the signing; this service owns only the decision to sign.
    """
    return security.create_token(str(employee.id), employee.role)
