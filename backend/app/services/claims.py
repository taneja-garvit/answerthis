import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError
from app.domain.enums import AccessLevel, EvidenceAvailability, ReviewStatus, SourceAccessStatus
from app.models import Assessment, Claim, Draft, Evidence
from app.repositories import claims as claims_repo
from app.schemas.claim import (
    AssessmentResponse,
    ClaimReviewResponse,
    DraftClaimsResponse,
    EvidenceAvailabilityResponse,
    EvidenceResponse,
    ReviewResponse,
    SourceSummary,
)

_AVAILABILITY_MESSAGES = {
    EvidenceAvailability.FULL_TEXT: "Evidence was retrieved from open-access full text.",
    EvidenceAvailability.USER_PROVIDED: "Evidence comes from text supplied by the user.",
    EvidenceAvailability.ABSTRACT: (
        "Assessment limited to the public abstract; the full text was not reviewed."
    ),
}


def latest_assessment(claim: Claim) -> Assessment | None:
    if not claim.assessments:
        return None
    return max(claim.assessments, key=lambda a: (a.created_at, str(a.id)))


def current_evidence(claim: Claim) -> list[Evidence]:
    """Passages from the latest retrieval run. Superseded rows stay in the
    database for the assessments that cited them, but are not shown."""
    return [e for e in claim.evidence if e.is_current]


def evidence_availability(claim: Claim) -> EvidenceAvailabilityResponse:
    """Say plainly what evidence the assessment could rely on. Absence of
    evidence is reported as UNAVAILABLE, never papered over."""
    evidence = current_evidence(claim)
    if evidence:
        levels = {e.access_level for e in evidence}
        for level, status in (
            (AccessLevel.FULL_TEXT, EvidenceAvailability.FULL_TEXT),
            (AccessLevel.USER_PROVIDED, EvidenceAvailability.USER_PROVIDED),
            (AccessLevel.ABSTRACT, EvidenceAvailability.ABSTRACT),
        ):
            if level in levels:
                message = _AVAILABILITY_MESSAGES[status]
                if any(e.is_synthetic for e in evidence):
                    message += (
                        " Includes clearly labelled synthetic text that is not from the source."
                    )
                return EvidenceAvailabilityResponse(status=status, message=message)

    primary = claim.citations[0].source if claim.citations else None
    if primary is None:
        message = "Full supporting evidence is unavailable: no source is linked to this claim."
    elif primary.access_status == SourceAccessStatus.UNAVAILABLE:
        message = (
            "Full supporting evidence is unavailable: the source's text could not be accessed. "
            "Assessment limited to available metadata."
        )
    else:
        message = (
            "Full supporting evidence is unavailable: no relevant passage was found in the "
            "accessible text."
        )
    return EvidenceAvailabilityResponse(status=EvidenceAvailability.UNAVAILABLE, message=message)


def to_claim_review_response(claim: Claim) -> ClaimReviewResponse:
    sources = [
        SourceSummary.model_validate(link.source).model_copy(
            update={"citation_marker": link.citation_marker}
        )
        for link in claim.citations
    ]
    assessment = latest_assessment(claim)
    return ClaimReviewResponse(
        id=claim.id,
        draft_id=claim.draft_id,
        project_id=claim.draft.project_id,
        order=claim.position,
        claim_text=claim.claim_text,
        original_sentence=claim.original_sentence,
        citation_marker=claim.citation_marker,
        status=claim.status,
        processing_error=claim.processing_error,
        source=sources[0] if sources else None,
        sources=sources,
        evidence=[EvidenceResponse.model_validate(e) for e in current_evidence(claim)],
        evidence_availability=evidence_availability(claim),
        assessment=AssessmentResponse.model_validate(assessment) if assessment else None,
        review=ReviewResponse.model_validate(claim.review) if claim.review else None,
        review_status=ReviewStatus.REVIEWED if claim.review else ReviewStatus.NEEDS_REVIEW,
    )


async def get_claim_review(session: AsyncSession, claim_id: uuid.UUID) -> ClaimReviewResponse:
    claim = await claims_repo.get_claim(session, claim_id)
    if claim is None:
        raise NotFoundError("Claim not found")
    return to_claim_review_response(claim)


async def list_draft_claims(session: AsyncSession, draft_id: uuid.UUID) -> DraftClaimsResponse:
    draft = await session.get(Draft, draft_id)
    if draft is None:
        raise NotFoundError("Draft not found")
    claims = await claims_repo.list_claims_for_draft(session, draft_id)
    return DraftClaimsResponse(
        draft_id=draft.id,
        project_id=draft.project_id,
        claims=[to_claim_review_response(c) for c in claims],
    )
