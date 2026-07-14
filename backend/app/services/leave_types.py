"""Leave Type command orchestration: the create, the list, and — since 2.12 — the EDIT.

Implements: FR-06 (Leave Types are defined as data, AD-11; and — its last clause, Story 2.12 — an
Admin changing policy is FORCED to say what happens to the balances that already exist), SM-5 (a
fourth type is added through the API with no code change and no schema migration, and — AC9 — its
policy is then edited and rolled over the same way), AD-3 (one transaction per command), AD-5 (the
`UNIQUE (code)` and `CHECK (disposition IN (…))` constraints are BACKSTOPS; this service is the gate),
AD-19 (the policy recalculation runs INSIDE this command's one transaction, and may refuse per pair
while the rest of the operation commits). SM-6.

--- Since Story 2.12, a Leave Type edit is not CRUD. It is a recalculation with a question attached ---

Story 2.1 shipped `POST` and `GET` and DELIBERATELY shipped no edit path, saying so by name: "Out of
scope for this story (same resource, later): `PATCH /leave-types/<id>` (requires
`RECALCULATE`/`PRESERVE` disposition → `policy_change`) and `GET /policy-changes`. Do not build them
here." This is that edit path.

Because `PATCH` is NEW, this story makes NO breaking change — unlike Story 2.11, which had to move
`POST`/`DELETE /holidays` off `201`/`204`. `POST /leave-types` stays `201`. Do not "helpfully"
harmonize it.

The refusals:
  - `LEAVE_TYPE_CODE_IN_USE` (409) — a duplicate `code` on CREATE. Pre-checked before the write, with
    an `IntegrityError` backstop around the insert-and-commit that re-raises the typed 409 for a
    genuine TOCTOU collision — the exact shape `services/employee.py` uses for `EMAIL_ALREADY_IN_USE`.
  - `POLICY_DISPOSITION_REQUIRED` (400) — a balance-affecting EDIT carrying no valid disposition.
    Nothing is applied. FR-06's whole point.
  - `FORBIDDEN_FIELD` (400) — a `PATCH` key this resource does not accept (`code` among them).
  - `RESOURCE_NOT_FOUND` (404) — a `PATCH` of an id that names no row.

A per-pair recalculation refusal is NOT in that list, and that is the whole of AD-19: it does not fail
the command. The edit commits, the endpoint answers `200`, and the refused pair is named in the
summary and recorded in `admin_review_flag`.

Each write command opens exactly one `with Session(get_engine(), expire_on_commit=False)` and commits
inside it (AD-3) — the idiom `services/departments.py` documents. `expire_on_commit=False` keeps the
returned row's attributes readable after the block closes, so the `api/` route can project it into the
response.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import vocabulary
from app.domain.errors import DomainError
from app.domain.proration import prorate_entitlement
from app.repositories import employee as employee_repo
from app.repositories import leave_type as leave_type_repo
from app.repositories import policy_change as policy_change_repo
from app.repositories.engine import get_engine
from app.repositories.models import LeaveType
from app.services import authorization as authz
from app.services import balances
from app.services import recalculation as recalculation_service
from app.services.recalculation import RecalculationSummary


def _now() -> datetime.datetime:
    """The current instant (UTC), from the shell clock (AD-1) — a `policy_change`'s moment.

    Private to this service, exactly like `leave_requests._now`, `cancellation._now`, `rollover._now`
    and `recalculation._now`: there is no shared clock module in this codebase, deliberately.
    Timezone-AWARE — `occurred_at` is a `TIMESTAMPTZ`, and a naive datetime against it is a defect,
    not a nit.
    """
    return datetime.datetime.now(datetime.timezone.utc)

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
            # Materialize a leave_balance row for the new Leave Type × every Employee, for the
            # current Leave Year — Story 2.4's create hook. This IS the SM-5 guarantee: a fourth
            # Leave Type added through the API immediately has a balance every Employee can apply
            # against — no migration, no code change. Inside this same transaction (AD-3), before
            # commit, so a materialization failure rolls the create back. Routes through
            # `balances.set_accrual` only — the sole balance writer (AD-17). Each Employee's
            # proration reads THEIR joining_date; `carried_forward = 0` (first year for this
            # type); `entitlement_basis` is the new type's annual_entitlement. The clock lives
            # here in the shell, never in `domain/` (AD-1).
            current_year = datetime.date.today().year
            for employee in employee_repo.all_employees(session):
                balances.set_accrual(
                    session,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    leave_year=current_year,
                    prorated_entitlement=prorate_entitlement(
                        leave_type.annual_entitlement, employee.joining_date, current_year
                    ),
                    carried_forward=0,
                    entitlement_basis=leave_type.annual_entitlement,
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


# ==============================================================================================
# Story 2.12 — the edit path, and the disposition the Admin is FORCED to choose (FR-06)
# ==============================================================================================

# The three attributes whose change AFFECTS BALANCES THAT ALREADY EXIST, and therefore demands a
# disposition. `annual_entitlement` and `carry_forward_cap` are named by AD-19, AD-6, architecture
# §6.3 and AC6. `carries_forward` is added on FR-06's own words — "a change that would affect Leave
# Balances that already exist" (Open Decision #2): `carry_forward_days` reads it FIRST, so flipping it
# `true → false` zeroes `carried_forward` in every materialized year. AD-19's list describes the
# recalculation MECHANISM; FR-06's condition is the GATE, and this is the gate.
#
# Deliberately NOT here: `name`, `code`, `requires_supporting_document`. None of them enters any
# balance arithmetic, so none of them can move a number that already exists. A `PATCH` touching only
# those needs no disposition, writes no `policy_change` row, and recalculates nothing.
_BALANCE_AFFECTING = ("annual_entitlement", "carry_forward_cap", "carries_forward")

# The attributes a `PATCH` may submit at all. `code` is deliberately absent — see `_forbidden_field`.
_UPDATABLE = (
    "name",
    "annual_entitlement",
    "carries_forward",
    "carry_forward_cap",
    "requires_supporting_document",
)

# The two attributes whose change makes `PRESERVE` UNIMPLEMENTABLE, so the forward-checked
# recomputation runs under BOTH dispositions (Landmine 3, Open Decision #1). See
# `_must_recalculate` for the argument; it is the load-bearing decision of this story.
_CAP_ATTRIBUTES = ("carry_forward_cap", "carries_forward")

_POLICY_DISPOSITION_REQUIRED_MESSAGE = (
    "This change affects leave balances that already exist. Choose what happens to them."
)

_FORBIDDEN_FIELD_MESSAGE = "That field cannot be changed on a leave type."


def _policy_disposition_required(
    attributes: list[str], disposition: object
) -> DomainError:
    """Build the `400 POLICY_DISPOSITION_REQUIRED` refusal, naming what forced the choice (AD-5).

    ONE code for BOTH failure modes — "no disposition was supplied" and "one was supplied but it is
    not `RECALCULATE` or `PRESERVE`" — because api-contracts defines exactly one code here and a
    second must not be invented. The two are the same question with the same answer: the Admin has
    not made a valid choice, so nothing is applied.

    `details` is ACTIONABLE (NFR-17): it names the attributes that forced the choice AND the two
    values that are accepted. "A disposition is required" without saying which ones exist is not an
    answer a client can act on. `supplied` echoes what was actually sent (possibly `None`), so an
    Admin who typed `"RECALCULATED"` can see their own typo rather than guess.
    """
    return DomainError(
        code=vocabulary.POLICY_DISPOSITION_REQUIRED,
        message=_POLICY_DISPOSITION_REQUIRED_MESSAGE,
        details={
            "attributes": sorted(attributes),
            "accepted": [
                vocabulary.DISPOSITION_RECALCULATE,
                vocabulary.DISPOSITION_PRESERVE,
            ],
            "supplied": disposition,
        },
    )


def _forbidden_field(fields: list[str]) -> DomainError:
    """Build the `400 FORBIDDEN_FIELD` refusal for a key this PATCH does not accept (G5's shape).

    `extra="allow"` on the request model (the `PATCH /me` precedent — see the route) means an unknown
    key REACHES this service rather than triggering a bare Pydantic `422` outside the
    `{code,message,details}` envelope (NFR-17). So the service refuses it, with the code Story 1.8
    coined for exactly this: the actor is permitted the endpoint and the resource, and the domain
    refuses the CONTENT.

    `code` is refused along with the unknown keys, and deliberately: it is a Leave Type's IDENTITY,
    carried by `UNIQUE (code)` and matched against by nothing but itself. Renaming it is not a policy
    change with a disposition — it is a different Leave Type — and neither the ACs nor api-contracts
    grant an edit path for it. Refusing it is honest; silently accepting it would need a duplicate-
    `code` 409 story this AC does not ask for.
    """
    return DomainError(
        code=vocabulary.FORBIDDEN_FIELD,
        message=_FORBIDDEN_FIELD_MESSAGE,
        details={"fields": sorted(fields), "updatable": sorted(_UPDATABLE)},
    )


def _stringify(value: object) -> str:
    """Render an attribute value for `policy_change.old_value`/`new_value` (TEXT, NOT NULL).

    ONE column pair must carry an `int` (`annual_entitlement`), a NULLABLE int
    (`carry_forward_cap`) and a `bool` (`carries_forward`) — erd.md L151-152 types them TEXT for
    exactly that reason. `None` becomes the literal string `"null"` (Open Decision #6), so the columns
    stay NOT NULL and "the cap was REMOVED" is a different recorded value from "there never was a
    cap". The screen renders whatever it receives (AD-2).
    """
    if value is None:
        return "null"
    return str(value)


def _must_recalculate(changed: dict[str, object], disposition: str) -> bool:
    """Does this change run the forward-checked recomputation? (AC5, AC6 — and Landmine 3.)

    ⚠️ THE DISPOSITIONS DO NOT MAP ONTO "write balances" / "don't write balances". They map onto WHAT
    HAS A BASIS TO PRESERVE. This function is where that distinction lives, and getting it wrong
    plants a 500 that detonates weeks later in an unrelated Manager's transaction.

    | attribute changed              | PRESERVE                          | RECALCULATE |
    |--------------------------------|-----------------------------------|-------------|
    | `annual_entitlement`           | balances untouched                | re-derive   |
    | `carry_forward_cap`            | ⚠️ re-derive ANYWAY               | re-derive   |
    | `carries_forward`              | ⚠️ re-derive ANYWAY               | re-derive   |

    --- Why PRESERVE is a genuine no-op for `annual_entitlement` (AC4) ---

    `entitlement_basis` FREEZES the annual entitlement on the balance row — that is the whole reason
    the column exists (erd.md L215: "without it, FR-06's RECALCULATE disposition has nothing to
    recalculate from"). And future accruals pick the new value up for free: `run_rollover` re-prorates
    `Y+1` from `leave_type.annual_entitlement` at every boundary, and the create hooks prorate from
    the live row. So "only future accruals use the new value" is delivered by updating the
    `leave_type` row and STOPPING. Write no balance, call no recompute, touch nothing else.

    --- Why PRESERVE CANNOT preserve a cap (Landmine 3, Open Decision #1) ---

    THERE IS NO `carry_forward_cap_basis`. Nothing freezes the cap. Every downstream trigger re-reads
    it LIVE off the `leave_type` row — `rollover.recompute_carry_forward` at :265/:295-299, and
    `run_rollover` at :176-180 — and NEITHER HAS A FORWARD CHECK. So "PRESERVE the cap, write
    nothing" does not preserve anything; it merely defers the re-derivation to a code path that
    cannot refuse:

      1. an Admin lowers EL's cap 30 → 5 under `PRESERVE`; the rows keep `carried_forward(Y+1) = 30`;
      2. weeks later an UNRELATED Manager rejects an UNRELATED year-`Y` request, which fires
         `recompute_carry_forward` (`leave_requests.py:533`) — which re-reads the NEW cap, computes
         `min(5, available(Y)) = 5 ≠ 30`, and drops `accrued(Y+1)` by 25;
      3. `Y+1` is already spent → `set_accrual`'s guard raises a bare `ValueError` → a RAW 500 on the
         Manager's reject. The three Story 2.10 hooks were wired on the premise that `available(Y)`
         only RISES; an out-of-band cap change destroys that premise, and none of them can refuse.
      4. The same change aborts the ENTIRE `run_rollover` batch transaction the next time it runs.

    `carries_forward: true → false` is worse still: it zeroes `carried_forward` in EVERY later year,
    from a path that cannot refuse.

    So a cap or `carries_forward` change runs AD-19's forward-checked recomputation under BOTH
    dispositions. This makes AC6 LITERALLY true — read it again, it carries no disposition qualifier:
    "Given a change to `carry_forward_cap` or `annual_entitlement`, when it commits, then AD-6's
    carry-forward recomputation is triggered explicitly." Neither does AD-6's own rule (SPINE L101).
    (Note architecture §6.3 DOES attach one — "with the disposition RECALCULATE" — and it is the only
    place in any artifact that does. The unqualified reading is the one that holds, because the
    qualified one promises something the schema cannot deliver.)

    The honest residue, stated rather than hidden: for a CAP-ONLY change, `PRESERVE` and `RECALCULATE`
    do the same thing to balances and differ only in what `policy_change` records. The UI says so.
    That is honest. Silently promising to preserve a number that the next unrelated reject will
    overwrite, unguarded, as a 500, is not.

    The alternative — REFUSING `PRESERVE` for a cap change — needs an error code api-contracts does
    not define. It is not invented.
    """
    if any(attribute in changed for attribute in _CAP_ATTRIBUTES):
        return True
    return (
        "annual_entitlement" in changed
        and disposition == vocabulary.DISPOSITION_RECALCULATE
    )


@dataclass(frozen=True)
class LeaveTypeCommandResult:
    """What a Leave Type edit did: the row it wrote, and the recalculation it triggered (AD-19).

    The pair the endpoint answers `200` with — the `HolidayCommandResult` shape
    (`services/holidays.py:107-117`), because the two commands are the same kind of thing: a write
    that may partially refuse. The `recalculation` half is not decoration; AC11 forbids showing the
    Admin an unqualified success for an operation that partially refused, so the summary travels all
    the way to the screen.

    A name-only edit returns an EMPTY summary (`0, 0, []`) — never `None`. One response shape, one
    projection, no optional branch for the caller to forget.
    """

    leave_type: LeaveType
    recalculation: RecalculationSummary


def update_leave_type(
    leave_type_id: uuid.UUID,
    submitted: dict[str, object],
    disposition: object,
) -> LeaveTypeCommandResult:
    """Change a Leave Type's policy, forcing an explicit disposition first (AC2–AC6, FR-06).

    THE STORY'S COMMAND. An Admin edits leave policy, and if the edit would touch balances that
    already exist, they must say WHAT HAPPENS TO THEM. The system never decides on their behalf.

    `submitted` is `model_dump(exclude_unset=True)` from the route — ONLY the keys the client actually
    sent (the `PATCH /me` precedent). That is what keeps "the cap was set to null" distinguishable
    from "the cap was not submitted", which matters: the first is a policy change that triggers the
    gate, the second is not.

    `disposition` is typed `object`, not `str | None` and CERTAINLY not a `Literal` — see the route.
    It is validated HERE, against the two vocabulary constants.

    ONE transaction (AD-3, AD-19). In order:

      1. Refuse any key that is not updatable → `400 FORBIDDEN_FIELD`, before any write.
      2. Resolve which submitted attributes actually CHANGE a value. A value equal to the stored one
         is NOT a change and must not trigger the gate.
      3. THE GATE (AC2): if any CHANGED attribute is balance-affecting and no VALID disposition was
         supplied → `400 POLICY_DISPOSITION_REQUIRED`, and NOTHING IS APPLIED — not the `leave_type`
         row, not a `policy_change` row. Raised before the first write, so "nothing is applied" is a
         property of the code, not of a rollback.
      4. UPDATE the `leave_type` row and `flush()`, so the recalculation reads the NEW policy — the
         `services/holidays.py` discipline exactly.
      5. RECALCULATE, if `_must_recalculate` says to (Landmine 3 — and it is NOT simply
         "disposition == RECALCULATE").
      6. One `policy_change` row PER CHANGED BALANCE-AFFECTING ATTRIBUTE (Open Decision #4), sharing
         one `occurred_at` and one disposition.
      7. Commit, once.

    --- The gate does NOT depend on whether balance rows exist (Open Decision #5) ---

    FR-06 says "balances that already exist", which tempts a gate that skips the disposition when a
    Leave Type has no materialized rows. That Leave Type would then get NO `policy_change` row at all,
    silently skipping AC3 — and it puts a data-dependent branch into a command that is hard enough
    already. So the disposition is required for ANY balance-affecting change, always. The
    recalculation over zero pairs is simply an empty summary.

    A per-pair recalculation refusal does NOT fail this command (AD-19): the edit commits, the
    endpoint answers `200`, and the refused pairs are named in the summary and recorded in
    `admin_review_flag`. That is why there is no `IntegrityError` backstop here and no `try` block at
    all: `code` is not updatable, so there is no `UNIQUE (code)` collision to race, and the
    recalculation's refusals are PREDICTED, never caught (AC5).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
        leave_type = leave_type_repo.get_leave_type(session, leave_type_id)
        if leave_type is None:
            # A `PATCH` of an id that names no row is `404 RESOURCE_NOT_FOUND`, byte-identical to a
            # scope miss (AD-10), reached through `services/authorization` as every other load-or-404
            # does.
            authz.not_found()

        # ---- 1. An unknown or non-updatable key is refused BEFORE anything else -----------------
        forbidden = [key for key in submitted if key not in _UPDATABLE]
        if forbidden:
            raise _forbidden_field(forbidden)

        # ---- 2. What actually CHANGED. A resubmitted identical value is not a change. -----------
        # This is what stops an Admin who re-saves the form unchanged from being asked for a
        # disposition they have no reason to give — and from writing a `policy_change` row recording
        # that nothing happened.
        changed: dict[str, object] = {
            key: value
            for key, value in submitted.items()
            if value != getattr(leave_type, key)
        }
        changed_balance_affecting = [
            key for key in changed if key in _BALANCE_AFFECTING
        ]

        # ---- 3. THE GATE (AC2) — before the first write, so NOTHING is applied -------------------
        # One code for "absent" AND for "present but not one of the two" (Landmine 9): an invalid
        # value would otherwise reach the `CHECK (disposition IN (…))` as a raw 500, which AD-5
        # forbids (the CHECK is a backstop, never a gate).
        valid_disposition = disposition in (
            vocabulary.DISPOSITION_RECALCULATE,
            vocabulary.DISPOSITION_PRESERVE,
        )
        if changed_balance_affecting and not valid_disposition:
            raise _policy_disposition_required(changed_balance_affecting, disposition)

        if not changed:
            # A no-op edit: every submitted value already equals the stored one. Nothing is written,
            # no `policy_change` row is recorded, and the empty summary is returned — the same shape
            # a name-only edit returns, so the route never branches.
            return LeaveTypeCommandResult(
                leave_type=leave_type,
                recalculation=RecalculationSummary(
                    requests_recalculated=0, pairs_recalculated=0, pairs_refused=[]
                ),
            )

        # The old values, captured BEFORE the update — `policy_change.old_value` needs them, and the
        # row is about to be overwritten in place.
        old_values = {key: getattr(leave_type, key) for key in changed}

        # ---- 4. Apply the policy, and FLUSH so the recalculation reads the NEW row ---------------
        leave_type_repo.update_leave_type(
            session, leave_type=leave_type, fields=changed
        )

        # ---- 5. RECALCULATE — under the rule Landmine 3 forced, not simply on RECALCULATE --------
        summary = RecalculationSummary(
            requests_recalculated=0, pairs_recalculated=0, pairs_refused=[]
        )
        if changed_balance_affecting and _must_recalculate(
            changed, str(disposition)
        ):
            # The NEW attribute values, read off the flushed row — never the submitted dict, which
            # holds only the keys that changed.
            summary = recalculation_service.recalculate_for_policy_change(
                session,
                leave_type_id=leave_type.id,
                annual_entitlement=leave_type.annual_entitlement,
                carries_forward=leave_type.carries_forward,
                carry_forward_cap=leave_type.carry_forward_cap,
            )

        # ---- 6. The log — one row per changed BALANCE-AFFECTING attribute (AC3) ------------------
        # A `name` change writes none: `policy_change.disposition` is NOT NULL under a two-value
        # CHECK, and a name change has no disposition to record (Open Decision #4). All rows from one
        # PATCH share one `occurred_at`, which is why the read orders by `(occurred_at DESC, id DESC)`.
        occurred_at = _now()
        for attribute in changed_balance_affecting:
            policy_change_repo.insert_policy_change(
                session,
                leave_type_id=leave_type.id,
                attribute=attribute,
                old_value=_stringify(old_values[attribute]),
                new_value=_stringify(changed[attribute]),
                disposition=str(disposition),
                occurred_at=occurred_at,
            )

        session.commit()
        return LeaveTypeCommandResult(leave_type=leave_type, recalculation=summary)
