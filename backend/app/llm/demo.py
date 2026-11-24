"""Demo provider: replays hand-labelled answers for the bundled sample sets.

Select it with `LLM_PROVIDER=demo` to try Groundwork without installing a
model. It answers each prompt the way a careful analyst would, using the
ground truth in `samples/*/labels.json`:

- extraction: the labelled pain-point quotes found in the transcript chunk;
- clustering: groups pain points by their labelled theme;
- assessment: the labelled per-interview stance and quotes;
- script: the hand-written demo questions for each target.

Everything downstream is real: quotes are still verified against the
transcripts, frequencies and verdicts are still computed by code, and the
human checkpoint still applies. Interviews that are not part of a sample set
get empty answers (no pain points, every hypothesis "not discussed"), and the
health check says so. No model is called, so the token counts are estimates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.llm.base import GenerationOptions, HealthStatus, Message, ProviderHealth
from app.llm.mock import MockProvider
from app.services.samples import DEFAULT_SAMPLES_DIR, list_sample_sets, load_labels

_INTERVIEW = re.compile(r"^Interview (\S+) \(participant", re.MULTILINE)
_PAIN_LINE = re.compile(r"^\[(?P<id>[^\]]+)\] (?P<summary>.*?) \| ", re.MULTILINE)
_HYP = re.compile(r"^(H\d+): ", re.MULTILINE)
_TARGET = re.compile(r"^- ([HT]\d+)\b[^:\n]*: (.*)$", re.MULTILINE)
_SEGMENT = re.compile(r"\[S(\d+)\]")

GENERIC_QUESTION = {
    "question": "Tell me about the last time this came up for you. What happened?",
    "purpose": "Get a concrete, recent example instead of an opinion.",
    "bias_check": "Asks about a past event, so the answer is a fact, not a prediction.",
    "follow_ups": ["What happened next?"],
}


def _segment_of(prompt: str, quote: str) -> int:
    """The [S..] number of the prompt line that contains the quote (1 if not found)."""
    probe = quote[:30]
    for line in prompt.splitlines():
        m = _SEGMENT.match(line)
        if m and probe in line:
            return int(m.group(1))
    return 1


class DemoProvider(MockProvider):
    name = "demo"

    def __init__(
        self, samples_dir: Path = DEFAULT_SAMPLES_DIR, *, set_ids: list[str] | None = None
    ):
        super().__init__(self._respond, model="hand-labelled-replay")
        ids = set_ids or [s.id for s in list_sample_sets(samples_dir)]
        self.labels: dict[str, dict[str, Any]] = {i: load_labels(i, samples_dir) for i in ids}
        self.interview_set: dict[str, str] = {}
        for set_id, labels in self.labels.items():
            for pp in labels["pain_points"]:
                for iid in pp["interviews"]:
                    self.interview_set.setdefault(iid, set_id)
            for per_interview in labels.get("stances", {}).values():
                for iid in per_interview:
                    self.interview_set.setdefault(iid, set_id)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            model=self.model,
            status=HealthStatus.OK,
            detail=(
                "Demo mode: answers are replayed from hand labels for the bundled sample sets. "
                "No model is called; your own interviews will return no findings."
            ),
        )

    # --- Dispatch -----------------------------------------------------------------------------

    def _respond(self, messages: list[Message], options: GenerationOptions) -> str:
        system, user = messages[0].content, messages[-1].content
        if "NEXT interview" in system:
            return self._script(user)
        if "THEMES" in system:
            return self._cluster(user)
        if "skeptical" in system:
            return self._assess(user)
        return self._extract(user)

    def _labels_for(self, user: str) -> dict[str, Any] | None:
        m = _INTERVIEW.search(user)
        set_id = self.interview_set.get(m.group(1)) if m else None
        return self.labels.get(set_id) if set_id else None

    def _extract(self, user: str) -> str:
        labels = self._labels_for(user)
        iid = m.group(1) if (m := _INTERVIEW.search(user)) else ""
        items = [
            {
                "segment": _segment_of(user, q["quote"]),
                "quote": q["quote"],
                "summary": pp["label"],
                "intensity": "high",
            }
            for pp in (labels or {}).get("pain_points", [])
            for q in pp["quotes"]
            if q["interview"] == iid and q["quote"][:30] in user
        ]
        return json.dumps({"pain_points": items})

    def _cluster(self, user: str) -> str:
        groups: dict[str, list[str]] = {}
        for m in _PAIN_LINE.finditer(user):
            groups.setdefault(m.group("summary"), []).append(m.group("id"))
        themes = [
            {"label": label, "description": label, "pain_point_ids": ids}
            for label, ids in groups.items()
        ]
        return json.dumps({"themes": themes})

    def stance_of(self, labels: dict[str, Any] | None, hid: str, iid: str) -> dict[str, Any]:
        entry = (labels or {}).get("stances", {}).get(hid, {}).get(iid)
        return entry or {"stance": "not_discussed", "supporting": [], "contradicting": []}

    def _assess(self, user: str) -> str:
        labels = self._labels_for(user)
        iid = m.group(1) if (m := _INTERVIEW.search(user)) else ""
        out = []
        for hid in _HYP.findall(user):
            entry = self.stance_of(labels, hid, iid)
            present = [q for q in entry["supporting"] + entry["contradicting"] if q[:30] in user]
            # A chunk that does not contain the labelled quotes says nothing about the hypothesis.
            stance = entry["stance"] if present else "not_discussed"
            out.append(
                {
                    "hypothesis_id": hid,
                    "stance": stance,
                    "rationale": f"Hand label: {stance.replace('_', ' ')}." if present else "",
                    "supporting": [
                        {"segment": _segment_of(user, q), "quote": q}
                        for q in entry["supporting"]
                        if q in present
                    ],
                    "contradicting": [
                        {"segment": _segment_of(user, q), "quote": q}
                        for q in entry["contradicting"]
                        if q in present
                    ],
                }
            )
        return json.dumps({"assessments": out})

    def _script(self, user: str) -> str:
        targets = _TARGET.findall(user)  # [(id, text)]
        labels = self._script_labels(user)
        by_label = {pp["label"]: pp["id"] for pp in (labels or {}).get("pain_points", [])}
        demo = (labels or {}).get("demo_questions", {})
        questions = []
        for tid, text in targets:
            key = by_label.get(text.strip(), tid) if tid.startswith("T") else tid
            for q in demo.get(key) or [GENERIC_QUESTION]:
                questions.append({"target": tid, **q})
        return json.dumps({"questions": questions})

    def _script_labels(self, user: str) -> dict[str, Any] | None:
        """The script prompt has no interview IDs: recognise the set by its theme labels."""
        best, hits = None, 0
        for labels in self.labels.values():
            n = sum(1 for pp in labels["pain_points"] if pp["label"] in user)
            if n > hits:
                best, hits = labels, n
        return best
