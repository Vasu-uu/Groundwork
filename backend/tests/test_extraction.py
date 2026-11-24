import json

import pytest

from app.llm import Message, ProviderUnavailableError, UsageTracker
from app.llm.mock import MockProvider
from app.models.evidence import MatchType
from app.services.extraction import ExtractionConfig, extract_corpus, extract_interview
from app.services.samples import load_labels, load_sample_set


@pytest.fixture(scope="module")
def sample():
    return load_sample_set("freelance-invoicing")


def reply(*items) -> str:
    return json.dumps({"pain_points": list(items)})


def item(segment, quote, summary="pain", intensity="medium"):
    return {"segment": segment, "quote": quote, "summary": summary, "intensity": intensity}


async def test_verified_rejected_and_interviewer_quotes(sample):
    t = sample.corpus.get("I-01")
    provider = MockProvider(
        [
            reply(
                item(
                    6, "I hate chasing people for money.", "Chasing payment is unpleasant", "high"
                ),
                item(8, "Last spring I had an agency that paid me 74 days after the invoice"),
                item(6, "I love chasing my clients, it is my favourite part of the job."),
                item(5, "What do you do when an invoice is late?"),
                item(10, "Its stressful because my income is already lumpy."),
            )
        ]
    )
    tracker = UsageTracker("run")
    result = await extract_interview(t, provider, tracker=tracker)

    assert [p.id for p in result.pain_points] == ["I-01-P01", "I-01-P02", "I-01-P03"]
    first = result.pain_points[0]
    assert first.intensity == "high"
    assert first.evidence.segment == 6 and first.evidence.speaker == "Maya"
    assert first.evidence.quote == t.text[first.evidence.start : first.evidence.end]
    assert result.pain_points[2].evidence.match is MatchType.FUZZY

    reasons = {r.quote: r.reason for r in result.rejected}
    assert "not found" in reasons["I love chasing my clients, it is my favourite part of the job."]
    assert "interviewer" in reasons["What do you do when an invoice is late?"]

    assert result.stats.proposed == 5
    assert result.stats.verified == 3
    assert result.stats.label() == "verified quotes: 3/5"
    assert result.prompt_id == "extract_pain_points.v1"
    assert tracker.summary().calls == 1


async def test_prompt_is_hypothesis_blind_and_marks_roles(sample):
    t = sample.corpus.get("I-01")
    provider = MockProvider([reply()])
    await extract_interview(t, provider)
    user: Message = provider.calls[0][0][1]
    assert "[S6] Maya (CUSTOMER): I hate chasing people for money." in user.content
    assert "(INTERVIEWER, do not quote)" in user.content
    for h in sample.hypotheses:
        assert h.text not in user.content


async def test_long_interview_is_chunked_and_numbering_continues(sample):
    t = sample.corpus.get("I-01")
    quotes = {6: "I hate chasing people for money.", 12: "They sounded robotic"}

    def responder(messages, options):
        text = messages[1].content
        return reply(*(item(n, q) for n, q in quotes.items() if f"[S{n}]" in text))

    provider = MockProvider(responder)
    result = await extract_interview(t, provider, config=ExtractionConfig(chunk_chars=300))
    assert len(provider.calls) > 2
    assert [p.id for p in result.pain_points] == ["I-01-P01", "I-01-P02"]


async def test_invalid_output_becomes_a_failure_not_a_crash(sample):
    t = sample.corpus.get("I-01")
    provider = MockProvider(["garbage"] * 3)
    result = await extract_interview(t, provider, config=ExtractionConfig(max_retries=2))
    assert result.pain_points == []
    assert len(result.failures) == 1
    assert result.failures[0].interview_id == "I-01"


async def test_provider_down_aborts_the_whole_corpus(sample):
    class Down(MockProvider):
        async def generate(self, messages, options=None):
            raise ProviderUnavailableError("Ollama is not running")

    with pytest.raises(ProviderUnavailableError):
        await extract_corpus(sample.corpus, Down())


@pytest.mark.parametrize("set_id", ["freelance-invoicing", "physio-no-shows", "restaurant-waste"])
async def test_ground_truth_quotes_all_verify_end_to_end(set_id):
    """Feed the hand-labelled quotes through the full pipeline: all must verify."""
    sample = load_sample_set(set_id)
    labels = load_labels(set_id)
    by_interview: dict[str, list[dict]] = {}
    for pp in labels["pain_points"]:
        for q in pp["quotes"]:
            by_interview.setdefault(q["interview"], []).append(item(1, q["quote"], pp["label"]))

    def responder(messages, options):
        iid = messages[1].content.split()[1]
        return reply(*by_interview.get(iid, []))

    result = await extract_corpus(sample.corpus, MockProvider(responder), config=ExtractionConfig())
    expected = sum(len(v) for v in by_interview.values())
    assert result.stats.proposed == expected
    assert result.stats.rate == 1.0, result.rejected
    assert {p.interview_id for p in result.pain_points} == set(by_interview)
