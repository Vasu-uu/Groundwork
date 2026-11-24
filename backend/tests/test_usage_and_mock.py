import pytest

from app.llm import Message, ProviderResponseError, UsageTracker
from app.llm.mock import MockProvider


async def test_mock_provider_scripts_and_records_calls():
    provider = MockProvider(["first", "second"])
    msgs = [Message(role="user", content="hello world")]
    assert (await provider.generate(msgs)).text == "first"
    assert (await provider.generate(msgs)).text == "second"
    assert len(provider.calls) == 2
    with pytest.raises(ProviderResponseError):
        await provider.generate(msgs)


async def test_mock_provider_accepts_a_responder():
    provider = MockProvider(lambda msgs, opts: msgs[-1].content.upper())
    resp = await provider.generate([Message(role="user", content="abc")])
    assert resp.text == "ABC"


async def test_usage_tracker_aggregates_calls():
    provider = MockProvider(["a" * 40, "b" * 80])
    tracker = UsageTracker(run_id="run-1")
    for purpose in ("extract", "cluster"):
        resp = await provider.generate([Message(role="user", content="x" * 400)])
        tracker.record(resp, purpose=purpose)
    tracker.record_failure("mock", "mock", purpose="evaluate")

    s = tracker.summary()
    assert s.calls == 3
    assert s.failed_calls == 1
    assert s.prompt_tokens == 200
    assert s.completion_tokens == 30
    assert s.total_tokens == 230
    assert s.cost_eur == 0.0
    assert s.providers == ["mock"]
