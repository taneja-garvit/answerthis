import uuid

from pydantic import Field

from app.domain.enums import DraftAnalysisStatus
from app.schemas.common import APIModel, UTCDateTime

# Hard ceiling on what the API will even parse; the configurable product limit
# (MAX_DRAFT_CHARS) is enforced in the draft service.
HARD_MAX_DRAFT_CHARS = 200_000


class DraftCreate(APIModel):
    original_text: str = Field(max_length=HARD_MAX_DRAFT_CHARS)


class DraftResponse(APIModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_text: str
    char_count: int
    analysis_status: DraftAnalysisStatus
    analyzed_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
