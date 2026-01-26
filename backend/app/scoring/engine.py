"""
Connection Strength Score Engine

Computes explainable 0-100 scores for tracked people based on:
- Recency: Days since last meaningful interaction (0-30 points)
- Frequency: Meaningful interactions in last 90 days (0-20 points)
- Bidirectionality: Mix of inbound/outbound in last 180 days (0-15 points)
- Meetings: Meetings in last 365 days + future scheduled (0-20 points)
- Context: LinkedIn connection + key relationship tags (0-15 points)
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from uuid import uuid4

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.models import Person, PersonScore, Interaction, CalendarOccurrence
from app.models.interactions import InteractionKind
from app.core.config import settings


class ScoreEngine:
    """
    Compute and cache connection strength scores.

    All scores are explainable with breakdown showing how each component
    contributed to the total score.
    """

    def __init__(self, db: Session):
        self.db = db
        self.now = datetime.now(timezone.utc)

        # Score maximums from config
        self.recency_max = settings.score_recency_max
        self.frequency_max = settings.score_frequency_max
        self.bidirectional_max = settings.score_bidirectional_max
        self.meetings_max = settings.score_meetings_max
        self.context_max = settings.score_context_max

    def compute_score(self, person_id: str) -> PersonScore:
        """
        Compute and save score for a single person.

        Returns:
            The updated PersonScore record.
        """
        person = self.db.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise ValueError(f"Person not found: {person_id}")

        # Get all interactions for this person
        interactions = self.db.query(Interaction).filter(
            Interaction.person_id == person_id
        ).all()

        # Filter to meaningful interactions
        meaningful = [i for i in interactions if i.is_meaningful]

        # Compute each score component
        recency_score, recency_reason = self._compute_recency(meaningful)
        frequency_score, frequency_reason = self._compute_frequency(meaningful)
        bidirectional_score, bidirectional_reason = self._compute_bidirectionality(meaningful)
        meetings_score, meetings_reason = self._compute_meetings(meaningful, person_id)
        context_score, context_reason = self._compute_context(person)

        # Total score
        total = recency_score + frequency_score + bidirectional_score + meetings_score + context_score

        # Build breakdown
        breakdown = {
            "recency": recency_score,
            "recency_max": self.recency_max,
            "recency_reason": recency_reason,
            "frequency": frequency_score,
            "frequency_max": self.frequency_max,
            "frequency_reason": frequency_reason,
            "bidirectionality": bidirectional_score,
            "bidirectionality_max": self.bidirectional_max,
            "bidirectionality_reason": bidirectional_reason,
            "meetings": meetings_score,
            "meetings_max": self.meetings_max,
            "meetings_reason": meetings_reason,
            "context": context_score,
            "context_max": self.context_max,
            "context_reason": context_reason,
        }

        # Compute aggregate metrics
        last_interaction_at = None
        last_inbound_at = None
        last_outbound_at = None
        last_meeting_at = None
        first_interaction_at = None

        if meaningful:
            sorted_interactions = sorted(meaningful, key=lambda x: x.occurred_at, reverse=True)
            last_interaction_at = sorted_interactions[0].occurred_at
            first_interaction_at = sorted_interactions[-1].occurred_at

            inbound = [i for i in sorted_interactions if i.direction == "inbound"]
            if inbound:
                last_inbound_at = inbound[0].occurred_at

            outbound = [i for i in sorted_interactions if i.direction == "outbound"]
            if outbound:
                last_outbound_at = outbound[0].occurred_at

            meetings = [i for i in sorted_interactions if i.kind == InteractionKind.MEETING]
            if meetings:
                last_meeting_at = meetings[0].occurred_at

        # Find next meeting
        next_meeting_at = self._find_next_meeting(person_id)

        # Get or create score record
        score_record = self.db.query(PersonScore).filter(
            PersonScore.person_id == person_id
        ).first()

        if score_record:
            score_record.score_total = total
            score_record.score_breakdown = breakdown
            score_record.interaction_count = len(meaningful)
            score_record.last_interaction_at = last_interaction_at
            score_record.last_inbound_at = last_inbound_at
            score_record.last_outbound_at = last_outbound_at
            score_record.last_meeting_at = last_meeting_at
            score_record.next_meeting_at = next_meeting_at
            score_record.first_interaction_at = first_interaction_at
        else:
            score_record = PersonScore(
                person_id=person_id,
                score_total=total,
                score_breakdown=breakdown,
                interaction_count=len(meaningful),
                last_interaction_at=last_interaction_at,
                last_inbound_at=last_inbound_at,
                last_outbound_at=last_outbound_at,
                last_meeting_at=last_meeting_at,
                next_meeting_at=next_meeting_at,
                first_interaction_at=first_interaction_at
            )
            self.db.add(score_record)

        self.db.commit()
        return score_record

    def _compute_recency(self, interactions: List[Interaction]) -> tuple[int, str]:
        """
        Compute recency score (0-30 points).

        Scoring:
        - Today: 30 points
        - 1-7 days: 25 points
        - 8-14 days: 20 points
        - 15-30 days: 15 points
        - 31-60 days: 10 points
        - 61-90 days: 5 points
        - 91+ days: 0 points
        """
        if not interactions:
            return 0, "No interactions"

        # Find most recent interaction
        most_recent = max(interactions, key=lambda x: x.occurred_at)
        days_ago = (self.now - most_recent.occurred_at).days

        if days_ago <= 0:
            return 30, f"Interaction today"
        elif days_ago <= 7:
            return 25, f"Last interaction {days_ago} days ago"
        elif days_ago <= 14:
            return 20, f"Last interaction {days_ago} days ago"
        elif days_ago <= 30:
            return 15, f"Last interaction {days_ago} days ago"
        elif days_ago <= 60:
            return 10, f"Last interaction {days_ago} days ago"
        elif days_ago <= 90:
            return 5, f"Last interaction {days_ago} days ago"
        else:
            return 0, f"Last interaction {days_ago} days ago (stale)"

    def _compute_frequency(self, interactions: List[Interaction]) -> tuple[int, str]:
        """
        Compute frequency score (0-20 points).

        Scoring based on meaningful interactions in last 90 days:
        - 20+ interactions: 20 points
        - 10-19: 15 points
        - 5-9: 10 points
        - 2-4: 5 points
        - 1: 2 points
        - 0: 0 points
        """
        ninety_days_ago = self.now - timedelta(days=90)
        recent = [i for i in interactions if i.occurred_at >= ninety_days_ago]
        count = len(recent)

        if count >= 20:
            return 20, f"{count} interactions in 90 days (very active)"
        elif count >= 10:
            return 15, f"{count} interactions in 90 days (active)"
        elif count >= 5:
            return 10, f"{count} interactions in 90 days (moderate)"
        elif count >= 2:
            return 5, f"{count} interactions in 90 days (occasional)"
        elif count == 1:
            return 2, f"1 interaction in 90 days"
        else:
            return 0, "No interactions in 90 days"

    def _compute_bidirectionality(self, interactions: List[Interaction]) -> tuple[int, str]:
        """
        Compute bidirectionality score (0-15 points).

        Measures balance of inbound/outbound communication in last 180 days.
        Bonus if they initiated 2+ times (shows engagement).
        """
        one_eighty_days_ago = self.now - timedelta(days=180)
        recent = [i for i in interactions if i.occurred_at >= one_eighty_days_ago]

        inbound = [i for i in recent if i.direction == "inbound"]
        outbound = [i for i in recent if i.direction == "outbound"]

        inbound_count = len(inbound)
        outbound_count = len(outbound)
        total = inbound_count + outbound_count

        if total == 0:
            return 0, "No email interactions in 180 days"

        # Compute balance ratio
        if inbound_count == 0:
            ratio = 0.0
        elif outbound_count == 0:
            ratio = 0.0
        else:
            ratio = min(inbound_count, outbound_count) / max(inbound_count, outbound_count)

        # Base score from ratio (0-10)
        base_score = int(ratio * 10)

        # Bonus for them initiating (shows engagement)
        bonus = 0
        if inbound_count >= 2:
            bonus = 5
            reason = f"Bidirectional ({inbound_count} in, {outbound_count} out) + they initiated"
        elif inbound_count >= 1:
            bonus = 2
            reason = f"Bidirectional ({inbound_count} in, {outbound_count} out)"
        elif outbound_count > 0:
            reason = f"Outbound only ({outbound_count} out, no responses)"
        else:
            reason = f"Inbound only ({inbound_count} in)"

        return min(base_score + bonus, 15), reason

    def _compute_meetings(self, interactions: List[Interaction], person_id: str) -> tuple[int, str]:
        """
        Compute meetings score (0-20 points).

        Scoring based on meetings in last 365 days + future meetings:
        - 10+ meetings: 15 points
        - 5-9 meetings: 12 points
        - 2-4 meetings: 8 points
        - 1 meeting: 4 points
        - Future meeting scheduled: +5 points bonus
        """
        one_year_ago = self.now - timedelta(days=365)
        meetings = [
            i for i in interactions
            if i.kind == InteractionKind.MEETING and i.occurred_at >= one_year_ago
        ]
        meeting_count = len(meetings)

        if meeting_count >= 10:
            base_score = 15
            reason = f"{meeting_count} meetings in past year (frequent)"
        elif meeting_count >= 5:
            base_score = 12
            reason = f"{meeting_count} meetings in past year"
        elif meeting_count >= 2:
            base_score = 8
            reason = f"{meeting_count} meetings in past year"
        elif meeting_count == 1:
            base_score = 4
            reason = "1 meeting in past year"
        else:
            base_score = 0
            reason = "No meetings in past year"

        # Check for future meetings
        next_meeting = self._find_next_meeting(person_id)
        if next_meeting:
            base_score = min(base_score + 5, 20)
            reason += " + upcoming meeting scheduled"

        return base_score, reason

    def _find_next_meeting(self, person_id: str) -> Optional[datetime]:
        """Find the next scheduled meeting with this person."""
        # First check interactions (meetings from ingestion)
        next_meeting = self.db.query(Interaction).filter(
            Interaction.person_id == person_id,
            Interaction.kind == InteractionKind.MEETING,
            Interaction.occurred_at > self.now
        ).order_by(Interaction.occurred_at).first()

        if next_meeting:
            return next_meeting.occurred_at

        # Also check calendar_occurrences by participant email
        person = self.db.query(Person).filter(Person.id == person_id).first()
        if person and person.primary_email:
            # This is a simplified check - in production, would use proper JSON querying
            from sqlalchemy import cast, String
            from sqlalchemy.dialects.postgresql import JSONB

            occurrence = self.db.query(CalendarOccurrence).filter(
                CalendarOccurrence.start_at > self.now,
                CalendarOccurrence.is_cancelled == False,
                CalendarOccurrence.participants.cast(String).ilike(f'%{person.primary_email}%')
            ).order_by(CalendarOccurrence.start_at).first()

            if occurrence:
                return occurrence.start_at

        return None

    def _compute_context(self, person: Person) -> tuple[int, str]:
        """
        Compute context score (0-15 points).

        Scoring:
        - LinkedIn connection: 5 points
        - "key_relationship" tag: 5 points
        - "important" tag: 3 points
        - "friend" tag: 2 points
        """
        score = 0
        reasons = []

        # LinkedIn connection
        if person.origin in [PersonOrigin.LINKEDIN, PersonOrigin.PROMOTED]:
            score += 5
            reasons.append("LinkedIn connected")

        # Tags
        tags = person.tags or []
        tag_lower = [t.lower() for t in tags]

        if "key_relationship" in tag_lower or "key-relationship" in tag_lower:
            score += 5
            reasons.append("key relationship tag")
        if "important" in tag_lower:
            score += 3
            reasons.append("important tag")
        if "friend" in tag_lower:
            score += 2
            reasons.append("friend tag")
        if "vip" in tag_lower:
            score += 5
            reasons.append("VIP tag")

        reason = ", ".join(reasons) if reasons else "No context signals"
        return min(score, 15), reason

    def recompute_all_scores(self) -> Dict[str, int]:
        """
        Recompute scores for all tracked people.

        Returns:
            Dict with count of updated scores.
        """
        tracked_people = self.db.query(Person).filter(
            Person.is_tracked == True
        ).all()

        updated = 0
        errors = 0

        for person in tracked_people:
            try:
                self.compute_score(person.id)
                updated += 1
            except Exception as e:
                errors += 1
                print(f"Error computing score for {person.id}: {e}")

        return {"updated": updated, "errors": errors}


# Import at bottom to avoid circular imports
from app.models.people import PersonOrigin
