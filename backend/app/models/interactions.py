"""Interaction and calendar models."""
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class InteractionKind(str, enum.Enum):
    """Type of interaction."""
    EMAIL_IN = "email_in"
    EMAIL_OUT = "email_out"
    MEETING = "meeting"
    LINKEDIN_CONNECT = "linkedin_connect"
    NOTE = "note"


class InteractionChannel(str, enum.Enum):
    """Source channel of interaction."""
    IMAP = "imap"
    OST = "ost"
    CALENDAR = "calendar"
    LINKEDIN = "linkedin"
    MANUAL = "manual"


class Interaction(Base, UUIDMixin):
    """A single interaction with a person."""

    __tablename__ = "interactions"

    person_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("people.id", ondelete="CASCADE")
    )
    kind: Mapped[InteractionKind] = mapped_column(
        Enum(InteractionKind, name="interaction_kind"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    direction: Mapped[Optional[str]] = mapped_column(Text)  # 'inbound', 'outbound'
    channel: Mapped[InteractionChannel] = mapped_column(
        Enum(InteractionChannel, name="interaction_channel"), nullable=False
    )
    subject: Mapped[Optional[str]] = mapped_column(Text)
    snippet: Mapped[Optional[str]] = mapped_column(Text)
    participants: Mapped[dict] = mapped_column(JSONB, default=list)
    external_id: Mapped[Optional[str]] = mapped_column(Text)
    source_account: Mapped[Optional[str]] = mapped_column(Text)
    raw_ref: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Derived flags
    is_automated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bulk: Mapped[bool] = mapped_column(Boolean, default=False)
    is_meaningful: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="interactions")

    def __repr__(self) -> str:
        return f"<Interaction {self.kind.value} at {self.occurred_at}>"


class CalendarSeries(Base, UUIDMixin, TimestampMixin):
    """A recurring calendar series definition."""

    __tablename__ = "calendar_series"

    source_series_id: Mapped[str] = mapped_column(Text, nullable=False)
    organizer_email: Mapped[Optional[str]] = mapped_column(Text)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="UTC")
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rrule: Mapped[Optional[str]] = mapped_column(Text)
    recurrence_blob: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_account: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    occurrences: Mapped[list["CalendarOccurrence"]] = relationship(
        "CalendarOccurrence", back_populates="series"
    )

    def __repr__(self) -> str:
        return f"<CalendarSeries {self.subject}>"


class CalendarOccurrence(Base, UUIDMixin, TimestampMixin):
    """A single calendar event occurrence."""

    __tablename__ = "calendar_occurrences"

    series_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("calendar_series.id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(Text)
    organizer_email: Mapped[Optional[str]] = mapped_column(Text)
    participants: Mapped[list] = mapped_column(JSONB, default=list)
    is_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    source_account: Mapped[Optional[str]] = mapped_column(Text)
    raw_ref: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Relationships
    series: Mapped[Optional["CalendarSeries"]] = relationship(
        "CalendarSeries", back_populates="occurrences"
    )

    def __repr__(self) -> str:
        return f"<CalendarOccurrence {self.subject} at {self.start_at}>"


# Import Person at the end to avoid circular imports
from .people import Person
