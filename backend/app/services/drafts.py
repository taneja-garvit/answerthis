import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import DomainValidationError, NotFoundError
from app.models import Draft
from app.schemas.draft import DraftResponse
from app.services.projects import get_project_or_404


def _to_response(draft: Draft) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        project_id=draft.project_id,
        original_text=draft.original_text,
        char_count=len(draft.original_text),
        analysis_status=draft.analysis_status,
        analyzed_at=draft.analyzed_at,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


async def create_draft(
    session: AsyncSession, project_id: uuid.UUID, text: str, *, max_chars: int
) -> DraftResponse:
    await get_project_or_404(session, project_id)
    text = text.strip()
    if not text:
        raise DomainValidationError("Draft text must not be empty", code="draft_empty")
    if len(text) > max_chars:
        raise DomainValidationError(
            f"Draft is {len(text)} characters; the limit is {max_chars}",
            code="draft_too_large",
        )
    draft = Draft(project_id=project_id, original_text=text)
    session.add(draft)
    await session.commit()
    return _to_response(draft)


async def get_draft(session: AsyncSession, draft_id: uuid.UUID) -> DraftResponse:
    draft = await session.get(Draft, draft_id)
    if draft is None:
        raise NotFoundError("Draft not found")
    return _to_response(draft)
