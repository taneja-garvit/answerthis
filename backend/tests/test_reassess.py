import uuid

import pytest
from sqlalchemy import func, select

from app.ai.base import LLMTimeoutError
from app.models import Assessment, Evidence
from app.papers.base import AbstractSection
from app.seed.demo import DRAFT_TEXT
from tests.fakes import HF_DOI, ScriptedLLM


async def _analyzed_claim(client) -> dict:
    project = (await client.post("/api/projects", json={"title": "Reassess"})).json()
    draft = (
        await client.post(
            f"/api/projects/{project['id']}/drafts", json={"original_text": DRAFT_TEXT}
        )
    ).json()
    body = (await client.post(f"/api/drafts/{draft['id']}/analyze")).json()
    return body["claims"][1]


async def test_reassess_appends_history_and_keeps_review(client, db_session):
    claim = await _analyzed_claim(client)
    await client.put(
        f"/api/claims/{claim['id']}/review", json={"decision": "QUALIFY", "reviewer_note": "n"}
    )
    evidence_before = await db_session.scalar(select(func.count()).select_from(Evidence))

    response = await client.post(f"/api/claims/{claim['id']}/assess")
    assert response.status_code == 200
    body = response.json()
    assert body["assessment"]["id"] != claim["assessment"]["id"]  # newest is current
    assert body["review"]["decision"] == "QUALIFY"  # human decision untouched
    history = (
        (
            await db_session.execute(
                select(Assessment.id).where(Assessment.claim_id == uuid.UUID(claim["id"]))
            )
        )
        .scalars()
        .all()
    )
    assert len(history) == 2  # appended, not overwritten
    # Same passages retrieved again: rows are reused, not duplicated.
    assert await db_session.scalar(select(func.count()).select_from(Evidence)) == evidence_before


async def test_changed_evidence_supersedes_old_rows_but_keeps_them(
    client, db_session, paper_providers
):
    claim = await _analyzed_claim(client)
    old_ids = {e["id"] for e in claim["evidence"]}
    replacement = "Mortality was lower with RPM, with an odds ratio of 0.81 versus usual care."
    for provider in paper_providers:
        record = provider.records[HF_DOI]
        provider.records[HF_DOI] = record.model_copy(
            update={
                "abstract": replacement,
                "abstract_sections": [AbstractSection(title="Results", text=replacement)],
            }
        )
    body = (
        await client.post(f"/api/claims/{claim['id']}/assess", json={"refresh_metadata": True})
    ).json()
    assert [e["passage"] for e in body["evidence"]] == [replacement]
    assert body["evidence"][0]["location"] == "Abstract — Results"
    stored = (
        await db_session.execute(
            select(Evidence.id, Evidence.is_current)
            .where(Evidence.claim_id == uuid.UUID(claim["id"]))
            .execution_options(populate_existing=True)
        )
    ).all()
    assert {str(i) for i, current in stored if not current} == old_ids  # kept for history


class TestReassessFailure:
    @pytest.fixture
    def llm(self):
        state = {"fail": False}

        def respond(request):
            if state["fail"]:
                return LLMTimeoutError("The AI provider timed out after 60s.")
            if request.task == "claim_extraction":
                return {
                    "claims": [
                        {"sentence_id": s["id"], "claim_text": s["text"]}
                        for s in request.payload["sentences"]
                    ]
                }
            return {
                "verdict": "SUPPORTED",
                "confidence_level": "HIGH",
                "issues": [],
                "explanation": "ok",
                "evidence_used": ["E1"],
            }

        llm = ScriptedLLM(respond)
        llm.state = state
        return llm

    async def test_failed_reassessment_keeps_previous_assessment(self, client, llm):
        claim = await _analyzed_claim(client)
        llm.state["fail"] = True
        response = await client.post(f"/api/claims/{claim['id']}/assess")
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "llm_timeout"
        after = (await client.get(f"/api/claims/{claim['id']}")).json()
        assert after["status"] == "READY"
        assert after["assessment"]["id"] == claim["assessment"]["id"]
        assert after["processing_error"].startswith("Latest reassessment failed")


async def test_reassess_outage_returns_503(client, paper_providers):
    claim = await _analyzed_claim(client)
    for provider in paper_providers:
        provider.failures["*"] = "unavailable"
    response = await client.post(
        f"/api/claims/{claim['id']}/assess", json={"refresh_metadata": True}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "metadata_providers_unavailable"


async def test_reassess_missing_claim(client):
    assert (await client.post(f"/api/claims/{uuid.uuid4()}/assess")).status_code == 404
