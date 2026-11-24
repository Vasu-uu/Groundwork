"""End-to-end pipeline on the sample sets, driven by a ground-truth oracle model."""

import pytest

from app.llm import ProviderUnavailableError, UsageTracker
from app.llm.mock import MockProvider
from app.models.analysis import Confidence, VerdictLabel
from app.models.hypothesis import Hypothesis
from app.services.analysis import AnalysisInputError, run_analysis
from app.services.corpus import build_corpus
from app.services.samples import load_labels, load_sample_set
from tests.fakes import FREELANCE_STANCES, OracleProvider


async def test_freelance_pipeline_reproduces_hand_labels():
    sample = load_sample_set("freelance-invoicing")
    labels = load_labels("freelance-invoicing")
    tracker = UsageTracker("e2e")
    steps: list[str] = []
    result = await run_analysis(
        sample.corpus,
        sample.hypotheses,
        OracleProvider("freelance-invoicing", FREELANCE_STANCES),
        tracker=tracker,
        run_id="e2e",
        on_progress=steps.append,
    )

    assert steps == ["extracting", "clustering", "assessing", "deciding", "done"]
    verdicts = {v.hypothesis.id: v for v in result.verdicts}
    expected = {h: labels["verdicts"][h]["verdict"] for h in labels["verdicts"]}
    assert {h: v.verdict.value for h, v in verdicts.items()} == expected

    h1 = verdicts["H1"]
    assert (h1.counts.supports, h1.counts.contradicts) == (5, 1)
    assert h1.confidence is Confidence.MEDIUM
    assert h1.counter_evidence[0].interview_id == "I-05"
    assert all(e.quote in sample.corpus.get(e.interview_id).text for e in h1.supporting)
    assert h1.related_theme_ids  # cites the same segments as the chasing theme

    top = result.clustering.themes[0]
    assert top.label == "Chasing late payments is stressful and awkward"
    assert top.frequency == 4  # labels name I-04 too, but give no quote for it
    assert result.quote_stats.rate == 1.0
    assert result.prompt_ids == [
        "assess_hypotheses.v1",
        "cluster_pain_points.v1",
        "extract_pain_points.v1",
    ]
    assert tracker.summary().calls == 6 + 1 + 6
    assert all(v.status == "ai_suggestion" for v in result.verdicts)


async def test_small_sample_is_provisional_everywhere():
    sample = load_sample_set("restaurant-waste")
    result = await run_analysis(
        sample.corpus, sample.hypotheses, OracleProvider("restaurant-waste")
    )
    assert any("provisional" in w for w in result.warnings)
    assert all(v.provisional and v.confidence is Confidence.LOW for v in result.verdicts)
    # No stances scripted for this set: everything is honestly UNTESTED.
    assert {v.verdict for v in result.verdicts} == {VerdictLabel.UNTESTED}


async def test_input_validation():
    sample = load_sample_set("freelance-invoicing")
    with pytest.raises(AnalysisInputError, match="hypothesis"):
        await run_analysis(sample.corpus, [], MockProvider([]))
    with pytest.raises(AnalysisInputError, match="unique"):
        dup = [Hypothesis(id="H1", text="abc"), Hypothesis(id="H1", text="def")]
        await run_analysis(sample.corpus, dup, MockProvider([]))
    with pytest.raises(AnalysisInputError, match="interview"):
        await run_analysis(build_corpus([]), sample.hypotheses, MockProvider([]))


async def test_provider_failure_aborts_cleanly():
    class Down(MockProvider):
        async def generate(self, messages, options=None):
            raise ProviderUnavailableError("down")

    sample = load_sample_set("freelance-invoicing")
    with pytest.raises(ProviderUnavailableError):
        await run_analysis(sample.corpus, sample.hypotheses, Down())
