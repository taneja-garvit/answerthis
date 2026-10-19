import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import ReviewDecision

if TYPE_CHECKING:
    from app.models.claim import Claim


class Review(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The current human decision for a claim (at most one per claim)."""

    __tablename__ = "reviews"
    __table_args__ = (enum_check("decision", ReviewDecision),)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), unique=True
    )
    decision: Mapped[str] = mapped_column(String(16))
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    revised_claim: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    claim: Mapped["Claim"] = relationship(back_populates="review")


class ReviewEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable history: one row per saved decision. Never updated or deleted
    by application code."""

    __tablename__ = "review_events"
    __table_args__ = (
        enum_check("decision", ReviewDecision),
        enum_check("previous_decision", ReviewDecision, name="previous_decision"),
        Index("ix_review_events_claim_id_created_at", "claim_id", "created_at"),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))
    previous_decision: Mapped[str | None] = mapped_column(String(16))
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    revised_claim: Mapped[str | None] = mapped_column(Text)
    # The assessment the reviewer was looking at when deciding.
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL")
    )
