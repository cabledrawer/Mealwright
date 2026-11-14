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
  day are accepted (cabledrawer 12 Nov)). A job looks every 10 minutes whether one is due: the last slot
  that has passed has no backup yet. A server that was off at 03:00 backs up when it starts.
  After a failure it tries again an hour later, not every 10 minutes.
- **Names:** `backup-<UTC date>-<UTC time>.db`. Only these are trimmed to the number kept. The
  copies made before a database upgrade (`pre-upgrade-…`, mealwright.migrate) and the one made
  before "Delete everything" (`before-delete-everything-…`) are never touched by the trim.
  No copy ever replaces another: a second backup in the same second leaves the first one;
  a second safety copy in the same second gets `-2` (then `-3`…) before `.db`.
- **Photos (0.9.5 step 16f, D2; cabledrawer 13 Nov):** recipe photos are files in
  `/data/photos/<household id>/`, not in the database. By default every copy (a backup, the safety
  copy before an upgrade, the one before "Delete everything") also gets a folder beside its `.db`
  named like it with `-photos` in place of `.db` (`backup-<stamp>-photos/`), holding the same
  `<household id>/<file>` layout. A photo file is never changed once written (it is written under
  another name and renamed, and deleted whole), so the folder holds **hard links** to the live
  files: no extra disk for photos that haven't changed, a photo deleted later stays in the older
  backups, and restore is one `cp -an`. Where a hard link can't be made (another disk or a share
  that can't), the file is copied instead. The household's switch "Include photos" (off) leaves the
  folder out. No photos on the server, no folder.
  **Consistent while in use:** the photo files are linked first, then the database is copied
  (SQLite's online backup, which holds only a read lock while it runs), then the photo folder is
  looked at once more for any photo added meanwhile. So every photo the copied database points to
  is in the folder, a photo added or deleted while it runs breaks nothing, and the database's
  write lock is never held while photos are copied. The folder is made under another name and
  renamed first; the `.db` is put in place last, and it is what makes a backup count: a failure
  (a full disk, say) removes everything made so far and leaves the older backups alone.
  **The one gap:** a photo saved and then deleted again within the few milliseconds between the
  first look and the second, while the database copy that points to it is made, can be in that
  database and not in the folder; restoring shows it as a missing photo, as any lost file.
  Symbolic links in the photo folder are never followed (skipped, as `photos.sweep_files` does).

Nothing here makes a network connection.
"""

import errno
import logging
import os
import re
import shutil
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
WEEKLY_ON = 0  # Monday (cabledrawer 12 Nov)
RETRY_AFTER = timedelta(hours=1)

BACKUP_NAME = re.compile(r"^backup-(\d{8}-\d{6})\.db$")
# Every kind of copy that can have a photo folder: a backup, the copy before Delete everything,
# the safety copy before an upgrade (mealwright.migrate.SAFETY_COPY_NAME has the same shape).
ANY_COPY = re.compile(
    r"^(?:backup-\d{8}-\d{6}|before-delete-everything-\d{8}-\d{6}(?:-\d+)?"
    r"|pre-upgrade-[0-9A-Za-z_]+-\d{8}-\d{6}(?:-\d+)?)\.db$"
)
# A photo folder beside a backup, and the half-made one (`.<pid>.part`, mealwright.migrate too).
PHOTOS_SUFFIX = "-photos"
_PHOTOS_PART = re.compile(r"^(?P<stem>.+)-photos\.(?P<pid>\d+)\.part$")
# The photo files the app writes (mealwright.photos): never anything else is copied.
_PHOTO_FILE = re.compile(r"^[0-9a-f]{32}(-list)?\.jpg$")
BEFORE_DELETE = "before-delete-everything"
_STAMP = "%Y%m%d-%H%M%S"

# One backup at a time: the job and "Back up now" never write at once.
# Re-entrant: `back_up` holds it and trims while it does, and `trim` takes it for itself.
_ONE_AT_A_TIME = threading.RLock()

# The photo folders being made in this process right now (their half-made and final names), so
# a sweep never removes one that is in the making. Known by this marker, not by the process ID:
# in Docker the app is PID 1 on every start, so a half-made folder left by a killed run has the
# same PID as the new one.
_MAKING: set[str] = set()
_MAKING_LOCK = threading.Lock()


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


def photo_store(folder: Path) -> Path:
    """The live photo files (`/data/photos`), beside the backups folder (`/data/backups`)."""
    return folder.parent / "photos"


def make_folder(folder: Path) -> None:
    """The backups folder, only Mealwright's own user can open it (0700)."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)  # also tighten a folder made before 0.9


def photos_beside(copy: Path) -> Path:
    """The folder of photos that goes with a database copy: `backup-X.db` has `backup-X-photos`."""
    return copy.with_name(copy.name.removesuffix(".db") + PHOTOS_SUFFIX)


def photo_files(store: Path, household_id: int | None = None) -> list[Path]:
    """Every photo file under `store` (`<household id>/<file>`), as paths relative to it; with
    `household_id`, only that household's."""
    found = []
    try:
        households = [
            p
            for p in store.iterdir()
            if p.name.isdigit()
            and (household_id is None or int(p.name) == household_id)
            and p.is_dir()
            and not p.is_symlink()
        ]
    except OSError:  # no photos yet
        return []
    for household in households:
        try:
            for path in household.iterdir():
                # Never a symbolic link (as `photos.sweep_files`): its target could be any file.
                if _PHOTO_FILE.match(path.name) and path.is_file() and not path.is_symlink():
                    found.append(path.relative_to(store))
        except OSError:
            continue
    return found


def photos_size(folder: Path, household_id: int | None = None) -> int:
    """The bytes of the photo files in `folder` (a store or a backup's photo folder), as their
    sizes say: a hard link counts in full, so this is what a copy of them would take. With
    `household_id`, only that household's."""
    total = 0
    for relative in photo_files(folder, household_id):
        try:
            total += (folder / relative).stat().st_size
        except OSError:
            continue
    return total


def _add_photos(store: Path, into: Path, have: set[Path]) -> None:
    """Put each photo file of `store` not in `have` into `into`: a hard link, or a copy where
    the folder can't make one. A file deleted meanwhile is skipped. The folders are 0700 and a
    copy 0600 (a link keeps the live file's own mode). Other errors (a full disk) are raised."""
    for relative in photo_files(store):
        if relative in have:
            continue
        target = into / relative
        target.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            os.link(store / relative, target, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except FileExistsError:
            pass
        except OSError as error:
            if error.errno in (errno.ENOSPC, errno.EDQUOT):
                raise
            try:
                _copy_file(store / relative, target)
            except FileNotFoundError:
                target.unlink(missing_ok=True)
                continue
            except OSError as again:
                target.unlink(missing_ok=True)
                if again.errno == errno.ELOOP:  # became a symbolic link meanwhile: left out
                    continue
                raise
        if target.is_symlink():  # a link put there meanwhile, and linked as it is: left out
            target.unlink(missing_ok=True)
            continue
        have.add(relative)


def _copy_file(source: Path, target: Path) -> None:
    """Copy a photo file to `target` (0600), never following a symbolic link: a link put in
    place of the file meanwhile is refused (ELOOP), not copied."""
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as reading, open(target, "xb") as writing:
        shutil.copyfileobj(reading, writing)
    target.chmod(0o600)


def _drop(path: Path) -> None:
    """Remove a file or a folder of photos (hard links go; the live files stay)."""
    with suppress(OSError):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def remove_copy(path: Path) -> bool:
    """Delete a database copy and the photo folder beside it. Never raises: what can't be removed
    is logged, in a line that names the file only. True when both are gone."""
    gone = True
    for each in (path, photos_beside(path)):
        try:
            if each.is_dir() and not each.is_symlink():
                shutil.rmtree(each)
            else:
                each.unlink(missing_ok=True)
        except OSError as error:
            gone = False
            log.warning("Couldn't remove the old copy %s: %s", each.name, error)
    return gone


def tidy_photo_folders(folder: Path) -> None:
    """Delete photo folders that no finished copy owns: half-made ones (`.part`, whoever's) and
    finished ones whose `.db` is gone, for every kind of copy (ANY_COPY). Not one being made in
    this process right now. Takes the one-at-a-time lock, so it never runs between a copy's photo
    folder being put in place and its `.db` arriving. Never raises."""
    with _ONE_AT_A_TIME:
        try:
            entries = list(folder.iterdir())
        except OSError:
            return
        names = {entry.name for entry in entries}
        with _MAKING_LOCK:
            making = set(_MAKING)
        for entry in entries:
            if entry.name in making or not entry.is_dir() or entry.is_symlink():
                continue
            part = _PHOTOS_PART.match(entry.name)
            if part:
                if ANY_COPY.match(part["stem"] + ".db"):
                    _drop(entry)
                continue
            db_name = entry.name.removesuffix(PHOTOS_SUFFIX) + ".db"
            owned = db_name in names or not ANY_COPY.match(db_name)
            if entry.name.endswith(PHOTOS_SUFFIX) and not owned:
                _drop(entry)


def copy_database(engine: Engine, target: Path, photos: Path | None = None) -> None:
    """Copy the database to `target` with SQLite's online backup, as one file readable by its
    owner only. Written as `<target>.<pid>.part` first and put in place when complete. Never
    replaces a file already there, even one that appears while the copy is written: raises
    FileExistsError instead (review r1: a second copy in the same second must never replace a
    good one). Raises OSError or sqlite3.Error; a half-written file is removed.

    With `photos` (the folder of photo files) and at least one photo in it, the photos go in a
    folder beside the copy first (see the module's note, "Photos"): everything made so far is
    removed if any step fails, and the `.db` is put in place last."""
    if target.exists():
        raise FileExistsError(errno.EEXIST, "A copy with that name is already there")
    partial = target.with_name(f"{target.name}.{os.getpid()}.part")
    final_photos = photos_beside(target)
    photos_part = final_photos.with_name(f"{final_photos.name}.{os.getpid()}.part")
    placed_photos = False
    with _MAKING_LOCK:
        _MAKING.update({final_photos.name, photos_part.name})
    try:
        partial.unlink(missing_ok=True)
        _drop(photos_part)
        have: set[Path] = set()
        if photos is not None:
            photos_part.mkdir(mode=0o700)
            _add_photos(photos, photos_part, have)  # before the database copy: see the note
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
        if photos is not None:
            # A photo added while the database was copied: the copy may point to it.
            _add_photos(photos, photos_part, have)
        if photos_part.is_dir() and not any(p.is_file() for p in photos_part.rglob("*")):
            _drop(photos_part)  # no photos at all: no folder
        if photos_part.is_dir():
            if final_photos.exists():  # another copy's, or one left unfinished: not ours to take
                raise FileExistsError(errno.EEXIST, "A copy with that name is already there")
            photos_part.rename(final_photos)
            placed_photos = True
        _put_in_place(partial, target)
    except BaseException:
        with suppress(OSError):
            partial.unlink(missing_ok=True)
        _drop(photos_part)
        if placed_photos:
            _drop(final_photos)
        raise
    finally:
        with _MAKING_LOCK:
            _MAKING.difference_update({final_photos.name, photos_part.name})


def _put_in_place(partial: Path, target: Path) -> None:
    """Give the finished copy its name, never over a file already there. A hard link fails
    by itself when the name is taken; a folder that can't make hard links (some network
    shares) gets a rename after a last look."""
    try:
        os.link(partial, target)
    except FileExistsError:
        raise
    except OSError:
        if target.exists():
            raise FileExistsError(errno.EEXIST, "A copy with that name is already there") from None
        partial.replace(target)
        return
    partial.unlink()


def copy_to_free_name(engine: Engine, folder: Path, stem: str, photos: Path | None = None) -> Path:
    """Copy the database to `<stem>.db` in `folder`, or `<stem>-2.db`, `<stem>-3.db`… when
    that name is taken (two copies in the same second), so no copy ever replaces another."""
    for number in range(1, 1000):
        target = folder / (f"{stem}.db" if number == 1 else f"{stem}-{number}.db")
        if target.exists():
            continue
        try:
            copy_database(engine, target, photos)
        except FileExistsError:
            continue  # taken while this copy was written: try the next name
        return target
    raise FileExistsError(errno.EEXIST, "Too many copies with the same time in their name")


@dataclass(frozen=True)
class Backup:
    path: Path
    made_at: datetime  # UTC, from the name
    size: int  # bytes of the database file
    photos: bool = False  # a photo folder is beside it


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
        found.append(
            Backup(path=path, made_at=made, size=size, photos=photos_beside(path).is_dir())
        )
    found.sort(key=lambda backup: backup.made_at, reverse=True)
    return found


def trim(folder: Path, keep: int) -> list[Path]:
    """Delete Mealwright's own backups beyond the newest `keep`, and tidy the photo folders no
    copy owns. Returns what went. Holds the one-at-a-time lock (a backup being made waits for it,
    and `back_up`, which holds the lock itself, can call this)."""
    gone = []
    with _ONE_AT_A_TIME:
        for backup in backups(folder)[max(keep, 1) :]:
            if remove_copy(backup.path):
                gone.append(backup.path)
        tidy_photo_folders(folder)
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


def back_up(
    engine: Engine,
    folder: Path,
    keep: int,
    now: datetime | None = None,
    photos: Path | None = None,
) -> Backup:
    """Make one backup now and trim the old ones to `keep`. `photos` is the folder of photo files
    to include (None: the database only). Raises BackupFailed in plain words."""
    if sqlite_file(engine) is None:
        raise BackupFailed("Backups need Mealwright’s own database file.")
    with _ONE_AT_A_TIME:
        at = (now or utcnow()).astimezone(UTC)
        target = folder / f"backup-{at.strftime(_STAMP)}.db"
        try:
            make_folder(folder)
            # Two in the same second: the first one stands, and is never replaced.
            with suppress(FileExistsError):
                copy_database(engine, target, photos)
            size = target.stat().st_size
        except (OSError, sqlite3.Error) as error:
            raise BackupFailed(_plain(error)) from error
        trim(folder, keep)
    log.info("Backed up the database: %s", target.name)
    return Backup(
        path=target,
        made_at=at.replace(microsecond=0),
        size=size,
        photos=photos_beside(target).is_dir(),
    )


def before_delete_everything(
    engine: Engine, folder: Path, now: datetime | None = None, photos: Path | None = None
) -> Path:
    """The safety backup made before "Delete everything" (cabledrawer 12 Nov), with the photos when
    `photos` is given (D2, 0.9.5), so a restore brings them back. The caller always gives them,
    whatever the Include photos switch says (proposed, for cabledrawer): Delete everything removes the
    photos for good, so this copy is the only way back. Never trimmed."""
    if sqlite_file(engine) is None:
        raise BackupFailed("Backups need Mealwright’s own database file.")
    with _ONE_AT_A_TIME:
        at = (now or utcnow()).astimezone(UTC)
        try:
            make_folder(folder)
            target = copy_to_free_name(
                engine, folder, f"{BEFORE_DELETE}-{at.strftime(_STAMP)}", photos
            )
        except (OSError, sqlite3.Error) as error:
            raise BackupFailed(_plain(error)) from error
    log.info("Backed up the database before deleting everything: %s", target.name)
    return target


_DELETE_NAME = re.compile(rf"^{BEFORE_DELETE}-(\d{{8}}-\d{{6}})(?:-\d+)?\.db$")


def last_delete_everything(folder: Path) -> datetime | None:
    """When the latest "Delete everything" of any household was done (by its safety backup,
    which is never trimmed and stays in the backups folder), or None. The log holds every
    household's lines, so a report leaves out all lines from before this (cabledrawer 12 Nov)."""
    try:
        names = [path.name for path in folder.iterdir()]
    except OSError:
        return None
    stamps = [m.group(1) for name in names if (m := _DELETE_NAME.match(name))]
    if not stamps:
        return None
    return datetime.strptime(max(stamps), _STAMP).replace(tzinfo=UTC)


def _plain(error: BaseException) -> str:
    """What went wrong, short. An OSError says which (the disk is full, no permission); the
    folder is always the backups folder, so its path isn't repeated."""
    if isinstance(error, OSError) and error.strerror:
        why = error.strerror
    else:
        why = str(error) or type(error).__name__
    return f"The backup couldn’t be written ({why[:200]})."


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
            photos = photo_store(folder) if household.backup_photos else None
        except Exception:
            log.exception("Couldn't check whether a backup is due (will look again soon)")
            return None
        try:
            made = back_up(engine, folder, keep, now, photos)
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
