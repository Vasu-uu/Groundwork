from app.models.transcript import SpeakerRole, Transcript
from app.services.segmentation import chunk_segments, segment_transcript


def assert_offsets_consistent(t: Transcript) -> None:
    for i, seg in enumerate(t.segments, start=1):
        assert seg.number == i
        assert t.text[seg.start : seg.end] == seg.text
        assert seg.text == seg.text.strip()


def roles(t: Transcript) -> dict[str, SpeakerRole]:
    return {s.label: s.role for s in t.speakers}


def test_markdown_bold_labels_with_front_matter():
    raw = (
        "---\nid: I-07\nparticipant: Maya Lopez\ndate: 2026-10-02\n---\n\n"
        "# Interview\n\n"
        "**Interviewer:** How do you get paid?\n\n"
        "**Maya:** Bank transfer.\nUsually late, sometimes very late.\n\n"
        "**Interviewer**: Why?\n\n"
        "**Maya**: Accounts payable."
    )
    t = segment_transcript(raw, source_filename="whatever.md")
    assert t.id == "I-07"
    assert t.participant == "Maya Lopez"
    assert t.metadata["date"] == "2026-10-02"
    assert t.format == "dialogue"
    assert [s.speaker for s in t.segments] == ["Interviewer", "Maya", "Interviewer", "Maya"]
    # A continuation line stays in the same turn.
    assert t.segments[1].text == "Bank transfer.\nUsually late, sometimes very late."
    assert roles(t) == {"Interviewer": SpeakerRole.INTERVIEWER, "Maya": SpeakerRole.INTERVIEWEE}
    assert [s.speaker for s in t.evidence_segments] == ["Maya", "Maya"]
    assert_offsets_consistent(t)


def test_timestamps_before_and_after_label():
    raw = (
        "[00:00:04] Interviewer: Hello?\n"
        "[00:00:09] Tomas: Hi there.\n"
        "Interviewer (00:01:10): Next question?\n"
        "Tomas (00:01:15): Sure."
    )
    t = segment_transcript(raw)
    assert [s.text for s in t.segments] == ["Hello?", "Hi there.", "Next question?", "Sure."]
    assert_offsets_consistent(t)


def test_q_and_a_labels():
    t = segment_transcript("Q: What hurts?\n\nA: Chasing money.\n\nQ: Why?\n\nA: It's awkward.")
    assert roles(t) == {"Q": SpeakerRole.INTERVIEWER, "A": SpeakerRole.INTERVIEWEE}


def test_single_use_colon_line_is_not_a_new_speaker():
    raw = (
        "Interviewer: What would you pay?\n"
        "Sofia: Not much.\n"
        "Budget: about 50 euros a year, honestly.\n"
        "Interviewer: Okay."
    )
    t = segment_transcript(raw)
    assert [s.speaker for s in t.segments] == ["Interviewer", "Sofia", "Interviewer"]
    assert "Budget: about 50 euros" in t.segments[1].text
    assert "https" not in {s.label for s in t.speakers}


def test_interviewer_guessed_from_questions_when_unlabelled():
    raw = (
        "Sam: How do you get paid?\nLea: Bank transfer.\n"
        "Sam: Is it late?\nLea: Always late.\n"
        "Sam: Why?\nLea: Startups delay freelancers first."
    )
    t = segment_transcript(raw)
    assert roles(t) == {"Sam": SpeakerRole.INTERVIEWER, "Lea": SpeakerRole.INTERVIEWEE}
    assert any("guessed" in w for w in t.warnings)


def test_metadata_interviewer_overrides_heuristic():
    raw = "---\ninterviewer: Lea\n---\nSam: Hi.\nLea: Hello.\nSam: Bye.\nLea: Bye?"
    t = segment_transcript(raw)
    assert roles(t)["Lea"] is SpeakerRole.INTERVIEWER
    assert roles(t)["Sam"] is SpeakerRole.INTERVIEWEE


def test_notes_without_labels_are_flagged_as_paraphrase():
    raw = (
        "---\nparticipant: Jonas\n---\n# Notes\n"
        "- Corporate clients pay late.\n- Uses a spreadsheet.\n\n"
        "General feeling: frustrated."
    )
    t = segment_transcript(raw)
    assert t.format == "notes"
    assert [s.text for s in t.segments] == [
        "Corporate clients pay late.",
        "Uses a spreadsheet.",
        "General feeling: frustrated.",
    ]
    assert all(s.role is SpeakerRole.NOTE for s in t.segments)
    assert t.evidence_segments  # notes are usable, but flagged
    assert any("paraphrase" in w for w in t.warnings)
    assert_offsets_consistent(t)


def test_long_turn_is_split_at_sentence_boundaries():
    sentence = "This is a sentence about late invoices and cash flow. "
    raw = "Interviewer: Tell me more?\nMaya: " + sentence * 20
    t = segment_transcript(raw, max_segment_chars=120)
    maya = [s for s in t.segments if s.speaker == "Maya"]
    assert len(maya) > 1
    assert {s.turn for s in maya} == {2}
    assert all(len(s.text) <= 120 for s in maya)
    assert all(s.text.endswith(".") for s in maya)
    assert_offsets_consistent(t)


def test_id_falls_back_to_filename_and_warns_on_thin_text():
    t = segment_transcript("Interviewer: Hi?\nBo: Fine.", source_filename="Call 3 - Bo.txt")
    assert t.id == "call-3-bo"
    assert any("Very little customer speech" in w for w in t.warnings)


def test_chunking_never_splits_segments():
    raw = "\n".join(f"Interviewer: Question {i}?\nMaya: {'word ' * 30}" for i in range(20))
    t = segment_transcript(raw)
    chunks = chunk_segments(t.segments, max_chars=500)
    assert len(chunks) > 1
    assert [s for c in chunks for s in c] == t.segments
    assert all(sum(len(s.text) for s in c) <= 500 for c in chunks if len(c) > 1)
