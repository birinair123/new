"""Scores API endpoints."""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Person, PersonScore
from app.scoring.engine import ScoreEngine


router = APIRouter()


class ScoreBreakdownSchema(BaseModel):
    """Score breakdown schema."""
    recency: int
    recency_max: int
    recency_reason: str
    frequency: int
    frequency_max: int
    frequency_reason: str
    bidirectionality: int
    bidirectionality_max: int
    bidirectionality_reason: str
    meetings: int
    meetings_max: int
    meetings_reason: str
    context: int
    context_max: int
    context_reason: str


class PersonScoreResponse(BaseModel):
    """Person score response."""
    person_id: str
    person_name: str
    score_total: int
    score_breakdown: ScoreBreakdownSchema
    interaction_count: int
    last_interaction_at: Optional[str]
    next_meeting_at: Optional[str]


class ScoreListResponse(BaseModel):
    """List of scores."""
    items: List[PersonScoreResponse]
    total: int


class RecomputeResponse(BaseModel):
    """Recompute job response."""
    message: str
    people_count: int


@router.get("", response_model=ScoreListResponse)
async def list_scores(
    limit: int = Query(50, ge=1, le=200),
    min_score: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """List top scores for tracked people."""
    query = db.query(PersonScore, Person).join(Person).filter(
        Person.is_tracked == True,
        PersonScore.score_total >= min_score
    ).order_by(PersonScore.score_total.desc()).limit(limit)

    results = query.all()

    items = []
    for score, person in results:
        breakdown = score.score_breakdown or {}
        items.append(PersonScoreResponse(
            person_id=score.person_id,
            person_name=person.full_name,
            score_total=score.score_total,
            score_breakdown=ScoreBreakdownSchema(
                recency=breakdown.get("recency", 0),
                recency_max=breakdown.get("recency_max", 30),
                recency_reason=breakdown.get("recency_reason", ""),
                frequency=breakdown.get("frequency", 0),
                frequency_max=breakdown.get("frequency_max", 20),
                frequency_reason=breakdown.get("frequency_reason", ""),
                bidirectionality=breakdown.get("bidirectionality", 0),
                bidirectionality_max=breakdown.get("bidirectionality_max", 15),
                bidirectionality_reason=breakdown.get("bidirectionality_reason", ""),
                meetings=breakdown.get("meetings", 0),
                meetings_max=breakdown.get("meetings_max", 20),
                meetings_reason=breakdown.get("meetings_reason", ""),
                context=breakdown.get("context", 0),
                context_max=breakdown.get("context_max", 15),
                context_reason=breakdown.get("context_reason", "")
            ),
            interaction_count=score.interaction_count,
            last_interaction_at=score.last_interaction_at.isoformat() if score.last_interaction_at else None,
            next_meeting_at=score.next_meeting_at.isoformat() if score.next_meeting_at else None
        ))

    return ScoreListResponse(items=items, total=len(items))


@router.get("/{person_id}", response_model=PersonScoreResponse)
async def get_person_score(
    person_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get score details for a specific person."""
    result = db.query(PersonScore, Person).join(Person).filter(
        PersonScore.person_id == person_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Score not found for this person")

    score, person = result
    breakdown = score.score_breakdown or {}

    return PersonScoreResponse(
        person_id=score.person_id,
        person_name=person.full_name,
        score_total=score.score_total,
        score_breakdown=ScoreBreakdownSchema(
            recency=breakdown.get("recency", 0),
            recency_max=breakdown.get("recency_max", 30),
            recency_reason=breakdown.get("recency_reason", ""),
            frequency=breakdown.get("frequency", 0),
            frequency_max=breakdown.get("frequency_max", 20),
            frequency_reason=breakdown.get("frequency_reason", ""),
            bidirectionality=breakdown.get("bidirectionality", 0),
            bidirectionality_max=breakdown.get("bidirectionality_max", 15),
            bidirectionality_reason=breakdown.get("bidirectionality_reason", ""),
            meetings=breakdown.get("meetings", 0),
            meetings_max=breakdown.get("meetings_max", 20),
            meetings_reason=breakdown.get("meetings_reason", ""),
            context=breakdown.get("context", 0),
            context_max=breakdown.get("context_max", 15),
            context_reason=breakdown.get("context_reason", "")
        ),
        interaction_count=score.interaction_count,
        last_interaction_at=score.last_interaction_at.isoformat() if score.last_interaction_at else None,
        next_meeting_at=score.next_meeting_at.isoformat() if score.next_meeting_at else None
    )


@router.post("/recompute", response_model=RecomputeResponse)
async def recompute_scores(
    person_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Recompute scores for all tracked people or a specific person.
    Runs in background for full recompute.
    """
    engine = ScoreEngine(db)

    if person_id:
        # Single person - compute immediately
        person = db.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        engine.compute_score(person_id)
        return RecomputeResponse(
            message="Score recomputed for person",
            people_count=1
        )
    else:
        # All tracked people
        tracked_count = db.query(Person).filter(Person.is_tracked == True).count()

        # Run in background for large datasets
        if background_tasks and tracked_count > 10:
            background_tasks.add_task(engine.recompute_all_scores)
            return RecomputeResponse(
                message="Score recomputation started in background",
                people_count=tracked_count
            )
        else:
            engine.recompute_all_scores()
            return RecomputeResponse(
                message="Scores recomputed for all tracked people",
                people_count=tracked_count
            )
