"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.llm import LLMProvider


def get_provider(request: Request) -> LLMProvider:
    """The process-wide LLM provider created at startup."""
    return request.app.state.provider


def get_app_settings(request: Request) -> Settings:
    """Settings the app was created with (lets tests override them)."""
    return request.app.state.settings
