"""Self-service command: the one write an Employee may make to their own profile.

Implements: FR-17 (an Employee corrects their own Full Name, and nothing else), G5 (the
`400 FORBIDDEN_FIELD` refusal — any field other than `full_name` is rejected, its
`details` naming the rejected field(s), and nothing is persisted), AD-3 (one transaction
per command), AD-14 (the actor is the row keyed by the token's subject — the mutation is
intrinsically scoped to "self", so there is no cross-Employee identifier and no role gate).
SM-6.

The two refusals this command raises, both BEFORE any write, so a rejected request persists
nothing (AC2) and every non-2xx body stays inside the `{code,message,details}` envelope
(NFR-17):
  - `FORBIDDEN_FIELD` (400) — the body carried a field other than `full_name` (`G5`).
  - `INVALID_NAME` (400) — `full_name` was present but its value is unusable: `null`, a
    non-string, or empty/whitespace-only (code review 2026-07-13). Without this gate a
    `null` reaches the `NOT NULL` column as an unenveloped 500 and a non-string trips a
    bare Pydantic 422 — both breaking NFR-17. The accepted value is trimmed before the write
    so leading/trailing whitespace is never stored (the client trims too; the server is the
    enforcement point, AD-14).

This is the deliberate OPPOSITE of `services/employee.py`'s `PATCH /employees/<id>`, which
*silently ignores* a field outside its allowlist (Trap 5 there). The two resources are
asymmetric on purpose: the Admin edits many fields and forgives extras; the Employee edits
exactly one field and refuses the rest. Do not copy the ignore-filter here.

The command opens exactly one `with Session(get_engine(), expire_on_commit=False)` and
commits inside it (AD-3), the idiom `services/employee.py` documents. `expire_on_commit=
False` keeps the returned row's attributes readable after the block closes, so the `api/`
route can project it once the session is gone; `department` is eager-loaded through
`load_employee` for the same reason.
"""

import uuid

from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import employee as employee_repo
from app.repositories.engine import get_engine
from app.repositories.models import Employee

# The one field `PATCH /me` accepts. Every other key in the body is forbidden — the mirror
# image of `services/employee.py`'s `_MUTABLE_FIELDS` allowlist, narrowed to a single name.
_EDITABLE_FIELD = "full_name"

# One message per refusal, stated once at module level — mirrors `services/employee.py`'s
# `_..._MESSAGE` constants. The rejected field names travel in `details`, not the message
# (NFR-17: the number/name a refusal must state belongs in `details`, not baked into prose).
_FORBIDDEN_FIELD_MESSAGE = (
    "Only your full name may be changed here; every other field was refused."
)

# One message per refusal, stated once at module level (mirrors the constant above and
# `services/employee.py`). The offending field name travels in `details`, not the prose.
_INVALID_NAME_MESSAGE = "Your full name must be a non-empty value."


def _forbidden_field(forbidden_fields: list[str]) -> DomainError:
    """Build the `400 FORBIDDEN_FIELD` refusal, naming the rejected field(s) (`G5`, NFR-17).

    `details.forbidden_fields` is what makes the refusal actionable — the caller (or a
    misbehaving client) learns exactly which keys `/me` will not accept. The list is sorted
    by the caller so the envelope is deterministic across test runs.
    """
    return DomainError(
        code=vocabulary.FORBIDDEN_FIELD,
        message=_FORBIDDEN_FIELD_MESSAGE,
        details={"forbidden_fields": forbidden_fields},
    )


def _invalid_name() -> DomainError:
    """Build the `400 INVALID_NAME` refusal for an unusable `full_name` value (NFR-17).

    Raised when `full_name` is present but `null`, non-string, or empty/whitespace-only.
    `details.field` names the offending field so the refusal is actionable and the envelope
    is deterministic across test runs.
    """
    return DomainError(
        code=vocabulary.INVALID_NAME,
        message=_INVALID_NAME_MESSAGE,
        details={"field": _EDITABLE_FIELD},
    )


def rename_me(actor_id: uuid.UUID, submitted: dict[str, object]) -> Employee:
    """Rename the calling Employee, refusing any field other than `full_name` (AC1–AC4).

    `submitted` carries only the fields the request set (the route builds it with
    `exclude_unset=True`). Two gates run FIRST, before the session opens, so a rejected
    request touches no row (AC2):
      1. Any key other than `full_name` → `400 FORBIDDEN_FIELD`, its `details` naming the
         rejected field(s). A body carrying `full_name` alongside a forbidden field is still
         refused — this gate wins, nothing persists.
      2. `full_name` present but its value unusable (`null`, non-string, or
         empty/whitespace-only) → `400 INVALID_NAME`. The accepted value is `strip()`ed
         before the write.

    A body with neither `full_name` nor a forbidden field (`{}`) is a graceful no-op:
    nothing is forbidden and nothing changes, so the current row is returned at `200`.

    Scope is intrinsic (AD-14): the mutation targets the row keyed by `actor_id`, the
    token's own subject, so there is no cross-Employee identifier, no `require_role`, and no
    `not_found()` scope mechanic — the row is guaranteed to exist because the token resolved
    to it. One transaction (AD-3); the loaded row carries `department` eager-loaded and, with
    `expire_on_commit=False`, stays readable after the block closes, so the same row instance
    is returned for the route to project into `MeResponse` — no second query.
    """
    forbidden = sorted(key for key in submitted if key != _EDITABLE_FIELD)
    if forbidden:
        raise _forbidden_field(forbidden)

    has_name = _EDITABLE_FIELD in submitted
    new_name: str | None = None
    if has_name:
        candidate = submitted[_EDITABLE_FIELD]
        if not isinstance(candidate, str) or not candidate.strip():
            raise _invalid_name()
        new_name = candidate.strip()

    with Session(get_engine(), expire_on_commit=False) as session:
        employee = employee_repo.load_employee(session, actor_id)

        if new_name is not None:
            employee_repo.apply_employee_changes(employee, {_EDITABLE_FIELD: new_name})
            session.commit()

        return employee
