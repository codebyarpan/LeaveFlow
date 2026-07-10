"""The canonical vocabulary. Every enumerated string in LeaveFlow is declared here.

Implements: AD-21 — every enumerated string is `UPPER_SNAKE_CASE`, declared exactly
once in `domain/`, and appears as a literal nowhere else. AC9: the values below are
this module's whole business, and `tests/test_vocabulary_literals.py` fails the build
if any of them appears as a string literal anywhere under `app/` or `seed/` except
here.

What arrives, and where:

- Story 1.2 (here) — the role values, and the error codes `AUTH_FAILED` and
  `TOKEN_INVALID`. `TOKEN_INVALID` is declared now, with the rest of login's
  vocabulary, even though Story 1.3 is the first to *raise* it: the vocabulary of a
  feature lands in one commit, not scattered across the stories that consume it.
- Story 2.1 — the Leave Type codes, as seeded *data*, not as constants here.
  `SM-5` requires a fourth Leave Type to be addable with no code change; a constant
  in this module would be exactly the code change it forbids.
- Story 2.6 onward — `leave_request.status`, which *is* code: four states the
  application handles exhaustively, stored as TEXT with a CHECK constraint.

The distinction between those last two is the whole of AD-11: a Leave Type is a row,
a request status is a constant.

--- On the database's copy of the role vocabulary ---

`employee.role`'s `CHECK (role IN ('EMPLOYEE','MANAGER','ADMIN'))` repeats these three
values in migration `0002` and in `repositories/models.py`. That is not a violation:
the literal check exempts `alembic/versions/` (a migration is immutable once applied,
and the DDL is the database's own copy of the constraint, prescribed by ERD §4.2) and
the models file mirrors that DDL. Everywhere else — services, api, seed — imports the
constants below.
"""

# Role values (AD-10, AD-14). The three roles the system authorizes against.
ROLE_EMPLOYEE = "EMPLOYEE"
ROLE_MANAGER = "MANAGER"
ROLE_ADMIN = "ADMIN"

# Error codes (api-contracts §2). Both map to 401 via `CODE_TO_STATUS`, wired in
# `main.py`. `AUTH_FAILED` is login's single refusal (Story 1.2); `TOKEN_INVALID` is
# the Bearer dependency's (Story 1.3) — declared here now, raised there.
AUTH_FAILED = "AUTH_FAILED"
TOKEN_INVALID = "TOKEN_INVALID"

__all__ = [
    "ROLE_EMPLOYEE",
    "ROLE_MANAGER",
    "ROLE_ADMIN",
    "AUTH_FAILED",
    "TOKEN_INVALID",
]
