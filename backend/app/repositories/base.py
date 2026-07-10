"""The SQLAlchemy declarative base every model inherits from.

Implements: AD-1 (models are `repositories/`' business, per the spine's source tree),
AC6 (this story creates no domain table).

`Base.metadata` is what Alembic's `env.py` compares the database against when
autogenerating a migration. No model exists yet, so the metadata is empty — and that
is precisely why `alembic revision --autogenerate` would produce an empty migration
today, and why Story 1.1's baseline revision is hand-written and no-op instead.

The base lives here rather than in `core/` because a model is persistence, and
`domain/` must remain a package with no way to reach a database. A `DeclarativeBase`
in `core/` would be importable from `domain/` — contract 5 forbids that import, but
the temptation should not exist in the first place.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every LeaveFlow ORM model.

    Naming conventions (spine, *Consistency Conventions*): tables are `snake_case`
    and **singular** — `employee`, `leave_request` — and models are `PascalCase`.
    """
