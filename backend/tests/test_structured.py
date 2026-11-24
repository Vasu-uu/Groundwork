import json

import pytest
from pydantic import BaseModel

from app.llm import Message, ProviderUnavailableError, UsageTracker
from app.llm.mock import MockProvider
from app.llm.structured import (
    StructuredOutputError,
    generate_structured,
    inline_schema,
    parse_json_loosely,
)
from app.services.extraction import ExtractionOutput

MSGS = [Message(role="user", content="go")]


class Item(BaseModel):
    name: str
    count: int


class Wrapper(BaseModel):
    items: list[Item]


def test_parse_json_loosely_repairs_fences_prose_and_trailing_commas():
    assert parse_json_loosely('```json\n{"a": 1,}\n```') == {"a": 1}
    assert parse_json_loosely('Sure! Here it is: {"a": [1, 2,],} Hope that helps.') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        parse_json_loosely("no json here")


def test_inline_schema_has_no_refs():
    schema = inline_schema(Wrapper)
    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)
    assert schema["properties"]["items"]["items"]["properties"]["count"]["type"] == "integer"


async def test_valid_output_needs_one_call_and_sends_schema():
    provider = MockProvider(['{"items": [{"name": "a", "count": 1}]}'])
    tracker = UsageTracker("r")
    out = await generate_structured(provider, MSGS, Wrapper, tracker=tracker, purpose="t")
    assert out.items[0].count == 1
    assert provider.calls[0][1].json_schema is not None
    assert tracker.summary().calls == 1


async def test_invalid_output_is_retried_with_the_validation_errors():
    provider = MockProvider(
        ['{"items": [{"name": "a"}]}', '{"items": [{"name": "a", "count": 2}]}']
    )
    tracker = UsageTracker("r")
    out = await generate_structured(provider, MSGS, Wrapper, tracker=tracker, purpose="t")
    assert out.items[0].count == 2
    retry_messages = provider.calls[1][0]
    assert retry_messages[-2].role == "assistant"
    assert "items.0.count" in retry_messages[-1].content
    assert [r.purpose for r in tracker.records] == ["t", "t:retry1"]


async def test_gives_up_after_max_retries():
    provider = MockProvider(["nope"] * 5)
    with pytest.raises(StructuredOutputError) as info:
        await generate_structured(provider, MSGS, Wrapper, max_retries=2)
    assert len(provider.calls) == 3
    assert info.value.attempts == 3
    assert info.value.last_output == "nope"


async def test_provider_errors_are_not_retried():
    class Down(MockProvider):
        async def generate(self, messages, options=None):
            raise ProviderUnavailableError("down")

    tracker = UsageTracker("r")
    with pytest.raises(ProviderUnavailableError):
        await generate_structured(Down(), MSGS, Wrapper, tracker=tracker)
    assert tracker.summary().failed_calls == 1


def test_extraction_output_accepts_bare_list_and_normalizes_intensity():
    out = ExtractionOutput.model_validate(
        [{"segment": 2, "quote": "q", "summary": "s", "intensity": "HIGH "}]
    )
    assert out.pain_points[0].intensity == "high"
