"""Alembic environment.

Implements: AC1 (`alembic upgrade head` is command two of the setup sequence),
AC5 / NFR-20 (the database URL is never written into a committed file),
AC6 (this story's migration creates no domain table),
AD-11 (a migration never inserts a Leave Type row — seeding is the seed command's job).

The URL is read from `app/core/settings.py`, which reads it from the environment.
`alembic.ini` deliberately leaves `sqlalchemy.url` unset; see the comment there.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.settings import get_settings

# Import the declarative base so `Base.metadata` carries every model that has been
# defined. Today there are none, and AC6 asserts precisely that.
#
# As models arrive (Story 1.2 onward) they must be imported here, or by something
# imported here, or `--autogenerate` will not see them and will cheerfully emit a
# migration that drops the tables it could not find.
from app.repositories.base import Base

# Importing the models registers them on `Base.metadata`, which is what makes
# `--autogenerate` and `alembic check` see them. Without this line the check would
# emit a diff proposing to DROP `department` and `employee` — the exact silent-drop
# failure the comment above warns about. Imported for the side effect, hence `noqa`.
from app.repositories import models  # noqa: E402, F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Injected at runtime rather than committed. The `%%` escaping is ours to do:
# `set_main_option` passes the value straight to ConfigParser, which treats `%` as
# interpolation syntax — its docstring says "a raw percent sign … must therefore be
# escaped". A URL-encoded password (`p%40ss`) would otherwise kill setup command two
# with an InterpolationSyntaxError. ConfigParser unescapes on read, so the engine
# sees the real URL.
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a DBAPI connection (`alembic upgrade head --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
