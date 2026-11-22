"""The browser tests' fixed clock (backend/scripts/e2e_server.py) is off in a real install."""

import importlib.util
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from mealwright import auth, models, setup_code, updates
from mealwright.config import Settings
from mealwright.household import today
from mealwright.main import create_app
from mealwright.models import Household, utcnow

BACKEND = Path(__file__).parent.parent
SOURCE = BACKEND / "src" / "mealwright"


def _launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "e2e_server", BACKEND / "scripts" / "e2e_server.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_clock_is_not_moved_by_default() -> None:
    assert timedelta(0) == models.TEST_CLOCK_SHIFT
    assert abs(utcnow() - datetime.now(UTC)) < timedelta(seconds=5)
    assert abs(auth.now() - datetime.now(UTC)) < timedelta(seconds=5)


def test_the_app_ignores_the_test_variable(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("E2E_CLOCK_SHIFT_MS", str(-400 * 24 * 3600 * 1000))
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/version").status_code == 200
    assert timedelta(0) == models.TEST_CLOCK_SHIFT
    assert abs(utcnow() - datetime.now(UTC)) < timedelta(seconds=5)


def test_nothing_in_the_app_moves_the_clock_or_reads_the_variable() -> None:
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "E2E_CLOCK_SHIFT_MS" not in text, path
        assert "E2E_SETUP_CODE" not in text, path
        assert not re.search(r"^\s*(?:import|from)\s+\S*e2e_server", text, re.MULTILINE), path
        sets = re.findall(r"^\s*(?:models\.)?TEST_CLOCK_SHIFT\s*[:=]", text, re.MULTILINE)
        if path.name == "models.py":
            assert sets == ["TEST_CLOCK_SHIFT ="], sets  # its definition, zero
        else:
            assert sets == [], path


def test_the_image_has_only_the_installed_package_and_the_web_app() -> None:
    dockerfile = (BACKEND.parent / "Dockerfile").read_text(encoding="utf-8")
    final_stage = dockerfile.rsplit("\nFROM ", 1)[1]
    copies = re.findall(r"^COPY .*$", final_stage, re.MULTILINE)
    assert copies == [
        "COPY --from=api /app/backend/.venv /app/backend/.venv",
        "COPY --from=web /src/frontend/build /app/frontend",
        # The licence notices of what the image ships (0.9.5).
        "COPY THIRD-PARTY-NOTICES.md /app/THIRD-PARTY-NOTICES.md",
    ]
    # The package is installed as a copy (not linked to the source folder), so scripts/ stays out.
    assert "--no-editable" in dockerfile


def test_the_launcher_moves_today_and_stored_times() -> None:
    launcher = _launcher()
    household = Household(name="Test", time_zone="Europe/London")
    fixed = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)  # 10:00 in London
    shift_ms = round((fixed - datetime.now(UTC)).total_seconds() * 1000)
    try:
        launcher.move_the_clock({"E2E_CLOCK_SHIFT_MS": str(shift_ms)})
        assert today(household) == date(2026, 10, 17)
        assert abs(utcnow() - fixed) < timedelta(seconds=5)
        assert abs(auth.now() - fixed) < timedelta(seconds=5)
    finally:
        models.TEST_CLOCK_SHIFT = timedelta(0)
    assert abs(utcnow() - datetime.now(UTC)) < timedelta(seconds=5)


def test_the_launcher_can_set_the_setup_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_code, "new_code", setup_code.new_code)  # put back afterwards
    _launcher().know_the_setup_code({"E2E_SETUP_CODE": "TEST-SETU-PCDE"})
    assert setup_code.new_code() == "TEST-SETU-PCDE"


def test_the_browser_tests_never_ask_github(monkeypatch: pytest.MonkeyPatch) -> None:
    """T4 (22 Nov): Check now in the browser tests answered from GitHub's real release list."""
    monkeypatch.setattr(updates, "RELEASE_LIST_URL", updates.RELEASE_LIST_URL)
    _launcher().ask_github_nothing()
    assert f"/{updates.PLACEHOLDER_OWNER}/" in updates.RELEASE_LIST_URL
    assert updates.OWNER not in updates.RELEASE_LIST_URL
