"""Settings, read from MEALWRIGHT_* environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEALWRIGHT_")

    # Everything the app keeps (database, photos, backups) lives here.
    data_dir: Path = Path("/data")
    # Defaults to SQLite inside data_dir.
    database_url: str | None = None
    # Apply database migrations when the app starts.
    migrate_on_start: bool = True

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'mealwright.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
