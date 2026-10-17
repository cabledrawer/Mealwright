"""The FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.telemetry import TelemetryConfig

from mealwright import __version__, migrate
from mealwright.api.v1 import router as api_v1
from mealwright.auth import SlowDown
from mealwright.config import Settings, get_settings
from mealwright.db import make_engine, make_sessionmaker
from mealwright.outbound import OutboundGate, install_network_guard
from mealwright.security import SecurityHeadersMiddleware

# FastAPI's built-in OpenTelemetry support: switch every part of it off, and never
# configure exporters from OTEL_* / FASTAPI_OTEL_* environment variables.
TELEMETRY_OFF: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # From here on, only the outbound gate may connect to anything (spec section 7).
    install_network_guard()
    engine = make_engine(settings.sqlalchemy_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_start:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            migrate.upgrade(engine)
        yield
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
    app.state.outbound = OutboundGate(app.state.sessionmaker)
    app.state.slow_down = SlowDown()
    app.include_router(api_v1)
    # Strict browser rules on every response (spec section 7).
    app.add_middleware(SecurityHeadersMiddleware)
    return app
