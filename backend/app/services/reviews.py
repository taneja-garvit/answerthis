import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError
from app.db.base import utcnow
from app.models import Claim, Review, ReviewEvent
from app.repositories import claims as claims_repo
from app.schemas.claim import ClaimReviewResponse
from app.schemas.review import ReviewUpsert
from app.services.claims import latest_assessment, to_claim_review_response


async def save_review(
    session: AsyncSession, claim_id: uuid.UUID, payload: ReviewUpsert
) -> ClaimReviewResponse:
    """Upsert the current Review and append an immutable ReviewEvent, in one
    transaction. The claim row is locked so concurrent saves serialize instead of
    racing on the one-review-per-claim constraint."""
    locked = await session.execute(select(Claim.id).where(Claim.id == claim_id).with_for_update())
    if locked.scalar_one_or_none() is None:
        raise NotFoundError("Claim not found")

    claim = await claims_repo.get_claim(session, claim_id)
    assert claim is not None
    now = utcnow()
    review = claim.review
    previous_decision = review.decision if review else None
    if review is None:
        review = Review(claim_id=claim.id, decision=payload.decision, reviewed_at=now)
        session.add(review)
        claim.review = review
    review.decision = payload.decision
    review.reviewer_note = payload.reviewer_note
    review.revised_claim = payload.revised_claim
    review.reviewed_at = now
    await session.flush()

    assessment = latest_assessment(claim)
    session.add(
        ReviewEvent(
            claim_id=claim.id,
            review_id=review.id,
            decision=payload.decision,
            previous_decision=previous_decision,
            reviewer_note=payload.reviewer_note,
            revised_claim=payload.revised_claim,
            assessment_id=assessment.id if assessment else None,
            created_at=now,
        )
    )
    await session.commit()
    return to_claim_review_response(claim)
