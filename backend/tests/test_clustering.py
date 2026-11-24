import json

import pytest

from app.llm import UsageTracker
from app.llm.mock import MockProvider
from app.models.evidence import Evidence, MatchType, PainPoint
from app.models.transcript import SpeakerRole
from app.services.clustering import ClusterConfig, cluster_pain_points, fallback_groups


def pp(pid: str, interview: str, summary: str, intensity="medium", note=False) -> PainPoint:
    return PainPoint(
        id=pid,
        interview_id=interview,
        summary=summary,
        intensity=intensity,
        evidence=Evidence(
            interview_id=interview, segment=1, speaker="x",
            role=SpeakerRole.NOTE if note else SpeakerRole.INTERVIEWEE,
            quote=f"quote for {pid}", start=0, end=5, match=MatchType.EXACT, score=1.0,
        ),
    )  # fmt: skip


POINTS = [
    pp("I-01-P01", "I-01", "Chasing late payments is stressful", "high"),
    pp("I-01-P02", "I-01", "Chasing late payments takes hours"),
    pp("I-02-P01", "I-02", "Chasing late payments feels awkward"),
    pp("I-03-P01", "I-03", "VAT rules are confusing", "low"),
    pp("I-03-P02", "I-03", "Tracking invoices in spreadsheets"),
]


def themes_reply(*themes) -> str:
    return json.dumps(
        {
            "themes": [
                {"label": name, "description": name, "pain_point_ids": ids} for name, ids in themes
            ]
        }
    )


async def test_frequency_counts_distinct_interviewees_and_ids_are_policed():
    provider = MockProvider(
        [
            themes_reply(
                ("VAT confusion", ["I-03-P01"]),
                ("Chasing payments", ["[I-01-P01]", "I-01-P02", "I-02-P01", "I-09-P07"]),
                ("Duplicate", ["I-01-P01"]),
            )
        ]
    )
    result = await cluster_pain_points(POINTS, 4, provider, tracker=UsageTracker("r"))
    assert result.method == "llm"
    first = result.themes[0]
    assert (first.id, first.label) == ("T01", "Chasing payments")
    assert first.frequency == 2  # three pain points, but only two interviewees
    assert first.interview_ids == ["I-01", "I-02"]
    assert first.share == 0.5
    assert first.top_intensity == "high"
    assert [t.label for t in result.themes] == ["Chasing payments", "VAT confusion"]
    assert result.dropped_ids == ["I-09-P07", "I-01-P01"]
    assert result.unclustered == ["I-03-P02"]


async def test_multi_batch_runs_a_merge_step():
    provider = MockProvider(
        [
            themes_reply(("Chasing payments", ["I-01-P01", "I-01-P02"])),
            themes_reply(("Awkward follow-ups", ["I-02-P01"]), ("VAT", ["I-03-P01"])),
            themes_reply(("Tracking", ["I-03-P02"])),
            json.dumps(
                {"groups": [{"label": "Chasing late payments", "theme_ids": ["T1", "[T02]"]}]}
            ),
        ]
    )
    result = await cluster_pain_points(POINTS, 3, provider, config=ClusterConfig(batch_size=2))
    labels = {t.label: t for t in result.themes}
    assert labels["Chasing late payments"].pain_point_ids == ["I-01-P01", "I-01-P02", "I-02-P01"]
    assert "VAT" in labels and "Tracking" in labels  # untouched themes survive the merge
    assert len(provider.calls) == 4


async def test_invalid_output_falls_back_to_keyword_grouping():
    provider = MockProvider(["not json"] * 3)
    result = await cluster_pain_points(POINTS, 3, provider, config=ClusterConfig(max_retries=2))
    assert result.method == "fallback"
    assert result.notes
    chasing = next(t for t in result.themes if "I-02-P01" in t.pain_point_ids)
    assert set(chasing.pain_point_ids) == {"I-01-P01", "I-01-P02", "I-02-P01"}


def test_fallback_is_deterministic():
    assert [g.ids for g in fallback_groups(POINTS)] == [g.ids for g in fallback_groups(POINTS)]


@pytest.mark.parametrize("note", [True, False])
async def test_paraphrase_only_flag(note):
    points = [pp("I-01-P01", "I-01", "x", note=note)]
    provider = MockProvider([themes_reply(("x", ["I-01-P01"]))])
    result = await cluster_pain_points(points, 1, provider)
    assert result.themes[0].paraphrase_only is note


async def test_no_pain_points_means_no_call():
    provider = MockProvider([])
    assert (await cluster_pain_points([], 3, provider)).themes == []
    assert provider.calls == []
