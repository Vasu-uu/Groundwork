"""Build the configured `LLMProvider` from settings."""

from __future__ import annotations

from app.config import ProviderName, Settings
from app.llm.base import GenerationOptions, LLMProvider
from app.llm.groq import GroqProvider
from app.llm.mock import MockProvider
from app.llm.ollama import OllamaProvider


def create_provider(settings: Settings) -> LLMProvider:
    """Instantiate the provider selected by `LLM_PROVIDER`."""
    match settings.llm_provider:
        case ProviderName.OLLAMA:
            return OllamaProvider(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                num_ctx=settings.ollama_num_ctx,
                force_cpu=settings.ollama_force_cpu,
                timeout=settings.llm_timeout_seconds,
            )
        case ProviderName.GROQ:
            key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else None
            return GroqProvider(
                model=settings.groq_model,
                api_key=key,
                base_url=settings.groq_base_url,
                timeout=settings.llm_timeout_seconds,
            )
        case ProviderName.MOCK:
            return MockProvider()
        case ProviderName.DEMO:
            from app.llm.demo import DemoProvider  # imports the sample loader; keep it lazy

            return DemoProvider()
    raise ValueError(f"Unknown provider: {settings.llm_provider}")  # pragma: no cover


def default_options(settings: Settings) -> GenerationOptions:
    """Generation options from settings (low temperature, fixed seed)."""
    return GenerationOptions(temperature=settings.llm_temperature, seed=settings.llm_seed)
