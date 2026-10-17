import logging
import os
import stat
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from mealwright import logs
from mealwright.logs import (
    FILE_NAME,
    KEEP_DAYS,
    formatter,
    remove_old_logs,
    set_up_logging,
    tidy_once,
)

DAY = 24 * 3600


@pytest.fixture
def clean_logging() -> Iterator[None]:
    """Put every logger set_up_logging touches back as it was."""
    root = logging.getLogger()
    saved = list(root.handlers)
    levels = {name: logging.getLogger(name).level for name in ("", "mealwright", "uvicorn.error")}
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        if handler not in saved:
            handler.close()
    for handler in saved:
        root.addHandler(handler)
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


def file_handler() -> logs.DailyLogFile:
    found = [h for h in logging.getLogger().handlers if isinstance(h, logs.DailyLogFile)]
    assert len(found) == 1
    return found[0]


def test_log_lines_carry_a_utc_timestamp() -> None:
    record = logging.LogRecord("mealwright", logging.WARNING, "", 0, "Hello", None, None)
    record.created = 0.0
    assert formatter().format(record) == "1970-01-01T00:00:00Z WARNING mealwright: Hello"


def test_log_file_is_written_and_private(tmp_path: Path, clean_logging: None) -> None:
    set_up_logging(tmp_path)
    logging.getLogger("mealwright.test").warning("Something went wrong")
    file_handler().flush()
    path = tmp_path / "logs" / FILE_NAME
    assert path.read_text().endswith("Z WARNING mealwright.test: Something went wrong\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600  # holds addresses: owner only


def test_rotation_puts_the_day_aside(tmp_path: Path, clean_logging: None) -> None:
    set_up_logging(tmp_path)
    handler = file_handler()
    logging.getLogger("mealwright.test").warning("Day one")
    handler.rotate("2026-10-17")
    logging.getLogger("mealwright.test").warning("Day two")
    handler.flush()
    folder = tmp_path / "logs"
    assert "Day one" in (folder / f"{FILE_NAME}.2026-10-17").read_text()
    assert "Day one" not in (folder / FILE_NAME).read_text()
    assert "Day two" in (folder / FILE_NAME).read_text()
    assert stat.S_IMODE((folder / FILE_NAME).stat().st_mode) == 0o600


def test_rotating_twice_in_a_day_keeps_both(tmp_path: Path, clean_logging: None) -> None:
    set_up_logging(tmp_path)
    handler = file_handler()
    for text in ("First", "Second"):
        logging.getLogger("mealwright.test").warning(text)
        handler.rotate("2026-10-17")
    kept = sorted((tmp_path / "logs").glob(f"{FILE_NAME}.2026-10-17*"))
    assert len(kept) == 2
    words = {word for path in kept for word in path.read_text().split()}
    assert {"First", "Second"} <= words


def test_files_older_than_14_days_go_even_on_a_quiet_server(tmp_path: Path) -> None:
    now = time.time()
    ages = {f"{FILE_NAME}.old": KEEP_DAYS + 1, f"{FILE_NAME}.recent": KEEP_DAYS - 1}
    ages[FILE_NAME] = KEEP_DAYS + 3  # the current file, untouched for weeks
    for name, days in ages.items():
        path = tmp_path / name
        path.write_text("Signed in: tess from 192.168.1.20\n")
        os.utime(path, (now - days * DAY, now - days * DAY))
    (tmp_path / "unrelated.txt").write_text("")
    os.utime(tmp_path / "unrelated.txt", (0, 0))
    removed = remove_old_logs(tmp_path, now)
    assert sorted(p.name for p in removed) == [FILE_NAME, f"{FILE_NAME}.old"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{FILE_NAME}.recent", "unrelated.txt"]


def test_old_files_are_removed_at_start_up(tmp_path: Path, clean_logging: None) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    old = folder / f"{FILE_NAME}.2026-01-01"
    old.write_text("old\n")
    os.utime(old, (0, 0))
    set_up_logging(tmp_path)
    assert not old.exists()


def test_data_folder_with_the_wrong_owner_still_logs_to_the_output(
    tmp_path: Path, clean_logging: None
) -> None:
    locked = tmp_path / "data"
    locked.mkdir(mode=0o500)  # like a /data that belongs to another user
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("running as root: permissions don't apply")
        assert set_up_logging(locked) is None
    finally:
        locked.chmod(0o700)
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1 and not isinstance(handlers[0], logs.DailyLogFile)


def test_a_failed_rotation_keeps_logging_in_the_same_file(
    tmp_path: Path, clean_logging: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_up_logging(tmp_path)
    handler = file_handler()
    logging.getLogger("mealwright.test").warning("Before")

    def refuse(self: Path, target: Path) -> Path:
        raise PermissionError("disk says no")

    monkeypatch.setattr(Path, "rename", refuse)
    tidy_once(handler, "2026-10-17")  # must not raise
    logging.getLogger("mealwright.test").warning("After")
    handler.flush()
    text = (tmp_path / "logs" / FILE_NAME).read_text()
    assert "Before" in text and "After" in text
    assert "Couldn't start a new log file" in text  # the problem is in the log too


def test_tidy_once_removes_old_files(tmp_path: Path, clean_logging: None) -> None:
    set_up_logging(tmp_path)
    old = tmp_path / "logs" / f"{FILE_NAME}.2026-01-01"
    old.write_text("old\n")
    os.utime(old, (0, 0))
    logging.getLogger("mealwright.test").warning("Today")
    tidy_once(file_handler(), "2026-10-17")
    assert not old.exists()
    assert (tmp_path / "logs" / f"{FILE_NAME}.2026-10-17").exists()


def test_rotate_after_close_does_nothing(tmp_path: Path, clean_logging: None) -> None:
    set_up_logging(tmp_path)
    handler = file_handler()
    handler.close()
    handler.rotate("2026-10-17")
    assert handler.stream is None


def test_an_old_logs_folder_is_tightened(tmp_path: Path, clean_logging: None) -> None:
    (tmp_path / "logs").mkdir(mode=0o755)
    set_up_logging(tmp_path)
    assert stat.S_IMODE((tmp_path / "logs").stat().st_mode) == 0o700


def test_sign_in_lines_stay_out_of_the_container_output(
    tmp_path: Path, clean_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    set_up_logging(tmp_path)
    logging.getLogger("mealwright.sign_in").info("Signed in: tess from 192.168.1.20")
    logging.getLogger("mealwright.sign_in").warning("Sign-in failed for unknown user from x")
    logging.getLogger("uvicorn.error").info("Application startup complete.")
    logging.getLogger("mealwright.main").warning("MEALWRIGHT_ALLOW_PLAIN_HTTP is on")
    logging.getLogger("mealwright.sign_in_other").error("Something broke")  # not sign-in
    file_handler().flush()
    output = capsys.readouterr().err
    assert "tess" not in output and "192.168.1.20" not in output
    assert "Sign-in failed" not in output
    assert "Application startup complete." in output
    assert "MEALWRIGHT_ALLOW_PLAIN_HTTP is on" in output
    assert "Something broke" in output
    text = (tmp_path / "logs" / FILE_NAME).read_text()
    assert "Signed in: tess from 192.168.1.20" in text
    assert "Application startup complete." in text


def test_every_sign_in_line_uses_the_sign_in_logger() -> None:
    from mealwright.api.v1 import account

    assert account.log.name == "mealwright.sign_in"
