"""Password hashing and JWT mechanics — and nothing else.

Implements: AD-14 (Bearer JWT with an hours-lifetime `exp`; `pwdlib` not `passlib`;
`PyJWT` not `python-jose`), AC3 (the token a successful login returns), AC6 (a stored
`password_hash` is a salted bcrypt digest from which the password cannot be recovered).

--- Where this module sits, and what it must never become ---

`core/` is a leaf (contract 6). This module imports `core.settings` and third-party
libraries ONLY. It must never import `app.domain` — and so it raises no `DomainError`
and knows no error *code*. It returns booleans and strings, and lets PyJWT's own
exceptions propagate to its caller in `services/`, which is the layer allowed to
translate a library failure into a domain refusal (`AUTH_FAILED`). A `DomainError`
raised here would need `import app.domain`, and the build would fail — correctly.

So this file is deliberately dumb: it knows how to hash, verify, sign and decode. It
does not know what a failed login *means*. That knowledge lives one layer up.

--- The three library traps this module is built around (all verified 2026-07-10) ---

1. `PasswordHash.recommended()` raises `HasherNotAvailable` here — the argon2 extra is
   not installed. The hasher is constructed explicitly instead.
2. bcrypt 5.0.0 raises `ValueError` for a password over 72 bytes; it no longer
   truncates. Both `hash_password` and `verify_password` pre-check the *encoded byte*
   length so an over-long password never reaches bcrypt.
3. `jwt.decode` without `algorithms=` raises `DecodeError` unconditionally in PyJWT
   2.13 — there is no default algorithm. `decode_token` always passes it.
"""

import datetime

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.settings import get_settings

# Constructed explicitly, NOT via `PasswordHash.recommended()` — see trap 1 above.
# `recommended()` tries argon2 first and raises `HasherNotAvailable` on this project's
# pins (`pwdlib[bcrypt]`, no argon2 extra). This produces `$2b$12$...` bcrypt digests.
_password_hash = PasswordHash((BcryptHasher(),))

# bcrypt's hard limit. A password whose UTF-8 encoding exceeds this many bytes cannot be
# hashed by bcrypt 5.0.0 — it raises rather than truncating. Multibyte characters count
# per byte, not per character, so the check is on `.encode("utf-8")`, never on `len()`.
_BCRYPT_MAX_BYTES = 72


def _exceeds_bcrypt_limit(password: str) -> bool:
    return len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES


def hash_password(password: str) -> str:
    """Return a salted bcrypt digest of `password` (AC6, AD-14).

    Raises `ValueError` on a password over 72 bytes. The only caller that hashes a
    human-supplied password is the seed command, at startup, where an over-long
    `SEED_ADMIN_PASSWORD` must fail loudly and legibly rather than 500 later — so the
    error is raised, not swallowed. `verify_password`, on the login path, swallows the
    same condition into a `False`; the asymmetry is deliberate.
    """
    if _exceeds_bcrypt_limit(password):
        raise ValueError(
            "password exceeds bcrypt's 72-byte limit (encoded as UTF-8). At seed time "
            "this means SEED_ADMIN_PASSWORD is too long — shorten it in .env."
        )
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Return whether `password` matches `hashed`. Password FIRST (pwdlib's order).

    An over-long password returns `False` here rather than raising: on the login path
    it is an ordinary failed attempt, indistinguishable from a wrong password, and it
    must not 500 (trap 2). The length check runs *before* any hashing on every path, so
    it leaks nothing about whether the account exists.

    Never raises for a malformed stored hash either in normal operation — every stored
    hash is one this module produced. A genuinely corrupt hash is a `pwdlib` error and
    is allowed to propagate, because it is a defect, not a failed login.
    """
    if _exceeds_bcrypt_limit(password):
        return False
    return _password_hash.verify(password, hashed)


# A constant hash, computed once at import, for the unknown-email path (AC5). The login
# service verifies against this when no Employee row is found, so that a missing row
# runs exactly the same one bcrypt comparison a present row does — the lookup never
# short-circuits. Its preimage is in this source, so a `True` from it must be discarded
# by the caller and MUST NEVER decide anything (Dev Notes trap 4).
FALLBACK_HASH = hash_password("leaveflow-constant-fallback-preimage")


def create_token(subject: str, role: str) -> str:
    """Sign a JWT carrying the subject id and role, expiring in `jwt_expire_hours` (AD-14).

    `subject` MUST be a string — pass `str(employee.id)`. PyJWT validates the `sub`
    claim's type and rejects a non-string. The lifetime is measured in hours (NFR-02:
    no refresh mechanism exists, so the access token is the whole session), never days.
    """
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "exp": now + datetime.timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT, returning its claims. Written now; consumed by Story 1.3.

    `algorithms=` is MANDATORY in PyJWT 2.13 — omitting it raises `DecodeError`
    unconditionally, so it is always passed (trap 3). A tampered token raises
    `InvalidSignatureError`, an expired one `ExpiredSignatureError`; both subclass
    `jwt.PyJWTError`, which Story 1.3's Bearer dependency catches to raise
    `TOKEN_INVALID`. This function does not catch them — translation is the caller's job.
    """
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
