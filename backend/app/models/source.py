import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import SourceAccessStatus

if TYPE_CHECKING:
    from app.models.project import Project


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A cited work, scoped to one project. Global cached metadata lives in PaperCache."""

    __tablename__ = "sources"
    __table_args__ = (
        enum_check("access_status", SourceAccessStatus),
        # One source row per DOI per project; sources without a DOI are allowed.
        Index(
            "uq_sources_project_id_doi",
            "project_id",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    doi: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    journal: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    abstract: Mapped[str | None] = mapped_column(Text)
    open_access_url: Mapped[str | None] = mapped_column(Text)
    access_status: Mapped[str] = mapped_column(String(32))
    # `metadata` is reserved on declarative classes, so the attribute is renamed.
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    project: Mapped["Project"] = relationship(back_populates="sources")

    def __repr__(self) -> str:
        return f"<Source {self.id}>"
