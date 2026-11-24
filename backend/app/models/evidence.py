"""Evidence models: verified quotes and the pain points built on them.

An `Evidence` object only exists for a quote that was found in the transcript
by `app.services.verification`. Its `quote` is the transcript's own text (not
the model's copy), and `start`/`end` locate it in `Transcript.text`.
Quotes that fail verification become `RejectedQuote`s and are never shown as
evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.models.transcript import SpeakerRole

Intensity = Literal["low", "medium", "high"]


class MatchType(StrEnum):
    EXACT = "exact"  # identical after whitespace/quote-style normalization
    FUZZY = "fuzzy"  # similarity >= threshold (default 0.92)
    UNVERIFIED = "unverified"


class Evidence(BaseModel):
    """A verified quote with its exact location."""

    interview_id: str
    segment: int
    speaker: str
    role: SpeakerRole
    quote: str = Field(description="Verbatim transcript text")
    start: int
    end: int
    match: MatchType
    score: float = Field(ge=0.0, le=1.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def paraphrase(self) -> bool:
        """True when the source is founder notes rather than recorded speech."""
        return self.role is SpeakerRole.NOTE


class PainPoint(BaseModel):
    id: str
    interview_id: str
    summary: str
    intensity: Intensity = "medium"
    evidence: Evidence


class RejectedQuote(BaseModel):
    """A model-proposed quote that could not be verified. Kept for transparency."""

    interview_id: str
    claimed_segment: int | None
    quote: str = Field(description="What the model claimed was said")
    summary: str = ""
    reason: str
    best_score: float = 0.0


class VerificationStats(BaseModel):
    """Counts behind the "verified quotes: X/Y" metric."""

    proposed: int = 0
    exact: int = 0
    fuzzy: int = 0
    rejected: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verified(self) -> int:
        return self.exact + self.fuzzy

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rate(self) -> float:
        return self.verified / self.proposed if self.proposed else 1.0

    def label(self) -> str:
        return f"verified quotes: {self.verified}/{self.proposed}"

    def __add__(self, other: VerificationStats) -> VerificationStats:
        return VerificationStats(
            proposed=self.proposed + other.proposed,
            exact=self.exact + other.exact,
            fuzzy=self.fuzzy + other.fuzzy,
            rejected=self.rejected + other.rejected,
        )
