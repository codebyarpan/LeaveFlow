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
- Story 1.4 (here) — the authorization codes `ACTION_NOT_PERMITTED` (→ 403, "may see,
  may not act") and `RESOURCE_NOT_FOUND` (→ 404). The 404 code is the one enumerated
  value api-contracts §2's list does not name: `NFR-17` requires *every* non-2xx body to
  carry the `{code, message, details}` envelope, so the not-found refusal is enveloped
  like every other refusal rather than left as FastAPI's bare `{"detail": "Not Found"}`.
  Every `404` — a genuine "no such id" and an out-of-scope scope miss alike — carries this
  one code, byte-identically, so a Manager cannot probe which resources exist (`AD-10`).
- Story 1.5 (here) — the error code `DEPARTMENT_NOT_EMPTY` (→ 409): a `DELETE` of a
  Department that still has assigned Employees is refused, naming the obstruction rather
  than letting the FK RESTRICT surface as a bare 500 (`FR-05`, `AD-5`).
- Story 1.6 (here) — the three Employee-management refusals: `EMAIL_ALREADY_IN_USE`
  (→ 409), the service gate over `UNIQUE (email)` on create/update (`G2`, `AD-5`);
  `REPORTING_CYCLE` (→ 400), the acyclic-graph gate over `CHECK (id <> manager_id)` on a
  manager assignment (`AD-23`, `G7`); and `EMPLOYEE_HAS_DIRECT_REPORTS` (→ 409), the
  refusal to deactivate or demote below `MANAGER` while an active Employee reports to them
  (`AD-22`, `G8`). `EMPLOYEE_HAS_PENDING_REQUESTS` is deliberately NOT declared here: its
  only raise site is Epic 2's Leave Request submission story, which creates the
  `leave_request` table — and the codebase's discipline is to declare a code *with* its
  raise site, so it lands there, when the table it queries exists.
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

# Authorization codes (Story 1.4, api-contracts §1). `ACTION_NOT_PERMITTED` → 403 is
# reserved for exactly "the actor may see this resource but may not act upon it", decided
# by the role gate before any row is read. `RESOURCE_NOT_FOUND` → 404 is the single code
# every not-found carries — a nonexistent id and a scope miss are indistinguishable down
# to the bytes (AD-10). Both wire to their statuses in `main.py`.
ACTION_NOT_PERMITTED = "ACTION_NOT_PERMITTED"
RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

# Resource-state code (Story 1.5, api-contracts §2). `DEPARTMENT_NOT_EMPTY` → 409 is the
# refusal to delete a Department that still has assigned Employees: the emptiness check is
# the gate (AD-5), so the obstruction is named in the envelope rather than reaching the
# client as the FK RESTRICT's bare 500. Wired to 409 in `main.py`.
DEPARTMENT_NOT_EMPTY = "DEPARTMENT_NOT_EMPTY"

# Employee-management codes (Story 1.6, api-contracts §2). Each is a SERVICE gate that
# raises before the write, so the underlying database constraint (`UNIQUE (email)`,
# `CHECK (id <> manager_id)`) is only the AD-5 backstop and never the surfaced 500.
# `EMAIL_ALREADY_IN_USE` → 409 (a duplicate email on create/update, `G2`);
# `REPORTING_CYCLE` → 400 (a manager assignment that would close a cycle, `AD-23`/`G7`);
# `EMPLOYEE_HAS_DIRECT_REPORTS` → 409 (deactivation or demotion-below-`MANAGER` while an
# active Employee reports to them, `AD-22`/`G8`). All three wire to their statuses in
# `main.py`. `EMPLOYEE_HAS_PENDING_REQUESTS` is NOT here — see the docstring above.
EMAIL_ALREADY_IN_USE = "EMAIL_ALREADY_IN_USE"
REPORTING_CYCLE = "REPORTING_CYCLE"
EMPLOYEE_HAS_DIRECT_REPORTS = "EMPLOYEE_HAS_DIRECT_REPORTS"

__all__ = [
    "ROLE_EMPLOYEE",
    "ROLE_MANAGER",
    "ROLE_ADMIN",
    "AUTH_FAILED",
    "TOKEN_INVALID",
    "ACTION_NOT_PERMITTED",
    "RESOURCE_NOT_FOUND",
    "DEPARTMENT_NOT_EMPTY",
    "EMAIL_ALREADY_IN_USE",
    "REPORTING_CYCLE",
    "EMPLOYEE_HAS_DIRECT_REPORTS",
]
