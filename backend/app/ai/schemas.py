"""Pydantic schemas every LLM response must satisfy before it is used."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import ConfidenceLevel, Verdict
from app.schemas.claim import Issue


def _upper_snake(value: object) -> object:
    # Accept "figure mismatch" / "Figure_Mismatch"; reject anything else via the enum.
    return (
        value.strip().upper().replace(" ", "_").replace("-", "_")
        if isinstance(value, str)
        else value
    )


class LLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ExtractedClaim(LLMOutput):
    sentence_id: str = Field(pattern=r"^S\d{1,5}$")
    claim_text: str = Field(min_length=3, max_length=1000)


class ExtractionOutput(LLMOutput):
    claims: list[ExtractedClaim] = Field(max_length=300)


class AssessmentIssue(Issue):
    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: object) -> object:
        return _upper_snake(value)


class AssessmentOutput(LLMOutput):
    verdict: Verdict
    confidence_level: ConfidenceLevel
    issues: list[AssessmentIssue] = Field(default_factory=list, max_length=10)
    explanation: str = Field(min_length=1, max_length=4000)
    suggested_revision: str | None = Field(default=None, max_length=2000)
    evidence_used: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("verdict", "confidence_level", mode="before")
    @classmethod
    def _normalize_enum(cls, value: object) -> object:
        return _upper_snake(value)

    @field_validator("suggested_revision", mode="before")
    @classmethod
    def _blank_revision(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value
