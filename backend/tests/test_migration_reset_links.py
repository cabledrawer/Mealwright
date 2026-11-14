"""0.9.5 step 16b's one database change: `join_link.kind` and `login.link_used_at`."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "d3a9f1c7e254"  # the line's newest before this (beta fix5 former names)
RESET = "b8e2d4f6a913"


def _columns(engine: object, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}  # type: ignore[arg-type]


def test_the_columns_come_and_go_and_the_rows_stay(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    assert "kind" not in _columns(engine, "join_link")
    assert "link_used_at" not in _columns(engine, "login")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO login (id, household_id, username, name, role, theme, created_at)"
            " VALUES (1, 1, 'sam', 'Sam', 'member', 'auto', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO join_link (id, household_id, login_id, token_hash, created_at,"
            " expires_at) VALUES (1, 1, 1, 'a', '2026-11-01', '2026-11-02')"
        )
    migrate.upgrade(engine, RESET)
    assert "kind" in _columns(engine, "join_link")
    assert "link_used_at" in _columns(engine, "login")
    with engine.begin() as connection:
        # An existing link is a sign-in link; an existing login has no "Link used" time.
        assert connection.exec_driver_sql("SELECT kind FROM join_link").scalar_one() == "join"
        assert connection.exec_driver_sql("SELECT link_used_at FROM login").scalar_one() is None
        connection.exec_driver_sql(
            "INSERT INTO join_link (id, household_id, login_id, token_hash, created_at,"
            " expires_at, kind) VALUES (2, 1, 1, 'b', '2026-11-01', '2026-11-02', 'reset')"
        )
    migrate.downgrade(engine, BEFORE)
    assert "kind" not in _columns(engine, "join_link")
    assert "link_used_at" not in _columns(engine, "login")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT username FROM login").scalar_one() == "sam"
        # Without its kind, a Reset password link would read as a sign-in link: it goes.
        assert connection.exec_driver_sql("SELECT token_hash FROM join_link").scalars().all() == [
            "a"
        ]
    migrate.upgrade(engine, RESET)
    assert "kind" in _columns(engine, "join_link")
