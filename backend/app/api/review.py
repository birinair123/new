"""Review queue API endpoints."""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import ReviewQueue, Person, PersonScore
from app.models.people import PersonOrigin


router = APIRouter()


class PersonSummary(BaseModel):
    """Brief person info for review queue."""
    id: str
    full_name: str
    primary_email: Optional[str]
    company: Optional[str]
    origin: str
    is_tracked: bool


class ReviewItemSchema(BaseModel):
    """Review queue item schema."""
    id: str
    queue_type: str
    person: PersonSummary
    suggested_person: Optional[PersonSummary]
    confidence_score: Optional[float]
    match_reason: Optional[dict]
    interaction_count: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    """Paginated review queue list."""
    items: List[ReviewItemSchema]
    total: int
    page: int
    page_size: int


class ReviewActionRequest(BaseModel):
    """Request body for review actions."""
    action: str  # 'accept', 'reject', 'ignore'


@router.get("", response_model=ReviewListResponse)
async def list_review_queue(
    queue_type: Optional[str] = None,
    status: str = "pending",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """List items in the review queue."""
    query = db.query(ReviewQueue).options(
        joinedload(ReviewQueue.person),
        joinedload(ReviewQueue.suggested_person)
    ).filter(ReviewQueue.status == status)

    if queue_type:
        query = query.filter(ReviewQueue.queue_type == queue_type)

    # Order by interaction count (most active first)
    query = query.order_by(ReviewQueue.interaction_count.desc())

    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()

    result_items = []
    for item in items:
        result_items.append(ReviewItemSchema(
            id=item.id,
            queue_type=item.queue_type,
            person=PersonSummary(
                id=item.person.id,
                full_name=item.person.full_name,
                primary_email=item.person.primary_email,
                company=item.person.company,
                origin=item.person.origin.value,
                is_tracked=item.person.is_tracked
            ),
            suggested_person=PersonSummary(
                id=item.suggested_person.id,
                full_name=item.suggested_person.full_name,
                primary_email=item.suggested_person.primary_email,
                company=item.suggested_person.company,
                origin=item.suggested_person.origin.value,
                is_tracked=item.suggested_person.is_tracked
            ) if item.suggested_person else None,
            confidence_score=item.confidence_score,
            match_reason=item.match_reason,
            interaction_count=item.interaction_count,
            status=item.status,
            created_at=item.created_at
        ))

    return ReviewListResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/{item_id}/action")
async def review_action(
    item_id: str,
    request: ReviewActionRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Take action on a review queue item.
    Actions:
    - accept: For 'promote' type, promotes the person. For 'link_suggestion', merges contacts.
    - reject: Mark as rejected (won't show again)
    - ignore: Mark as ignored (can be reviewed later)
    """
    item = db.query(ReviewQueue).filter(ReviewQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    if item.status != "pending":
        raise HTTPException(status_code=400, detail="Item already reviewed")

    action = request.action.lower()

    if action == "accept":
        if item.queue_type == "promote":
            # Promote the email-only person
            person = db.query(Person).filter(Person.id == item.person_id).first()
            if person:
                person.origin = PersonOrigin.PROMOTED
                person.is_tracked = True
                person.promoted_at = datetime.now(timezone.utc)

        elif item.queue_type == "link_suggestion" and item.suggested_person_id:
            # Merge interactions from email-only person to LinkedIn person
            from app.models import Interaction
            db.query(Interaction).filter(
                Interaction.person_id == item.person_id
            ).update({Interaction.person_id: item.suggested_person_id})

            # Delete the email-only person (cascade will clean up emails, scores)
            db.query(Person).filter(Person.id == item.person_id).delete()

        item.status = "accepted"

    elif action == "reject":
        item.status = "rejected"

    elif action == "ignore":
        item.status = "ignored"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": f"Review item {action}ed", "item_id": item_id}


@router.get("/stats")
async def get_review_stats(
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get statistics about the review queue."""
    from sqlalchemy import func

    stats = db.query(
        ReviewQueue.queue_type,
        ReviewQueue.status,
        func.count(ReviewQueue.id)
    ).group_by(
        ReviewQueue.queue_type,
        ReviewQueue.status
    ).all()

    result = {}
    for queue_type, status, count in stats:
        if queue_type not in result:
            result[queue_type] = {}
        result[queue_type][status] = count

    # Count email-only people with significant interactions
    from datetime import timedelta
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

    high_signal_unlinked = db.query(func.count(Person.id)).filter(
        Person.origin == PersonOrigin.EMAIL_ONLY,
        Person.is_tracked == False
    ).join(PersonScore).filter(
        PersonScore.interaction_count >= 5,
        PersonScore.last_interaction_at >= ninety_days_ago
    ).scalar() or 0

    return {
        "queue_stats": result,
        "high_signal_unlinked_count": high_signal_unlinked,
        "total_pending": db.query(ReviewQueue).filter(ReviewQueue.status == "pending").count()
    }


@router.post("/refresh")
async def refresh_review_queue(
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Refresh the review queue by scanning for:
    - Email-only people with high interaction counts (promote candidates)
    - Possible matches between email-only and LinkedIn people
    """
    from app.ingestion.linker import PersonLinker

    linker = PersonLinker(db)
    result = linker.refresh_review_queue()

    return {
        "message": "Review queue refreshed",
        "promote_candidates_added": result.get("promote_candidates", 0),
        "link_suggestions_added": result.get("link_suggestions", 0)
    }
