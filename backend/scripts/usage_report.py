"""Summarise logged model calls for the AI Disclosure Statement.

Usage (from `backend/`):
    python -m scripts.usage_report                 # database from .env
    python -m scripts.usage_report --study <id>    # one study only

Every model call Groundwork makes is stored (provider, model, prompt version,
tokens, latency, success). This prints a Markdown table to paste into
docs/ai-disclosure.md.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from sqlalchemy import select

from app.config import get_settings
from app.db.models import LLMCallRow
from app.db.session import init_db, make_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", help="only calls for this study ID")
    args = parser.parse_args()

    session_factory = init_db(make_engine(get_settings().database_url))
    with session_factory() as db:
        query = select(LLMCallRow)
        if args.study:
            query = query.where(LLMCallRow.study_id == args.study)
        rows = list(db.scalars(query))

    if not rows:
        print("No model calls logged yet.")
        return 0

    groups: dict[tuple[str, str, str], list[LLMCallRow]] = defaultdict(list)
    for r in rows:
        prompt = r.purpose.split(":")[0]
        groups[(r.provider, r.model, prompt)].append(r)

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    studies = len({r.study_id for r in rows})
    first, last = min(r.at for r in rows), max(r.at for r in rows)
    print(
        f"Model calls logged from {first:%Y-%m-%d} to {last:%Y-%m-%d} across {studies} studies.\n"
    )
    print(
        "| Provider | Model | Prompt | Calls | Failed "
        "| Prompt tokens | Completion tokens | Avg latency |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for (provider, model, prompt), calls in sorted(groups.items()):
        ok = [c for c in calls if c.ok]
        avg = sum(c.latency_ms for c in ok) / len(ok) / 1000 if ok else 0
        print(
            f"| {provider} | {model} | {prompt} | {len(calls)} | {len(calls) - len(ok)} "
            f"| {sum(c.prompt_tokens for c in calls)} | {sum(c.completion_tokens for c in calls)} "
            f"| {avg:.1f}s |"
        )
    total = sum(r.prompt_tokens + r.completion_tokens for r in rows)
    print(f"\n**Total:** {len(rows)} calls, {total} tokens, cost 0 EUR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
