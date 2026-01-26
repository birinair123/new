"""Ingestion API endpoints for triggering data imports."""
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.auth import get_current_user


router = APIRouter()


class IngestionResult(BaseModel):
    """Result of an ingestion operation."""
    success: bool
    message: str
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    errors: list = []


class IngestionStatus(BaseModel):
    """Status of ingestion sources."""
    linkedin_csv_available: bool
    ost_jsonl_available: bool
    imap_configured: bool
    last_linkedin_import: Optional[str]
    last_ost_import: Optional[str]
    last_imap_sync: Optional[str]


@router.get("/status", response_model=IngestionStatus)
async def get_ingestion_status(
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Get status of all ingestion sources."""
    from app.models import IngestionCheckpoint

    # Check for LinkedIn CSV files
    linkedin_csv_available = False
    if settings.linkedin_csv_dir.exists():
        csv_files = list(settings.linkedin_csv_dir.glob("*.csv"))
        linkedin_csv_available = len(csv_files) > 0

    # Check for OST JSONL files
    ost_jsonl_available = False
    if settings.ost_export_dir.exists():
        jsonl_files = list(settings.ost_export_dir.glob("*.jsonl"))
        ost_jsonl_available = len(jsonl_files) > 0

    # Check IMAP configuration
    imap_configured = bool(settings.imap_server and settings.imap_username)

    # Get last import timestamps
    def get_last_checkpoint(source: str) -> Optional[str]:
        checkpoint = db.query(IngestionCheckpoint).filter(
            IngestionCheckpoint.source == source
        ).order_by(IngestionCheckpoint.updated_at.desc()).first()
        return checkpoint.updated_at.isoformat() if checkpoint else None

    return IngestionStatus(
        linkedin_csv_available=linkedin_csv_available,
        ost_jsonl_available=ost_jsonl_available,
        imap_configured=imap_configured,
        last_linkedin_import=get_last_checkpoint("linkedin"),
        last_ost_import=get_last_checkpoint("ost_calendar"),
        last_imap_sync=get_last_checkpoint("imap")
    )


@router.post("/linkedin", response_model=IngestionResult)
async def ingest_linkedin_csv(
    file: Optional[UploadFile] = File(None),
    filename: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Import LinkedIn connections from CSV.
    Either upload a file or specify a filename in the linkedin_csv_dir.
    """
    from app.ingestion.linkedin import LinkedInIngester

    ingester = LinkedInIngester(db)

    if file:
        # Handle uploaded file
        content = await file.read()
        csv_path = settings.linkedin_csv_dir / file.filename
        settings.linkedin_csv_dir.mkdir(parents=True, exist_ok=True)
        csv_path.write_bytes(content)
    elif filename:
        csv_path = settings.linkedin_csv_dir / filename
        if not csv_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    else:
        # Look for the most recent CSV in the directory
        csv_files = sorted(settings.linkedin_csv_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not csv_files:
            raise HTTPException(status_code=404, detail="No LinkedIn CSV files found")
        csv_path = csv_files[0]

    try:
        result = ingester.ingest_csv(csv_path)
        return IngestionResult(
            success=True,
            message=f"LinkedIn CSV imported from {csv_path.name}",
            records_processed=result["processed"],
            records_created=result["created"],
            records_updated=result["updated"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        return IngestionResult(
            success=False,
            message=str(e),
            errors=[str(e)]
        )


@router.post("/ost/calendar", response_model=IngestionResult)
async def ingest_ost_calendar(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Import calendar data from OST export JSONL files.
    Looks for events.jsonl and series.jsonl in the ost_export_dir.
    """
    from app.ingestion.calendar import CalendarIngester

    events_path = settings.ost_export_dir / "events.jsonl"
    series_path = settings.ost_export_dir / "series.jsonl"

    if not events_path.exists() and not series_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No calendar JSONL files found in export directory"
        )

    ingester = CalendarIngester(db)

    try:
        result = ingester.ingest_jsonl(
            events_path=events_path if events_path.exists() else None,
            series_path=series_path if series_path.exists() else None
        )
        return IngestionResult(
            success=True,
            message="Calendar data imported from OST export",
            records_processed=result["processed"],
            records_created=result["created"],
            records_updated=result["updated"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        return IngestionResult(
            success=False,
            message=str(e),
            errors=[str(e)]
        )


@router.post("/ost/emails", response_model=IngestionResult)
async def ingest_ost_emails(
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Import email metadata from OST export JSONL file.
    Looks for emails.jsonl in the ost_export_dir.
    """
    from app.ingestion.email import EmailIngester

    emails_path = settings.ost_export_dir / "emails.jsonl"

    if not emails_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No emails.jsonl found in export directory"
        )

    ingester = EmailIngester(db)

    try:
        result = ingester.ingest_jsonl(emails_path)
        return IngestionResult(
            success=True,
            message="Email metadata imported from OST export",
            records_processed=result["processed"],
            records_created=result["created"],
            records_updated=result["updated"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        return IngestionResult(
            success=False,
            message=str(e),
            errors=[str(e)]
        )


@router.post("/imap", response_model=IngestionResult)
async def sync_imap(
    folder: str = "INBOX",
    days: int = 30,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Sync email metadata from IMAP server.
    Requires IMAP settings to be configured.
    """
    if not settings.imap_server or not settings.imap_username:
        raise HTTPException(
            status_code=400,
            detail="IMAP not configured. Set IMAP_SERVER, IMAP_USERNAME, IMAP_PASSWORD in environment."
        )

    from app.ingestion.imap import IMAPIngester

    ingester = IMAPIngester(db)

    try:
        result = ingester.sync_folder(folder=folder, days_back=days)
        return IngestionResult(
            success=True,
            message=f"IMAP folder '{folder}' synced",
            records_processed=result["processed"],
            records_created=result["created"],
            records_updated=result["updated"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        return IngestionResult(
            success=False,
            message=str(e),
            errors=[str(e)]
        )


@router.post("/recompute-all")
async def recompute_all(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """
    Trigger full recomputation of all derived data:
    - Re-link interactions to people
    - Recompute all scores
    - Update review queue
    """
    from app.ingestion.linker import PersonLinker
    from app.scoring.engine import ScoreEngine

    def run_recompute():
        from app.core.database import SessionLocal
        db_session = SessionLocal()
        try:
            # Re-link all interactions
            linker = PersonLinker(db_session)
            linker.relink_all()

            # Recompute scores
            engine = ScoreEngine(db_session)
            engine.recompute_all_scores()
        finally:
            db_session.close()

    background_tasks.add_task(run_recompute)

    return {"message": "Recomputation started in background"}
