"""Background jobs, run by APScheduler inside the app (no second container, no Redis).

Every job is added in `scheduler()`, in one place:

- **History** (spec section 6, "History and undo"): just after start-up and then every hour,
  changes older than the history length (12 months) become monthly totals, and emptied
  packets go once they can no longer be undone. The shopping lists are tidied too (sync
  protocol 3.9): old notes and answered questions, long-removed items and lists, and old
  sync-log details. It's cheap and safe to repeat, so it
  doesn't wait for a particular hour: a server that's off at night still gets it.
- **Log tidy** (mealwright.logs): just after each midnight (UTC), the day's log file is
  put aside and files older than 14 days are deleted. If the server was asleep at
  midnight, it runs when it wakes; at start-up, mealwright.logs puts aside a file from an
  earlier day.

- **Removed ingredients and recipes** (spec section 6): just after start-up and then every
  hour, ingredients and recipes removed longer ago than the undo window (7 days) are deleted
  for good, recipe photos with them (their files too). Photos uploaded but not saved on any
  recipe within 24 hours are deleted, and so are photo files with no record that are older
  than that (cabledrawer 20 Oct).
- **Drafts** (spec section 6, "Drafts"): in the same run, a draft 15 days past its last change
  is deleted quietly, and a deleted draft once its undo window has passed, photo and all
  (cabledrawer 21 and 22 Oct). Nothing is logged about a draft except how many went.

- **Backups** (mealwright.backups; spec section 7, cabledrawer 17 Oct): every 10 minutes, and just
  after start-up, it looks whether a backup of the database is due (03:00 in the household's own
  time, daily by default) and makes it, keeping the household's chosen number.
- **Daily update check** (spec section 7, "Updates"; mealwright.updates): every hour, for each
  household whose Privacy switch "Check for updates daily" is on and whose last answer is
  missing or nearly a day old, one request to the public release list through the outbound
  gate. Off by default; with the switch off it connects nowhere.
- **Single sign-on** (0.9 O1): every 5 minutes, each single sign-on sign-in that's due (once
  an hour) is checked with the sign-in server through the outbound gate, under the Single
  sign-on switch (`mealwright.sso_accounts.check_sessions`). A sign-in the server has ended is
  signed out here too. With the switch off nothing is sent and nobody is signed out.

No job has a lateness limit (misfire_grace_time=None): a late run still runs.

Apart from the daily update check and the single sign-on check, both through the outbound gate,
nothing here makes a network connection.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from mealwright import backups
from mealwright.events import Broadcaster
from mealwright.former_names import remove_expired
from mealwright.logs import DailyLogFile, tidy_once
from mealwright.models import Household, utcnow
from mealwright.outbound import OutboundGate  # at run time: APScheduler reads the job's signature
from mealwright.updates import UpdateChecks

log = logging.getLogger(__name__)


def tidy_logs(
    handler: DailyLogFile,
    now: datetime | None = None,
    factory: sessionmaker[Session] | None = None,
) -> None:
    """Put yesterday's (UTC) log file aside and remove old ones, and with them the old names
    kept for them (mealwright.former_names): those older than the log files plus a day."""
    now = now or datetime.now(UTC)
    tidy_once(handler, (now - timedelta(days=1)).date().isoformat())
    if factory is not None:
        try:
            with factory() as db:
                remove_expired(db, now)
        except Exception:
            log.exception("Couldn't remove old kept names")


def thin_history(factory: sessionmaker[Session], now: datetime | None = None) -> None:
    """Thin every household's history. Runs straight after start-up (in the background,
    so a big backlog never holds start-up up) and then every hour. Never raises."""
    from mealwright.history import thin, tidy_lists  # imported here: history needs the API

    now = now or utcnow()
    with factory() as db:
        try:
            households = list(db.scalars(select(Household)))
        except Exception:
            log.exception("Couldn't thin the history (will try again within the hour)")
            return
        for household in households:
            try:
                thinned = thin(db, household, now)
                if thinned:
                    log.info("Thinned %d old changes into monthly totals", thinned)
                tidied = tidy_lists(db, household, now)
                if tidied:
                    log.info("Tidied %d old shopping-list records", tidied)
            except Exception:
                db.rollback()
                log.exception("Couldn't thin the history (will try again within the hour)")


def purge_removed_ingredients(factory: sessionmaker[Session], now: datetime | None = None) -> None:
    """Delete ingredients removed longer ago than the undo window. Runs straight after
    start-up and then every hour. Never raises."""
    from mealwright.drafts import purge as purge_drafts
    from mealwright.history import purge_removed  # imported here: history needs the API
    from mealwright.mealie_import import tidy as tidy_mealie
    from mealwright.people import free_old_usernames
    from mealwright.recipes import drop_waiting_photos, purge_removed_recipes

    now = now or utcnow()
    with factory() as db:
        try:
            if tidied := tidy_mealie(db, now):
                log.info("Deleted %d Mealie files nobody brought in", tidied)
        except Exception as why:
            db.rollback()
            # The kind of failure only: a traceback could carry the file's path (round 2, S5).
            log.warning(
                "Couldn't tidy Mealie files (%s; will try again within the hour)",
                type(why).__name__,
            )
        try:
            households = list(db.scalars(select(Household)))
        except Exception:
            log.exception("Couldn't tidy removed ingredients (will try again within the hour)")
            return
        for household in households:
            try:
                purged = purge_removed(db, household, now)
                if purged:
                    log.info("Deleted %d removed ingredients for good", purged)
                gone = purge_removed_recipes(db, household, now)
                if gone:
                    log.info("Deleted %d removed recipes for good", gone)
                dropped = drop_waiting_photos(db, household, now)
                if dropped:
                    log.info("Deleted %d photos that were never saved on a recipe", dropped)
                freed = free_old_usernames(db, household, now)
                if freed:
                    db.commit()
                    log.info("Let go of %d removed people's usernames", freed)
                old_drafts = purge_drafts(db, household, now)
                if old_drafts:
                    log.info("Deleted %d old drafts", old_drafts)
            except Exception:
                db.rollback()
                log.exception("Couldn't tidy removed ingredients (will try again within the hour)")


def back_up_if_due(factory: sessionmaker[Session], engine: Engine, folder: Path) -> None:
    """Make the database's backup when one is due. Never raises."""
    backups.run_if_due(factory, engine, folder)


def check_single_sign_on(
    gate: OutboundGate,
    factory: sessionmaker[Session],
    data_dir: Path,
    events: Broadcaster,
) -> None:
    from mealwright import sso_accounts  # imported here: it needs the API's models

    sso_accounts.fill_memory(gate, factory)  # first: a restart empties the memory
    ended = sso_accounts.check_sessions(gate, factory, data_dir, events)
    if ended:
        log.info("Single sign-on: %d sign-ins ended by the sign-in server", ended)


def scheduler(
    factory: sessionmaker[Session],
    log_file: DailyLogFile | None = None,
    backups_folder: Path | None = None,
    updates: UpdateChecks | None = None,
    single_sign_on: tuple[OutboundGate, Path, Broadcaster] | None = None,
) -> BackgroundScheduler:
    """The app's scheduler, with every job added. Started and stopped with the app."""
    jobs = BackgroundScheduler(
        timezone=UTC,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": None},
    )
    jobs.add_job(
        thin_history,
        CronTrigger(minute=30, timezone=UTC),
        args=[factory],
        next_run_time=datetime.now(UTC),  # catch up straight away, off the start-up path
        id="history",
        name="Thin old history",
    )
    jobs.add_job(
        purge_removed_ingredients,
        CronTrigger(minute=40, timezone=UTC),
        args=[factory],
        next_run_time=datetime.now(UTC),
        id="removed-ingredients",
        name="Delete removed ingredients and recipes for good",
    )
    if backups_folder is not None:
        engine = factory.kw["bind"]
        jobs.add_job(
            back_up_if_due,
            CronTrigger(minute="*/10", timezone=UTC),
            args=[factory, engine, backups_folder],
            next_run_time=datetime.now(UTC),
            id="backups",
            name="Back the database up when it's due",
        )
    if updates is not None:
        jobs.add_job(
            updates.daily_check,
            CronTrigger(minute=50, timezone=UTC),
            args=[factory],
            id="update-check",
            name="Check for updates daily (only while its Privacy switch is on)",
        )
    if single_sign_on is not None:
        jobs.add_job(
            check_single_sign_on,
            IntervalTrigger(minutes=5, timezone=UTC),
            args=[single_sign_on[0], factory, single_sign_on[1], single_sign_on[2]],
            next_run_time=datetime.now(UTC),  # at start too: a restart empties the memory
            id="single-sign-on",
            name="Check single sign-on sign-ins with the sign-in server",
        )
    if log_file is not None:
        jobs.add_job(
            tidy_logs,
            CronTrigger(hour=0, minute=0, second=1, timezone=UTC),
            args=[log_file],
            kwargs={"factory": factory},
            id="log-tidy",
            name="Tidy the log folder",
        )
    return jobs
