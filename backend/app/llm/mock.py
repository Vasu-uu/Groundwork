"""Deterministic in-process provider for tests and offline demos.

It never touches the network. Responses come from a script: either a list
consumed in order, or a function of the incoming messages.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable

from app.llm.base import (
    GenerationOptions,
    HealthStatus,
    LLMProvider,
    LLMResponse,
    Message,
    ProviderHealth,
    ProviderResponseError,
)

Responder = Callable[[list[Message], GenerationOptions], str]


def _approx_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) so usage numbers are non-zero."""
    return max(1, len(text) // 4)


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(
        self,
        responses: Iterable[str] | Responder | None = None,
        model: str = "mock",
    ) -> None:
        super().__init__(model)
        self._responder: Responder | None = responses if callable(responses) else None
        self._queue: deque[str] = deque(
            [] if responses is None or callable(responses) else responses
        )
        #: Every call received, for assertions in tests.
        self.calls: list[tuple[list[Message], GenerationOptions]] = []

    async def generate(
        self, messages: list[Message], options: GenerationOptions | None = None
    ) -> LLMResponse:
        options = options or GenerationOptions()
        self.calls.append((messages, options))
        if self._responder is not None:
            text = self._responder(messages, options)
        elif self._queue:
            text = self._queue.popleft()
        else:
            raise ProviderResponseError("MockProvider has no scripted response left")
        prompt = "".join(m.content for m in messages)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=_approx_tokens(prompt),
            completion_tokens=_approx_tokens(text),
            latency_ms=0.0,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            model=self.model,
            status=HealthStatus.OK,
            detail="Mock provider (no model, deterministic scripted output).",
        )
