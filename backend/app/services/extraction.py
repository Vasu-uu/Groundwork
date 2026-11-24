"""Pain-point extraction: transcript chunks -> LLM -> verified pain points.

Map step of the analysis. For each interview, each chunk of segments is sent
to the model with `prompts/extract_pain_points.v*.md`. Every proposed quote is
then checked by `verify_quote`:

- verified and spoken by a customer (or in founder notes) -> `PainPoint`
- not found, too short, or spoken by the interviewer       -> `RejectedQuote`

Extraction is deliberately hypothesis-blind: the model never sees the
founder's hypotheses here, so it cannot go looking for confirming quotes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import Settings
from app.llm import GenerationOptions, LLMProvider, UsageTracker
from app.llm.prompts import PromptTemplate, load_prompt
from app.llm.structured import StructuredOutputError, generate_structured
from app.models.evidence import (
    Intensity,
    MatchType,
    PainPoint,
    RejectedQuote,
    VerificationStats,
)
from app.models.transcript import Segment, SpeakerRole, Transcript
from app.services.corpus import Corpus
from app.services.segmentation import chunk_segments
from app.services.verification import DEFAULT_THRESHOLD, to_evidence, verify_quote

logger = logging.getLogger("groundwork.extraction")

PROMPT_NAME = "extract_pain_points"

_ROLE_TAG = {
    SpeakerRole.INTERVIEWER: "INTERVIEWER, do not quote",
    SpeakerRole.INTERVIEWEE: "CUSTOMER",
    SpeakerRole.NOTE: "FOUNDER NOTE",
}


# --- What the model must return -------------------------------------------------


class ExtractedPainPoint(BaseModel):
    segment: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=800)
    summary: str = Field(min_length=1, max_length=300)
    intensity: Intensity = "medium"

    @field_validator("intensity", mode="before")
    @classmethod
    def _lower(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class ExtractionOutput(BaseModel):
    pain_points: list[ExtractedPainPoint] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_list(cls, data: Any) -> Any:
        """Small models sometimes return the list without the wrapping object."""
        return {"pain_points": data} if isinstance(data, list) else data


# --- Results ---------------------------------------------------------------------


class InterviewFailure(BaseModel):
    interview_id: str
    segments: str  # e.g. "S1-S24"
    error: str


class ExtractionResult(BaseModel):
    pain_points: list[PainPoint] = Field(default_factory=list)
    rejected: list[RejectedQuote] = Field(default_factory=list)
    failures: list[InterviewFailure] = Field(default_factory=list)
    stats: VerificationStats = Field(default_factory=VerificationStats)
    prompt_id: str = ""

    def merge(self, other: ExtractionResult) -> ExtractionResult:
        return ExtractionResult(
            pain_points=self.pain_points + other.pain_points,
            rejected=self.rejected + other.rejected,
            failures=self.failures + other.failures,
            stats=self.stats + other.stats,
            prompt_id=self.prompt_id or other.prompt_id,
        )


@dataclass(frozen=True)
class ExtractionConfig:
    threshold: float = DEFAULT_THRESHOLD
    chunk_chars: int = 6000
    max_retries: int = 2
    concurrency: int = 1

    @classmethod
    def from_settings(cls, s: Settings) -> ExtractionConfig:
        return cls(
            threshold=s.quote_match_threshold,
            chunk_chars=s.extraction_chunk_chars,
            max_retries=s.llm_max_retries,
            concurrency=s.llm_concurrency,
        )


# --- Implementation --------------------------------------------------------------


def render_segments(segments: list[Segment]) -> str:
    """Prompt view of segments: `[S4] Maya (CUSTOMER): text`."""
    return "\n".join(
        f"[S{s.number}] {s.speaker} ({_ROLE_TAG[s.role]}): {' '.join(s.text.split())}"
        for s in segments
    )


def _process_items(
    transcript: Transcript,
    items: list[ExtractedPainPoint],
    config: ExtractionConfig,
    start_index: int,
    seen_spans: set[tuple[int, int]],
) -> ExtractionResult:
    result = ExtractionResult()
    stats = VerificationStats(proposed=len(items))
    for item in items:
        match = verify_quote(
            transcript, item.quote, claimed_segment=item.segment, threshold=config.threshold
        )
        reason = match.reason
        if match.status is not MatchType.UNVERIFIED:
            seg = transcript.segment(match.segment or 0)
            if seg is not None and seg.role is SpeakerRole.INTERVIEWER:
                reason = "quote is the interviewer's words, not the customer's"
        if reason:
            stats.rejected += 1
            result.rejected.append(
                RejectedQuote(
                    interview_id=transcript.id,
                    claimed_segment=item.segment,
                    quote=item.quote,
                    summary=item.summary,
                    reason=reason,
                    best_score=match.score,
                )
            )
            continue
        if match.status is MatchType.EXACT:
            stats.exact += 1
        else:
            stats.fuzzy += 1
        span = (match.start, match.end)
        if span in seen_spans:
            continue  # same quote proposed twice: keep the first
        seen_spans.add(span)
        n = start_index + len(result.pain_points) + 1
        result.pain_points.append(
            PainPoint(
                id=f"{transcript.id}-P{n:02d}",
                interview_id=transcript.id,
                summary=item.summary.strip(),
                intensity=item.intensity,
                evidence=to_evidence(transcript, match),
            )
        )
    result.stats = stats
    return result


async def extract_interview(
    transcript: Transcript,
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    config: ExtractionConfig | None = None,
    prompt: PromptTemplate | None = None,
) -> ExtractionResult:
    """Extract verified pain points from one interview (map over its chunks).

    Invalid model output for a chunk is recorded as a failure and the other
    chunks still run. Provider errors (unreachable, misconfigured) propagate.
    """
    config = config or ExtractionConfig()
    prompt = prompt or load_prompt(PROMPT_NAME)
    result = ExtractionResult(prompt_id=prompt.id)
    if not transcript.evidence_segments:
        return result

    seen: set[tuple[int, int]] = set()
    for chunk in chunk_segments(transcript.segments, config.chunk_chars):
        if not any(s.role is not SpeakerRole.INTERVIEWER for s in chunk):
            continue
        label = f"S{chunk[0].number}-S{chunk[-1].number}"
        messages = prompt.render(
            interview_id=transcript.id,
            participant=transcript.participant or "unknown",
            first_segment=chunk[0].number,
            last_segment=chunk[-1].number,
            segments=render_segments(chunk),
        )
        try:
            output = await generate_structured(
                provider,
                messages,
                ExtractionOutput,
                options=options,
                tracker=tracker,
                purpose=f"{prompt.id}:{transcript.id}:{label}",
                max_retries=config.max_retries,
            )
        except StructuredOutputError as exc:
            logger.warning("extraction failed for %s %s: %s", transcript.id, label, exc)
            result.failures.append(
                InterviewFailure(interview_id=transcript.id, segments=label, error=str(exc))
            )
            continue
        result = result.merge(
            _process_items(transcript, output.pain_points, config, len(result.pain_points), seen)
        )
    return result


async def extract_corpus(
    corpus: Corpus,
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    config: ExtractionConfig | None = None,
) -> ExtractionResult:
    """Run extraction over every interview, `config.concurrency` at a time."""
    config = config or ExtractionConfig()
    prompt = load_prompt(PROMPT_NAME)
    gate = asyncio.Semaphore(config.concurrency)

    async def one(t: Transcript) -> ExtractionResult:
        async with gate:
            return await extract_interview(
                t, provider, options=options, tracker=tracker, config=config, prompt=prompt
            )

    # TaskGroup cancels the remaining interviews as soon as one hits a provider
    # error (e.g. Ollama went down), instead of failing them one by one.
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(t)) for t in corpus.transcripts]
    except ExceptionGroup as group_error:
        # Surface the first real error (e.g. ProviderUnavailableError) to callers.
        raise group_error.exceptions[0] from None
    total = ExtractionResult(prompt_id=prompt.id)
    for task in tasks:  # input order, so the output is deterministic
        total = total.merge(task.result())
    return total
