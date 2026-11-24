"""Application settings, loaded from environment variables and an optional `.env` file.

Every setting has a safe default so the app starts with zero configuration
(local Ollama, deterministic generation). See `.env.example` at the repo root.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class ProviderName(StrEnum):
    """Supported LLM providers. All of them are free to use at runtime."""

    OLLAMA = "ollama"
    GROQ = "groq"
    MOCK = "mock"


class Settings(BaseSettings):
    """Typed runtime configuration."""

    model_config = SettingsConfigDict(
        # Look for `.env` in the repo root first, then the current directory.
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Provider selection
    llm_provider: ProviderName = ProviderName.OLLAMA

    # Generation settings shared by all providers (determinism first).
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_seed: int | None = 42
    llm_timeout_seconds: float = Field(default=300.0, gt=0)
    # Retries after invalid structured output (the first attempt is not counted).
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    # Parallel LLM calls. 1 suits a single local GPU; raise for hosted providers.
    llm_concurrency: int = Field(default=1, ge=1, le=8)

    # Analysis
    # Minimum similarity for a fuzzy quote match to count as verified.
    quote_match_threshold: float = Field(default=0.92, ge=0.5, le=1.0)
    # Max transcript characters per extraction prompt (map-reduce chunk size).
    extraction_chunk_chars: int = Field(default=6000, ge=500)

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_num_ctx: int = Field(default=8192, ge=512)
    ollama_force_cpu: bool = False

    # Groq free tier
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # App
    database_url: str = "sqlite:///./data/groundwork.db"
    # NoDecode: parse the raw env string ourselves (comma-separated) instead of as JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a JSON list."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value: object) -> object:
        """Treat `GROQ_API_KEY=` (empty, as in `.env.example`) as unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def active_model(self) -> str:
        """Model name for the currently selected provider."""
        return {
            ProviderName.OLLAMA: self.ollama_model,
            ProviderName.GROQ: self.groq_model,
            ProviderName.MOCK: "mock",
        }[self.llm_provider]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached; override in tests via DI)."""
    return Settings()
