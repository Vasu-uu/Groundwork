"""Assemble parsed transcripts into a corpus and flag sample-size problems.

A corpus is the set of interviews one analysis runs on. This is where the
"too few interviews to draw conclusions" rule lives, so the API, the demo mode
and the eval harness all apply it the same way.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.transcript import SpeakerRole, Transcript
from app.services.documents import extract_text
from app.services.segmentation import segment_transcript

#: Below this many interviews the UI warns that conclusions are provisional.
MIN_INTERVIEWS_FOR_CONCLUSIONS = 5


class Corpus(BaseModel):
    transcripts: list[Transcript]
    warnings: list[str] = Field(default_factory=list)

    @property
    def interview_count(self) -> int:
        return len(self.transcripts)

    @property
    def small_sample(self) -> bool:
        return self.interview_count < MIN_INTERVIEWS_FOR_CONCLUSIONS

    def get(self, transcript_id: str) -> Transcript | None:
        return next((t for t in self.transcripts if t.id == transcript_id), None)


def parse_upload(filename: str, data: bytes) -> Transcript:
    """Extract text from an uploaded file and segment it.

    Raises `app.services.documents.DocumentError` for unusable files.
    """
    return segment_transcript(extract_text(filename, data), source_filename=filename)


def build_corpus(transcripts: list[Transcript]) -> Corpus:
    """Give every transcript a unique ID and collect corpus-level warnings."""
    seen: dict[str, int] = {}
    unique: list[Transcript] = []
    for t in transcripts:
        n = seen.get(t.id, 0) + 1
        seen[t.id] = n
        unique.append(t if n == 1 else t.model_copy(update={"id": f"{t.id}-{n}"}))

    warnings: list[str] = []
    usable = [t for t in unique if t.evidence_segments]
    if not usable:
        warnings.append("No interview contains customer speech; there is nothing to analyse.")
    elif len(usable) < MIN_INTERVIEWS_FOR_CONCLUSIONS:
        warnings.append(
            f"Only {len(usable)} usable interview(s). Treat every finding as provisional: "
            f"aim for at least {MIN_INTERVIEWS_FOR_CONCLUSIONS} before drawing conclusions."
        )
    renamed = [
        f"{a.id} -> {b.id}" for a, b in zip(transcripts, unique, strict=True) if a.id != b.id
    ]
    if renamed:
        warnings.append(f"Duplicate interview IDs were renamed: {', '.join(renamed)}.")
    notes = [t.id for t in unique if any(s.role is SpeakerRole.NOTE for s in t.segments)]
    if notes:
        warnings.append(
            f"{len(notes)} interview(s) are founder notes, not transcripts ({', '.join(notes)}). "
            "Their quotes are paraphrases and carry less weight."
        )
    return Corpus(transcripts=unique, warnings=warnings)
