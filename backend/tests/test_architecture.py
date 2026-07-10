"""Enforces AD-1 and NFR-13: the layered structure is mechanical, not aspirational.

Implements the test side of: AC2 (import direction; a violation fails the build) and
AC3 (`domain/` and `services/` import no HTTP).

--- Why this is a test and not a CI step ---

AC2 requires that a violation "fails the build rather than merely warning", and no
story in this project establishes a CI pipeline — finding F-14 of the readiness
report records that gap and accepts it for a three-day trainee project.

So `pytest` is the build. Running `lint_imports()` inside the test suite is the whole
of what makes "fails the build" true today. Deleting this file does not merely remove
a test; it silently unenforces AD-1 for all 26 remaining stories.

The contracts themselves live in `pyproject.toml` under `[tool.importlinter]`, beside
a comment explaining why a `layers` contract alone is insufficient.
"""

from pathlib import Path

import pytest
from importlinter.cli import EXIT_STATUS_SUCCESS, lint_imports

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = BACKEND_ROOT / "pyproject.toml"


def test_import_direction_contracts_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2, AC3: every import-linter contract passes.

    `lint_imports()` returns 0 when every contract holds and 1 when any is broken.
    It resolves relative paths against the working directory, so the chdir makes the
    result independent of where `pytest` was invoked from.
    """
    monkeypatch.chdir(BACKEND_ROOT)

    exit_status = lint_imports(config_filename=str(PYPROJECT))

    assert exit_status == EXIT_STATUS_SUCCESS, (
        "Architecture contract violated — run `lint-imports` in backend/ for the "
        "offending import chain. This is AD-1; fix the import, not the contract."
    )


def test_every_contract_in_pyproject_is_actually_exercised() -> None:
    """Guards the guard: every contract must be present WITH its content intact.

    `lint_imports()` exits 0 when it finds *zero* contracts, so a `pyproject.toml`
    that lost its `[[tool.importlinter.contracts]]` blocks — to a bad merge, or to a
    developer silencing a failure — would leave the test above passing over an
    unenforced architecture. That is the precise failure this project cannot afford.

    Content, not just names: the realistic way a failure gets silenced is not
    deleting a contract but emptying its `forbidden_modules` list, which a name-set
    assertion waves through.
    """
    import tomllib

    with PYPROJECT.open("rb") as handle:
        config = tomllib.load(handle)

    contracts = {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}

    expected = {
        "Layered architecture (AD-1)": {
            "layers": ["app.api", "app.services", "app.repositories", "app.domain"],
        },
        "api/ talks only to services/ (AD-1)": {
            "source_modules": ["app.api"],
            "forbidden_modules": ["app.repositories", "app.domain"],
            # Pinned so the option cannot be silently dropped: AC2 forbids api/ from
            # importing repositories/ or domain/ DIRECTLY, not the layered call chain
            # api -> services -> domain. Removing this would fail the build the moment a
            # route calls a service that raises a DomainError (Story 1.2's login onward);
            # flipping it to strict would unenforce nothing but break the architecture.
            "allow_indirect_imports": "true",
        },
        "domain/ is pure (AD-1)": {
            "source_modules": ["app.domain"],
            "forbidden_modules": [
                "sqlalchemy",
                "psycopg",
                "alembic",
                "fastapi",
                "starlette",
                "httpx",
                "requests",
            ],
        },
        "services/ imports no HTTP (AC3)": {
            "source_modules": ["app.services"],
            "forbidden_modules": ["fastapi", "starlette", "httpx", "requests"],
        },
        "domain/ does not import core/ (AD-1)": {
            "source_modules": ["app.domain"],
            "forbidden_modules": ["app.core"],
        },
        "core/ is a leaf (AD-1)": {
            "source_modules": ["app.core"],
            "forbidden_modules": [
                "app.api",
                "app.services",
                "app.repositories",
                "app.domain",
            ],
        },
        "jobs/ never imports api/ (AD-1)": {
            "source_modules": ["app.jobs"],
            "forbidden_modules": ["app.api"],
        },
    }

    assert set(contracts) == set(expected), "a contract was added, renamed or lost"

    for name, required in expected.items():
        for key, value in required.items():
            assert contracts[name].get(key) == value, (
                f"contract {name!r}: {key} was changed — the architecture is no "
                "longer what the tests claim it is. Fix the import, not the contract."
            )
