"""One "now" and one rule for a stored time's zone (0.9.5-beta.3, D4, BE23).

`models.utcnow()` is now (the browser tests move it), `models.machine_now()` the machine's own
clock for the scheduler and the log files, and `models.as_utc()` the one place that gives a time
read back from SQLite its zone. No other module reads the clock or writes the rule again.
"""

import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from mealwright.models import as_utc

SOURCE = Path(__file__).parent.parent / "src" / "mealwright"

# Only these may read the machine's clock straight: models.py (where utcnow and machine_now
# live) and the migrations, which run before the app and stamp what they write.
CLOCK_READERS = {"models.py"}


def _app_files() -> list[Path]:
    return [p for p in SOURCE.rglob("*.py") if "migrations" not in p.parts]


def test_only_models_reads_the_clock() -> None:
    for path in _app_files():
        if path.name in CLOCK_READERS:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"datetime\.(now|utcnow|today)\(", text), path
        assert not re.search(r"\bdate\.today\(", text), path
        # `time.time()` stays where it is compared with the machine's own seconds: file times
        # (logs.py, photos.py) and a sign-in server's token times (sso.py).


def test_no_module_writes_the_zone_rule_again() -> None:
    for path in _app_files():
        if path.name == "models.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"def _?(as_utc|utc|aware_utc)\(", text), path
        # "A zoneless time is UTC", written inline.
        assert not re.search(r"\.tzinfo (is None|else)", text), path
        assert not re.search(r"if \w+\.tzinfo\b", text), path


def test_as_utc_gives_a_zoneless_time_utc_and_turns_others_into_utc() -> None:
    naive = datetime(2026, 11, 20, 10, 0)
    assert as_utc(naive) == datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    assert as_utc(naive).tzinfo is UTC
    two_ahead = datetime(2026, 11, 20, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert as_utc(two_ahead) == datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    assert as_utc(two_ahead).isoformat() == "2026-11-20T10:00:00+00:00"
