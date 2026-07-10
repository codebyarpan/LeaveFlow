"""The deployment probe.

Implements the test side of: AC1 (`GET /api/v1/health` answers 200),
api-contracts §4.10 (`GET /health`, anonymous).

Deliberately thin. NFR-15 and the story's testing standards are explicit that
coverage of the health endpoint matters less than coverage of the hard rules, and
that this endpoint is not where to chase it. One assertion per claim the
acceptance criteria actually make.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_answers_200_under_the_versioned_base_path() -> None:
    """AC1: `GET /api/v1/health` answers 200."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_requires_no_authentication() -> None:
    """api-contracts §4.10: the probe is anonymous.

    Asserted by sending no Authorization header at all, which is what a
    deployment probe does.
    """
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert "www-authenticate" not in {k.lower() for k in response.headers}
