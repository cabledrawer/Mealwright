"""Library telemetry stays off (spec section 7)."""

from importlib.metadata import distributions

import pytest
from fastapi.testclient import TestClient

from mealwright.config import Settings
from mealwright.main import create_app


def test_fastapi_telemetry_is_off(settings: Settings) -> None:
    app = create_app(settings)
    assert app._native_telemetry.enabled() is False
    assert app._telemetry["auto_configure"] is False


def test_otel_environment_is_ignored(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example:4318")
    app = create_app(settings)
    assert app._telemetry["auto_configure"] is False
    with TestClient(app) as client:
        assert client.get("/api/v1/version").status_code == 200


def test_only_the_opentelemetry_api_is_installed() -> None:
    # FastAPI needs opentelemetry-api (a no-op on its own). An SDK or exporter
    # package would be able to send data, so none may be installed.
    installed = {dist.metadata["Name"].lower() for dist in distributions()}
    extra = {name for name in installed if name.startswith("opentelemetry")}
    assert extra <= {"opentelemetry-api"}
