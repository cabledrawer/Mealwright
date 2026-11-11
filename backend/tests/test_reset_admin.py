"""`python -m mealwright reset-admin <username>` (PR A2): the only admin's way back in."""

import io
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright.auth import hash_password
from mealwright.config import Settings
from mealwright.models import Login
from mealwright.reset_admin import reset_admin


def _reset(settings: Settings, username: str) -> tuple[int, str]:
    out = io.StringIO()
    return reset_admin(settings, username, out), out.getvalue()


def test_a_new_password_shown_once_and_signed_out_everywhere(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    phone = TestClient(kitchen.app, base_url="https://testserver")
    old = {"username": ADMIN["username"], "password": ADMIN["password"]}
    assert phone.post("/api/v1/session", json=old).status_code == 200

    with caplog.at_level(logging.INFO, logger="mealwright"):
        status, printed = _reset(settings, "Tess")  # any case
    assert status == 0
    found = re.search(r"New password for tess: (\S+)", printed)
    assert found
    password = found.group(1)
    assert len(password) >= 12
    assert "shown only this once" in printed
    # Never in the log; who and how many are.
    assert password not in caplog.text
    assert "reset-admin: new password set for tess; signed out on 2 device(s)" in caplog.text

    assert kitchen.get("/api/v1/me").status_code == 401
    assert phone.get("/api/v1/me").status_code == 401
    fresh = TestClient(kitchen.app, base_url="https://testserver")
    assert fresh.post("/api/v1/session", json=old).status_code == 401
    assert fresh.post("/api/v1/session", json={**old, "password": password}).status_code == 200
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Login.password_changed_at)).one() is not None


def test_each_reset_is_a_different_password(kitchen: TestClient) -> None:
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    first = _reset(settings, "tess")[1]
    second = _reset(settings, "tess")[1]
    assert first != second


def test_refuses_an_unknown_username(
    kitchen: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    status, printed = _reset(settings, "nobody")
    assert status == 1
    assert printed == ""
    assert "The login 'nobody' doesn't exist. Admins: tess." in capsys.readouterr().err
    assert kitchen.get("/api/v1/me").status_code == 200


def test_refuses_someone_who_isnt_an_admin(
    kitchen: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    before = hash_password("a member's own password")
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(household_id=1, username="ayla", name="Ayla", password_hash=before, role="member")
        )
        db.commit()
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    status, _ = _reset(settings, "ayla")
    assert status == 1
    assert "The login 'ayla' isn't an admin. Admins: tess." in capsys.readouterr().err
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        login = db.scalars(select(Login).where(Login.username == "ayla")).one()
        assert login.password_hash == before


def test_an_admin_of_another_household_can_be_reset(neighbour: TestClient) -> None:
    settings = neighbour.app.state.settings  # type: ignore[attr-defined]
    assert _reset(settings, "neighbour")[0] == 0
    assert neighbour.get("/api/v1/me").status_code == 401


def test_no_database_no_change(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(data_dir=tmp_path, run_jobs=False)
    assert _reset(settings, "tess")[0] == 1
    assert "There's no Mealwright database" in capsys.readouterr().err
    assert not (tmp_path / "mealwright.db").exists()


def test_the_command_line(kitchen: TestClient) -> None:
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    env = {"MEALWRIGHT_DATA_DIR": str(settings.data_dir), "PATH": "/usr/bin:/bin"}
    ran = subprocess.run(
        [sys.executable, "-m", "mealwright", "reset-admin", "tess"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.startswith("New password for tess: ")
    usage = subprocess.run(
        [sys.executable, "-m", "mealwright", "reset-admin"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert usage.returncode == 2
    assert "username" in usage.stderr
