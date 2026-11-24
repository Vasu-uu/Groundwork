"""Deleting studies, and the explicit failure when every model answer is unusable."""

from sqlalchemy import func, select

from app.db.models import DecisionLogRow, LLMCallRow, ReviewRow, ScriptRow
from app.llm.mock import MockProvider
from tests.fakes import FREELANCE_STANCES, OracleProvider
from tests.test_api_script import approve_all
from tests.test_api_studies import analyzed_sample, error_code, make_client


def test_delete_study_removes_all_its_data():
    with make_client(OracleProvider("freelance-invoicing", FREELANCE_STANCES)) as client:
        sid = analyzed_sample(client)
        approve_all(client, sid)
        client.post(f"/api/studies/{sid}/script").raise_for_status()

        assert client.delete(f"/api/studies/{sid}").status_code == 204
        assert error_code(client.get(f"/api/studies/{sid}")) == "not_found"
        with client.app.state.session_factory() as db:
            for table in (ReviewRow, DecisionLogRow, LLMCallRow, ScriptRow):
                assert db.scalar(select(func.count()).select_from(table)) == 0, table


def test_unusable_output_everywhere_is_a_failure_not_empty_results():
    with make_client(MockProvider(lambda messages, options: "I cannot help with that.")) as client:
        sid = client.post("/api/studies/from-sample/freelance-invoicing").json()["id"]
        client.post(f"/api/studies/{sid}/analyze")
        status = client.get(f"/api/studies/{sid}/status").json()
        assert status["status"] == "failed"
        assert status["error_kind"] == "model_output"
        assert "every interview" in status["error"]
