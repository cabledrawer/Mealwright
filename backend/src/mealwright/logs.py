"""Mealwright's own log: errors and sign-ins only (spec section 7).

Log lines go to the container output and to a log file in the data folder,
`/data/logs/mealwright.log`. Each day just after midnight (UTC) the file is put aside as
`mealwright.log.YYYY-MM-DD` and a new one started, and files last written more than 14
days ago are deleted. This runs on a timer, not when a line is written, so on a quiet
server sign-in lines still go after 14 days. The file can be read by Mealwright's own
user only. "Report a problem" (0.8) will read recent errors from it. Nothing here is
ever sent anywhere.
"""

import logging
import os
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from io import TextIOWrapper
from pathlib import Path

KEEP_DAYS = 14
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

    def rotate(self, day: str) -> None:
        """Put the current file aside as mealwright.log.<day> and start a new one."""
        self.acquire()
        try:
            if self.stream:
                self.stream.close()
            current = Path(self.baseFilename)
            if current.exists() and current.stat().st_size:
                target = self.folder / f"{FILE_NAME}.{day}"
                if target.exists():  # put aside twice in one day: keep both
                    target = self.folder / f"{FILE_NAME}.{day}.{time.time_ns()}"
                current.rename(target)
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


def _keep_tidy(handler: DailyLogFile) -> None:
    """Background timer: just after each midnight (UTC), rotate and remove old files."""
    while True:
        now = datetime.now(UTC)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0)
        time.sleep((midnight - now).total_seconds())
        try:
            handler.rotate((midnight - timedelta(days=1)).date().isoformat())
            remove_old_logs(handler.folder)
        except OSError as error:
            logging.getLogger(__name__).error("Couldn't tidy the log folder: %s", error)


def set_up_logging(data_dir: Path) -> DailyLogFile | None:
    """Send our log lines (and the web server's errors) to the output and the log file."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    output = logging.StreamHandler(sys.stderr)
    output.setFormatter(formatter())
    root.addHandler(output)
    root.setLevel(logging.WARNING)
    logging.getLogger("mealwright").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    folder = data_dir / "logs"
    try:
        folder.mkdir(mode=0o700, exist_ok=True)
        remove_old_logs(folder)
        file = DailyLogFile(folder)
    except OSError as error:
        logging.getLogger(__name__).warning(
            "Can't write the log file in %s (%s); logging to the output only", folder, error
        )
        return None
    file.setFormatter(formatter())
    root.addHandler(file)
    threading.Thread(target=_keep_tidy, args=(file,), name="log-tidy", daemon=True).start()
    return file
