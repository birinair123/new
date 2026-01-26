"""LinkedIn CSV ingestion module."""
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Person, PersonEmail, Interaction, IngestionCheckpoint
from app.models.people import PersonOrigin
from app.models.interactions import InteractionKind, InteractionChannel


class LinkedInIngester:
    """
    Ingest LinkedIn connections from exported CSV.

    LinkedIn exports have columns like:
    - First Name, Last Name
    - Email Address
    - Company
    - Position
    - Connected On
    - URL (LinkedIn profile URL)
    """

    def __init__(self, db: Session):
        self.db = db

    def ingest_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        Ingest a LinkedIn connections CSV file.
        Creates tracked people from LinkedIn connections.

        Returns:
            Dict with processed, created, updated counts and errors list.
        """
        result = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "errors": []
        }

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            # LinkedIn CSVs may have different column names
            reader = csv.DictReader(f)

            # Normalize column names (handle variations)
            fieldnames = reader.fieldnames or []
            col_map = self._map_columns(fieldnames)

            for row in reader:
                result["processed"] += 1
                try:
                    person_result = self._process_row(row, col_map)
                    if person_result == "created":
                        result["created"] += 1
                    elif person_result == "updated":
                        result["updated"] += 1
                except Exception as e:
                    result["errors"].append(f"Row {result['processed']}: {str(e)}")

        # Update checkpoint
        self._update_checkpoint(csv_path.name, result["processed"])

        self.db.commit()
        return result

    def _map_columns(self, fieldnames: list) -> Dict[str, str]:
        """Map various LinkedIn CSV column names to standard names."""
        col_map = {}

        # Common variations
        mappings = {
            "first_name": ["First Name", "FirstName", "first_name"],
            "last_name": ["Last Name", "LastName", "last_name"],
            "email": ["Email Address", "Email", "email", "E-Mail"],
            "company": ["Company", "company", "Organization"],
            "title": ["Position", "Title", "Job Title", "position", "title"],
            "connected_on": ["Connected On", "ConnectedOn", "connected_on", "Connection Date"],
            "linkedin_url": ["URL", "Profile URL", "LinkedIn URL", "url"],
        }

        for standard_name, variations in mappings.items():
            for var in variations:
                if var in fieldnames:
                    col_map[standard_name] = var
                    break

        return col_map

    def _process_row(self, row: Dict[str, str], col_map: Dict[str, str]) -> str:
        """
        Process a single CSV row.

        Returns:
            'created', 'updated', or 'skipped'
        """
        # Extract values
        first_name = row.get(col_map.get("first_name", ""), "").strip()
        last_name = row.get(col_map.get("last_name", ""), "").strip()
        email = row.get(col_map.get("email", ""), "").strip().lower()
        company = row.get(col_map.get("company", ""), "").strip()
        title = row.get(col_map.get("title", ""), "").strip()
        connected_on = row.get(col_map.get("connected_on", ""), "").strip()
        linkedin_url = row.get(col_map.get("linkedin_url", ""), "").strip()

        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            return "skipped"

        # Parse connected date
        linkedin_connected_at = None
        if connected_on:
            try:
                # Try common date formats
                for fmt in ["%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        linkedin_connected_at = datetime.strptime(connected_on, fmt)
                        linkedin_connected_at = linkedin_connected_at.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Extract LinkedIn ID from URL
        linkedin_id = None
        if linkedin_url and "/in/" in linkedin_url:
            linkedin_id = linkedin_url.split("/in/")[-1].strip("/").split("/")[0].split("?")[0]

        # Check for existing person by email or LinkedIn URL
        existing_person = None

        if email:
            existing_email = self.db.query(PersonEmail).filter(
                PersonEmail.email == email
            ).first()
            if existing_email:
                existing_person = existing_email.person

        if not existing_person and linkedin_url:
            existing_person = self.db.query(Person).filter(
                Person.linkedin_url == linkedin_url
            ).first()

        if not existing_person and linkedin_id:
            existing_person = self.db.query(Person).filter(
                Person.linkedin_id == linkedin_id
            ).first()

        if existing_person:
            # Update existing person
            existing_person.origin = PersonOrigin.LINKEDIN
            existing_person.is_tracked = True
            existing_person.linkedin_url = linkedin_url or existing_person.linkedin_url
            existing_person.linkedin_id = linkedin_id or existing_person.linkedin_id
            existing_person.company = company or existing_person.company
            existing_person.title = title or existing_person.title
            if linkedin_connected_at:
                existing_person.linkedin_connected_at = linkedin_connected_at

            # Add LinkedIn connect interaction if new
            self._add_connect_interaction(existing_person.id, linkedin_connected_at)

            return "updated"
        else:
            # Create new person
            person = Person(
                id=str(uuid4()),
                full_name=full_name,
                primary_email=email if email else None,
                linkedin_url=linkedin_url,
                linkedin_id=linkedin_id,
                company=company if company else None,
                title=title if title else None,
                origin=PersonOrigin.LINKEDIN,
                is_tracked=True,
                linkedin_connected_at=linkedin_connected_at
            )
            self.db.add(person)
            self.db.flush()  # Get the ID

            # Add email to person_emails
            if email:
                email_record = PersonEmail(
                    id=str(uuid4()),
                    person_id=person.id,
                    email=email,
                    is_primary=True,
                    source="linkedin"
                )
                self.db.add(email_record)

            # Add LinkedIn connect interaction
            self._add_connect_interaction(person.id, linkedin_connected_at)

            return "created"

    def _add_connect_interaction(self, person_id: str, connected_at: datetime = None):
        """Add a LinkedIn connection interaction."""
        if not connected_at:
            connected_at = datetime.now(timezone.utc)

        # Check if interaction already exists
        existing = self.db.query(Interaction).filter(
            Interaction.person_id == person_id,
            Interaction.kind == InteractionKind.LINKEDIN_CONNECT,
            Interaction.channel == InteractionChannel.LINKEDIN
        ).first()

        if not existing:
            interaction = Interaction(
                id=str(uuid4()),
                person_id=person_id,
                kind=InteractionKind.LINKEDIN_CONNECT,
                occurred_at=connected_at,
                channel=InteractionChannel.LINKEDIN,
                subject="LinkedIn connection",
                is_meaningful=True
            )
            self.db.add(interaction)

    def _update_checkpoint(self, filename: str, count: int):
        """Update ingestion checkpoint."""
        checkpoint = self.db.query(IngestionCheckpoint).filter(
            IngestionCheckpoint.source == "linkedin",
            IngestionCheckpoint.account == "default"
        ).first()

        if checkpoint:
            checkpoint.checkpoint_data = {
                "last_file": filename,
                "last_count": count,
                "last_import": datetime.now(timezone.utc).isoformat()
            }
        else:
            checkpoint = IngestionCheckpoint(
                id=str(uuid4()),
                source="linkedin",
                account="default",
                checkpoint_data={
                    "last_file": filename,
                    "last_count": count,
                    "last_import": datetime.now(timezone.utc).isoformat()
                }
            )
            self.db.add(checkpoint)
