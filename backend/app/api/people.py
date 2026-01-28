"""People API endpoints."""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Person, PersonEmail, PersonScore, Interaction
from app.models.people import PersonOrigin


router = APIRouter()


# Pydantic schemas
class PersonEmailSchema(BaseModel):
    """Email address schema."""
    email: str
    is_primary: bool = False


class PersonScoreSchema(BaseModel):
    """Person score schema."""
    score_total: int
    score_breakdown: dict
    last_interaction_at: Optional[datetime]
    last_meeting_at: Optional[datetime]
    next_meeting_at: Optional[datetime]
    first_interaction_at: Optional[datetime]


class PersonBase(BaseModel):
    """Base person schema."""
    full_name: str
    primary_email: Optional[str] = None
    linkedin_url: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None


class PersonCreate(PersonBase):
    """Schema for creating a person."""
    origin: str = "manual"
    is_tracked: bool = True


class PersonUpdate(BaseModel):
    """Schema for updating a person."""
    full_name: Optional[str] = None
    primary_email: Optional[str] = None
    linkedin_url: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    is_tracked: Optional[bool] = None


class PersonResponse(PersonBase):
    """Person response schema."""
    id: str
    origin: str
    is_tracked: bool
    linkedin_connected_at: Optional[datetime]
    promoted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    emails: List[PersonEmailSchema] = []
    score: Optional[PersonScoreSchema] = None

    class Config:
        from_attributes = True


class PersonListResponse(BaseModel):
    """Paginated list of people."""
    items: List[PersonResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


@router.get("", response_model=PersonListResponse)
async def list_people(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    tracked_only: bool = True,
    origin: Optional[str] = None,
    sort_by: str = Query("score", pattern="^(score|name|last_interaction|created)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    List people with filtering and pagination.
    Default shows only tracked (LinkedIn) + promoted people.
    """
    # Base query for filtering (without eager loading for count)
    base_query = db.query(Person)

    # Filter by tracked status
    if tracked_only:
        base_query = base_query.filter(Person.is_tracked == True)

    # Filter by origin
    if origin:
        try:
            origin_enum = PersonOrigin(origin)
            base_query = base_query.filter(Person.origin == origin_enum)
        except ValueError:
            pass

    # Search by name, email, or company
    if search:
        search_term = f"%{search}%"
        base_query = base_query.filter(
            or_(
                Person.full_name.ilike(search_term),
                Person.primary_email.ilike(search_term),
                Person.company.ilike(search_term)
            )
        )

    # Get total count (before joins/eager loading)
    total = base_query.count()

    # Now build the query with sorting
    if sort_by == "score":
        base_query = base_query.outerjoin(PersonScore, Person.id == PersonScore.person_id)
        order_col = PersonScore.score_total
    elif sort_by == "name":
        order_col = Person.full_name
    elif sort_by == "last_interaction":
        base_query = base_query.outerjoin(PersonScore, Person.id == PersonScore.person_id)
        order_col = PersonScore.last_interaction_at
    else:
        order_col = Person.created_at

    if sort_order == "desc":
        base_query = base_query.order_by(order_col.desc().nullslast())
    else:
        base_query = base_query.order_by(order_col.asc().nullsfirst())

    # Pagination
    offset = (page - 1) * page_size

    # Get IDs first, then load with relationships to avoid cartesian product
    person_ids = [p.id for p in base_query.offset(offset).limit(page_size).all()]

    # Now load full objects with relationships
    if person_ids:
        people = db.query(Person).options(
            joinedload(Person.emails),
            joinedload(Person.score)
        ).filter(Person.id.in_(person_ids)).all()

        # Re-sort since IN query doesn't preserve order
        id_order = {pid: idx for idx, pid in enumerate(person_ids)}
        people = sorted(people, key=lambda p: id_order.get(p.id, 0))
    else:
        people = []

    # Build response
    items = []
    for person in people:
        person_data = PersonResponse(
            id=person.id,
            full_name=person.full_name,
            primary_email=person.primary_email,
            linkedin_url=person.linkedin_url,
            company=person.company,
            title=person.title,
            tags=person.tags or [],
            notes=person.notes,
            origin=person.origin.value,
            is_tracked=person.is_tracked,
            linkedin_connected_at=person.linkedin_connected_at,
            promoted_at=person.promoted_at,
            created_at=person.created_at,
            updated_at=person.updated_at,
            emails=[PersonEmailSchema(email=e.email, is_primary=e.is_primary) for e in person.emails],
            score=PersonScoreSchema(
                score_total=person.score.score_total,
                score_breakdown=person.score.score_breakdown,
                last_interaction_at=person.score.last_interaction_at,
                last_meeting_at=person.score.last_meeting_at,
                next_meeting_at=person.score.next_meeting_at,
                first_interaction_at=person.score.first_interaction_at
            ) if person.score else None
        )
        items.append(person_data)

    return PersonListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total
    )


@router.get("/{person_id}", response_model=PersonResponse)
async def get_person(
    person_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get a single person by ID."""
    person = db.query(Person).options(
        joinedload(Person.emails),
        joinedload(Person.score)
    ).filter(Person.id == person_id).first()

    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    return PersonResponse(
        id=person.id,
        full_name=person.full_name,
        primary_email=person.primary_email,
        linkedin_url=person.linkedin_url,
        company=person.company,
        title=person.title,
        tags=person.tags or [],
        notes=person.notes,
        origin=person.origin.value,
        is_tracked=person.is_tracked,
        linkedin_connected_at=person.linkedin_connected_at,
        promoted_at=person.promoted_at,
        created_at=person.created_at,
        updated_at=person.updated_at,
        emails=[PersonEmailSchema(email=e.email, is_primary=e.is_primary) for e in person.emails],
        score=PersonScoreSchema(
            score_total=person.score.score_total,
            score_breakdown=person.score.score_breakdown,
            last_interaction_at=person.score.last_interaction_at,
            last_meeting_at=person.score.last_meeting_at,
            next_meeting_at=person.score.next_meeting_at,
            first_interaction_at=person.score.first_interaction_at
        ) if person.score else None
    )


@router.post("", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
async def create_person(
    person_data: PersonCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Create a new person manually."""
    try:
        origin = PersonOrigin(person_data.origin)
    except ValueError:
        origin = PersonOrigin.MANUAL

    person = Person(
        id=str(uuid4()),
        full_name=person_data.full_name,
        primary_email=person_data.primary_email,
        linkedin_url=person_data.linkedin_url,
        company=person_data.company,
        title=person_data.title,
        tags=person_data.tags,
        notes=person_data.notes,
        origin=origin,
        is_tracked=person_data.is_tracked
    )

    db.add(person)

    # Add primary email to person_emails if provided
    if person_data.primary_email:
        email_record = PersonEmail(
            id=str(uuid4()),
            person_id=person.id,
            email=person_data.primary_email,
            is_primary=True,
            source="manual"
        )
        db.add(email_record)

    db.commit()
    db.refresh(person)

    return PersonResponse(
        id=person.id,
        full_name=person.full_name,
        primary_email=person.primary_email,
        linkedin_url=person.linkedin_url,
        company=person.company,
        title=person.title,
        tags=person.tags or [],
        notes=person.notes,
        origin=person.origin.value,
        is_tracked=person.is_tracked,
        linkedin_connected_at=person.linkedin_connected_at,
        promoted_at=person.promoted_at,
        created_at=person.created_at,
        updated_at=person.updated_at,
        emails=[],
        score=None
    )


@router.patch("/{person_id}", response_model=PersonResponse)
async def update_person(
    person_id: str,
    updates: PersonUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Update a person."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(person, field, value)

    db.commit()
    db.refresh(person)

    # Reload with relationships
    person = db.query(Person).options(
        joinedload(Person.emails),
        joinedload(Person.score)
    ).filter(Person.id == person_id).first()

    return PersonResponse(
        id=person.id,
        full_name=person.full_name,
        primary_email=person.primary_email,
        linkedin_url=person.linkedin_url,
        company=person.company,
        title=person.title,
        tags=person.tags or [],
        notes=person.notes,
        origin=person.origin.value,
        is_tracked=person.is_tracked,
        linkedin_connected_at=person.linkedin_connected_at,
        promoted_at=person.promoted_at,
        created_at=person.created_at,
        updated_at=person.updated_at,
        emails=[PersonEmailSchema(email=e.email, is_primary=e.is_primary) for e in person.emails],
        score=PersonScoreSchema(
            score_total=person.score.score_total,
            score_breakdown=person.score.score_breakdown,
            last_interaction_at=person.score.last_interaction_at,
            last_meeting_at=person.score.last_meeting_at,
            next_meeting_at=person.score.next_meeting_at,
            first_interaction_at=person.score.first_interaction_at
        ) if person.score else None
    )


@router.post("/{person_id}/promote")
async def promote_person(
    person_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Promote an email-only person to tracked."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if person.is_tracked:
        return {"message": "Person is already tracked"}

    person.origin = PersonOrigin.PROMOTED
    person.is_tracked = True
    person.promoted_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Person promoted to tracked", "person_id": person_id}


@router.post("/{person_id}/tags")
async def add_tag(
    person_id: str,
    tag: str = Query(...),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Add a tag to a person."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if person.tags is None:
        person.tags = []

    if tag not in person.tags:
        person.tags = person.tags + [tag]
        db.commit()

    return {"tags": person.tags}


@router.delete("/{person_id}/tags")
async def remove_tag(
    person_id: str,
    tag: str = Query(...),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Remove a tag from a person."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if person.tags and tag in person.tags:
        person.tags = [t for t in person.tags if t != tag]
        db.commit()

    return {"tags": person.tags}
