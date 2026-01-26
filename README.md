# LinkedIn CRM

A privacy-focused personal CRM where LinkedIn connections define your "people universe" and email/calendar data enriches interaction history.

## Features

- **LinkedIn-first**: Import connections from LinkedIn CSV, automatically track relationships
- **Calendar integration**: Sync meetings from Outlook OST via Windows VM extractor
- **Email metadata**: Track email interactions without storing full bodies (privacy by default)
- **Connection strength scores**: 0-100 explainable scores based on recency, frequency, meetings
- **Mobile-first PWA**: Access from your phone with offline support
- **Smart matching**: Fuzzy match email contacts to LinkedIn connections
- **Review queue**: Promote high-signal email-only contacts to tracked

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Windows VM                              │
│  OST Extractor (Python + pywin32)                          │
│  → Reads Outlook via COM/MAPI                              │
│  → Outputs: events.jsonl, series.jsonl, emails.jsonl       │
└────────────────────┬────────────────────────────────────────┘
                     │ Shared Folder
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                     macOS Host                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Backend (FastAPI + PostgreSQL)                      │  │
│  │  - LinkedIn CSV ingestion                            │  │
│  │  - IMAP sync (optional)                              │  │
│  │  - JSONL ingestion from Windows                      │  │
│  │  - Score computation engine                          │  │
│  │  - REST API                                          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Frontend (Next.js PWA)                              │  │
│  │  - Mobile-first responsive UI                        │  │
│  │  - People list with search                           │  │
│  │  - Person detail with timeline                       │  │
│  │  - Score breakdown visualization                     │  │
│  │  - Review queue for promotions                       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │   Phone     │
              │  (Browser)  │
              └─────────────┘
```

## Quick Start

### 1. Set up database

```bash
createdb linkedin_crm
psql linkedin_crm < backend/app/db/schema.sql
```

### 2. Run backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your settings
uvicorn app.main:app --reload
```

### 3. Run frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Import your LinkedIn data

1. Export connections from LinkedIn (Settings > Data Privacy > Get a copy)
2. Place CSV in `backend/data/linkedin/`
3. Run: `python cli.py ingest_linkedin`

## Project Structure

```
/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── api/            # REST API endpoints
│   │   ├── core/           # Config, auth, database
│   │   ├── db/             # Schema and migrations
│   │   ├── ingestion/      # Data import modules
│   │   ├── models/         # SQLAlchemy models
│   │   └── scoring/        # Score computation engine
│   ├── cli.py              # CLI commands
│   └── requirements.txt
│
├── frontend/               # Next.js PWA frontend
│   ├── app/               # Next.js App Router pages
│   ├── components/        # React components
│   ├── lib/               # API client, utilities
│   └── public/            # Static assets, manifest
│
├── ost_extractor_windows/ # Windows OST extractor
│   ├── extractor.py       # Outlook COM extraction
│   └── requirements.txt
│
└── docs/                  # Documentation
    ├── IMPLEMENTATION_PLAN.md
    └── SETUP.md
```

## Connection Strength Score

Scores are 0-100 with explainable breakdown:

| Component | Max Points | Description |
|-----------|------------|-------------|
| Recency | 30 | Days since last meaningful interaction |
| Frequency | 20 | Meaningful interactions in last 90 days |
| Bidirectionality | 15 | Mix of inbound/outbound + bonus if they initiate |
| Meetings | 20 | Meetings in last year + bonus for upcoming |
| Context | 15 | LinkedIn connection + tags (VIP, key relationship) |

## CLI Commands

```bash
# Data ingestion
python cli.py ingest_linkedin [csv_path]
python cli.py ingest_ost_calendar
python cli.py ingest_ost_emails
python cli.py ingest_imap INBOX --days 30

# Score computation
python cli.py recompute_scores
python cli.py recompute_scores --person_id UUID

# Maintenance
python cli.py refresh_review_queue
python cli.py init_db
```

## Privacy Features

- **Metadata-only by default**: Only stores from/to/subject, not email bodies
- **Snippets are opt-in**: Configurable, capped at 200 chars
- **LinkedIn-first noise control**: Only tracked contacts visible by default
- **No cloud sync**: All data stays on your machine unless you deploy it

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/people` | List people with filtering/search |
| `GET /api/people/{id}` | Get person details |
| `POST /api/people/{id}/promote` | Promote email-only to tracked |
| `GET /api/interactions/person/{id}/timeline` | Get interaction history |
| `GET /api/interactions/upcoming` | Get upcoming meetings |
| `GET /api/scores` | Get score leaderboard |
| `POST /api/scores/recompute` | Trigger score recomputation |
| `GET /api/review` | Get review queue items |
| `POST /api/review/{id}/action` | Accept/reject review item |
| `POST /api/ingestion/linkedin` | Trigger LinkedIn import |
| `POST /api/ingestion/ost/calendar` | Trigger calendar import |

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy 2.0, PostgreSQL
- **Frontend**: Next.js 14, React 18, Tailwind CSS, SWR
- **Windows Extractor**: Python with pywin32 for Outlook COM
- **Mobile**: PWA with service worker for offline support

## License

MIT

## Contributing

This is a personal CRM designed for individual use. Feel free to fork and customize for your needs.
