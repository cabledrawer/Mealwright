"""Serving the built web app, and allowing only its own inline scripts."""

import base64
import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mealwright.config import Settings
from mealwright.frontend import inline_script_hashes
from mealwright.main import create_app

BOOT = "\n\t\t\t\t__sveltekit_x = { base: '' };\n\t\t\t"
INDEX = f"""<!doctype html><html><head>
<link rel="stylesheet" href="/_app/immutable/assets/app.abc123.css">
</head><body><div id="app"></div>
<script>{BOOT}</script>
<script type="module" src="/_app/immutable/entry/start.def456.js"></script>
</body></html>"""


def sha(text: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()


@pytest.fixture
def build(tmp_path: Path) -> Path:
    folder = tmp_path / "build"
    (folder / "_app/immutable/entry").mkdir(parents=True)
    (folder / "index.html").write_text(INDEX)
    (folder / "sign-in.html").write_text("<!doctype html><p>sign in</p>")
    (folder / "_app/immutable/entry/start.def456.js").write_text("console.log('hi')")
    (folder / "favicon.svg").write_text("<svg/>")
    (folder / "service-worker.js").write_text("self.addEventListener('fetch', () => {})")
    (folder / "manifest.webmanifest").write_text('{"name": "Mealwright"}')
    (tmp_path / "secret.txt").write_text("not for the web")
    return folder


@pytest.fixture
def web(tmp_path: Path, build: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path / "data", frontend_dir=build)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        yield client


def test_home_page(web: TestClient) -> None:
    response = web.get("/")
    assert response.status_code == 200
    assert '<div id="app">' in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_pages_by_name(web: TestClient) -> None:
    assert web.get("/sign-in").text == "<!doctype html><p>sign in</p>"


def test_app_addresses_get_the_app(web: TestClient) -> None:
    # The app's own router handles /plan, /recipes/12 and so on.
    for path in ("/plan", "/recipes/12", "/shopping/"):
        response = web.get(path)
        assert response.status_code == 200
        assert '<div id="app">' in response.text


def test_hashed_files_are_cached_for_a_year(web: TestClient) -> None:
    response = web.get("/_app/immutable/entry/start.def456.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_missing_files_are_404_not_the_app(web: TestClient) -> None:
    assert web.get("/_app/immutable/entry/gone.js").status_code == 404
    assert web.get("/nothing.png").status_code == 404


def test_api_addresses_never_get_the_app(web: TestClient) -> None:
    response = web.get("/api/v1/no-such-thing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
    assert web.get("/api").status_code == 404


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"])
def test_nothing_outside_the_build_folder(web: TestClient, path: str) -> None:
    response = web.get(path)
    assert "not for the web" not in response.text


def test_only_the_apps_own_inline_scripts_are_allowed(web: TestClient, build: Path) -> None:
    assert inline_script_hashes(build) == [sha(BOOT)]
    policy = web.get("/").headers["content-security-policy"]
    script_src = next(p for p in policy.split(";") if p.strip().startswith("script-src"))
    assert script_src.split() == ["script-src", "'self'", f"'{sha(BOOT)}'"]
    # The same policy is on API responses too.
    assert web.get("/api/v1/version").headers["content-security-policy"] == policy


def test_without_a_build_the_api_still_works(settings: Settings) -> None:
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert client.get("/api/v1/version").status_code == 200
        assert client.get("/").status_code == 404


def test_service_worker_is_always_checked_again(web: TestClient) -> None:
    response = web.get("/service-worker.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "javascript" in response.headers["content-type"]


def test_manifest_has_its_own_type_and_is_checked_again(web: TestClient) -> None:
    response = web.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert response.headers["cache-control"] == "no-cache"


def test_the_policy_still_allows_the_worker_and_manifest_from_our_own_server_only(
    web: TestClient,
) -> None:
    policy = web.get("/").headers["content-security-policy"]
    assert "worker-src 'self';" in policy
    assert "manifest-src 'self';" in policy
    assert "connect-src 'self';" in policy
    assert "default-src 'self';" in policy
