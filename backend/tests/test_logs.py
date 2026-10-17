import logging
from collections.abc import Iterator
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest

from mealwright.logs import KEEP_DAYS, formatter, set_up_logging


@pytest.fixture
def clean_root() -> Iterator[None]:
    root = logging.getLogger()
    saved, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in saved:
        root.addHandler(handler)
    root.setLevel(level)


def test_log_lines_carry_a_utc_timestamp() -> None:
    record = logging.LogRecord("mealwright", logging.WARNING, "", 0, "Hello", None, None)
    record.created = 0.0
    line = formatter().format(record)
    assert line == "1970-01-01T00:00:00Z WARNING mealwright: Hello"


def test_log_file_kept_14_days(tmp_path: Path, clean_root: None) -> None:
    set_up_logging(tmp_path)
    files = [h for h in logging.getLogger().handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(files) == 1
    assert KEEP_DAYS == 14
    assert files[0].backupCount == 14 and files[0].when == "MIDNIGHT" and files[0].utc
    logging.getLogger("mealwright.test").warning("Something went wrong")
    files[0].flush()
    text = (tmp_path / "logs" / "mealwright.log").read_text()
    assert text.endswith("WARNING mealwright.test: Something went wrong\n")
    assert text[:4].isdigit() and "Z WARNING" in text


def test_unwritable_data_folder_still_logs_to_the_output(tmp_path: Path, clean_root: None) -> None:
    blocked = tmp_path / "file-not-folder"
    blocked.write_text("")
    set_up_logging(blocked)  # can't make blocked/logs
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1 and not isinstance(handlers[0], TimedRotatingFileHandler)
