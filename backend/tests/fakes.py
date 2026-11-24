"""Test doubles built on the demo provider (hand-labelled answers, no model)."""

from __future__ import annotations

from typing import Any

from app.llm.demo import DemoProvider
from app.services.samples import load_labels

Stances = dict[str, dict[str, tuple[str, list[str], list[str]]]]


def labelled_stances(set_id: str) -> Stances:
    """The hand-labelled per-interview stances of a sample set."""
    return {
        hid: {iid: (e["stance"], e["supporting"], e["contradicting"]) for iid, e in per.items()}
        for hid, per in load_labels(set_id)["stances"].items()
    }


FREELANCE_STANCES = labelled_stances("freelance-invoicing")


class OracleProvider(DemoProvider):
    """The demo provider limited to one sample set, with test-controlled stances.

    `stances=None` means every hypothesis is "not discussed", which some tests
    rely on; pass `FREELANCE_STANCES` (or the set's labelled stances) to get
    a full analysis.
    """

    def __init__(self, set_id: str, stances: dict | None = None) -> None:
        super().__init__(set_ids=[set_id])
        self.name = "mock"
        self.model = "mock"
        self.test_stances = stances or {}

    def stance_of(self, labels: dict[str, Any] | None, hid: str, iid: str) -> dict[str, Any]:
        stance, sup, con = self.test_stances.get(hid, {}).get(iid, ("not_discussed", [], []))
        return {"stance": stance, "supporting": sup, "contradicting": con}
