"""Run database migrations from code (on start-up and in tests)."""

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "mealwright:migrations")
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def downgrade(engine: Engine, revision: str) -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, revision)
