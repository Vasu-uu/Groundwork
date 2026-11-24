import pytest

from app.config import ProviderName, Settings
from app.llm import create_provider, default_options
from app.llm.groq import GroqProvider
from app.llm.mock import MockProvider
from app.llm.ollama import OllamaProvider


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep a developer's local .env from leaking into these tests."""
    for var in ("LLM_PROVIDER", "GROQ_API_KEY", "CORS_ORIGINS", "OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_are_local_and_deterministic():
    s = Settings(_env_file=None)
    assert s.llm_provider is ProviderName.OLLAMA
    assert s.llm_temperature <= 0.2
    assert s.llm_seed is not None
    opts = default_options(s)
    assert (opts.temperature, opts.seed) == (s.llm_temperature, s.llm_seed)


def test_env_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["http://a.test", "http://b.test"]
    assert s.groq_api_key is None
    assert s.active_model == s.groq_model


@pytest.mark.parametrize(
    ("name", "cls"),
    [("ollama", OllamaProvider), ("groq", GroqProvider), ("mock", MockProvider)],
)
async def test_factory_builds_selected_provider(name, cls):
    provider = create_provider(Settings(_env_file=None, llm_provider=name))
    assert isinstance(provider, cls)
    await provider.aclose()
