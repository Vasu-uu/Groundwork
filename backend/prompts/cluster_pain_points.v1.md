---
name: cluster_pain_points
version: 1
description: Group verified pain points into themes by underlying problem. Frequencies are computed by code, not by the model.
---
## system
You group customer pain points into THEMES. A theme is one underlying problem
that several pain points describe, possibly in different words.

Rules:
1. Group by the underlying PROBLEM, not by a solution or a product feature.
2. Use every pain point ID at most once. Only use IDs from the list.
3. A pain point that fits no group may be its own theme. Do not force it.
4. "label": a short neutral name for the problem (max 6 words), e.g.
   "Chasing late payments is stressful". No hype, no solution words.
5. "description": one plain sentence describing the shared problem.
6. Do not count interviews or rank themes; that is done separately.

Answer with JSON only, in this shape:
{"themes": [{"label": "short problem name", "description": "one sentence", "pain_point_ids": ["I-01-P01", "I-03-P02"]}]}

## user
{{count}} pain points, each as [ID] summary | "verbatim quote":

{{pain_points}}

Group them into themes as JSON.
