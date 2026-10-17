"""Background jobs, run by APScheduler inside the app (no second container, no Redis).

Every job is added in `scheduler()`, in one place:

- **History** (spec section 6, "History and undo"): each night at 03:30 in the
  household's own time zone, changes older than the history length (12 months) become
  monthly totals, and emptied packets go once they can no longer be undone.
- **Log tidy** (mealwright.logs): just after each midnight (UTC), the day's log file is
  put aside and files older than 14 days are deleted.

Nothing here makes a network connection.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mealwright.household import zone
from mealwright.logs import DailyLogFile, tidy_once
from mealwright.models import Household

log = logging.getLogger(__name__)

HISTORY_HOUR = 3  # 03:30 local time, when nobody's cooking


def tidy_logs(handler: DailyLogFile, now: datetime | None = None) -> None:
    """Put yesterday's (UTC) log file aside and remove old ones."""
    now = now or datetime.now(UTC)
    tidy_once(handler, (now - timedelta(days=1)).date().isoformat())


def thin_history(factory: sessionmaker[Session], now: datetime | None = None) -> None:
    """Runs every hour at :30; each household is thinned in its own 03:30. Thinning is
    safe to repeat, so a missed night is simply caught up the next one."""
    from mealwright.history import thin  # imported here: history needs the API package

    now = now or datetime.now(UTC)
    with factory() as db:
        for household in db.scalars(select(Household)):
            if now.astimezone(zone(household)).hour != HISTORY_HOUR:
                continue
            try:
                thinned = thin(db, household, now)
                if thinned:
                    log.info("Thinned %d old changes into monthly totals", thinned)
            except Exception:
                db.rollback()
                log.exception("Couldn't thin the history")


def scheduler(
    factory: sessionmaker[Session], log_file: DailyLogFile | None = None
) -> BackgroundScheduler:
    """The app's scheduler, with every job added. Started and stopped with the app."""
    jobs = BackgroundScheduler(
        timezone=UTC,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    )
    jobs.add_job(
        thin_history,
        CronTrigger(minute=30, timezone=UTC),
        args=[factory],
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
