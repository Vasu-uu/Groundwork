import json

import httpx
import pytest

from app.llm import (
    GenerationOptions,
    HealthStatus,
    Message,
    ProviderConfigError,
    ProviderUnavailableError,
)
from app.llm.groq import GroqProvider

MSGS = [Message(role="user", content="hi")]


def make(handler, api_key: str | None = "test-key") -> GroqProvider:
    return GroqProvider(
        model="llama-3.1-8b-instant", api_key=api_key, transport=httpx.MockTransport(handler)
    )


async def test_generate_uses_json_mode_seed_and_parses_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "llama-3.1-8b-instant",
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 2},
            },
        )

    resp = await make(handler).generate(
        MSGS, GenerationOptions(seed=1, json_schema={"type": "object"})
    )
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["seed"] == 1
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert (resp.prompt_tokens, resp.completion_tokens) == (30, 2)


async def test_missing_key_is_config_error_and_unhealthy():
    provider = make(lambda r: httpx.Response(200), api_key=None)
    with pytest.raises(ProviderConfigError):
        await provider.generate(MSGS)
    assert (await provider.health()).status is HealthStatus.MISCONFIGURED


async def test_rejected_key_and_rate_limit():
    with pytest.raises(ProviderConfigError):
        await make(lambda r: httpx.Response(401)).generate(MSGS)
    with pytest.raises(ProviderUnavailableError, match="rate limit"):
        await make(lambda r: httpx.Response(429)).generate(MSGS)


async def test_health_checks_model_listing():
    listing = {"data": [{"id": "llama-3.1-8b-instant"}]}
    assert (await make(lambda r: httpx.Response(200, json=listing)).health()).ok
    other = {"data": [{"id": "something-else"}]}
    health = await make(lambda r: httpx.Response(200, json=other)).health()
    assert health.status is HealthStatus.MODEL_MISSING
