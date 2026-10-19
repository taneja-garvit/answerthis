import uuid

from app.schemas.claim import ClaimReviewResponse
from app.schemas.common import APIModel, UTCDateTime
from app.schemas.progress import ProgressResponse
from app.schemas.review import ReviewEventResponse

AUDIT_DISCLAIMER = (
    "AI assessments are suggestions generated to assist human review. They do not "
    "establish scientific truth. Human decisions and notes are the reviewer's own."
)


class AuditProject(APIModel):
    id: uuid.UUID
    title: str
    description: str | None


class AuditClaim(ClaimReviewResponse):
    review_history: list[ReviewEventResponse]


class AuditResponse(APIModel):
    export_version: str = "1"
    generated_at: UTCDateTime
    disclaimer: str = AUDIT_DISCLAIMER
    project: AuditProject
    progress: ProgressResponse
    claims: list[AuditClaim]
