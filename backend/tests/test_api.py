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


def test_every_place_the_version_shows_agrees_with_pyproject(client: TestClient) -> None:
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    wanted = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert __version__ == wanted
    assert client.get("/api/v1/version").json() == {"version": wanted}
    assert client.get("/api/v1/openapi.json").json()["info"]["version"] == wanted
