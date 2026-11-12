"""PR O1's one database change: single sign-on's table and its login and session columns."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "c7a1e5d3f802"  # PR U2's onboarding change (the line's newest before this)
SSO = "c1d5e9a3f702"


def _columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _rows(engine: Engine) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    with engine.connect() as connection:
        logins = connection.exec_driver_sql(
            "SELECT id, household_id, username, password_hash, role, password_changed_at"
            " FROM login ORDER BY id"
        ).all()
        sessions = connection.exec_driver_sql(
            "SELECT id, login_id, token_hash, remember, device, expires_at FROM session"
        ).all()
    return list(logins), list(sessions)


def _old_database(tmp_path: Path) -> Engine:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')",
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at, password_changed_at) VALUES (1, 1, 'tess', 'Tess', 'x', 'admin',"
            " 'auto', '2026-10-01', '2026-11-10')",
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at) VALUES (2, 1, 'ayla', 'Ayla', 'y', 'member', 'auto', '2026-10-01')",
            "INSERT INTO session (id, household_id, login_id, token_hash, remember, created_at,"
            " last_seen_at, expires_at, device) VALUES (1, 1, 1, 'abc', 1, '2026-11-01',"
            " '2026-11-02', '2026-12-01', 'iPhone · Safari')",
        ):
            connection.execute(text(sql))
    return engine


def test_sso_migration_adds_empty_columns_and_a_table_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    engine = _old_database(tmp_path)
    before = _rows(engine)

    migrate.upgrade(engine, SSO)
    assert "sso_settings" in inspect(engine).get_table_names()
    assert {"sso_issuer", "sso_subject"} <= _columns(engine, "login")
    assert {"sso", "sso_refresh_sealed", "sso_check_at"} <= _columns(engine, "session")
    assert "household_id" in _columns(engine, "sso_settings")
    assert _rows(engine) == before  # every login and session kept, unchanged
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT sso_issuer, sso_subject FROM login").all() == [
            (None, None),
            (None, None),
        ]
        assert connection.exec_driver_sql(
            "SELECT sso, sso_refresh_sealed, sso_check_at FROM session"
        ).all() == [(0, None, None)]
        assert connection.exec_driver_sql("SELECT count(*) FROM sso_settings").scalar() == 0
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE login SET sso_issuer = 'https://id.example', sso_subject = 's1' WHERE id = 1"
        )
        connection.exec_driver_sql(
            "INSERT INTO sso_settings (household_id, issuer, client_id, client_secret_sealed,"
            " button_name, redirect_uri, group_claim, group_roles, anyone_else, make_accounts,"
            " password_sign_in, updated_at) VALUES (1, 'https://id.example', 'mealwright',"
            " 'sealed', 'Authentik', 'https://mw.example/auth/callback', 'groups', '[]',"
            " 'none', 1, 1, '2026-11-14')"
        )

    migrate.downgrade(engine, BEFORE)
    assert "sso_settings" not in inspect(engine).get_table_names()
    assert not {"sso_issuer", "sso_subject"} & _columns(engine, "login")
    assert not {"sso", "sso_refresh_sealed", "sso_check_at"} & _columns(engine, "session")
    assert _rows(engine) == before

    migrate.upgrade(engine)
    assert _rows(engine) == before
    engine.dispose()


def test_one_subject_at_one_issuer_is_one_login(tmp_path: Path) -> None:
    engine = _old_database(tmp_path)
    migrate.upgrade(engine, SSO)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE login SET sso_issuer = 'https://id.example', sso_subject = 's1' WHERE id = 1"
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE login SET sso_issuer = 'https://id.example', sso_subject = 's1' WHERE id = 2"
        )
    with engine.begin() as connection:  # the same subject at another issuer is someone else
        connection.exec_driver_sql(
            "UPDATE login SET sso_issuer = 'https://other.example', sso_subject = 's1' WHERE id = 2"
        )
    engine.dispose()


def test_anyone_else_is_none_or_member(tmp_path: Path) -> None:
    engine = _old_database(tmp_path)
    migrate.upgrade(engine, SSO)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO sso_settings (household_id, issuer, client_id, button_name,"
            " redirect_uri, group_claim, group_roles, anyone_else, make_accounts,"
            " password_sign_in, updated_at) VALUES (1, 'i', 'c', 'b', 'r', 'groups', '[]',"
            " 'admin', 1, 1, '2026-11-14')"
        )
    engine.dispose()
