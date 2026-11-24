"""Ollama provider: local open-weight models (default).

Uses the native Ollama HTTP API:
- `POST /api/chat` with `stream=false` for generation. `format` accepts a JSON
  schema, which Ollama enforces with constrained decoding.
- `GET /api/tags` for the health check (lists locally pulled models).

Inference runs on the GPU when one is available and falls back to CPU
automatically. `force_cpu=True` sends `num_gpu=0` to pin it to CPU, for
machines whose GPU is too small for the chosen model.
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

_HEALTH_TIMEOUT = 5.0


def _same_model(wanted: str, available: str) -> bool:
    """Ollama reports `llama3.1:latest` for a model pulled as `llama3.1`."""
    if ":" not in wanted:
        wanted = f"{wanted}:latest"
    return wanted == available


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        *,
        num_ctx: int = 8192,
        force_cpu: bool = False,
        timeout: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(model)
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.force_cpu = force_cpu
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    def _payload(self, messages: list[Message], options: GenerationOptions) -> dict[str, Any]:
        model_options: dict[str, Any] = {
            "temperature": options.temperature,
            "num_ctx": self.num_ctx,
        }
        if options.seed is not None:
            model_options["seed"] = options.seed
        if options.max_tokens is not None:
            model_options["num_predict"] = options.max_tokens
        if self.force_cpu:
            model_options["num_gpu"] = 0

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
            "options": model_options,
        }
        if options.json_schema is not None:
            payload["format"] = options.json_schema
        return payload

    async def generate(
        self, messages: list[Message], options: GenerationOptions | None = None
    ) -> LLMResponse:
        options = options or GenerationOptions()
        started = time.perf_counter()
        try:
            resp = await self._client.post("/api/chat", json=self._payload(messages, options))
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                f"Ollama timed out after {self._client.timeout.read}s. "
                "CPU inference is slow; raise LLM_TIMEOUT_SECONDS or use a smaller model."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` running?"
            ) from exc

        if resp.status_code == 404:
            raise ProviderConfigError(
                f"Model '{self.model}' is not available in Ollama. Run `ollama pull {self.model}`."
            )
        if resp.status_code >= 400:
            raise ProviderResponseError(f"Ollama error {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            text = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderResponseError("Ollama returned an unexpected payload") from exc

        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def health(self) -> ProviderHealth:
        def result(status: HealthStatus, detail: str, hint: str | None = None) -> ProviderHealth:
            return ProviderHealth(
                provider=self.name, model=self.model, status=status, detail=detail, hint=hint
            )

        try:
            resp = await self._client.get("/api/tags", timeout=_HEALTH_TIMEOUT)
            resp.raise_for_status()
            names = [m.get("name", "") for m in resp.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as exc:
            return result(
                HealthStatus.UNREACHABLE,
                f"Cannot reach Ollama at {self.base_url} ({type(exc).__name__}).",
                hint="Install Ollama from https://ollama.com and run `ollama serve`.",
            )

        if not any(_same_model(self.model, n) for n in names):
            return result(
                HealthStatus.MODEL_MISSING,
                f"Ollama is running but model '{self.model}' is not pulled.",
                hint=f"ollama pull {self.model}",
            )
        device = "CPU (forced)" if self.force_cpu else "GPU if available, else CPU"
        return result(HealthStatus.OK, f"Ollama reachable, model ready. Device: {device}.")

    async def aclose(self) -> None:
        await self._client.aclose()
