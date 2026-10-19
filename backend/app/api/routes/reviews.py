import uuid

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.claim import ClaimReviewResponse
from app.schemas.progress import ProgressResponse
from app.schemas.review import ReviewUpsert
from app.services import progress as progress_service
from app.services import reviews as review_service

router = APIRouter(tags=["reviews"])


@router.put("/claims/{claim_id}/review", response_model=ClaimReviewResponse)
async def save_review(
    claim_id: uuid.UUID, payload: ReviewUpsert, session: SessionDep
) -> ClaimReviewResponse:
    """Record the human decision. Returns the updated composite claim."""
    return await review_service.save_review(session, claim_id, payload)


@router.get("/projects/{project_id}/progress", response_model=ProgressResponse)
async def get_progress(project_id: uuid.UUID, session: SessionDep) -> ProgressResponse:
    return await progress_service.compute_progress(session, project_id)
