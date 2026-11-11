"""PR A2's one database change: `session.device` and `login.password_changed_at`."""

from pathlib import Path

from sqlalchemy import Engine, inspect, text

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "b4e8c2a6d917"  # the migration just before (0.9 A1's people)
SIGN_IN = "b4f8e2a6c917"


def _columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _rows(engine: Engine) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    with engine.connect() as connection:
        logins = connection.exec_driver_sql(
            "SELECT id, household_id, username, password_hash, last_sign_in_at FROM login"
        ).all()
        sessions = connection.exec_driver_sql(
            "SELECT id, login_id, token_hash, remember, last_seen_at, expires_at FROM session"
        ).all()
    return list(logins), list(sessions)


def test_sign_in_migration_adds_two_empty_columns_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')",
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at, last_sign_in_at) VALUES (1, 1, 'tess', 'Tess', 'x', 'admin',"
            " 'auto', '2026-10-01', '2026-11-01')",
            "INSERT INTO session (id, household_id, login_id, token_hash, remember, created_at,"
            " last_seen_at, expires_at) VALUES (1, 1, 1, 'abc', 1, '2026-11-01', '2026-11-02',"
            " '2026-12-01')",
        ):
            connection.execute(text(sql))
    before = _rows(engine)

    migrate.upgrade(engine, SIGN_IN)
    assert "device" in _columns(engine, "session")
    assert "password_changed_at" in _columns(engine, "login")
    assert _rows(engine) == before  # every login and session kept, unchanged
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT device FROM session").all() == [(None,)]
        assert connection.exec_driver_sql("SELECT password_changed_at FROM login").all() == [
            (None,)
        ]
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE session SET device = 'iPhone · Safari'")
        connection.exec_driver_sql("UPDATE login SET password_changed_at = '2026-11-10'")

    migrate.downgrade(engine, BEFORE)
    assert "device" not in _columns(engine, "session")
    assert "password_changed_at" not in _columns(engine, "login")
    assert _rows(engine) == before  # going back keeps everyone signed in

    migrate.upgrade(engine, SIGN_IN)  # and forward again starts them empty
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT device FROM session").all() == [(None,)]
    assert _rows(engine) == before
