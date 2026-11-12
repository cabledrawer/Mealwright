"""The data folder is for the Mealwright user alone (spec section 7): files 0600, folders 0700."""

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mealwright import __main__ as server
from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.private_files import tighten


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_tighten_fixes_files_and_folders_made_with_wider_permissions(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "backups").mkdir(parents=True)
    (data / "photos" / "a").mkdir(parents=True)
    files = [
        data / "mealwright.db",
        data / "mealwright.db-wal",
        data / "mealwright.db-shm",
        data / "backups" / "pre-upgrade.db",
        data / "photos" / "a" / "one.webp",
    ]
    for file in files:
        file.write_bytes(b"x")
        file.chmod(0o644)
    for folder in (data, data / "backups", data / "photos", data / "photos" / "a"):
        folder.chmod(0o755)
    tighten(data)
    assert all(mode(file) == 0o600 for file in files)
    assert all(
        mode(folder) == 0o700
        for folder in (data, data / "backups", data / "photos", data / "photos" / "a")
    )


def test_tighten_leaves_links_alone_and_carries_on(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    outside.chmod(0o644)
    data = tmp_path / "data"
    data.mkdir()
    (data / "link").symlink_to(outside)
    tighten(data)
    assert mode(outside) == 0o644
    tighten(tmp_path / "nothing-here")  # no folder: nothing to do, no error


def test_starting_the_app_tightens_an_older_install(settings: Settings) -> None:
    db = settings.data_dir / "mealwright.db"
    db.chmod(0o644)
    settings.data_dir.chmod(0o755)
    with TestClient(create_app(settings)):
        assert mode(db) == 0o600
        assert mode(settings.data_dir) == 0o700
        for extra in ("-wal", "-shm"):
            side = db.with_name(db.name + extra)
            if side.exists():
                assert mode(side) == 0o600


def test_the_server_sets_a_private_umask_before_it_makes_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`python -m mealwright` sets the umask first thing, so new files are 0600 and new
    folders 0700 (the database's -wal and -shm files, backups, photos, logs)."""
    calls: list[str] = []
    monkeypatch.setenv("MEALWRIGHT_DATA_DIR", str(tmp_path))

    def record(text: str) -> None:
        calls.append(text)

    def fake_umask(value: int) -> int:
        record(f"umask {value:o}")
        return 0

    def fake_logging(_dir: Path) -> None:
        record("logging")

    monkeypatch.setattr("os.umask", fake_umask)
    monkeypatch.setattr(server, "set_up_logging", fake_logging)
    monkeypatch.setattr(
        server, "create_app", lambda *_args: SimpleNamespace(state=SimpleNamespace(events=None))
    )
    monkeypatch.setattr(
        server, "StoppableServer", lambda *_args: SimpleNamespace(run=lambda: record("run"))
    )
    server.main()
    assert calls == ["umask 77", "logging", "run"]


def test_the_warning_names_the_first_path_it_could_not_restrict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    data = tmp_path / "data"
    (data / "photos").mkdir(parents=True)
    stuck = data / "photos" / "one.webp"
    stuck.write_bytes(b"x")
    stuck.chmod(0o644)
    real_chmod = Path.chmod

    def refuse(self: Path, mode: int, **kwargs: bool) -> None:
        if self == stuck:
            raise PermissionError("not yours")
        real_chmod(self, mode, **kwargs)

    monkeypatch.setattr(Path, "chmod", refuse)
    with caplog.at_level("WARNING", logger="mealwright.private_files"):
        tighten(data)
    warning = " ".join(record.getMessage() for record in caplog.records)
    assert "photos/one.webp" in warning
    assert str(tmp_path) not in warning.replace(str(data), "")
    assert "docs/hardening.md" in warning
