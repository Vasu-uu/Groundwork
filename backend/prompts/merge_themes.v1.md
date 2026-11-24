---
name: merge_themes
version: 1
description: Reduce step of clustering. Merge themes from different batches that describe the same problem.
---
## system
You receive themes that were found separately in batches of customer pain
points. Some describe the same underlying problem in different words. Merge
those; keep distinct problems separate.

Rules:
1. Use every theme ID at most once. Only use IDs from the list.
2. A theme that matches no other stays in its own group.
3. "label": short neutral problem name (max 6 words). "description": one sentence.

Answer with JSON only, in this shape:
{"groups": [{"label": "short problem name", "description": "one sentence", "theme_ids": ["T1", "T4"]}]}

## user
Themes:

{{themes}}

Merge themes that describe the same problem, as JSON.
