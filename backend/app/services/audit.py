import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.repositories import claims as claims_repo
from app.schemas.audit import AuditClaim, AuditProject, AuditResponse
from app.schemas.review import ReviewEventResponse
from app.services.claims import to_claim_review_response
from app.services.progress import compute_progress
from app.services.projects import get_project_or_404


async def build_audit(session: AsyncSession, project_id: uuid.UUID) -> AuditResponse:
    project = await get_project_or_404(session, project_id)
    progress = await compute_progress(session, project_id)
    claims = await claims_repo.list_claims_for_project(session, project_id)
    events = await claims_repo.list_review_events(session, [c.id for c in claims])

    history: dict[uuid.UUID, list[ReviewEventResponse]] = defaultdict(list)
    for event in events:
        history[event.claim_id].append(ReviewEventResponse.model_validate(event))

    return AuditResponse(
        generated_at=utcnow(),
        project=AuditProject.model_validate(project),
        progress=progress,
        claims=[
            AuditClaim(**to_claim_review_response(c).model_dump(), review_history=history[c.id])
            for c in claims
        ],
    )
