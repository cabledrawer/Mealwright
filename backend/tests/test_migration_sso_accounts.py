"""0.9.5 step 16c's database change: the `sso_account` table (single sign-on sign-ins that wait
for an admin, Pe3/M2)."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "b6e2d8f4a913"  # the line's newest before this (the Mealie import)
ACCOUNTS = "c30b3fee4849"


def _tables(engine: object) -> set[str]:
    return set(inspect(engine).get_table_names())  # type: ignore[arg-type]


def test_the_table_comes_and_goes_and_the_logins_stay(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    assert "sso_account" not in _tables(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO login (id, household_id, username, name, role, theme, created_at,"
            " sso_issuer, sso_subject) VALUES (1, 1, 'sam', 'Sam', 'admin', 'auto',"
            " '2026-10-01', 'https://sign-in.example', 'sub-sam')"
        )
    migrate.upgrade(engine, ACCOUNTS)
    assert "sso_account" in _tables(engine)
    with engine.begin() as connection:
        # Nothing is waiting after the upgrade, and the existing link stays as it was.
        assert connection.exec_driver_sql("SELECT count(*) FROM sso_account").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT sso_subject FROM login").scalar_one() == (
            "sub-sam"
        )
        connection.exec_driver_sql(
            "INSERT INTO sso_account (household_id, issuer, subject, username, role, seen_at,"
            " waiting_since) VALUES (1, 'https://sign-in.example', 'sub-lorna', 'lorna.s',"
            " 'member', '2026-11-16', '2026-11-16')"
        )
        made = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'sso_account'"
        ).scalar_one()
        assert "AUTOINCREMENT" in made.upper()  # a waiting sign-in's number is never reused
    migrate.downgrade(engine, BEFORE)
    assert "sso_account" not in _tables(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT username FROM login").scalar_one() == "sam"
    migrate.upgrade(engine, ACCOUNTS)
    assert "sso_account" in _tables(engine)
