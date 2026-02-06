#!/usr/bin/env python3
"""
Outlook OST Extractor for Windows

Extracts calendar and email data from Outlook via COM/MAPI interface.
Outputs newline-delimited JSON (JSONL) files for import into the CRM.

Requirements:
- Windows with Outlook installed
- Python 3.8+ with pywin32
- Outlook profile configured with the OST file

Usage:
    python extractor.py calendar --output /path/to/output
    python extractor.py emails --output /path/to/output --days 90
    python extractor.py all --output /path/to/output
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import hashlib

# Check for Windows
if sys.platform != 'win32':
    print("This script must be run on Windows with Outlook installed.")
    sys.exit(1)

try:
    import win32com.client
    import pythoncom
    from pywintypes import com_error
except ImportError:
    print("Please install pywin32: pip install pywin32")
    sys.exit(1)


class CheckpointManager:
    """Manage extraction checkpoints for incremental/resumable extraction."""

    def __init__(self, output_dir: Path):
        self.checkpoint_file = output_dir / "checkpoint.json"
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r') as f:
                return json.load(f)
        return {}

    def save(self):
        with open(self.checkpoint_file, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()


class OutlookExtractor:
    """Extract data from Outlook via COM/MAPI."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint = CheckpointManager(self.output_dir)

        # Initialize COM
        pythoncom.CoInitialize()

        # Connect to Outlook
        try:
            self.outlook = win32com.client.Dispatch("Outlook.Application")
            self.namespace = self.outlook.GetNamespace("MAPI")
        except com_error as e:
            print(f"Failed to connect to Outlook: {e}")
            sys.exit(1)

        # Outlook folder types
        self.FOLDER_CALENDAR = 9
        self.FOLDER_INBOX = 6
        self.FOLDER_SENT = 5

    def extract_calendar(self, days_back: int = 365, days_forward: int = 90) -> Dict[str, int]:
        """
        Extract calendar events and series.

        Args:
            days_back: Days in the past to extract
            days_forward: Days in the future to extract

        Returns:
            Dict with counts of extracted items.
        """
        result = {"series": 0, "events": 0, "errors": 0}

        events_file = self.output_dir / "events.jsonl"
        series_file = self.output_dir / "series.jsonl"

        # Get date range
        start_date = datetime.now() - timedelta(days=days_back)
        end_date = datetime.now() + timedelta(days=days_forward)

        print(f"Extracting calendar events from {start_date.date()} to {end_date.date()}")

        # Track series we've already exported
        exported_series = set()

        with open(events_file, 'w', encoding='utf-8') as ef, \
             open(series_file, 'w', encoding='utf-8') as sf:

            # Get all calendar folders
            for folder in self._get_calendar_folders():
                try:
                    items = folder.Items
                    items.Sort("[Start]")
                    items.IncludeRecurrences = True

                    # Filter by date range
                    restriction = f"[Start] >= '{start_date.strftime('%m/%d/%Y')}' AND [Start] <= '{end_date.strftime('%m/%d/%Y')}'"
                    filtered_items = items.Restrict(restriction)

                    for item in filtered_items:
                        try:
                            event_data = self._extract_calendar_item(item)
                            if event_data:
                                # Write event
                                ef.write(json.dumps(event_data, default=str) + '\n')
                                result["events"] += 1

                                # Export series if recurring and not yet exported
                                if item.IsRecurring and event_data.get("series_id"):
                                    series_id = event_data["series_id"]
                                    if series_id not in exported_series:
                                        series_data = self._extract_series(item)
                                        if series_data:
                                            sf.write(json.dumps(series_data, default=str) + '\n')
                                            result["series"] += 1
                                            exported_series.add(series_id)

                        except Exception as e:
                            result["errors"] += 1
                            print(f"Error extracting calendar item: {e}")

                except Exception as e:
                    print(f"Error processing calendar folder: {e}")

        self.checkpoint.set("calendar_last_run", datetime.now().isoformat())
        self.checkpoint.set("calendar_events", result["events"])

        print(f"Extracted {result['events']} events, {result['series']} series")
        return result

    def _get_calendar_folders(self):
        """Get all calendar folders across all accounts."""
        folders = []

        # Default calendar
        try:
            default_calendar = self.namespace.GetDefaultFolder(self.FOLDER_CALENDAR)
            folders.append(default_calendar)
        except:
            pass

        # Additional calendars in each store
        for store in self.namespace.Stores:
            try:
                root = store.GetRootFolder()
                for folder in root.Folders:
                    if folder.DefaultItemType == 1:  # olAppointmentItem
                        if folder not in folders:
                            folders.append(folder)
            except:
                pass

        return folders

    def _extract_calendar_item(self, item) -> Optional[Dict[str, Any]]:
        """Extract data from a single calendar item."""
        try:
            # Generate stable external ID
            external_id = self._generate_id(item.EntryID)

            # Get series ID for recurring items
            series_id = None
            is_exception = False
            if item.IsRecurring:
                try:
                    # For recurring items, use the master appointment's EntryID
                    master = item.Parent.Items.GetFirst()  # This might not work perfectly
                    series_id = self._generate_id(item.EntryID.split('_')[0] if '_' in item.EntryID else item.EntryID)
                except:
                    series_id = external_id + "_series"

                # Check if this is an exception
                try:
                    is_exception = hasattr(item, 'RecurrenceState') and item.RecurrenceState == 2
                except:
                    pass

            # Extract participants
            participants = []
            try:
                if item.Organizer:
                    participants.append({
                        "email": self._get_email_from_name(item.Organizer),
                        "name": item.Organizer,
                        "response": "organizer"
                    })
            except:
                pass

            try:
                for recipient in item.Recipients:
                    email = ""
                    try:
                        email = recipient.Address
                        if not email or "@" not in email:
                            # Try to get SMTP address from AddressEntry
                            entry = recipient.AddressEntry
                            if entry.Type == "EX":
                                email = entry.GetExchangeUser().PrimarySmtpAddress if entry.GetExchangeUser() else ""
                            else:
                                email = entry.Address
                    except:
                        pass

                    response = "unknown"
                    try:
                        response_map = {0: "none", 1: "organizer", 2: "tentative", 3: "accepted", 4: "declined"}
                        response = response_map.get(recipient.MeetingResponseStatus, "unknown")
                    except:
                        pass

                    participants.append({
                        "email": email.lower() if email else "",
                        "name": recipient.Name,
                        "response": response
                    })
            except:
                pass

            return {
                "external_id": external_id,
                "series_id": series_id,
                "subject": item.Subject,
                "start_at": item.Start.isoformat() if item.Start else None,
                "end_at": item.End.isoformat() if item.End else None,
                "timezone": self._get_timezone(item),
                "location": item.Location,
                "organizer_email": self._get_email_from_name(item.Organizer) if item.Organizer else None,
                "participants": participants,
                "is_exception": is_exception,
                "is_cancelled": item.MeetingStatus == 5 if hasattr(item, 'MeetingStatus') else False,
                "is_all_day": item.AllDayEvent,
                "extracted_at": datetime.now().isoformat()
            }

        except Exception as e:
            print(f"Error extracting calendar item: {e}")
            return None

    def _extract_series(self, item) -> Optional[Dict[str, Any]]:
        """Extract series/recurrence pattern from a recurring item."""
        try:
            pattern = item.GetRecurrencePattern()

            # Build RRULE string
            rrule_parts = []

            # Frequency
            freq_map = {0: "DAILY", 1: "WEEKLY", 2: "MONTHLY", 3: "MONTHNTH", 4: "YEARLY", 5: "YEARNTH"}
            freq = freq_map.get(pattern.RecurrenceType, "WEEKLY")
            rrule_parts.append(f"FREQ={freq}")

            # Interval
            if pattern.Interval > 1:
                rrule_parts.append(f"INTERVAL={pattern.Interval}")

            # Days of week (for weekly)
            if pattern.RecurrenceType == 1:  # Weekly
                days = []
                day_mask = pattern.DayOfWeekMask
                day_names = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]
                for i, day in enumerate(day_names):
                    if day_mask & (1 << i):
                        days.append(day)
                if days:
                    rrule_parts.append(f"BYDAY={','.join(days)}")

            # Day of month (for monthly)
            if pattern.RecurrenceType in [2, 3]:
                try:
                    rrule_parts.append(f"BYMONTHDAY={pattern.DayOfMonth}")
                except:
                    pass

            # End condition
            if pattern.NoEndDate:
                pass  # No end
            elif pattern.Occurrences:
                rrule_parts.append(f"COUNT={pattern.Occurrences}")
            elif pattern.PatternEndDate:
                rrule_parts.append(f"UNTIL={pattern.PatternEndDate.strftime('%Y%m%dT%H%M%SZ')}")

            rrule = ";".join(rrule_parts)

            # Recurrence blob with full details
            recurrence_blob = {
                "type": freq.lower(),
                "interval": pattern.Interval,
                "day_of_week_mask": pattern.DayOfWeekMask,
                "day_of_month": getattr(pattern, 'DayOfMonth', None),
                "month_of_year": getattr(pattern, 'MonthOfYear', None),
                "no_end_date": pattern.NoEndDate,
                "occurrences": pattern.Occurrences if not pattern.NoEndDate else None,
                "pattern_end_date": pattern.PatternEndDate.isoformat() if pattern.PatternEndDate else None,
                "exceptions": []
            }

            # Get exceptions
            try:
                for exception in pattern.Exceptions:
                    recurrence_blob["exceptions"].append({
                        "original_date": exception.OriginalDate.isoformat(),
                        "deleted": exception.Deleted
                    })
            except:
                pass

            series_id = self._generate_id(item.EntryID.split('_')[0] if '_' in item.EntryID else item.EntryID)

            return {
                "external_id": series_id,
                "subject": item.Subject,
                "organizer_email": self._get_email_from_name(item.Organizer) if item.Organizer else None,
                "timezone": self._get_timezone(item),
                "start_at": pattern.StartTime.isoformat() if pattern.StartTime else None,
                "end_at": pattern.EndTime.isoformat() if pattern.EndTime else None,
                "rrule": rrule,
                "recurrence_blob": recurrence_blob,
                "extracted_at": datetime.now().isoformat()
            }

        except Exception as e:
            print(f"Error extracting series: {e}")
            return None

    def extract_emails(self, days_back: int = 90, folders: List[str] = None) -> Dict[str, int]:
        """
        Extract email metadata.

        Args:
            days_back: Days of emails to extract
            folders: List of folder names to extract (default: Inbox, Sent)

        Returns:
            Dict with counts of extracted items.
        """
        result = {"emails": 0, "errors": 0}

        emails_file = self.output_dir / "emails.jsonl"

        # Date filter
        since_date = datetime.now() - timedelta(days=days_back)

        print(f"Extracting emails since {since_date.date()}")

        # Get last checkpoint
        last_checkpoint = self.checkpoint.get("email_last_date")

        with open(emails_file, 'w', encoding='utf-8') as f:
            # Process inbox
            try:
                inbox = self.namespace.GetDefaultFolder(self.FOLDER_INBOX)
                result["emails"] += self._extract_folder_emails(f, inbox, since_date, "Inbox")
            except Exception as e:
                print(f"Error processing Inbox: {e}")

            # Process sent items
            try:
                sent = self.namespace.GetDefaultFolder(self.FOLDER_SENT)
                result["emails"] += self._extract_folder_emails(f, sent, since_date, "Sent")
            except Exception as e:
                print(f"Error processing Sent: {e}")

        self.checkpoint.set("email_last_run", datetime.now().isoformat())
        self.checkpoint.set("email_count", result["emails"])

        print(f"Extracted {result['emails']} emails")
        return result

    def _extract_folder_emails(self, file, folder, since_date: datetime, folder_name: str) -> int:
        """Extract emails from a single folder."""
        count = 0

        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)  # Descending

            # Restrict by date
            restriction = f"[ReceivedTime] >= '{since_date.strftime('%m/%d/%Y')}'"
            filtered = items.Restrict(restriction)

            for item in filtered:
                try:
                    email_data = self._extract_email_item(item, folder_name)
                    if email_data:
                        file.write(json.dumps(email_data, default=str) + '\n')
                        count += 1

                        # Progress indicator
                        if count % 100 == 0:
                            print(f"  Processed {count} emails from {folder_name}...")

                except Exception as e:
                    pass  # Skip individual email errors silently

        except Exception as e:
            print(f"Error processing folder {folder_name}: {e}")

        return count

    def _extract_email_item(self, item, folder_name: str) -> Optional[Dict[str, Any]]:
        """Extract metadata from a single email."""
        try:
            # Get message ID
            message_id = ""
            try:
                # PR_INTERNET_MESSAGE_ID
                message_id = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1035001F")
            except:
                message_id = self._generate_id(item.EntryID)

            # Get conversation ID
            conversation_id = ""
            try:
                conversation_id = item.ConversationID
            except:
                pass

            # Determine direction
            direction = "inbound"
            if folder_name == "Sent" or item.SenderEmailAddress == self.namespace.CurrentUser.Address:
                direction = "outbound"

            # Extract recipients
            to_list = []
            cc_list = []
            try:
                for recipient in item.Recipients:
                    email = self._get_recipient_email(recipient)
                    entry = {
                        "email": email.lower() if email else "",
                        "name": recipient.Name
                    }
                    if recipient.Type == 1:  # TO
                        to_list.append(entry)
                    elif recipient.Type == 2:  # CC
                        cc_list.append(entry)
            except:
                pass

            # Get sender email
            sender_email = ""
            try:
                if item.SenderEmailType == "EX":
                    sender = item.Sender.GetExchangeUser()
                    sender_email = sender.PrimarySmtpAddress if sender else item.SenderEmailAddress
                else:
                    sender_email = item.SenderEmailAddress
            except:
                sender_email = item.SenderEmailAddress

            # Get snippet (first 200 chars of body)
            snippet = ""
            try:
                body = item.Body
                if body:
                    # Clean up and truncate
                    snippet = ' '.join(body.split())[:200]
            except:
                pass

            # Check for list-unsubscribe header
            list_unsubscribe = None
            try:
                list_unsubscribe = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/string/{00020386-0000-0000-C000-000000000046}/list-unsubscribe")
            except:
                pass

            return {
                "external_id": message_id,
                "conversation_id": conversation_id,
                "subject": item.Subject,
                "from_email": sender_email.lower() if sender_email else "",
                "from_name": item.SenderName,
                "to": to_list,
                "cc": cc_list,
                "sent_at": item.SentOn.isoformat() if item.SentOn else None,
                "received_at": item.ReceivedTime.isoformat() if item.ReceivedTime else None,
                "direction": direction,
                "snippet": snippet,
                "has_attachments": item.Attachments.Count > 0,
                "headers": {
                    "list_unsubscribe": list_unsubscribe
                },
                "folder": folder_name,
                "source_account": self.namespace.CurrentUser.Address,
                "extracted_at": datetime.now().isoformat()
            }

        except Exception as e:
            return None

    def _get_recipient_email(self, recipient) -> str:
        """Get SMTP email address from a recipient."""
        try:
            if recipient.AddressEntry.Type == "EX":
                user = recipient.AddressEntry.GetExchangeUser()
                if user:
                    return user.PrimarySmtpAddress
            return recipient.Address
        except:
            return recipient.Address

    def _get_email_from_name(self, name: str) -> str:
        """Try to extract email from organizer name (often includes email)."""
        if not name:
            return ""
        # Sometimes the name is "Name <email@example.com>"
        if "<" in name and ">" in name:
            start = name.index("<") + 1
            end = name.index(">")
            return name[start:end].lower()
        return ""

    def _get_timezone(self, item) -> str:
        """Get timezone for a calendar item."""
        try:
            return item.StartTimeZone.Name
        except:
            return "UTC"

    def _generate_id(self, entry_id: str) -> str:
        """Generate a stable external ID from Outlook's EntryID."""
        if not entry_id:
            return ""
        # EntryIDs can be very long, so we hash them
        return hashlib.md5(entry_id.encode()).hexdigest()

    def cleanup(self):
        """Cleanup COM resources."""
        pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(description="Outlook OST Extractor")
    parser.add_argument("command", choices=["calendar", "emails", "all", "info"],
                        help="What to extract (use 'info' to show connected accounts)")
    parser.add_argument("--output", "-o",
                        help="Output directory for JSONL files (required except for 'info')")
    parser.add_argument("--days", type=int, default=365,
                        help="Days of history to extract (default: 365)")
    parser.add_argument("--days-forward", type=int, default=90,
                        help="Days of future calendar to extract (default: 90)")

    args = parser.parse_args()

    # Info command doesn't need output dir
    if args.command == "info":
        show_outlook_info()
        return

    if not args.output:
        parser.error("--output is required for calendar/emails/all commands")

    output_dir = Path(args.output)
    extractor = OutlookExtractor(output_dir)

    try:
        if args.command in ["calendar", "all"]:
            print("\n=== Extracting Calendar ===")
            extractor.extract_calendar(
                days_back=args.days,
                days_forward=args.days_forward
            )

        if args.command in ["emails", "all"]:
            print("\n=== Extracting Emails ===")
            extractor.extract_emails(days_back=args.days)

        print("\n=== Done! ===")
        print(f"Output files in: {output_dir}")

    finally:
        extractor.cleanup()


def show_outlook_info():
    """Display diagnostic info about connected Outlook accounts."""
    pythoncom.CoInitialize()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")

        print("\n=== Outlook Connection Info ===\n")

        # Current user
        try:
            print(f"Current User: {namespace.CurrentUser.Name}")
            print(f"Current User Address: {namespace.CurrentUser.Address}")
        except Exception as e:
            print(f"Could not get current user: {e}")

        # List all stores (accounts/OST files)
        print("\n--- Connected Stores/Accounts ---")
        for i, store in enumerate(namespace.Stores, 1):
            try:
                print(f"\n  Store {i}: {store.DisplayName}")
                print(f"    File Path: {store.FilePath}")
                print(f"    Store Type: {store.ExchangeStoreType}")
            except Exception as e:
                print(f"  Store {i}: Error reading details - {e}")

        # List calendar folders
        print("\n--- Calendar Folders ---")
        FOLDER_CALENDAR = 9

        # Default calendar
        try:
            default_cal = namespace.GetDefaultFolder(FOLDER_CALENDAR)
            print(f"\n  Default Calendar: {default_cal.Name}")
            print(f"    Items: {default_cal.Items.Count}")
        except Exception as e:
            print(f"  Default Calendar: Error - {e}")

        # Calendars in each store
        for store in namespace.Stores:
            try:
                root = store.GetRootFolder()
                for folder in root.Folders:
                    if folder.DefaultItemType == 1:  # olAppointmentItem
                        print(f"\n  Calendar: {store.DisplayName} / {folder.Name}")
                        print(f"    Items: {folder.Items.Count}")
            except:
                pass

        print("\n")

    except com_error as e:
        print(f"Failed to connect to Outlook: {e}")
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
