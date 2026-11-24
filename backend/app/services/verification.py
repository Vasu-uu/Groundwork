"""Programmatic quote verification: is this quote really in the transcript?

LLMs paraphrase, merge sentences and invent quotes. Before any quote is shown
as evidence it must be located in the transcript:

1. Both texts are normalized for comparison only: case, whitespace, curly vs
   straight quotes, dash and ellipsis styles. A map back to the original
   characters is kept, so the returned span is the transcript's own text.
2. Exact match: the normalized quote occurs in a speaker turn.
3. Elided match: a quote with "..." whose parts all occur, in order, in one turn.
4. Fuzzy match: the best word-window in a turn reaches the similarity threshold
   (difflib ratio, default 0.92). This tolerates a dropped word or a typo fix,
   not a paraphrase.

Search runs over whole speaker turns (a long turn is split into several
segments), starting with the segment the model cited. The segment number in
the result is the one that actually contains the quote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models.evidence import Evidence, MatchType
from app.models.transcript import Segment, Transcript

DEFAULT_THRESHOLD = 0.92
MIN_QUOTE_WORDS = 3

_CHAR_MAP = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "′": "'", "`": "'",
        "“": '"', "”": '"', "„": '"', "″": '"',
        "–": "-", "—": "-", "‑": "-", "−": "-",
        "…": "...",
    }
)  # fmt: skip
_WORD = re.compile(r"\S+")
_EDGE_JUNK = " \t\n\"'"
# Tokens whose change flips or rescales meaning; a fuzzy match must keep them identical.
_CRITICAL = re.compile(
    r"\d+(?:[.,]\d+)*|\b(?:not|no|never|nothing|nobody|none|neither|nor|cannot)\b|n't\b"
)


def _critical_tokens(normalized: str) -> list[str]:
    """Numbers and negations; "isn't", "is not" and "cannot" all count as "not"."""
    return sorted("not" if t in ("n't", "cannot") else t for t in _CRITICAL.findall(normalized))


@dataclass(frozen=True)
class QuoteMatch:
    status: MatchType
    score: float
    start: int = -1  # offsets in Transcript.text (original characters)
    end: int = -1
    segment: int | None = None
    reason: str = ""


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalize `text` for matching; `index[i]` is the original offset of char i."""
    out: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                index.append(i)
            continue
        for c in ch.translate(_CHAR_MAP).casefold():
            out.append(c)
            index.append(i)
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def normalize(text: str) -> str:
    return normalize_with_map(text)[0]


@dataclass
class _Unit:
    """A speaker turn: contiguous text covering one or more segments."""

    segments: list[Segment]
    start: int
    norm: str
    index: list[int]

    def span(self, a: int, b: int) -> tuple[int, int]:
        """Original offsets for normalized range [a, b)."""
        return self.start + self.index[a], self.start + self.index[b - 1] + 1

    def segment_at(self, offset: int) -> Segment:
        for seg in self.segments:
            if offset < seg.end:
                return seg
        return self.segments[-1]


def _units(transcript: Transcript) -> list[_Unit]:
    turns: dict[int, list[Segment]] = {}
    for seg in transcript.segments:
        turns.setdefault(seg.turn, []).append(seg)
    units = []
    for segs in turns.values():
        start, end = segs[0].start, segs[-1].end
        norm, index = normalize_with_map(transcript.text[start:end])
        units.append(_Unit(segs, start, norm, index))
    return units


def _exact(unit: _Unit, quote: str) -> tuple[int, int] | None:
    for q in (quote, quote.rstrip(" .,;:!?")):
        if q and (i := unit.norm.find(q)) >= 0:
            return i, i + len(q)
    return None


def _elided(unit: _Unit, quote: str) -> tuple[int, int] | None:
    parts = [p.strip(" .,;:") for p in quote.split("...")]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return None
    pos, first = 0, None
    for part in parts:
        i = unit.norm.find(part, pos)
        if i < 0:
            return None
        first = i if first is None else first
        pos = i + len(part)
    assert first is not None
    return first, pos


def _fuzzy(unit: _Unit, quote: str, floor: float) -> tuple[float, int, int]:
    """Best (score, start, end) over word windows close to the quote's length."""
    words = [(m.start(), m.end()) for m in _WORD.finditer(unit.norm)]
    n = len(quote.split())
    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(quote)
    best = (0.0, -1, -1)
    for size in range(max(1, n - 2), n + 3):
        for i in range(len(words) - size + 1):
            a, b = words[i][0], words[i + size - 1][1]
            matcher.set_seq1(unit.norm[a:b])
            bar = max(best[0], floor)
            if matcher.real_quick_ratio() <= bar or matcher.quick_ratio() <= bar:
                continue
            score = matcher.ratio()
            if score > best[0]:
                best = (score, a, b)
    return best


def verify_quote(
    transcript: Transcript,
    quote: str,
    *,
    claimed_segment: int | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> QuoteMatch:
    """Locate `quote` in `transcript`. Never raises; failure is an UNVERIFIED match."""
    q = normalize(quote).strip(_EDGE_JUNK)
    if len(q.split()) < MIN_QUOTE_WORDS:
        return QuoteMatch(
            MatchType.UNVERIFIED, 0.0, reason=f"too short (fewer than {MIN_QUOTE_WORDS} words)"
        )

    units = _units(transcript)
    if claimed_segment is not None:
        # Search the cited turn first: cheaper, and the right answer when the model is accurate.
        units.sort(key=lambda u: not any(s.number == claimed_segment for s in u.segments))

    def found(unit: _Unit, a: int, b: int, status: MatchType, score: float) -> QuoteMatch:
        start, end = unit.span(a, b)
        seg = unit.segment_at(start)
        return QuoteMatch(status, round(score, 4), start, end, seg.number)

    for unit in units:
        if hit := _exact(unit, q):
            return found(unit, *hit, MatchType.EXACT, 1.0)
    for unit in units:
        if hit := _elided(unit, q):
            return found(unit, *hit, MatchType.EXACT, 1.0)

    best: tuple[float, _Unit | None, int, int] = (0.0, None, -1, -1)
    for unit in units:
        score, a, b = _fuzzy(unit, q, floor=best[0])
        if score > best[0]:
            best = (score, unit, a, b)
        if score >= 0.99:
            break
    score, unit, a, b = best
    if unit is not None and score >= threshold:
        if _critical_tokens(unit.norm[a:b]) != _critical_tokens(q):
            return QuoteMatch(
                MatchType.UNVERIFIED,
                round(score, 4),
                reason="near match changes a number or a negation, so it is not the same claim",
            )
        return found(unit, a, b, MatchType.FUZZY, score)
    return QuoteMatch(
        MatchType.UNVERIFIED,
        round(score, 4),
        reason=f"not found in transcript (best similarity {score:.2f} < {threshold:.2f})",
    )


def to_evidence(transcript: Transcript, match: QuoteMatch) -> Evidence:
    """Build an `Evidence` from a successful match (uses the transcript's own text)."""
    if match.status is MatchType.UNVERIFIED or match.segment is None:
        raise ValueError("cannot build evidence from an unverified quote")
    seg = transcript.segment(match.segment)
    assert seg is not None
    return Evidence(
        interview_id=transcript.id,
        segment=seg.number,
        speaker=seg.speaker,
        role=seg.role,
        quote=transcript.text[match.start : match.end],
        start=match.start,
        end=match.end,
        match=match.status,
        score=match.score,
    )
