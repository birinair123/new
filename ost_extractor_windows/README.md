# OST Extractor for Windows

Extracts calendar and email data from Microsoft Outlook via COM/MAPI interface.

## Prerequisites

1. **Windows** with Microsoft Outlook installed
2. **Outlook profile** configured with the OST file you want to extract from
3. **Python 3.8+** installed on Windows
4. **pywin32** package

## Installation

```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

## Usage

### Extract Calendar Events

```powershell
python extractor.py calendar --output C:\shared\crm_export --days 365
```

This creates:
- `events.jsonl` - Individual calendar occurrences
- `series.jsonl` - Recurring event definitions

### Extract Email Metadata

```powershell
python extractor.py emails --output C:\shared\crm_export --days 90
```

This creates:
- `emails.jsonl` - Email metadata (from/to/subject/timestamps)

### Extract Everything

```powershell
python extractor.py all --output C:\shared\crm_export --days 365
```

## Shared Folder Setup

For the macOS aggregator to access these files, set up a shared folder:

### Option 1: VMware/Parallels Shared Folders

1. In your VM settings, add a shared folder pointing to a macOS directory
2. Access it from Windows as `\\vmware-host\Shared Folders\folder_name` or similar
3. Use that path as your `--output` directory

### Option 2: SMB Share

1. Create a shared folder on your Mac
2. Mount it on Windows: `net use Z: \\machost\share`
3. Use `Z:\crm_export` as your output directory

## Output Format

### events.jsonl

```json
{
  "external_id": "abc123...",
  "series_id": "def456...",
  "subject": "Weekly 1:1 with John",
  "start_at": "2024-01-15T10:00:00-05:00",
  "end_at": "2024-01-15T10:30:00-05:00",
  "timezone": "Eastern Standard Time",
  "location": "Zoom",
  "organizer_email": "john@company.com",
  "participants": [
    {"email": "me@example.com", "name": "Me", "response": "accepted"},
    {"email": "john@company.com", "name": "John", "response": "organizer"}
  ],
  "is_exception": false,
  "is_cancelled": false,
  "is_all_day": false,
  "extracted_at": "2024-01-20T15:30:00"
}
```

### series.jsonl

```json
{
  "external_id": "def456...",
  "subject": "Weekly 1:1 with John",
  "organizer_email": "john@company.com",
  "timezone": "Eastern Standard Time",
  "start_at": "2024-01-01T10:00:00",
  "end_at": "2024-01-01T10:30:00",
  "rrule": "FREQ=WEEKLY;BYDAY=MO",
  "recurrence_blob": {
    "type": "weekly",
    "interval": 1,
    "day_of_week_mask": 2,
    "exceptions": [
      {"original_date": "2024-02-19T10:00:00", "deleted": true}
    ]
  },
  "extracted_at": "2024-01-20T15:30:00"
}
```

### emails.jsonl

```json
{
  "external_id": "message-id@example.com",
  "conversation_id": "conv123",
  "subject": "Re: Project Update",
  "from_email": "john@company.com",
  "from_name": "John Doe",
  "to": [{"email": "me@example.com", "name": "Me"}],
  "cc": [],
  "sent_at": "2024-01-15T14:30:00",
  "received_at": "2024-01-15T14:30:05",
  "direction": "inbound",
  "snippet": "Thanks for the update on the project...",
  "has_attachments": false,
  "headers": {"list_unsubscribe": null},
  "folder": "Inbox",
  "source_account": "me@company.com",
  "extracted_at": "2024-01-20T15:30:00"
}
```

## Checkpointing

The extractor saves a `checkpoint.json` file in the output directory to track:
- Last extraction time
- Number of items extracted
- Can be used for incremental extraction in future versions

## Troubleshooting

### "Failed to connect to Outlook"

- Ensure Outlook is installed and configured with a profile
- Run the script as the same user that owns the Outlook profile
- If Outlook is running, try closing it first

### Missing emails/events

- The OST file must be synchronized with the Exchange server
- Increase the `--days` parameter to go further back in history

### Performance on large OST files

- For 30GB+ OST files, initial extraction may take 30-60 minutes
- Email extraction is typically slower than calendar
- Use `--days` to limit the scope if needed

## Scheduling

You can schedule this script to run periodically using Windows Task Scheduler:

```powershell
# Create a scheduled task (run daily at 2 AM)
schtasks /create /tn "CRM OST Extract" /tr "python C:\path\to\extractor.py all --output C:\shared\crm_export" /sc daily /st 02:00
```
