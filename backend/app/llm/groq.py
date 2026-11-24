"""Groq provider: optional free-tier hosted API, for deployed demo links.

Groq exposes an OpenAI-compatible chat-completions endpoint and hosts
open-weight models (Llama, Qwen, ...). Only the free tier is assumed; no paid
features are used. Requires `GROQ_API_KEY` (free key from console.groq.com).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.llm.base import (
    GenerationOptions,
    HealthStatus,
    LLMProvider,
    LLMResponse,
    Message,
    ProviderConfigError,
    ProviderHealth,
    ProviderResponseError,
    ProviderUnavailableError,
)

_HEALTH_TIMEOUT = 10.0


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self,
        model: str,
        api_key: str | None,
        base_url: str = "https://api.groq.com/openai/v1",
        *,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(model)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=headers, transport=transport
        )

    def _payload(self, messages: list[Message], options: GenerationOptions) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": options.temperature,
        }
        if options.seed is not None:
            payload["seed"] = options.seed
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if options.json_schema is not None:
            # JSON mode is supported by all Groq chat models; strict schema mode
            # is not, so the schema is enforced by our own validation layer.
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def generate(
        self, messages: list[Message], options: GenerationOptions | None = None
    ) -> LLMResponse:
        if not self.api_key:
            raise ProviderConfigError(
                "GROQ_API_KEY is not set. Get a free key at console.groq.com."
            )
        options = options or GenerationOptions()
        started = time.perf_counter()
        try:
            resp = await self._client.post(
                "/chat/completions", json=self._payload(messages, options)
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Cannot reach Groq at {self.base_url}.") from exc

        if resp.status_code in (401, 403):
            raise ProviderConfigError("Groq rejected the API key (check GROQ_API_KEY).")
        if resp.status_code == 429:
            raise ProviderUnavailableError("Groq free-tier rate limit reached; retry shortly.")
        if resp.status_code >= 400:
            raise ProviderResponseError(f"Groq error {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError("Groq returned an unexpected payload") from exc

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def health(self) -> ProviderHealth:
        def result(status: HealthStatus, detail: str, hint: str | None = None) -> ProviderHealth:
            return ProviderHealth(
                provider=self.name, model=self.model, status=status, detail=detail, hint=hint
            )

        if not self.api_key:
            return result(
                HealthStatus.MISCONFIGURED,
                "GROQ_API_KEY is not set.",
                hint="Create a free key at https://console.groq.com/keys and add it to .env.",
            )
        try:
            resp = await self._client.get("/models", timeout=_HEALTH_TIMEOUT)
        except httpx.HTTPError as exc:
            return result(HealthStatus.UNREACHABLE, f"Cannot reach Groq ({type(exc).__name__}).")
        if resp.status_code in (401, 403):
            return result(HealthStatus.MISCONFIGURED, "Groq rejected the API key.")
        if resp.status_code >= 400:
            return result(HealthStatus.UNREACHABLE, f"Groq returned HTTP {resp.status_code}.")
        try:
            ids = [m.get("id") for m in resp.json().get("data", [])]
        except ValueError:
            return result(HealthStatus.UNREACHABLE, "Groq returned an unexpected payload.")
        if self.model not in ids:
            return result(
                HealthStatus.MODEL_MISSING,
                f"Model '{self.model}' is not offered by Groq.",
                hint="Pick a model listed at https://console.groq.com/docs/models.",
            )
        return result(HealthStatus.OK, "Groq reachable, model available (free tier).")

    async def aclose(self) -> None:
        await self._client.aclose()
