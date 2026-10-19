import uuid

from app.schemas.common import APIModel


class DecisionCounts(APIModel):
    KEEP: int = 0
    QUALIFY: int = 0
    REPLACE: int = 0
    REMOVE: int = 0


class VerdictCounts(APIModel):
    SUPPORTED: int = 0
    PARTIALLY_SUPPORTED: int = 0
    UNSUPPORTED: int = 0
    UNVERIFIABLE: int = 0
    NOT_ASSESSED: int = 0


class ProgressResponse(APIModel):
    project_id: uuid.UUID
    total_claims: int
    reviewed_claims: int
    remaining_claims: int
    completion_percentage: float
    is_complete: bool
    # Kept separate on purpose: what the human decided vs what the AI suggested.
    human_decisions: DecisionCounts
    ai_verdicts: VerdictCounts
