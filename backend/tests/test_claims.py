import uuid

from app.domain.enums import AccessLevel, IssueType, SourceAccessStatus, Verdict
from tests import factories as f


async def test_list_claims_empty_draft(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    response = await client.get(f"/api/drafts/{draft.id}/claims")
    assert response.status_code == 200
    assert response.json() == {
        "draft_id": str(draft.id),
        "project_id": str(project.id),
        "claims": [],
    }


async def test_claims_listed_in_order(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    await f.make_claim(db_session, draft, position=2, text="Second.")
    await f.make_claim(db_session, draft, position=1, text="First.")
    claims = (await client.get(f"/api/drafts/{draft.id}/claims")).json()["claims"]
    assert [c["order"] for c in claims] == [1, 2]
    assert [c["claim_text"] for c in claims] == ["First.", "Second."]


async def test_composite_claim_response(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    source = await f.make_source(db_session, project)
    claim = await f.make_claim(db_session, draft, source=source)
    evidence = await f.make_evidence(db_session, claim, source)
    await f.make_assessment(
        db_session,
        claim,
        verdict=Verdict.PARTIALLY_SUPPORTED,
        issues=[
            {
                "type": IssueType.FIGURE_MISMATCH,
                "description": "Numbers differ",
                "claim_value": "22%",
                "evidence_value": "OR 0.81",
            }
        ],
    )

    response = await client.get(f"/api/claims/{claim.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(claim.id)
    assert body["project_id"] == str(project.id)
    assert body["citation_marker"] == "[1]"
    assert body["source"]["doi"] == "10.1000/test"
    assert body["source"]["citation_marker"] == "[1]"
    assert len(body["sources"]) == 1
    assert body["evidence"][0]["id"] == str(evidence.id)
    assert body["evidence"][0]["access_level"] == "ABSTRACT"
    assert body["evidence_availability"]["status"] == "ABSTRACT"
    assert body["assessment"]["verdict"] == "PARTIALLY_SUPPORTED"
    assert body["assessment"]["issues"][0] == {
        "type": "FIGURE_MISMATCH",
        "description": "Numbers differ",
        "claim_value": "22%",
        "evidence_value": "OR 0.81",
    }
    assert body["review"] is None
    assert body["review_status"] == "NEEDS_REVIEW"


async def test_latest_assessment_is_returned(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    claim = await f.make_claim(db_session, draft)
    await f.make_assessment(db_session, claim, verdict=Verdict.SUPPORTED, age_seconds=60)
    await f.make_assessment(db_session, claim, verdict=Verdict.UNSUPPORTED, age_seconds=0)
    body = (await client.get(f"/api/claims/{claim.id}")).json()
    assert body["assessment"]["verdict"] == "UNSUPPORTED"


async def test_unavailable_evidence_is_explicit(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    source = await f.make_source(db_session, project, access_status=SourceAccessStatus.UNAVAILABLE)
    claim = await f.make_claim(db_session, draft, source=source)
    body = (await client.get(f"/api/claims/{claim.id}")).json()
    assert body["evidence"] == []
    assert body["evidence_availability"]["status"] == "UNAVAILABLE"
    assert "could not be accessed" in body["evidence_availability"]["message"]


async def test_claim_without_source_is_unavailable(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    claim = await f.make_claim(db_session, draft)
    body = (await client.get(f"/api/claims/{claim.id}")).json()
    assert body["source"] is None
    assert body["evidence_availability"]["status"] == "UNAVAILABLE"
    assert "no source" in body["evidence_availability"]["message"]


async def test_full_text_evidence_takes_precedence(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    source = await f.make_source(db_session, project)
    claim = await f.make_claim(db_session, draft, source=source)
    await f.make_evidence(db_session, claim, source, access_level=AccessLevel.ABSTRACT)
    await f.make_evidence(db_session, claim, source, access_level=AccessLevel.FULL_TEXT, rank=1)
    body = (await client.get(f"/api/claims/{claim.id}")).json()
    assert body["evidence_availability"]["status"] == "FULL_TEXT"
    assert [e["rank"] for e in body["evidence"]] == [0, 1]


async def test_missing_claim_returns_404(client):
    response = await client.get(f"/api/claims/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Claim not found"


async def test_invalid_claim_id_returns_422(client):
    assert (await client.get("/api/claims/xyz")).status_code == 422
