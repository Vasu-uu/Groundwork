"""Cluster verified pain points into themes (map-reduce).

Map:    batches of pain points -> LLM groups them (`cluster_pain_points.v*`).
Reduce: when there was more than one batch, the batch themes are merged by
        meaning (`merge_themes.v*`).

The model only proposes groupings. Code then:
- drops IDs the model invented or used twice (reported in `dropped_ids`),
- computes frequency as the number of DISTINCT interviewees per theme,
- ranks themes and assigns stable IDs.

If the model cannot produce valid output, a deterministic keyword-overlap
fallback groups the pain points instead, and the result says so.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.llm import GenerationOptions, LLMProvider, UsageTracker
from app.llm.prompts import load_prompt
from app.llm.structured import StructuredOutputError, generate_structured
from app.models.analysis import ClusteringResult, Theme
from app.models.evidence import PainPoint

logger = logging.getLogger("groundwork.clustering")

_INTENSITY_RANK = {"low": 0, "medium": 1, "high": 2}


# --- Model output schemas ------------------------------------------------------------


def _wrap_list(key: str, data: Any) -> Any:
    return {key: data} if isinstance(data, list) else data


class LLMTheme(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=400)
    pain_point_ids: list[str] = Field(min_length=1)


class ClusterOutput(BaseModel):
    themes: list[LLMTheme] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _bare(cls, data: Any) -> Any:
        return _wrap_list("themes", data)


class LLMGroup(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=400)
    theme_ids: list[str] = Field(min_length=1)


class MergeOutput(BaseModel):
    groups: list[LLMGroup] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _bare(cls, data: Any) -> Any:
        return _wrap_list("groups", data)


# --- Helpers -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ClusterConfig:
    batch_size: int = 40
    max_retries: int = 2


@dataclass
class _Group:
    label: str
    description: str
    ids: list[str]


def _clean_id(raw: str) -> str:
    """Accept `[I-01-P01]`, `"I-01-P01"` etc. as `I-01-P01`."""
    return raw.strip().strip("[]\"' ")


def _theme_key(raw: str) -> str:
    """Accept `T3`, `[T3]`, `T03` or `3` as the theme key `T3`."""
    digits = _clean_id(raw).upper().removeprefix("T")
    return f"T{int(digits)}" if digits.isdigit() else _clean_id(raw)


def render_pain_points(points: list[PainPoint]) -> str:
    lines = []
    for p in points:
        quote = " ".join(p.evidence.quote.split())
        if len(quote) > 220:
            quote = quote[:217] + "..."
        lines.append(f'[{p.id}] {p.summary} | "{quote}"')
    return "\n".join(lines)


def build_themes(
    groups: list[_Group],
    pain_points: list[PainPoint],
    interview_count: int,
    *,
    method: str,
    dropped: list[str] | None = None,
    notes: list[str] | None = None,
) -> ClusteringResult:
    """Turn raw groups into ranked `Theme`s with code-computed frequencies."""
    by_id = {p.id: p for p in pain_points}
    themes: list[Theme] = []
    for g in groups:
        members = [by_id[i] for i in g.ids]
        interviews = sorted({p.interview_id for p in members})
        themes.append(
            Theme(
                id="",
                label=g.label.strip(),
                description=g.description.strip(),
                pain_point_ids=list(g.ids),
                interview_ids=interviews,
                frequency=len(interviews),
                share=round(len(interviews) / max(interview_count, 1), 4),
                top_intensity=max((p.intensity for p in members), key=_INTENSITY_RANK.__getitem__),
                paraphrase_only=all(p.evidence.paraphrase for p in members),
            )
        )
    themes.sort(
        key=lambda t: (
            -t.frequency,
            -_INTENSITY_RANK[t.top_intensity],
            -len(t.pain_point_ids),
            t.label,
        )
    )
    for i, t in enumerate(themes, start=1):
        t.id = f"T{i:02d}"
    claimed = {i for g in groups for i in g.ids}
    return ClusteringResult(
        themes=themes,
        unclustered=[p.id for p in pain_points if p.id not in claimed],
        method=method,  # type: ignore[arg-type]
        dropped_ids=dropped or [],
        notes=notes or [],
    )


# --- Fallback --------------------------------------------------------------------------

_STOP_WORDS = (
    "a an the and or but to of in on for with at by from is are was were be been it its this that "
    "i me my we our you your they them their he she his her not no too very so as about into "
    "than then there have has had do does did can could would should will just also more most "
    "get gets getting"
)
_STOP = set(_STOP_WORDS.split())
_TOKEN = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return {w.rstrip("s") for w in _TOKEN.findall(text.lower()) if w not in _STOP and len(w) > 2}


def fallback_groups(pain_points: list[PainPoint], threshold: float = 0.25) -> list[_Group]:
    """Deterministic greedy grouping by keyword overlap (Jaccard) of summaries."""
    groups: list[tuple[set[str], _Group]] = []
    ordered = sorted(pain_points, key=lambda p: -_INTENSITY_RANK[p.intensity])
    for p in ordered:
        toks = _tokens(p.summary)
        best, best_score = None, 0.0
        for g_toks, g in groups:
            union = toks | g_toks
            score = len(toks & g_toks) / len(union) if union else 0.0
            if score > best_score:
                best, best_score = (g_toks, g), score
        if best is not None and best_score >= threshold:
            best[1].ids.append(p.id)
            best[0].update(toks)
        else:
            groups.append((set(toks), _Group(p.summary, "", [p.id])))
    return [g for _, g in groups]


# --- Main entry point ----------------------------------------------------------------------


async def cluster_pain_points(
    pain_points: list[PainPoint],
    interview_count: int,
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    config: ClusterConfig | None = None,
) -> ClusteringResult:
    """Group pain points into ranked themes. Provider errors propagate."""
    config = config or ClusterConfig()
    if not pain_points:
        return ClusteringResult(themes=[], method="llm")

    cluster_prompt = load_prompt("cluster_pain_points")
    merge_prompt = load_prompt("merge_themes")
    batches = [
        pain_points[i : i + config.batch_size]
        for i in range(0, len(pain_points), config.batch_size)
    ]
    groups: list[_Group] = []
    dropped: list[str] = []
    try:
        for n, batch in enumerate(batches, start=1):
            valid = {p.id for p in batch}
            out = await generate_structured(
                provider,
                cluster_prompt.render(count=len(batch), pain_points=render_pain_points(batch)),
                ClusterOutput,
                options=options,
                tracker=tracker,
                purpose=f"{cluster_prompt.id}:batch{n}",
                max_retries=config.max_retries,
            )
            used: set[str] = set()
            for theme in out.themes:
                ids = []
                for raw in theme.pain_point_ids:
                    pid = _clean_id(raw)
                    if pid in valid and pid not in used:
                        used.add(pid)
                        ids.append(pid)
                    else:
                        dropped.append(raw)
                if ids:
                    groups.append(_Group(theme.label, theme.description, ids))

        if len(batches) > 1 and len(groups) > 1:
            groups = await _merge(groups, provider, merge_prompt, options, tracker, config, dropped)
    except StructuredOutputError as exc:
        logger.warning("clustering fell back to keyword overlap: %s", exc)
        return build_themes(
            fallback_groups(pain_points),
            pain_points,
            interview_count,
            method="fallback",
            notes=[
                "The model could not produce valid themes, so pain points were grouped by "
                "keyword overlap instead. Review theme labels carefully."
            ],
        )
    return build_themes(groups, pain_points, interview_count, method="llm", dropped=dropped)


async def _merge(
    groups: list[_Group],
    provider: LLMProvider,
    prompt: Any,
    options: GenerationOptions | None,
    tracker: UsageTracker | None,
    config: ClusterConfig,
    dropped: list[str],
) -> list[_Group]:
    keyed = {f"T{i}": g for i, g in enumerate(groups, start=1)}
    listing = "\n".join(
        f"[{k}] {g.label}: {g.description} ({len(g.ids)} pain points)" for k, g in keyed.items()
    )
    out = await generate_structured(
        provider,
        prompt.render(themes=listing),
        MergeOutput,
        options=options,
        tracker=tracker,
        purpose=f"{prompt.id}:reduce",
        max_retries=config.max_retries,
    )
    merged: list[_Group] = []
    used: set[str] = set()
    for grp in out.groups:
        ids: list[str] = []
        for raw in grp.theme_ids:
            key = _theme_key(raw)
            if key in keyed and key not in used:
                used.add(key)
                ids.extend(keyed[key].ids)
            else:
                dropped.append(raw)
        if ids:
            merged.append(_Group(grp.label, grp.description, ids))
    # Themes the model forgot to mention survive unchanged.
    merged += [g for k, g in keyed.items() if k not in used]
    return merged
