"""Run the full analysis (extract, cluster, assess, decide) on a sample set.

Usage (from `backend/`):
    python -m scripts.analyze --set freelance-invoicing

Prints pain themes with frequencies and the AI-suggested verdict for each
hypothesis, with its confidence note and what would change it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_settings
from app.llm import LLMError, UsageTracker, create_provider, default_options
from app.services.analysis import AnalysisConfig, run_analysis
from app.services.samples import load_sample_set


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_id", default="freelance-invoicing")
    args = parser.parse_args()

    settings = get_settings()
    sample = load_sample_set(args.set_id)
    provider = create_provider(settings)
    tracker = UsageTracker(run_id=f"analyze-{args.set_id}")
    try:
        result = await run_analysis(
            sample.corpus,
            sample.hypotheses,
            provider,
            options=default_options(settings),
            tracker=tracker,
            config=AnalysisConfig.from_settings(settings),
            on_progress=lambda step: print(f"... {step}", file=sys.stderr),
        )
    except LLMError as exc:
        print(f"error: {exc}")
        return 1
    finally:
        await provider.aclose()

    for w in result.warnings:
        print(f"! {w}")
    print(f"\nThemes ({result.clustering.method}):")
    for t in result.clustering.themes:
        print(f"  {t.id} [{t.frequency}/{result.interview_count} interviewees] {t.label}")
    print("\nHypotheses (AI suggestions, pending founder review):")
    for v in result.verdicts:
        print(f"  {v.hypothesis.id} {v.verdict} ({v.confidence} confidence): {v.hypothesis.text}")
        print(f"     {v.confidence_note}")
        print(f"     What would change it: {v.what_would_change}")
    usage = tracker.summary()
    print(f"\n{result.quote_stats.label()}")
    print(f"{usage.calls} calls, {usage.total_tokens} tokens, {usage.cost_eur:.2f} EUR")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
