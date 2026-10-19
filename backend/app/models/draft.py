import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import DraftAnalysisStatus

if TYPE_CHECKING:
    from app.models.claim import Claim
    from app.models.project import Project


class Draft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drafts"
    __table_args__ = (enum_check("analysis_status", DraftAnalysisStatus),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    original_text: Mapped[str] = mapped_column(Text)
    analysis_status: Mapped[str] = mapped_column(
        String(32),
        default=DraftAnalysisStatus.NOT_ANALYZED,
        server_default=text("'NOT_ANALYZED'"),
    )
    analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped["Project"] = relationship(back_populates="drafts")
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Claim.position",
    )

    def __repr__(self) -> str:
        return f"<Draft {self.id}>"
