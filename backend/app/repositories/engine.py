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
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return the shared engine, constructed on first use.

    Cached so the pool is process-wide. A test that points at a different database
    calls `get_engine.cache_clear()` after `get_settings.cache_clear()`, in that order —
    the engine is built from settings, so a stale engine would outlive a settings reset.
    """
    return create_engine(get_settings().database_url)
