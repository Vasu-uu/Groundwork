"""Structured (JSON) generation with validation, local repair and bounded retries.

Small local models sometimes wrap JSON in code fences, leave trailing commas,
or miss a field. The pipeline is:

1. Ask for JSON, passing the Pydantic model's schema to the provider
   (Ollama enforces it with constrained decoding; others use JSON mode).
2. Parse leniently: strip fences, cut to the outermost JSON value, drop
   trailing commas.
3. Validate with Pydantic.
4. On failure, send the validation errors back and ask for a corrected
   answer, at most `max_retries` times (default 2). Then give up with a
   `StructuredOutputError` instead of passing bad data downstream.

Every attempt is recorded in the run's `UsageTracker`.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.base import GenerationOptions, LLMError, LLMProvider, Message
from app.llm.usage import UsageTracker

T = TypeVar("T", bound=BaseModel)

DEFAULT_MAX_RETRIES = 2

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n?|\n?\s*```\s*$")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")

REPAIR_INSTRUCTION = (
    "Your previous answer could not be used: {errors}\n"
    "Reply again with ONLY the corrected JSON object that matches the schema. "
    "No explanations, no code fences."
)


class StructuredOutputError(LLMError):
    """The model did not produce valid output within the retry budget."""

    def __init__(self, message: str, *, last_output: str, errors: str, attempts: int) -> None:
        super().__init__(message)
        self.last_output = last_output
        self.errors = errors
        self.attempts = attempts


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with `$ref`s inlined (some grammar converters reject refs)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return resolve(copy.deepcopy(defs[ref.split("/")[-1]]))
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def parse_json_loosely(text: str) -> Any:
    """Parse JSON from model output, repairing the most common defects.

    Raises `ValueError` if nothing parseable is found.
    """
    s = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON object found in the output")
    start = min(starts)
    end = max(s.rfind("}"), s.rfind("]"))
    if end <= start:
        raise ValueError("unterminated JSON in the output")
    candidate = _TRAILING_COMMA.sub(r"\1", s[start : end + 1])
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON ({exc.msg} at position {exc.pos})") from exc


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        problems = [
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()[:8]
        ]
        return "schema validation failed: " + "; ".join(problems)
    return str(exc)


async def generate_structured(
    provider: LLMProvider,
    messages: list[Message],
    output_model: type[T],
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    purpose: str = "structured",
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> T:
    """Generate and validate an `output_model` instance.

    Provider errors (unreachable, misconfigured) propagate immediately: retrying
    cannot fix them. Invalid output is retried up to `max_retries` times.
    """
    opts = (options or GenerationOptions()).model_copy(
        update={"json_schema": inline_schema(output_model)}
    )
    conversation = list(messages)
    last_output = ""
    errors = ""
    for attempt in range(max_retries + 1):
        label = purpose if attempt == 0 else f"{purpose}:retry{attempt}"
        try:
            resp = await provider.generate(conversation, opts)
        except LLMError:
            if tracker:
                tracker.record_failure(provider.name, provider.model, label)
            raise
        if tracker:
            tracker.record(resp, label)
        last_output = resp.text
        try:
            return output_model.model_validate(parse_json_loosely(resp.text))
        except ValueError as exc:  # includes JSONDecodeError and ValidationError
            errors = _describe(exc)
            conversation = [
                *messages,
                Message(role="assistant", content=resp.text[:4000]),
                Message(role="user", content=REPAIR_INSTRUCTION.format(errors=errors)),
            ]
    raise StructuredOutputError(
        f"{purpose}: model output was still invalid after {max_retries + 1} attempts ({errors})",
        last_output=last_output,
        errors=errors,
        attempts=max_retries + 1,
    )
