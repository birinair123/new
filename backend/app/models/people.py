"""People-related models."""
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, func
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class PersonOrigin(str, enum.Enum):
    """Origin of a person record."""
    LINKEDIN = "linkedin"
    MANUAL = "manual"
    PROMOTED = "promoted"
    EMAIL_ONLY = "email_only"


class Person(Base, UUIDMixin, TimestampMixin):
    """A person/contact in the CRM."""

    __tablename__ = "people"

    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_email: Mapped[Optional[str]] = mapped_column(Text)
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text)
    linkedin_id: Mapped[Optional[str]] = mapped_column(Text)
    company: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    origin: Mapped[PersonOrigin] = mapped_column(
        Enum(PersonOrigin, name="person_origin", values_callable=lambda x: [e.value for e in x]),
        default=PersonOrigin.EMAIL_ONLY
    )
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    linkedin_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    emails: Mapped[list["PersonEmail"]] = relationship(
        "PersonEmail", back_populates="person", cascade="all, delete-orphan"
    )
    interactions: Mapped[list["Interaction"]] = relationship(
        "Interaction", back_populates="person", cascade="all, delete-orphan"
    )
    score: Mapped[Optional["PersonScore"]] = relationship(
        "PersonScore", back_populates="person", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Person {self.full_name} ({self.origin.value})>"


class PersonEmail(Base, UUIDMixin):
    """Email addresses associated with a person."""

    __tablename__ = "person_emails"

    person_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    person: Mapped["Person"] = relationship("Person", back_populates="emails")

    def __repr__(self) -> str:
        return f"<PersonEmail {self.email}>"


class PersonScore(Base):
    """Cached connection strength scores for a person."""

    __tablename__ = "person_scores"

    person_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_inbound_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_outbound_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_meeting_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_meeting_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    person: Mapped["Person"] = relationship("Person", back_populates="score")

    def __repr__(self) -> str:
        return f"<PersonScore person_id={self.person_id} score={self.score_total}>"


# Import Interaction at the end to avoid circular imports
from .interactions import Interaction
