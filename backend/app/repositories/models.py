"""The ORM models. Persistence is `repositories/`' business (AD-1, the spine's source tree).

Implements: FR-01 (an Employee authenticates with email + password), FR-04 (a
deactivated Employee cannot authenticate), AD-10 (every read is scoped — the columns
that scope it, `department_id` and `manager_id`, live here), AD-14 (`password_hash` is
where the bcrypt digest is stored, never the password), AD-23 (`CHECK (id <> manager_id)`
is a *backstop* for the reporting-cycle refusal — the gate itself is the employee
service in Story 1.6). SM-6: every model names the requirements it serves.

Why `department` and `employee` arrive together, in this story rather than Story 1.5:
`employee.department_id` is NOT NULL (PRD §3 — every Employee belongs to exactly one
Department), so the Admin seeded here (AC2) needs a Department to belong to. Story 1.5
adds the Department *endpoints*; the table has to exist before an Admin can be seeded.

These models must stay byte-for-byte faithful to migration `0002` — `alembic check`
(exercised by the schema test) emits an empty diff only while they agree. Change one,
change both, in the same commit.
"""

import datetime
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.repositories.base import Base


class Department(Base):
    """A unit of the organization every Employee belongs to (FR-01, PRD §3).

    No `UNIQUE (name)`: the ERD does not declare one, and inventing schema the ERD
    does not name is how two sources of truth begin to disagree. The seed reconciles
    a duplicate name by select-then-insert (Story 1.2 Task 6), not by a constraint.
    """

    __tablename__ = "department"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        # PostgreSQL 18 native built-in — no extension, no CREATE EXTENSION (ERD §4.4).
        server_default=text("uuidv7()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


class Employee(Base):
    """A person who authenticates and, later, requests leave (FR-01, FR-04, AD-10, AD-14).

    `manager_id` is nullable — an Admin, and the top of any reporting chain, reports to
    no one (AC2). `CHECK (id <> manager_id)` is AD-23's backstop only: it refuses the
    one-node self-loop the database can see cheaply, but the transitive cycle refusal is
    the employee service's (Story 1.6). A CHECK violation reaching a client is a defect
    and a 500 (AD-5), never a validation message — the service is the gate.
    """

    __tablename__ = "employee"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("department.id"),
        nullable=False,
        index=True,  # NFR-12; ERD §4.4 — reads filter by department.
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id"),
        nullable=True,
        index=True,  # NFR-12; ERD §4.4 — "my team" walks this edge.
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    joining_date: Mapped[datetime.date] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    department: Mapped["Department"] = relationship(back_populates="employees")
    manager: Mapped["Employee | None"] = relationship(remote_side="Employee.id")

    __table_args__ = (
        CheckConstraint(
            "role IN ('EMPLOYEE', 'MANAGER', 'ADMIN')",
            name="employee_role_check",
        ),
        # AD-23 backstop. Named so the migration and the model agree on it.
        CheckConstraint("id <> manager_id", name="employee_not_own_manager_check"),
    )
