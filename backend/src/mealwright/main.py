"""The FastAPI application."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.telemetry import TelemetryConfig
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from mealwright import __version__, errors, events, jobs, migrate
from mealwright.api.v1 import router as api_v1
from mealwright.auth import SlowDown
from mealwright.config import Settings, get_settings
from mealwright.db import make_engine, make_sessionmaker
from mealwright.events import Broadcaster
from mealwright.frontend import inline_script_hashes, mount_frontend
from mealwright.logs import DailyLogFile
from mealwright.outbound import OutboundGate, install_network_guard
from mealwright.security import SecurityHeadersMiddleware

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


def create_app(settings: Settings | None = None, log_file: DailyLogFile | None = None) -> FastAPI:
    settings = settings or get_settings()
    # From here on, only the outbound gate may connect to anything (spec section 7).
    install_network_guard()
    engine = make_engine(settings.sqlalchemy_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_start:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            migrate.upgrade(engine)
        background = None
        if settings.run_jobs:
            background = jobs.scheduler(app.state.sessionmaker, log_file)
            background.start()
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
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.events = Broadcaster()
    events.install(app.state.sessionmaker, app.state.events)
    app.state.outbound = OutboundGate(app.state.sessionmaker)
    app.state.slow_down = SlowDown()
    errors.install(app)
    app.include_router(api_v1)
    mount_frontend(app, settings.frontend_dir)  # after the API, so it only gets the rest
    # Strict browser rules on every response (spec section 7). The web app's own inline
    # start-up scripts are allowed by their exact fingerprint, nothing else.
    app.add_middleware(
        SecurityHeadersMiddleware, script_hashes=inline_script_hashes(settings.frontend_dir)
    )
    # Outermost: the visitor's real address and scheme from the reverse proxy's
    # X-Forwarded-For/-Proto headers, believed only from MEALWRIGHT_TRUSTED_PROXIES (off
    # by default). The sign-in slow-down counts per address, so it needs the real one.
    if settings.trusted_proxies.strip():
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)
    if settings.allow_plain_http:
        log.warning(
            "MEALWRIGHT_ALLOW_PLAIN_HTTP is on: sign-in works over plain http://, so "
            "passwords and sign-in cookies can travel unencrypted. Use only for testing "
            "on a network you trust."
        )
    return app
