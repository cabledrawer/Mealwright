from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect

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
