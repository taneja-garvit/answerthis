import uuid

from app.domain.enums import Verdict
from tests import factories as f


async def test_zero_claims(client, db_session):
    project = await f.make_project(db_session)
    body = (await client.get(f"/api/projects/{project.id}/progress")).json()
    assert body["total_claims"] == 0
    assert body["reviewed_claims"] == 0
    assert body["remaining_claims"] == 0
    assert body["completion_percentage"] == 0.0
    assert body["is_complete"] is False
    assert body["human_decisions"] == {"KEEP": 0, "QUALIFY": 0, "REPLACE": 0, "REMOVE": 0}
    assert body["ai_verdicts"] == {
        "SUPPORTED": 0,
        "PARTIALLY_SUPPORTED": 0,
        "UNSUPPORTED": 0,
        "UNVERIFIABLE": 0,
        "NOT_ASSESSED": 0,
    }


async def test_progress_and_separate_distributions(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    verdicts = [Verdict.SUPPORTED, Verdict.SUPPORTED, Verdict.UNSUPPORTED, Verdict.UNVERIFIABLE]
    claims = []
    for position, verdict in enumerate(verdicts, start=1):
        claim = await f.make_claim(db_session, draft, position=position)
        await f.make_assessment(db_session, claim, verdict=verdict)
        claims.append(claim)
    await f.make_claim(db_session, draft, position=5)  # never assessed

    await client.put(f"/api/claims/{claims[0].id}/review", json={"decision": "KEEP"})
    await client.put(f"/api/claims/{claims[1].id}/review", json={"decision": "QUALIFY"})
    # A human may keep a claim the AI flagged: decisions are independent of verdicts.
    await client.put(f"/api/claims/{claims[2].id}/review", json={"decision": "KEEP"})

    body = (await client.get(f"/api/projects/{project.id}/progress")).json()
    assert body["total_claims"] == 5
    assert body["reviewed_claims"] == 3
    assert body["remaining_claims"] == 2
    assert body["completion_percentage"] == 60.0
    assert body["is_complete"] is False
    assert body["human_decisions"] == {"KEEP": 2, "QUALIFY": 1, "REPLACE": 0, "REMOVE": 0}
    assert body["ai_verdicts"] == {
        "SUPPORTED": 2,
        "PARTIALLY_SUPPORTED": 0,
        "UNSUPPORTED": 1,
        "UNVERIFIABLE": 1,
        "NOT_ASSESSED": 1,
    }


async def test_changing_decision_does_not_double_count(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    claim = await f.make_claim(db_session, draft)
    await client.put(f"/api/claims/{claim.id}/review", json={"decision": "KEEP"})
    await client.put(f"/api/claims/{claim.id}/review", json={"decision": "REMOVE"})
    body = (await client.get(f"/api/projects/{project.id}/progress")).json()
    assert body["reviewed_claims"] == 1
    assert body["human_decisions"]["KEEP"] == 0
    assert body["human_decisions"]["REMOVE"] == 1
    assert body["is_complete"] is True
    assert body["completion_percentage"] == 100.0


async def test_only_latest_assessment_counts(client, db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    claim = await f.make_claim(db_session, draft)
    await f.make_assessment(db_session, claim, verdict=Verdict.UNVERIFIABLE, age_seconds=120)
    await f.make_assessment(db_session, claim, verdict=Verdict.SUPPORTED)
    body = (await client.get(f"/api/projects/{project.id}/progress")).json()
    assert body["ai_verdicts"]["SUPPORTED"] == 1
    assert body["ai_verdicts"]["UNVERIFIABLE"] == 0


async def test_progress_counts_all_drafts_of_project_only(client, db_session):
    project = await f.make_project(db_session)
    other = await f.make_project(db_session, title="Other")
    for p in (project, project, other):
        draft = await f.make_draft(db_session, p)
        await f.make_claim(db_session, draft)
    body = (await client.get(f"/api/projects/{project.id}/progress")).json()
    assert body["total_claims"] == 2


async def test_progress_missing_project_404(client):
    assert (await client.get(f"/api/projects/{uuid.uuid4()}/progress")).status_code == 404
