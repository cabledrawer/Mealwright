"""The FastAPI application."""

import logging
import multiprocessing
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.telemetry import TelemetryConfig
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from mealwright import (
    __version__,
    backups,
    errors,
    events,
    jobs,
    migrate,
    private_files,
    setup_code,
    sso,
)
from mealwright.api.v1 import router as api_v1
from mealwright.auth import OldCookieMiddleware, SlowDown
from mealwright.config import Settings, get_settings
from mealwright.db import make_engine, make_sessionmaker
from mealwright.events import Broadcaster
from mealwright.forwarded import ForwardedMiddleware
from mealwright.frontend import inline_script_hashes, mount_frontend
from mealwright.limits import BodyLimitMiddleware
from mealwright.logs import DailyLogFile
from mealwright.mealie_import import MealieRunner
from mealwright.models import Login
from mealwright.outbound import OutboundGate, install_network_guard
from mealwright.security import SecurityHeadersMiddleware
from mealwright.updates import UpdateChecks

log = logging.getLogger(__name__)

# FastAPI's built-in OpenTelemetry support: switch every part of it off, and never
# configure exporters from OTEL_* / FASTAPI_OTEL_* environment variables.
TELEMETRY_OFF: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}


class UnsupportedSetup(RuntimeError):
    """Mealwright can't run safely like this, so it refuses to start (spec section 6)."""


def refuse_unsupported_setup(settings: Settings) -> None:
    """Before 1.0 Mealwright runs on SQLite in one process: the live updates, the sign-in
    slow-down and the nightly jobs live in that one process's memory, and SQLite takes one
    writer. Say why instead of half-working."""
    try:
        backend = make_url(settings.sqlalchemy_url).get_backend_name()
    except ArgumentError:
        backend = ""
    if backend != "sqlite":
        raise UnsupportedSetup(
            "MEALWRIGHT_DATABASE_URL must be a SQLite address (sqlite:///...). Other "
            "databases aren't supported yet. Leave it unset to use /data/mealwright.db."
        )
    concurrency = os.environ.get("WEB_CONCURRENCY", "").strip()
    # A supervisor (uvicorn --workers, --reload) starts each worker as a child process.
    if multiprocessing.parent_process() is not None or concurrency not in {"", "1"}:
        raise UnsupportedSetup(
            "Mealwright runs as one worker. Start it with `python -m mealwright` (as the "
            "container does), without --workers or WEB_CONCURRENCY."
        )


def create_app(settings: Settings | None = None, log_file: DailyLogFile | None = None) -> FastAPI:
    settings = settings or get_settings()
    refuse_unsupported_setup(settings)
    # From here on, only the outbound gate may connect to anything (spec section 7).
    install_network_guard()
    engine = make_engine(settings.sqlalchemy_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_start:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            migrate.upgrade(engine, backups=settings.data_dir / backups.FOLDER)
        # After the database is open (its -wal and -shm files exist): fix older installs.
        private_files.tighten(settings.data_dir)
        # A fresh install gets a one-off setup code, printed in the log (PR A2): only
        # someone who can read the server's log can create the admin account.
        with app.state.sessionmaker() as db:
            fresh = db.scalar(select(func.count()).select_from(Login)) == 0
        if fresh:
            app.state.setup_code = setup_code.new_code()
            setup_code.announce(app.state.setup_code)
        background = None
        if settings.run_jobs:
            background = jobs.scheduler(
                app.state.sessionmaker,
                log_file,
                settings.data_dir / backups.FOLDER,
                app.state.updates,
                single_sign_on=(app.state.outbound, settings.data_dir, app.state.events),
            )
            background.start()
            app.state.mealie.resume()  # carry on imports a restart stopped
        yield
        app.state.events.close()  # end open live streams so shutdown isn't held up
        if background is not None:
            background.shutdown(wait=False)
        engine.dispose()

    app = FastAPI(
        title="Mealwright",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        # FastAPI's built-in docs pages load scripts from a CDN, which the ethos forbids.
        # Bundled API docs can come later; the OpenAPI document is always available.
        docs_url=None,
        redoc_url=None,
        telemetry=TELEMETRY_OFF,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine, settings.data_dir / "photos")
    app.state.database_turns = {}  # filled by auth.get_db: who may use the database now
    app.state.events = Broadcaster()
    events.install(app.state.sessionmaker, app.state.events)
    app.state.outbound = OutboundGate(app.state.sessionmaker)
    app.state.updates = UpdateChecks(app.state.outbound)
    app.state.slow_down = SlowDown()
    app.state.sso_used = sso.Used()  # single sign-on states already used (memory only)
    app.state.sso_tests = {}  # the setup screen's last test, by household (memory only)
    app.state.sso_links = {}  # a test's link waiting for its admin's OK (memory only)
    # The setup an Admin has proven works for them, by household (memory only; proposed, for
    # cabledrawer): passwords go off only over it, and a restart forgets it.
    app.state.sso_proven = {}
    # An SSO-only admin's fresh confirmation of Delete everything (D3; memory only, 10 minutes).
    app.state.sso_confirmed = {}
    app.state.setup_code = None  # set at start-up on a fresh install
    # Imports from Mealie run on the server, one thread each (0.9.5).
    app.state.mealie = MealieRunner(app.state.sessionmaker)
    errors.install(app)
    app.include_router(api_v1)
    mount_frontend(app, settings.frontend_dir)  # after the API, so it only gets the rest
    # No body bigger than the biggest real one, checked before anything reads it.
    app.add_middleware(BodyLimitMiddleware)
    # Strict browser rules on every response (spec section 7). The web app's own inline
    # start-up scripts are allowed by their exact fingerprint, nothing else. HSTS only in
    # https mode (cabledrawer 19 Oct).
    app.add_middleware(
        SecurityHeadersMiddleware,
        script_hashes=inline_script_hashes(settings.frontend_dir),
        https=not settings.allow_plain_http,
    )
    # In https mode a sign-in cookie under the old name is cleared (spec section 7: the
    # `__Host-` name signs everyone out once).
    if not settings.allow_plain_http:
        app.add_middleware(OldCookieMiddleware)
    # Outermost: the visitor's real address and scheme from the reverse proxy's
    # X-Forwarded-For/-Proto headers, believed only from MEALWRIGHT_TRUSTED_PROXIES (off
    # by default). The sign-in slow-down counts per address, so it needs the real one.
    if settings.trusted_proxies.strip():
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)
    # Outside that: X-Forwarded-Host from a trusted proxy, and one warning when a proxy's
    # X-Forwarded-For isn't believed (PR A2).
    app.add_middleware(ForwardedMiddleware, trusted=settings.trusted_proxies)
    if settings.allow_plain_http:
        log.warning(
            "MEALWRIGHT_ALLOW_PLAIN_HTTP is on: sign-in works over plain http://, so "
            "passwords and sign-in cookies can travel unencrypted. Use only for testing "
            "on a network you trust."
        )
    return app
