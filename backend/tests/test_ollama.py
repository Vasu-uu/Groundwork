import json

import httpx
import pytest

from app.llm import (
    GenerationOptions,
    HealthStatus,
    Message,
    ProviderConfigError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.llm.ollama import OllamaProvider

MSGS = [Message(role="user", content="hi")]


def make(handler, **kwargs) -> OllamaProvider:
    return OllamaProvider(
        model=kwargs.pop("model", "qwen2.5:7b"), transport=httpx.MockTransport(handler), **kwargs
    )


async def test_generate_sends_deterministic_options_and_parses_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "prompt_eval_count": 12,
                "eval_count": 5,
            },
        )

    provider = make(handler)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    resp = await provider.generate(
        MSGS, GenerationOptions(temperature=0.0, seed=7, json_schema=schema)
    )

    assert seen["path"] == "/api/chat"
    body = seen["body"]
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.0
    assert body["options"]["seed"] == 7
    assert body["options"]["num_ctx"] == 8192
    assert "num_gpu" not in body["options"]
    assert body["format"] == schema
    assert resp.text == '{"ok": true}'
    assert (resp.prompt_tokens, resp.completion_tokens, resp.total_tokens) == (12, 5, 17)
    assert resp.provider == "ollama"


async def test_force_cpu_sets_num_gpu_zero():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "x"}})

    await make(handler, force_cpu=True).generate(MSGS)
    assert seen["body"]["options"]["num_gpu"] == 0
    assert "format" not in seen["body"]


async def test_missing_model_raises_config_error():
    provider = make(lambda r: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(ProviderConfigError, match="ollama pull qwen2.5:7b"):
        await provider.generate(MSGS)


async def test_connection_error_raises_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailableError):
        await make(handler).generate(MSGS)


async def test_bad_payload_raises_response_error():
    with pytest.raises(ProviderResponseError):
        await make(lambda r: httpx.Response(200, json={"nope": 1})).generate(MSGS)


async def test_health_ok_matches_latest_tag():
    tags = {"models": [{"name": "llama3.1:latest"}]}
    health = await make(lambda r: httpx.Response(200, json=tags), model="llama3.1").health()
    assert health.status is HealthStatus.OK
    assert health.ok


async def test_health_model_missing_gives_pull_hint():
    tags = {"models": [{"name": "llama3.1:latest"}]}
    health = await make(lambda r: httpx.Response(200, json=tags)).health()
    assert health.status is HealthStatus.MODEL_MISSING
    assert health.hint == "ollama pull qwen2.5:7b"


async def test_health_unreachable_never_raises():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    health = await make(handler).health()
    assert health.status is HealthStatus.UNREACHABLE
    assert not health.ok
