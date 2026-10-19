import uuid

from pydantic import Field, field_validator, model_validator

from app.domain.enums import ReviewDecision
from app.schemas.common import APIModel, UTCDateTime


class ReviewUpsert(APIModel):
    decision: ReviewDecision
    reviewer_note: str | None = Field(default=None, max_length=5000)
    revised_claim: str | None = Field(default=None, max_length=2000)

    @field_validator("reviewer_note", "revised_claim")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _check_revision_rules(self) -> "ReviewUpsert":
        if self.decision == ReviewDecision.REPLACE and self.revised_claim is None:
            raise ValueError("revised_claim is required when decision is REPLACE")
        if (
            self.decision in (ReviewDecision.KEEP, ReviewDecision.REMOVE)
            and self.revised_claim is not None
        ):
            # Rejected rather than silently dropped so no reviewer text is lost.
            raise ValueError(
                f"revised_claim must be empty when decision is {self.decision.value}; "
                "use QUALIFY or REPLACE to revise the claim"
            )
        return self


class ReviewEventResponse(APIModel):
    id: uuid.UUID
    decision: ReviewDecision
    previous_decision: ReviewDecision | None
    reviewer_note: str | None
    revised_claim: str | None
    assessment_id: uuid.UUID | None
    created_at: UTCDateTime
