import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import ConfidenceLevel, Verdict

if TYPE_CHECKING:
    from app.models.claim import Claim


class Assessment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An AI (or fixture) assessment of a claim. Append-only: re-assessing adds a
    row, and the newest row is the current assessment."""

    __tablename__ = "assessments"
    __table_args__ = (
        enum_check("verdict", Verdict),
        enum_check("confidence_level", ConfidenceLevel),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_assessments_claim_id_created_at", "claim_id", "created_at"),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(32))
    # Coarse level reported by the assessor (see docs/architecture.md). The
    # numeric column is reserved for providers that expose calibrated scores;
    # it is NULL for LLM and fixture assessments.
    confidence_level: Mapped[str | None] = mapped_column(String(8))
    confidence: Mapped[float | None] = mapped_column(Float)
    # List of {type, description, claim_value, evidence_value}, validated by
    # app.schemas.claim.Issue before it is written.
    issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    explanation: Mapped[str] = mapped_column(Text)
    suggested_revision: Mapped[str | None] = mapped_column(Text)
    # Evidence rows the assessment was based on, for traceability.
    evidence_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    claim: Mapped["Claim"] = relationship(back_populates="assessments")
