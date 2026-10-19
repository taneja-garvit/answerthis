"""Direct-to-database builders for test data (no external services)."""

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.domain.enums import AccessLevel, ClaimStatus, SourceAccessStatus, Verdict
from app.models import Assessment, Claim, ClaimSource, Draft, Evidence, Project, Source


async def make_project(session: AsyncSession, title: str = "Test project") -> Project:
    project = Project(title=title)
    session.add(project)
    await session.flush()
    return project


async def make_draft(session: AsyncSession, project: Project, text: str = "Draft text.") -> Draft:
    draft = Draft(project_id=project.id, original_text=text)
    session.add(draft)
    await session.flush()
    return draft


async def make_source(
    session: AsyncSession,
    project: Project,
    *,
    doi: str | None = "10.1000/test",
    access_status: SourceAccessStatus = SourceAccessStatus.ABSTRACT_ONLY,
    title: str = "A test paper",
) -> Source:
    source = Source(
        project_id=project.id,
        doi=doi,
        title=title,
        authors=[{"given": "Ada", "family": "Lovelace"}],
        journal="Journal of Tests",
        publication_year=2024,
        access_status=access_status,
    )
    session.add(source)
    await session.flush()
    return source


async def make_claim(
    session: AsyncSession,
    draft: Draft,
    *,
    position: int = 1,
    text: str = "Treatment X reduced outcome Y.",
    source: Source | None = None,
) -> Claim:
    claim = Claim(
        draft_id=draft.id,
        position=position,
        claim_text=text,
        original_sentence=text + " [1]",
        citation_marker="[1]" if source else None,
        status=ClaimStatus.READY,
    )
    session.add(claim)
    await session.flush()
    if source is not None:
        session.add(ClaimSource(claim_id=claim.id, source_id=source.id, citation_marker="[1]"))
        await session.flush()
    return claim


async def make_evidence(
    session: AsyncSession,
    claim: Claim,
    source: Source,
    *,
    passage: str = "Outcome Y was lower with treatment X (OR 0.80).",
    access_level: AccessLevel = AccessLevel.ABSTRACT,
    rank: int = 0,
) -> Evidence:
    evidence = Evidence(
        claim_id=claim.id,
        source_id=source.id,
        passage=passage,
        location="Abstract — Results",
        access_level=access_level,
        retrieval_method="test",
        retrieval_score=0.5,
        rank=rank,
    )
    session.add(evidence)
    await session.flush()
    return evidence


async def make_assessment(
    session: AsyncSession,
    claim: Claim,
    *,
    verdict: Verdict = Verdict.SUPPORTED,
    confidence: float = 0.8,
    issues: list[dict[str, Any]] | None = None,
    age_seconds: int = 0,
) -> Assessment:
    assessment = Assessment(
        claim_id=claim.id,
        verdict=verdict,
        confidence=confidence,
        issues=issues or [],
        explanation="Test explanation.",
        provider="test",
        created_at=utcnow() - timedelta(seconds=age_seconds),
    )
    session.add(assessment)
    await session.flush()
    return assessment
