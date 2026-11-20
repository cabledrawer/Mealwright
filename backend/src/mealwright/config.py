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
    # The built web app (SvelteKit static build). Missing folder = API only.
    frontend_dir: Path = Path("/app/frontend")
    # Apply database migrations when the app starts.
    migrate_on_start: bool = True
    # Where the server listens. In the container, all interfaces: only the reverse
    # proxy can reach it. Tests use 127.0.0.1.
    host: str = "0.0.0.0"  # noqa: S104  # nosec B104
    port: int = 8080
    # Signing in needs HTTPS (spec section 7): the session cookie is HTTPS-only. Set this
    # to allow sign-in over plain http:// for testing on a network you trust; the cookie
    # and password then travel unencrypted, and a warning is logged at start-up.
    allow_plain_http: bool = False
    # The reverse proxy (Caddy, Traefik, nginx, Nginx Proxy Manager…) whose
    # X-Forwarded-For/-Proto headers are believed: its addresses or networks,
    # comma-separated (e.g. "172.28.10.0/24"). Empty (the default) believes nobody's.
    # The visitor's address is then the last one the proxy added, which a visitor can't
    # fake. "*" believes anyone and takes the first address: only safe when the proxy
    # replaces any X-Forwarded-For a visitor sends (Caddy does; nginx by default doesn't).
    trusted_proxies: str = ""
    # Run the background jobs (history thinning, removals for good, backups, the daily update
    # check, single sign-on checks, log tidy; docs/environment.md lists them). Off only in tests.
    run_jobs: bool = True

    # How often the live-updates stream sends a keep-alive line and re-checks the sign-in.
    # Only tests change it.
    events_keepalive_seconds: float = 25

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'mealwright.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
