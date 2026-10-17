from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect

from mealwright import migrate
from mealwright.db import Base, make_engine


def test_startup_creates_database(client: TestClient, tmp_path: Path) -> None:
    assert (tmp_path / "data" / "mealwright.db").exists()


def test_migrations_match_models(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], "models changed without a migration: run alembic revision --autogenerate"


def test_downgrade_to_empty(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    migrate.downgrade(engine, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_every_table_has_household_id() -> None:
    for table in Base.metadata.sorted_tables:
        if table.name == "household":
            continue
        assert "household_id" in table.columns, f"{table.name} has no household_id"


def _counts(engine: Engine) -> tuple[int, int, int]:
    with engine.connect() as connection:
        return tuple(  # type: ignore[return-value]
            connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()  # noqa: S608
            for table in ("household", "login", "session")
        )


def _make_0_1_database(path: Path) -> Engine:
    """A 0.1 database with a household, its admin (dark theme) and a signed-in session."""
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, "d60b64f1e4ff")  # 0.1.0
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at) VALUES (1, 1, 'tess', 'Tess', 'x', 'admin', 'dark', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO session (household_id, login_id, token_hash, remember, created_at,"
            " last_seen_at, expires_at) VALUES (1, 1, 'abc', 0, '2026-10-01', '2026-10-01',"
            " '2026-11-01')"
        )
    return engine


def test_downgrade_keeps_logins_and_sessions(tmp_path: Path) -> None:
    # Rebuilding the household table must not cascade into its logins (foreign keys are
    # switched off while migrating on SQLite).
    engine = _make_0_1_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    assert _counts(engine) == (1, 1, 1)
    migrate.downgrade(engine, "d60b64f1e4ff")
    assert _counts(engine) == (1, 1, 1)
    with engine.connect() as connection:
        theme = connection.exec_driver_sql("SELECT theme FROM login").scalar_one()
    assert theme == "dark"


def test_upgrade_downgrade_upgrade_round_trip(tmp_path: Path) -> None:
    engine = _make_0_1_database(tmp_path / "old.db")
    migrate.upgrade(engine)
    migrate.downgrade(engine, "d60b64f1e4ff")
    migrate.upgrade(engine)
    assert _counts(engine) == (1, 1, 1)
    with engine.connect() as connection:
        places = connection.exec_driver_sql("SELECT count(*) FROM place").scalar_one()
        on = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    assert places == 4
    assert on == 1  # switched back on after migrating
