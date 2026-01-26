"""Person linking and matching module."""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4
import re

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models import Person, PersonEmail, Interaction, PersonScore, ReviewQueue
from app.models.people import PersonOrigin


class PersonLinker:
    """
    Handle person linking, matching, and review queue management.

    Features:
    - Email-based exact matching
    - Name + company fuzzy matching
    - High-signal unlinked detection
    - Review queue population
    """

    def __init__(self, db: Session):
        self.db = db

    def find_person_by_email(self, email: str) -> Optional[Person]:
        """Find a person by exact email match."""
        email = email.lower().strip()
        person_email = self.db.query(PersonEmail).filter(
            PersonEmail.email == email
        ).first()
        return person_email.person if person_email else None

    def find_potential_matches(
        self,
        name: str,
        company: str = None,
        email_domain: str = None
    ) -> List[Tuple[Person, float, Dict]]:
        """
        Find potential person matches based on name and company.

        Returns:
            List of (person, confidence_score, match_reason) tuples
        """
        matches = []

        if not name:
            return matches

        # Normalize name for comparison
        name_parts = self._normalize_name(name)
        if not name_parts:
            return matches

        # Query candidates
        candidates = self.db.query(Person).filter(
            Person.is_tracked == True  # Only match to tracked people
        ).all()

        for person in candidates:
            confidence, reason = self._compute_match_score(
                name_parts, company, email_domain, person
            )
            if confidence >= 0.5:  # Minimum threshold
                matches.append((person, confidence, reason))

        # Sort by confidence descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:5]  # Return top 5

    def _normalize_name(self, name: str) -> List[str]:
        """Normalize a name into parts for comparison."""
        # Remove common prefixes/suffixes
        name = re.sub(r"\b(Mr|Mrs|Ms|Dr|Jr|Sr|III|II|IV)\b\.?", "", name, flags=re.IGNORECASE)
        # Split into parts
        parts = name.lower().split()
        # Filter empty parts
        return [p.strip() for p in parts if p.strip() and len(p) > 1]

    def _compute_match_score(
        self,
        name_parts: List[str],
        company: str,
        email_domain: str,
        person: Person
    ) -> Tuple[float, Dict]:
        """
        Compute match confidence score between query and person.

        Returns:
            (confidence, reason_dict)
        """
        score = 0.0
        reasons = {}

        person_name_parts = self._normalize_name(person.full_name)

        # Name matching
        if person_name_parts:
            # Exact name match
            if name_parts == person_name_parts:
                score += 0.6
                reasons["name"] = "exact_match"
            else:
                # Check first name + last name match
                if len(name_parts) >= 2 and len(person_name_parts) >= 2:
                    if name_parts[0] == person_name_parts[0] and name_parts[-1] == person_name_parts[-1]:
                        score += 0.5
                        reasons["name"] = "first_last_match"
                    elif name_parts[0] == person_name_parts[0]:
                        score += 0.2
                        reasons["name"] = "first_name_match"
                    elif name_parts[-1] == person_name_parts[-1]:
                        score += 0.15
                        reasons["name"] = "last_name_match"

        # Company matching
        if company and person.company:
            company_norm = company.lower().strip()
            person_company_norm = person.company.lower().strip()

            if company_norm == person_company_norm:
                score += 0.3
                reasons["company"] = "exact_match"
            elif company_norm in person_company_norm or person_company_norm in company_norm:
                score += 0.15
                reasons["company"] = "partial_match"

        # Email domain matching
        if email_domain and person.primary_email:
            person_domain = person.primary_email.split("@")[-1].lower()
            if email_domain.lower() == person_domain:
                score += 0.1
                reasons["email_domain"] = "match"

        return min(score, 1.0), reasons

    def link_interaction_to_person(
        self,
        interaction_id: str,
        person_id: str
    ) -> bool:
        """Manually link an interaction to a person."""
        interaction = self.db.query(Interaction).filter(
            Interaction.id == interaction_id
        ).first()

        if not interaction:
            return False

        person = self.db.query(Person).filter(Person.id == person_id).first()
        if not person:
            return False

        interaction.person_id = person_id
        self.db.commit()
        return True

    def merge_persons(
        self,
        source_id: str,
        target_id: str
    ) -> bool:
        """
        Merge source person into target person.
        Moves all interactions and emails from source to target.
        """
        source = self.db.query(Person).filter(Person.id == source_id).first()
        target = self.db.query(Person).filter(Person.id == target_id).first()

        if not source or not target:
            return False

        # Move interactions
        self.db.query(Interaction).filter(
            Interaction.person_id == source_id
        ).update({Interaction.person_id: target_id})

        # Move emails (avoiding duplicates)
        source_emails = self.db.query(PersonEmail).filter(
            PersonEmail.person_id == source_id
        ).all()

        for email_record in source_emails:
            existing = self.db.query(PersonEmail).filter(
                PersonEmail.person_id == target_id,
                PersonEmail.email == email_record.email
            ).first()
            if not existing:
                email_record.person_id = target_id
                email_record.is_primary = False

        # Delete source person (cascade will clean up remaining)
        self.db.delete(source)
        self.db.commit()

        return True

    def relink_all(self) -> Dict[str, int]:
        """
        Re-link all unlinked interactions to persons.

        Returns:
            Dict with counts of linked interactions.
        """
        result = {"linked": 0, "unlinked": 0}

        # Find interactions without person_id
        unlinked = self.db.query(Interaction).filter(
            Interaction.person_id == None
        ).all()

        for interaction in unlinked:
            # Try to find person from participants
            linked = False

            participants = interaction.participants or []
            for p in participants:
                email = p.get("email", "").lower()
                if email:
                    person = self.find_person_by_email(email)
                    if person:
                        interaction.person_id = person.id
                        result["linked"] += 1
                        linked = True
                        break

            if not linked:
                result["unlinked"] += 1

        self.db.commit()
        return result

    def refresh_review_queue(self) -> Dict[str, int]:
        """
        Refresh the review queue with:
        1. Email-only people with high interaction counts (promote candidates)
        2. Possible matches between email-only and LinkedIn people

        Returns:
            Dict with counts of added items.
        """
        result = {"promote_candidates": 0, "link_suggestions": 0}

        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

        # Find high-signal email-only people
        high_signal_query = self.db.query(Person).filter(
            Person.origin == PersonOrigin.EMAIL_ONLY,
            Person.is_tracked == False
        ).join(PersonScore).filter(
            PersonScore.interaction_count >= 5,
            PersonScore.last_interaction_at >= ninety_days_ago
        )

        # Or people with any meetings
        meeting_query = self.db.query(Person).filter(
            Person.origin == PersonOrigin.EMAIL_ONLY,
            Person.is_tracked == False
        ).join(Interaction).filter(
            Interaction.kind == "meeting"
        )

        # Combine and deduplicate
        candidates = set()
        for person in high_signal_query.all():
            candidates.add(person.id)
        for person in meeting_query.all():
            candidates.add(person.id)

        for person_id in candidates:
            person = self.db.query(Person).filter(Person.id == person_id).first()
            if not person:
                continue

            # Check if already in queue
            existing = self.db.query(ReviewQueue).filter(
                ReviewQueue.person_id == person_id,
                ReviewQueue.status == "pending"
            ).first()

            if existing:
                continue

            # Get interaction count
            interaction_count = self.db.query(func.count(Interaction.id)).filter(
                Interaction.person_id == person_id
            ).scalar() or 0

            # Look for potential LinkedIn matches
            matches = self.find_potential_matches(
                name=person.full_name,
                company=person.company,
                email_domain=person.primary_email.split("@")[-1] if person.primary_email else None
            )

            if matches and matches[0][1] >= 0.7:
                # High confidence match suggestion
                best_match, confidence, reason = matches[0]
                queue_item = ReviewQueue(
                    id=str(uuid4()),
                    person_id=person_id,
                    queue_type="link_suggestion",
                    suggested_person_id=best_match.id,
                    confidence_score=confidence,
                    match_reason=reason,
                    interaction_count=interaction_count
                )
                self.db.add(queue_item)
                result["link_suggestions"] += 1
            else:
                # No match found, suggest promotion
                queue_item = ReviewQueue(
                    id=str(uuid4()),
                    person_id=person_id,
                    queue_type="promote",
                    interaction_count=interaction_count
                )
                self.db.add(queue_item)
                result["promote_candidates"] += 1

        self.db.commit()
        return result
