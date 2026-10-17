from fastapi.testclient import TestClient

from mealwright import __version__


def test_version(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json() == {"version": __version__}


def test_openapi_is_versioned(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/version" in paths
    assert all(path.startswith("/api/v1/") for path in paths)


def test_no_cdn_docs_pages(client: TestClient) -> None:
    # FastAPI's default docs pages pull scripts from a CDN.
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
