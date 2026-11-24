"""Per-run token and call accounting.

Every LLM call made during an analysis run is recorded here so the UI can show
"0 EUR, N tokens" and the AI Disclosure Statement can be filled from real logs.
Persistence to SQLite is added with the API layer (Stage 5); this module only
holds the in-memory record and logs each call.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.llm.base import LLMResponse

logger = logging.getLogger("groundwork.llm.usage")


class CallRecord(BaseModel):
    """One LLM call."""

    purpose: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    ok: bool = True
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UsageSummary(BaseModel):
    """Aggregate usage for one run."""

    run_id: str
    calls: int
    failed_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    # Runtime models are open-weight or free tier, so the cost is always zero.
    cost_eur: float = 0.0
    providers: list[str]
    models: list[str]


class UsageTracker:
    """Collects `CallRecord`s for a single analysis run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.records: list[CallRecord] = []

    def record(self, response: LLMResponse, purpose: str) -> CallRecord:
        """Record a successful call."""
        rec = CallRecord(
            purpose=purpose,
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
        )
        self.records.append(rec)
        logger.info(
            "llm_call run=%s purpose=%s provider=%s model=%s prompt=%d completion=%d ms=%.0f",
            self.run_id,
            purpose,
            rec.provider,
            rec.model,
            rec.prompt_tokens,
            rec.completion_tokens,
            rec.latency_ms,
        )
        return rec

    def record_failure(self, provider: str, model: str, purpose: str) -> CallRecord:
        """Record a call that failed (still counts as a call in the disclosure)."""
        rec = CallRecord(
            purpose=purpose,
            provider=provider,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0.0,
            ok=False,
        )
        self.records.append(rec)
        logger.warning(
            "llm_call_failed run=%s purpose=%s provider=%s", self.run_id, purpose, provider
        )
        return rec

    def summary(self) -> UsageSummary:
        prompt = sum(r.prompt_tokens for r in self.records)
        completion = sum(r.completion_tokens for r in self.records)
        return UsageSummary(
            run_id=self.run_id,
            calls=len(self.records),
            failed_calls=sum(1 for r in self.records if not r.ok),
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            providers=sorted({r.provider for r in self.records}),
            models=sorted({r.model for r in self.records}),
        )
