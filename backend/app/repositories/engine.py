"""The process-wide SQLAlchemy engine, and the one place a connection pool is built.

Implements: AD-3 (one transaction per command, opened in `services/` — the *engine*
those transactions draw from lives here, in `repositories/`, because a connection pool
is persistence infrastructure), NFR-21.

`services/` opens the transaction; this module hands it the engine to open it against.
Keeping the engine here rather than in `services/` means the pool is created once and
shared, not rebuilt per command, and that `repositories/` (which contract 1 lets
`services/` import) is the single owner of the database handle.

Why `psycopg` needs nothing special here: the URL settings build is already
`postgresql+psycopg://...`, so `create_engine` selects psycopg 3 automatically.

--- This engine connects as the APPLICATION role, never the owner (AD-9, Story 2.9) ---

`app_database_url`, NOT `database_url`. The distinction is the whole of AD-9: the owner
role owns every table and runs Alembic; the application role is granted `INSERT` and
`SELECT` on `audit_entry` and NEITHER `UPDATE` NOR `DELETE`, so the audit trail is
append-only at the DATABASE and not merely by habit in `repositories/audit_entry.py`.
Point this at the owner URL and that guarantee silently evaporates — an owner cannot be
denied on its own table — while every test still passes. There is deliberately NO
`get_owner_engine()` here: the application has no legitimate use for one, and offering it
would put the bypass one import away. Schema maintenance is Alembic's, under the owner
(`alembic/env.py`); test cleanup that must delete audit rows uses the owner engine the
integration `conftest` builds, and that asymmetry is the point, not an inconvenience.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return the shared engine — connected as the APPLICATION role (AD-9).

    Cached so the pool is process-wide. A test that points at a different database
    calls `get_engine.cache_clear()` after `get_settings.cache_clear()`, in that order —
    the engine is built from settings, so a stale engine would outlive a settings reset.
    """
    return create_engine(get_settings().app_database_url)
