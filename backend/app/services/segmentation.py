"""Split a transcript into speaker turns and numbered, citable segments.

Supported layouts (mixed freely, as founders paste whatever they have):

    Interviewer: How do you get paid?          plain labels
    **Maya:** Mostly bank transfer.            markdown bold labels
    [00:03:12] Maya: It takes weeks.           timestamp before the label
    Maya (00:03:12): It takes weeks.           timestamp after the label
    Q: ... / A: ...                            Q&A style

A label only counts as a speaker if it is a known role word (Interviewer, Q,
Participant, ...) or appears on at least two lines; that keeps lines such as
"Budget: about 50 EUR" inside a turn from being read as a new speaker.

Text without any speaker labels is treated as founder notes: each bullet or
paragraph becomes a segment with role NOTE, flagged as paraphrase.

An optional `---` front-matter block at the top carries metadata
(`id`, `participant`, `interviewer`, `date`, `persona`, ...).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePath

from app.models.transcript import Segment, SpeakerInfo, SpeakerRole, Transcript
from app.services.documents import normalize_text

DEFAULT_MAX_SEGMENT_CHARS = 400

_TS = r"[\[(]?\d{1,2}:\d{2}(?::\d{2})?[\])]?"
_SPEAKER_LINE = re.compile(
    rf"""^[ \t]*
    (?:{_TS}[ \t]*[-–]?[ \t]*)?          # [00:01:02] -
    (?:\*\*|__)?
    (?P<label>[^\W\d_][\w.'’\- ]{{0,38}}?)  # speaker label
    (?:[ \t]*{_TS})?                           # Maya (00:01)
    [ \t]*(?:\*\*|__)?[ \t]*:(?:\*\*|__)?      # the colon, optionally bolded
    (?:[ \t]+|$)
    (?P<body>.*)$""",
    re.VERBOSE,
)
_HEADING = re.compile(r"^[ \t]*(#{1,6}[ \t]|(-{3,}|\*{3,}|_{3,})[ \t]*$)")
_BULLET = re.compile(r"^[ \t]*(?:[-*•]|\d{1,3}[.)])[ \t]+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"'”’)]?\s+")
_SLUG = re.compile(r"[^a-z0-9]+")

INTERVIEWER_LABELS = {
    "interviewer", "founder", "me", "q", "question", "host", "moderator",
    "researcher", "int", "us", "we",
}  # fmt: skip
INTERVIEWEE_LABELS = {
    "a", "answer", "participant", "interviewee", "customer", "respondent",
    "user", "client", "guest",
}  # fmt: skip
_PARTICIPANT_LABEL = re.compile(r"^(participant|p|interviewee|customer|respondent)[ \t]*\d+$")
_NOTES_SPEAKER = "Notes"


@dataclass
class _Turn:
    speaker: str
    start: int
    end: int


def _key(label: str) -> str:
    return " ".join(label.casefold().split())


# --- Front matter -----------------------------------------------------------------


def _parse_front_matter(text: str) -> tuple[dict[str, str], int]:
    """Return (metadata, offset where the body starts)."""
    if not text.startswith("---\n"):
        return {}, 0
    close = re.search(r"^---[ \t]*$", text[4:], re.MULTILINE)
    if close is None:
        return {}, 0
    block = text[4 : 4 + close.start()]
    meta: dict[str, str] = {}
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            meta[_key(key).replace(" ", "_")] = value.strip().strip("\"'")
    return meta, 4 + close.end()


def _lines(text: str, start: int) -> list[tuple[int, str]]:
    """(offset, line) pairs for `text[start:]`, offsets relative to `text`."""
    out: list[tuple[int, str]] = []
    pos = start
    for line in text[start:].split("\n"):
        out.append((pos, line))
        pos += len(line) + 1
    return out


# --- Turn detection ---------------------------------------------------------------


def _speaker_match(line: str) -> re.Match[str] | None:
    if _HEADING.match(line) or _BULLET.match(line):
        return None
    m = _SPEAKER_LINE.match(line)
    if m is None or len(m.group("label").split()) > 4:
        return None
    return m


def _accepted_labels(lines: list[tuple[int, str]]) -> set[str]:
    """Decide which `Label:` prefixes are real speakers.

    Accepted: role words, labels used on 2+ lines, and a one-off label that
    directly answers a question asked by another accepted speaker (a customer
    who speaks once). A one-off "Budget: 50 EUR" line mid-answer is not.
    """
    matches = [(ln, m) for _, ln in lines if (m := _speaker_match(ln))]
    counts = Counter(_key(m.group("label")) for _, m in matches)
    accepted = {
        k
        for k, n in counts.items()
        if n >= 2 or k in INTERVIEWER_LABELS or k in INTERVIEWEE_LABELS
        or _PARTICIPANT_LABEL.match(k)
    }  # fmt: skip

    prev_key: str | None = None
    prev_text = ""
    for _, ln in lines:
        m = _speaker_match(ln)
        key = _key(m.group("label")) if m else None
        if m and key not in accepted and prev_key and prev_key != key and prev_text.endswith("?"):
            accepted.add(key)  # type: ignore[arg-type]
        if m and key in accepted:
            prev_key, prev_text = key, m.group("body").strip()
        elif ln.strip() and prev_key:
            prev_text = ln.strip()  # continuation line of the current turn
    return accepted


def _dialogue_turns(lines: list[tuple[int, str]], accepted: set[str]) -> tuple[list[_Turn], int]:
    """Group lines into speaker turns. Returns (turns, chars of unattributed preamble)."""
    turns: list[_Turn] = []
    current: _Turn | None = None
    preamble_chars = 0
    for offset, line in lines:
        if not line.strip() or _HEADING.match(line):
            continue
        m = _speaker_match(line)
        if m and _key(m.group("label")) in accepted:
            body = m.group("body")
            body_start = offset + m.start("body")
            current = _Turn(speaker=m.group("label").strip(), start=-1, end=-1)
            turns.append(current)
            if body.strip():
                current.start = body_start + (len(body) - len(body.lstrip()))
                current.end = offset + len(line)
            continue
        if current is None:
            preamble_chars += len(line.strip())
            continue
        if current.start < 0:
            current.start = offset + (len(line) - len(line.lstrip()))
        current.end = offset + len(line)
    return [t for t in turns if t.start >= 0], preamble_chars


def _notes_turns(lines: list[tuple[int, str]], speaker: str) -> list[_Turn]:
    """Each bullet line, or each paragraph of plain lines, becomes one turn."""
    turns: list[_Turn] = []
    para: _Turn | None = None
    for offset, line in lines:
        if not line.strip() or _HEADING.match(line):
            para = None
            continue
        bullet = _BULLET.match(line)
        if bullet:
            turns.append(_Turn(speaker, offset + bullet.end(), offset + len(line)))
            para = None
        elif para is None:
            para = _Turn(speaker, offset + (len(line) - len(line.lstrip())), offset + len(line))
            turns.append(para)
        else:
            para.end = offset + len(line)
    return turns


# --- Roles ------------------------------------------------------------------------


def _assign_roles(
    turns: list[_Turn], text: str, meta: dict[str, str]
) -> tuple[dict[str, SpeakerRole], list[str]]:
    speakers = list(dict.fromkeys(t.speaker for t in turns))
    keys = {s: _key(s) for s in speakers}
    warnings: list[str] = []

    interviewer_names = {_key(meta["interviewer"])} if meta.get("interviewer") else set()
    interviewers = {
        s for s in speakers if keys[s] in INTERVIEWER_LABELS or keys[s] in interviewer_names
    }

    if not interviewers and len(speakers) >= 2:
        # Heuristic: the interviewer is whoever mostly asks questions.
        ratios = {}
        for s in speakers:
            own = [t for t in turns if t.speaker == s]
            questions = sum(1 for t in own if text[t.start : t.end].rstrip().endswith("?"))
            ratios[s] = questions / len(own)
        best = max(ratios, key=lambda s: ratios[s])
        if ratios[best] >= 0.3:
            interviewers = {best}
            warnings.append(
                f"Interviewer guessed as '{best}' (asks most of the questions). "
                "Label them 'Interviewer:' to be sure."
            )
        else:
            warnings.append(
                "Could not tell who the interviewer is; every speaker is treated as a customer. "
                "Label the interviewer's lines with 'Interviewer:'."
            )

    roles = {
        s: SpeakerRole.INTERVIEWER if s in interviewers else SpeakerRole.INTERVIEWEE
        for s in speakers
    }
    if speakers and all(r is SpeakerRole.INTERVIEWER for r in roles.values()):
        warnings.append("Only interviewer lines were found; there is no customer speech to cite.")
    return roles, warnings


# --- Segmenting -------------------------------------------------------------------


def _split_span(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Split [start, end) at sentence boundaries into pieces of at most `max_chars`.

    A single sentence longer than `max_chars` is kept whole: segments never cut
    through a sentence, so verbatim quotes stay inside one segment.
    """
    if end - start <= max_chars:
        return [(start, end)]
    sentences: list[tuple[int, int]] = []
    pos = start
    for m in _SENTENCE_END.finditer(text, start, end):
        sentences.append((pos, m.start() + len(m.group(0).rstrip())))
        pos = m.end()
    if pos < end:
        sentences.append((pos, end))

    pieces: list[tuple[int, int]] = []
    for s_start, s_end in sentences:
        if pieces and s_end - pieces[-1][0] <= max_chars:
            pieces[-1] = (pieces[-1][0], s_end)
        else:
            pieces.append((s_start, s_end))
    return pieces


def _slug(value: str) -> str:
    return _SLUG.sub("-", value.casefold()).strip("-")


def segment_transcript(
    raw_text: str,
    *,
    transcript_id: str | None = None,
    source_filename: str | None = None,
    max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
) -> Transcript:
    """Parse text into a `Transcript` with speaker roles and numbered segments.

    The ID comes from, in order: the `transcript_id` argument, the `id` field of
    the front matter, the file name, or "interview".
    """
    text = normalize_text(raw_text)
    meta, body_start = _parse_front_matter(text)
    lines = _lines(text, body_start)
    accepted = _accepted_labels(lines)
    warnings: list[str] = []

    if accepted:
        fmt = "dialogue"
        turns, preamble = _dialogue_turns(lines, accepted)
        roles, role_warnings = _assign_roles(turns, text, meta)
        warnings += role_warnings
        if preamble > 200:
            warnings.append(f"{preamble} characters before the first speaker label were ignored.")
    else:
        fmt = "notes"
        speaker = meta.get("participant") or _NOTES_SPEAKER
        turns = _notes_turns(lines, speaker)
        roles = {speaker: SpeakerRole.NOTE}
        if turns:
            warnings.append(
                "No speaker labels found, so this is treated as interview notes. "
                "Quotes from notes are the founder's paraphrase, not verbatim customer speech."
            )

    segments: list[Segment] = []
    for turn_no, turn in enumerate(turns, start=1):
        for start, end in _split_span(text, turn.start, turn.end, max_segment_chars):
            segments.append(
                Segment(
                    number=len(segments) + 1,
                    turn=turn_no,
                    speaker=turn.speaker,
                    role=roles[turn.speaker],
                    text=text[start:end],
                    start=start,
                    end=end,
                )
            )

    speakers = [
        SpeakerInfo(
            label=label,
            role=role,
            segments=sum(1 for s in segments if s.speaker == label),
            chars=sum(len(s.text) for s in segments if s.speaker == label),
        )
        for label, role in roles.items()
    ]
    customers = [sp for sp in speakers if sp.role is not SpeakerRole.INTERVIEWER]
    main = max(customers, key=lambda sp: sp.chars, default=None)
    participant = meta.get("participant") or (main.label if main else None)

    if not segments:
        warnings.append("No usable text was found in this transcript.")
    elif sum(sp.chars for sp in customers) < 200:
        warnings.append(
            "Very little customer speech (under 200 characters); evidence will be thin."
        )

    stem = PurePath(source_filename).stem if source_filename else ""
    tid = transcript_id or meta.get("id") or _slug(stem) or "interview"
    title = meta.get("title") or (f"Interview with {participant}" if participant else tid)

    return Transcript(
        id=tid,
        title=title,
        source_filename=source_filename,
        format=fmt,
        text=text,
        metadata=meta,
        participant=participant,
        speakers=speakers,
        segments=segments,
        warnings=warnings,
    )


def chunk_segments(segments: list[Segment], max_chars: int = 6000) -> list[list[Segment]]:
    """Group consecutive segments into chunks that fit a prompt budget.

    Used for map-reduce over long transcripts: each chunk is analysed on its
    own, then results are merged. Segments are never split across chunks.
    """
    chunks: list[list[Segment]] = []
    size = 0
    for seg in segments:
        if chunks and size + len(seg.text) <= max_chars:
            chunks[-1].append(seg)
            size += len(seg.text)
        else:
            chunks.append([seg])
            size = len(seg.text)
    return chunks
