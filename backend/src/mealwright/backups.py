"""Mealwright's own backups of its database (spec section 7, "Backups", cabledrawer 17 Oct).

Daily by default, into the data folder (`/data/backups/`), keeping the last 7; how often and how
many are household settings an admin can change. Nothing leaves the server: the person's own
backup tools can copy the folder from there.

- **How a backup is made:** SQLite's own online backup, which gives a consistent copy while
  Mealwright is in use (writes carry on meanwhile). The copy is a single file that opens on its
  own (a plain journal, no `-wal` or `-shm` beside it). It is written under another name first and
  renamed when complete, so a half-written backup never counts. Files are readable by Mealwright's
  own user only (0600), in a folder only it can open (0700).
- **When:** at 03:00 in the household's own time (UTC until the browser has said which):
  "daily" every day, "twice-daily" at 03:00 and 15:00, "weekly" on Mondays (the choices and the
  day are proposed, for cabledrawer). A job looks every 10 minutes whether one is due: the last slot
  that has passed has no backup yet. A server that was off at 03:00 backs up when it starts.
  After a failure it tries again an hour later, not every 10 minutes.
- **Names:** `backup-<UTC date>-<UTC time>.db`. Only these are trimmed to the number kept. The
  copies made before a database upgrade (`pre-upgrade-…`, mealwright.migrate) and the one made
  before "Delete everything" (`before-delete-everything-…`) are never touched by the trim.
- **Photos** are files in `/data/photos`, not in the database: a copy of the whole data folder
  carries them; Mealwright's own backup is the database (docs/restore.md).

Nothing here makes a network connection.
"""

import logging
import os
import re
import sqlite3
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from mealwright.household import zone
from mealwright.models import Household, utcnow

log = logging.getLogger(__name__)

FOLDER = "backups"
EVERY = ("daily", "twice-daily", "weekly")
KEEP_DEFAULT = 7
KEEP_MOST = 30
AT = time(3, 0)  # 03:00 in the household's own time
WEEKLY_ON = 0  # Monday (proposed, for cabledrawer)
RETRY_AFTER = timedelta(hours=1)

BACKUP_NAME = re.compile(r"^backup-(\d{8}-\d{6})\.db$")
BEFORE_DELETE = "before-delete-everything"
_STAMP = "%Y%m%d-%H%M%S"

# One backup at a time: the job and "Back up now" never write at once.
_ONE_AT_A_TIME = threading.Lock()


class BackupFailed(RuntimeError):
    """The backup couldn't be made. Its message is in plain words, with no content in it."""


def sqlite_file(engine: Engine) -> Path | None:
    """The database file, or None when it isn't a SQLite file (in memory, or not SQLite)."""
    if engine.dialect.name != "sqlite":
        return None
    database = engine.url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return None
    return Path(database)


def make_folder(folder: Path) -> None:
    """The backups folder, only Mealwright's own user can open it (0700)."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)  # also tighten a folder made before 0.9


def copy_database(engine: Engine, target: Path) -> None:
    """Copy the database to `target` with SQLite's online backup, as one file readable by its
    owner only. Written as `<target>.<pid>.part` first and renamed when complete. Raises OSError
    or sqlite3.Error; a half-written file is removed."""
    partial = target.with_name(f"{target.name}.{os.getpid()}.part")
    try:
        partial.unlink(missing_ok=True)
        # Made empty and owner-only first: SQLite takes an empty file as a new database, and
        # the copy never exists with wider permissions, even for a moment.
        os.close(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        raw = engine.raw_connection()
        try:
            source = raw.driver_connection
            if not isinstance(source, sqlite3.Connection):
                raise sqlite3.Error("not a SQLite connection")
            copy = sqlite3.connect(partial)
            try:
                source.backup(copy)
                # The copy keeps the source's WAL mode; a plain journal makes it one file that
                # opens on its own, with no "-wal" or "-shm" files appearing beside it.
                copy.execute("PRAGMA journal_mode=DELETE")
            finally:
                copy.close()
        finally:
            raw.close()
        partial.chmod(0o600)
        partial.replace(target)
    except BaseException:
        with suppress(OSError):
            partial.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class Backup:
    path: Path
    made_at: datetime  # UTC, from the name
    size: int  # bytes


def backups(folder: Path) -> list[Backup]:
    """Mealwright's own backups in the folder, newest first (not the other copies)."""
    found = []
    try:
        paths = list(folder.iterdir())
    except OSError:  # no folder yet, or something else in its place
        return []
    for path in paths:
        match = BACKUP_NAME.match(path.name)
        if not match:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        made = datetime.strptime(match.group(1), _STAMP).replace(tzinfo=UTC)
        found.append(Backup(path=path, made_at=made, size=size))
    found.sort(key=lambda backup: backup.made_at, reverse=True)
    return found


def trim(folder: Path, keep: int) -> list[Path]:
    """Delete Mealwright's own backups beyond the newest `keep`. Returns what went."""
    gone = []
    for backup in backups(folder)[max(keep, 1) :]:
        try:
            backup.path.unlink(missing_ok=True)
            gone.append(backup.path)
        except OSError as error:
            log.warning("Couldn't remove the old backup %s: %s", backup.path.name, error)
    return gone


def last_slot(household: Household, now: datetime) -> datetime:
    """The most recent time a backup was due (UTC), from the household's choice and time zone."""
    here = zone(household)
    local = now.astimezone(here)
    every = household.backup_every if household.backup_every in EVERY else "daily"
    slots = [AT]
    if every == "twice-daily":
        slots = [AT, time(AT.hour + 12, AT.minute)]
    day = local.date()
    for _ in range(9):  # a week and a bit always holds a slot
        if every != "weekly" or day.weekday() == WEEKLY_ON:
            for at in sorted(slots, reverse=True):
                slot = datetime.combine(day, at, tzinfo=here)
                if slot <= local:
                    return slot.astimezone(UTC)
        day -= timedelta(days=1)
    raise AssertionError("no backup slot in the last 9 days")  # pragma: no cover


def is_due(household: Household, folder: Path, now: datetime) -> bool:
    """A backup is due when the last slot that has passed has none yet, unless the last try
    failed less than an hour ago."""
    problem_at = household.backup_problem_at
    if problem_at is not None:
        if problem_at.tzinfo is None:
            problem_at = problem_at.replace(tzinfo=UTC)
        if now - problem_at < RETRY_AFTER:
            return False
    newest = backups(folder)
    return not newest or newest[0].made_at < last_slot(household, now)


def back_up(engine: Engine, folder: Path, keep: int, now: datetime | None = None) -> Backup:
    """Make one backup now and trim the old ones to `keep`. Raises BackupFailed in plain words."""
    if sqlite_file(engine) is None:
        raise BackupFailed("Backups need Mealwright's own database file.")
    with _ONE_AT_A_TIME:
        at = (now or utcnow()).astimezone(UTC)
        target = folder / f"backup-{at.strftime(_STAMP)}.db"
        try:
            make_folder(folder)
            if not target.exists():  # two in the same second: the first one stands
                copy_database(engine, target)
            size = target.stat().st_size
        except (OSError, sqlite3.Error) as error:
            raise BackupFailed(_plain(error)) from error
        trim(folder, keep)
    log.info("Backed up the database: %s", target.name)
    return Backup(path=target, made_at=at.replace(microsecond=0), size=size)


def before_delete_everything(engine: Engine, folder: Path, now: datetime | None = None) -> Path:
    """The safety backup made before "Delete everything" (proposed, for cabledrawer). Never trimmed."""
    if sqlite_file(engine) is None:
        raise BackupFailed("Backups need Mealwright's own database file.")
    with _ONE_AT_A_TIME:
        at = (now or utcnow()).astimezone(UTC)
        target = folder / f"{BEFORE_DELETE}-{at.strftime(_STAMP)}.db"
        try:
            make_folder(folder)
            copy_database(engine, target)
        except (OSError, sqlite3.Error) as error:
            raise BackupFailed(_plain(error)) from error
    log.info("Backed up the database before deleting everything: %s", target.name)
    return target


def _plain(error: BaseException) -> str:
    """What went wrong, short. An OSError says which (the disk is full, no permission); the
    folder is always the backups folder, so its path isn't repeated."""
    if isinstance(error, OSError) and error.strerror:
        why = error.strerror
    else:
        why = str(error) or type(error).__name__
    return f"The backup couldn't be written ({why[:200]})."


def run_if_due(
    factory: sessionmaker[Session], engine: Engine, folder: Path, now: datetime | None = None
) -> Backup | None:
    """The scheduled job: back up if one is due, and note how it went. Never raises."""
    now = now or utcnow()
    with factory() as db:
        try:
            household = db.scalars(select(Household).order_by(Household.id)).first()
            if household is None or not is_due(household, folder, now):
                return None
            keep = household.backup_keep
        except Exception:
            log.exception("Couldn't check whether a backup is due (will look again soon)")
            return None
        try:
            made = back_up(engine, folder, keep, now)
        except BackupFailed as error:
            log.error("%s It will be tried again in an hour.", error)
            note_problem(db, household, str(error), now)
            return None
        except Exception:
            log.exception("The backup failed (will try again in an hour)")
            note_problem(db, household, "The backup failed. The log says why.", now)
            return None
        note_problem(db, household, None, now)
        return made


def note_problem(
    db: Session, household: Household, problem: str | None, now: datetime | None = None
) -> None:
    """Remember the last problem (or that there's none now). Never raises."""
    try:
        if problem is None and household.backup_problem is None:
            return
        household.backup_problem = problem[:300] if problem else None
        household.backup_problem_at = (now or utcnow()) if problem else None
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Couldn't note how the backup went")
