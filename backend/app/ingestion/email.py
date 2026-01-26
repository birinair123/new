"""Email JSONL ingestion module."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from uuid import uuid4

from sqlalchemy.orm import Session
from dateutil import parser as date_parser

from app.models import Interaction, Person, PersonEmail, IngestionCheckpoint
from app.models.people import PersonOrigin
from app.models.interactions import InteractionKind, InteractionChannel
from app.core.config import settings


# Patterns for automated/bulk email detection
AUTOMATED_PATTERNS = [
    r"no[-_]?reply",
    r"noreply",
    r"do[-_]?not[-_]?reply",
    r"mailer[-_]?daemon",
    r"postmaster",
    r"notifications?@",
    r"alerts?@",
    r"auto[-_]?confirm",
    r"automated",
]

BULK_PATTERNS = [
    r"newsletter",
    r"marketing",
    r"promo",
    r"campaign",
    r"unsubscribe",
    r"list[-_]?unsubscribe",
]

# Compile patterns
AUTOMATED_RE = re.compile("|".join(AUTOMATED_PATTERNS), re.IGNORECASE)
BULK_RE = re.compile("|".join(BULK_PATTERNS), re.IGNORECASE)


class EmailIngester:
    """
    Ingest email metadata from OST export JSONL files.

    Handles:
    - Email metadata (from/to/cc, subject, timestamps)
    - Direction detection (inbound/outbound)
    - Automated/bulk email filtering
    - Person linking and creation
    """

    def __init__(self, db: Session):
        self.db = db
        self.own_emails = set(e.lower() for e in settings.own_emails)
        self.store_snippets = settings.store_email_snippets
        self.snippet_max_length = settings.snippet_max_length

    def ingest_jsonl(
        self,
        emails_path: Path,
        source_account: str = "default"
    ) -> Dict[str, Any]:
        """
        Ingest email metadata from JSONL file.

        Args:
            emails_path: Path to emails.jsonl
            source_account: Account identifier

        Returns:
            Dict with processed, created, updated counts and errors list.
        """
        result = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "skipped_automated": 0,
            "skipped_bulk": 0,
            "errors": []
        }

        if not emails_path.exists():
            raise FileNotFoundError(f"Email file not found: {emails_path}")

        with open(emails_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                result["processed"] += 1
                try:
                    data = json.loads(line)
                    email_result = self._process_email(data, source_account)
                    if email_result == "created":
                        result["created"] += 1
                    elif email_result == "updated":
                        result["updated"] += 1
                    elif email_result == "skipped_automated":
                        result["skipped_automated"] += 1
                    elif email_result == "skipped_bulk":
                        result["skipped_bulk"] += 1
                except json.JSONDecodeError as e:
                    result["errors"].append(f"JSON parse error: {e}")
                except Exception as e:
                    result["errors"].append(f"Processing error: {e}")

        # Update checkpoint
        self._update_checkpoint(source_account, result)

        self.db.commit()
        return result

    def _process_email(self, data: Dict[str, Any], source_account: str) -> str:
        """
        Process a single email record.

        Returns:
            'created', 'updated', 'skipped_automated', 'skipped_bulk', or 'skipped'
        """
        external_id = data.get("external_id") or data.get("message_id")
        if not external_id:
            return "skipped"

        from_email = data.get("from_email", "").lower()
        from_name = data.get("from_name", "")
        to_list = data.get("to", [])
        cc_list = data.get("cc", [])
        subject = data.get("subject", "")

        # Detect if automated
        is_automated = self._is_automated(from_email, subject)
        if is_automated:
            # Still record but mark as not meaningful
            pass

        # Detect if bulk
        is_bulk = self._is_bulk(data, len(to_list) + len(cc_list))

        # Determine direction
        direction = self._detect_direction(from_email, to_list, cc_list)
        if direction is None:
            return "skipped"

        # Parse timestamps
        sent_at = self._parse_datetime(data.get("sent_at"))
        received_at = self._parse_datetime(data.get("received_at"))
        occurred_at = sent_at or received_at
        if not occurred_at:
            return "skipped"

        # Get the "other" email (person we're communicating with)
        if direction == "inbound":
            other_email = from_email
            other_name = from_name
            kind = InteractionKind.EMAIL_IN
        else:
            # For outbound, use primary recipient
            if to_list:
                other_email = to_list[0].get("email", "").lower()
                other_name = to_list[0].get("name", "")
            else:
                return "skipped"
            kind = InteractionKind.EMAIL_OUT

        if not other_email or other_email in self.own_emails:
            return "skipped"

        # Find or create person
        person_id = self._find_or_create_person(other_email, other_name)

        # Check if interaction already exists
        existing = self.db.query(Interaction).filter(
            Interaction.external_id == external_id,
            Interaction.channel == InteractionChannel.OST
        ).first()

        # Prepare snippet
        snippet = None
        if self.store_snippets and data.get("snippet"):
            snippet = data["snippet"][:self.snippet_max_length]

        # Prepare participants
        participants = []
        if from_email:
            participants.append({"email": from_email, "name": from_name, "role": "from"})
        for p in to_list:
            participants.append({"email": p.get("email", ""), "name": p.get("name", ""), "role": "to"})
        for p in cc_list:
            participants.append({"email": p.get("email", ""), "name": p.get("name", ""), "role": "cc"})

        is_meaningful = not is_automated and not is_bulk

        if existing:
            # Update existing interaction
            existing.subject = subject
            existing.snippet = snippet
            existing.is_automated = is_automated
            existing.is_bulk = is_bulk
            existing.is_meaningful = is_meaningful
            existing.participants = participants
            return "updated"
        else:
            # Create new interaction
            interaction = Interaction(
                id=str(uuid4()),
                person_id=person_id,
                kind=kind,
                occurred_at=occurred_at,
                direction=direction,
                channel=InteractionChannel.OST,
                subject=subject,
                snippet=snippet,
                participants=participants,
                external_id=external_id,
                source_account=source_account,
                is_automated=is_automated,
                is_bulk=is_bulk,
                is_meaningful=is_meaningful
            )
            self.db.add(interaction)

            if is_automated:
                return "skipped_automated"
            if is_bulk:
                return "skipped_bulk"
            return "created"

    def _is_automated(self, from_email: str, subject: str) -> bool:
        """Check if email is from an automated sender."""
        if AUTOMATED_RE.search(from_email):
            return True
        # Check for common automated subject patterns
        automated_subjects = ["confirmation", "verification", "password reset", "order confirmed"]
        subject_lower = subject.lower()
        return any(p in subject_lower for p in automated_subjects)

    def _is_bulk(self, data: Dict[str, Any], recipient_count: int) -> bool:
        """Check if email is bulk/newsletter."""
        # Check List-Unsubscribe header
        headers = data.get("headers", {})
        if headers.get("list_unsubscribe"):
            return True

        # Check recipient count (many recipients = likely bulk)
        if recipient_count > 10:
            return True

        # Check subject for bulk patterns
        subject = data.get("subject", "")
        if BULK_RE.search(subject):
            return True

        return False

    def _detect_direction(
        self,
        from_email: str,
        to_list: List[Dict],
        cc_list: List[Dict]
    ) -> Optional[str]:
        """
        Detect email direction based on from/to/cc.

        Returns:
            'inbound', 'outbound', or None if can't determine
        """
        if from_email in self.own_emails:
            return "outbound"

        # Check if any of our emails are in to/cc
        all_recipients = [p.get("email", "").lower() for p in to_list + cc_list]
        if any(e in self.own_emails for e in all_recipients):
            return "inbound"

        # Can't determine direction without own emails configured
        # Default to inbound for safety
        return "inbound"

    def _find_or_create_person(self, email: str, name: str = None) -> str:
        """Find or create a person by email."""
        # Look up existing person by email
        person_email = self.db.query(PersonEmail).filter(
            PersonEmail.email == email
        ).first()

        if person_email:
            return person_email.person_id

        # Create new email-only person
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

        email_record = PersonEmail(
            id=str(uuid4()),
            person_id=person.id,
            email=email,
            is_primary=True,
            source="email"
        )
        self.db.add(email_record)

        return person.id

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
            IngestionCheckpoint.source == "ost_email",
            IngestionCheckpoint.account == source_account
        ).first()

        checkpoint_data = {
            "last_import": datetime.now(timezone.utc).isoformat(),
            "processed": result["processed"],
            "created": result["created"],
            "skipped_automated": result["skipped_automated"],
            "skipped_bulk": result["skipped_bulk"]
        }

        if checkpoint:
            checkpoint.checkpoint_data = checkpoint_data
        else:
            checkpoint = IngestionCheckpoint(
                id=str(uuid4()),
                source="ost_email",
                account=source_account,
                checkpoint_data=checkpoint_data
            )
            self.db.add(checkpoint)
