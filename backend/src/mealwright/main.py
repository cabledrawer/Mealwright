"""The FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mealwright import __version__, migrate
from mealwright.api.v1 import router as api_v1
from mealwright.config import Settings, get_settings
from mealwright.db import make_engine, make_sessionmaker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
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
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.include_router(api_v1)
    return app
