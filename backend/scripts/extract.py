"""Run pain-point extraction on a sample set with the configured provider.

Usage (from `backend/`):
    python -m scripts.extract --set freelance-invoicing [--interview I-01]

Prints verified pain points, rejected quotes, the "verified quotes: X/Y" metric
and token usage. Needs a working provider (see `python -m scripts.check_llm`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_settings
from app.llm import LLMError, UsageTracker, create_provider, default_options
from app.services.corpus import build_corpus
from app.services.extraction import ExtractionConfig, extract_corpus
from app.services.samples import load_sample_set


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_id", default="freelance-invoicing")
    parser.add_argument("--interview", help="only this interview ID")
    args = parser.parse_args()

    settings = get_settings()
    corpus = load_sample_set(args.set_id).corpus
    if args.interview:
        corpus = build_corpus([t for t in corpus.transcripts if t.id == args.interview])
    provider = create_provider(settings)
    tracker = UsageTracker(run_id=f"extract-{args.set_id}")
    try:
        result = await extract_corpus(
            corpus,
            provider,
            options=default_options(settings),
            tracker=tracker,
            config=ExtractionConfig.from_settings(settings),
        )
    except LLMError as exc:
        print(f"error: {exc}")
        return 1
    finally:
        await provider.aclose()

    for p in result.pain_points:
        e = p.evidence
        print(f"[{p.id}] ({p.intensity}) {p.summary}")
        print(
            f'    {e.interview_id} S{e.segment} {e.speaker} [{e.match} {e.score:.2f}]: "{e.quote}"'
        )
    if result.rejected:
        print("\nRejected quotes (never shown as evidence):")
        for r in result.rejected:
            print(f'  {r.interview_id} S{r.claimed_segment}: "{r.quote}" -> {r.reason}')
    for f in result.failures:
        print(f"  FAILED {f.interview_id} {f.segments}: {f.error}")
    usage = tracker.summary()
    print(f"\n{result.stats.label()} (exact {result.stats.exact}, fuzzy {result.stats.fuzzy})")
    print(f"{usage.calls} calls, {usage.total_tokens} tokens, {usage.cost_eur:.2f} EUR")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
