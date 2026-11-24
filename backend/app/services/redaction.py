"""Optional redaction of speaker names before a transcript is stored.

When the founder ticks "replace names" on upload, every speaker name and the
`participant`/`interviewer` front-matter names are replaced with neutral labels
("Participant", "Participant 2", "Interviewer") everywhere in the transcript,
including where a name is mentioned inside an answer. The transcript is then
segmented again, so quote offsets stay exact.

Limits (also shown to the user): only names that appear as speaker labels or in
the front matter are known. Other people mentioned in the text (a colleague, a
client company) are not detected; read the transcript before sharing it.
Nothing is sent to a model, so redaction happens before any analysis.
"""

from __future__ import annotations

import re
from pathlib import PurePath

from app.models.transcript import SpeakerRole, Transcript
from app.services.segmentation import (
    INTERVIEWEE_LABELS,
    INTERVIEWER_LABELS,
    segment_transcript,
)

_GENERIC = re.compile(r"^(participant|p|interviewee|customer|respondent)[ \t]*\d*$", re.IGNORECASE)
_SKIP = INTERVIEWER_LABELS | INTERVIEWEE_LABELS | {"notes", "note"}

REDACTION_WARNING = (
    "Speaker names were replaced ({names}). Other names mentioned in the text, "
    "such as colleagues or companies, are not detected: check before sharing."
)


def _is_name(label: str) -> bool:
    key = label.strip().casefold()
    return bool(key) and key not in _SKIP and not _GENERIC.match(key)


def pseudonyms(t: Transcript) -> dict[str, str]:
    """Map each known name to its neutral replacement."""
    mapping: dict[str, str] = {}
    customers = [
        s.label for s in t.speakers if s.role is not SpeakerRole.INTERVIEWER and _is_name(s.label)
    ]
    interviewers = [
        s.label for s in t.speakers if s.role is SpeakerRole.INTERVIEWER and _is_name(s.label)
    ]
    for label in interviewers:
        mapping[label] = (
            "Interviewer" if len(interviewers) == 1 else f"Interviewer {len(mapping) + 1}"
        )
    for i, label in enumerate(customers, start=1):
        mapping[label] = "Participant" if len(customers) == 1 else f"Participant {i}"

    for key, default in (("participant", "Participant"), ("interviewer", "Interviewer")):
        name = t.metadata.get(key, "").strip()
        if name and _is_name(name) and name not in mapping:
            mapping[name] = (
                mapping.get(t.participant or "", default) if key == "participant" else default
            )

    # "Maya Lopez" is often called "Maya" in the conversation.
    for name, alias in list(mapping.items()):
        first = name.split()[0]
        if first != name and _is_name(first) and len(first) > 2:
            mapping.setdefault(first, alias)
    return mapping


def _replace(text: str, mapping: dict[str, str], *, ignore_case: bool = False) -> str:
    for name in sorted(mapping, key=len, reverse=True):
        flags = re.IGNORECASE if ignore_case else 0
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", mapping[name], text, flags=flags)
    return text


def redact_names(t: Transcript) -> Transcript:
    """A copy of the transcript with speaker names replaced (unchanged if none found)."""
    mapping = pseudonyms(t)
    if not mapping:
        return t
    slug_map = {n.lower(): v.lower().replace(" ", "-") for n, v in mapping.items()}
    filename = t.source_filename
    if filename:
        path = PurePath(filename)
        filename = _replace(path.stem, slug_map, ignore_case=True) + path.suffix
    redacted = segment_transcript(
        _replace(t.text, mapping),
        transcript_id=_replace(t.id, slug_map, ignore_case=True),
        source_filename=filename,
    )
    shown = ", ".join(sorted({v for v in mapping.values()}))
    return redacted.model_copy(
        update={"warnings": [*redacted.warnings, REDACTION_WARNING.format(names=f"now {shown}")]}
    )
