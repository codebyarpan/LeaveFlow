"""A leave policy change, with an explicit disposition — against real PostgreSQL (Story 2.12).

Implements the test side of: AC1 (`policy_change` exists, carries NO actor column, and is APPEND-ONLY
— proved LIVE, as the app role, not read off the migration), AC2 (no disposition → `400
POLICY_DISPOSITION_REQUIRED`, and NOTHING is applied), AC3 (one `policy_change` row per changed
balance-affecting attribute), AC4 (`PRESERVE` leaves existing balances alone; only future accruals use
the new value), AC5 (`RECALCULATE` re-derives every materialized year under the forward check, and a
pair it would drive negative is left ENTIRELY unchanged and flagged), AC6 (AD-6's recomputation is
triggered explicitly — and is a provable NO-OP), AC7/AC8 (an Admin reads the log; nobody else does),
AC9/SM-5 (a fourth Leave Type is created, applied for, approved, RE-POLICIED and rolled over with no
code change and no migration). FR-06, AD-5, AD-6, AD-19, AD-20.

--- Real PostgreSQL, because the whole story is about what the database is NOT allowed to decide ---

AC5 says the refusal must be "discovered by the forward check, never by an AD-5 CHECK violation and
never by a caught `ValueError`". That is a claim about WHICH LAYER refuses, and it is only falsifiable
against a database that HAS those CHECKs and those GRANTs. So `leave_balance`'s `available >= 0` CHECK
and the `INSERT, SELECT`-only grant on `policy_change` are both live here, and
`test_the_forward_check_is_what_refuses_not_the_guard` proves the check is LOAD-BEARING by disabling
it and watching the write path blow up instead.

--- The scenario that drives almost every test here (Landmine 1) ---

A NON-CARRYING Leave Type — `carries_forward=False`, which is CL and FL, two of the three seeded types
— whose `annual_entitlement` is LOWERED while a LATER Leave Year is already spent.

That combination is the one the pre-2.12 `project_forward` gets WRONG. `carry_forward_days` returns 0
unconditionally for such a type, and the stored `carried_forward` is already 0, so its fixed-point
`break` fires on the FIRST iteration and the walk exits before checking a single later year. The
projection then answers "not refused", the service applies, and `set_accrual`'s `available >= 0` guard
fires a bare `ValueError` — a raw 500, with every one of Story 2.11's tests still green. The unit test
for that is in `tests/domain/test_recalculation.py`; this file proves the same thing end-to-end,
through the endpoint, against the real CHECKs.

--- Why the years are derived from the clock, never hardcoded ---

Story 2.4's create hooks materialize balances for `date.today().year` and NO OTHER YEAR, so the tests
here build their own `Y + 1` rows explicitly through `balances.set_accrual` — the sole legal writer of
the accrual triple (AD-17). A hardcoded year would silently degrade into a test of the missing-row
path the moment the calendar turned. Same reasoning as Stories 2.10 and 2.11.

--- Teardown runs as the OWNER, and that IS AC1 ---

The app role holds `INSERT` and `SELECT` on `policy_change` and neither `UPDATE` nor `DELETE`, so a
test cannot delete its own policy-change rows through `get_engine()` — the delete is REFUSED. That
refusal is the guarantee working, not a bug. Cleanup is maintenance, and maintenance is the owner's
(`owner_engine`), exactly as Stories 2.9, 2.10 and 2.11 established.
"""

import datetime
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, delete, inspect, select, text
from sqlalchemy.orm import Session

from app.core import security
from app.domain import vocabulary
from app.main import app
from app.repositories.engine import get_engine
from app.repositories.models import (
    AdminReviewFlag,
    AuditEntry,
    Department,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
    PolicyChange,
)
from app.services import balances
from app.services import leave_types as leave_types_service
from app.services import rollover

_KNOWN_PASSWORD = "correct-horse-battery-staple"

_YEAR = datetime.date.today().year
_NEXT_YEAR = _YEAR + 1
# 1 January, so `prorate_entitlement` returns the FULL annual entitlement for every year under test.
# A mid-year joining date would make every expected figure below a second calculation, and would test
# proration rather than the recalculation this story is about (proration has its own DB-free suite).
_JOINING_DATE = datetime.date(_YEAR, 1, 1)

_ENTITLEMENT = 12
_HIGH_CAP = 30

_client = TestClient(app)


class _World:
    """Two Employees, an Admin, a Manager, and TWO Leave Types — one CARRYING, one NOT.

    TWO EMPLOYEES, because the unit of refusal is the (Employee, Leave Type) PAIR: AC5's load-bearing
    clause is that a refused pair is left alone WHILE THE REST OF THE OPERATION COMMITS. A policy
    change edits ONE Leave Type, so the thing that must still commit is ANOTHER EMPLOYEE'S balance in
    that same type. One Employee cannot show that.

    TWO LEAVE TYPES, one `carries_forward=False` and one `True`:

      * `lapsing` is the Landmine 1 type — `carry_forward_days` returns 0 for it unconditionally, so
        the stale fixed-point `break` fires immediately and skips every later year.
      * `carrying` is the control, and the type whose CAP change drives Landmine 3.

    A MANAGER, so the Employees' requests land PENDING and RESERVE (a managerless Employee's
    submission is auto-APPROVED and consumes directly, FR-09) — which is what AC9 and the Landmine 3
    reject-path test need.
    """

    def __init__(
        self,
        suffix: str,
        department_name: str,
        lapsing_id: uuid.UUID,
        carrying_id: uuid.UUID,
        alice_id: uuid.UUID,
        alice_token: str,
        bob_id: uuid.UUID,
        bob_token: str,
        manager_id: uuid.UUID,
        manager_token: str,
        admin_id: uuid.UUID,
        admin_token: str,
    ) -> None:
        self.suffix = suffix
        self.department_name = department_name
        self.lapsing_id = lapsing_id
        self.carrying_id = carrying_id
        self.alice_id = alice_id
        self.alice_token = alice_token
        self.bob_id = bob_id
        self.bob_token = bob_token
        self.manager_id = manager_id
        self.manager_token = manager_token
        self.admin_id = admin_id
        self.admin_token = admin_token

    @property
    def leave_type_ids(self) -> list[uuid.UUID]:
        return [self.lapsing_id, self.carrying_id]


@pytest.fixture
def world(db_connection: Connection, owner_engine: Engine) -> Iterator[_World]:
    """Build the world, and tear it down as the OWNER (AC1 — the app role cannot delete these rows).

    Leave Types are created through the SERVICE so Story 2.4's materialization hook writes every
    Employee a full-entitlement `_YEAR` balance — which is what gives the recalculation something to
    recalculate. Later years are built per-test, because which years exist is the variable under test.
    """
    suffix = uuid.uuid4().hex[:12]
    department_name = f"pol-dept-{suffix}"
    hashed = security.hash_password(_KNOWN_PASSWORD)

    def _employee(
        session: Session,
        department_id: uuid.UUID,
        *,
        label: str,
        role: str,
        manager_id: uuid.UUID | None,
    ) -> uuid.UUID:
        employee = Employee(
            department_id=department_id,
            manager_id=manager_id,
            email=f"pol-{label}-{suffix}@example.com",
            full_name=f"Policy {label}",
            role=role,
            joining_date=_JOINING_DATE,
            is_active=True,
            password_hash=hashed,
        )
        session.add(employee)
        session.flush()
        return employee.id

    with Session(get_engine()) as session:
        department = Department(name=department_name)
        session.add(department)
        session.flush()

        manager_id = _employee(
            session,
            department.id,
            label="mgr",
            role=vocabulary.ROLE_MANAGER,
            manager_id=None,
        )
        alice_id = _employee(
            session,
            department.id,
            label="alice",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        bob_id = _employee(
            session,
            department.id,
            label="bob",
            role=vocabulary.ROLE_EMPLOYEE,
            manager_id=manager_id,
        )
        admin_id = _employee(
            session,
            department.id,
            label="adm",
            role=vocabulary.ROLE_ADMIN,
            manager_id=None,
        )
        session.commit()

    alice_token = security.create_token(str(alice_id), vocabulary.ROLE_EMPLOYEE)
    bob_token = security.create_token(str(bob_id), vocabulary.ROLE_EMPLOYEE)
    manager_token = security.create_token(str(manager_id), vocabulary.ROLE_MANAGER)
    admin_token = security.create_token(str(admin_id), vocabulary.ROLE_ADMIN)

    lapsing_id = leave_types_service.create_leave_type(
        code=f"PL-{suffix}",
        name="Policy Lapsing",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=False,
        carry_forward_cap=None,
        requires_supporting_document=False,
    ).id
    carrying_id = leave_types_service.create_leave_type(
        code=f"PC-{suffix}",
        name="Policy Carrying",
        annual_entitlement=_ENTITLEMENT,
        carries_forward=True,
        carry_forward_cap=_HIGH_CAP,
        requires_supporting_document=False,
    ).id

    try:
        yield _World(
            suffix,
            department_name,
            lapsing_id,
            carrying_id,
            alice_id,
            alice_token,
            bob_id,
            bob_token,
            manager_id,
            manager_token,
            admin_id,
            admin_token,
        )
    finally:
        # The OWNER engine (AD-9/AD-20): the app role can neither UPDATE nor DELETE `policy_change`,
        # `admin_review_flag` or `audit_entry`, so these deletes are REFUSED through `get_engine()` —
        # which is AC1 working, not a bug. Cleanup is maintenance, and maintenance is the owner's.
        #
        # Audit rows MUST go, and not only for tidiness: SM-4's ledger
        # (`test_audit_entries.py`) counts audit rows across the WHOLE database and pins the total at
        # exactly 14. A test that left its own behind would break that count from three files away.
        ids = [lapsing_id, carrying_id]
        employee_ids = [manager_id, alice_id, bob_id, admin_id]
        with Session(owner_engine) as session:
            # ⚠️ Balances and requests are deleted by EMPLOYEE as well as by LEAVE TYPE, and the
            # `run_rollover` tests are why. `run_rollover` materializes `Y+1` for EVERY Employee ×
            # EVERY Leave Type in the database — so this world's Employees end up holding balance rows
            # against the SEEDED Leave Types too, which the FK on `leave_balance.employee_id` will not
            # let us delete an Employee out from under. Deleting only by `leave_type_id` leaves those
            # behind and the Employee delete fails with a ForeignKeyViolation.
            lr_ids = select(LeaveRequest.id).where(
                (LeaveRequest.leave_type_id.in_(ids))
                | (LeaveRequest.employee_id.in_(employee_ids))
            )
            session.execute(delete(AuditEntry).where(AuditEntry.subject_id.in_(lr_ids)))
            session.execute(
                delete(PolicyChange).where(PolicyChange.leave_type_id.in_(ids))
            )
            session.execute(
                delete(AdminReviewFlag).where(
                    (AdminReviewFlag.leave_type_id.in_(ids))
                    | (AdminReviewFlag.employee_id.in_(employee_ids))
                )
            )
            # Story 3.4 (Landmine 16): notification rows FIRST. Every submission/decision through
            # the API now writes one, and it FK-references BOTH `leave_request` and `employee` with
            # NO `ON DELETE` clause (by decision — an Employee is deactivated, never deleted; a
            # Leave Request has no DELETE endpoint). So deleting either parent first raises
            # `ForeignKeyViolation` and errors this whole module. Deleting them explicitly, ahead of
            # their parents, is the sanctioned fix — NOT granting the app role `DELETE` (this block
            # already runs as the owner) and NOT `ON DELETE CASCADE` (it would signal a deletion
            # path the product forbids). Every recipient is one of this fixture's own Employees.
            session.execute(
                delete(Notification).where(
                    Notification.recipient_employee_id.in_(
                        select(Employee.id).where(Employee.email.like(f"%{suffix}%"))
                    )
                )
            )
            session.execute(
                delete(LeaveRequest).where(
                    (LeaveRequest.leave_type_id.in_(ids))
                    | (LeaveRequest.employee_id.in_(employee_ids))
                )
            )
            session.execute(
                delete(LeaveBalance).where(
                    (LeaveBalance.leave_type_id.in_(ids))
                    | (LeaveBalance.employee_id.in_(employee_ids))
                )
            )
            session.execute(delete(Employee).where(Employee.email.like(f"%{suffix}%")))
            session.execute(delete(LeaveType).where(LeaveType.id.in_(ids)))
            session.execute(delete(Department).where(Department.name == department_name))
            session.commit()


# --- helpers ---------------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _patch(
    world: _World,
    leave_type_id: uuid.UUID,
    body: dict,  # type: ignore[type-arg]
    *,
    token: str | None = None,
):  # type: ignore[no-untyped-def]
    """`PATCH /leave-types/<id>` as the Admin (unless another token is given). Returns the response."""
    return _client.patch(
        f"/api/v1/leave-types/{leave_type_id}",
        json=body,
        headers=_auth(token or world.admin_token),
    )


def _materialize(
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    leave_year: int,
    *,
    prorated: int,
    carried: int,
    basis: int,
    consumed: int = 0,
    reserved: int = 0,
) -> None:
    """Build one balance year exactly, through the SANCTIONED writers only (AD-17).

    `set_accrual` for the accrual triple, then `consume_direct`/`reserve` for the spent and committed
    halves — never a raw UPDATE. A test that wrote these columns directly could construct a state the
    application cannot reach, and would then be testing a database that does not exist.
    """
    with Session(get_engine()) as session:
        balances.set_accrual(
            session,
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            leave_year=leave_year,
            prorated_entitlement=prorated,
            carried_forward=carried,
            entitlement_basis=basis,
        )
        if consumed:
            balances.consume_direct(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                days=consumed,
            )
        if reserved:
            balances.reserve(
                session,
                employee_id=employee_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                days=reserved,
            )
        session.commit()


def _snapshot(
    leave_type_ids: list[uuid.UUID],
) -> dict[tuple[uuid.UUID, uuid.UUID, int], tuple[int, int, int, int, int, int]]:
    """Every balance row for these Leave Types, as plain comparable numbers.

    Used for the "byte-unchanged" assertions that carry half of AC2 ("nothing is applied") and all of
    AC4 (`PRESERVE` writes no balance row) and AC6 (the recomputation is a no-op). Comparing whole
    dicts means a test cannot pass by checking only the column it happened to think of.
    """
    with Session(get_engine()) as session:
        rows = session.execute(
            select(
                LeaveBalance.employee_id,
                LeaveBalance.leave_type_id,
                LeaveBalance.leave_year,
                LeaveBalance.accrued,
                LeaveBalance.prorated_entitlement,
                LeaveBalance.carried_forward,
                LeaveBalance.entitlement_basis,
                LeaveBalance.reserved,
                LeaveBalance.consumed,
            ).where(LeaveBalance.leave_type_id.in_(leave_type_ids))
        ).all()
    return {
        (row[0], row[1], row[2]): (row[3], row[4], row[5], row[6], row[7], row[8])
        for row in rows
    }


def _balance(
    employee_id: uuid.UUID, leave_type_id: uuid.UUID, leave_year: int
) -> LeaveBalance:
    with Session(get_engine()) as session:
        row = session.scalars(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.leave_year == leave_year,
            )
        ).one()
        session.expunge(row)
        return row


def _policy_changes(leave_type_id: uuid.UUID) -> list[PolicyChange]:
    with Session(get_engine()) as session:
        rows = list(
            session.scalars(
                select(PolicyChange)
                .where(PolicyChange.leave_type_id == leave_type_id)
                .order_by(PolicyChange.attribute)
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def _flags(leave_type_id: uuid.UUID) -> list[AdminReviewFlag]:
    with Session(get_engine()) as session:
        rows = list(
            session.scalars(
                select(AdminReviewFlag).where(
                    AdminReviewFlag.leave_type_id == leave_type_id
                )
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def _leave_type(leave_type_id: uuid.UUID) -> LeaveType:
    with Session(get_engine()) as session:
        row = session.get(LeaveType, leave_type_id)
        assert row is not None
        session.expunge(row)
        return row


def _spend_a_later_year(world: _World, employee_id: uuid.UUID, consumed: int) -> None:
    """Give `employee_id` a `_NEXT_YEAR` row on the LAPSING type with `consumed` days already spent.

    This is the Landmine 1 setup: a non-carrying type whose later year is ALREADY SPENT. Lower the
    entitlement under it and the later year goes negative — through its OWN re-proration, with its
    `carried_forward` never moving off zero, which is exactly the case the stale fixed-point `break`
    skips.
    """
    _materialize(
        employee_id,
        world.lapsing_id,
        _NEXT_YEAR,
        prorated=_ENTITLEMENT,
        carried=0,
        basis=_ENTITLEMENT,
        consumed=consumed,
    )


# ===============================================================================================
# AC1 — the table, its CHECK, its missing actor column, and its append-only GRANT
# ===============================================================================================


class TestTheTableIsWhatAC1Says:
    def test_policy_change_carries_no_actor_column_by_decision(
        self, db_connection: Connection
    ) -> None:
        """AC1: "it carries NO actor column, by decision". A testable absence, so it is tested.

        PRD §1 promises attribution for LEAVE REQUEST state changes — that is `audit_entry`'s job, and
        `audit_entry` has `actor_type`/`actor_id` for exactly that reason. It promises none for a
        configuration change, and the ERD names no actor column here. A later story that "helpfully"
        adds one fails this test, which is the point: the absence is a decision, and a decision that
        nothing enforces is a decision that will be quietly reversed.
        """
        columns = {c["name"] for c in inspect(db_connection).get_columns("policy_change")}

        assert columns == {
            "id",
            "leave_type_id",
            "attribute",
            "old_value",
            "new_value",
            "disposition",
            "occurred_at",
        }
        assert not [name for name in columns if "actor" in name]

    def test_the_disposition_check_admits_exactly_the_two_values(
        self, world: _World
    ) -> None:
        """AC1's one non-negotiable constraint — asserted as the BACKSTOP it is (AD-5).

        The gate is the service, which refuses an invalid disposition with a typed `400` long before a
        row is built (see `TestTheDispositionGate`). This proves the backstop is nonetheless armed: a
        third value inserted directly is refused by PostgreSQL.
        """
        with Session(get_engine()) as session:
            # The CHECK fires on the INSERT itself, not at commit — it is not deferrable, and that is
            # the point: an invalid disposition can never be present even momentarily.
            with pytest.raises(Exception) as refused:
                session.execute(
                    text(
                        "INSERT INTO policy_change "
                        "(leave_type_id, attribute, old_value, new_value, disposition, occurred_at) "
                        "VALUES (:lt, 'annual_entitlement', '12', '2', 'MAYBE', now())"
                    ),
                    {"lt": world.lapsing_id},
                )
            session.rollback()

        assert "policy_change_disposition_check" in str(refused.value)

    def test_the_app_role_may_insert_and_select_but_never_update_or_delete(
        self, world: _World
    ) -> None:
        """AC1/AD-9/NFR-09: append-only is a GRANT, and it is proved LIVE as the role the api uses.

        Not read off the migration file — asserted against the running database, as the application's
        own non-owner role. `0008` deliberately issued no `ALTER DEFAULT PRIVILEGES`, so this table
        inherits nothing and `0011` grants for itself: `INSERT, SELECT`, and neither of the other two.

        A policy change is the record of WHY a balance is the number it is. If it could be rewritten,
        the justification for a balance could be rewritten — which is PRD §1's "wrong figure that will
        be believed", one level up.
        """
        # INSERT and SELECT: granted.
        with Session(get_engine()) as session:
            session.execute(
                text(
                    "INSERT INTO policy_change "
                    "(leave_type_id, attribute, old_value, new_value, disposition, occurred_at) "
                    "VALUES (:lt, 'annual_entitlement', '12', '2', :d, now())"
                ),
                {"lt": world.lapsing_id, "d": vocabulary.DISPOSITION_PRESERVE},
            )
            session.commit()

        assert len(_policy_changes(world.lapsing_id)) == 1

        # UPDATE: refused by the database.
        with Session(get_engine()) as session:
            with pytest.raises(Exception) as no_update:
                session.execute(
                    text("UPDATE policy_change SET new_value = '99' WHERE leave_type_id = :lt"),
                    {"lt": world.lapsing_id},
                )
                session.commit()
        assert isinstance(no_update.value.orig, psycopg.errors.InsufficientPrivilege)  # type: ignore[attr-defined]

        # DELETE: refused by the database.
        with Session(get_engine()) as session:
            with pytest.raises(Exception) as no_delete:
                session.execute(
                    text("DELETE FROM policy_change WHERE leave_type_id = :lt"),
                    {"lt": world.lapsing_id},
                )
                session.commit()
        assert isinstance(no_delete.value.orig, psycopg.errors.InsufficientPrivilege)  # type: ignore[attr-defined]

        # And it is still there, unaltered — the two refusals above changed nothing.
        rows = _policy_changes(world.lapsing_id)
        assert len(rows) == 1
        assert rows[0].new_value == "2"


# ===============================================================================================
# AC2 — the gate. No disposition, no change: NOTHING is applied.
# ===============================================================================================


class TestTheDispositionGate:
    def test_a_balance_affecting_change_without_a_disposition_applies_nothing(
        self, world: _World
    ) -> None:
        """AC2, both halves: `400 POLICY_DISPOSITION_REQUIRED`, AND nothing is applied.

        The second half is the one that is easy to leave untested and easy to get wrong. "Nothing is
        applied" means the `leave_type` row is untouched AND no `policy_change` row exists AND every
        balance row is byte-identical — which is a property of the gate raising BEFORE the first
        write, not of a rollback tidying up afterwards.
        """
        before = _snapshot(world.leave_type_ids)

        response = _patch(world, world.lapsing_id, {"annual_entitlement": 2})

        assert response.status_code == 400, response.text
        body = response.json()
        assert body["code"] == vocabulary.POLICY_DISPOSITION_REQUIRED
        # NFR-17: the refusal is ACTIONABLE — it names what forced the choice and what is accepted.
        assert body["details"]["attributes"] == ["annual_entitlement"]
        assert set(body["details"]["accepted"]) == {
            vocabulary.DISPOSITION_RECALCULATE,
            vocabulary.DISPOSITION_PRESERVE,
        }

        assert _leave_type(world.lapsing_id).annual_entitlement == _ENTITLEMENT
        assert _policy_changes(world.lapsing_id) == []
        assert _snapshot(world.leave_type_ids) == before

    def test_an_invalid_disposition_is_the_same_400_and_never_a_422_or_a_500(
        self, world: _World
    ) -> None:
        """Landmine 9. `"FOO"` is refused by the SERVICE, inside the envelope — not by Pydantic, not
        by the CHECK.

        Three ways this could have gone wrong, and each ships green in a naive implementation:

          * typed as a Pydantic `Literal`, it would be a bare `422` OUTSIDE the
            `{code,message,details}` envelope (NFR-17);
          * typed as an unvalidated `str`, it would reach `CHECK (disposition IN (…))` and fire a RAW
            500 — an AD-5 violation, because the CHECK is a backstop and never a gate;
          * and a `Literal` cannot even be written here: `test_vocabulary_literals.py` AST-forbids the
            two values anywhere under `app/`.

        One code covers "absent" and "not one of the two", because api-contracts defines exactly one
        and a second must not be invented.
        """
        before = _snapshot(world.leave_type_ids)

        response = _patch(
            world, world.lapsing_id, {"annual_entitlement": 2, "disposition": "FOO"}
        )

        assert response.status_code == 400, response.text
        assert response.json()["code"] == vocabulary.POLICY_DISPOSITION_REQUIRED
        assert response.json()["details"]["supplied"] == "FOO"
        assert _leave_type(world.lapsing_id).annual_entitlement == _ENTITLEMENT
        assert _policy_changes(world.lapsing_id) == []
        assert _snapshot(world.leave_type_ids) == before

    def test_a_name_only_edit_needs_no_disposition_and_touches_no_balance(
        self, world: _World
    ) -> None:
        """The gate is scoped to BALANCE-AFFECTING attributes, and `name` is not one.

        A rename cannot move a number that already exists, so demanding a disposition for it would be
        asking a question with no meaning — and would write a `policy_change` row recording a
        disposition that governed nothing. `200`, no log row, no balance touched, and an EMPTY summary
        (never `null` — one response shape, no optional branch for the client to forget).
        """
        before = _snapshot(world.leave_type_ids)

        response = _patch(world, world.lapsing_id, {"name": "Renamed Policy"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["leave_type"]["name"] == "Renamed Policy"
        assert body["recalculation"] == {
            "requests_recalculated": 0,
            "pairs_recalculated": 0,
            "pairs_refused": [],
        }
        assert _policy_changes(world.lapsing_id) == []
        assert _snapshot(world.leave_type_ids) == before

    def test_resubmitting_an_identical_value_is_not_a_change(self, world: _World) -> None:
        """A value equal to the stored one is NOT a change, so it does not trigger the gate.

        An Admin who opens the form and saves it unchanged must not be interrogated about a
        disposition for an edit that moves nothing — nor have a `policy_change` row recorded saying
        that nothing happened.
        """
        response = _patch(
            world, world.lapsing_id, {"annual_entitlement": _ENTITLEMENT}
        )

        assert response.status_code == 200, response.text
        assert _policy_changes(world.lapsing_id) == []

    def test_a_forbidden_field_is_refused_inside_the_envelope(self, world: _World) -> None:
        """`code` is a Leave Type's IDENTITY, not a policy attribute — and no AC grants an edit path.

        `extra="allow"` on the request model means the unknown key REACHES the service rather than
        triggering a bare Pydantic `422` outside the envelope; the service refuses it with the code
        Story 1.8 coined for exactly this shape (the actor owns the resource; the domain refuses the
        CONTENT).
        """
        response = _patch(world, world.lapsing_id, {"code": "STOLEN"})

        assert response.status_code == 400, response.text
        assert response.json()["code"] == vocabulary.FORBIDDEN_FIELD
        assert response.json()["details"]["fields"] == ["code"]

    def test_a_negative_entitlement_is_refused_before_it_reaches_proration(
        self, world: _World
    ) -> None:
        """Open Decision #3, closing `deferred-work.md:44` — reachable ON AN ADMIN'S EDIT since today.

        A negative `annual_entitlement` reaches `prorate_entitlement` and fires a raw 500. On CREATE
        that was a curiosity; on `PATCH … RECALCULATE` it is a 500 against live balances. `Field(ge=0)`
        makes it a `422` — and a `422` is the honest code here: a malformed NUMBER is a schema-level
        fault, unlike `FORBIDDEN_FIELD`, which is a domain rule about authority.
        """
        response = _patch(
            world,
            world.lapsing_id,
            {
                "annual_entitlement": -5,
                "disposition": vocabulary.DISPOSITION_RECALCULATE,
            },
        )

        assert response.status_code == 422, response.text
        assert _leave_type(world.lapsing_id).annual_entitlement == _ENTITLEMENT

    def test_a_non_admin_never_reaches_the_edit(self, world: _World) -> None:
        """AD-14: the role gate is a dependency, so it runs BEFORE the body and no row is written."""
        for token in (world.alice_token, world.manager_token):
            response = _patch(
                world,
                world.lapsing_id,
                {
                    "annual_entitlement": 2,
                    "disposition": vocabulary.DISPOSITION_RECALCULATE,
                },
                token=token,
            )
            assert response.status_code == 403, response.text
            assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED

        assert _leave_type(world.lapsing_id).annual_entitlement == _ENTITLEMENT
        assert _policy_changes(world.lapsing_id) == []


# ===============================================================================================
# AC3 — the log: one row per changed balance-affecting attribute
# ===============================================================================================


class TestThePolicyChangeLog:
    def test_one_row_per_changed_balance_affecting_attribute(self, world: _World) -> None:
        """AC3, Open Decision #4. The table is SINGULAR, so two attributes are two rows.

        `attribute`, `old_value`, `new_value` — one triple per row. A `PATCH` moving both
        `annual_entitlement` and `carry_forward_cap` therefore writes TWO rows, sharing ONE
        `occurred_at` and ONE disposition. That shared timestamp is exactly why the read orders by
        `(occurred_at DESC, id DESC)` — without the `id` tiebreak, a paginated read of these two rows
        could show one twice and skip the other.

        The `name` moves too, and writes NO row: `disposition` is NOT NULL under a two-value CHECK, and
        a rename has no disposition to record.
        """
        response = _patch(
            world,
            world.carrying_id,
            {
                "name": "Renamed And Repolicied",
                "annual_entitlement": 15,
                "carry_forward_cap": 10,
                "disposition": vocabulary.DISPOSITION_RECALCULATE,
            },
        )
        assert response.status_code == 200, response.text

        rows = _policy_changes(world.carrying_id)  # ordered by `attribute`

        assert [row.attribute for row in rows] == [
            "annual_entitlement",
            "carry_forward_cap",
        ]
        assert (rows[0].old_value, rows[0].new_value) == (str(_ENTITLEMENT), "15")
        assert (rows[1].old_value, rows[1].new_value) == (str(_HIGH_CAP), "10")
        assert {row.disposition for row in rows} == {vocabulary.DISPOSITION_RECALCULATE}
        # ONE moment for the whole PATCH — the tie the `id` ordering exists to break.
        assert rows[0].occurred_at == rows[1].occurred_at
        assert rows[0].occurred_at.tzinfo is not None

    def test_a_removed_cap_is_recorded_as_null_and_means_uncapped(
        self, world: _World
    ) -> None:
        """Open Decisions #6 and #12. `null` is UNCAPPED, not zero — and the log says which.

        `old_value`/`new_value` are TEXT because one column pair carries an int, a NULLABLE int and a
        bool. `None` is rendered as the literal string `"null"`, so the columns stay NOT NULL and "the
        cap was REMOVED" is a different recorded value from "there never was a cap".

        And REMOVING a cap means UNCAPPED (Story 2.10's Open Decision #2, inherited free through
        `carry_forward_days`) — never a cap of zero, which is a real and very different policy.
        """
        response = _patch(
            world,
            world.carrying_id,
            {
                "carry_forward_cap": None,
                "disposition": vocabulary.DISPOSITION_PRESERVE,
            },
        )
        assert response.status_code == 200, response.text

        rows = _policy_changes(world.carrying_id)
        assert len(rows) == 1
        assert rows[0].attribute == "carry_forward_cap"
        assert rows[0].old_value == str(_HIGH_CAP)
        assert rows[0].new_value == "null"
        assert _leave_type(world.carrying_id).carry_forward_cap is None


# ===============================================================================================
# AC4 — PRESERVE. And Landmine 3: what PRESERVE cannot preserve.
# ===============================================================================================


class TestPreserve:
    def test_preserve_writes_no_balance_row_and_only_future_accruals_use_the_new_value(
        self, world: _World
    ) -> None:
        """AC4. For an `annual_entitlement` change, `PRESERVE` is a genuine no-op on balances.

        `entitlement_basis` FREEZES the annual entitlement on the row — that is the whole reason the
        column exists. And future accruals pick the new value up FOR FREE, because `run_rollover`
        re-prorates `Y+1` from the LIVE `leave_type.annual_entitlement` at every boundary. So "only
        future accruals use the new value" is delivered by updating the `leave_type` row and STOPPING.

        The second half of the test is what makes the first half mean something: the balances are
        byte-identical, AND the next rollover materializes `Y+1` at the NEW figure. Without it,
        "PRESERVE writes nothing" would be indistinguishable from "PRESERVE does nothing at all".
        """
        before = _snapshot(world.leave_type_ids)

        response = _patch(
            world,
            world.lapsing_id,
            {"annual_entitlement": 20, "disposition": vocabulary.DISPOSITION_PRESERVE},
        )
        assert response.status_code == 200, response.text
        assert response.json()["recalculation"]["pairs_recalculated"] == 0

        # Existing balances: untouched, every column, every row.
        assert _snapshot(world.leave_type_ids) == before
        # The policy itself: changed.
        assert _leave_type(world.lapsing_id).annual_entitlement == 20
        # And the old basis is still frozen on the row — that is what "as accrued" MEANS.
        assert _balance(world.alice_id, world.lapsing_id, _YEAR).entitlement_basis == (
            _ENTITLEMENT
        )

        # Only FUTURE accruals use the new value. Roll the year and watch `Y+1` arrive at 20.
        rollover.run_rollover(_YEAR)

        next_year = _balance(world.alice_id, world.lapsing_id, _NEXT_YEAR)
        assert next_year.prorated_entitlement == 20
        assert next_year.entitlement_basis == 20
        # The year that was preserved is still preserved — the rollover did not backfill it.
        assert _balance(world.alice_id, world.lapsing_id, _YEAR).prorated_entitlement == (
            _ENTITLEMENT
        )

    def test_preserving_a_lowered_cap_re_derives_carry_forward_now_instead_of_leaving_it_stale(
        self, world: _World
    ) -> None:
        """⚠️ LANDMINE 3. `PRESERVE` cannot preserve a cap, so it does not pretend to.

        THERE IS NO `carry_forward_cap_basis`. `entitlement_basis` freezes the annual entitlement;
        NOTHING freezes the cap. Every downstream trigger re-reads it LIVE off the `leave_type` row —
        `recompute_carry_forward` and `run_rollover` both — and NEITHER HAS A FORWARD CHECK.

        So under the naive reading ("PRESERVE writes nothing"), lowering the cap 30 → 5 leaves
        `carried_forward(Y+1)` sitting at 12 — a number the new policy says is impossible. The
        Employee's dashboard shows 5 PHANTOM DAYS they do not have, and goes on showing them until
        some unrelated transaction happens to fire the recomputation and silently corrects it. PRD §1:
        "a leave balance that is wrong is worse than a leave balance that is absent, because it will be
        believed."

        The resolution: a cap or `carries_forward` change runs the FORWARD-CHECKED recomputation under
        BOTH dispositions. `PRESERVE` preserves what actually has a basis — the proration
        (`entitlement_basis`) — and nothing else. That is what makes AC6 literally true (it carries no
        disposition qualifier), and it is the only reading under which `PRESERVE` is not a promise the
        system cannot keep.

        This test pins that: the cap decrease re-derives `carried_forward` IMMEDIATELY, under
        `PRESERVE`, guarded by the forward check — and a later unrelated reject is then a clean `200`
        against an already-correct balance. Against the naive implementation the first assertion fails
        with `12 != 5`, which is exactly the phantom days.

        ⚠️ It does NOT claim the delayed 500 is impossible in general. For a pair that CANNOT absorb
        the new cap, it is still reachable — see
        `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject` below, which is this
        story's one unresolved defect and is raised to the reviewer as such.
        """
        # Alice, year Y+1: carrying the full 12 forward, with 11 of the resulting 24 already spent.
        # 11 is the load-bearing number: under the NEW cap the year re-derives to `12 + 5 = 17`
        # accrued, which still covers 11 — so this pair CAN absorb the decrease, and the forward check
        # applies it rather than refusing.
        _materialize(
            world.alice_id,
            world.carrying_id,
            _NEXT_YEAR,
            prorated=_ENTITLEMENT,
            carried=_ENTITLEMENT,
            basis=_ENTITLEMENT,
            consumed=11,
        )

        # A year-Y PENDING request for Alice — the "unrelated" one the Manager will reject later. It
        # reserves 2 days, so `available(Y)` is 10.
        start = _next_monday()
        request_id = _submit(
            world,
            world.carrying_id,
            world.alice_id,
            world.alice_token,
            start,
            start + datetime.timedelta(days=1),
        )

        # Lower the cap 30 → 5, under PRESERVE.
        response = _patch(
            world,
            world.carrying_id,
            {"carry_forward_cap": 5, "disposition": vocabulary.DISPOSITION_PRESERVE},
        )
        assert response.status_code == 200, response.text
        assert response.json()["recalculation"]["pairs_refused"] == []

        # THE ASSERTION THIS TEST EXISTS FOR — AC6, unqualified. The recomputation RAN, under
        # PRESERVE, because a cap has no basis to preserve. `carried_forward(Y+1)` is now
        # `min(5, available(Y))`, re-derived under the forward check. Naive PRESERVE leaves it at 12,
        # and this fails with `12 != 5`: five days the Employee can see and cannot take.
        assert _balance(world.alice_id, world.carrying_id, _NEXT_YEAR).carried_forward == 5

        # The proration IS preserved, though — that is what has a basis, and `PRESERVE` still means
        # something. Only the carry-forward moved.
        preserved = _balance(world.alice_id, world.carrying_id, _NEXT_YEAR)
        assert preserved.prorated_entitlement == _ENTITLEMENT
        assert preserved.entitlement_basis == _ENTITLEMENT

        # And the later unrelated reject is clean, against a balance that is already correct.
        rejected = _client.post(
            f"/api/v1/leave-requests/{request_id}/reject",
            headers=_auth(world.manager_token),
        )
        assert rejected.status_code == 200, rejected.text

        for year in (_YEAR, _NEXT_YEAR):
            row = _balance(world.alice_id, world.carrying_id, year)
            assert row.accrued - row.consumed - row.reserved >= 0
            assert row.accrued == row.prorated_entitlement + row.carried_forward

    def test_a_refused_pair_with_a_stale_cap_is_flagged_not_500(
        self, world: _World
    ) -> None:
        """✅ THE DEFECT STORY 2.12 SHIPPED, NOW FIXED — Story 3.4, Task 11.

        This REPLACES `test_a_refused_pair_still_carries_a_stale_cap_into_an_unrelated_reject`, which
        asserted a RAW 500 and passed because the bug was real. `deferred-work.md:74` said in advance:
        *"if that test ever fails, someone fixed the bug."* Someone did, so it is replaced rather than
        quietly deleted, and this test pins the NEW, correct behaviour on the same scenario.

        --- The bug that was ---

        `carry_forward_cap` is a LIVE, GLOBAL input to `carry_forward_days`. A pair the forward check
        REFUSES is left holding a `carried_forward` the NEW policy says is impossible, and the next
        trigger to fire `recompute_carry_forward` on it tried to LOWER it — from a code path that had
        no forward check and whose only backstop was `set_accrual`'s bare `ValueError`. An unrelated
        Manager, rejecting an unrelated request, got a raw 500 (and `run_rollover` aborted its whole
        batch on the same row).

        --- What happens now ---

        `rollover.recompute_carry_forward` is FORWARD-CHECKED (Story 3.4, Task 11). It projects the
        walk with `project_forward` BEFORE its first write; when the projection refuses it writes NO
        balance and appends ONE `admin_review_flag` instead. **The reject still COMMITS**: a Manager is
        never refused, and never 500'd, over a carry-forward artifact in a later year that has nothing
        to do with her decision. The unreconcilable balance goes to an Admin.

        Both of that fix's halves are visible here — and note the FIRST one, which is the AD-6 hole
        itself: the submission below now recomputes carry-forward, so `carried_forward(Y+1)` is
        RE-DERIVED at submit time (12 → 10) instead of silently going stale-high. That is Task 11's
        primary mandate; the no-500-on-reject below is the second defect it closes for free, because
        both had one root cause — this function was unguarded.
        """
        # 20 of 24 spent in Y+1 — beyond what the new cap can support (`12 + 5 = 17`).
        _materialize(
            world.alice_id,
            world.carrying_id,
            _NEXT_YEAR,
            prorated=_ENTITLEMENT,
            carried=_ENTITLEMENT,
            basis=_ENTITLEMENT,
            consumed=20,
        )
        start = _next_monday()
        request_id = _submit(
            world,
            world.carrying_id,
            world.alice_id,
            world.alice_token,
            start,
            start + datetime.timedelta(days=1),
        )

        # 🆕 AD-6, CLOSED. The submission reserved 2 days, so `available(Y)` fell 12 → 10, and the
        # submit-side recompute (Story 3.4, Task 11) RE-DERIVED `carried_forward(Y+1)` to match:
        # `accrued(Y+1) = 12 + 10 = 22` against 20 consumed, so the projection PASSED and the write
        # went through. Before Task 11 this stayed at a stale-high 12 and nothing ever corrected it.
        assert (
            _balance(world.alice_id, world.carrying_id, _NEXT_YEAR).carried_forward == 10
        )
        # The submission itself was never at risk — it committed, and raised NO flag, because its
        # recompute succeeded.
        assert len(_flags(world.carrying_id)) == 0

        # The cap decrease. The pair is REFUSED and FLAGGED — AD-19 working exactly as specified.
        response = _patch(
            world,
            world.carrying_id,
            {"carry_forward_cap": 5, "disposition": vocabulary.DISPOSITION_PRESERVE},
        )
        assert response.status_code == 200, response.text
        refused = response.json()["recalculation"]["pairs_refused"]
        assert len(refused) == 1
        assert refused[0]["employee_id"] == str(world.alice_id)
        assert len(_flags(world.carrying_id)) == 1

        # Left entirely unchanged, as AD-19 promises — and therefore holding a carry-forward the new
        # cap cannot justify (`min(5, 10) = 5`, and `12 + 5 = 17 < 20` consumed).
        assert (
            _balance(world.alice_id, world.carrying_id, _NEXT_YEAR).carried_forward == 10
        )

        # ✅ AND HERE IS THE FIX. The unrelated Manager's reject SUCCEEDS — 200, not a raw 500.
        reject = _client.post(
            f"/api/v1/leave-requests/{request_id}/reject",
            headers=_auth(world.manager_token),
        )
        assert reject.status_code == 200, reject.text
        assert reject.json()["status"] == vocabulary.STATUS_REJECTED

        # The reject's own recompute could not reconcile the stale cap either — so it too wrote no
        # balance and raised a SECOND flag, this one stamped with the cause of the event that hit it.
        flags = _flags(world.carrying_id)
        assert len(flags) == 2
        assert [f.cause for f in flags].count(
            vocabulary.CAUSE_TRANSITION_RECALCULATION
        ) == 1

        # The balance is STILL untouched — the refusal writes nothing, which is exactly what makes it
        # safe to run on a path that must not fail.
        assert (
            _balance(world.alice_id, world.carrying_id, _NEXT_YEAR).carried_forward == 10
        )

    def test_preserve_still_records_the_disposition_it_was_given(
        self, world: _World
    ) -> None:
        """The honest residue, asserted (Open Decision #1).

        For a CAP-ONLY change, `PRESERVE` and `RECALCULATE` do the same thing to balances and differ
        ONLY in what `policy_change` records. That is stated in the UI copy rather than hidden, and it
        is stated here too: the Admin's choice is still recorded faithfully, even where the two
        choices converge.
        """
        _patch(
            world,
            world.carrying_id,
            {"carry_forward_cap": 5, "disposition": vocabulary.DISPOSITION_PRESERVE},
        )

        rows = _policy_changes(world.carrying_id)
        assert len(rows) == 1
        assert rows[0].disposition == vocabulary.DISPOSITION_PRESERVE


# ===============================================================================================
# AC5 — RECALCULATE, the forward check, and the per-pair refusal
# ===============================================================================================


class TestRecalculate:
    def test_every_materialized_year_is_re_derived(self, world: _World) -> None:
        """AC5, the happy path. `accrued`, `prorated_entitlement`, `carried_forward` and
        `entitlement_basis` move in EVERY materialized year — not just the current one.

        This is Landmine 2 in assertion form. `recompute_carry_forward` PRESERVES proration by design,
        so a service that leaned on it to propagate upward would leave `Y+1` on the OLD
        `prorated_entitlement` and the OLD `entitlement_basis` — the policy change applying to one year
        and silently not to the next, which is a wrong figure that would be believed.
        """
        _materialize(
            world.alice_id,
            world.carrying_id,
            _NEXT_YEAR,
            prorated=_ENTITLEMENT,
            carried=_ENTITLEMENT,
            basis=_ENTITLEMENT,
        )

        response = _patch(
            world,
            world.carrying_id,
            {
                "annual_entitlement": 20,
                "disposition": vocabulary.DISPOSITION_RECALCULATE,
            },
        )
        assert response.status_code == 200, response.text
        # A policy change touches NO Leave Request — `leave_days` is a function of the calendar, not
        # of entitlement (AD-18). Always 0, and not a stub.
        assert response.json()["recalculation"]["requests_recalculated"] == 0
        assert response.json()["recalculation"]["pairs_refused"] == []

        this_year = _balance(world.alice_id, world.carrying_id, _YEAR)
        next_year = _balance(world.alice_id, world.carrying_id, _NEXT_YEAR)

        # Year Y: re-prorated to the new annual entitlement, and the basis OVERWRITTEN with it
        # (Open Decision #8 — AC5's "re-derived from `entitlement_basis`" read literally is circular;
        # the operative meaning is that RECALCULATE re-derives from the NEW annual entitlement and
        # writes it as the new basis).
        assert this_year.prorated_entitlement == 20
        assert this_year.entitlement_basis == 20
        assert this_year.carried_forward == 0  # the lowest year: nothing below to carry from
        assert this_year.accrued == 20

        # Year Y+1: ALSO re-prorated — the half `recompute_carry_forward` would have left behind —
        # and its carry-forward re-derived from Y's new Available (20, under a cap of 30).
        assert next_year.prorated_entitlement == 20
        assert next_year.entitlement_basis == 20
        assert next_year.carried_forward == 20
        assert next_year.accrued == 40

        # The non-deferrable equality CHECK, restated as a property of every row we touched.
        for row in (this_year, next_year):
            assert row.accrued == row.prorated_entitlement + row.carried_forward

    def test_a_lapsing_type_refuses_the_pair_at_the_later_year_and_commits_the_rest(
        self, world: _World
    ) -> None:
        """⚠️ LANDMINE 1, end-to-end. The case today's `project_forward` would wave through.

        A NON-CARRYING type whose entitlement is LOWERED while a later year is ALREADY SPENT.
        `carry_forward_days` returns 0 for it unconditionally and the stored `carried_forward` is
        already 0, so the pre-2.12 fixed-point `break` fires on the FIRST iteration and never checks
        `Y+1` at all. The projection would answer "not refused", `set_accrual`'s guard would fire a
        bare `ValueError`, and the Admin would get a raw 500.

        Here it must instead be a clean per-pair REFUSAL (AD-19):

          * ALICE (whose `Y+1` is spent) is left ENTIRELY unchanged — every column, every year;
          * BOB (whose `Y+1` is not) is recalculated normally, IN THE SAME OPERATION;
          * one `admin_review_flag` names Alice, with `CAUSE_POLICY_RECALCULATION`, at the year the
            refusal was DISCOVERED (`Y+1`, not the year that was edited — Open Decision #7);
          * the endpoint answers `200` with a summary, NOT an error;
          * and Alice's OTHER Leave Type is untouched, because a policy change edits one type.
        """
        _spend_a_later_year(world, world.alice_id, consumed=8)
        # Bob gets a later year too, but an UNSPENT one — so the same operation must succeed for him.
        _materialize(
            world.bob_id,
            world.lapsing_id,
            _NEXT_YEAR,
            prorated=_ENTITLEMENT,
            carried=0,
            basis=_ENTITLEMENT,
        )

        alice_before = {
            year: _balance(world.alice_id, world.lapsing_id, year)
            for year in (_YEAR, _NEXT_YEAR)
        }
        carrying_before = _snapshot([world.carrying_id])

        response = _patch(
            world,
            world.lapsing_id,
            {
                "annual_entitlement": 2,
                "disposition": vocabulary.DISPOSITION_RECALCULATE,
            },
        )

        # `200`, not an error. AD-19: the edit COMMITS while the refused pair is left alone.
        assert response.status_code == 200, response.text
        summary = response.json()["recalculation"]

        # Alice refused — and NAMED, because "employee 3f2a…" is not something an Admin can act on.
        assert len(summary["pairs_refused"]) == 1
        refused = summary["pairs_refused"][0]
        assert refused["employee_id"] == str(world.alice_id)
        assert refused["employee_name"] == "Policy alice"
        assert refused["leave_type_id"] == str(world.lapsing_id)
        assert refused["cause"] == vocabulary.CAUSE_POLICY_RECALCULATION
        # The year the refusal was DISCOVERED at — the one the Admin has to go and look at.
        assert refused["leave_year"] == _NEXT_YEAR

        # Alice: ENTIRELY unchanged. Every column, every year — "entirely" is the word AC5 uses.
        for year in (_YEAR, _NEXT_YEAR):
            after = _balance(world.alice_id, world.lapsing_id, year)
            before = alice_before[year]
            assert (
                after.accrued,
                after.prorated_entitlement,
                after.carried_forward,
                after.entitlement_basis,
                after.reserved,
                after.consumed,
            ) == (
                before.accrued,
                before.prorated_entitlement,
                before.carried_forward,
                before.entitlement_basis,
                before.reserved,
                before.consumed,
            )

        # Bob: recalculated normally, IN THE SAME OPERATION. This is the "rest of it commits" clause —
        # the whole of AD-19, and the reason a refusal is scoped to the PAIR rather than the command.
        #
        # Note the count is not 1: `create_leave_type`'s materialization hook (Story 2.4) writes a
        # balance row for the new type × EVERY Employee IN THE DATABASE, so the sweep legitimately
        # covers all of them — the seeded Employees and every other test's, not just this world's two.
        # That is correct behaviour and the assertion is written against it rather than around it: of
        # every pair that exists, exactly one was refused and every other one committed.
        total_pairs = len({key[0] for key in _snapshot([world.lapsing_id])})
        assert summary["pairs_recalculated"] == total_pairs - 1

        bob_next = _balance(world.bob_id, world.lapsing_id, _NEXT_YEAR)
        assert bob_next.prorated_entitlement == 2
        assert bob_next.entitlement_basis == 2

        # The policy itself changed, and the log recorded it — the refusal did not roll the edit back.
        assert _leave_type(world.lapsing_id).annual_entitlement == 2
        assert len(_policy_changes(world.lapsing_id)) == 1

        # Exactly one flag, naming Alice at the year it was discovered.
        flags = _flags(world.lapsing_id)
        assert len(flags) == 1
        assert flags[0].employee_id == world.alice_id
        assert flags[0].leave_year == _NEXT_YEAR
        assert flags[0].cause == vocabulary.CAUSE_POLICY_RECALCULATION

        # And the OTHER Leave Type is untouched — a policy change edits exactly one.
        assert _snapshot([world.carrying_id]) == carrying_before

    def test_the_forward_check_is_what_refuses_not_the_guard(
        self, world: _World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC5's NON-VACUITY, proved the way Story 2.11 proved its own (Landmine 5).

        AC5 forbids DISCOVERING the refusal from a CHECK violation or a caught `ValueError`. A test
        that merely observes "the refusal happened" cannot tell WHICH LAYER refused — the forward
        check and a caught guard produce the same flag.

        So: monkeypatch `project_forward` to always answer "not refused", and run the refusal scenario
        again. If the forward check is load-bearing, the write path now walks straight into
        `set_accrual`'s `available >= 0` guard and raises an UNHANDLED `ValueError` — because there is
        no `try/except` anywhere on this path, and there must not be. If nothing changed, the check is
        decoration and the guard was doing the work all along.
        """
        _spend_a_later_year(world, world.alice_id, consumed=8)

        def _never_refuses(**kwargs):  # type: ignore[no-untyped-def]
            from app.domain.recalculation import ForwardProjection

            years = kwargs["years"]
            return ForwardProjection(
                refused=False,
                refused_year=None,
                carried_forward_by_year={year.leave_year: 0 for year in years[1:]},
            )

        monkeypatch.setattr(
            "app.services.recalculation.project_forward", _never_refuses
        )

        with pytest.raises(ValueError, match="would make available negative"):
            _patch(
                world,
                world.lapsing_id,
                {
                    "annual_entitlement": 2,
                    "disposition": vocabulary.DISPOSITION_RECALCULATE,
                },
            )

    def test_a_carrying_type_is_refused_when_the_cap_binds_and_a_later_year_is_spent(
        self, world: _World
    ) -> None:
        """The same unsoundness reached by a CARRYING type — the second half of Landmine 1.

        Here the fixed point is reached not because the type lapses but because THE CAP BINDS: the
        recomputed `carried_forward` lands on exactly the value already stored, so the stale `break`
        fires and the walk stops — while `Y+1`'s OWN re-proration has moved and driven it negative.
        """
        # Alice, year Y+1: carrying the full 12 forward, 20 already consumed against an accrual of 24.
        _materialize(
            world.alice_id,
            world.carrying_id,
            _NEXT_YEAR,
            prorated=_ENTITLEMENT,
            carried=_ENTITLEMENT,
            basis=_ENTITLEMENT,
            consumed=20,
        )

        # Drop the entitlement to 2. Y+1 re-prorates to 2, carries min(30, 2) = 2 → accrued 4, against
        # 20 consumed → available = −16. Refused.
        response = _patch(
            world,
            world.carrying_id,
            {
                "annual_entitlement": 2,
                "disposition": vocabulary.DISPOSITION_RECALCULATE,
            },
        )

        assert response.status_code == 200, response.text
        refused = response.json()["recalculation"]["pairs_refused"]
        assert len(refused) == 1
        assert refused[0]["employee_id"] == str(world.alice_id)
        assert refused[0]["leave_year"] == _NEXT_YEAR

        # Untouched, as always.
        assert _balance(world.alice_id, world.carrying_id, _NEXT_YEAR).consumed == 20
        assert _balance(
            world.alice_id, world.carrying_id, _NEXT_YEAR
        ).prorated_entitlement == _ENTITLEMENT


# ===============================================================================================
# AC6 — AD-6's recomputation, triggered explicitly, and provably a NO-OP
# ===============================================================================================


class TestTheCarryForwardRecomputation:
    def test_the_explicit_recomputation_is_a_no_op(self, world: _World) -> None:
        """AC6, and the assertion that turns it from a ceremony into a proof.

        "A policy change is not a balance change, so the recompute trigger as originally stated would
        never have fired at all" (architecture §6.3). So the service triggers it EXPLICITLY, after its
        apply loop.

        But the apply loop already wrote every year's `carried_forward` — from the projection. If the
        two disagreed, the recomputation would silently overwrite the loop's work with a different
        number, and nobody would know which was right. They cannot disagree: the projection and
        `recompute_carry_forward` are the ONE propagation rule (AD-6) evaluated twice, and they agree
        by construction.

        This proves it. Run the recomputation AGAIN, in its own transaction, over the freshly
        recalculated rows: every column must be byte-identical afterwards. A no-op is what a fixed
        point looks like from the outside.
        """
        _materialize(
            world.alice_id,
            world.carrying_id,
            _NEXT_YEAR,
            prorated=_ENTITLEMENT,
            carried=_ENTITLEMENT,
            basis=_ENTITLEMENT,
        )

        assert (
            _patch(
                world,
                world.carrying_id,
                {
                    "annual_entitlement": 20,
                    "disposition": vocabulary.DISPOSITION_RECALCULATE,
                },
            ).status_code
            == 200
        )

        after_patch = _snapshot([world.carrying_id])

        with Session(get_engine()) as session:
            for employee_id in (world.alice_id, world.bob_id):
                # `cause`/`occurred_at` are required since Story 3.4's Task 11 made this
                # forward-checked. They are the flag's payload and are unreachable here: this call is
                # asserted to be a NO-OP, so its projection cannot refuse.
                rollover.recompute_carry_forward(
                    session,
                    employee_id=employee_id,
                    leave_type_id=world.carrying_id,
                    leave_year=_YEAR,
                    cause=vocabulary.CAUSE_POLICY_RECALCULATION,
                    occurred_at=datetime.datetime.now(datetime.UTC),
                )
            session.commit()

        assert _snapshot([world.carrying_id]) == after_patch


# ===============================================================================================
# AC7 / AC8 — the Admin reads the log; nobody else does
# ===============================================================================================


class TestTheReadSurface:
    def test_an_admin_reads_the_recorded_changes_and_their_dispositions(
        self, world: _World
    ) -> None:
        """AC7. Everything AC12's screen needs, including the Leave Type's CODE, not just its id."""
        _patch(
            world,
            world.carrying_id,
            {"annual_entitlement": 15, "disposition": vocabulary.DISPOSITION_PRESERVE},
        )

        response = _client.get(
            "/api/v1/policy-changes", headers=_auth(world.admin_token)
        )

        assert response.status_code == 200, response.text
        mine = [
            item
            for item in response.json()["items"]
            if item["leave_type_id"] == str(world.carrying_id)
        ]
        assert len(mine) == 1
        assert mine[0]["leave_type_code"] == f"PC-{world.suffix}"
        assert mine[0]["attribute"] == "annual_entitlement"
        assert mine[0]["old_value"] == str(_ENTITLEMENT)
        assert mine[0]["new_value"] == "15"
        assert mine[0]["disposition"] == vocabulary.DISPOSITION_PRESERVE
        assert "actor" not in " ".join(mine[0].keys())

    def test_an_employee_and_a_manager_are_both_refused(self, world: _World) -> None:
        """AC8/G3: `403 ACTION_NOT_PERMITTED` — denied by ROLE GRANT, before any row is read.

        Not a `404`: 404 is reserved for a SCOPE miss (AD-10), and this is not one. No new error code
        arrives with this endpoint — `ACTION_NOT_PERMITTED` was declared in Story 1.4 and mapped to
        403 in `main.py` then.
        """
        for token in (world.alice_token, world.manager_token):
            response = _client.get("/api/v1/policy-changes", headers=_auth(token))
            assert response.status_code == 403, response.text
            assert response.json()["code"] == vocabulary.ACTION_NOT_PERMITTED

    def test_an_unauthenticated_caller_is_401(self) -> None:
        response = _client.get("/api/v1/policy-changes")
        assert response.status_code == 401, response.text
        assert response.json()["code"] == vocabulary.TOKEN_INVALID


# ===============================================================================================
# AC9 / SM-5 — the metric the whole epic is graded on
# ===============================================================================================


class TestSM5:
    def test_a_fourth_leave_type_is_created_used_repolicied_and_rolled_over(
        self, world: _World, owner_engine: Engine
    ) -> None:
        """AC9 / SM-5: a Leave Type created entirely through CONFIGURATION goes the whole distance.

        "Given a fourth Leave Type created entirely through configuration, when it is applied for,
        reserved against, approved, and rolled over at the Leave Year boundary, then every step
        succeeds with no code change and no schema migration."

        This is the metric the epic is judged on, and Story 2.12 adds one step to the road: the type is
        also RE-POLICIED, through `PATCH`, with a disposition. Nothing below tests a Leave Type by name
        or code, and nothing below could: `carry_forward_days` is built so it CANNOT see a code (AD-11),
        which is what makes SM-5 unfalsifiable rather than merely asserted.
        """
        suffix = uuid.uuid4().hex[:8]

        # 1. CREATED — through the API, by an Admin. No migration, no code change.
        created = _client.post(
            "/api/v1/leave-types",
            json={
                "code": f"SM5-{suffix}",
                "name": "Sabbatical",
                "annual_entitlement": 10,
                "carries_forward": True,
                "carry_forward_cap": 5,
                "requires_supporting_document": False,
            },
            headers=_auth(world.admin_token),
        )
        assert created.status_code == 201, created.text
        fourth_id = uuid.UUID(created.json()["id"])

        try:
            # 2. APPLIED FOR and RESERVED — the create hook already materialized Alice a balance.
            start = _next_monday()
            request_id = _submit(
                world, fourth_id, world.alice_id, world.alice_token, start, start + datetime.timedelta(days=1)
            )
            assert _balance(world.alice_id, fourth_id, _YEAR).reserved == 2

            # 3. APPROVED — reserved becomes consumed; available is unchanged.
            approved = _client.post(
                f"/api/v1/leave-requests/{request_id}/approve",
                headers=_auth(world.manager_token),
            )
            assert approved.status_code == 200, approved.text
            assert _balance(world.alice_id, fourth_id, _YEAR).consumed == 2

            # 4. RE-POLICIED — Story 2.12's addition to the SM-5 road.
            repolicied = _patch(
                world,
                fourth_id,
                {
                    "annual_entitlement": 14,
                    "disposition": vocabulary.DISPOSITION_RECALCULATE,
                },
            )
            assert repolicied.status_code == 200, repolicied.text
            assert repolicied.json()["recalculation"]["pairs_refused"] == []
            assert _balance(world.alice_id, fourth_id, _YEAR).prorated_entitlement == 14

            # 5. ROLLED OVER — carry-forward re-derived under the NEW policy, capped at 5.
            rollover.run_rollover(_YEAR)

            next_year = _balance(world.alice_id, fourth_id, _NEXT_YEAR)
            # available(Y) = 14 − 2 consumed = 12; the cap of 5 binds.
            assert next_year.carried_forward == 5
            assert next_year.prorated_entitlement == 14
            assert next_year.accrued == 19
        finally:
            with Session(owner_engine) as session:
                lr_ids = select(LeaveRequest.id).where(
                    LeaveRequest.leave_type_id == fourth_id
                )
                session.execute(
                    delete(AuditEntry).where(AuditEntry.subject_id.in_(lr_ids))
                )
                session.execute(
                    delete(PolicyChange).where(PolicyChange.leave_type_id == fourth_id)
                )
                session.execute(
                    delete(AdminReviewFlag).where(
                        AdminReviewFlag.leave_type_id == fourth_id
                    )
                )
                # Story 3.4 (Landmine 16): notification rows FIRST. The submit and the approve
                # above each wrote one, and a notification FK-references `leave_request` with no
                # `ON DELETE` clause — so deleting the requests first raises `ForeignKeyViolation`.
                # `lr_ids` is exactly the set about to be deleted, so it is the honest predicate
                # here (this teardown is scoped by Leave Type, not by an employee suffix).
                session.execute(
                    delete(Notification).where(
                        Notification.leave_request_id.in_(lr_ids)
                    )
                )
                session.execute(
                    delete(LeaveRequest).where(LeaveRequest.leave_type_id == fourth_id)
                )
                session.execute(
                    delete(LeaveBalance).where(LeaveBalance.leave_type_id == fourth_id)
                )
                session.execute(delete(LeaveType).where(LeaveType.id == fourth_id))
                session.commit()


# --- shared request helpers (declared last; used by the classes above) --------------------------


def _next_monday() -> datetime.date:
    """A future Monday inside `_YEAR` — derived from the clock, never hardcoded.

    Story 2.4's create hooks materialize balances for the CURRENT year only, so a request must fall
    inside it. A hardcoded date would silently degrade into a test of the missing-row path the moment
    the calendar turned. The December corner has no future work-week left inside the Leave Year, and
    is skipped loudly rather than passing against zeroes (the Story 2.10/2.11 precedent).
    """
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    if monday.year != _YEAR:  # pragma: no cover - only reachable in late December
        pytest.skip(
            "No future work-week remains inside the current Leave Year, so a request cannot be "
            "submitted for the year under recalculation. Re-run outside the last weeks of December."
        )
    return monday


def _submit(
    world: _World,
    leave_type_id: uuid.UUID,
    employee_id: uuid.UUID,
    token: str,
    start: datetime.date,
    end: datetime.date,
) -> str:
    """Submit a Leave Request as a MANAGED Employee — it lands PENDING and RESERVES its days."""
    response = _client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type_id": str(leave_type_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
