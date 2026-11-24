from app.llm.demo import DemoProvider
from app.services.analysis import run_analysis
from app.services.samples import load_labels, load_sample_set
from evals.harness import score, to_markdown


async def scored(set_id: str):
    sample = load_sample_set(set_id)
    result = await run_analysis(sample.corpus, sample.hypotheses, DemoProvider())
    return score(sample, load_labels(set_id), result)


async def test_demo_replay_reproduces_the_labels():
    s = await scored("physio-no-shows")
    assert s.verification_rate == 1.0
    assert s.pain_recall == 1.0 and s.pain_quotes_labelled == 11
    assert s.stance_agreement == 1.0
    assert [(h.hypothesis_id, h.predicted) for h in s.hypotheses] == [
        ("H1", "VALIDATED"), ("H2", "MIXED"), ("H3", "INVALIDATED"), ("H4", "UNTESTED"),
    ]  # fmt: skip


async def test_harness_reports_rule_vs_label_disagreement():
    # Two of three interviewees support restaurant H3: the hand label says VALIDATED,
    # the verdict rule needs 75% agreement and says MIXED. The harness must show it.
    s = await scored("restaurant-waste")
    h3 = next(h for h in s.hypotheses if h.hypothesis_id == "H3")
    assert (h3.expected, h3.predicted, h3.agrees) == ("VALIDATED", "MIXED", False)
    report = to_markdown([s], provider="demo", model="replay", when="now")
    assert "| H3 | VALIDATED | MIXED ✗ | 3/3 |" in report
    assert "verdict agreement 2/3" in report


async def test_unknown_interviews_get_empty_demo_answers():
    sample = load_sample_set("freelance-invoicing")
    renamed = sample.corpus.model_copy(
        update={
            "transcripts": [
                t.model_copy(update={"id": f"X-{i}"})
                for i, t in enumerate(sample.corpus.transcripts)
            ]
        }
    )
    result = await run_analysis(renamed, sample.hypotheses, DemoProvider())
    assert result.pain_points == []
    assert {v.verdict.value for v in result.verdicts} == {"UNTESTED"}
