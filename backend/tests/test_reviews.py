import uuid

import pytest
from sqlalchemy import func, select

from app.models import Assessment, Review, ReviewEvent
from tests import factories as f


@pytest.fixture
async def claim(db_session):
    project = await f.make_project(db_session)
    draft = await f.make_draft(db_session, project)
    claim = await f.make_claim(db_session, draft)
    await f.make_assessment(db_session, claim)
    return claim


async def _events(db_session, claim_id):
    # populate_existing refreshes rows already in this session's identity map
    # (the API wrote them through its own session).
    result = await db_session.execute(
        select(ReviewEvent)
        .execution_options(populate_existing=True)
        .where(ReviewEvent.claim_id == claim_id)
        .order_by(ReviewEvent.created_at)
    )
    return result.scalars().all()


async def test_create_review(client, db_session, claim):
    response = await client.put(
        f"/api/claims/{claim.id}/review",
        json={"decision": "KEEP", "reviewer_note": "Matches abstract."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "REVIEWED"
    assert body["review"]["decision"] == "KEEP"
    assert body["review"]["reviewer_note"] == "Matches abstract."
    assert body["review"]["revised_claim"] is None
    assert body["review"]["reviewed_at"]

    events = await _events(db_session, claim.id)
    assert len(events) == 1
    assert events[0].decision == "KEEP"
    assert events[0].previous_decision is None
    assessment_id = await db_session.scalar(
        select(Assessment.id).where(Assessment.claim_id == claim.id)
    )
    assert events[0].assessment_id == assessment_id  # what the reviewer was shown


async def test_review_persists_across_requests(client, claim):
    await client.put(f"/api/claims/{claim.id}/review", json={"decision": "REMOVE"})
    body = (await client.get(f"/api/claims/{claim.id}")).json()
    assert body["review"]["decision"] == "REMOVE"
    assert body["review_status"] == "REVIEWED"


async def test_update_review_keeps_one_review_and_appends_history(client, db_session, claim):
    first = (await client.put(f"/api/claims/{claim.id}/review", json={"decision": "KEEP"})).json()[
        "review"
    ]
    second = (
        await client.put(
            f"/api/claims/{claim.id}/review",
            json={
                "decision": "QUALIFY",
                "reviewer_note": "Changed 22% to 19%.",
                "revised_claim": "RPM was associated with ~19% lower odds of death.",
            },
        )
    ).json()["review"]

    assert second["id"] == first["id"]
    assert second["decision"] == "QUALIFY"
    assert second["revised_claim"] == "RPM was associated with ~19% lower odds of death."
    assert second["reviewed_at"] > first["reviewed_at"]
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]

    count = await db_session.scalar(
        select(func.count()).select_from(Review).where(Review.claim_id == claim.id)
    )
    assert count == 1

    events = await _events(db_session, claim.id)
    assert [e.decision for e in events] == ["KEEP", "QUALIFY"]
    assert [e.previous_decision for e in events] == [None, "KEEP"]
    # The first event is unchanged by the second save (history is immutable).
    assert events[0].reviewer_note is None
    assert events[0].revised_claim is None
    assert events[1].reviewer_note == "Changed 22% to 19%."


async def test_replace_requires_revised_claim(client, db_session, claim):
    response = await client.put(f"/api/claims/{claim.id}/review", json={"decision": "REPLACE"})
    assert response.status_code == 422
    assert "revised_claim is required" in response.text
    assert await _events(db_session, claim.id) == []


async def test_replace_with_blank_revised_claim_rejected(client, claim):
    response = await client.put(
        f"/api/claims/{claim.id}/review", json={"decision": "REPLACE", "revised_claim": "   "}
    )
    assert response.status_code == 422


async def test_replace_with_revised_claim(client, claim):
    response = await client.put(
        f"/api/claims/{claim.id}/review",
        json={"decision": "REPLACE", "revised_claim": "A different, supported claim."},
    )
    assert response.status_code == 200
    assert response.json()["review"]["revised_claim"] == "A different, supported claim."


@pytest.mark.parametrize("decision", ["KEEP", "REMOVE"])
async def test_keep_and_remove_reject_revised_claim(client, claim, decision):
    response = await client.put(
        f"/api/claims/{claim.id}/review",
        json={"decision": decision, "revised_claim": "Something"},
    )
    assert response.status_code == 422
    assert "must be empty" in response.text


async def test_qualify_without_revision_allowed(client, claim):
    response = await client.put(
        f"/api/claims/{claim.id}/review", json={"decision": "QUALIFY", "reviewer_note": "  "}
    )
    assert response.status_code == 200
    review = response.json()["review"]
    assert review["revised_claim"] is None
    assert review["reviewer_note"] is None  # blank note stored as null


async def test_invalid_decision_rejected(client, claim):
    response = await client.put(f"/api/claims/{claim.id}/review", json={"decision": "APPROVE"})
    assert response.status_code == 422


async def test_overlong_note_rejected(client, claim):
    response = await client.put(
        f"/api/claims/{claim.id}/review", json={"decision": "KEEP", "reviewer_note": "x" * 5001}
    )
    assert response.status_code == 422


async def test_review_missing_claim_returns_404(client):
    response = await client.put(f"/api/claims/{uuid.uuid4()}/review", json={"decision": "KEEP"})
    assert response.status_code == 404


async def test_ai_assessment_does_not_mark_claim_reviewed(client, claim):
    body = (await client.get(f"/api/claims/{claim.id}")).json()
    assert body["assessment"] is not None
    assert body["review_status"] == "NEEDS_REVIEW"
