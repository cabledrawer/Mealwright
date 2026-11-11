"""The household's backup settings migration (0.9, D1): upgrade, downgrade and upgrade again.

In its own file so it doesn't collide with the other 0.9 migrations' tests."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "b4f8e2a6c917"  # the migration just before this one (0.9 A2: sign-in device and password date)
THIS = "b2f7c4e8a915"
COLUMNS = {"backup_every", "backup_keep", "backup_problem", "backup_problem_at"}


def _columns(engine: object) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("household")}  # type: ignore[arg-type]


def test_backup_settings_migration_gives_daily_and_7_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        for h in (1, 2):
            connection.exec_driver_sql(
                "INSERT INTO household (id, name, created_at) VALUES (?, 'Home', '2026-10-01')",
                (h,),
            )
            connection.exec_driver_sql(
                "INSERT INTO login (household_id, username, name, password_hash, role, theme,"
                " created_at) VALUES (?, ?, 'User', 'x', 'admin', 'auto', '2026-10-01')",
                (h, f"user{h}"),
            )
    migrate.upgrade(engine, THIS)
    assert _columns(engine) >= COLUMNS
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT backup_every, backup_keep, backup_problem, backup_problem_at FROM household"
            " ORDER BY id"
        ).all()
    assert rows == [("daily", 7, None, None)] * 2

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE household SET backup_every = 'weekly', backup_keep = 3,"
            " backup_problem = 'disk full' WHERE id = 1"
        )
    migrate.downgrade(engine, BEFORE)
    assert not COLUMNS & _columns(engine)
    with engine.connect() as connection:  # nothing else went: both households and their logins
        assert connection.exec_driver_sql("SELECT count(*) FROM household").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM login").scalar_one() == 2

    migrate.upgrade(engine, THIS)
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT backup_every, backup_keep, backup_problem FROM household ORDER BY id"
        ).all()
    assert rows == [("daily", 7, None)] * 2
