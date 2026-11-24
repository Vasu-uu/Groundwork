import pytest

from app.models.evidence import MatchType
from app.models.transcript import SpeakerRole
from app.services.segmentation import segment_transcript
from app.services.verification import normalize, to_evidence, verify_quote

RAW = """Interviewer: What happens when an invoice is late?
Maya: I hate chasing people for money. It feels like I’m begging for something I already earned.
Interviewer: How late was the worst one?
Maya: An agency paid me 74 days after the invoice. I would never work with them again.
Interviewer: Would you pay for a tool?
Maya: I wouldn't pay for reminders alone, because my app already sends them for free."""


@pytest.fixture(scope="module")
def t():
    return segment_transcript(RAW, transcript_id="I-01")


def check_span(t, m, expected_text):
    assert t.text[m.start : m.end] == expected_text
    seg = t.segment(m.segment)
    assert seg.start <= m.start and m.end <= seg.end + 1


def test_normalize_unifies_quotes_dashes_case_and_space():
    assert normalize("  I’m  “TIRED” — really… ") == 'i\'m "tired" - really...'


def test_exact_match_ignores_quote_style_case_and_spacing(t):
    m = verify_quote(t, '  "it feels like I\'m   begging for something I already earned." ')
    assert m.status is MatchType.EXACT
    assert m.segment == 2
    check_span(t, m, "It feels like I’m begging for something I already earned.")


def test_wrong_claimed_segment_is_corrected(t):
    m = verify_quote(t, "An agency paid me 74 days after the invoice.", claimed_segment=2)
    assert m.status is MatchType.EXACT
    assert m.segment == 4


def test_fuzzy_match_tolerates_small_wording_drift(t):
    m = verify_quote(t, "It feels like I am begging for something I have already earned.")
    assert m.status is MatchType.FUZZY
    assert m.score >= 0.92
    check_span(t, m, "It feels like I’m begging for something I already earned.")


def test_paraphrase_is_rejected(t):
    m = verify_quote(t, "Chasing clients for payment makes me feel like a beggar.")
    assert m.status is MatchType.UNVERIFIED
    assert m.score < 0.92
    assert "not found" in m.reason


def test_changed_number_or_negation_is_rejected_even_if_similar(t):
    number = verify_quote(t, "An agency paid me 47 days after the invoice.")
    assert number.status is MatchType.UNVERIFIED
    assert "number or a negation" in number.reason
    negation = verify_quote(
        t, "I would pay for reminders alone, because my app already sends them for free."
    )
    assert negation.status is MatchType.UNVERIFIED


def test_contractions_count_as_the_same_negation(t):
    m = verify_quote(
        t, "I would not pay for reminders alone, because my app already sends them for free."
    )
    assert m.status is MatchType.FUZZY


def test_elided_quote_matches_original_span(t):
    m = verify_quote(t, "I hate chasing people ... begging for something I already earned")
    assert m.status is MatchType.EXACT
    assert t.text[m.start : m.end].startswith("I hate chasing people")
    assert t.text[m.start : m.end].endswith("already earned")


def test_too_short_quotes_are_not_evidence(t):
    assert verify_quote(t, "Never.").status is MatchType.UNVERIFIED


def test_quote_spanning_two_segments_of_one_turn():
    long = "Maya: " + " ".join(f"Sentence number {i} is here." for i in range(30))
    t = segment_transcript("Interviewer: Go on?\n" + long, max_segment_chars=100)
    quote = "Sentence number 5 is here. Sentence number 6 is here."
    m = verify_quote(t, quote)
    assert m.status is MatchType.EXACT
    assert t.text[m.start : m.end] == quote


def test_to_evidence_uses_transcript_text_and_role(t):
    m = verify_quote(t, "it feels like i am begging for something i have already earned")
    ev = to_evidence(t, m)
    assert ev.quote == t.text[ev.start : ev.end]
    assert ev.speaker == "Maya" and ev.role is SpeakerRole.INTERVIEWEE
    assert not ev.paraphrase
    with pytest.raises(ValueError):
        to_evidence(t, verify_quote(t, "completely made up sentence here"))
