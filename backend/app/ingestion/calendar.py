"""Calendar JSONL ingestion module."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import uuid4

from sqlalchemy.orm import Session
from dateutil import parser as date_parser

from app.models import (
    CalendarSeries, CalendarOccurrence, Interaction,
    Person, PersonEmail, IngestionCheckpoint
)
from app.models.interactions import InteractionKind, InteractionChannel
from app.core.config import settings


class CalendarIngester:
    """
    Ingest calendar data from OST export JSONL files.

    Handles:
    - Calendar series (recurring events)
    - Calendar occurrences (individual instances)
    - Creates meeting interactions linked to people
    """

    def __init__(self, db: Session):
        self.db = db
        self.own_emails = set(e.lower() for e in settings.own_emails)

    def ingest_jsonl(
        self,
        events_path: Optional[Path] = None,
        series_path: Optional[Path] = None,
        source_account: str = "default"
    ) -> Dict[str, Any]:
        """
        Ingest calendar data from JSONL files.

        Args:
            events_path: Path to events.jsonl (occurrences)
            series_path: Path to series.jsonl (recurring series)
            source_account: Account identifier

        Returns:
            Dict with processed, created, updated counts and errors list.
        """
        result = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "series_created": 0,
            "errors": []
        }

        # First, process series if available
        if series_path and series_path.exists():
            with open(series_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._process_series(data, source_account)
                        result["series_created"] += 1
                    except json.JSONDecodeError as e:
                        result["errors"].append(f"Series JSON parse error: {e}")
                    except Exception as e:
                        result["errors"].append(f"Series processing error: {e}")

        # Then process events/occurrences
        if events_path and events_path.exists():
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    result["processed"] += 1
                    try:
                        data = json.loads(line)
                        event_result = self._process_event(data, source_account)
                        if event_result == "created":
                            result["created"] += 1
                        elif event_result == "updated":
                            result["updated"] += 1
                    except json.JSONDecodeError as e:
                        result["errors"].append(f"Event JSON parse error: {e}")
                    except Exception as e:
                        result["errors"].append(f"Event processing error: {e}")

        # Update checkpoint
        self._update_checkpoint(source_account, result)

        self.db.commit()
        return result

    def _process_series(self, data: Dict[str, Any], source_account: str) -> None:
        """Process a calendar series record."""
        external_id = data.get("external_id")
        if not external_id:
            return

        # Check for existing series
        existing = self.db.query(CalendarSeries).filter(
            CalendarSeries.source_series_id == external_id,
            CalendarSeries.source_account == source_account
        ).first()

        if existing:
            # Update existing series
            existing.subject = data.get("subject")
            existing.organizer_email = data.get("organizer_email", "").lower()
            existing.timezone = data.get("timezone", "UTC")
            existing.rrule = data.get("rrule")
            existing.recurrence_blob = data.get("recurrence_blob")
            if data.get("start_at"):
                existing.start_at = self._parse_datetime(data["start_at"])
            if data.get("end_at"):
                existing.end_at = self._parse_datetime(data["end_at"])
        else:
            # Create new series
            series = CalendarSeries(
                id=str(uuid4()),
                source_series_id=external_id,
                organizer_email=data.get("organizer_email", "").lower(),
                subject=data.get("subject"),
                timezone=data.get("timezone", "UTC"),
                start_at=self._parse_datetime(data.get("start_at")),
                end_at=self._parse_datetime(data.get("end_at")),
                rrule=data.get("rrule"),
                recurrence_blob=data.get("recurrence_blob"),
                source_account=source_account
            )
            self.db.add(series)

    def _process_event(self, data: Dict[str, Any], source_account: str) -> str:
        """
        Process a calendar event/occurrence record.

        Returns:
            'created', 'updated', or 'skipped'
        """
        external_id = data.get("external_id")
        if not external_id:
            return "skipped"

        start_at = self._parse_datetime(data.get("start_at"))
        if not start_at:
            return "skipped"

        # Check for existing occurrence
        existing = self.db.query(CalendarOccurrence).filter(
            CalendarOccurrence.external_id == external_id,
            CalendarOccurrence.source_account == source_account
        ).first()

        # Find series if referenced
        series_id = None
        if data.get("series_id"):
            series = self.db.query(CalendarSeries).filter(
                CalendarSeries.source_series_id == data["series_id"],
                CalendarSeries.source_account == source_account
            ).first()
            if series:
                series_id = series.id

        participants = data.get("participants", [])
        is_cancelled = data.get("is_cancelled", False)

        if existing:
            # Update existing occurrence
            existing.subject = data.get("subject")
            existing.start_at = start_at
            existing.end_at = self._parse_datetime(data.get("end_at"))
            existing.timezone = data.get("timezone")
            existing.location = data.get("location")
            existing.organizer_email = data.get("organizer_email", "").lower()
            existing.participants = participants
            existing.is_exception = data.get("is_exception", False)
            existing.is_cancelled = is_cancelled
            existing.is_all_day = data.get("is_all_day", False)
            existing.series_id = series_id
            result = "updated"
        else:
            # Create new occurrence
            occurrence = CalendarOccurrence(
                id=str(uuid4()),
                series_id=series_id,
                external_id=external_id,
                subject=data.get("subject"),
                start_at=start_at,
                end_at=self._parse_datetime(data.get("end_at")),
                timezone=data.get("timezone"),
                location=data.get("location"),
                organizer_email=data.get("organizer_email", "").lower(),
                participants=participants,
                is_exception=data.get("is_exception", False),
                is_cancelled=is_cancelled,
                is_all_day=data.get("is_all_day", False),
                source_account=source_account
            )
            self.db.add(occurrence)
            result = "created"

        # Create meeting interactions for participants (if not cancelled)
        if not is_cancelled and participants:
            self._create_meeting_interactions(
                external_id=external_id,
                subject=data.get("subject"),
                start_at=start_at,
                end_at=self._parse_datetime(data.get("end_at")),
                participants=participants,
                source_account=source_account
            )

        return result

    def _create_meeting_interactions(
        self,
        external_id: str,
        subject: str,
        start_at: datetime,
        end_at: datetime,
        participants: List[Dict],
        source_account: str
    ) -> None:
        """Create meeting interactions for each non-self participant."""
        for participant in participants:
            email = participant.get("email", "").lower()
            if not email or email in self.own_emails:
                continue

            # Find or create person
            person_email = self.db.query(PersonEmail).filter(
                PersonEmail.email == email
            ).first()

            person_id = None
            if person_email:
                person_id = person_email.person_id
            else:
                # Create email-only person
                person = self._create_email_only_person(
                    email=email,
                    name=participant.get("name")
                )
                person_id = person.id

            # Check if interaction already exists
            interaction_ext_id = f"{external_id}:{email}"
            existing = self.db.query(Interaction).filter(
                Interaction.external_id == interaction_ext_id,
                Interaction.channel == InteractionChannel.CALENDAR
            ).first()

            if not existing:
                interaction = Interaction(
                    id=str(uuid4()),
                    person_id=person_id,
                    kind=InteractionKind.MEETING,
                    occurred_at=start_at,
                    end_at=end_at,
                    channel=InteractionChannel.CALENDAR,
                    subject=subject,
                    participants=participants,
                    external_id=interaction_ext_id,
                    source_account=source_account,
                    is_meaningful=True
                )
                self.db.add(interaction)

    def _create_email_only_person(self, email: str, name: str = None) -> Person:
        """Create an email-only person record."""
        from app.models.people import PersonOrigin

        # Generate a name from email if not provided
        if not name:
            name = email.split("@")[0].replace(".", " ").replace("_", " ").title()

        person = Person(
            id=str(uuid4()),
            full_name=name,
            primary_email=email,
            origin=PersonOrigin.EMAIL_ONLY,
            is_tracked=False
        )
        self.db.add(person)
        self.db.flush()

        # Add email record
        email_record = PersonEmail(
            id=str(uuid4()),
            person_id=person.id,
            email=email,
            is_primary=True,
            source="calendar"
        )
        self.db.add(email_record)

        return person

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse a datetime string."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            dt = date_parser.parse(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def _update_checkpoint(self, source_account: str, result: Dict[str, Any]) -> None:
        """Update ingestion checkpoint."""
        checkpoint = self.db.query(IngestionCheckpoint).filter(
            IngestionCheckpoint.source == "ost_calendar",
            IngestionCheckpoint.account == source_account
        ).first()

        checkpoint_data = {
            "last_import": datetime.now(timezone.utc).isoformat(),
            "events_processed": result["processed"],
            "events_created": result["created"],
            "series_created": result["series_created"]
        }

        if checkpoint:
            checkpoint.checkpoint_data = checkpoint_data
        else:
            checkpoint = IngestionCheckpoint(
                id=str(uuid4()),
                source="ost_calendar",
                account=source_account,
                checkpoint_data=checkpoint_data
            )
            self.db.add(checkpoint)
