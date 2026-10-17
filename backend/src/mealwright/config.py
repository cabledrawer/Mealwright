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
    # Where the server listens. In the container, all interfaces: only the reverse
    # proxy can reach it. Tests use 127.0.0.1.
    host: str = "0.0.0.0"  # noqa: S104  # nosec B104
    port: int = 8080
    # Session cookies are only sent over HTTPS. Turn off only for plain-HTTP testing.
    cookie_secure: bool = True
    # Addresses of reverse proxies whose X-Forwarded-For/-Proto headers are believed,
    # comma-separated, or "*" when the app is only reachable through the proxy.
    trusted_proxies: str = "127.0.0.1"

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'mealwright.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
