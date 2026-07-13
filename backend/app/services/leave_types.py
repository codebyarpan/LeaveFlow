"""Leave Type command orchestration: the create, the list, and the one refusal.

Implements: FR-06 (Leave Types are defined as data, AD-11), SM-5 (a fourth type is added
through the API with no code change and no schema migration), AD-3 (one transaction per
command), AD-5 (the `UNIQUE (code)` constraint is a BACKSTOP; this service is the gate that
raises `409 LEAVE_TYPE_CODE_IN_USE`). SM-6.

The single refusal this story raises:
  - `LEAVE_TYPE_CODE_IN_USE` (409) — a duplicate `code` on create. Pre-checked before the
    write, with an `IntegrityError` backstop around the insert-and-commit that re-raises the
    typed 409 for a genuine TOCTOU collision — the exact shape `services/employee.py` uses for
    `EMAIL_ALREADY_IN_USE`.

The write command opens exactly one `with Session(get_engine(), expire_on_commit=False)`
and commits inside it (AD-3) — the idiom `services/departments.py` documents.
`expire_on_commit=False` keeps the returned row's attributes readable after the block
closes, so the `api/` route can project it into the response.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.repositories import leave_type as leave_type_repo
from app.repositories.engine import get_engine
from app.repositories.models import LeaveType

# One message per refusal, stated once at module level — mirrors `services/employee.py`'s
# `_EMAIL_ALREADY_IN_USE_MESSAGE`. The `details` carry the conflicting `code` so NFR-17's
# "names the obstruction" is satisfied — unlike an email, a Leave Type `code` is not
# sensitive, so naming it is helpful rather than a disclosure.
_LEAVE_TYPE_CODE_IN_USE_MESSAGE = "A leave type with that code already exists."


def _leave_type_code_in_use(code: str) -> DomainError:
    """Build the `409 LEAVE_TYPE_CODE_IN_USE` refusal, naming the conflicting `code` (AD-5).

    Shared by the pre-write gate and the `UNIQUE (code)` `IntegrityError` backstop so both
    paths raise a byte-identical envelope — the same code, message and `details.code` shape.
    """
    return DomainError(
        code=vocabulary.LEAVE_TYPE_CODE_IN_USE,
        message=_LEAVE_TYPE_CODE_IN_USE_MESSAGE,
        details={"code": code},
    )


def create_leave_type(
    *,
    code: str,
    name: str,
    annual_entitlement: int,
    carries_forward: bool,
    carry_forward_cap: int | None,
    requires_supporting_document: bool,
) -> LeaveType:
    """Create a Leave Type and return it, refusing a duplicate `code` (AC3, AC6, SM-5).

    One transaction (AD-3). In order:
      1. Pre-check the `code` — an existing row → `409 LEAVE_TYPE_CODE_IN_USE` before the
         write (Trap: the gate, not the constraint's 500).
      2. Insert and `flush` (for the server-default id) INSIDE the `try` — the repo's
         `flush()` is what emits the INSERT, so a concurrent duplicate raises the
         `IntegrityError` HERE, not at commit. Wrapping only `commit()` would let that raw
         500 escape (the pre-check hides it in every non-concurrent test).
      3. Commit; a `UNIQUE (code)` `IntegrityError` from the flush OR the commit rolls back
         and re-raises the typed 409 ONLY for a genuine `code` collision (a concurrent insert
         between the pre-check and the commit) — the TOCTOU backstop (AD-5, mirrors
         `create_employee`). Any other IntegrityError is re-raised untouched rather than
         mislabeled as a duplicate code.

    Adding a fourth Leave Type is exactly this path: no schema migration, no code change —
    the AC3/SM-5 acceptance.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        if leave_type_repo.code_exists(session, code):
            raise _leave_type_code_in_use(code)

        try:
            leave_type = leave_type_repo.create_leave_type(
                session,
                code=code,
                name=name,
                annual_entitlement=annual_entitlement,
                carries_forward=carries_forward,
                carry_forward_cap=carry_forward_cap,
                requires_supporting_document=requires_supporting_document,
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if leave_type_repo.code_exists(session, code):
                raise _leave_type_code_in_use(code) from exc
            raise
        return leave_type


def list_leave_types(limit: int, offset: int) -> tuple[list[LeaveType], int]:
    """Return one page of Leave Types and the full count (AC4, AC9).

    A thin pass-through opening a read session and delegating to the repository; the `api/`
    route assembles the `Page` envelope from the `(rows, total)` this returns. Scope is
    `all` — any authenticated role reads the whole list — so there is no actor here.
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        return leave_type_repo.list_leave_types(session, limit, offset)
