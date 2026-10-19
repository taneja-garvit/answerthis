import uuid

from pydantic import Field, field_validator

from app.domain.enums import DraftAnalysisStatus, ProjectStatus
from app.schemas.common import APIModel, UTCDateTime


class ProjectCreate(APIModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class DraftSummary(APIModel):
    id: uuid.UUID
    char_count: int
    claim_count: int
    analysis_status: DraftAnalysisStatus
    created_at: UTCDateTime


class ProjectResponse(APIModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: ProjectStatus
    is_demo: bool
    drafts: list[DraftSummary]
    created_at: UTCDateTime
    updated_at: UTCDateTime
