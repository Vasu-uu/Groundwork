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
from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.llm import LLMProvider, create_provider


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    """Application factory. Tests inject settings and a provider directly."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.provider = provider or create_provider(settings)
        logging.getLogger("groundwork").info(
            "Groundwork %s started with provider=%s model=%s",
            __version__,
            app.state.provider.name,
            app.state.provider.model,
        )
        try:
            yield
        finally:
            await app.state.provider.aclose()

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
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
