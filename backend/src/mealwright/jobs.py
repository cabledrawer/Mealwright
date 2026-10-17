"""Background jobs, run by APScheduler inside the app (no second container, no Redis).

Every job is added in `scheduler()`, in one place:

- **History** (spec section 6, "History and undo"): just after start-up and then every hour,
  changes older than the history length (12 months) become monthly totals, and emptied
  packets go once they can no longer be undone. It's cheap and safe to repeat, so it
  doesn't wait for a particular hour: a server that's off at night still gets it.
- **Log tidy** (mealwright.logs): just after each midnight (UTC), the day's log file is
  put aside and files older than 14 days are deleted. If the server was asleep at
  midnight, it runs when it wakes; at start-up, mealwright.logs puts aside a file from an
  earlier day.

Neither job has a lateness limit (misfire_grace_time=None): a late run still runs.

Nothing here makes a network connection.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mealwright.logs import DailyLogFile, tidy_once
from mealwright.models import Household

log = logging.getLogger(__name__)


def tidy_logs(handler: DailyLogFile, now: datetime | None = None) -> None:
    """Put yesterday's (UTC) log file aside and remove old ones."""
    now = now or datetime.now(UTC)
    tidy_once(handler, (now - timedelta(days=1)).date().isoformat())


def thin_history(factory: sessionmaker[Session], now: datetime | None = None) -> None:
    """Thin every household's history. Runs straight after start-up (in the background,
    so a big backlog never holds start-up up) and then every hour. Never raises."""
    from mealwright.history import thin  # imported here: history needs the API package

    now = now or datetime.now(UTC)
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
            except Exception:
                db.rollback()
                log.exception("Couldn't thin the history (will try again within the hour)")


def scheduler(
    factory: sessionmaker[Session], log_file: DailyLogFile | None = None
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
    if log_file is not None:
        jobs.add_job(
            tidy_logs,
            CronTrigger(hour=0, minute=0, second=1, timezone=UTC),
            args=[log_file],
            id="log-tidy",
            name="Tidy the log folder",
        )
    return jobs
