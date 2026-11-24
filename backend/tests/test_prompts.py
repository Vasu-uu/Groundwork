import pytest

from app.llm.prompts import PromptError, available_versions, load_prompt, parse_prompt

TEMPLATE = """---
name: demo
version: 3
description: A demo prompt.
---
## system
Return JSON like {"a": 1}.
## user
Hello {{ who }}, segments: {{segments}}
"""


def test_parse_and_render():
    p = parse_prompt(TEMPLATE, name="demo", version=3)
    assert p.id == "demo.v3"
    assert p.description == "A demo prompt."
    assert p.variables == {"who", "segments"}
    system, user = p.render(who="Maya", segments="[S1] ...")
    assert system.content == 'Return JSON like {"a": 1}.'  # single braces untouched
    assert user.content == "Hello Maya, segments: [S1] ..."


def test_render_rejects_missing_and_unexpected_variables():
    p = parse_prompt(TEMPLATE, name="demo", version=3)
    with pytest.raises(PromptError, match="missing"):
        p.render(who="Maya")
    with pytest.raises(PromptError, match="unexpected"):
        p.render(who="Maya", segments="x", extra=1)


def test_sections_are_required():
    with pytest.raises(PromptError):
        parse_prompt("## system\nonly system", name="x", version=1)


def test_bundled_extraction_prompt_loads():
    assert available_versions("extract_pain_points") == [1]
    p = load_prompt("extract_pain_points")
    assert p.id == "extract_pain_points.v1"
    assert p.variables == {
        "interview_id",
        "participant",
        "first_segment",
        "last_segment",
        "segments",
    }
    with pytest.raises(PromptError):
        load_prompt("extract_pain_points", 99)
