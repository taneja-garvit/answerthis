import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError
from app.models import Claim, Draft, Project
from app.schemas.project import DraftSummary, ProjectCreate, ProjectResponse


async def get_project_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project


async def create_project(session: AsyncSession, payload: ProjectCreate) -> ProjectResponse:
    project = Project(title=payload.title, description=payload.description)
    session.add(project)
    await session.commit()
    return await get_project(session, project.id)


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> ProjectResponse:
    project = await get_project_or_404(session, project_id)
    claim_counts = (
        select(Claim.draft_id, func.count(Claim.id).label("n")).group_by(Claim.draft_id).subquery()
    )
    rows = await session.execute(
        select(
            Draft.id,
            func.char_length(Draft.original_text),
            func.coalesce(claim_counts.c.n, 0),
            Draft.analysis_status,
            Draft.created_at,
        )
        .outerjoin(claim_counts, claim_counts.c.draft_id == Draft.id)
        .where(Draft.project_id == project_id)
        .order_by(Draft.created_at, Draft.id)
    )
    drafts = [
        DraftSummary(
            id=d_id, char_count=chars, claim_count=n, analysis_status=status, created_at=created
        )
        for d_id, chars, n, status, created in rows
    ]
    return ProjectResponse(
        id=project.id,
        title=project.title,
        description=project.description,
        status=project.status,
        is_demo=project.seed_key is not None,
        drafts=drafts,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
