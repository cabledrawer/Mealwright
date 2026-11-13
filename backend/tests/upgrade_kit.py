"""Helpers for the upgrade tests: the saved old databases (`upgrade/databases/<tag>.sqlite`,
one per earlier 0.x release; see `upgrade/README.md`) brought up to the newest layout.

`upgrade_copy` is what a start-up does to an old install: a copy of the file, then the app's
own migrations with its safety copy. Later tests that need a database from a real 0.9 install
use the `upgraded_09_db` fixture (conftest.py)."""

import shutil
import sqlite3
from pathlib import Path

from mealwright import migrate
from mealwright.config import Settings
from mealwright.db import make_engine

DATABASES = Path(__file__).parent / "upgrade" / "databases"
# Every saved database, oldest first. Each stands for a real install of that release.
TAGS = sorted(
    (path.stem for path in DATABASES.glob("*.sqlite")),
    key=lambda tag: [int(part) for part in tag[1:].split("-")[0].split(".")] + [-tag.count("-")],
)
FIXTURE_09 = "v0.9.0-beta.1"
# The admin every saved database has.
ADMIN = {"username": "sam", "password": "correct horse battery"}


def copy_of(tag: str, data_dir: Path) -> Path:
    """A copy of that release's saved database as `data_dir`/mealwright.db."""
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "mealwright.db"
    shutil.copyfile(DATABASES / f"{tag}.sqlite", target)
    return target


def upgrade_copy(tag: str, data_dir: Path) -> Path:
    """Copy the saved database and upgrade it the way a start-up does (with a safety copy in
    the backups folder). The file is left folded into one (no -wal beside it)."""
    path = copy_of(tag, data_dir)
    engine = make_engine(f"sqlite:///{path}")
    try:
        migrate.upgrade(engine, backups=data_dir / "backups")
    finally:
        engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


def settings_for(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, run_jobs=False)
