"""Score an analysis against the hand-labelled sample sets.

Metrics per sample set:

- quote verification rate: verified quotes / quotes the model proposed
  (unverified quotes are never shown as evidence, so a low rate means wasted
  work, not wrong evidence);
- verdict agreement: AI-suggested verdict == hand-labelled verdict;
- stance agreement: per interview and hypothesis, AI stance == labelled stance
  (interviews not listed in the labels count as "not_discussed");
- pain-quote recall: share of labelled pain-point quotes that the extraction
  recovered as verified evidence (same interview, overlapping span).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.analysis import AnalysisResult
from app.services.samples import SampleSet


@dataclass
class HypothesisScore:
    hypothesis_id: str
    expected: str
    predicted: str
    stance_matches: int
    stance_total: int
    stance_misses: list[str] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return self.expected == self.predicted


@dataclass
class SetScore:
    set_id: str
    interviews: int
    quotes_proposed: int
    quotes_verified: int
    pain_quotes_labelled: int
    pain_quotes_found: int
    hypotheses: list[HypothesisScore]
    calls: int = 0
    failed_calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    failures: list[str] = field(default_factory=list)

    @property
    def verification_rate(self) -> float:
        return self.quotes_verified / self.quotes_proposed if self.quotes_proposed else 0.0

    @property
    def verdict_agreement(self) -> float:
        return (
            sum(h.agrees for h in self.hypotheses) / len(self.hypotheses)
            if self.hypotheses
            else 0.0
        )

    @property
    def stance_agreement(self) -> float:
        total = sum(h.stance_total for h in self.hypotheses)
        return sum(h.stance_matches for h in self.hypotheses) / total if total else 0.0

    @property
    def pain_recall(self) -> float:
        return (
            self.pain_quotes_found / self.pain_quotes_labelled if self.pain_quotes_labelled else 0.0
        )


def _span_of(text: str, quote: str) -> tuple[int, int] | None:
    i = text.find(quote)
    return (i, i + len(quote)) if i >= 0 else None


def score(sample: SampleSet, labels: dict[str, Any], result: AnalysisResult) -> SetScore:
    transcripts = {t.id: t for t in sample.corpus.transcripts}

    # Pain-quote recall: a labelled quote counts as found when a verified pain
    # point from the same interview overlaps its span in the transcript.
    found = labelled = 0
    spans: dict[str, list[tuple[int, int]]] = {}
    for p in result.pain_points:
        spans.setdefault(p.interview_id, []).append((p.evidence.start, p.evidence.end))
    for pp in labels["pain_points"]:
        for q in pp["quotes"]:
            t = transcripts.get(q["interview"])
            span = _span_of(t.text, q["quote"]) if t else None
            if span is None:
                continue
            labelled += 1
            if any(s < span[1] and span[0] < e for s, e in spans.get(q["interview"], [])):
                found += 1

    stances = labels.get("stances", {})
    verdicts = {v.hypothesis.id: v for v in result.verdicts}
    hyp_scores = []
    for hid, expected in labels["verdicts"].items():
        v = verdicts.get(hid)
        matches, misses = 0, []
        if v is not None:
            for a in v.assessments:
                want = stances.get(hid, {}).get(a.interview_id, {}).get("stance", "not_discussed")
                if a.stance.value == want:
                    matches += 1
                else:
                    misses.append(f"{a.interview_id}: {a.stance.value} (label {want})")
        hyp_scores.append(
            HypothesisScore(
                hypothesis_id=hid,
                expected=expected["verdict"],
                predicted=v.verdict.value if v else "MISSING",
                stance_matches=matches,
                stance_total=len(v.assessments) if v else len(transcripts),
                stance_misses=misses,
            )
        )

    return SetScore(
        set_id=sample.id,
        interviews=result.interview_count,
        quotes_proposed=result.quote_stats.proposed,
        quotes_verified=result.quote_stats.verified,
        pain_quotes_labelled=labelled,
        pain_quotes_found=found,
        hypotheses=hyp_scores,
        failures=list(result.failures),
    )


def to_markdown(scores: list[SetScore], *, provider: str, model: str, when: str) -> str:
    lines = [
        "# Groundwork eval results",
        "",
        f"Provider `{provider}`, model `{model}`, run {when}.",
        "",
        "| Sample set | Interviews | Verified quotes | Verdict agreement | Stance agreement "
        "| Pain-quote recall | Calls (failed) | Tokens | Time |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in scores:
        agreed = sum(h.agrees for h in s.hypotheses)
        lines.append(
            f"| {s.set_id} | {s.interviews} | {s.quotes_verified}/{s.quotes_proposed} "
            f"({s.verification_rate:.0%}) | {agreed}/{len(s.hypotheses)} "
            f"({s.verdict_agreement:.0%}) | {s.stance_agreement:.0%} | "
            f"{s.pain_quotes_found}/{s.pain_quotes_labelled} ({s.pain_recall:.0%}) | "
            f"{s.calls} ({s.failed_calls}) | {s.tokens} | {s.seconds:.0f}s |"
        )
    if scores:
        proposed = sum(s.quotes_proposed for s in scores)
        verified = sum(s.quotes_verified for s in scores)
        hyps = [h for s in scores for h in s.hypotheses]
        lines += [
            "",
            f"**Overall:** verified quotes {verified}/{proposed} "
            f"({verified / proposed if proposed else 0:.0%}), verdict agreement "
            f"{sum(h.agrees for h in hyps)}/{len(hyps)}.",
        ]
    for s in scores:
        lines += [
            "",
            f"## {s.set_id}",
            "",
            "| Hypothesis | Label | AI suggestion | Stances matching |",
        ]
        lines.append("| --- | --- | --- | --- |")
        for h in s.hypotheses:
            mark = "" if h.agrees else " ✗"
            lines.append(
                f"| {h.hypothesis_id} | {h.expected} | {h.predicted}{mark} "
                f"| {h.stance_matches}/{h.stance_total} |"
            )
        misses = [f"{h.hypothesis_id} {m}" for h in s.hypotheses for m in h.stance_misses]
        if misses:
            lines += ["", "Stance disagreements: " + "; ".join(misses) + "."]
        if s.failures:
            lines += ["", "Model failures: " + "; ".join(s.failures)]
    return "\n".join(lines) + "\n"
