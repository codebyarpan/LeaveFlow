"""A domain exception raised in `services/` surfaces as `{code, message, details}`.

Implements the test side of: AC3, NFR-17 (one envelope), api-contracts §2.

Scope, and why it stops where it does. AC3 is about the *mechanism*: one handler,
one `code -> status` map, one envelope shape. The endpoint-level assertion — that
every non-2xx response of every real endpoint carries this envelope — belongs to
Story 1.2, the first story in which any endpoint can return a non-2xx response.
Asserting it here would test a codebase that does not yet exist.

The route below is registered on a test-only app and discarded with it. Story 1.1
adds no permanent route that exists only to raise.
"""

from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.errors import CODE_TO_STATUS, DEFAULT_ERROR_STATUS, domain_error_handler
from app.domain.errors import DomainError

# A code that exists only for this test. It is deliberately not added to
# `domain/vocabulary.py`: AD-21 governs the vocabulary of the running system, and a
# test fixture is not part of it.
TEST_ONLY_CODE = "TEST_ONLY_REFUSAL"


def _service_that_refuses(details: dict[str, Any] | None = None) -> None:
    """Stand in for a `services/` function that raises a typed domain exception.

    Defined here rather than in `app/services/` on purpose. Story 1.1 implements no
    service, and a permanent module whose only reason to exist is to raise would be
    the same defect as the permanent route Task 4 forbids.

    That `services/` genuinely cannot import HTTP is not asserted by this test — it
    is asserted structurally, by contract 4 in `pyproject.toml`, and exercised by
    `test_architecture.py`. A test can show that a mechanism works; only the import
    contract can show that no other mechanism was used.
    """
    raise DomainError(
        code=TEST_ONLY_CODE,
        message="The request was refused for a reason the domain can state.",
        details={} if details is None else details,
    )


def _throwaway_app() -> FastAPI:
    """A FastAPI app carrying one route, wired exactly as `main.py` wires the real one."""
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)

    @app.get("/throwaway")
    def _raise_from_the_service_layer() -> None:
        _service_that_refuses({"days_requested": 4, "days_available": 1})

    @app.get("/throwaway-with-a-date")
    def _refuse_with_a_date() -> None:
        _service_that_refuses({"end_date": date(2026, 7, 10)})

    return app


def test_domain_error_surfaces_as_the_error_envelope() -> None:
    """AC3: the exception becomes `{code, message, details}` — those three keys, exactly."""
    response = TestClient(_throwaway_app()).get("/throwaway")

    assert response.json() == {
        "code": TEST_ONLY_CODE,
        "message": "The request was refused for a reason the domain can state.",
        "details": {"days_requested": 4, "days_available": 1},
    }


def test_details_carries_the_numbers_a_refusal_must_state() -> None:
    """api-contracts §2: `details` is where a refusal puts its numbers."""
    response = TestClient(_throwaway_app()).get("/throwaway")

    assert response.json()["details"] == {"days_requested": 4, "days_available": 1}


def test_details_carrying_a_date_still_serializes() -> None:
    """The envelope survives non-JSON-primitive detail values (review P1).

    This is a *leave* system: refusals carry dates almost immediately. Python-mode
    `model_dump()` leaves `datetime.date` intact and `json.dumps` raises TypeError
    on it — detonating the error path exactly when a refusal is being stated. The
    handler must dump in JSON mode.
    """
    response = TestClient(_throwaway_app()).get("/throwaway-with-a-date")

    assert response.json()["details"] == {"end_date": "2026-07-10"}


def test_an_unmapped_code_becomes_500_not_400() -> None:
    """A forgotten map entry is a programming error, and must not masquerade as a 4xx.

    `CODE_TO_STATUS` is empty in Story 1.1, so `TEST_ONLY_CODE` is necessarily unmapped.
    """
    assert TEST_ONLY_CODE not in CODE_TO_STATUS

    response = TestClient(_throwaway_app()).get("/throwaway")

    assert response.status_code == DEFAULT_ERROR_STATUS == 500


def test_the_status_map_is_consulted(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC3: the handler maps the code to a status *via the map*, not via a default.

    Proven by inserting an entry and observing the status follow it. Without this,
    `test_an_unmapped_code_becomes_500_not_400` would also pass against a handler
    that ignored `CODE_TO_STATUS` entirely and always returned 500.
    """
    monkeypatch.setitem(CODE_TO_STATUS, TEST_ONLY_CODE, 409)

    response = TestClient(_throwaway_app()).get("/throwaway")

    assert response.status_code == 409
    assert response.json()["code"] == TEST_ONLY_CODE


def test_details_defaults_to_empty_and_is_not_shared_between_instances() -> None:
    """A mutable default would be shared across every DomainError ever raised."""
    first = DomainError(code="A", message="first")
    second = DomainError(code="B", message="second")

    first.details["leaked"] = True

    assert first.details == {"leaked": True}
    assert second.details == {}
