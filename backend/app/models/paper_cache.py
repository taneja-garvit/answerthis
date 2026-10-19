from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class PaperCache(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provider metadata cached across projects, keyed by normalized (lowercase) DOI."""

    __tablename__ = "paper_cache"

    doi: Mapped[str] = mapped_column(String(255), unique=True)
    # Provider-independent shape consumed by citation resolution.
    normalized: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Raw (or trimmed) payload per provider name, kept for debugging/reprocessing.
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    providers: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text)
