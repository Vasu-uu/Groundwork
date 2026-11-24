"""A scripted stand-in for the LLM that answers like a perfect analyst would.

It reads the hand-labelled ground truth (samples/*/labels.json) plus the
per-interview stances below, and replies to each prompt type in the expected
JSON shape. That lets the whole pipeline run end to end without a model.
"""

from __future__ import annotations

import json
import re

from app.llm.base import GenerationOptions, Message
from app.llm.mock import MockProvider
from app.services.samples import load_labels

# Per-interview stances for the freelance set, with verbatim quotes.
FREELANCE_STANCES: dict[str, dict[str, tuple[str, list[str], list[str]]]] = {
    "H1": {
        "I-01": ("supports", ["I hate chasing people for money."], []),
        "I-02": ("supports", ["Chasing late invoices eats a couple of hours every month, and it's the part of the job I dread most."], []),
        "I-03": ("supports", ["I've had to chase one client for six weeks and I ended up texting the CEO directly, which felt awful."], []),
        "I-04": ("supports", ['Said chasing corporate invoices is "a second unpaid job" and he puts it off for weeks because it feels awkward.'], []),
        "I-05": ("contradicts", [], ["Maybe once a year an agency is late and one email fixes it."]),
        "I-06": ("supports", ["I have to chase almost every single one, and some I just give up on because chasing a 300 euro invoice for weeks isn't worth the stress."], []),
    },
    "H2": {
        "I-01": ("supports", ["If it actually got me paid faster and didn't damage the relationship, yes, I'd pay ten or fifteen euros a month without thinking."], []),
        "I-02": ("mixed", ["Maybe. I'd want to try it free first."], ["I'm not sure reminders alone fix the accounts payable black hole."]),
        "I-03": ("contradicts", [], ["My tool already sends reminders and I wouldn't pay extra for that."]),
        "I-04": ("mixed", [], ['Was lukewarm on paying for a reminder tool: "the reminder isn\'t the problem, the PO process is."']),
        "I-05": ("contradicts", [], ["No, I wouldn't use them."]),
        "I-06": ("supports", ["Yes, honestly, I would pay for that today."], []),
    },
    "H3": {
        "I-01": ("contradicts", [], ["I have a template in my invoicing app, so that part takes maybe five minutes."]),
        "I-02": ("contradicts", [], ["Creating it? Two minutes."]),
        "I-03": ("contradicts", [], ["I use a free invoicing tool, the invoice itself is quick."]),
        "I-04": ("contradicts", [], ["Invoices themselves take him a few minutes, he did not see that as a problem."]),
        "I-05": ("contradicts", [], ["The agencies often generate the purchase order and I just copy the numbers into my template."]),
        "I-06": ("contradicts", [], ["Making the invoice is fast, I use a template."]),
    },
}  # fmt: skip

_INTERVIEW = re.compile(r"^Interview (\S+) \(participant", re.MULTILINE)
_PAIN_LINE = re.compile(r"^\[(?P<id>[^\]]+)\] (?P<summary>.*?) \| ", re.MULTILINE)
_HYP = re.compile(r"^(H\d+): ", re.MULTILINE)


def _segment_of(text: str, quote: str) -> int:
    """Find the [S..] line containing the quote (prompt view), default 1."""
    for line in text.splitlines():
        m = re.match(r"\[S(\d+)\]", line)
        if m and quote[:30] in line:
            return int(m.group(1))
    return 1


class OracleProvider(MockProvider):
    """Answers extraction, clustering and assessment prompts from ground truth."""

    def __init__(self, set_id: str, stances: dict | None = None) -> None:
        self.labels = load_labels(set_id)
        self.stances = stances if stances is not None else {}
        super().__init__(self._respond)

    def _respond(self, messages: list[Message], options: GenerationOptions) -> str:
        system, user = messages[0].content, messages[-1].content
        if "THEMES" in system:
            return self._cluster(user)
        if "skeptical" in system:
            return self._assess(user)
        return self._extract(user)

    def _extract(self, user: str) -> str:
        iid = _INTERVIEW.search(user).group(1)  # type: ignore[union-attr]
        items = [
            {"segment": _segment_of(user, q["quote"]), "quote": q["quote"], "summary": pp["label"], "intensity": "high"}
            for pp in self.labels["pain_points"]
            for q in pp["quotes"]
            if q["interview"] == iid and q["quote"][:30] in user
        ]  # fmt: skip
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

    def _assess(self, user: str) -> str:
        iid = _INTERVIEW.search(user).group(1)  # type: ignore[union-attr]
        out = []
        for hid in _HYP.findall(user):
            stance, sup, con = self.stances.get(hid, {}).get(iid, ("not_discussed", [], []))
            out.append(
                {
                    "hypothesis_id": hid,
                    "stance": stance,
                    "rationale": f"{iid} {stance}",
                    "supporting": [{"segment": _segment_of(user, q), "quote": q} for q in sup],
                    "contradicting": [{"segment": _segment_of(user, q), "quote": q} for q in con],
                }
            )
        return json.dumps({"assessments": out})
