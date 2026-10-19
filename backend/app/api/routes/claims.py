import uuid
from typing import Annotated

from fastapi import APIRouter, Body

from app.api.deps import PipelineDep, SessionDep
from app.schemas.analysis import ReassessRequest
from app.schemas.claim import ClaimReviewResponse
from app.services import claims as claim_service

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("/{claim_id}", response_model=ClaimReviewResponse)
async def get_claim(claim_id: uuid.UUID, session: SessionDep) -> ClaimReviewResponse:
    return await claim_service.get_claim_review(session, claim_id)


@router.post("/{claim_id}/assess", response_model=ClaimReviewResponse)
async def reassess_claim(
    claim_id: uuid.UUID,
    session: SessionDep,
    pipeline: PipelineDep,
    payload: Annotated[ReassessRequest | None, Body()] = None,
) -> ClaimReviewResponse:
    """Re-run retrieval and assessment for one claim. Appends a new assessment;
    earlier assessments and any human review are kept."""
    payload = payload or ReassessRequest()
    return await pipeline.reassess_claim(
        session, claim_id, refresh_metadata=payload.refresh_metadata
    )
