from app.services.redaction import pseudonyms, redact_names
from app.services.segmentation import segment_transcript
from tests.fakes import OracleProvider
from tests.test_api_studies import make_client

DIALOGUE = """---
participant: Maya Lopez
interviewer: Sam
---
Sam: How do you get paid?
Maya Lopez: Mostly bank transfer. Maya is what clients call me, by the way.
Sam: And late payments?
Maya Lopez: I chase them, and my accountant Priya helps.
"""


def test_speaker_and_front_matter_names_are_replaced_everywhere():
    t = segment_transcript(DIALOGUE, source_filename="maya-lopez-call.txt")
    r = redact_names(t)
    assert "Maya" not in r.text and "Sam" not in r.text
    assert "Participant: I chase them" in r.text
    assert "Participant is what clients call me" in r.text  # first-name mention
    assert {s.label for s in r.speakers} == {"Interviewer", "Participant"}
    assert r.participant == "Participant" and r.title == "Interview with Participant"
    assert "maya" not in (r.source_filename or "").lower() and "maya" not in r.id
    # Offsets are recomputed on the redacted text, so quotes still verify.
    assert all(r.text[s.start : s.end] == s.text for s in r.segments)
    # Names that are not speakers are not detected, and the user is told so.
    assert "Priya" in r.text
    assert any("not detected" in w for w in r.warnings)


def test_generic_labels_are_left_alone():
    t = segment_transcript("Interviewer: Hi?\nCustomer: Hello there, nice to meet you.\n")
    assert pseudonyms(t) == {}
    assert redact_names(t) is t


def test_several_customers_get_numbered_labels():
    t = segment_transcript(
        "Q: Who runs it?\nAna: I do the books.\nBen: And I do sales.\n"
        "Q: Ok?\nAna: Yes.\nBen: Yes.\n"
    )
    assert pseudonyms(t) == {"Ana": "Participant 1", "Ben": "Participant 2"}


def test_api_redacts_on_request():
    with make_client(OracleProvider("freelance-invoicing")) as client:
        sid = client.post("/api/studies", json={"name": "x"}).json()["id"]
        r = client.post(
            f"/api/studies/{sid}/interviews/text", json={"text": DIALOGUE, "redact": True}
        ).json()
        iid = r["added"][0]["id"]
        assert "Maya" not in client.get(f"/api/studies/{sid}/interviews/{iid}").json()["text"]

        files = {"files": ("maya.txt", DIALOGUE.encode(), "text/plain")}
        up = client.post(f"/api/studies/{sid}/interviews?redact=true", files=files).json()
        assert up["added"][0]["participant"] == "Participant"
        kept = client.post(f"/api/studies/{sid}/interviews", files=files).json()
        assert kept["added"][0]["participant"] == "Maya Lopez"
