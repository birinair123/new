"""System and administrative models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class IngestionCheckpoint(Base, UUIDMixin, TimestampMixin):
    """Track progress for incremental imports."""

    __tablename__ = "ingestion_checkpoints"

    source: Mapped[str] = mapped_column(Text, nullable=False)  # 'imap', 'ost_calendar', etc.
    account: Mapped[str] = mapped_column(Text, nullable=False)
    folder: Mapped[Optional[str]] = mapped_column(Text)
    checkpoint_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<IngestionCheckpoint {self.source}:{self.account}>"


class ReviewQueue(Base, UUIDMixin):
    """Queue for unlinked contacts and match suggestions."""

    __tablename__ = "review_queue"

    person_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    queue_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'promote', 'link_suggestion'
    suggested_person_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("people.id", ondelete="CASCADE")
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    match_reason: Mapped[Optional[dict]] = mapped_column(JSONB)
    interaction_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending, accepted, rejected, ignored
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[person_id]
    )
    suggested_person: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[suggested_person_id]
    )

    def __repr__(self) -> str:
        return f"<ReviewQueue {self.queue_type} for person_id={self.person_id}>"


class Setting(Base):
    """Application settings (key-value store)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Setting {self.key}>"


class AuthSession(Base, UUIDMixin):
    """Session tokens for authentication."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuthSession expires={self.expires_at}>"


# Import Person at the end to avoid circular imports
from .people import Person
