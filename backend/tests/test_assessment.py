import json

import pytest

from app.llm.mock import MockProvider
from app.models.analysis import Stance
from app.models.hypothesis import Hypothesis
from app.services.assessment import assess_interview
from app.services.extraction import ExtractionConfig
from app.services.samples import load_sample_set

HYPS = [
    Hypothesis(id="H1", text="Freelancers struggle to chase late invoices."),
    Hypothesis(id="H2", text="Freelancers would pay for automated reminders."),
    Hypothesis(id="H3", text="Creating invoices is time-consuming."),
]


@pytest.fixture(scope="module")
def i01():
    return load_sample_set("freelance-invoicing").corpus.get("I-01")


def reply(*items) -> str:
    return json.dumps({"assessments": list(items)})


def a(hid, stance, sup=(), con=(), rationale="r"):
    return {
        "hypothesis_id": hid,
        "stance": stance,
        "rationale": rationale,
        "supporting": [{"segment": 1, "quote": q} for q in sup],
        "contradicting": [{"segment": 1, "quote": q} for q in con],
    }


async def test_stances_need_verified_quotes(i01):
    provider = MockProvider(
        [
            reply(
                a("h1", "Support", sup=["I hate chasing people for money."]),
                # Invented quote: the claimed support does not survive verification.
                a("H2", "supports", sup=["I would happily pay any price for a reminder tool."]),
                # Interviewer question used as evidence: rejected.
                a("H3", "contradicts", con=["What do you do when an invoice is late?"]),
            )
        ]
    )
    result = await assess_interview(i01, HYPS, provider)
    by = {x.hypothesis_id: x for x in result.assessments}
    assert by["H1"].stance is Stance.SUPPORTS
    assert by["H1"].supporting[0].segment == 6  # corrected from the claimed segment 1
    assert by["H2"].stance is Stance.NOT_DISCUSSED
    assert by["H2"].downgraded_from is Stance.SUPPORTS
    assert by["H3"].stance is Stance.NOT_DISCUSSED
    assert result.stats.proposed == 3 and result.stats.verified == 1
    reasons = " ".join(r.reason for r in result.rejected)
    assert "interviewer" in reasons and "not found" in reasons


async def test_missing_hypotheses_default_to_not_discussed(i01):
    provider = MockProvider([reply(a("H9", "supports"))])
    result = await assess_interview(i01, HYPS, provider)
    assert [x.stance for x in result.assessments] == [Stance.NOT_DISCUSSED] * 3


async def test_mixed_survives_with_one_verified_side(i01):
    quote = "My invoicing app has automatic reminders, but I turned them off."
    provider = MockProvider([reply(a("H2", "mixed", con=[quote]))])
    result = await assess_interview(i01, HYPS, provider)
    h2 = next(x for x in result.assessments if x.hypothesis_id == "H2")
    assert h2.stance is Stance.MIXED


async def test_chunks_are_merged_per_hypothesis(i01):
    def responder(messages, options):
        user = messages[-1].content
        if "[S6]" in user:
            return reply(a("H1", "supports", sup=["I hate chasing people for money."]))
        if "[S2]" in user:
            return reply(a("H3", "contradicts", con=["so that part takes maybe five minutes"]))
        if "[S12]" in user:
            return reply(
                a("H1", "contradicts", con=["With small clients the relationship is everything."])
            )
        return reply()

    result = await assess_interview(
        i01, HYPS, MockProvider(responder), config=ExtractionConfig(chunk_chars=250)
    )
    by = {x.hypothesis_id: x for x in result.assessments}
    assert by["H1"].stance is Stance.MIXED  # supported in one chunk, contradicted in another
    assert by["H3"].stance is Stance.CONTRADICTS


async def test_interview_with_only_failed_chunks_is_excluded(i01):
    result = await assess_interview(i01, HYPS, MockProvider(["bad"] * 3))
    assert result.assessments == []
    assert result.failed_interviews == ["I-01"]
