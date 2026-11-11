"""Run database migrations from code (on start-up and in tests)."""

import logging
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

from mealwright.backups import copy_database, make_folder, sqlite_file

log = logging.getLogger(__name__)

# How many safety copies are kept (spec section 6, "Decided for 0.7.0 and 0.7.1").
SAFETY_COPIES_KEPT = 3
# pre-upgrade-<revision>-<UTC date and time>.db, e.g. pre-upgrade-c5f1b8d2a763-20261030-142501.db
SAFETY_COPY_NAME = re.compile(r"^pre-upgrade-([0-9A-Za-z_]+)-(\d{8}-\d{6})\.db$")
# cabledrawer 31 Oct ("K1's 'upgrade-failed' note: OK"; 0.7 K1 review): while an upgrade hasn't yet
# worked, this file in the backups folder names the clean copy made before it. A start-up that finds
# it makes no new copy (on SQLite a failed migration can leave the database half-upgraded, so a new
# copy could be half-upgraded too), and that clean copy is never trimmed: not while the upgrade
# keeps failing, and not on the trim after it finally works.
PART_NAME = re.compile(r"^pre-upgrade-[0-9A-Za-z_]+-\d{8}-\d{6}\.db\.(\d+)\.part$")
UPGRADE_FAILED = "upgrade-failed"


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "mealwright:migrations")
    return config


@contextmanager
def foreign_keys_off(connection: Connection) -> Iterator[None]:
    """On SQLite, switch foreign keys off while migrating.

    Batch migrations rebuild a table to change it (copy, drop, rename). With foreign keys
    on, dropping the old copy of a parent table counts as deleting its rows, and ON DELETE
    CASCADE would then delete every row that points at it: changing `household` would
    delete every login. SQLite's own advice is to switch foreign keys off for this. It
    can only be changed outside a transaction. Afterwards every foreign key is checked.
    """
    if connection.dialect.name != "sqlite":
        yield
        return
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    try:
        yield
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(f"Migration left broken links between tables: {broken[:5]}")
        connection.commit()
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def _run(engine: Engine, action: str, revision: str) -> None:
    config = alembic_config()
    with engine.connect() as connection, foreign_keys_off(connection):
        config.attributes["connection"] = connection
        if action == "upgrade":
            command.upgrade(config, revision)
        else:
            command.downgrade(config, revision)
        connection.commit()


class SafetyCopyFailed(RuntimeError):
    """The database couldn't be copied before an upgrade, so it was not upgraded."""


def current_revision(engine: Engine) -> str | None:
    """The database's migration revision. None: a new, empty database."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def safety_copy(engine: Engine, backups: Path, now: datetime | None = None) -> Path | None:
    """Copy the database before upgrading it (cabledrawer 28 Oct, review of v0.6.0): SQLite's own
    backup, which gives a consistent copy while the database is in use (WAL included), to
    `backups/pre-upgrade-<current revision>-<UTC date>.db`. Old copies are trimmed by
    `upgrade`, and only once the upgrade has worked.

    Nothing is copied for a new database or one that is already up to date. Returns the copy,
    or None. Raises SafetyCopyFailed if the copy can't be made: then don't upgrade."""
    if sqlite_file(engine) is None:
        return None
    revision = current_revision(engine)
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if revision is None or revision == head:
        return None
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%d-%H%M%S")
    target = backups / f"pre-upgrade-{revision}-{stamp}.db"
    # Written under another name first, so a copy cut short never counts as one of the three
    # (with the process ID, so two Mealwrights started at once never write the same file), and
    # readable by Mealwright's own user only (mealwright.backups).
    try:
        make_folder(backups)
        copy_database(engine, target)
    except (OSError, sqlite3.Error) as error:
        raise SafetyCopyFailed(
            f"Couldn't make a safety copy of the database in {backups} before upgrading it "
            f"({error}). The database was not changed. Check that the folder can be written "
            "and the disk isn't full, then start Mealwright again."
        ) from error
    log.info("Safety copy of the database before upgrading it: %s", target.name)
    return target


def _drop_stale_parts(backups: Path) -> None:
    """Delete half-written copies left by a start that was killed (another process's `.part`
    files). This process's own stay. A file that can't be removed is logged, never fatal."""
    for path in backups.iterdir():
        found = PART_NAME.match(path.name)
        if found and int(found.group(1)) != os.getpid():
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                log.warning("Couldn't remove the half-written copy %s: %s", path, error)


def _keep_newest(backups: Path, also: str | None = None) -> None:
    """Only the newest SAFETY_COPIES_KEPT copies stay, plus `also` (the clean copy from before
    an upgrade that failed); other files in the folder are never touched."""
    _drop_stale_parts(backups)
    copies = []
    for path in backups.iterdir():
        found = SAFETY_COPY_NAME.match(path.name)
        if found and path.is_file() and path.name != also:
            copies.append((found.group(2), path.name, path))
    copies.sort(reverse=True)
    for _stamp, _name, path in copies[SAFETY_COPIES_KEPT:]:
        path.unlink(missing_ok=True)


def _made_on(name: str) -> str:
    """ " (made on 2026-10-31)" from a copy's name, so a stale marker shows; else nothing."""
    found = SAFETY_COPY_NAME.match(name)
    if not found:
        return ""
    stamp = found.group(2)
    return f" (made on {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]})"


def _failed_before(backups: Path) -> str | None:
    """The clean copy's name, if an earlier upgrade didn't work; else None."""
    try:
        return (backups / UPGRADE_FAILED).read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None
    except OSError as error:
        raise SafetyCopyFailed(
            f"Couldn't read {backups / UPGRADE_FAILED} ({error}). The database was not "
            "changed. Check that the folder can be read, then start Mealwright again."
        ) from error


def upgrade(engine: Engine, revision: str = "head", backups: Path | None = None) -> None:
    """Bring the database up to `revision`. With `backups` (on start-up), a safety copy is
    made there first, and nothing is upgraded if it fails. While an upgrade keeps failing,
    no new copy is made and nothing is trimmed (see UPGRADE_FAILED); once it works, old
    copies are trimmed, keeping the clean one from before the trouble."""
    if backups is None:
        _run(engine, "upgrade", revision)
        return
    clean = _failed_before(backups)
    if clean is not None and not (backups / clean).is_file():
        # The copy the marker names is gone (say, restored and moved on): a stale marker must
        # not stop a fresh copy being made.
        log.warning(
            "The safety copy %s, named by %s, is missing. Removing the marker and making a "
            "fresh copy.",
            backups / clean,
            backups / UPGRADE_FAILED,
        )
        try:
            (backups / UPGRADE_FAILED).unlink(missing_ok=True)
        except OSError as error:
            raise SafetyCopyFailed(
                f"Couldn't remove {backups / UPGRADE_FAILED} ({error}). The database was not "
                "changed. Check that the folder can be written, then start Mealwright again."
            ) from error
        clean = None
    kept_aside = clean  # only a copy from before an earlier failure is kept beyond the three
    if clean is None:
        copy = safety_copy(engine, backups)
        if copy is not None:
            clean = copy.name
            try:
                (backups / UPGRADE_FAILED).write_text(clean + "\n", encoding="utf-8")
            except OSError as error:
                raise SafetyCopyFailed(
                    f"Couldn't write {backups / UPGRADE_FAILED} ({error}). The database was "
                    "not changed. Check that the folder can be written and the disk isn't "
                    "full, then start Mealwright again."
                ) from error
    else:
        log.warning(
            "An earlier database upgrade failed. Your data from before it is safe in %s%s. "
            "Trying the upgrade again.",
            backups / clean,
            _made_on(clean),
        )
    try:
        _run(engine, "upgrade", revision)
    except Exception:
        if clean is not None:
            # Plain words for the person reading the log (cabledrawer 31 Oct).
            log.error(
                "Database upgrade failed. Your data from before is safe in %s. Mealwright "
                "didn't start. See docs/dev/test-on-homelab.md, 'Going back to the previous "
                "version'.",
                backups / clean,
            )
        raise
    if clean is None:
        return
    # The upgrade worked: tidying up after it never stops Mealwright starting.
    try:
        (backups / UPGRADE_FAILED).unlink(missing_ok=True)
        _keep_newest(backups, also=kept_aside)
    except OSError as error:
        log.warning("Couldn't tidy the safety copies in %s: %s", backups, error)


def downgrade(engine: Engine, revision: str) -> None:
    _run(engine, "downgrade", revision)
