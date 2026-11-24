"""Map domain errors to HTTP responses with a stable shape:

{"error": {"code": "checkpoint_required", "message": "..."}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.llm import LLMError, ProviderConfigError, ProviderUnavailableError
from app.services.analysis import AnalysisInputError
from app.services.documents import DocumentError
from app.services.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
)

_STATUS = [(NotFoundError, 404), (ConflictError, 409), (InvalidInputError, 422)]


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        status = next((s for cls, s in _STATUS if isinstance(exc, cls)), 400)
        return JSONResponse(_body(exc.code, exc.message), status_code=status)

    @app.exception_handler(AnalysisInputError)
    async def _analysis_input(_: Request, exc: AnalysisInputError) -> JSONResponse:
        return JSONResponse(_body("invalid_input", str(exc)), status_code=422)

    @app.exception_handler(DocumentError)
    async def _document(_: Request, exc: DocumentError) -> JSONResponse:
        return JSONResponse(_body("invalid_document", str(exc)), status_code=422)

    @app.exception_handler(LLMError)
    async def _llm(_: Request, exc: LLMError) -> JSONResponse:
        # Only synchronous model calls (script drafting) reach here; background
        # analyses report failures through the study status instead.
        if isinstance(exc, ProviderUnavailableError):
            code, status = "provider_unavailable", 503
        elif isinstance(exc, ProviderConfigError):
            code, status = "provider_config", 503
        else:
            code, status = "model_output", 502
        return JSONResponse(_body(code, str(exc)), status_code=status)
