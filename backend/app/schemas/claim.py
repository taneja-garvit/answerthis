import uuid
from typing import Any

from pydantic import Field

from app.domain.enums import (
    AccessLevel,
    ClaimStatus,
    ConfidenceLevel,
    EvidenceAvailability,
    IssueType,
    ReviewDecision,
    ReviewStatus,
    SourceAccessStatus,
    Verdict,
)
from app.schemas.common import APIModel, UTCDateTime


class Issue(APIModel):
    """One potential problem the assessor flagged. Stored as JSONB on Assessment."""

    type: IssueType
    description: str = Field(min_length=1, max_length=2000)
    claim_value: str | None = Field(default=None, max_length=500)
    evidence_value: str | None = Field(default=None, max_length=500)


class SourceSummary(APIModel):
    id: uuid.UUID
    doi: str | None
    title: str
    authors: list[dict[str, Any]]
    journal: str | None
    publication_year: int | None
    open_access_url: str | None
    access_status: SourceAccessStatus
    citation_marker: str | None = None


class EvidenceResponse(APIModel):
    id: uuid.UUID
    source_id: uuid.UUID
    passage: str
    location: str | None
    access_level: AccessLevel
    retrieval_method: str
    # Lexical relevance of the passage to the claim; not evidence of support.
    retrieval_score: float | None
    rank: int
    is_synthetic: bool


class EvidenceAvailabilityResponse(APIModel):
    status: EvidenceAvailability
    message: str


class AssessmentResponse(APIModel):
    id: uuid.UUID
    verdict: Verdict
    # Confidence in the claim-vs-evidence classification, not in the science.
    # NULL for rule-based outcomes, where no model judgement was made.
    confidence_level: ConfidenceLevel | None
    confidence: float | None
    issues: list[Issue]
    explanation: str
    suggested_revision: str | None
    evidence_ids: list[uuid.UUID]
    provider: str
    model: str | None
    prompt_version: str | None
    generation_metadata: dict[str, Any]
    created_at: UTCDateTime


class ReviewResponse(APIModel):
    id: uuid.UUID
    decision: ReviewDecision
    reviewer_note: str | None
    revised_claim: str | None
    reviewed_at: UTCDateTime
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ClaimReviewResponse(APIModel):
    """Everything the review screen needs for one claim, in one response."""

    id: uuid.UUID
    draft_id: uuid.UUID
    project_id: uuid.UUID
    order: int
    claim_text: str
    original_sentence: str
    citation_marker: str | None
    status: ClaimStatus
    processing_error: str | None
    source: SourceSummary | None
    sources: list[SourceSummary]
    evidence: list[EvidenceResponse]
    evidence_availability: EvidenceAvailabilityResponse
    assessment: AssessmentResponse | None
    review: ReviewResponse | None
    review_status: ReviewStatus


class DraftClaimsResponse(APIModel):
    draft_id: uuid.UUID
    project_id: uuid.UUID
    claims: list[ClaimReviewResponse]
