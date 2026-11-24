import pytest

from app.models.analysis import Confidence, InterviewAssessment, Stance, StanceCounts, VerdictLabel
from app.models.evidence import Evidence, MatchType
from app.models.hypothesis import Hypothesis
from app.models.transcript import SpeakerRole
from app.services.verdicts import _label, build_verdict, what_would_change

H = Hypothesis(id="H1", text="Freelancers struggle to chase late invoices.")


def counts(s=0, c=0, m=0, n=0) -> StanceCounts:
    return StanceCounts(supports=s, contradicts=c, mixed=m, not_discussed=n)


def assessments(s=0, c=0, m=0, n=0) -> list[InterviewAssessment]:
    stances = [Stance.SUPPORTS] * s + [Stance.CONTRADICTS] * c + [Stance.MIXED] * m
    stances += [Stance.NOT_DISCUSSED] * n
    return [
        InterviewAssessment(interview_id=f"I-{i:02d}", hypothesis_id="H1", stance=st)
        for i, st in enumerate(stances, start=1)
    ]


@pytest.mark.parametrize(
    ("c", "expected"),
    [
        (counts(5, 1), VerdictLabel.VALIDATED),  # freelance H1: 5/6 = 83%
        (counts(2, 2, 2), VerdictLabel.MIXED),  # freelance H2: 3/6 = 50%
        (counts(0, 6), VerdictLabel.INVALIDATED),  # freelance H3
        (counts(n=6), VerdictLabel.UNTESTED),  # freelance H4
        (counts(4, 1), VerdictLabel.VALIDATED),  # physio H1: 80%
        (counts(3, 2), VerdictLabel.MIXED),  # physio H2: 60%
        (counts(2, 1), VerdictLabel.MIXED),  # 67% is not enough
        (counts(1, n=5), VerdictLabel.UNTESTED),  # never VALIDATED from one interview
        (counts(c=1, n=5), VerdictLabel.UNTESTED),  # ...nor INVALIDATED
        (counts(1, 1), VerdictLabel.MIXED),
        (counts(2, 0, 2), VerdictLabel.VALIDATED),  # 3/4 = 75%: on the threshold
        (counts(1, 0, 3), VerdictLabel.MIXED),  # 62.5%, and only 1 clear supporter
        (counts(0, 2, 1), VerdictLabel.INVALIDATED),  # 0.5/3 = 17%, 2 contradicting
        (counts(1, 2), VerdictLabel.MIXED),  # 33% support
    ],
)
def test_decision_rules(c, expected):
    assert _label(c) is expected


def test_mixed_interviews_count_half():
    assert counts(1, 0, 2).support_ratio == pytest.approx(2 / 3)


def test_what_would_change_is_quantified():
    # VALIDATED 5/6: one more contradicting -> 5/7 = 71% -> MIXED.
    assert what_would_change(counts(5, 1), VerdictLabel.VALIDATED).startswith(
        "1 more interview contradicting it would turn this into MIXED"
    )
    # INVALIDATED 0/6: +2 supporting -> 2/8 = 25% (still invalidated); +3 -> 33%.
    assert what_would_change(counts(0, 6), VerdictLabel.INVALIDATED).startswith(
        "3 more interviews supporting it"
    )
    mixed = what_would_change(counts(2, 2, 2), VerdictLabel.MIXED)
    assert "VALIDATED after" in mixed and "INVALIDATED after" in mixed
    assert "at least 2 interviews" in what_would_change(counts(n=4), VerdictLabel.UNTESTED)
    assert "Only 1 interview" in what_would_change(counts(1, n=3), VerdictLabel.UNTESTED)


def test_confidence_levels():
    high = build_verdict(H, assessments(s=6), small_sample=False)
    assert (high.verdict, high.confidence) == (VerdictLabel.VALIDATED, Confidence.HIGH)
    medium = build_verdict(H, assessments(s=5, c=1), small_sample=False)
    assert medium.confidence is Confidence.MEDIUM  # 83% is not one-sided enough for high
    small = build_verdict(H, assessments(s=3), small_sample=True)
    assert small.verdict is VerdictLabel.VALIDATED
    assert small.confidence is Confidence.LOW
    assert small.provisional
    assert "provisional" in small.confidence_note
    untested = build_verdict(H, assessments(n=6), small_sample=False)
    assert untested.confidence is Confidence.LOW
    assert untested.status == "ai_suggestion"


def test_note_states_the_counts_and_rule():
    v = build_verdict(H, assessments(s=4, c=1, n=1), small_sample=False)
    assert v.confidence_note.startswith(
        "4 of 6 interviewees support it, 1 contradict it, 0 are mixed and 1 did not discuss it."
    )
    assert "VALIDATED needs" in v.rule


def _ev(iid: str, start: int, role=SpeakerRole.INTERVIEWEE) -> Evidence:
    return Evidence(
        interview_id=iid, segment=1, speaker="x", role=role, quote="q", start=start,
        end=start + 1, match=MatchType.EXACT, score=1.0,
    )  # fmt: skip


def test_counter_evidence_puts_strongest_first():
    a = [
        InterviewAssessment(
            interview_id="I-01", hypothesis_id="H1", stance=Stance.MIXED,
            contradicting=[_ev("I-01", 5)],
        ),
        InterviewAssessment(
            interview_id="I-02", hypothesis_id="H1", stance=Stance.CONTRADICTS,
            contradicting=[_ev("I-02", 9, SpeakerRole.NOTE), _ev("I-02", 3)],
        ),
    ]  # fmt: skip
    v = build_verdict(H, a, small_sample=False)
    order = [(e.interview_id, e.start) for e in v.counter_evidence]
    # verbatim before paraphrase; clear contradiction before mixed
    assert order == [("I-02", 3), ("I-01", 5), ("I-02", 9)]
