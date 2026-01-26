# LinkedIn CRM Setup Guide

Complete setup instructions for the LinkedIn-first personal CRM.

## Prerequisites

- macOS for development and hosting
- Windows VM (VMware/Parallels) with Outlook installed
- PostgreSQL 14+
- Python 3.10+
- Node.js 18+
- Docker (optional, for containerized deployment)

## Quick Start

### 1. Database Setup

```bash
# Install PostgreSQL (macOS)
brew install postgresql@14
brew services start postgresql@14

# Create database
createdb linkedin_crm
createuser crm --password  # Set password: crm

# Apply schema
cd backend
psql linkedin_crm < app/db/schema.sql
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Initialize database (if not done via SQL)
python cli.py init_db

# Run development server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The app is now available at http://localhost:3000

### 4. Windows VM Extractor Setup

On the Windows VM:

```powershell
# Install Python (if not installed)
# Download from python.org

# Set up extractor
cd C:\path\to\ost_extractor_windows
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Configure shared folder (see below)
```

## Detailed Configuration

### Environment Variables (Backend)

Create `/backend/.env`:

```env
# Database
DATABASE_URL=postgresql://crm:crm@localhost:5432/linkedin_crm

# Authentication (CHANGE THIS!)
AUTH_PASSWORD=your-secure-password
AUTH_SECRET_KEY=generate-a-random-32-char-string

# Your email addresses for direction detection
OWN_EMAILS=you@example.com,your.work@company.com

# IMAP (optional)
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=you@gmail.com
IMAP_PASSWORD=your-app-specific-password
IMAP_USE_SSL=true

# Paths
DATA_DIR=./data
LINKEDIN_CSV_DIR=./data/linkedin
OST_EXPORT_DIR=/shared/crm_export

# Privacy
STORE_EMAIL_SNIPPETS=true
SNIPPET_MAX_LENGTH=200
```

### Shared Folder Configuration

#### VMware Fusion

1. VM Settings > Sharing > Add a shared folder
2. Point to a macOS folder (e.g., `/Users/you/shared/crm_export`)
3. On Windows, access as `\\vmware-host\Shared Folders\crm_export`

#### Parallels Desktop

1. Preferences > Options > Sharing
2. Enable "Share Mac folders with Windows"
3. Add your export folder

#### Manual SMB Share

```bash
# On macOS, create shared folder
mkdir -p /Users/you/shared/crm_export

# On Windows
net use Z: \\mac.local\shared
```

Update `OST_EXPORT_DIR` in backend `.env` to match.

### LinkedIn Data Export

1. Go to LinkedIn Settings > Data Privacy > Get a copy of your data
2. Select "Connections" only for fastest export
3. Download the ZIP when ready
4. Extract and place CSV in `backend/data/linkedin/`

### Running the OST Extractor

On Windows VM:

```powershell
# Activate environment
cd C:\ost_extractor_windows
.\venv\Scripts\activate

# Extract calendar (last year + next 3 months)
python extractor.py calendar --output Z:\crm_export --days 365 --days-forward 90

# Extract emails (optional, last 90 days)
python extractor.py emails --output Z:\crm_export --days 90

# Or extract everything
python extractor.py all --output Z:\crm_export
```

### Ingesting Data

From macOS:

```bash
cd backend
source venv/bin/activate

# Import LinkedIn connections
python cli.py ingest_linkedin

# Import calendar data
python cli.py ingest_ost_calendar

# Import email metadata (optional)
python cli.py ingest_ost_emails

# Compute connection scores
python cli.py recompute_scores
```

## Deployment for Phone Access

### Option 1: Tailscale (Recommended)

1. Install Tailscale on your Mac and phone
2. Run the backend and frontend on your Mac
3. Access via Tailscale IP from phone

```bash
# Run production build
cd frontend && npm run build && npm start &
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

### Option 2: Cloudflare Tunnel

```bash
# Install cloudflared
brew install cloudflared

# Create tunnel
cloudflared tunnel create linkedin-crm

# Configure tunnel (creates config.yml)
cloudflared tunnel route dns linkedin-crm crm.yourdomain.com

# Run tunnel
cloudflared tunnel run linkedin-crm
```

### Option 3: Docker Deployment

```bash
# Build and run with docker-compose
docker-compose up -d

# Or deploy to fly.io, Railway, etc.
```

## CLI Reference

```bash
# Database
python cli.py init_db                    # Create tables

# Ingestion
python cli.py ingest_linkedin [csv_path] # Import LinkedIn CSV
python cli.py ingest_ost_calendar        # Import calendar JSONL
python cli.py ingest_ost_emails          # Import email JSONL
python cli.py ingest_imap [folder]       # Sync from IMAP

# Scoring
python cli.py recompute_scores           # Recompute all scores
python cli.py recompute_scores --person_id UUID  # Single person

# Maintenance
python cli.py refresh_review_queue       # Update review queue
```

## Troubleshooting

### "Connection refused" on API calls

Check the backend is running: `curl http://localhost:8000/api/health`

### "401 Unauthorized"

Clear browser cookies and re-login with the password from your `.env`

### Calendar events not showing

1. Verify OST extractor created files: `ls /shared/crm_export/`
2. Check ingestion: `python cli.py ingest_ost_calendar`
3. Check logs for errors

### Scores are all zero

Run `python cli.py recompute_scores` after importing data.

### Windows extractor can't connect to Outlook

- Ensure Outlook is closed before running the extractor
- Run as the same Windows user that owns the Outlook profile
- Check Outlook is properly configured with the account

## Security Notes

1. **Change the default password** in `.env`
2. **Use HTTPS** in production (via reverse proxy or Cloudflare Tunnel)
3. **Never expose** the backend directly to the internet without auth
4. **Rotate secrets** periodically
5. **IMAP passwords** should use app-specific passwords, not main account passwords

## Backup

```bash
# Backup database
pg_dump linkedin_crm > backup.sql

# Restore
psql linkedin_crm < backup.sql
```
