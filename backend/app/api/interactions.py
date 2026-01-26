"""Interactions API endpoints."""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Interaction, Person, CalendarOccurrence
from app.models.interactions import InteractionKind, InteractionChannel


router = APIRouter()


class InteractionSchema(BaseModel):
    """Interaction response schema."""
    id: str
    person_id: Optional[str]
    kind: str
    occurred_at: datetime
    end_at: Optional[datetime]
    direction: Optional[str]
    channel: str
    subject: Optional[str]
    snippet: Optional[str]
    participants: list
    is_automated: bool
    is_bulk: bool
    is_meaningful: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InteractionListResponse(BaseModel):
    """Paginated interactions list."""
    items: List[InteractionSchema]
    total: int
    page: int
    page_size: int
    has_more: bool


class CalendarOccurrenceSchema(BaseModel):
    """Calendar occurrence response schema."""
    id: str
    subject: Optional[str]
    start_at: datetime
    end_at: Optional[datetime]
    location: Optional[str]
    organizer_email: Optional[str]
    participants: list
    is_cancelled: bool
    is_all_day: bool

    class Config:
        from_attributes = True


class UpcomingMeetingsResponse(BaseModel):
    """List of upcoming meetings."""
    items: List[CalendarOccurrenceSchema]


@router.get("", response_model=InteractionListResponse)
async def list_interactions(
    person_id: Optional[str] = None,
    kind: Optional[str] = None,
    channel: Optional[str] = None,
    meaningful_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """List interactions with filtering."""
    query = db.query(Interaction)

    if person_id:
        query = query.filter(Interaction.person_id == person_id)

    if kind:
        try:
            kind_enum = InteractionKind(kind)
            query = query.filter(Interaction.kind == kind_enum)
        except ValueError:
            pass

    if channel:
        try:
            channel_enum = InteractionChannel(channel)
            query = query.filter(Interaction.channel == channel_enum)
        except ValueError:
            pass

    if meaningful_only:
        query = query.filter(Interaction.is_meaningful == True)

    total = query.count()

    # Order by most recent first
    query = query.order_by(desc(Interaction.occurred_at))

    # Pagination
    offset = (page - 1) * page_size
    interactions = query.offset(offset).limit(page_size).all()

    items = [
        InteractionSchema(
            id=i.id,
            person_id=i.person_id,
            kind=i.kind.value,
            occurred_at=i.occurred_at,
            end_at=i.end_at,
            direction=i.direction,
            channel=i.channel.value,
            subject=i.subject,
            snippet=i.snippet,
            participants=i.participants or [],
            is_automated=i.is_automated,
            is_bulk=i.is_bulk,
            is_meaningful=i.is_meaningful,
            created_at=i.created_at
        )
        for i in interactions
    ]

    return InteractionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total
    )


@router.get("/person/{person_id}/timeline", response_model=InteractionListResponse)
async def get_person_timeline(
    person_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get interaction timeline for a specific person."""
    # Verify person exists
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    query = db.query(Interaction).filter(
        Interaction.person_id == person_id
    ).order_by(desc(Interaction.occurred_at))

    total = query.count()
    offset = (page - 1) * page_size
    interactions = query.offset(offset).limit(page_size).all()

    items = [
        InteractionSchema(
            id=i.id,
            person_id=i.person_id,
            kind=i.kind.value,
            occurred_at=i.occurred_at,
            end_at=i.end_at,
            direction=i.direction,
            channel=i.channel.value,
            subject=i.subject,
            snippet=i.snippet,
            participants=i.participants or [],
            is_automated=i.is_automated,
            is_bulk=i.is_bulk,
            is_meaningful=i.is_meaningful,
            created_at=i.created_at
        )
        for i in interactions
    ]

    return InteractionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total
    )


@router.get("/upcoming", response_model=UpcomingMeetingsResponse)
async def get_upcoming_meetings(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get upcoming calendar meetings."""
    from datetime import timedelta, timezone

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days)

    occurrences = db.query(CalendarOccurrence).filter(
        CalendarOccurrence.start_at >= now,
        CalendarOccurrence.start_at <= end_date,
        CalendarOccurrence.is_cancelled == False
    ).order_by(CalendarOccurrence.start_at).limit(limit).all()

    items = [
        CalendarOccurrenceSchema(
            id=o.id,
            subject=o.subject,
            start_at=o.start_at,
            end_at=o.end_at,
            location=o.location,
            organizer_email=o.organizer_email,
            participants=o.participants or [],
            is_cancelled=o.is_cancelled,
            is_all_day=o.is_all_day
        )
        for o in occurrences
    ]

    return UpcomingMeetingsResponse(items=items)


@router.get("/{interaction_id}", response_model=InteractionSchema)
async def get_interaction(
    interaction_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get a single interaction by ID."""
    interaction = db.query(Interaction).filter(Interaction.id == interaction_id).first()

    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")

    return InteractionSchema(
        id=interaction.id,
        person_id=interaction.person_id,
        kind=interaction.kind.value,
        occurred_at=interaction.occurred_at,
        end_at=interaction.end_at,
        direction=interaction.direction,
        channel=interaction.channel.value,
        subject=interaction.subject,
        snippet=interaction.snippet,
        participants=interaction.participants or [],
        is_automated=interaction.is_automated,
        is_bulk=interaction.is_bulk,
        is_meaningful=interaction.is_meaningful,
        created_at=interaction.created_at
    )
