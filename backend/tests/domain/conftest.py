"""Tests of the pure core. No database fixture is defined here, and none may be.

Implements: the spine's *Testing* row and NFR-15 / SM-2 — "`tests/domain/` runs with
no database fixture".

This package holds no tests in Story 1.1, because `domain/` holds no rule yet:
`errors.py` and a near-empty `vocabulary.py` are all there is. It exists now so that
the first domain rule has an unambiguous home for its tests, and lands in a directory
where reaching for a database is visibly out of place.

The absence of a `db_connection` fixture here is load-bearing, not an oversight.
`tests/integration/conftest.py` defines one; pytest resolves fixtures by walking *up*
the directory tree from the test module, never sideways, so nothing under
`tests/domain/` can reach it. A domain test that finds itself needing a database has
found a domain rule implemented in the wrong layer. The fix is to move the rule, not
to import the fixture.

This module is intentionally free of fixtures. An autouse fixture asserting "no
database was touched" was written here and removed: it could only have checked whether
`sqlalchemy` appeared in `sys.modules`, which another test module in the same session
imports legitimately. It would have asserted nothing while looking like a guarantee —
the same error as mistaking an import contract for proof that no I/O occurs.

The real guarantee is structural. `domain/` cannot import SQLAlchemy, psycopg or a web
framework: contract 3 in `pyproject.toml` forbids it, and `test_architecture.py` fails
the build when it happens. A pure function reached by a test in this directory has no
database to reach for.

SM-2's boundary tests — the leave-day count across weekends, Company Holidays and
Leave Year edges — land here, and will run in milliseconds because of it.
"""
