"""No enumerated value appears as a bare string literal outside `domain/vocabulary.py`.

Implements the test side of: AC9, AD-21 ("declared exactly once in `domain/`, and
appears as a literal nowhere else").

A static check over the source. Needs no database. `pytest` is the build (F-14), so a
planted `"AUTH_FAILED"` in `api/` or `services/` fails the suite rather than merely
warning — which is what makes AD-21 an enforced rule and not a coding-style aspiration.

--- Why it iterates `__all__` rather than a hardcoded list ---

The value set is read from `domain/vocabulary.__all__` at runtime. Story 1.6 adds role
guards, Story 2.6 adds the four `leave_request.status` codes, and every one of them
lands in `__all__` — the moment it does, this check starts enforcing it, with no edit
here. A hardcoded list would silently stop covering the vocabulary the day someone
forgot to extend it, which is precisely the day it matters.

--- Why exact equality, not substring ---

The forbidden thing is the *value used as a literal* — `role = "ADMIN"` typed in a
service. A compound string that merely contains the value — the CHECK DDL
`"role IN ('EMPLOYEE', 'MANAGER', 'ADMIN')"` mirrored in `repositories/models.py`, the
database's own copy per ERD §4.2 — is not that, and a substring match would flag it
wrongly. So a literal offends only when it equals an exported value exactly.

--- Why it walks the AST rather than grepping ---

Same reason as `test_migrations_insert_nothing.py`: this very file, and
`vocabulary.py`'s own docstring, discuss `AUTH_FAILED` in prose. A regex would trip on
the explanation. `ast` discards comments, and docstrings are skipped explicitly, so
prose about a value is not mistaken for the value.
"""

import ast
from pathlib import Path

import pytest

from app.domain import vocabulary

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# The two trees the running system is assembled from. `alembic/versions/` is NOT here:
# a migration is immutable once applied, and its `CHECK (role IN (...))` DDL is the
# database's copy of the vocabulary, prescribed verbatim by ERD §4.2 (Task 3 scope
# decision). `tests/` is not scanned either — tests SHOULD import the constants, and a
# byte-identity assertion built from `vocabulary.AUTH_FAILED` is the point, not a smell.
_SCANNED_TREES = (BACKEND_ROOT / "app", BACKEND_ROOT / "seed")

# The one file allowed to hold these values as literals — it is where they are declared.
_VOCABULARY_FILE = Path(vocabulary.__file__).resolve()


def _forbidden_values() -> set[str]:
    """Every string value exported by `domain/vocabulary.py`, read from `__all__`.

    Reading `__all__` rather than listing names here is what makes the check pick up
    every constant a later story adds, automatically (AC9).
    """
    values: set[str] = set()
    for name in vocabulary.__all__:
        value = getattr(vocabulary, name)
        # Only string constants are enumerated values. A later non-string export
        # (there is none today) is simply not something this check governs.
        if isinstance(value, str):
            values.add(value)
    return values


class _LiteralVisitor(ast.NodeVisitor):
    """Collects every bare string literal that equals an enumerated value exactly."""

    def __init__(self, forbidden: set[str]) -> None:
        self._forbidden = forbidden
        self.offenders: list[str] = []

    def visit_Expr(self, node: ast.Expr) -> None:
        """Skip bare string statements — module, class and function docstrings.

        Identical to `test_migrations_insert_nothing.py`'s pattern: not descending
        into a docstring is what lets `vocabulary.py` and this test *name* the values
        in prose without being read as using them.
        """
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and node.value in self._forbidden:
            self.offenders.append(f"{node.value!r} at line {node.lineno}")
        self.generic_visit(node)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for tree in _SCANNED_TREES:
        for path in sorted(tree.rglob("*.py")):
            if path.resolve() != _VOCABULARY_FILE:
                files.append(path)
    return files


def test_there_are_files_to_scan_and_values_to_forbid() -> None:
    """A check over zero files or zero values passes vacuously and proves nothing."""
    assert _forbidden_values(), "vocabulary.__all__ exports no string values"
    assert _scanned_files(), "no source files found under app/ or seed/"


@pytest.mark.parametrize("source_file", _scanned_files(), ids=lambda p: str(p.relative_to(BACKEND_ROOT)))
def test_no_enumerated_value_appears_as_a_literal(source_file: Path) -> None:
    """AD-21: outside `domain/vocabulary.py`, an enumerated value is imported, never typed.

    Parametrized per file so a failure names the offending file directly, and so the
    set of files grows with the codebase without this test being revisited.
    """
    visitor = _LiteralVisitor(_forbidden_values())
    visitor.visit(ast.parse(source_file.read_text(encoding="utf-8")))

    assert not visitor.offenders, (
        f"{source_file.relative_to(BACKEND_ROOT)} uses an enumerated value as a literal: "
        f"{visitor.offenders}.\n"
        "AD-21: import it from `app.domain.vocabulary` instead — e.g. "
        "`vocabulary.AUTH_FAILED`, never `\"AUTH_FAILED\"`."
    )


def test_the_guard_detects_a_planted_literal() -> None:
    """Guards the guard: prove the visitor fires on the literal it exists to catch.

    Without this, a visitor that matched nothing — a broken `__all__` read, a typo —
    would leave every file "passing". The planted source uses a real exported value.
    """
    planted_value = next(iter(_forbidden_values()))
    planted_source = f"role = {planted_value!r}\n"

    visitor = _LiteralVisitor(_forbidden_values())
    visitor.visit(ast.parse(planted_source))

    assert visitor.offenders, f"guard failed to catch a planted literal: {planted_source!r}"

    # And the false positive it must NOT raise: the same value named only in a docstring.
    innocent = ast.parse(f'"""This module raises {planted_value} on a bad token."""')
    visitor = _LiteralVisitor(_forbidden_values())
    visitor.visit(innocent)

    assert not visitor.offenders, "guard tripped over a docstring that merely names a value"
