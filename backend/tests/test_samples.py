"""The bundled sample sets are parseable and their labels are trustworthy."""

import re

import pytest

from app.models.transcript import SpeakerRole
from app.services.corpus import build_corpus
from app.services.samples import list_sample_sets, load_labels, load_sample_set
from app.services.segmentation import segment_transcript

SET_IDS = [s.id for s in list_sample_sets()]
VERDICTS = {"VALIDATED", "INVALIDATED", "UNTESTED", "MIXED"}


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_three_sample_sets_exist():
    assert set(SET_IDS) == {"freelance-invoicing", "physio-no-shows", "restaurant-waste"}


@pytest.mark.parametrize("set_id", SET_IDS)
def test_every_interview_parses_with_customer_speech(set_id):
    sample = load_sample_set(set_id)
    for t in sample.corpus.transcripts:
        assert t.evidence_segments, t.id
        assert t.participant, t.id
        if t.format == "dialogue":
            assert any(s.role is SpeakerRole.INTERVIEWER for s in t.speakers), t.id
    ids = [t.id for t in sample.corpus.transcripts]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("set_id", SET_IDS)
def test_label_quotes_are_verbatim_and_inside_one_customer_segment(set_id):
    sample = load_sample_set(set_id)
    labels = load_labels(set_id)
    for pp in labels["pain_points"]:
        for q in pp["quotes"]:
            t = sample.corpus.get(q["interview"])
            assert t is not None, q
            hits = [s for s in t.evidence_segments if squash(q["quote"]) in squash(s.text)]
            assert hits, f"{set_id}/{q['interview']}: quote not found: {q['quote']!r}"
            assert q["interview"] in pp["interviews"]


@pytest.mark.parametrize("set_id", SET_IDS)
def test_every_hypothesis_has_an_expected_verdict(set_id):
    sample = load_sample_set(set_id)
    verdicts = load_labels(set_id)["verdicts"]
    assert set(verdicts) == {h.id for h in sample.hypotheses}
    assert {v["verdict"] for v in verdicts.values()} <= VERDICTS


def test_small_sample_warning_only_for_small_set():
    small = load_sample_set("restaurant-waste").corpus
    assert small.small_sample
    assert any("provisional" in w for w in small.warnings)
    big = load_sample_set("freelance-invoicing").corpus
    assert not big.small_sample
    assert not any("provisional" in w for w in big.warnings)
    assert any("founder notes" in w for w in big.warnings)


def test_duplicate_ids_are_renamed():
    t = segment_transcript("Interviewer: Hi?\nMaya: Hello there.", transcript_id="I-01")
    corpus = build_corpus([t, t])
    assert [x.id for x in corpus.transcripts] == ["I-01", "I-01-2"]
    assert any("Duplicate" in w for w in corpus.warnings)
