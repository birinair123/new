# LinkedIn-First Personal CRM - Implementation Plan

## Overview

A privacy-focused personal CRM where LinkedIn connections define the "people universe" and email/calendar data enriches interaction history.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WINDOWS VM                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  OST Extractor Service (Python + pywin32)                           │    │
│  │  - Reads Outlook via COM/MAPI                                       │    │
│  │  - Incremental extraction with checkpoints                          │    │
│  │  - Outputs: events.jsonl, series.jsonl, emails.jsonl               │    │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
│                             │                                                │
│                             ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Shared Folder (VMware/Parallels shared or SMB)                     │    │
│  │  /shared/crm_export/                                                │    │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
└─────────────────────────────┼───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              macOS HOST                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Backend (FastAPI + Celery/Background Jobs)                         │    │
│  │  - LinkedIn CSV ingestion                                           │    │
│  │  - IMAP polling (read-only)                                         │    │
│  │  - JSONL file watcher/ingestion                                     │    │
│  │  - Score computation engine                                         │    │
│  │  - REST API                                                         │    │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
│                             │                                                │
│  ┌──────────────────────────┴──────────────────────────────────────────┐    │
│  │  PostgreSQL Database                                                │    │
│  │  - people, person_emails, interactions                              │    │
│  │  - calendar_series, calendar_occurrences                            │    │
│  │  - person_scores                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Frontend (Next.js PWA)                                             │    │
│  │  - Mobile-first responsive UI                                       │    │
│  │  - Service worker for offline                                       │    │
│  │  - Simple auth (password/magic link)                                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Phone Browser  │
                    │  (PWA Install)  │
                    └─────────────────┘
```

## Milestones

### Milestone 1: Foundation (Week 1-2)
- [x] Repository structure
- [x] Database schema and migrations
- [x] Basic FastAPI skeleton with auth
- [x] LinkedIn CSV import
- [x] Basic person list UI

### Milestone 2: Calendar Integration (Week 3)
- [x] OST Extractor for calendar (Windows)
- [x] JSONL contract definitions
- [x] Calendar series + occurrences ingestion
- [x] Next/last meeting display in UI

### Milestone 3: Email Integration (Week 4)
- [ ] IMAP metadata extraction
- [ ] OST email extraction (Windows)
- [ ] Email matching to people
- [ ] Interaction timeline UI

### Milestone 4: Scoring & Polish (Week 5)
- [x] Score computation engine
- [x] Score breakdown UI
- [ ] Review queue for unlinked
- [ ] Promotion flows

### Milestone 5: Production Ready (Week 6)
- [ ] PWA manifest and service worker
- [ ] Deployment guide (Docker/fly.io)
- [ ] Security hardening
- [ ] Performance optimization

## Key Design Decisions

### 1. Privacy by Default
- Only metadata synced to cloud (from/to, subject, timestamps)
- Email bodies never stored unless explicitly enabled
- Snippets are opt-in and capped at 200 chars

### 2. LinkedIn-First Noise Control
- Only LinkedIn connections are "tracked" by default
- Email-only contacts are shadow records for matching
- Manual promotion flow to elevate important contacts

### 3. Calendar Fidelity
- Use Outlook COM/MAPI for accurate recurrence handling
- Store both series (RRULE) and expanded occurrences
- Track exceptions and cancellations properly

### 4. Idempotent Ingestion
- Every record has external_id + channel unique constraint
- Checkpointing allows resume after interruption
- Upsert semantics for all imports

## JSONL Contract Specifications

### events.jsonl (Calendar Occurrences)
```json
{
  "external_id": "AAMkAGI2...",
  "series_id": "AAMkAGI2...series",
  "subject": "Weekly 1:1 with John",
  "start_at": "2024-01-15T10:00:00-05:00",
  "end_at": "2024-01-15T10:30:00-05:00",
  "timezone": "America/New_York",
  "location": "Zoom",
  "organizer_email": "john@company.com",
  "participants": [
    {"email": "me@example.com", "name": "Me", "response": "accepted"},
    {"email": "john@company.com", "name": "John Doe", "response": "accepted"}
  ],
  "is_exception": false,
  "is_cancelled": false,
  "is_all_day": false,
  "extracted_at": "2024-01-20T15:30:00Z"
}
```

### series.jsonl (Calendar Series)
```json
{
  "external_id": "AAMkAGI2...series",
  "subject": "Weekly 1:1 with John",
  "organizer_email": "john@company.com",
  "timezone": "America/New_York",
  "start_at": "2024-01-01T10:00:00-05:00",
  "end_at": "2024-01-01T10:30:00-05:00",
  "rrule": "FREQ=WEEKLY;BYDAY=MO;COUNT=52",
  "recurrence_blob": {
    "type": "weekly",
    "interval": 1,
    "days_of_week": ["monday"],
    "count": 52,
    "exceptions": ["2024-01-22", "2024-02-19"]
  },
  "extracted_at": "2024-01-20T15:30:00Z"
}
```

### emails.jsonl (Email Metadata)
```json
{
  "external_id": "message-id@example.com",
  "conversation_id": "conv-123",
  "subject": "Re: Project Update",
  "from_email": "john@company.com",
  "from_name": "John Doe",
  "to": [{"email": "me@example.com", "name": "Me"}],
  "cc": [],
  "sent_at": "2024-01-15T14:30:00Z",
  "received_at": "2024-01-15T14:30:05Z",
  "direction": "inbound",
  "snippet": "Thanks for the update...",
  "has_attachments": true,
  "headers": {
    "list_unsubscribe": null,
    "x_mailer": "Microsoft Outlook"
  },
  "folder": "Inbox",
  "source_account": "work@example.com",
  "extracted_at": "2024-01-20T15:30:00Z"
}
```

## Assumptions & Defaults

1. **Single user system** - No multi-tenancy in v1
2. **Outlook 2016+** on Windows for OST extraction
3. **English names** - Fuzzy matching optimized for Western names
4. **Meeting = 2+ participants** - 1:1 meetings with self excluded
5. **Shared folder path**: `/shared/crm_export/` or configured via env
6. **Default IMAP poll interval**: 15 minutes
7. **Score recomputation**: On-demand or daily batch
