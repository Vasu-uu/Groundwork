"""Smoke-test the configured LLM provider end to end.

Usage (from `backend/`):  python -m scripts.check_llm

Prints the health probe, then runs one tiny JSON-mode generation and reports
token usage and latency. Exits non-zero if the provider is not usable.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.llm import LLMError, Message, UsageTracker, create_provider, default_options


async def main() -> int:
    settings = get_settings()
    provider = create_provider(settings)
    try:
        health = await provider.health()
        print(f"provider={health.provider} model={health.model} status={health.status}")
        print(f"  {health.detail}")
        if health.hint:
            print(f"  hint: {health.hint}")
        if not health.ok:
            return 1

        options = default_options(settings).model_copy(
            update={
                "json_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                }
            }
        )
        messages = [
            Message(role="system", content="Reply with JSON only."),
            Message(role="user", content='Say hello. Return {"answer": "..."}.'),
        ]
        tracker = UsageTracker(run_id="smoke")
        try:
            resp = await provider.generate(messages, options)
        except LLMError as exc:
            print(f"generation failed: {exc}")
            return 1
        tracker.record(resp, purpose="smoke")
        s = tracker.summary()
        print(f"  output: {resp.text.strip()[:200]}")
        print(f"  tokens: {s.total_tokens} ({s.prompt_tokens} in / {s.completion_tokens} out)")
        print(f"  latency: {resp.latency_ms:.0f} ms, cost: {s.cost_eur:.2f} EUR")
        return 0
    finally:
        await provider.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
