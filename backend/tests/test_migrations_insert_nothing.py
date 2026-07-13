"""No migration inserts data. Ever.

Implements the test side of: AC6 ("no migration inserts a Leave Type row"), AD-11.

A static check over the migration sources. Needs no database.

--- Why this test exists before there is anything for it to catch ---

AC6 holds *vacuously* today: Story 1.1 creates no table, so no migration could insert
a Leave Type row even if it wanted to. It stops holding vacuously the moment someone
reaches for `op.bulk_insert()` in Story 2.1, where the `leave_type` table arrives and
the temptation to seed it in the same migration is at its strongest.

A test written then would be written by the person about to violate it. Writing it now,
against zero migrations, is the only moment at which it costs nothing.

AD-11 exists so SM-5 can hold: a fourth Leave Type must be addable with no code change
*and no schema migration*. That is impossible if the first three entered through a
migration, because the fourth would then have nowhere to come from but a fourth one.

--- Why this walks the AST rather than grepping the source ---

The first version of this test was a regex over the file's text, and it failed against
this project's own baseline migration — whose docstrings discuss `op.bulk_insert()`
precisely in order to forbid it. A checker that trips over its own explanation gets
deleted within the week.

`ast` sees code. Comments are discarded by the parser, and docstrings are the one
string form we skip explicitly. Prose about a forbidden call is no longer indistinguishable
from the call.
"""

import ast
import re
from pathlib import Path

import pytest

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"

# Data manipulation, as opposed to schema definition. Matched against *string literals*
# that survive the docstring filter — `op.execute("INSERT INTO ...")`, `sa.text(...)`.
# Identifiers may be schema-qualified or quoted (`UPDATE public.leave_type`,
# `UPDATE "leave_type"`), so the identifier class is wider than \w. MERGE, TRUNCATE
# and COPY ... FROM write (or destroy) rows just as surely as INSERT does.
_SQL_DML = re.compile(
    r"""\binsert\s+into\b
      | \bupdate\s+[\w."']+\s+set\b
      | \bdelete\s+from\b
      | \bmerge\s+into\b
      | \btruncate\s+(?:table\s+)?[\w."']+
      | \bcopy\s+[\w."']+\s+from\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Calls that write rows. `bulk_insert` is Alembic's; `insert` covers BOTH SQLAlchemy
# forms — the method (`table.insert()`, an ast.Attribute) and the 2.0-canonical
# function (`from sqlalchemy import insert; insert(table)`, an ast.Name).
_WRITING_CALLS = {"bulk_insert", "insert"}


class _DataMutationVisitor(ast.NodeVisitor):
    """Collects every expression in a migration that writes a row."""

    def __init__(self) -> None:
        self.offenders: list[str] = []

    def visit_Expr(self, node: ast.Expr) -> None:
        """Skip bare string statements — that is exactly what a docstring is.

        Not descending into them is what lets a migration explain in prose why it must
        not call `op.bulk_insert()` without that explanation being read as the call.
        """
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Attribute calls (`op.bulk_insert`, `table.insert()`) AND bare-name calls
        # (`insert(table)` after `from sqlalchemy import insert`). The first guard
        # only caught attributes, and the bare-name form is the canonical
        # SQLAlchemy 2.0 style — exactly what Story 2.1 would reach for.
        if isinstance(node.func, ast.Attribute):
            called = node.func.attr
        elif isinstance(node.func, ast.Name):
            called = node.func.id
        else:
            called = None

        if called in _WRITING_CALLS:
            self.offenders.append(f"{called}() at line {node.lineno}")

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Catch DML hidden in a string, e.g. `op.execute("INSERT INTO leave_type ...")`.

        Docstrings never reach here: `visit_Expr` returns before descending into them.
        """
        if isinstance(node.value, str) and _SQL_DML.search(node.value):
            self.offenders.append(f"SQL DML in a string literal at line {node.lineno}")

        self.generic_visit(node)


def _migration_files() -> list[Path]:
    return sorted(p for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py")


def test_the_migration_history_is_the_expected_ordered_chain() -> None:
    """The revision files are exactly the baseline then Story 1.2's schema, in order.

    Story 1.1 shipped one no-op baseline; Story 1.2 adds `0002`, the first migration
    that creates schema. Asserted as an exact ordered list rather than a count, so a
    stray or misnamed revision file is caught, not merely tallied. Later stories extend
    this list as they add migrations — the `_SQL_DML` guard below needs no such edit,
    because it parametrizes over whatever files exist.
    """
    assert [p.name for p in _migration_files()] == [
        "0001_baseline_baseline_no_domain_table_ac6_ad_11.py",
        "0002_department_and_employee.py",
        "0003_leave_type.py",
        "0004_company_holiday.py",
    ]


@pytest.mark.parametrize("migration", _migration_files(), ids=lambda p: p.name)
def test_no_migration_inserts_or_updates_data(migration: Path) -> None:
    """AD-11: migrations move schema. Data enters through `python -m seed`, only.

    Parametrized over every migration in the tree, so it keeps asserting as Stories
    1.2, 2.1 and 2.10 add theirs. It does not need to be revisited.
    """
    visitor = _DataMutationVisitor()
    visitor.visit(ast.parse(migration.read_text(encoding="utf-8")))

    assert not visitor.offenders, (
        f"{migration.name} writes data: {visitor.offenders}.\n"
        "AD-11: a migration never inserts a Leave Type row. Seeding is the seed "
        "command's job (`python -m seed`), so that SM-5 can add a fourth Leave Type "
        "with no code change and no schema migration."
    )


def test_the_guard_detects_a_real_bulk_insert() -> None:
    """Guards the guard: prove the visitor fires on the call it exists to catch.

    Without this, a visitor that silently matched nothing — a renamed attribute, a
    typo in `_WRITING_METHODS` — would leave every migration "passing".

    The sources below are the ways AD-11 gets violated in practice — including the
    bypasses the first version of this guard missed (bare-name `insert()`, quoted
    and schema-qualified identifiers, MERGE, COPY) — and the last is the prose that
    must NOT trip it.
    """
    violations = [
        'op.bulk_insert(leave_type_table, [{"code": "EL"}])',
        'op.execute("INSERT INTO leave_type (code) VALUES (\'EL\')")',
        "op.execute(leave_type.insert().values(code='EL'))",
        # The 2.0-canonical function form: an ast.Name call, not an ast.Attribute.
        "op.execute(insert(leave_type).values(code='EL'))",
        # Quoted and schema-qualified identifiers defeat a \w+ pattern.
        'op.execute(\'UPDATE "leave_type" SET code = 1\')',
        "op.execute(\"UPDATE public.leave_type SET code = 'EL'\")",
        "op.execute('MERGE INTO leave_type USING ...')",
        "op.execute('TRUNCATE TABLE leave_type')",
        "op.execute('COPY leave_type FROM stdin')",
    ]

    for source in violations:
        visitor = _DataMutationVisitor()
        visitor.visit(ast.parse(source))
        assert visitor.offenders, f"guard failed to catch: {source}"

    # And the false positive that broke the first version of this test.
    innocent = ast.parse('"""This migration must never call op.bulk_insert() — AD-11."""')
    visitor = _DataMutationVisitor()
    visitor.visit(innocent)

    assert not visitor.offenders, "guard tripped over a docstring that merely names the call"
