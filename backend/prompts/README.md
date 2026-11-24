# Prompt templates

Each prompt lives in its own versioned file, e.g. `extract_pain_points.v1.md`.
A change in wording gets a new version file instead of editing the old one, so
eval results and run logs can always name the exact prompt they used.
The prompt ID (e.g. `extract_pain_points.v1`) is recorded with every LLM call.

File layout: a `---` front-matter block (`name`, `version`, `description`),
then `## system` and `## user` sections. Variables use `{{name}}`; rendering
fails if one is missing or unexpected. See `app/llm/prompts.py`.

| Prompt | Used by | Notes |
| --- | --- | --- |
| `extract_pain_points.v1` | `app/services/extraction.py` | Hypothesis-blind; verbatim quote + segment per pain point |
