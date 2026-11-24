"""The `LLMProvider` interface every model backend implements.

Services never talk to a concrete provider: they depend on this interface and
receive an instance from `app.llm.factory.get_provider`. That keeps the choice
of model a pure configuration concern (`LLM_PROVIDER` in `.env`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    """One chat message."""

    role: Role
    content: str


class GenerationOptions(BaseModel):
    """Per-call generation settings. Defaults favour reproducibility."""

    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    seed: int | None = 42
    max_tokens: int | None = Field(default=None, gt=0)
    # When set, ask the provider for JSON output. Providers that support
    # schema-constrained decoding (Ollama) use the schema itself; others fall
    # back to plain JSON mode. Callers must still validate the result.
    json_schema: dict[str, Any] | None = None


class LLMResponse(BaseModel):
    """A completed generation plus the accounting needed for the AI disclosure."""

    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class HealthStatus(StrEnum):
    OK = "ok"
    MODEL_MISSING = "model_missing"
    UNREACHABLE = "unreachable"
    MISCONFIGURED = "misconfigured"


class ProviderHealth(BaseModel):
    """Result of a provider health probe. Never raises; failures are data."""

    provider: str
    model: str
    status: HealthStatus
    detail: str = ""
    # Extra hints for the UI, e.g. the exact command to fix a missing model.
    hint: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        return self.status is HealthStatus.OK


# --- Errors -------------------------------------------------------------------


class LLMError(Exception):
    """Base class for all provider errors."""


class ProviderUnavailableError(LLMError):
    """The provider could not be reached (server down, network error, timeout)."""


class ProviderConfigError(LLMError):
    """The provider is misconfigured (missing API key, unknown model, ...)."""


class ProviderResponseError(LLMError):
    """The provider answered, but with an error or an unusable payload."""


# --- Interface ----------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract chat-completion backend.

    Implementations must be safe to share across requests and must surface
    failures as the `LLMError` subclasses above, never as raw HTTP errors.
    """

    #: Short identifier, e.g. "ollama". Used in logs and the AI disclosure.
    name: str

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    async def generate(
        self, messages: list[Message], options: GenerationOptions | None = None
    ) -> LLMResponse:
        """Run one chat completion and return the text with token usage."""

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Probe the provider. Must not raise; report problems in the result."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Release network resources. Override when the provider holds a client."""
