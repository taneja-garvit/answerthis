from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

# Timestamps are always emitted in UTC, whatever the database session timezone.
UTCDateTime = Annotated[datetime, AfterValidator(lambda value: value.astimezone(UTC))]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
