"""Mealwright refuses to start with a database that isn't SQLite, or as more than one worker,
and says why (spec section 6, "From the 28 Oct review of v0.6.0")."""

import multiprocessing
import os
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

from mealwright.config import Settings
from mealwright.main import UnsupportedSetup, create_app, refuse_unsupported_setup


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://mealwright:secret@db/mealwright",
        "postgresql+psycopg://db/mealwright",
        "mysql://db/mealwright",
        "not a database address",
    ],
)
def test_a_database_that_isnt_sqlite_is_refused(tmp_path: Path, url: str) -> None:
    settings = Settings(data_dir=tmp_path, database_url=url, run_jobs=False)
    with pytest.raises(UnsupportedSetup, match="must be a SQLite address"):
        create_app(settings)


@pytest.mark.parametrize("url", [None, "sqlite:///{dir}/other.db", "sqlite+pysqlite:///{dir}/x.db"])
def test_sqlite_addresses_are_fine(tmp_path: Path, url: str | None) -> None:
    address = url.format(dir=tmp_path) if url else None
    refuse_unsupported_setup(Settings(data_dir=tmp_path, database_url=address, run_jobs=False))


@pytest.mark.parametrize("value", ["2", "4", " 8 "])
def test_more_than_one_worker_by_web_concurrency_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", value)
    with pytest.raises(UnsupportedSetup, match="runs as one worker"):
        create_app(Settings(data_dir=tmp_path, run_jobs=False))


def test_web_concurrency_of_one_is_fine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    refuse_unsupported_setup(Settings(data_dir=tmp_path, run_jobs=False))


def test_a_worker_started_by_a_supervisor_is_refused(tmp_path: Path) -> None:
    """uvicorn --workers starts each worker as a spawned child process: run the check in one."""
    child = multiprocessing.get_context("spawn").Process(
        target=refuse_unsupported_setup, args=(Settings(data_dir=tmp_path, run_jobs=False),)
    )
    child.start()
    try:
        child.join(60)
        assert child.exitcode == 1  # the check raised in the child
    finally:
        if child.is_alive():
            child.terminate()


@pytest.mark.parametrize(
    ("setting", "what_is_wrong", "how_to_fix"),
    [
        (
            {"MEALWRIGHT_DATABASE_URL": "postgresql://db/mealwright"},
            "Not starting: MEALWRIGHT_DATABASE_URL must be a SQLite address",
            "Leave it unset to use /data/mealwright.db.",
        ),
        (
            {"WEB_CONCURRENCY": "4"},
            "Not starting: Mealwright runs as one worker.",
            "Start it with `python -m mealwright`",
        ),
    ],
)
def test_the_server_says_why_and_stops(
    tmp_path: Path, setting: dict[str, str], what_is_wrong: str, how_to_fix: str
) -> None:
    """The log has one plain line saying what is wrong and how to fix it, no traceback, and
    the process ends with a non-zero code (cabledrawer 28 Oct)."""
    env = {**os.environ, "MEALWRIGHT_DATA_DIR": str(tmp_path), **setting}
    run = subprocess.run(
        [sys.executable, "-m", "mealwright"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert run.returncode == 1
    output = run.stdout + run.stderr
    assert what_is_wrong in output
    assert how_to_fix in output
    assert output.count("Not starting") == 1
    assert "Traceback" not in output
