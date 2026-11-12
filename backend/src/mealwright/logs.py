"""Mealwright's own log: errors and sign-ins only (spec section 7).

Every line goes to a log file in the data folder, `/data/logs/mealwright.log`. The
container output (what `docker logs` shows) gets everything except sign-in lines, which
name an account or an address: in practice start-up messages, warnings and errors.
Docker keeps its copy by size, not age, so on a quiet server it could keep sign-in lines
for months (cabledrawer 17 Oct). Each day just after midnight (UTC) the file is put aside as
`mealwright.log.YYYY-MM-DD` and a new one started, and files last written more than 14
days ago are deleted. This runs as a scheduled job (mealwright.jobs), not when a line is
written, so on a quiet server sign-in lines still go after 14 days. The file can be read
by Mealwright's own user only. "Report a problem" reads recent errors from it
(mealwright.problem_report).
Nothing here is ever sent anywhere.
"""

import logging
import os
import sys
import time
from io import TextIOWrapper
from pathlib import Path

KEEP_DAYS = 14

# Lines that name an account or an address: log file only, never the container output.
SIGN_IN_LOGGER = "mealwright.sign_in"
FILE_NAME = "mealwright.log"

# 2026-10-17T18:21:50Z WARNING mealwright.api.v1.account: Sign-in failed for unknown user …
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def formatter() -> logging.Formatter:
    """Times in UTC, written as ISO 8601 with a Z, so they're the same on every server."""
    result = logging.Formatter(FORMAT, DATE_FORMAT)
    result.converter = time.gmtime
    return result


class DailyLogFile(logging.FileHandler):
    """The log file, readable by its owner only, put aside once a day by `rotate`."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        super().__init__(folder / FILE_NAME, encoding="utf-8")

    def _open(self) -> TextIOWrapper:
        descriptor = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(self.baseFilename, 0o600)  # an older file may have wider permissions
        return open(descriptor, "a", encoding=self.encoding)

    def close(self) -> None:
        self.acquire()
        try:
            self.closed_for_good = True
            super().close()
        finally:
            self.release()

    def rotate(self, day: str) -> None:
        """Put the current file aside as mealwright.log.<day> and start a new one.

        If putting it aside fails, logging carries on in the same file, and the error is
        raised for the caller to log.
        """
        self.acquire()
        try:
            if getattr(self, "closed_for_good", False):
                return  # shutting down
            if self.stream:
                self.stream.close()
                self.stream = None  # emit() reopens it on the next line
            try:
                current = Path(self.baseFilename)
                if current.exists() and current.stat().st_size:
                    target = self.folder / f"{FILE_NAME}.{day}"
                    if target.exists():  # put aside twice in one day: keep both
                        target = self.folder / f"{FILE_NAME}.{day}.{time.time_ns()}"
                    current.rename(target)
            finally:
                self.stream = self._open()
        finally:
            self.release()


def remove_old_logs(folder: Path, now: float | None = None) -> list[Path]:
    """Delete log files last written more than KEEP_DAYS days ago. Returns what went."""
    now = time.time() if now is None else now
    limit = now - KEEP_DAYS * 24 * 3600
    removed = []
    for path in folder.glob(f"{FILE_NAME}*"):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
                removed.append(path)
        except OSError:
            continue
    return removed


def set_aside_stale(folder: Path, now: float | None = None) -> Path | None:
    """At start-up: if the current file was last written before today (UTC), put it aside
    under the day it was last written. A server that was asleep or stopped at midnight
    then still keeps the 14-day promise: the file gets its date and is deleted on time."""
    current = folder / FILE_NAME
    now = time.time() if now is None else now
    try:
        written = current.stat().st_mtime
    except OSError:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(written))
    if day >= time.strftime("%Y-%m-%d", time.gmtime(now)):
        return None
    target = folder / f"{FILE_NAME}.{day}"
    if target.exists():
        target = folder / f"{FILE_NAME}.{day}.{time.time_ns()}"
    current.rename(target)
    return target


def tidy_once(handler: DailyLogFile, day: str) -> None:
    """Put the day's file aside and remove old ones. Never raises: a problem is logged."""
    try:
        handler.rotate(day)
    except Exception:
        logging.getLogger(__name__).exception("Couldn't start a new log file")
    try:
        remove_old_logs(handler.folder)
    except Exception:
        logging.getLogger(__name__).exception("Couldn't remove old log files")


def not_sign_in(record: logging.LogRecord) -> bool:
    """Filter for the container output: leaves out sign-in lines."""
    return not (record.name == SIGN_IN_LOGGER or record.name.startswith(SIGN_IN_LOGGER + "."))


def set_up_logging(data_dir: Path) -> DailyLogFile | None:
    """Send our log lines (and the web server's errors) to the output and the log file."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    output = logging.StreamHandler(sys.stderr)
    output.setFormatter(formatter())
    output.addFilter(not_sign_in)
    root.addHandler(output)
    root.setLevel(logging.WARNING)
    logging.getLogger("mealwright").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    folder = data_dir / "logs"
    try:
        folder.mkdir(mode=0o700, exist_ok=True)
        folder.chmod(0o700)  # also tighten a folder made before 0.1.1
        set_aside_stale(folder)
        remove_old_logs(folder)
        file = DailyLogFile(folder)
    except OSError as error:
        logging.getLogger(__name__).error(
            "Can't write the log file in %s (%s): sign-in lines aren't being kept", folder, error
        )
        return None
    file.setFormatter(formatter())
    root.addHandler(file)
    # Tidied each night by the app's scheduler (mealwright.jobs).
    return file
