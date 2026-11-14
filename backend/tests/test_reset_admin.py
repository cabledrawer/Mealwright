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


def _admin_person(kitchen: TestClient, name: str, username: str, join: bool) -> int:
    """An admin person of the household; with `join`, they have chosen their password."""
    api = "/api/v1"
    assert kitchen.post(f"{api}/people", json={"name": name}).status_code == 201
    people = kitchen.get(f"{api}/people").json()["people"]
    member_id = int(next(p["id"] for p in people if p["name"] == name))
    link = kitchen.post(
        f"{api}/people/{member_id}/login", json={"username": username, "role": "admin"}
    )
    assert link.status_code == 201, link.text
    if join:
        token = link.json()["path"].removeprefix("/join#")
        fresh = TestClient(kitchen.app, base_url="https://testserver")
        r = fresh.post(f"{api}/join", json={"token": token, "password": "a long own password"})
        assert r.status_code == 200, r.text
    return member_id


def test_refuses_a_removed_admin_and_lists_only_admins_who_can_sign_in(
    kitchen: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A removed admin can't sign in, so a new password would only look like a way back in
    (0.9.0-alpha.1 security pass). The list names admins who can sign in, and an admin whose
    sign-in link isn't used yet, marked."""
    joss = _admin_person(kitchen, "Joss", "joss", join=True)
    _admin_person(kitchen, "Pia", "pia", join=False)
    _admin_person(kitchen, "Ola", "ola", join=True)
    assert kitchen.delete(f"/api/v1/people/{joss}").status_code == 200
    # Removing an admin ends every admin's unused sign-in link (16b security re-check S2-M1;
    # proposed): the admin who hasn't joined yet is given a new one.
    for someone in kitchen.get("/api/v1/people").json()["people"]:
        login = someone["login"]
        if login and login["role"] == "admin" and not login["signs_in"]:
            body = {"username": login["username"], "role": "admin"}
            again = kitchen.post(f"/api/v1/people/{someone['id']}/login", json=body)
            assert again.status_code == 201, again.text
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        before = db.scalars(select(Login.password_hash).where(Login.username == "joss")).one()
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    status, printed = _reset(settings, "joss")
    assert status == 1
    assert printed == ""
    assert capsys.readouterr().err == (
        "The login 'joss' can't be reset: Joss has been removed from the household. "
        "Admins: ola, pia (sign-in link not used yet), tess.\n"
    )
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        after = db.scalars(select(Login.password_hash).where(Login.username == "joss")).one()
    assert after == before
    # The same list when the name is wrong: never the removed admin.
    assert _reset(settings, "nobody")[0] == 1
    assert capsys.readouterr().err == (
        "The login 'nobody' doesn't exist. Admins: ola, pia (sign-in link not used yet), tess.\n"
    )
