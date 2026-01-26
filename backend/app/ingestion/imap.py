"""IMAP email ingestion module."""
import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Interaction, Person, PersonEmail, IngestionCheckpoint
from app.models.people import PersonOrigin
from app.models.interactions import InteractionKind, InteractionChannel
from app.core.config import settings


class IMAPIngester:
    """
    Ingest email metadata from IMAP server.

    Features:
    - Read-only access (no modifications to mailbox)
    - Metadata-only extraction (no full body storage by default)
    - Incremental sync with checkpointing
    - Direction detection based on configured own emails
    """

    def __init__(self, db: Session):
        self.db = db
        self.own_emails = set(e.lower() for e in settings.own_emails)
        self.store_snippets = settings.store_email_snippets
        self.snippet_max_length = settings.snippet_max_length

    def sync_folder(
        self,
        folder: str = "INBOX",
        days_back: int = 30,
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Sync email metadata from an IMAP folder.

        Args:
            folder: IMAP folder name
            days_back: Number of days to sync (from now)
            batch_size: Number of messages to fetch at a time

        Returns:
            Dict with processed, created, updated counts and errors list.
        """
        result = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": []
        }

        # Connect to IMAP server
        try:
            if settings.imap_use_ssl:
                conn = imaplib.IMAP4_SSL(settings.imap_server, settings.imap_port)
            else:
                conn = imaplib.IMAP4(settings.imap_server, settings.imap_port)

            conn.login(settings.imap_username, settings.imap_password)
        except Exception as e:
            result["errors"].append(f"IMAP connection failed: {e}")
            return result

        try:
            # Select folder (readonly)
            status, data = conn.select(folder, readonly=True)
            if status != "OK":
                result["errors"].append(f"Failed to select folder: {folder}")
                return result

            # Calculate date range
            since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            since_str = since_date.strftime("%d-%b-%Y")

            # Get checkpoint for incremental sync
            checkpoint = self._get_checkpoint(folder)
            last_uid = checkpoint.get("last_uid", 0) if checkpoint else 0

            # Search for messages
            search_criteria = f"SINCE {since_str}"
            if last_uid > 0:
                search_criteria = f"UID {last_uid + 1}:* SINCE {since_str}"

            status, message_ids = conn.search(None, search_criteria)
            if status != "OK":
                result["errors"].append("IMAP search failed")
                return result

            msg_id_list = message_ids[0].split()

            # Process messages in batches
            for i in range(0, len(msg_id_list), batch_size):
                batch = msg_id_list[i:i + batch_size]

                for msg_id in batch:
                    result["processed"] += 1
                    try:
                        msg_result = self._process_message(conn, msg_id.decode(), folder)
                        if msg_result == "created":
                            result["created"] += 1
                        elif msg_result == "updated":
                            result["updated"] += 1
                        else:
                            result["skipped"] += 1
                    except Exception as e:
                        result["errors"].append(f"Message {msg_id}: {e}")

                # Commit in batches
                self.db.commit()

            # Update checkpoint with highest UID
            if msg_id_list:
                last_uid = max(int(uid.decode()) for uid in msg_id_list)
                self._update_checkpoint(folder, last_uid, result["processed"])

        finally:
            conn.logout()

        self.db.commit()
        return result

    def _process_message(self, conn: imaplib.IMAP4, msg_id: str, folder: str) -> str:
        """
        Process a single email message.

        Returns:
            'created', 'updated', or 'skipped'
        """
        # Fetch message headers and envelope
        status, data = conn.fetch(msg_id, "(UID RFC822.HEADER)")
        if status != "OK" or not data or not data[0]:
            return "skipped"

        # Parse UID
        uid_match = re.search(rb"UID (\d+)", data[0][0])
        uid = uid_match.group(1).decode() if uid_match else msg_id

        # Parse headers
        if isinstance(data[0], tuple) and len(data[0]) > 1:
            raw_headers = data[0][1]
        else:
            return "skipped"

        msg = email.message_from_bytes(raw_headers)

        # Extract metadata
        message_id = msg.get("Message-ID", "").strip("<>")
        if not message_id:
            message_id = f"imap:{uid}"

        subject = self._decode_header(msg.get("Subject", ""))
        from_header = msg.get("From", "")
        to_header = msg.get("To", "")
        cc_header = msg.get("Cc", "")
        date_header = msg.get("Date", "")

        # Parse addresses
        from_name, from_email = parseaddr(from_header)
        from_email = from_email.lower()

        to_list = self._parse_address_list(to_header)
        cc_list = self._parse_address_list(cc_header)

        # Parse date
        sent_at = None
        if date_header:
            try:
                sent_at = parsedate_to_datetime(date_header)
            except Exception:
                sent_at = datetime.now(timezone.utc)

        if not sent_at:
            return "skipped"

        # Determine direction
        direction = self._detect_direction(from_email, to_list, cc_list)
        if direction is None:
            return "skipped"

        # Get the "other" email
        if direction == "inbound":
            other_email = from_email
            other_name = self._decode_header(from_name)
            kind = InteractionKind.EMAIL_IN
        else:
            if to_list:
                other_email = to_list[0][1].lower()
                other_name = to_list[0][0]
            else:
                return "skipped"
            kind = InteractionKind.EMAIL_OUT

        if not other_email or other_email in self.own_emails:
            return "skipped"

        # Find or create person
        person_id = self._find_or_create_person(other_email, other_name)

        # Build external ID
        external_id = f"imap:{message_id}"

        # Check if interaction exists
        existing = self.db.query(Interaction).filter(
            Interaction.external_id == external_id,
            Interaction.channel == InteractionChannel.IMAP
        ).first()

        # Check for automated/bulk
        is_automated = self._is_automated(from_email, msg)
        is_bulk = self._is_bulk(msg, len(to_list) + len(cc_list))
        is_meaningful = not is_automated and not is_bulk

        # Prepare participants
        participants = [{"email": from_email, "name": self._decode_header(from_name), "role": "from"}]
        for name, addr in to_list:
            participants.append({"email": addr.lower(), "name": name, "role": "to"})
        for name, addr in cc_list:
            participants.append({"email": addr.lower(), "name": name, "role": "cc"})

        if existing:
            existing.is_automated = is_automated
            existing.is_bulk = is_bulk
            existing.is_meaningful = is_meaningful
            return "updated"
        else:
            interaction = Interaction(
                id=str(uuid4()),
                person_id=person_id,
                kind=kind,
                occurred_at=sent_at,
                direction=direction,
                channel=InteractionChannel.IMAP,
                subject=subject[:500] if subject else None,
                participants=participants,
                external_id=external_id,
                source_account=settings.imap_username,
                is_automated=is_automated,
                is_bulk=is_bulk,
                is_meaningful=is_meaningful,
                raw_ref={"folder": folder, "uid": uid}
            )
            self.db.add(interaction)
            return "created"

    def _decode_header(self, value: str) -> str:
        """Decode email header value."""
        if not value:
            return ""
        decoded_parts = decode_header(value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(encoding or "utf-8", errors="replace"))
                except Exception:
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(part)
        return " ".join(result)

    def _parse_address_list(self, header: str) -> List[Tuple[str, str]]:
        """Parse a comma-separated list of email addresses."""
        if not header:
            return []
        addresses = []
        for addr in header.split(","):
            name, email_addr = parseaddr(addr.strip())
            if email_addr:
                addresses.append((self._decode_header(name), email_addr))
        return addresses

    def _detect_direction(
        self,
        from_email: str,
        to_list: List[Tuple[str, str]],
        cc_list: List[Tuple[str, str]]
    ) -> Optional[str]:
        """Detect email direction."""
        if from_email in self.own_emails:
            return "outbound"

        all_recipients = [addr.lower() for _, addr in to_list + cc_list]
        if any(e in self.own_emails for e in all_recipients):
            return "inbound"

        return "inbound"  # Default

    def _is_automated(self, from_email: str, msg: email.message.Message) -> bool:
        """Check if email is automated."""
        auto_patterns = ["noreply", "no-reply", "donotreply", "mailer-daemon", "postmaster"]
        if any(p in from_email for p in auto_patterns):
            return True

        # Check for auto-submitted header
        auto_submitted = msg.get("Auto-Submitted", "").lower()
        if auto_submitted and auto_submitted != "no":
            return True

        return False

    def _is_bulk(self, msg: email.message.Message, recipient_count: int) -> bool:
        """Check if email is bulk."""
        if msg.get("List-Unsubscribe"):
            return True
        if recipient_count > 10:
            return True
        if msg.get("Precedence", "").lower() in ["bulk", "list"]:
            return True
        return False

    def _find_or_create_person(self, email_addr: str, name: str = None) -> str:
        """Find or create a person by email."""
        person_email = self.db.query(PersonEmail).filter(
            PersonEmail.email == email_addr
        ).first()

        if person_email:
            return person_email.person_id

        if not name:
            name = email_addr.split("@")[0].replace(".", " ").replace("_", " ").title()

        person = Person(
            id=str(uuid4()),
            full_name=name,
            primary_email=email_addr,
            origin=PersonOrigin.EMAIL_ONLY,
            is_tracked=False
        )
        self.db.add(person)
        self.db.flush()

        email_record = PersonEmail(
            id=str(uuid4()),
            person_id=person.id,
            email=email_addr,
            is_primary=True,
            source="imap"
        )
        self.db.add(email_record)

        return person.id

    def _get_checkpoint(self, folder: str) -> Optional[Dict]:
        """Get checkpoint for folder."""
        checkpoint = self.db.query(IngestionCheckpoint).filter(
            IngestionCheckpoint.source == "imap",
            IngestionCheckpoint.account == settings.imap_username,
            IngestionCheckpoint.folder == folder
        ).first()
        return checkpoint.checkpoint_data if checkpoint else None

    def _update_checkpoint(self, folder: str, last_uid: int, processed: int) -> None:
        """Update checkpoint for folder."""
        checkpoint = self.db.query(IngestionCheckpoint).filter(
            IngestionCheckpoint.source == "imap",
            IngestionCheckpoint.account == settings.imap_username,
            IngestionCheckpoint.folder == folder
        ).first()

        checkpoint_data = {
            "last_uid": last_uid,
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "processed": processed
        }

        if checkpoint:
            checkpoint.checkpoint_data = checkpoint_data
        else:
            checkpoint = IngestionCheckpoint(
                id=str(uuid4()),
                source="imap",
                account=settings.imap_username,
                folder=folder,
                checkpoint_data=checkpoint_data
            )
            self.db.add(checkpoint)
