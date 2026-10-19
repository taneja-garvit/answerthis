import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, false, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import AccessLevel

if TYPE_CHECKING:
    from app.models.claim import Claim
    from app.models.source import Source


class Evidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A passage from a source, retrieved for a claim. Linked to both so a claim
    can accumulate evidence from several sources."""

    __tablename__ = "evidence"
    __table_args__ = (enum_check("access_level", AccessLevel),)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    passage: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    access_level: Mapped[str] = mapped_column(String(32))
    # How the passage was obtained, e.g. "seed_fixture" or "bm25_v1".
    retrieval_method: Mapped[str] = mapped_column(String(64))
    # Lexical relevance only; never a measure of scientific support.
    retrieval_score: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # True only for clearly labelled synthetic text that is not from the source.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # False once a later retrieval run superseded this passage. Kept (not
    # deleted) because older assessments reference it in their evidence_ids.
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    claim: Mapped["Claim"] = relationship(back_populates="evidence")
    source: Mapped["Source"] = relationship()
