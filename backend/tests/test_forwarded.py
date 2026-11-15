"""The reverse proxy's X-Forwarded-Host, and a warning when its X-Forwarded-For isn't believed
(PR A2)."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient

from mealwright.config import Settings
from mealwright.forwarded import TrustedProxies
from mealwright.main import create_app

PROXY_NAME = "mealwright:8080"  # what a proxy may pass as Host: its upstream's name
OUR_ADDRESS = "meals.example.org"
SETTINGS = {"theme": "dark"}


def make_client(tmp_path: Path, trusted_proxies: str) -> TestClient:
    # TestClient connects from the address "testclient", playing the reverse proxy.
    settings = Settings(data_dir=tmp_path / "data", trusted_proxies=trusted_proxies)
    return TestClient(create_app(settings), base_url=f"https://{PROXY_NAME}")


def change_theme(client: TestClient, headers: dict[str, str]) -> int:
    """A same-site-only change, from a browser on https://meals.example.org."""
    sent = {"Origin": f"https://{OUR_ADDRESS}", **headers}
    return client.put("/api/v1/me/preferences", json=SETTINGS, headers=sent).status_code


@pytest.fixture
def trusted(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path, "testclient") as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        yield client


def test_a_trusted_proxys_forwarded_host_is_the_host(trusted: TestClient) -> None:
    assert change_theme(trusted, {}) == 403  # Host is the proxy's upstream name: refused
    assert change_theme(trusted, {"X-Forwarded-Host": OUR_ADDRESS}) == 200


def test_the_last_forwarded_host_counts(trusted: TestClient) -> None:
    # A visitor's own X-Forwarded-Host comes first; the proxy adds the real one last.
    both = {"X-Forwarded-Host": f"evil.example, {OUR_ADDRESS}"}
    assert change_theme(trusted, both) == 200
    faked = {"X-Forwarded-Host": f"{OUR_ADDRESS}, evil.example"}
    assert change_theme(trusted, faked) == 403


@pytest.mark.parametrize(
    "bad", ["meals.example.org/evil", "meals example", "@evil", "a" * 300, "meals:99999999"]
)
def test_a_strange_forwarded_host_is_ignored(trusted: TestClient, bad: str) -> None:
    assert change_theme(trusted, {"X-Forwarded-Host": bad}) == 403


def test_an_untrusted_forwarded_host_is_ignored(tmp_path: Path) -> None:
    with make_client(tmp_path, "") as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        assert change_theme(client, {"X-Forwarded-Host": OUR_ADDRESS}) == 403


def test_one_warning_when_forwarded_for_isnt_believed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="mealwright"),
        make_client(tmp_path, "") as client,
    ):
        for address in ("203.0.113.5", "198.51.100.7", "203.0.113.9"):
            client.get("/api/v1/version", headers={"X-Forwarded-For": address})
    warnings = [r for r in caplog.records if r.name == "mealwright.proxy"]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "MEALWRIGHT_TRUSTED_PROXIES" in message
    assert "203.0.113" not in message and "testclient" not in message


def test_no_warning_without_a_proxy_or_from_a_trusted_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="mealwright"):
        with make_client(tmp_path / "a", "") as direct:
            direct.get("/api/v1/version")
        with make_client(tmp_path / "b", "testclient") as behind:
            behind.get("/api/v1/version", headers={"X-Forwarded-For": "203.0.113.5"})
    assert not [r for r in caplog.records if r.name == "mealwright.proxy"]


def test_trusted_addresses_and_networks() -> None:
    trusted = TrustedProxies("172.28.10.0/24, 10.0.0.1, fd00::/8, testclient")
    assert "172.28.10.7" in trusted
    assert "10.0.0.1" in trusted
    assert "fd00::5" in trusted
    assert "testclient" in trusted
    assert "10.0.0.2" not in trusted
    assert "172.28.11.1" not in trusted
    assert None not in trusted
    assert "203.0.113.5" in TrustedProxies("*")
    assert "203.0.113.5" not in TrustedProxies("")
