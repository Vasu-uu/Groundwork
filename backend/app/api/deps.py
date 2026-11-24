"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.llm import LLMProvider
from app.services.runner import AnalysisRunner


def get_provider(request: Request) -> LLMProvider:
    """The process-wide LLM provider created at startup."""
    return request.app.state.provider


def get_app_settings(request: Request) -> Settings:
    """Settings the app was created with (lets tests override them)."""
    return request.app.state.settings


def get_runner(request: Request) -> AnalysisRunner:
    return request.app.state.runner


def get_db(request: Request) -> Iterator[Session]:
    """One session per request: committed on success, rolled back on error."""
    with request.app.state.session_factory() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
