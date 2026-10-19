import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Claim, ClaimSource, Draft, ReviewEvent


def _composite_options():
    # Everything ClaimReviewResponse needs in four queries regardless of claim
    # count: to-one links are joined, collections are loaded with one IN query each.
    # Round trips matter: the database is remote.
    return (
        joinedload(Claim.draft),
        joinedload(Claim.review),
        selectinload(Claim.citations).joinedload(ClaimSource.source),
        selectinload(Claim.evidence),
        selectinload(Claim.assessments),
    )


async def get_claim(
    session: AsyncSession, claim_id: uuid.UUID, *, populate_existing: bool = False
) -> Claim | None:
    # populate_existing refreshes objects (and their eager-loaded collections)
    # already in the session's identity map, e.g. after the pipeline wrote rows.
    result = await session.execute(
        select(Claim)
        .where(Claim.id == claim_id)
        .options(*_composite_options())
        .execution_options(populate_existing=populate_existing)
    )
    return result.scalar_one_or_none()


async def list_claims_for_draft(
    session: AsyncSession, draft_id: uuid.UUID, *, populate_existing: bool = False
) -> Sequence[Claim]:
    result = await session.execute(
        select(Claim)
        .where(Claim.draft_id == draft_id)
        .order_by(Claim.position)
        .options(*_composite_options())
        .execution_options(populate_existing=populate_existing)
    )
    return result.scalars().all()


async def list_claims_for_project(session: AsyncSession, project_id: uuid.UUID) -> Sequence[Claim]:
    result = await session.execute(
        select(Claim)
        .join(Draft, Claim.draft_id == Draft.id)
        .where(Draft.project_id == project_id)
        .order_by(Draft.created_at, Draft.id, Claim.position)
        .options(*_composite_options())
    )
    return result.scalars().all()


async def list_review_events(
    session: AsyncSession, claim_ids: Sequence[uuid.UUID]
) -> Sequence[ReviewEvent]:
    if not claim_ids:
        return []
    result = await session.execute(
        select(ReviewEvent)
        .where(ReviewEvent.claim_id.in_(claim_ids))
        .order_by(ReviewEvent.created_at, ReviewEvent.id)
    )
    return result.scalars().all()
