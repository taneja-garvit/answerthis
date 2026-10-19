from sqlalchemy import func, select

from app.models import Assessment, PaperCache, Project
from app.seed.demo import DEMO_SEED_KEY, DRAFT_TEXT, FIXTURE_PROVIDER, PAPER, seed_demo


async def test_seed_creates_three_claims_with_expected_states(client, db_session):
    result = await seed_demo(db_session, reset=True)
    assert result.created is True

    claims = (await client.get(f"/api/drafts/{result.draft_id}/claims")).json()["claims"]
    assert len(claims) == 3
    assert [c["assessment"]["verdict"] for c in claims] == [
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "UNSUPPORTED",
    ]
    assert [i["type"] for i in claims[1]["assessment"]["issues"]] == ["FIGURE_MISMATCH"]
    assert "OVERGENERALIZATION" in [i["type"] for i in claims[2]["assessment"]["issues"]]
    for claim in claims:
        assert claim["review"] is None
        assert claim["review_status"] == "NEEDS_REVIEW"
        assert claim["source"]["doi"] == "10.1002/ejhf.3568"
        assert claim["evidence_availability"]["status"] == "ABSTRACT"
        assert claim["original_sentence"] in DRAFT_TEXT


async def test_seed_evidence_is_verbatim_from_public_abstract(client, db_session):
    result = await seed_demo(db_session, reset=True)
    claims = (await client.get(f"/api/drafts/{result.draft_id}/claims")).json()["claims"]
    passages = [e for c in claims for e in c["evidence"]]
    assert passages
    for evidence in passages:
        assert evidence["passage"] in PAPER["abstract"]
        assert evidence["access_level"] == "ABSTRACT"
        assert evidence["is_synthetic"] is False
        assert evidence["retrieval_score"] is None  # no retrieval was run


async def test_seed_assessments_are_labelled_as_fixtures(db_session):
    result = await seed_demo(db_session, reset=True)
    assessments = (
        (
            await db_session.execute(
                select(Assessment)
                .execution_options(populate_existing=True)
                .where(Assessment.claim.has(draft_id=result.draft_id))
            )
        )
        .scalars()
        .all()
    )
    assert len(assessments) == 3
    for assessment in assessments:
        assert assessment.provider == FIXTURE_PROVIDER
        assert assessment.model is None
        assert assessment.generation_metadata["live_model"] is False
        assert len(assessment.evidence_ids) >= 1


async def test_seed_is_idempotent_and_preserves_reviews(client, db_session):
    first = await seed_demo(db_session, reset=True)
    claims = (await client.get(f"/api/drafts/{first.draft_id}/claims")).json()["claims"]
    await client.put(f"/api/claims/{claims[0]['id']}/review", json={"decision": "KEEP"})

    again = await seed_demo(db_session)
    assert again.created is False
    assert (again.project_id, again.draft_id) == (first.project_id, first.draft_id)

    count = await db_session.scalar(
        select(func.count()).select_from(Project).where(Project.seed_key == DEMO_SEED_KEY)
    )
    assert count == 1
    cached = await db_session.scalar(
        select(func.count()).select_from(PaperCache).where(PaperCache.doi == "10.1002/ejhf.3568")
    )
    assert cached == 1
    claim = (await client.get(f"/api/claims/{claims[0]['id']}")).json()
    assert claim["review"]["decision"] == "KEEP"


async def test_seed_reset_recreates_without_reviews(client, db_session):
    first = await seed_demo(db_session, reset=True)
    claims = (await client.get(f"/api/drafts/{first.draft_id}/claims")).json()["claims"]
    await client.put(f"/api/claims/{claims[0]['id']}/review", json={"decision": "KEEP"})

    reset = await seed_demo(db_session, reset=True)
    assert reset.created is True
    assert reset.project_id != first.project_id
    assert (await client.get(f"/api/projects/{first.project_id}")).status_code == 404
    progress = (await client.get(f"/api/projects/{reset.project_id}/progress")).json()
    assert progress["reviewed_claims"] == 0
    assert progress["total_claims"] == 3


async def test_demo_endpoint(client):
    created = await client.post("/api/demo", params={"reset": "true"})
    assert created.status_code == 201
    assert created.json()["created"] is True
    again = await client.post("/api/demo")
    assert again.status_code == 200
    assert again.json()["project_id"] == created.json()["project_id"]
    project = (await client.get(f"/api/projects/{created.json()['project_id']}")).json()
    assert project["is_demo"] is True
    assert project["drafts"][0]["claim_count"] == 3
