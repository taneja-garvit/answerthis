import uuid
from typing import Literal

from pydantic import Field, field_validator

from app.domain.enums import DraftAnalysisStatus
from app.schemas.claim import ClaimReviewResponse
from app.schemas.common import APIModel
from app.services.citations import normalize_doi


class AnalyzeRequest(APIModel):
    mode: Literal["resume", "reextract"] = "resume"
    # Optional explicit mapping from numeric citation marker to DOI, e.g.
    # {"1": "10.1002/ejhf.3568"}. Overrides the draft's reference list.
    citations: dict[str, str] = Field(default_factory=dict, max_length=200)
    refresh_metadata: bool = False

    @field_validator("citations")
    @classmethod
    def _normalize(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for marker, raw in value.items():
            key = marker.strip().strip("[]").strip()
            if not key.isdigit():
                raise ValueError(f"citation marker {marker!r} must be a number such as '1'")
            doi = normalize_doi(raw)
            if doi is None:
                raise ValueError(f"{raw!r} is not a valid DOI")
            normalized[str(int(key))] = doi
        return normalized


class ReassessRequest(APIModel):
    refresh_metadata: bool = False


class AnalysisResponse(APIModel):
    draft_id: uuid.UUID
    project_id: uuid.UUID
    analysis_status: DraftAnalysisStatus
    rerun: bool  # claims already existed before this request
    claims_extracted: int  # claims the draft now has
    claims_processed: int  # claims (re)processed by this request
    claims_reused: int  # claims left untouched because they were already assessed
    claims_assessed: int  # claims with at least one assessment
    claims_unverifiable: int  # latest assessment is UNVERIFIABLE
    claims_failed: int  # status ERROR; re-run to retry
    llm_provider: str
    llm_model: str | None
    llm_calls: int
    claims: list[ClaimReviewResponse]
