"""0.9.5 step 16f's one database change: `household.backup_photos` ("Include photos")."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "b8e2d4f6a913"  # the line's newest before this (16b's reset links)
THIS = "c6a1f3b9d805"


def _columns(engine: object) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("household")}  # type: ignore[arg-type]


def test_every_household_includes_photos_and_the_column_comes_and_goes(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    assert "backup_photos" not in _columns(engine)
    with engine.begin() as connection:
        for number in (1, 2):
            connection.exec_driver_sql(
                "INSERT INTO household (id, name, created_at) VALUES (?, 'Home', '2026-10-01')",
                (number,),
            )
    migrate.upgrade(engine, THIS)
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT backup_photos FROM household").scalars().all()
    assert rows == [1, 1]  # the usual: photos are included
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE household SET backup_photos = 0 WHERE id = 1")
    migrate.downgrade(engine, BEFORE)
    assert "backup_photos" not in _columns(engine)
    with engine.connect() as connection:  # both households stay
        assert connection.exec_driver_sql("SELECT count(*) FROM household").scalar_one() == 2
    migrate.upgrade(engine, THIS)
    with engine.connect() as connection:  # the choice to leave photos out was lost, as said
        rows = connection.exec_driver_sql("SELECT backup_photos FROM household").scalars().all()
    assert rows == [1, 1]
