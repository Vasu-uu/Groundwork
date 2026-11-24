"""Request and response bodies of the studies API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.llm.usage import UsageSummary
from app.models.analysis import AnalysisResult, VerdictLabel
from app.models.evidence import Evidence
from app.models.hypothesis import Hypothesis
from app.models.transcript import SpeakerRole, Transcript
from app.services.review import CheckpointState

# --- Requests -------------------------------------------------------------------------------


class CreateStudyIn(BaseModel):
    name: str = Field(default="Untitled study", max_length=200)
    hypotheses: list[str] = Field(default_factory=list, max_length=10)


class HypothesesIn(BaseModel):
    hypotheses: list[str] = Field(max_length=10)


class PasteIn(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)
    title: str = Field(default="", max_length=120)


class ApproveIn(BaseModel):
    acknowledge_small_sample: bool = False


class ReopenIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


# --- Responses ------------------------------------------------------------------------------


class InterviewSummary(BaseModel):
    id: str
    title: str
    participant: str | None
    format: str
    source_filename: str | None
    segments: int
    customer_segments: int
    warnings: list[str]

    @classmethod
    def of(cls, t: Transcript) -> InterviewSummary:
        return cls(
            id=t.id,
            title=t.title,
            participant=t.participant,
            format=t.format,
            source_filename=t.source_filename,
            segments=len(t.segments),
            customer_segments=sum(1 for s in t.segments if s.role is not SpeakerRole.INTERVIEWER),
            warnings=t.warnings,
        )


class FileError(BaseModel):
    filename: str
    error: str


class UploadOut(BaseModel):
    added: list[InterviewSummary]
    errors: list[FileError]


def cost_label(usage: UsageSummary) -> str:
    tokens = f"{usage.total_tokens:,}".replace(",", " ")  # 12 345 tokens
    return f"{usage.cost_eur:.0f} EUR, {tokens} tokens"


class ReviewOut(BaseModel):
    hypothesis_id: str
    decision: str
    ai_verdict: VerdictLabel
    final_verdict: VerdictLabel | None
    reasoning: str
    removed_evidence: list[str]
    note: str
    reviewed_at: datetime
    recomputed_ai_verdict: VerdictLabel = Field(
        description="What the rules give once the removed quotes are left out"
    )


class StudySummaryOut(BaseModel):
    id: str
    name: str
    status: str
    sample_set: str | None
    created_at: datetime
    interviews: int
    hypotheses: int


class StudyOut(BaseModel):
    id: str
    name: str
    status: str
    progress: str | None
    error: str | None
    error_kind: str | None
    sample_set: str | None
    created_at: datetime
    updated_at: datetime
    analyzed_at: datetime | None
    approved_at: datetime | None
    hypotheses: list[Hypothesis]
    interviews: list[InterviewSummary]
    corpus_warnings: list[str]
    small_sample: bool
    result: AnalysisResult | None
    reviews: dict[str, ReviewOut]
    checkpoint: CheckpointState
    usage: UsageSummary

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_label(self) -> str:
        return cost_label(self.usage)


class StatusOut(BaseModel):
    status: str
    progress: str | None
    error: str | None
    error_kind: str | None
    usage: UsageSummary

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_label(self) -> str:
        return cost_label(self.usage)


class LogEntryOut(BaseModel):
    id: int
    at: datetime
    actor: str
    action: str
    hypothesis_id: str | None
    details: dict[str, Any]


class FinalDecisionOut(BaseModel):
    """A founder-approved decision: what downstream steps are allowed to use."""

    hypothesis_id: str
    text: str
    ai_verdict: VerdictLabel
    final_verdict: VerdictLabel | None
    decision: str
    reasoning: str
    note: str
    supporting: list[Evidence]
    contradicting: list[Evidence]
