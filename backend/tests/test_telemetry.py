"""Library telemetry stays off (spec section 7)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mealwright.config import Settings
from mealwright.main import create_app

SCRIPTS = Path(__file__).parent.parent / "scripts"


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
    # The same script runs against the built Docker image.
    result = subprocess.run(  # noqa: S603 (fixed command, no user input)
        [sys.executable, "-I", str(SCRIPTS / "check_no_telemetry.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_check_script_rejects_an_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("check", SCRIPTS / "check_no_telemetry.py")
    assert spec is not None and spec.loader is not None
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)

    class FakeDist:
        def __init__(self, name: str) -> None:
            self.metadata = {"Name": name}

    fake = [FakeDist("opentelemetry-api"), FakeDist("opentelemetry_exporter_otlp")]
    monkeypatch.setattr(check, "distributions", lambda: fake)
    assert check.forbidden_packages() == ["opentelemetry-exporter-otlp"]
    assert check.main() == 1
