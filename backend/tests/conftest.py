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
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client
