from typing import TYPE_CHECKING

from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from app.domain.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.draft import Draft
    from app.models.source import Source


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (enum_check("status", ProjectStatus),)

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), default=ProjectStatus.ACTIVE, server_default=text("'ACTIVE'")
    )
    # Stable key for seeded projects so seeding is idempotent; NULL for user projects.
    seed_key: Mapped[str | None] = mapped_column(String(100), unique=True)

    drafts: Mapped[list["Draft"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Draft.created_at",
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Project {self.id}>"
