"""Turn per-interview stances into a hypothesis verdict with transparent rules.

The model never picks the verdict. Given how many interviewees support,
contradict, are mixed on, or never discussed a hypothesis:

    discussed = supports + contradicts + mixed
    ratio     = (supports + 0.5 * mixed) / discussed

    discussed == 0                         -> UNTESTED
    discussed == 1                         -> UNTESTED  (one interview proves nothing)
    supports >= 2 and ratio >= 0.75        -> VALIDATED
    contradicts >= 2 and ratio <= 0.25     -> INVALIDATED
    otherwise                              -> MIXED

Confidence (low / medium / high) depends on how many interviews discussed it
and how one-sided they are, and is capped at "low" below the 5-interview
minimum. Each verdict also states, in numbers, what would change it.
"""

from __future__ import annotations

from app.models.analysis import (
    Confidence,
    HypothesisVerdict,
    InterviewAssessment,
    StanceCounts,
    Theme,
    VerdictLabel,
)
from app.models.evidence import Evidence, PainPoint
from app.models.hypothesis import Hypothesis
from app.services.corpus import MIN_INTERVIEWS_FOR_CONCLUSIONS

VALIDATE_RATIO = 0.75
INVALIDATE_RATIO = 0.25
MIN_AGREEING_INTERVIEWS = 2
_MAX_SEARCH = 200

RULE_TEXT = (
    "VALIDATED needs >= 2 supporting interviews and >= 75% support among interviews that "
    "discussed it; INVALIDATED needs >= 2 contradicting and <= 25% support; fewer than 2 "
    "discussing interviews is UNTESTED; anything else is MIXED. Mixed interviews count half."
)


def _label(c: StanceCounts) -> VerdictLabel:
    if c.discussed < 2:
        return VerdictLabel.UNTESTED
    if c.supports >= MIN_AGREEING_INTERVIEWS and c.support_ratio >= VALIDATE_RATIO:
        return VerdictLabel.VALIDATED
    if c.contradicts >= MIN_AGREEING_INTERVIEWS and c.support_ratio <= INVALIDATE_RATIO:
        return VerdictLabel.INVALIDATED
    return VerdictLabel.MIXED


def _with(c: StanceCounts, supports: int = 0, contradicts: int = 0) -> StanceCounts:
    return c.model_copy(
        update={"supports": c.supports + supports, "contradicts": c.contradicts + contradicts}
    )


def _needed(c: StanceCounts, *, supports: bool, until: set[VerdictLabel]) -> int | None:
    """Smallest number of extra supporting (or contradicting) interviews that reaches `until`."""
    for k in range(1, _MAX_SEARCH):
        nxt = _with(c, supports=k) if supports else _with(c, contradicts=k)
        if _label(nxt) in until:
            return k
    return None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def what_would_change(c: StanceCounts, label: VerdictLabel) -> str:
    if label is VerdictLabel.UNTESTED:
        if c.discussed == 0:
            return (
                "No interview discussed this. Ask about it directly (without leading) in at "
                "least 2 interviews before drawing any conclusion."
            )
        return (
            "Only 1 interview discussed this, and one interview cannot settle a hypothesis. "
            "Ask about it in at least 1 more interview."
        )
    if label is VerdictLabel.VALIDATED:
        k = _needed(c, supports=False, until={VerdictLabel.MIXED, VerdictLabel.INVALIDATED})
        return f"{_plural(k or 0, 'more interview')} contradicting it would turn this into MIXED."
    if label is VerdictLabel.INVALIDATED:
        k = _needed(c, supports=True, until={VerdictLabel.MIXED, VerdictLabel.VALIDATED})
        return f"{_plural(k or 0, 'more interview')} supporting it would turn this into MIXED."
    up = _needed(c, supports=True, until={VerdictLabel.VALIDATED})
    down = _needed(c, supports=False, until={VerdictLabel.INVALIDATED})
    return (
        f"It would become VALIDATED after {_plural(up or 0, 'more supporting interview')}, "
        f"or INVALIDATED after {_plural(down or 0, 'more contradicting interview')}. "
        "A sharper, non-leading question would help separate the two."
    )


def _confidence(
    c: StanceCounts, label: VerdictLabel, small_sample: bool, mostly_paraphrase: bool
) -> Confidence:
    if label is VerdictLabel.UNTESTED or small_sample:
        return Confidence.LOW
    one_sided = c.support_ratio >= 0.85 or c.support_ratio <= 0.15
    if c.discussed >= 5 and one_sided and label is not VerdictLabel.MIXED:
        level = Confidence.HIGH
    elif c.discussed >= 3:
        level = Confidence.MEDIUM
    else:
        level = Confidence.LOW
    if mostly_paraphrase and level is not Confidence.LOW:
        level = Confidence.MEDIUM if level is Confidence.HIGH else Confidence.LOW
    return level


def _note(c: StanceCounts, small_sample: bool, mostly_paraphrase: bool, failed: int) -> str:
    parts = [
        f"{c.supports} of {c.total} interviewees support it, {c.contradicts} contradict it, "
        f"{c.mixed} are mixed and {c.not_discussed} did not discuss it."
    ]
    if small_sample:
        parts.append(
            f"Fewer than {MIN_INTERVIEWS_FOR_CONCLUSIONS} interviews in total: "
            "treat this as provisional."
        )
    if mostly_paraphrase:
        parts.append(
            "Most of the evidence comes from founder notes (paraphrase), not verbatim speech."
        )
    if failed:
        parts.append(f"{_plural(failed, 'interview')} could not be assessed and are not counted.")
    return " ".join(parts)


def _dedupe(evidence: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, int, int]] = set()
    out = []
    for e in evidence:
        key = (e.interview_id, e.start, e.end)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def related_themes(
    evidence: list[Evidence], themes: list[Theme], pain_points: list[PainPoint]
) -> list[str]:
    """Themes whose pain points cite the same transcript segments as this verdict."""
    cited = {(e.interview_id, e.segment) for e in evidence}
    by_id = {p.id: p for p in pain_points}
    return [
        t.id
        for t in themes
        if any(
            (by_id[pid].interview_id, by_id[pid].evidence.segment) in cited
            for pid in t.pain_point_ids
            if pid in by_id
        )
    ]


def build_verdict(
    hypothesis: Hypothesis,
    assessments: list[InterviewAssessment],
    *,
    small_sample: bool,
    themes: list[Theme] | None = None,
    pain_points: list[PainPoint] | None = None,
    failed_interviews: int = 0,
) -> HypothesisVerdict:
    own = [a for a in assessments if a.hypothesis_id == hypothesis.id]
    counts = StanceCounts()
    for a in own:
        setattr(counts, a.stance.value, getattr(counts, a.stance.value) + 1)

    supporting = _dedupe([e for a in own for e in a.supporting])
    contradicting = _dedupe([e for a in own for e in a.contradicting])
    evidence = supporting + contradicting
    mostly_paraphrase = bool(evidence) and sum(e.paraphrase for e in evidence) * 2 > len(evidence)

    label = _label(counts)
    return HypothesisVerdict(
        hypothesis=hypothesis,
        verdict=label,
        confidence=_confidence(counts, label, small_sample, mostly_paraphrase),
        confidence_note=_note(counts, small_sample, mostly_paraphrase, failed_interviews),
        what_would_change=what_would_change(counts, label),
        rule=RULE_TEXT,
        counts=counts,
        provisional=small_sample,
        supporting=supporting,
        contradicting=contradicting,
        assessments=own,
        related_theme_ids=related_themes(evidence, themes or [], pain_points or []),
    )
