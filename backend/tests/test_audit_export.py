import csv
import io
import json
import uuid

import pytest

from app.domain.enums import IssueType, SourceAccessStatus, Verdict
from app.services.audit_export import CSV_COLUMNS
from tests import factories as f


@pytest.fixture
async def project(db_session):
    """Two claims: one with abstract evidence and a review, one with no
    accessible evidence and no review."""
    project = await f.make_project(db_session, title="Audit / Export: test?")
    draft = await f.make_draft(db_session, project)
    source = await f.make_source(db_session, project)
    blocked = await f.make_source(
        db_session, project, doi="10.1000/paywalled", access_status=SourceAccessStatus.UNAVAILABLE
    )
    first = await f.make_claim(db_session, draft, position=1, source=source)
    await f.make_evidence(db_session, first, source)
    await f.make_assessment(
        db_session,
        first,
        verdict=Verdict.PARTIALLY_SUPPORTED,
        confidence=0.86,
        issues=[
            {
                "type": IssueType.FIGURE_MISMATCH,
                "description": "22% vs OR 0.81",
                "claim_value": "22%",
                "evidence_value": "OR 0.81",
            }
        ],
    )
    second = await f.make_claim(db_session, draft, position=2, text="Unverifiable.", source=blocked)
    await f.make_assessment(db_session, second, verdict=Verdict.UNVERIFIABLE, confidence=0.3)
    project.claim_ids = [first.id, second.id]  # convenience for tests
    return project


async def _review_first(client, project, **payload):
    payload = {"decision": "QUALIFY", "reviewer_note": "Changed 22% to 19%.", **payload}
    response = await client.put(f"/api/claims/{project.claim_ids[0]}/review", json=payload)
    assert response.status_code == 200


async def test_audit_contains_full_trail_and_history(client, project):
    await _review_first(client, project, decision="KEEP", reviewer_note=None)
    await _review_first(client, project, revised_claim="About 19% lower odds.")
    body = (await client.get(f"/api/projects/{project.id}/audit")).json()

    assert "do not establish scientific truth" in body["disclaimer"]
    assert body["project"]["title"] == "Audit / Export: test?"
    assert body["progress"]["reviewed_claims"] == 1
    first, second = body["claims"]
    assert first["assessment"]["issues"][0]["type"] == "FIGURE_MISMATCH"
    assert first["review"]["decision"] == "QUALIFY"
    assert [e["decision"] for e in first["review_history"]] == ["KEEP", "QUALIFY"]
    assert second["review"] is None
    assert second["review_history"] == []
    assert second["evidence_availability"]["status"] == "UNAVAILABLE"


async def test_json_export(client, project):
    await _review_first(client, project, revised_claim="About 19% lower odds.")
    response = await client.get(f"/api/projects/{project.id}/export", params={"format": "json"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="evidence-review-audit-export-test-')
    assert disposition.endswith('.json"')

    body = json.loads(response.text)
    issue = body["claims"][0]["assessment"]["issues"][0]
    assert issue == {
        "type": "FIGURE_MISMATCH",
        "description": "22% vs OR 0.81",
        "claim_value": "22%",
        "evidence_value": "OR 0.81",
    }
    assert body["claims"][0]["review"]["revised_claim"] == "About 19% lower odds."
    assert body["claims"][1]["evidence"] == []
    assert body["claims"][1]["evidence_availability"]["status"] == "UNAVAILABLE"


async def _csv_rows(client, project) -> list[dict[str, str]]:
    response = await client.get(f"/api/projects/{project.id}/export", params={"format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].endswith('.csv"')
    text = response.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == CSV_COLUMNS
    return list(reader)


async def test_csv_export(client, project):
    await _review_first(client, project, revised_claim="About 19% lower odds.")
    first, second = await _csv_rows(client, project)

    assert first["claim_number"] == "1"
    assert first["citation"] == "[1]"
    assert first["doi"] == "10.1000/test"
    assert first["evidence_passage"] == "Outcome Y was lower with treatment X (OR 0.80)."
    assert first["evidence_location"] == "Abstract — Results"
    assert first["ai_verdict"] == "PARTIALLY_SUPPORTED"
    assert first["ai_confidence"] == "0.86"
    assert first["issues"] == "FIGURE_MISMATCH: 22% vs OR 0.81"
    assert first["human_decision"] == "QUALIFY"
    assert first["reviewer_note"] == "Changed 22% to 19%."
    assert first["revised_claim"] == "About 19% lower odds."
    assert first["review_status"] == "REVIEWED"
    assert first["reviewed_at"]

    assert second["human_decision"] == "NOT_REVIEWED"
    assert second["review_status"] == "NEEDS_REVIEW"


async def test_unavailable_evidence_is_explicit_in_csv(client, project):
    _, second = await _csv_rows(client, project)
    assert second["evidence_availability"] == "UNAVAILABLE"
    assert second["evidence_passage"].startswith("[EVIDENCE UNAVAILABLE]")
    assert second["evidence_location"] == "N/A"
    assert second["ai_verdict"] == "UNVERIFIABLE"


async def test_csv_injection_is_neutralized(client, project):
    await _review_first(
        client,
        project,
        reviewer_note='=HYPERLINK("http://evil.example","click")',
        revised_claim="+1+cmd|' /C calc'!A0",
    )
    first, _ = await _csv_rows(client, project)
    assert first["reviewer_note"] == '\'=HYPERLINK("http://evil.example","click")'
    assert first["revised_claim"].startswith("'+")


async def test_export_without_reviews_or_claims(client, db_session):
    empty = await f.make_project(db_session, title="Empty")
    response = await client.get(f"/api/projects/{empty.id}/export", params={"format": "csv"})
    lines = response.content.decode("utf-8-sig").strip().splitlines()
    assert len(lines) == 1  # header only


async def test_export_invalid_format(client, project):
    response = await client.get(f"/api/projects/{project.id}/export", params={"format": "xlsx"})
    assert response.status_code == 422


async def test_export_missing_format(client, project):
    assert (await client.get(f"/api/projects/{project.id}/export")).status_code == 422


async def test_export_missing_project(client):
    response = await client.get(f"/api/projects/{uuid.uuid4()}/export", params={"format": "json"})
    assert response.status_code == 404
    assert (await client.get(f"/api/projects/{uuid.uuid4()}/audit")).status_code == 404
