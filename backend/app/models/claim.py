import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import ClaimStatus

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.draft import Draft
    from app.models.evidence import Evidence
    from app.models.review import Review
    from app.models.source import Source


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        enum_check("status", ClaimStatus),
        UniqueConstraint("draft_id", "position", name="uq_claims_draft_id_position"),
    )

    # Indexed through uq_claims_draft_id_position (draft_id is its leading column).
    draft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)  # 1-based order within the draft
    claim_text: Mapped[str] = mapped_column(Text)
    original_sentence: Mapped[str] = mapped_column(Text)
    citation_marker: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32), default=ClaimStatus.PENDING, server_default=text("'PENDING'")
    )
    # Short, user-safe reason when status is ERROR (e.g. provider rate limit).
    processing_error: Mapped[str | None] = mapped_column(Text)

    draft: Mapped["Draft"] = relationship(back_populates="claims")
    citations: Mapped[list["ClaimSource"]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClaimSource.position",
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Evidence.rank",
    )
    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Assessment.created_at",
    )
    review: Mapped["Review | None"] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Claim {self.id}>"


class ClaimSource(CreatedAtMixin, Base):
    """Which sources a claim cites. Many-to-many so multi-citation claims need no
    migration; the MVP pipeline analyses the first (position 0) as primary."""

    __tablename__ = "claim_sources"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    citation_marker: Mapped[str | None] = mapped_column(String(64))

    claim: Mapped["Claim"] = relationship(back_populates="citations")
    source: Mapped["Source"] = relationship()
