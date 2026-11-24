"""Health check endpoint.

Always answers HTTP 200 while the API process is up. Whether the LLM is usable
is reported in the body, so the UI can show an explicit failure state
("model unreachable", "model not pulled") instead of a generic network error.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.api.deps import get_provider
from app.llm import LLMProvider, ProviderHealth

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    llm: ProviderHealth
    # Runtime models are open-weight (Ollama) or free tier: no cost per run.
    cost_eur: float = 0.0


@router.get("/health", response_model=HealthResponse)
async def health(provider: Annotated[LLMProvider, Depends(get_provider)]) -> HealthResponse:
    llm = await provider.health()
    return HealthResponse(status="ok" if llm.ok else "degraded", version=__version__, llm=llm)
