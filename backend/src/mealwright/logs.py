"""Mealwright's own log: errors and sign-ins only (spec section 7).

Log lines go to the container output and to a log file in the data folder,
`/data/logs/mealwright.log`. The file starts afresh at midnight (UTC) and the last 14 days
are kept, so the app itself keeps the spec's "logs kept for 14 days" whatever Docker does
with its own copy. The file is also what Settings → About → "Report a problem" will read
recent errors from (0.8). Nothing here is ever sent anywhere.
"""

import logging
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

KEEP_DAYS = 14

# 2026-10-17T18:21:50Z WARNING mealwright.api.v1.account: Sign-in failed for unknown user …
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def formatter() -> logging.Formatter:
    """Times in UTC, written as ISO 8601 with a Z, so they're the same on every server."""
    result = logging.Formatter(FORMAT, DATE_FORMAT)
    result.converter = time.gmtime
    return result


def set_up_logging(data_dir: Path) -> None:
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
        folder.mkdir(exist_ok=True)
        file = TimedRotatingFileHandler(
            folder / "mealwright.log",
            when="midnight",
            backupCount=KEEP_DAYS,
            utc=True,
            encoding="utf-8",
        )
    except OSError as error:
        logging.getLogger(__name__).warning(
            "Can't write the log file in %s (%s); logging to the output only", folder, error
        )
        return
    file.setFormatter(formatter())
    root.addHandler(file)
