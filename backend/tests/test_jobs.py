"""The nightly jobs: thinning history to monthly totals, and tidying the log folder."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from mealwright import jobs
from mealwright.history import thin
from mealwright.logs import FILE_NAME, DailyLogFile
from mealwright.models import Change, ChangeLine, ChangeMonth, Household, StockLot, utcnow

API = "/api/v1"


def db(kitchen: TestClient) -> Any:
    return kitchen.app.state.sessionmaker()  # type: ignore[attr-defined]


def make_history(kitchen: TestClient) -> tuple[int, int]:
    spinach = kitchen.post(f"{API}/foods", json={"name": "Spinach"}).json()["food"]
    body = {"food_id": spinach["id"], "amount": {"amount": 200, "unit": "g"}}
    lot = kitchen.post(f"{API}/stock", json=body).json()["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/used", json={"amount": {"amount": 50, "unit": "g"}})
    kitchen.post(f"{API}/stock/{lot['id']}/used", json={"amount": {"amount": 30, "unit": "g"}})
    return spinach["id"], lot["id"]


def test_thinning_turns_old_changes_into_monthly_totals(kitchen: TestClient) -> None:
    food_id, _lot = make_history(kitchen)
    old = datetime(2025, 3, 10, 12, tzinfo=UTC)
    with db(kitchen) as session:
        session.execute(update(Change).values(at=old))
        session.commit()
        household = session.get(Household, 1)
        assert thin(session, household, now=datetime(2026, 10, 17, tzinfo=UTC)) == 4
        assert session.scalar(select(func.count()).select_from(Change)) == 0
        assert session.scalar(select(func.count()).select_from(ChangeLine)) == 0
        totals = {
            (row.month, row.kind): (row.amount_milli, row.changes)
            for row in session.scalars(select(ChangeMonth).where(ChangeMonth.food_id == food_id))
        }
    assert totals == {
        ("2025-03", "added"): (200_000, 1),
        ("2025-03", "used"): (-80_000, 2),
    }
    # The pantry itself is untouched.
    assert kitchen.get(f"{API}/foods/{food_id}").json()["stock"]["amount"] == 120.0


def test_recent_history_is_kept(kitchen: TestClient) -> None:
    make_history(kitchen)
    with db(kitchen) as session:
        household = session.get(Household, 1)
        assert thin(session, household) == 0
        assert session.scalar(select(func.count()).select_from(Change)) == 4


def test_thinning_an_undone_change(kitchen: TestClient) -> None:
    _food_id, lot_id = make_history(kitchen)
    used = kitchen.post(f"{API}/stock/{lot_id}/used").json()["change"]
    kitchen.post(f"{API}/changes/{used['id']}/undo")
    with db(kitchen) as session:
        session.execute(update(Change).values(at=utcnow() - timedelta(days=400)))
        session.commit()
        assert thin(session, session.get(Household, 1)) == 6


def test_empty_packets_go_after_the_undo_window(kitchen: TestClient) -> None:
    _food_id, lot_id = make_history(kitchen)
    kitchen.post(f"{API}/stock/{lot_id}/used")
    with db(kitchen) as session:
        household = session.get(Household, 1)
        thin(session, household)
        assert session.get(StockLot, lot_id) is not None  # can still be undone
        thin(session, household, now=utcnow() + timedelta(days=8))
        assert session.get(StockLot, lot_id) is None
        # Its change lines stay, just no longer pointing at it.
        lines = session.scalars(select(ChangeLine).where(ChangeLine.lot_id.is_(None))).all()
        assert len(lines) == 4


def test_history_job_thins_at_any_hour(kitchen: TestClient) -> None:
    make_history(kitchen)
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    with db(kitchen) as session:
        session.execute(update(Change).values(at=utcnow() - timedelta(days=400)))
        session.commit()
    jobs.thin_history(factory, now=datetime(2026, 10, 17, 14, 30, tzinfo=UTC))
    with db(kitchen) as session:
        assert session.scalar(select(func.count()).select_from(Change)) == 0


def test_a_missed_night_is_caught_up_at_start_up(tmp_path: Path) -> None:
    from mealwright.config import Settings
    from mealwright.main import create_app

    admin = {"name": "Tess", "username": "tess", "password": "correct horse battery"}
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        client.post(f"{API}/setup", json=admin)
        make_history(client)
        with db(client) as session:
            session.execute(update(Change).values(at=utcnow() - timedelta(days=400)))
            session.commit()
    # The server was off; when it starts again, old history is thinned straight away.
    settings = Settings(data_dir=tmp_path / "data", run_jobs=True)
    with (
        TestClient(create_app(settings), base_url="https://testserver") as client,
        db(client) as session,
    ):
        assert session.scalar(select(func.count()).select_from(Change)) == 0
        assert session.scalar(select(func.count()).select_from(ChangeMonth)) == 2


def test_scheduler_has_every_job(kitchen: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    handler = DailyLogFile(folder)
    try:
        background = jobs.scheduler(kitchen.app.state.sessionmaker, handler)  # type: ignore[attr-defined]
        assert {job.id for job in background.get_jobs()} == {"history", "log-tidy"}
        background.start()
        assert background.running
        # A late run still runs (asleep at midnight, busy on the hour).
        assert all(job.misfire_grace_time is None for job in background.get_jobs())
        background.shutdown(wait=False)
        without_log = jobs.scheduler(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
        assert [job.id for job in without_log.get_jobs()] == ["history"]
    finally:
        handler.close()


def test_tidy_logs_puts_yesterday_aside(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    handler = DailyLogFile(folder)
    try:
        (folder / FILE_NAME).write_text("a line\n")
        jobs.tidy_logs(handler, now=datetime(2026, 10, 18, 0, 0, 1, tzinfo=UTC))
        assert (folder / f"{FILE_NAME}.2026-10-17").read_text() == "a line\n"
    finally:
        handler.close()


def test_app_starts_and_stops_the_scheduler(tmp_path: Path) -> None:
    from mealwright.config import Settings
    from mealwright.main import create_app

    app = create_app(Settings(data_dir=tmp_path / "data", run_jobs=True))
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(f"{API}/version").status_code == 200
