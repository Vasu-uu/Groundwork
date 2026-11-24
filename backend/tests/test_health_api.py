from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import HealthStatus, ProviderHealth
from app.llm.mock import MockProvider
from app.main import create_app


class DownProvider(MockProvider):
    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="ollama",
            model="qwen2.5:7b",
            status=HealthStatus.UNREACHABLE,
            detail="Cannot reach Ollama",
            hint="ollama serve",
        )


def client_for(provider) -> TestClient:
    settings = Settings(_env_file=None, llm_provider="mock")
    return TestClient(create_app(settings=settings, provider=provider))


def test_health_ok():
    with client_for(MockProvider()) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm"]["ok"] is True
    assert body["cost_eur"] == 0.0


def test_health_degraded_when_model_unreachable():
    with client_for(DownProvider()) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["llm"]["status"] == "unreachable"
    assert body["llm"]["hint"] == "ollama serve"
