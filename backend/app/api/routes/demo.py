import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.seed.demo import seed_demo

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoResponse(BaseModel):
    project_id: uuid.UUID
    draft_id: uuid.UUID
    created: bool


@router.post("", response_model=DemoResponse)
async def create_demo(
    session: SessionDep,
    response: Response,
    reset: bool = Query(False, description="Delete and recreate the demo project"),
) -> DemoResponse:
    """Idempotent: returns the existing demo project (and its saved reviews)
    unless `reset=true`."""
    result = await seed_demo(session, reset=reset)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return DemoResponse(
        project_id=result.project_id, draft_id=result.draft_id, created=result.created
    )
