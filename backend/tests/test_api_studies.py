"""HTTP-level tests of the studies API and the human checkpoint.

TestClient runs background tasks before returning, so an analysis started with
POST /analyze has finished by the time the next request is made.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.models import StudyRow
from app.db.session import init_db, make_engine
from app.llm import ProviderUnavailableError
from app.llm.mock import MockProvider
from app.main import create_app
from app.services.studies import StudyStatus, recover_interrupted
from tests.fakes import FREELANCE_STANCES, OracleProvider


def make_client(provider) -> TestClient:
    settings = Settings(_env_file=None, llm_provider="mock", database_url="sqlite://")
    return TestClient(create_app(settings=settings, provider=provider))


@pytest.fixture
def client():
    with make_client(OracleProvider("freelance-invoicing", FREELANCE_STANCES)) as c:
        yield c


def error_code(resp) -> str:
    return resp.json()["error"]["code"]


def analyzed_sample(client: TestClient, set_id: str = "freelance-invoicing") -> str:
    sid = client.post(f"/api/studies/from-sample/{set_id}").json()["id"]
    assert client.post(f"/api/studies/{sid}/analyze").status_code == 202
    assert client.get(f"/api/studies/{sid}/status").json()["status"] == "awaiting_review"
    return sid


def test_full_flow_through_the_human_checkpoint(client):
    created = client.post("/api/studies/from-sample/freelance-invoicing")
    assert created.status_code == 201
    study = created.json()
    sid = study["id"]
    assert study["status"] == "draft"
    assert len(study["interviews"]) == 6 and len(study["hypotheses"]) == 4

    # Downstream data is gated before any analysis.
    gated = client.get(f"/api/studies/{sid}/decisions")
    assert gated.status_code == 409 and error_code(gated) == "checkpoint_required"

    assert client.post(f"/api/studies/{sid}/analyze").status_code == 202
    status = client.get(f"/api/studies/{sid}/status").json()
    assert status["status"] == "awaiting_review"
    assert status["usage"]["calls"] == 13
    assert status["cost_label"].startswith("0 EUR, ")

    study = client.get(f"/api/studies/{sid}").json()
    verdicts = {v["hypothesis"]["id"]: v for v in study["result"]["verdicts"]}
    assert verdicts["H1"]["verdict"] == "VALIDATED"
    assert verdicts["H1"]["status"] == "ai_suggestion"
    assert verdicts["H1"]["counter_evidence"][0]["interview_id"] == "I-05"
    assert study["checkpoint"] == {
        "total": 4, "reviewed": 0, "missing": ["H1", "H2", "H3", "H4"],
        "approved": False, "can_approve": False, "needs_small_sample_ack": False,
    }  # fmt: skip

    # Approving before every verdict is reviewed is refused server-side.
    early = client.post(f"/api/studies/{sid}/approve", json={})
    assert early.status_code == 409 and error_code(early) == "checkpoint_required"

    # Approve H1, removing one quote: the server shows the recomputed AI verdict.
    removed = verdicts["H1"]["supporting"][0]["key"]
    r = client.put(
        f"/api/studies/{sid}/reviews/H1",
        json={"decision": "approve", "removed_evidence": [removed], "note": "solid"},
    )
    assert r.status_code == 200
    review = r.json()["reviews"]["H1"]
    assert review["final_verdict"] == "VALIDATED"
    assert review["recomputed_ai_verdict"] == "VALIDATED"  # 4 of 5 still support

    # Changing a verdict requires a reason.
    no_reason = client.put(
        f"/api/studies/{sid}/reviews/H2", json={"decision": "change", "verdict": "VALIDATED"}
    )
    assert no_reason.status_code == 422
    same = client.put(
        f"/api/studies/{sid}/reviews/H2",
        json={"decision": "change", "verdict": "MIXED", "reasoning": "same as AI"},
    )
    assert same.status_code == 422
    client.put(
        f"/api/studies/{sid}/reviews/H2",
        json={"decision": "change", "verdict": "INVALIDATED", "reasoning": "Free tools exist."},
    ).raise_for_status()
    client.put(
        f"/api/studies/{sid}/reviews/H3",
        json={"decision": "reject", "reasoning": "Asked as a leading question."},
    ).raise_for_status()
    bad_key = client.put(
        f"/api/studies/{sid}/reviews/H4",
        json={"decision": "approve", "removed_evidence": ["I-01:0:1"]},
    )
    assert bad_key.status_code == 422
    last = client.put(f"/api/studies/{sid}/reviews/H4", json={"decision": "approve"}).json()
    assert last["checkpoint"]["can_approve"] is True

    approved = client.post(f"/api/studies/{sid}/approve", json={})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    decisions = {d["hypothesis_id"]: d for d in client.get(f"/api/studies/{sid}/decisions").json()}
    assert decisions["H2"]["final_verdict"] == "INVALIDATED"
    assert decisions["H3"]["final_verdict"] is None and decisions["H3"]["decision"] == "reject"
    assert removed not in {e["key"] for e in decisions["H1"]["supporting"]}

    # Approved studies are locked until reopened.
    locked = client.put(f"/api/studies/{sid}/reviews/H4", json={"decision": "approve"})
    assert locked.status_code == 409 and error_code(locked) == "locked"
    paste = client.post(f"/api/studies/{sid}/interviews/text", json={"text": "Q: hi?\nA: hello"})
    assert paste.status_code == 409
    assert (
        client.post(f"/api/studies/{sid}/reopen", json={"reason": "new info"}).json()["status"]
        == "awaiting_review"
    )

    log = client.get(f"/api/studies/{sid}/decision-log").json()
    actions = [e["action"] for e in log]
    assert actions[:3] == ["study_created", "analysis_started", "analysis_completed"]
    assert actions.count("review_saved") == 4
    assert actions[-2:] == ["approved", "reopened"]
    h2 = next(e for e in log if e["action"] == "review_saved" and e["hypothesis_id"] == "H2")
    assert h2["actor"] == "founder"
    assert h2["details"]["ai_suggestion"] == "MIXED"
    assert h2["details"]["after"]["final_verdict"] == "INVALIDATED"
    assert all(e["at"] for e in log)


def test_model_unreachable_is_an_explicit_failure_state():
    class Down(MockProvider):
        async def generate(self, messages, options=None):
            raise ProviderUnavailableError("Cannot reach Ollama at http://localhost:11434.")

    with make_client(Down()) as client:
        sid = client.post("/api/studies/from-sample/freelance-invoicing").json()["id"]
        client.post(f"/api/studies/{sid}/analyze")
        status = client.get(f"/api/studies/{sid}/status").json()
        assert status["status"] == "failed"
        assert status["error_kind"] == "provider_unavailable"
        assert "Cannot reach Ollama" in status["error"]
        assert status["usage"]["failed_calls"] == 1
        # A failed study can be analysed again.
        assert client.post(f"/api/studies/{sid}/analyze").status_code == 202


def test_analysis_needs_hypotheses_and_interviews(client):
    sid = client.post("/api/studies", json={"name": "Empty"}).json()["id"]
    resp = client.post(f"/api/studies/{sid}/analyze")
    assert resp.status_code == 422 and error_code(resp) == "invalid_input"
    dup = client.post("/api/studies", json={"hypotheses": ["Same thing", "same  thing"]})
    assert dup.status_code == 422


def test_upload_paste_view_and_delete_interviews(client):
    sid = client.post(
        "/api/studies", json={"name": "Mine", "hypotheses": ["Late invoices hurt"]}
    ).json()["id"]
    call = b"Interviewer: How is it?\nMaya: Chasing invoices is awful."
    files = [
        ("files", ("call-1.txt", call, "text/plain")),
        ("files", ("voice.mp3", b"ID3", "audio/mpeg")),
        ("files", ("blank.md", b"   \n", "text/markdown")),
    ]  # fmt: skip
    up = client.post(f"/api/studies/{sid}/interviews", files=files).json()
    assert [a["id"] for a in up["added"]] == ["call-1"]
    assert {e["filename"] for e in up["errors"]} == {"voice.mp3", "blank.md"}

    pasted = client.post(
        f"/api/studies/{sid}/interviews/text",
        json={"title": "call-1", "text": "Interviewer: And you?\nTom: Same problem here."},
    ).json()
    assert pasted["added"][0]["id"] == "call-1-2"  # duplicate IDs are made unique

    t = client.get(f"/api/studies/{sid}/interviews/call-1").json()
    seg = t["segments"][1]
    assert t["text"][seg["start"] : seg["end"]] == "Chasing invoices is awful."

    study = client.get(f"/api/studies/{sid}").json()
    assert study["small_sample"] is True
    assert any("provisional" in w for w in study["corpus_warnings"])

    assert client.delete(f"/api/studies/{sid}/interviews/call-1").status_code == 204
    assert client.get(f"/api/studies/{sid}/interviews/call-1").status_code == 404


def test_changing_inputs_after_analysis_clears_the_review(client):
    sid = analyzed_sample(client)
    client.put(f"/api/studies/{sid}/reviews/H1", json={"decision": "approve"}).raise_for_status()
    study = client.put(
        f"/api/studies/{sid}/hypotheses", json={"hypotheses": ["Something new to test"]}
    ).json()
    assert study["status"] == "draft"
    assert study["result"] is None and study["reviews"] == {}
    log = client.get(f"/api/studies/{sid}/decision-log").json()
    assert log[-2]["action"] == "analysis_reset"


def test_small_sample_approval_needs_explicit_acknowledgement():
    with make_client(OracleProvider("restaurant-waste")) as client:
        sid = analyzed_sample(client, "restaurant-waste")
        for hid in ("H1", "H2", "H3"):
            client.put(f"/api/studies/{sid}/reviews/{hid}", json={"decision": "approve"})
        refused = client.post(f"/api/studies/{sid}/approve", json={})
        assert refused.status_code == 409
        assert error_code(refused) == "small_sample_ack_required"
        ok = client.post(f"/api/studies/{sid}/approve", json={"acknowledge_small_sample": True})
        assert ok.json()["status"] == "approved"


def test_unknown_things_are_404(client):
    assert error_code(client.get("/api/studies/nope")) == "not_found"
    assert client.post("/api/studies/from-sample/nope").status_code == 404
    assert len(client.get("/api/samples").json()) == 3


def test_interrupted_runs_fail_on_startup():
    factory = init_db(make_engine("sqlite://"))
    with factory.begin() as db:
        db.add(StudyRow(id="s1", name="x", status=StudyStatus.ANALYZING.value))
    with factory.begin() as db:
        assert recover_interrupted(db) == 1
    with factory() as db:
        row = db.get(StudyRow, "s1")
        assert (row.status, row.error_kind) == ("failed", "interrupted")
