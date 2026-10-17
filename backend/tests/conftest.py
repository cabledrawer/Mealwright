from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.outbound import install_network_guard

# The whole test suite runs with the network guard on: any connection or DNS lookup
# outside the outbound gate fails the test that made it.
install_network_guard()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # The nightly jobs are tested on their own (test_jobs.py).
    return Settings(data_dir=tmp_path / "data", run_jobs=False)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # HTTPS, as behind Caddy, so the Secure session cookie is sent back.
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        yield client


ADMIN = {"name": "Tess", "username": "tess", "password": "correct horse battery"}


@pytest.fixture
def kitchen(client: TestClient) -> TestClient:
    """A client signed in as the household's admin, on a fresh install."""
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
    return client
