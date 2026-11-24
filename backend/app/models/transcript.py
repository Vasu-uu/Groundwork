"""Domain models for parsed interview transcripts.

Offsets (`start`, `end`) are character positions in `Transcript.text`, the
normalized full text. `Transcript.text[seg.start:seg.end] == seg.text` always
holds, so the UI can highlight any segment or quote in the original document.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SpeakerRole(StrEnum):
    INTERVIEWER = "interviewer"
    INTERVIEWEE = "interviewee"
    # Founder's own notes with no speaker labels: paraphrases, not verbatim speech.
    NOTE = "note"


class Segment(BaseModel):
    """A citable unit of a transcript: one speaker turn, or a slice of a long turn."""

    number: int = Field(ge=1, description="1-based, unique within the transcript")
    turn: int = Field(ge=1, description="1-based index of the speaker turn it belongs to")
    speaker: str
    role: SpeakerRole
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class SpeakerInfo(BaseModel):
    label: str
    role: SpeakerRole
    segments: int
    chars: int


class Transcript(BaseModel):
    """One interview, split into speaker turns and numbered segments."""

    id: str
    title: str
    source_filename: str | None = None
    format: Literal["dialogue", "notes"]
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)
    participant: str | None = Field(
        default=None, description="Main interviewee (label or metadata name)"
    )
    speakers: list[SpeakerInfo] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def evidence_segments(self) -> list[Segment]:
        """Segments that may be cited as customer evidence (never the interviewer)."""
        return [s for s in self.segments if s.role is not SpeakerRole.INTERVIEWER]

    def segment(self, number: int) -> Segment | None:
        if 1 <= number <= len(self.segments):
            seg = self.segments[number - 1]
            if seg.number == number:
                return seg
        return next((s for s in self.segments if s.number == number), None)
