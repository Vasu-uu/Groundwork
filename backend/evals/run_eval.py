"""Run the analysis on every hand-labelled sample set and score it.

Usage (from `backend/`):

    python -m evals.run_eval                    # provider from .env (Ollama by default)
    python -m evals.run_eval --provider demo    # harness self-check, no model needed
    python -m evals.run_eval --set physio-no-shows --out evals/results/my-run.md

Prints a Markdown table (quote verification rate, verdict agreement, stance
agreement, pain-quote recall, calls, tokens, time) and, with `--out`, saves it.
The demo provider replays the labels themselves, so it measures the pipeline's
deterministic parts (verification, frequencies, verdict rules), not a model.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import ProviderName, get_settings
from app.llm import LLMError, UsageTracker, create_provider, default_options
from app.services.analysis import AnalysisConfig, run_analysis
from app.services.samples import list_sample_sets, load_labels, load_sample_set
from evals.harness import SetScore, score, to_markdown


async def evaluate(
    set_ids: list[str], provider_name: str | None
) -> tuple[list[SetScore], str, str]:
    settings = get_settings()
    if provider_name:
        settings = settings.model_copy(update={"llm_provider": ProviderName(provider_name)})
    provider = create_provider(settings)
    scores = []
    try:
        for set_id in set_ids:
            sample = load_sample_set(set_id)
            tracker = UsageTracker(f"eval-{set_id}")
            print(f"... {set_id}: {len(sample.corpus.transcripts)} interviews", file=sys.stderr)
            started = time.perf_counter()
            result = await run_analysis(
                sample.corpus,
                sample.hypotheses,
                provider,
                options=default_options(settings),
                tracker=tracker,
                config=AnalysisConfig.from_settings(settings),
            )
            s = score(sample, load_labels(set_id), result)
            usage = tracker.summary()
            s.calls, s.failed_calls, s.tokens = usage.calls, usage.failed_calls, usage.total_tokens
            s.seconds = time.perf_counter() - started
            scores.append(s)
    finally:
        await provider.aclose()
    return scores, provider.name, provider.model


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--set", dest="set_ids", action="append", help="sample set id (repeatable)")
    parser.add_argument("--provider", choices=[p.value for p in ProviderName if p != "mock"])
    parser.add_argument("--out", type=Path, help="also write the Markdown report here")
    args = parser.parse_args()

    set_ids = args.set_ids or [s.id for s in list_sample_sets()]
    try:
        scores, provider, model = asyncio.run(evaluate(set_ids, args.provider))
    except LLMError as exc:
        print(f"Model error: {exc}", file=sys.stderr)
        return 1
    report = to_markdown(
        scores,
        provider=provider,
        model=model,
        when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Saved to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
