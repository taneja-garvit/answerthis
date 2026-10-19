"""Analyze endpoint and PipelineService, end to end against the test database.
Crossref/OpenAlex are fakes serving recorded responses; the LLM is the
deterministic provider or a scripted fake. No network access."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.ai.base import LLMRateLimitError
from app.db.base import utcnow
from app.models import Assessment, Claim, Draft, Evidence, Source
from app.papers.base import PaperRecord
from app.seed.demo import DRAFT_TEXT, PAPER
from tests.fakes import HF_DOI, ScriptedLLM


async def _draft(client, text: str = DRAFT_TEXT) -> str:
    project = (await client.post("/api/projects", json={"title": "Pipeline"})).json()
    draft = await client.post(f"/api/projects/{project['id']}/drafts", json={"original_text": text})
    return draft.json()["id"]


async def _count(db_session, model, **where) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in where.items():
        statement = statement.where(getattr(model, column) == value)
    return await db_session.scalar(statement)


async def test_heart_failure_draft_end_to_end_deterministic(client, db_session):
    draft_id = await _draft(client)
    response = await client.post(f"/api/drafts/{draft_id}/analyze")
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "ANALYZED"
    assert (body["claims_extracted"], body["claims_assessed"], body["claims_failed"]) == (3, 3, 0)
    assert body["rerun"] is False
    assert body["llm_provider"] == "deterministic"
    assert body["llm_calls"] == 4  # 1 extraction + 3 assessments

    claims = body["claims"]
    assert [c["assessment"]["verdict"] for c in claims] == [
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "UNSUPPORTED",
    ]
    for claim in claims:
        assert claim["status"] == "READY"
        assert claim["citation_marker"] == "[1]"
        assert claim["source"]["doi"] == HF_DOI
        assert claim["source"]["title"] == PAPER["title"]
        assert claim["source"]["access_status"] == "ABSTRACT_ONLY"
        assert claim["evidence"], "evidence retrieved"
        for evidence in claim["evidence"]:
            assert evidence["passage"] in PAPER["abstract"]  # verbatim from the public abstract
            assert evidence["access_level"] == "ABSTRACT"
            assert evidence["retrieval_method"] == "bm25_numeric_v1"
            assert evidence["retrieval_score"] > 0
        assessment = claim["assessment"]
        assert assessment["provider"] == "deterministic"
        assert assessment["prompt_version"] == "claim_assessment.v1"
        assert set(assessment["evidence_ids"]) <= {e["id"] for e in claim["evidence"]}
        assert claim["review_status"] == "NEEDS_REVIEW"  # AI never marks a claim reviewed
    assert claims[1]["assessment"]["issues"][0]["type"] == "FIGURE_MISMATCH"
    assert await _count(db_session, Source, doi=HF_DOI) == 1  # one source shared by all claims


async def test_rerun_is_idempotent_and_makes_no_llm_calls(client, db_session, llm):
    draft_id = await _draft(client)
    first = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    claim_ids = [c["id"] for c in first["claims"]]
    counts = [await _count(db_session, m) for m in (Claim, Evidence, Assessment)]

    second = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    assert second["rerun"] is True
    assert (second["claims_processed"], second["claims_reused"], second["llm_calls"]) == (0, 3, 0)
    assert [c["id"] for c in second["claims"]] == claim_ids
    assert [await _count(db_session, m) for m in (Claim, Evidence, Assessment)] == counts


async def test_reextract_refuses_when_reviews_exist_and_works_otherwise(client):
    draft_id = await _draft(client)
    first = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()

    redo = await client.post(f"/api/drafts/{draft_id}/analyze", json={"mode": "reextract"})
    assert redo.status_code == 200
    assert {c["id"] for c in redo.json()["claims"]}.isdisjoint({c["id"] for c in first["claims"]})

    claim_id = redo.json()["claims"][0]["id"]
    await client.put(f"/api/claims/{claim_id}/review", json={"decision": "KEEP"})
    blocked = await client.post(f"/api/drafts/{draft_id}/analyze", json={"mode": "reextract"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "reviews_exist"
    # The lock was released and the draft keeps its analyzed state.
    draft = (await client.get(f"/api/drafts/{draft_id}")).json()
    assert draft["analysis_status"] == "ANALYZED"
    kept = (await client.get(f"/api/claims/{claim_id}")).json()
    assert kept["review"]["decision"] == "KEEP"


PARTIAL_DRAFT = (
    "Remote patient monitoring was associated with lower odds of first heart-failure "
    "hospitalization (OR 0.78) [1]. "
    "Telemonitoring reduced readmissions in a separate cohort [2]. "
    "A wrong DOI was cited for this outcome [3]. "
    "Exercise improved quality of life in this population. "
    "Monitoring also lowered mortality [1, 4].\n\n"
    "References\n"
    "[1] De Lathauwer ILJ, et al. Remote patient monitoring in heart failure: a comprehensive "
    "meta-analysis of effective programme components for hospitalization and mortality "
    f"reduction. 2025. doi:{HF_DOI}\n"
    "[2] Unpublished cohort report. 2024.\n"
    "[3] Doe J. Missing paper. 2023. doi:10.9999/missing\n"
)


async def test_partial_failures_are_isolated_per_claim(client):
    draft_id = await _draft(client, PARTIAL_DRAFT)
    body = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    claims = {c["order"]: c for c in body["claims"]}
    assert len(claims) == 5

    assert claims[1]["status"] == "READY" and claims[1]["source"]["doi"] == HF_DOI

    unresolved = claims[2]["assessment"]
    assert unresolved["verdict"] == "UNVERIFIABLE"
    assert unresolved["provider"] == "pipeline_rules"
    assert unresolved["confidence_level"] is None
    assert unresolved["issues"][0]["type"] == "EVIDENCE_UNAVAILABLE"
    assert "[2]" in unresolved["issues"][0]["description"]
    assert claims[2]["evidence_availability"]["status"] == "UNAVAILABLE"

    missing = claims[3]["assessment"]
    assert missing["verdict"] == "UNVERIFIABLE"
    assert missing["issues"][0]["type"] == "SOURCE_MISMATCH"
    assert "10.9999/missing" in missing["issues"][0]["description"]

    uncited = claims[4]["assessment"]
    assert uncited["issues"][0]["description"] == "No citation is attached to this claim."

    mixed = claims[5]
    assert mixed["citation_marker"] == "[1, 4]"
    assert any(
        i["type"] == "EVIDENCE_UNAVAILABLE" and "[4]" in i["description"]
        for i in mixed["assessment"]["issues"]
    )
    # Rule-based outcomes made no LLM call: 1 extraction + claims 1 and 5 only.
    assert body["llm_calls"] == 3
    assert body["claims_unverifiable"] >= 3


async def test_provider_outage_marks_claim_for_retry(client, paper_providers):
    for provider in paper_providers:
        provider.failures["*"] = "timeout"
    draft_id = await _draft(client)
    body = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    assert body["claims_failed"] == 3
    assert all(c["status"] == "ERROR" for c in body["claims"])
    assert "unavailable" in body["claims"][0]["processing_error"]
    assert all(c["assessment"] is None for c in body["claims"])

    for provider in paper_providers:
        provider.failures.clear()
    retry = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    assert (retry["claims_processed"], retry["claims_failed"], retry["claims_assessed"]) == (
        3,
        0,
        3,
    )


async def test_missing_abstract_is_unverifiable(client, paper_providers):
    bare = PaperRecord(doi=HF_DOI, title=PAPER["title"], providers=["crossref"])
    paper_providers[0].records[HF_DOI] = bare
    paper_providers[1].records.clear()
    draft_id = await _draft(client)
    body = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    for claim in body["claims"]:
        assert claim["assessment"]["verdict"] == "UNVERIFIABLE"
        assert claim["assessment"]["issues"][0]["type"] == "EVIDENCE_UNAVAILABLE"
        assert claim["source"]["access_status"] == "UNAVAILABLE"
        assert claim["evidence"] == []


async def test_explicit_citation_mapping_overrides_reference_list(client):
    text = "Remote patient monitoring lowered the odds of death by 22% [7]."
    draft_id = await _draft(client, text)
    body = (
        await client.post(
            f"/api/drafts/{draft_id}/analyze",
            json={"citations": {"[7]": f"https://doi.org/{HF_DOI}"}},
        )
    ).json()
    assert body["claims"][0]["source"]["doi"] == HF_DOI


async def test_invalid_citation_mapping_rejected(client):
    draft_id = await _draft(client)
    response = await client.post(
        f"/api/drafts/{draft_id}/analyze", json={"citations": {"1": "nope"}}
    )
    assert response.status_code == 422


async def test_reference_title_mismatch_is_flagged(client):
    text = (
        "Remote patient monitoring lowered the odds of death by 22% [1].\n\n"
        "[1] Roe K. Statins for stroke prevention in elderly adults with diabetes. 2019. "
        f"doi:{HF_DOI}"
    )
    draft_id = await _draft(client, text)
    claim = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()["claims"][0]
    assert any(i["type"] == "SOURCE_MISMATCH" for i in claim["assessment"]["issues"])


class TestWithScriptedModel:
    @pytest.fixture
    def llm(self):
        def respond(request):
            if request.task == "claim_extraction":
                return {
                    "claims": [
                        {"sentence_id": s["id"], "claim_text": s["text"].replace(" [1]", "")}
                        for s in request.payload["sentences"]
                    ]
                }
            return {
                "verdict": "PARTIALLY_SUPPORTED",
                "confidence_level": "MEDIUM",
                "issues": [{"type": "FIGURE_MISMATCH", "description": "Numbers differ."}],
                "explanation": "Scripted.",
                "suggested_revision": None,
                "evidence_used": [request.payload["evidence"][0]["id"]],
            }

        return ScriptedLLM(respond, model="scripted-model-7")

    async def test_live_style_assessment_is_persisted_with_metadata(self, client, db_session):
        draft_id = await _draft(client)
        body = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
        assessment = body["claims"][0]["assessment"]
        assert assessment["provider"] == "scripted"
        assert assessment["model"] == "scripted-model-7"
        assert assessment["confidence_level"] == "MEDIUM"
        assert assessment["confidence"] is None
        assert assessment["generation_metadata"]["live_model"] is True
        assert assessment["generation_metadata"]["usage"] == {"total_tokens": 10}
        assert len(assessment["evidence_ids"]) == 1
        assert body["llm_model"] == "scripted-model-7"


class TestRateLimitCircuitBreaker:
    @pytest.fixture
    def llm(self):
        def respond(request):
            if request.task == "claim_extraction":
                return {
                    "claims": [
                        {"sentence_id": s["id"], "claim_text": s["text"]}
                        for s in request.payload["sentences"]
                    ]
                }
            return LLMRateLimitError("The AI provider's rate limit was reached. Wait and retry.")

        return ScriptedLLM(respond)

    async def test_stops_calling_the_model_after_rate_limit(self, client, llm):
        draft_id = await _draft(client)
        response = await client.post(f"/api/drafts/{draft_id}/analyze")
        assert response.status_code == 200
        body = response.json()
        assert body["claims_failed"] == 3
        assessments = [r for r in llm.requests if r.task == "claim_assessment"]
        assert len(assessments) == 1  # claims 2 and 3 skipped, not attempted
        assert body["claims"][1]["processing_error"].startswith("Skipped:")


class TestExtractionFailure:
    @pytest.fixture
    def llm(self):
        return ScriptedLLM(
            lambda _r: LLMRateLimitError("The AI provider's rate limit was reached.")
        )

    async def test_extraction_failure_returns_error_and_releases_lock(self, client):
        draft_id = await _draft(client)
        response = await client.post(f"/api/drafts/{draft_id}/analyze")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "llm_rate_limited"
        draft = (await client.get(f"/api/drafts/{draft_id}")).json()
        assert draft["analysis_status"] == "FAILED"
        again = await client.post(f"/api/drafts/{draft_id}/analyze")
        assert again.status_code == 503  # not 409: the lock was released


async def test_concurrent_analysis_is_rejected_but_stale_lock_recovers(client, db_session):
    draft_id = await _draft(client)
    await db_session.execute(
        update(Draft)
        .where(Draft.id == uuid.UUID(draft_id))
        .values(analysis_status="ANALYZING", analysis_started_at=utcnow())
    )
    await db_session.flush()
    busy = await client.post(f"/api/drafts/{draft_id}/analyze")
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "analysis_in_progress"

    await db_session.execute(
        update(Draft)
        .where(Draft.id == uuid.UUID(draft_id))
        .values(analysis_started_at=utcnow() - timedelta(minutes=20))
    )
    await db_session.flush()
    assert (await client.post(f"/api/drafts/{draft_id}/analyze")).status_code == 200


async def test_analyze_missing_draft(client):
    assert (await client.post(f"/api/drafts/{uuid.uuid4()}/analyze")).status_code == 404
    assert (await client.post("/api/drafts/nope/analyze")).status_code == 422


async def test_analyze_draft_without_claims(client):
    draft_id = await _draft(client, "Introduction\n\nWhy does this matter? We will see.")
    body = (await client.post(f"/api/drafts/{draft_id}/analyze")).json()
    assert body["claims_extracted"] == 0 and body["analysis_status"] == "ANALYZED"
