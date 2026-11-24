"""Analysis outputs: pain themes and hypothesis verdicts.

Division of labour, by design:
- The LLM proposes theme groupings and, per interview, a stance on each
  hypothesis with verbatim quotes.
- Code verifies every quote, computes theme frequencies (distinct
  interviewees), and turns per-interview stances into a verdict with
  transparent, testable rules (`app.services.verdicts`).

Every verdict starts as an AI suggestion; the founder's review (Stage 5) is
what makes it a decision.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.evidence import Evidence, Intensity, PainPoint, RejectedQuote, VerificationStats
from app.models.hypothesis import Hypothesis

# --- Themes -------------------------------------------------------------------------


class Theme(BaseModel):
    id: str
    label: str
    description: str = ""
    pain_point_ids: list[str]
    interview_ids: list[str] = Field(description="Distinct interviews with this pain")
    frequency: int = Field(ge=0, description="How many distinct interviewees mentioned it")
    share: float = Field(ge=0.0, le=1.0, description="frequency / interviews in the corpus")
    top_intensity: Intensity = "medium"
    paraphrase_only: bool = Field(
        default=False, description="All evidence comes from founder notes, none verbatim"
    )


class ClusteringResult(BaseModel):
    themes: list[Theme]
    unclustered: list[str] = Field(
        default_factory=list, description="Pain point IDs no theme claimed"
    )
    method: Literal["llm", "fallback"] = "llm"
    dropped_ids: list[str] = Field(
        default_factory=list, description="IDs the model invented or repeated (ignored)"
    )
    notes: list[str] = Field(default_factory=list)


# --- Hypothesis verdicts -----------------------------------------------------------------


class Stance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MIXED = "mixed"
    NOT_DISCUSSED = "not_discussed"


class VerdictLabel(StrEnum):
    VALIDATED = "VALIDATED"
    INVALIDATED = "INVALIDATED"
    MIXED = "MIXED"
    UNTESTED = "UNTESTED"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InterviewAssessment(BaseModel):
    """One interview's stance on one hypothesis, backed by verified quotes only."""

    interview_id: str
    hypothesis_id: str
    stance: Stance
    rationale: str = ""
    supporting: list[Evidence] = Field(default_factory=list)
    contradicting: list[Evidence] = Field(default_factory=list)
    downgraded_from: Stance | None = Field(
        default=None,
        description="Stance the model claimed before unverified quotes were removed",
    )


class StanceCounts(BaseModel):
    supports: int = 0
    contradicts: int = 0
    mixed: int = 0
    not_discussed: int = 0

    @property
    def discussed(self) -> int:
        return self.supports + self.contradicts + self.mixed

    @property
    def total(self) -> int:
        return self.discussed + self.not_discussed

    @property
    def support_ratio(self) -> float:
        """Share of discussing interviews in favour; a mixed interview counts half."""
        if not self.discussed:
            return 0.0
        return (self.supports + 0.5 * self.mixed) / self.discussed


class HypothesisVerdict(BaseModel):
    hypothesis: Hypothesis
    verdict: VerdictLabel
    confidence: Confidence
    confidence_note: str
    what_would_change: str
    rule: str = Field(description="The decision rule that produced this verdict")
    counts: StanceCounts
    provisional: bool = Field(description="True when the corpus is below the interview minimum")
    supporting: list[Evidence] = Field(default_factory=list)
    contradicting: list[Evidence] = Field(default_factory=list)
    assessments: list[InterviewAssessment] = Field(default_factory=list)
    related_theme_ids: list[str] = Field(default_factory=list)
    status: Literal["ai_suggestion"] = "ai_suggestion"

    @property
    def counter_evidence(self) -> list[Evidence]:
        """Devil's advocate view: the strongest evidence against this hypothesis.

        Verbatim quotes before founder-note paraphrases, and contradicting quotes
        from interviews that clearly disagree before those from mixed ones.
        """
        clear = {a.interview_id for a in self.assessments if a.stance is Stance.CONTRADICTS}
        return sorted(
            self.contradicting,
            key=lambda e: (e.paraphrase, e.interview_id not in clear, e.interview_id, e.start),
        )


# --- Whole run --------------------------------------------------------------------------


class AnalysisResult(BaseModel):
    run_id: str
    interview_count: int
    warnings: list[str] = Field(default_factory=list)
    pain_points: list[PainPoint]
    rejected_quotes: list[RejectedQuote]
    quote_stats: VerificationStats
    clustering: ClusteringResult
    verdicts: list[HypothesisVerdict]
    failures: list[str] = Field(default_factory=list)
    prompt_ids: list[str] = Field(default_factory=list)
