import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment, Claim, Draft, Review
from app.schemas.progress import DecisionCounts, ProgressResponse, VerdictCounts
from app.services.projects import get_project_or_404


async def compute_progress(session: AsyncSession, project_id: uuid.UUID) -> ProgressResponse:
    await get_project_or_404(session, project_id)
    project_claims = (
        select(Claim.id)
        .join(Draft, Claim.draft_id == Draft.id)
        .where(Draft.project_id == project_id)
        .subquery()
    )

    total = await session.scalar(select(func.count()).select_from(project_claims)) or 0

    decision_rows = await session.execute(
        select(Review.decision, func.count())
        .where(Review.claim_id.in_(select(project_claims.c.id)))
        .group_by(Review.decision)
    )
    decisions = DecisionCounts(**{decision: n for decision, n in decision_rows})

    # Only the newest assessment per claim counts (Postgres DISTINCT ON).
    latest = (
        select(Assessment.claim_id, Assessment.verdict)
        .where(Assessment.claim_id.in_(select(project_claims.c.id)))
        .ext(distinct_on(Assessment.claim_id))
        .order_by(Assessment.claim_id, Assessment.created_at.desc(), Assessment.id.desc())
        .subquery()
    )
    verdict_rows = await session.execute(
        select(latest.c.verdict, func.count()).group_by(latest.c.verdict)
    )
    verdict_counts = {verdict: n for verdict, n in verdict_rows}
    assessed = sum(verdict_counts.values())
    verdicts = VerdictCounts(**verdict_counts, NOT_ASSESSED=total - assessed)

    reviewed = sum(decisions.model_dump().values())
    return ProgressResponse(
        project_id=project_id,
        total_claims=total,
        reviewed_claims=reviewed,
        remaining_claims=total - reviewed,
        completion_percentage=round(reviewed / total * 100, 1) if total else 0.0,
        is_complete=total > 0 and reviewed == total,
        human_decisions=decisions,
        ai_verdicts=verdicts,
    )
