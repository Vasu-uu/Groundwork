"""Next interview script and report export, end to end through the API."""

from __future__ import annotations

from app.llm import ProviderUnavailableError
from tests.fakes import FREELANCE_STANCES, OracleProvider
from tests.test_api_studies import analyzed_sample, error_code, make_client


def approve_all(client, sid: str) -> None:
    client.put(f"/api/studies/{sid}/reviews/H1", json={"decision": "approve"}).raise_for_status()
    client.put(
        f"/api/studies/{sid}/reviews/H2",
        json={"decision": "change", "verdict": "VALIDATED", "reasoning": "Agencies pay late."},
    ).raise_for_status()
    client.put(
        f"/api/studies/{sid}/reviews/H3",
        json={"decision": "reject", "reasoning": "Asked as a leading question."},
    ).raise_for_status()
    client.put(f"/api/studies/{sid}/reviews/H4", json={"decision": "approve"}).raise_for_status()
    client.post(f"/api/studies/{sid}/approve", json={}).raise_for_status()


def test_script_and_export_are_gated_by_the_checkpoint():
    with make_client(OracleProvider("freelance-invoicing", FREELANCE_STANCES)) as client:
        sid = analyzed_sample(client)
        for method, path in [
            ("post", "script"),
            ("get", "script"),
            ("get", "report.md"),
            ("get", "report.pdf"),
        ]:
            r = getattr(client, method)(f"/api/studies/{sid}/{path}")
            assert r.status_code == 409 and error_code(r) == "checkpoint_required", path


def test_generate_edit_and_export():
    with make_client(OracleProvider("freelance-invoicing", FREELANCE_STANCES)) as client:
        sid = analyzed_sample(client)
        approve_all(client, sid)
        calls_before = client.get(f"/api/studies/{sid}").json()["usage"]["calls"]

        missing = client.get(f"/api/studies/{sid}/script")
        assert missing.status_code == 404 and error_code(missing) == "no_script"

        r = client.post(f"/api/studies/{sid}/script")
        assert r.status_code == 200
        script = r.json()
        targets = [t["id"] for t in script["targets"]]
        # H2 is now VALIDATED (founder's change), H3 was rejected, H4 is untested.
        assert [t for t in targets if t.startswith("H")] == ["H3", "H4"]
        assert any(t.startswith("T") for t in targets)
        assert script["questions"][0]["section"] == "warmup"
        assert all(q["bias_check"] for q in script["questions"])
        assert client.get(f"/api/studies/{sid}").json()["usage"]["calls"] == calls_before + 1

        # The founder rewrites one question into a leading one: the server flags it.
        edits = [{"id": q["id"], "question": q["question"]} for q in script["questions"]]
        edits[1]["question"] = "Don't you hate chasing invoices?"
        edits.append({"question": "What tools do you use for invoicing today?"})
        saved = client.put(f"/api/studies/{sid}/script", json={"questions": edits}).json()
        assert saved["questions"][1]["edited"] is True
        assert any("Leading" in i for i in saved["questions"][1]["lint"])
        assert saved["questions"][-1]["section"] == "custom"
        assert client.get(f"/api/studies/{sid}/script").json() == saved

        md = client.get(f"/api/studies/{sid}/report.md")
        assert md.status_code == 200
        assert md.headers["content-type"].startswith("text/markdown")
        assert 'filename="groundwork-freelancers' in md.headers["content-disposition"]
        text = md.text
        for heading in ("## Summary", "## Decisions and evidence", "## Pain themes",
                        "## Next interview script", "## Decision log", "## AI usage"):  # fmt: skip
            assert heading in text
        assert "H2 VALIDATED (AI suggested MIXED)" in text
        assert "H3 RE-TEST" in text
        assert "segment S" in text and "> — " in text  # quotes carry their location
        assert "Wording problem: Leading" in text
        assert "Cost: 0 EUR" in text and "draft_interview_script.v1" in text

        pdf = client.get(f"/api/studies/{sid}/report.pdf")
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")

        log = [e["action"] for e in client.get(f"/api/studies/{sid}/decision-log").json()]
        assert log[-2:] == ["script_generated", "script_edited"]

        # Reopening the review makes the script stale: it is discarded.
        client.post(f"/api/studies/{sid}/reopen", json={"reason": "new interview"})
        log = [e["action"] for e in client.get(f"/api/studies/{sid}/decision-log").json()]
        assert log[-1] == "script_discarded"
        client.post(f"/api/studies/{sid}/approve", json={}).raise_for_status()
        assert error_code(client.get(f"/api/studies/{sid}/script")) == "no_script"


def test_script_generation_reports_an_unreachable_model():
    oracle = OracleProvider("freelance-invoicing", FREELANCE_STANCES)
    with make_client(oracle) as client:
        sid = analyzed_sample(client)
        approve_all(client, sid)

        async def down(messages, options=None):
            raise ProviderUnavailableError("Cannot reach Ollama.")

        oracle.generate = down  # type: ignore[method-assign]
        r = client.post(f"/api/studies/{sid}/script")
        assert r.status_code == 503 and error_code(r) == "provider_unavailable"
        assert client.get(f"/api/studies/{sid}/script").status_code == 404
