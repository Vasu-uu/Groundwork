"""FastAPI application entry point.

Run locally with:  uvicorn app.main:app --reload  (from the `backend/` folder)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import install_error_handlers
from app.api.health import router as health_router
from app.api.studies import router as studies_router
from app.config import Settings, get_settings
from app.db.session import init_db, make_engine
from app.llm import LLMProvider, create_provider, default_options
from app.services.analysis import AnalysisConfig
from app.services.runner import AnalysisRunner
from app.services.studies import recover_interrupted

logger = logging.getLogger("groundwork")


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    """Application factory. Tests inject settings and a provider directly."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        session_factory = init_db(engine)
        with session_factory.begin() as db:
            if interrupted := recover_interrupted(db):
                logger.warning("%d analysis run(s) were interrupted by a restart", interrupted)

        app.state.settings = settings
        app.state.session_factory = session_factory
        app.state.provider = provider or create_provider(settings)
        app.state.runner = AnalysisRunner(
            app.state.provider,
            session_factory,
            options=default_options(settings),
            config=AnalysisConfig.from_settings(settings),
        )
        logger.info(
            "Groundwork %s started with provider=%s model=%s",
            __version__,
            app.state.provider.name,
            app.state.provider.model,
        )
        try:
            yield
        finally:
            await app.state.provider.aclose()
            engine.dispose()

    app = FastAPI(
        title="Groundwork API",
        version=__version__,
        description="Evidence-first customer discovery copilot.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(studies_router, prefix="/api")
    return app


app = create_app()
