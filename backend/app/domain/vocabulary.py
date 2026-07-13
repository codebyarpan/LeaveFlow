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

# Self-service code (Story 1.8, api-contracts §4.1, `G5`). `FORBIDDEN_FIELD` → 400 is the
# refusal `PATCH /me` raises when the body carries any field other than `full_name`: the
# actor is permitted both the endpoint and the resource (their own profile), so the domain
# refuses the *content* — a 400, not the 403 of "may see, may not act" nor the 404 of a
# scope miss. It is the last unmapped code in Epic 1. The service gate names the rejected
# field(s) in `details`; the `422` FastAPI would otherwise emit is suppressed so the
# envelope holds (NFR-17). Wired to 400 in `main.py`.
FORBIDDEN_FIELD = "FORBIDDEN_FIELD"

# Self-service code (Story 1.8, code review 2026-07-13). `INVALID_NAME` → 400 is the refusal
# `PATCH /me` raises when `full_name` is present but its *value* is unusable — `null`, a
# non-string, or empty/whitespace-only. Distinct from `FORBIDDEN_FIELD` (a rejected *key*):
# here the key is accepted but the content is refused, still a 400 (the actor owns the
# resource; the domain refuses the content). Validated in `services/me.py` BEFORE any write,
# so nothing persists; the check keeps every non-2xx body inside the `{code,message,details}`
# envelope (NFR-17) instead of leaking a bare Pydantic 422 or a NOT NULL 500. Wired in `main.py`.
INVALID_NAME = "INVALID_NAME"

# Resource-state code (Story 2.1, api-contracts §2). `LEAVE_TYPE_CODE_IN_USE` → 409 is the
# refusal `POST /leave-types` raises when the `code` already belongs to a Leave Type: the
# service pre-checks the duplicate and re-raises the `UNIQUE (code)` `IntegrityError` as this
# typed 409 (AD-5), so the constraint stays a backstop and never surfaces as a raw 500 —
# mirroring `EMAIL_ALREADY_IN_USE` (Story 1.6). Wired to 409 in `main.py`. EL/CL/FL are
# seeded DATA, never constants here (AD-11): a fourth Leave Type must add no code (SM-5).
LEAVE_TYPE_CODE_IN_USE = "LEAVE_TYPE_CODE_IN_USE"

# Resource-state code (Story 2.2, api-contracts §2). `HOLIDAY_DATE_IN_USE` → 409 is the
# refusal `POST /holidays` raises when a Company Holiday already falls on that `holiday_date`:
# the service pre-checks the duplicate and re-raises the `UNIQUE (holiday_date)`
# `IntegrityError` as this typed 409 (AD-5), so the constraint stays a backstop and never
# surfaces as a raw 500 — mirroring `LEAVE_TYPE_CODE_IN_USE` (Story 2.1). Wired to 409 in
# `main.py`. The holiday calendar starts empty and is populated through the API (AD-11-adjacent).
HOLIDAY_DATE_IN_USE = "HOLIDAY_DATE_IN_USE"

# Exclusion reasons (Story 2.5, api-contracts §4.5, FR-08/AD-2). These are RESPONSE REASONS,
# not error codes: they travel on the wire as `excluded_dates[].reason` in the preview payload,
# naming WHY a picked date costs no Leave Day — a `WEEKEND` (Sat/Sun) or a `HOLIDAY` (a Company
# Holiday, which also carries its `name`). They map to no HTTP status, so `main.py`'s
# `CODE_TO_STATUS` is untouched. They belong HERE because they are enumerated strings that leave
# the process, and AD-21 admits no enumerated literal outside this file: the instant they land in
# `__all__`, `test_vocabulary_literals.py` enforces them, so `domain/calendar.py` (the sole
# producer) and every test reference `vocabulary.EXCLUSION_WEEKEND`/`_HOLIDAY`, never the bare
# string. Weekend precedence (a holiday-on-a-weekend reports once as `WEEKEND`) lives in
# `domain/calendar.excluded_dates`, not here — these are only the two labels.
EXCLUSION_WEEKEND = "WEEKEND"
EXCLUSION_HOLIDAY = "HOLIDAY"

# Balance code (Story 2.4, api-contracts §4.4, AD-5). `INSUFFICIENT_BALANCE` → 400 is the
# refusal the balance-mutation module (`services/balances.py`) raises when a `reserve` or a
# `consume_direct` would take more days than `available` (`accrued − consumed − reserved`),
# read under the row's `SELECT … FOR UPDATE` lock. It is the GATE (AD-5): the three CHECK
# constraints on `leave_balance` are only the backstop, and a CHECK reaching a client is a
# defect and a 500 — so the module pre-checks and raises this typed 400 first, naming
# `days_requested` and `days_available` in `details` (NFR-17: "not enough balance" is not an
# actionable answer). Its raise site is `services/balances.py`, so — following the discipline
# that declares a code WITH its raise site (see `EMPLOYEE_HAS_PENDING_REQUESTS` above) — it is
# declared here, not in the later submission story (2.6) that merely CALLS `reserve`. Wired to
# 400 in `main.py`.
INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"

# Leave Request statuses (Story 2.6). These ARE code (AD-11): four states the application
# handles exhaustively, stored as TEXT with a `CHECK (status IN (...))` on `leave_request` — the
# counterpart to a Leave Type being a row. A submission is admitted as `PENDING` (a managed
# applicant, awaiting a Manager decision) or straight to `APPROVED` (managerless auto-approval,
# FR-09). `REJECTED`/`CANCELLED` are Story 2.7/2.8's guarded transitions, declared here now
# because the four are one closed vocabulary and the `CHECK` names all four. The only exempt
# copies of these literals are the model `__table_args__` CHECK and the migration DDL that mirror
# it (like `employee.role`), exactly as the docstring above records.
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_CANCELLED = "CANCELLED"

# Leave Request range-refusal codes (Story 2.6, api-contracts §2). Each is a SERVICE gate raised
# BEFORE the write (AD-5), so the `leave_request` CHECKs (`end_date >= start_date`, `leave_days >
# 0`) stay a backstop and never surface as a raw 500. All four map to 400 in `main.py`. Declared
# here WITH their raise site, `services/leave_requests.submit_leave_request`, which now exists —
# the same discipline that withheld these until the submission story owned them.
#   `INVALID_DATE_RANGE`   — `end_date < start_date` (an inverted range).
#   `PAST_DATE_RANGE`      — the range lies wholly in the past (`end_date < today`).
#   `SPANS_TWO_LEAVE_YEARS`— `start_date.year != end_date.year`; `details` names the boundary.
#   `ZERO_LEAVE_DAYS`      — the range contains no Working Day (`count_leave_days == 0`).
INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
PAST_DATE_RANGE = "PAST_DATE_RANGE"
SPANS_TWO_LEAVE_YEARS = "SPANS_TWO_LEAVE_YEARS"
ZERO_LEAVE_DAYS = "ZERO_LEAVE_DAYS"

# Employee-state code (Story 2.6, api-contracts §2). `EMPLOYEE_HAS_PENDING_REQUESTS` → 409 is the
# refusal `deactivate_employee` raises when the target still holds a Pending Leave Request:
# deactivating them would strand a request with no possible approval (AD-22). WITHHELD from Story
# 1.6 because no `leave_request` table existed then — its raise site becomes executable HERE, when
# the table it queries ships. `details` names the pending count. Wired to 409 in `main.py`.
EMPLOYEE_HAS_PENDING_REQUESTS = "EMPLOYEE_HAS_PENDING_REQUESTS"

# Audit vocabulary (Story 2.6, ERD §2, AD-8). These are enumerated strings that leave the process
# on an `audit_entry` row, so AD-21 requires them declared HERE, once. `ACTOR_EMPLOYEE`/
# `ACTOR_SYSTEM` are the two `actor_type` values (SYSTEM is the managerless auto-approval, with a
# NULL `actor_id` — the biconditional CHECK); `SUBJECT_LEAVE_REQUEST` is the polymorphic
# `subject_type` for a request row; `REASON_SUBMITTED` and `REASON_AUTO_APPROVED_NO_MANAGER` are
# the two `reason` strings this story writes (a plain PENDING submit vs. the FR-09 auto-approval),
# keeping `reason` NOT NULL and symmetric across both branches. They map to no HTTP status, so
# `CODE_TO_STATUS` is untouched.
ACTOR_EMPLOYEE = "EMPLOYEE"
ACTOR_SYSTEM = "SYSTEM"
SUBJECT_LEAVE_REQUEST = "LEAVE_REQUEST"
REASON_SUBMITTED = "SUBMITTED"
REASON_AUTO_APPROVED_NO_MANAGER = "AUTO_APPROVED_NO_MANAGER"

# Transition reasons (Story 2.7, ERD §2, AD-8/AD-21). The three `reason` strings the manual
# lifecycle transitions write on their `audit_entry` row — an approve, a reject, an applicant
# cancel. Symmetric with `REASON_SUBMITTED`/`REASON_AUTO_APPROVED_NO_MANAGER` (Open Decision #1,
# option (a)): the `from_state`/`to_state` on the row already carry the *what* of the transition;
# `reason` carries a stable label. `audit_entry.reason` is NOT NULL, so every transition names one.
# They map to no HTTP status, so `CODE_TO_STATUS` is untouched.
REASON_APPROVED = "APPROVED"
REASON_REJECTED = "REJECTED"
REASON_CANCELLED = "CANCELLED"

# Approved-leave-cancellation code (Story 2.8, api-contracts §2). `LEAVE_ALREADY_TAKEN` → 400 is
# the refusal `raise_cancellation_request` raises when a Cancellation Request is filed against an
# Approved request whose dates have already passed (`end_date < today` — the SAME `is_wholly_past`
# predicate `PAST_DATE_RANGE` uses at submission, DR-14): leave already taken cannot be un-taken.
# A past-date refusal names no numbers, so `details` is empty. Its raise site is
# `services/cancellation`, so it is declared here WITH that raise site, the same discipline the
# other refusals followed. Wired to 400 in `main.py`.
LEAVE_ALREADY_TAKEN = "LEAVE_ALREADY_TAKEN"

# Cancellation Request audit vocabulary (Story 2.8, ERD §3, AD-8/AD-21). A Cancellation Request is
# its own audit subject, so `SUBJECT_CANCELLATION_REQUEST` is the second `subject_type` value
# alongside `SUBJECT_LEAVE_REQUEST` (a decision writes one row per subject, discriminated by it —
# AC9). `REASON_CANCELLATION_REQUESTED` is the `reason` on the `NULL → PENDING` filing row when the
# raise is audited (Open Decision #3, Option A: every transition writes exactly one audit row, as a
# submission does — keeping AD-8/SM-4 one-to-one). The CR's own decision transitions reuse
# `REASON_APPROVED`/`REASON_REJECTED`, and the target Leave Request's `APPROVED → CANCELLED` move
# reuses `REASON_CANCELLED` (all from 2.7). The three CR STATUS values reuse
# `STATUS_PENDING`/`STATUS_APPROVED`/`STATUS_REJECTED` (Open Decision #1: identical strings, and
# AD-21 declares each string once — the `subject_type` discriminates which entity a status belongs
# to; the `cancellation_request` CHECK DDL is the only exempt copy, like `leave_request`). These
# map to no HTTP status, so `CODE_TO_STATUS` is untouched.
SUBJECT_CANCELLATION_REQUEST = "CANCELLATION_REQUEST"
REASON_CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"

# Transition-conflict code (Story 2.7, api-contracts §2). `TRANSITION_NOT_ALLOWED` → 409 is the
# refusal a guarded conditional `UPDATE … WHERE status = :from` raises when it matches ZERO rows:
# the request is no longer in the state the transition requires — someone committed a competing
# transition first (a Manager approving a request the applicant just cancelled), or the request was
# never `PENDING`. This is AD-4's first-committed-wins made a clean 409 rather than a silent
# overwrite; the whole transaction rolls back, so no balance moves and no audit row lands. Its raise
# site is `services/leave_requests` (the three transition commands), so it is declared here WITH that
# raise site, the same discipline the range refusals followed. Wired to 409 in `main.py`.
TRANSITION_NOT_ALLOWED = "TRANSITION_NOT_ALLOWED"

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
    "FORBIDDEN_FIELD",
    "INVALID_NAME",
    "LEAVE_TYPE_CODE_IN_USE",
    "HOLIDAY_DATE_IN_USE",
    "EXCLUSION_WEEKEND",
    "EXCLUSION_HOLIDAY",
    "INSUFFICIENT_BALANCE",
    "STATUS_PENDING",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    "STATUS_CANCELLED",
    "INVALID_DATE_RANGE",
    "PAST_DATE_RANGE",
    "SPANS_TWO_LEAVE_YEARS",
    "ZERO_LEAVE_DAYS",
    "EMPLOYEE_HAS_PENDING_REQUESTS",
    "ACTOR_EMPLOYEE",
    "ACTOR_SYSTEM",
    "SUBJECT_LEAVE_REQUEST",
    "REASON_SUBMITTED",
    "REASON_AUTO_APPROVED_NO_MANAGER",
    "REASON_APPROVED",
    "REASON_REJECTED",
    "REASON_CANCELLED",
    "TRANSITION_NOT_ALLOWED",
    "LEAVE_ALREADY_TAKEN",
    "SUBJECT_CANCELLATION_REQUEST",
    "REASON_CANCELLATION_REQUESTED",
]
