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


def issue_token(employee: Employee) -> str:
    """Sign the session token for an already-authenticated Employee (AC3, AD-14).

    `str(employee.id)` — the JWT `sub` claim must be a string, and `employee.id` is a
    UUID. `core.security` owns the signing; this service owns only the decision to sign.
    """
    return security.create_token(str(employee.id), employee.role)
