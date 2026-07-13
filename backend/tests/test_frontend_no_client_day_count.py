"""The client never computes a leave-day count. Enforced from the backend suite.

Implements the test side of Story 2.3 AC6 / AC11 and AD-2: the server is the sole
authority on a Leave Day count. The count, its excluded dates, each date's reason
(``WEEKEND`` / ``HOLIDAY``) and every holiday name arrive from the preview endpoint
(Story 2.5); the client renders them and computes nothing. A client-side copy of the
weekend-and-holiday rule would drift the instant the Admin changes the holiday calendar —
that is why exactly one implementation exists, and it is on the server (`domain/calendar.py`).

--- Why this guard forbids `getDay`/`getUTCDay` and NOT the words "weekday"/"holiday" ---

AC6 reads, literally, "the frontend source … no module references a weekday or a Company
Holiday." Taken as a `grep` for those *words*, the AC fails on the very code that enforces
it and on shipped, allowed features:

  * `frontend/src/features/README.md` and `frontend/src/api/client.ts` *state* the AD-2
    rule in prose — they use the words "weekday"/"holiday" precisely to forbid the client
    from computing with them.
  * Story 2.2 shipped `frontend/src/features/holidays/` and `frontend/src/api/holidays.ts`,
    which handle Company Holidays as *display data* (a `Holiday` type, a list, a date
    input). AD-2 allows that: the client renders the holidays the Admin manages; it never
    derives a day count from them.

So the guard enforces the *intent*, not the vocabulary. `getDay` and `getUTCDay` are the
only JavaScript primitives that yield a day-of-week, and therefore the necessary
precondition for reimplementing weekend logic — there is no way to ask "is this a Saturday?"
in JS without one. Holiday-set membership alone cannot produce a Leave Day count either.
Forbidding these two primitives is precise and false-positive-free, and it fits the
project's house idiom: `test_migrations_insert_nothing.py` scans migrations, and
`test_vocabulary_literals.py` scans `app/` + `seed/` — this scans `frontend/src`.

Today the guard passes trivially (the frontend has no `getDay`/`getUTCDay`). Like
`test_scoped_getters.py`, its value is as an *armed* guardrail: the moment Story 2.5's
preview screen — or any later work — is tempted to compute a count client-side, the build
(which is `pytest`; there is no frontend test runner) fails.
"""

import re
from pathlib import Path

import pytest

# backend/tests/ -> backend/ -> repo root -> frontend/src.
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

# The JS day-of-week primitives. Matched as whole identifiers (`\b`) so that unrelated
# names containing the substring are not caught, and both `Date.prototype` forms are
# covered. These are the precondition for computing a weekend on the client.
_DAY_OF_WEEK_PRIMITIVE = re.compile(r"\b(getDay|getUTCDay)\b")

# Directories that are not shipped client source. `__tests__` would hold test doubles;
# `node_modules` is vendored. Neither is present today, but excluding them keeps the guard
# correct if they appear.
_EXCLUDED_DIRS = {"node_modules", "__tests__"}


def _client_source_files() -> list[Path]:
    """Every shipped `*.ts` / `*.tsx` file under `frontend/src`, excluding tests/vendored."""
    files: list[Path] = []
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in (".ts", ".tsx"):
            continue
        if _EXCLUDED_DIRS & set(path.parts):
            continue
        files.append(path)
    return files


@pytest.mark.skipif(
    not FRONTEND_SRC.is_dir(),
    reason="frontend/src not present in this checkout (backend-only checkout)",
)
def test_no_client_module_computes_a_day_of_week() -> None:
    """AC6/AC11 (AD-2): no `frontend/src` module uses `getDay`/`getUTCDay`.

    The client obtains every Leave Day count from the server's preview endpoint. A
    day-of-week primitive on the client is the necessary precondition for reimplementing
    the weekend-and-holiday rule — the one thing AD-2 forbids the client from doing.
    """
    offenders: list[str] = []
    for path in _client_source_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _DAY_OF_WEEK_PRIMITIVE.search(line):
                rel = path.relative_to(FRONTEND_SRC.parents[1])
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "A frontend module computes a day-of-week — AD-2 forbids the client from computing "
        "a Leave Day count. The count and its excluded dates come from the preview endpoint "
        "(Story 2.5), never from client-side weekend logic:\n" + "\n".join(offenders)
    )


@pytest.mark.skipif(
    not FRONTEND_SRC.is_dir(),
    reason="frontend/src not present in this checkout (backend-only checkout)",
)
def test_the_guard_actually_scans_client_source() -> None:
    """Guards the guard: prove files are being read, so a green result means "clean", not "empty".

    A guard that silently walked zero files — a broken path, a wrong glob — would "pass"
    while enforcing nothing. `frontend/src/api/client.ts` is known to exist (it carries the
    AD-2 note this guard arms), so the file list must be non-empty and include it.
    """
    files = _client_source_files()
    assert files, "the guard scanned no files — check FRONTEND_SRC and the *.ts/*.tsx glob"
    assert any(p.name == "client.ts" for p in files)


def test_the_guard_detects_a_day_of_week_primitive() -> None:
    """Guards the guard: the pattern fires on the calls it exists to catch, and not on innocents.

    Runs without the frontend present — it exercises the regex on source strings directly,
    so a backend-only checkout still verifies the detector is not silently inert.
    """
    violations = [
        "const dow = d.getDay();",
        "if (new Date(x).getUTCDay() === 6) return true;",
    ]
    for source in violations:
        assert _DAY_OF_WEEK_PRIMITIVE.search(source), f"guard failed to catch: {source}"

    # Words that legitimately appear in rule-documenting prose and in the holidays *data*
    # feature must NOT trip the guard — that was the whole trap in a word-based check.
    innocents = [
        "// no module under src/ may reference a weekday or a Company Holiday",
        "type Holiday = { date: string; name: string };",
        "const label = new Date(iso).toLocaleDateString();  // getDate/getFullYear are fine",
    ]
    for source in innocents:
        assert not _DAY_OF_WEEK_PRIMITIVE.search(source), f"guard tripped on: {source}"
