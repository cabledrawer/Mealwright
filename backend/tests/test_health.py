"""GET /api/v1/health: the container's health check (0.9.5). Ok only when the database answers."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_health_is_ok_with_no_sign_in_and_says_nothing_else(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}  # no version, no counts


def test_health_fails_when_the_database_cannot_answer(client: TestClient, tmp_path: Path) -> None:
    # A database whose file can't be opened (its path is a folder): the process is up, the
    # database is not. The answer says no reason.
    broken = create_engine(f"sqlite:///{tmp_path}")
    original = client.app.state.sessionmaker  # type: ignore[attr-defined]
    client.app.state.sessionmaker = sessionmaker(broken)  # type: ignore[attr-defined]
    try:
        response = client.get("/api/v1/health")
    finally:
        client.app.state.sessionmaker = original  # type: ignore[attr-defined]
        broken.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_health_is_in_the_public_api_and_version_is_unchanged(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/version" in paths
    assert client.get("/api/v1/version").json().keys() == {"version"}


def test_the_image_healthcheck_asks_the_health_endpoint() -> None:
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    check = dockerfile[dockerfile.index("HEALTHCHECK") :]
    assert "/api/v1/health" in check
    assert "/api/v1/version" not in check
