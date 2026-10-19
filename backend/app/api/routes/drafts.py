import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Response, status

from app.api.deps import PipelineDep, SessionDep, SettingsDep
from app.schemas.analysis import AnalysisResponse, AnalyzeRequest
from app.schemas.claim import DraftClaimsResponse
from app.schemas.draft import DraftCreate, DraftResponse
from app.services import claims as claim_service
from app.services import drafts as draft_service
from app.services.pipeline import AnalyzeOptions

router = APIRouter(tags=["drafts"])


@router.post(
    "/projects/{project_id}/drafts",
    status_code=status.HTTP_201_CREATED,
    response_model=DraftResponse,
)
async def create_draft(
    project_id: uuid.UUID,
    payload: DraftCreate,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> DraftResponse:
    draft = await draft_service.create_draft(
        session, project_id, payload.original_text, max_chars=settings.max_draft_chars
    )
    response.headers["Location"] = f"/api/drafts/{draft.id}"
    return draft


@router.get("/drafts/{draft_id}", response_model=DraftResponse)
async def get_draft(draft_id: uuid.UUID, session: SessionDep) -> DraftResponse:
    return await draft_service.get_draft(session, draft_id)


@router.get("/drafts/{draft_id}/claims", response_model=DraftClaimsResponse)
async def list_draft_claims(draft_id: uuid.UUID, session: SessionDep) -> DraftClaimsResponse:
    return await claim_service.list_draft_claims(session, draft_id)


@router.post("/drafts/{draft_id}/analyze", response_model=AnalysisResponse)
async def analyze_draft(
    draft_id: uuid.UUID,
    session: SessionDep,
    pipeline: PipelineDep,
    payload: Annotated[AnalyzeRequest | None, Body()] = None,
) -> AnalysisResponse:
    """Synchronously extract claims, resolve citations, retrieve evidence and
    assess claims. Safe to repeat: already-assessed claims are reused."""
    payload = payload or AnalyzeRequest()
    return await pipeline.analyze_draft(
        session,
        draft_id,
        AnalyzeOptions(
            mode=payload.mode,
            citations=payload.citations,
            refresh_metadata=payload.refresh_metadata,
        ),
    )
