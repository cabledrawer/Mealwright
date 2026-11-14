"""D1/S5 (cabledrawer 13 Nov): login numbers are never reused, not even after Delete everything. The
`login` table never hands out a removed login's number again (`AUTOINCREMENT`, migration
91246ac80e8c); before it, the first login made after Delete everything got number 1 again."""

from pathlib import Path

from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, select

from mealwright import migrate
from mealwright.db import make_engine
from mealwright.models import Login

BEFORE = "c30b3fee4849"  # sso_account, the newest before this
LOGIN_IDS = "91246ac80e8c"


def _ids(client: TestClient) -> list[int]:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return list(db.scalars(select(Login.id).order_by(Login.id)))


def test_after_delete_everything_the_new_admin_gets_a_new_number(kitchen: TestClient) -> None:
    gone = _ids(kitchen)
    assert gone
    answer = kitchen.post(
        "/api/v1/delete-everything",
        json={"words": "delete everything", "password": ADMIN["password"]},
    )
    assert answer.status_code == 204, answer.text
    assert _ids(kitchen) == []
    assert kitchen.post("/api/v1/setup", json=ADMIN).status_code == 201
    (new,) = _ids(kitchen)
    assert new > max(gone)


def _login_sql(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'login'"
            ).scalar_one()
        )


def _shape(engine: Engine) -> tuple[object, ...]:
    """Everything about the login table but AUTOINCREMENT: its columns, indexes, unique
    constraints and links, in and out."""
    look = inspect(engine)
    pointing_in = sorted(
        (table, str(fk["constrained_columns"]), fk["options"].get("ondelete"))
        for table in look.get_table_names()
        for fk in look.get_foreign_keys(table)
        if fk["referred_table"] == "login"
    )
    return (
        [(c["name"], str(c["type"]), c["nullable"]) for c in look.get_columns("login")],
        sorted(
            (i["name"], tuple(i["column_names"]), i["unique"]) for i in look.get_indexes("login")
        ),
        sorted((u["name"], tuple(u["column_names"])) for u in look.get_unique_constraints("login")),
        sorted(
            (str(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
            for fk in look.get_foreign_keys("login")
        ),
        pointing_in,
    )


def test_the_migration_keeps_every_login_and_link_and_goes_back(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        for number, name in ((1, "sam"), (2, "lorna"), (3, "noor")):
            connection.exec_driver_sql(
                "INSERT INTO login (id, household_id, username, name, role, theme, created_at,"
                " sso_issuer, sso_subject) VALUES (?, 1, ?, ?, 'admin', 'auto', '2026-10-01',"
                " 'https://sign-in.example', ?)",
                (number, name, name.capitalize(), f"sub-{name}"),
            )
        connection.exec_driver_sql(
            "INSERT INTO session (household_id, login_id, token_hash, remember, created_at,"
            " expires_at, last_seen_at)"
            " VALUES (1, 2, 'hash', 0, '2026-11-01', '2026-12-01', '2026-11-01')"
        )
    shape = _shape(engine)
    assert "AUTOINCREMENT" not in _login_sql(engine).upper()
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT * FROM login ORDER BY id").all()

    migrate.upgrade(engine, LOGIN_IDS)
    assert "AUTOINCREMENT" in _login_sql(engine).upper()
    assert _shape(engine) == shape
    with engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT * FROM login ORDER BY id").all() == rows
        # The session that points at Lorna is kept, and still points at her.
        assert connection.exec_driver_sql("SELECT login_id FROM session").scalar_one() == 2
        connection.exec_driver_sql("DELETE FROM session")
        connection.exec_driver_sql("DELETE FROM login WHERE id = 3")
        connection.exec_driver_sql(
            "INSERT INTO login (household_id, username, name, role, theme, created_at)"
            " VALUES (1, 'asha', 'Asha', 'member', 'auto', '2026-11-17')"
        )
        assert (
            connection.exec_driver_sql("SELECT id FROM login WHERE username = 'asha'").scalar_one()
            == 4
        )

    migrate.downgrade(engine, BEFORE)
    assert "AUTOINCREMENT" not in _login_sql(engine).upper()
    assert _shape(engine) == shape
    with engine.connect() as connection:
        names = connection.exec_driver_sql("SELECT username FROM login ORDER BY id").scalars()
        assert list(names) == ["sam", "lorna", "asha"]
    migrate.upgrade(engine, LOGIN_IDS)
    assert "AUTOINCREMENT" in _login_sql(engine).upper()
