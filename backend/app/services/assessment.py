"""Per-interview hypothesis assessment (the map step of hypothesis evaluation).

For each interview (chunked if long), the model states a stance on every
hypothesis with verbatim quotes (`assess_hypotheses.v*`). Code then:

1. verifies each quote and drops unverified or interviewer quotes;
2. recomputes the stance from what survived: a stance needs at least one
   verified quote, otherwise it is downgraded (and the original is recorded);
3. merges chunks of the same interview into one assessment per hypothesis.

Every interview gets an assessment for every hypothesis, so counts in the
verdict always add up to the number of interviews assessed.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.llm import GenerationOptions, LLMProvider, UsageTracker
from app.llm.prompts import PromptTemplate, load_prompt
from app.llm.structured import StructuredOutputError, generate_structured
from app.models.analysis import InterviewAssessment, Stance
from app.models.evidence import Evidence, MatchType, RejectedQuote, VerificationStats
from app.models.hypothesis import Hypothesis
from app.models.transcript import SpeakerRole, Transcript
from app.services.concurrency import map_bounded
from app.services.corpus import Corpus
from app.services.extraction import ExtractionConfig, render_segments
from app.services.segmentation import chunk_segments
from app.services.verification import to_evidence, verify_quote

logger = logging.getLogger("groundwork.assessment")

PROMPT_NAME = "assess_hypotheses"

_STANCE_ALIASES = {
    "support": Stance.SUPPORTS,
    "supported": Stance.SUPPORTS,
    "validates": Stance.SUPPORTS,
    "contradict": Stance.CONTRADICTS,
    "contradicted": Stance.CONTRADICTS,
    "refutes": Stance.CONTRADICTS,
    "against": Stance.CONTRADICTS,
    "neutral": Stance.NOT_DISCUSSED,
    "none": Stance.NOT_DISCUSSED,
    "n/a": Stance.NOT_DISCUSSED,
    "not discussed": Stance.NOT_DISCUSSED,
    "not_mentioned": Stance.NOT_DISCUSSED,
    "irrelevant": Stance.NOT_DISCUSSED,
    "unclear": Stance.NOT_DISCUSSED,
}


class LLMQuote(BaseModel):
    segment: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=800)


class LLMAssessment(BaseModel):
    hypothesis_id: str
    stance: Stance
    rationale: str = Field(default="", max_length=500)
    supporting: list[LLMQuote] = Field(default_factory=list)
    contradicting: list[LLMQuote] = Field(default_factory=list)

    @field_validator("stance", mode="before")
    @classmethod
    def _stance(cls, v: Any) -> Any:
        if isinstance(v, str):
            key = v.strip().lower()
            return _STANCE_ALIASES.get(key, key.replace(" ", "_"))
        return v

    @field_validator("supporting", "contradicting", mode="before")
    @classmethod
    def _none_is_empty(cls, v: Any) -> Any:
        return [] if v is None else v


class AssessOutput(BaseModel):
    assessments: list[LLMAssessment] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _bare(cls, data: Any) -> Any:
        return {"assessments": data} if isinstance(data, list) else data


class AssessmentResult(BaseModel):
    assessments: list[InterviewAssessment] = Field(default_factory=list)
    rejected: list[RejectedQuote] = Field(default_factory=list)
    stats: VerificationStats = Field(default_factory=VerificationStats)
    failures: list[str] = Field(default_factory=list)
    failed_interviews: list[str] = Field(
        default_factory=list, description="Interviews with no usable assessment at all"
    )


def render_hypotheses(hypotheses: list[Hypothesis]) -> str:
    return "\n".join(f"{h.id}: {h.text}" for h in hypotheses)


def final_stance(claimed: list[Stance], has_sup: bool, has_con: bool) -> Stance:
    """Stance supported by verified quotes. Unbacked claims fall to not_discussed."""
    if has_sup and has_con:
        return Stance.MIXED
    if Stance.MIXED in claimed and (has_sup or has_con):
        return Stance.MIXED  # lukewarm: one verified quote is enough to keep "mixed"
    if has_sup:
        return Stance.SUPPORTS
    if has_con:
        return Stance.CONTRADICTS
    return Stance.NOT_DISCUSSED


class _Acc:
    """Accumulates one interview's evidence for one hypothesis across chunks."""

    def __init__(self) -> None:
        self.claimed: list[Stance] = []
        self.rationales: list[str] = []
        self.supporting: list[Evidence] = []
        self.contradicting: list[Evidence] = []
        self.spans: set[tuple[str, int, int]] = set()

    def add(self, side: str, ev: Evidence) -> None:
        key = (side, ev.start, ev.end)
        if key not in self.spans:
            self.spans.add(key)
            (self.supporting if side == "supporting" else self.contradicting).append(ev)


async def assess_interview(
    transcript: Transcript,
    hypotheses: list[Hypothesis],
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    config: ExtractionConfig | None = None,
    prompt: PromptTemplate | None = None,
) -> AssessmentResult:
    config = config or ExtractionConfig()
    prompt = prompt or load_prompt(PROMPT_NAME)
    result = AssessmentResult()
    acc = {h.id: _Acc() for h in hypotheses}
    ids = {h.id.casefold(): h.id for h in hypotheses}

    chunks = [
        c
        for c in chunk_segments(transcript.segments, config.chunk_chars)
        if any(s.role is not SpeakerRole.INTERVIEWER for s in c)
    ]
    ok_chunks = 0
    for chunk in chunks:
        label = f"S{chunk[0].number}-S{chunk[-1].number}"
        try:
            out = await generate_structured(
                provider,
                prompt.render(
                    hypotheses=render_hypotheses(hypotheses),
                    interview_id=transcript.id,
                    participant=transcript.participant or "unknown",
                    first_segment=chunk[0].number,
                    last_segment=chunk[-1].number,
                    segments=render_segments(chunk),
                ),
                AssessOutput,
                options=options,
                tracker=tracker,
                purpose=f"{prompt.id}:{transcript.id}:{label}",
                max_retries=config.max_retries,
            )
        except StructuredOutputError as exc:
            logger.warning("assessment failed for %s %s: %s", transcript.id, label, exc)
            result.failures.append(f"{transcript.id} {label}: {exc}")
            continue
        ok_chunks += 1
        for a in out.assessments:
            hid = ids.get(a.hypothesis_id.strip().casefold())
            if hid is None:
                continue  # unknown hypothesis ID: ignore
            target = acc[hid]
            target.claimed.append(a.stance)
            if a.rationale.strip() and a.stance is not Stance.NOT_DISCUSSED:
                target.rationales.append(a.rationale.strip())
            for side, quotes in (("supporting", a.supporting), ("contradicting", a.contradicting)):
                for q in quotes:
                    result.stats.proposed += 1
                    match = verify_quote(
                        transcript, q.quote, claimed_segment=q.segment, threshold=config.threshold
                    )
                    reason = match.reason
                    if match.status is not MatchType.UNVERIFIED:
                        seg = transcript.segment(match.segment or 0)
                        if seg is not None and seg.role is SpeakerRole.INTERVIEWER:
                            reason = "quote is the interviewer's words, not the customer's"
                    if reason:
                        result.stats.rejected += 1
                        result.rejected.append(
                            RejectedQuote(
                                interview_id=transcript.id,
                                claimed_segment=q.segment,
                                quote=q.quote,
                                summary=f"{hid} {side}",
                                reason=reason,
                                best_score=match.score,
                            )
                        )
                        continue
                    if match.status is MatchType.EXACT:
                        result.stats.exact += 1
                    else:
                        result.stats.fuzzy += 1
                    target.add(side, to_evidence(transcript, match))

    if chunks and ok_chunks == 0:
        result.failed_interviews.append(transcript.id)
        return result  # no assessment at all: excluded from counts, reported as failure

    for h in hypotheses:
        a = acc[h.id]
        stance = final_stance(a.claimed, bool(a.supporting), bool(a.contradicting))
        strongest_claim = next(
            (s for s in (Stance.MIXED, Stance.SUPPORTS, Stance.CONTRADICTS) if s in a.claimed),
            None,
        )
        result.assessments.append(
            InterviewAssessment(
                interview_id=transcript.id,
                hypothesis_id=h.id,
                stance=stance,
                rationale=" ".join(a.rationales) if stance is not Stance.NOT_DISCUSSED else "",
                supporting=a.supporting,
                contradicting=a.contradicting,
                downgraded_from=(
                    strongest_claim
                    if strongest_claim is not None and strongest_claim is not stance
                    else None
                ),
            )
        )
    return result


async def assess_corpus(
    corpus: Corpus,
    hypotheses: list[Hypothesis],
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    config: ExtractionConfig | None = None,
) -> AssessmentResult:
    """Assess every hypothesis in every interview. Provider errors propagate."""
    config = config or ExtractionConfig()
    prompt = load_prompt(PROMPT_NAME)

    async def one(t: Transcript) -> AssessmentResult:
        return await assess_interview(
            t, hypotheses, provider, options=options, tracker=tracker, config=config, prompt=prompt
        )

    total = AssessmentResult()
    for r in await map_bounded(one, corpus.transcripts, config.concurrency):
        total.assessments += r.assessments
        total.rejected += r.rejected
        total.stats = total.stats + r.stats
        total.failures += r.failures
        total.failed_interviews += r.failed_interviews
    return total
