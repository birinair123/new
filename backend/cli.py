#!/usr/bin/env python3
"""
CLI commands for LinkedIn CRM data management.

Usage:
    python cli.py ingest_linkedin [csv_path]
    python cli.py ingest_ost_calendar
    python cli.py ingest_ost_emails
    python cli.py ingest_imap [folder] [--days N]
    python cli.py recompute_scores [--person_id ID]
    python cli.py refresh_review_queue
    python cli.py init_db
"""
import argparse
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))


def get_db():
    """Get database session."""
    from app.core.database import SessionLocal
    return SessionLocal()


def cmd_init_db(args):
    """Initialize the database schema."""
    from app.core.database import engine
    from app.models import Base

    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Done!")


def cmd_ingest_linkedin(args):
    """Ingest LinkedIn connections from CSV."""
    from app.ingestion.linkedin import LinkedInIngester
    from app.core.config import settings

    db = get_db()
    ingester = LinkedInIngester(db)

    if args.csv_path:
        csv_path = Path(args.csv_path)
    else:
        # Find most recent CSV in linkedin_csv_dir
        csv_files = sorted(
            settings.linkedin_csv_dir.glob("*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not csv_files:
            print(f"No CSV files found in {settings.linkedin_csv_dir}")
            sys.exit(1)
        csv_path = csv_files[0]

    print(f"Ingesting LinkedIn CSV: {csv_path}")
    result = ingester.ingest_csv(csv_path)

    print(f"Processed: {result['processed']}")
    print(f"Created: {result['created']}")
    print(f"Updated: {result['updated']}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"  - {err}")

    db.close()


def cmd_ingest_ost_calendar(args):
    """Ingest calendar data from OST export JSONL."""
    from app.ingestion.calendar import CalendarIngester
    from app.core.config import settings

    db = get_db()
    ingester = CalendarIngester(db)

    events_path = settings.ost_export_dir / "events.jsonl"
    series_path = settings.ost_export_dir / "series.jsonl"

    print(f"Looking for JSONL files in: {settings.ost_export_dir}")

    if not events_path.exists() and not series_path.exists():
        print("No calendar JSONL files found!")
        sys.exit(1)

    result = ingester.ingest_jsonl(
        events_path=events_path if events_path.exists() else None,
        series_path=series_path if series_path.exists() else None
    )

    print(f"Series created: {result.get('series_created', 0)}")
    print(f"Events processed: {result['processed']}")
    print(f"Events created: {result['created']}")
    print(f"Events updated: {result['updated']}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"  - {err}")

    db.close()


def cmd_ingest_ost_emails(args):
    """Ingest email metadata from OST export JSONL."""
    from app.ingestion.email import EmailIngester
    from app.core.config import settings

    db = get_db()
    ingester = EmailIngester(db)

    emails_path = settings.ost_export_dir / "emails.jsonl"

    print(f"Looking for emails.jsonl in: {settings.ost_export_dir}")

    if not emails_path.exists():
        print("No emails.jsonl found!")
        sys.exit(1)

    result = ingester.ingest_jsonl(emails_path)

    print(f"Processed: {result['processed']}")
    print(f"Created: {result['created']}")
    print(f"Updated: {result['updated']}")
    print(f"Skipped (automated): {result.get('skipped_automated', 0)}")
    print(f"Skipped (bulk): {result.get('skipped_bulk', 0)}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"  - {err}")

    db.close()


def cmd_ingest_imap(args):
    """Sync email metadata from IMAP server."""
    from app.ingestion.imap import IMAPIngester
    from app.core.config import settings

    if not settings.imap_server:
        print("IMAP not configured. Set IMAP_SERVER, IMAP_USERNAME, IMAP_PASSWORD.")
        sys.exit(1)

    db = get_db()
    ingester = IMAPIngester(db)

    folder = args.folder or "INBOX"
    days = args.days or 30

    print(f"Syncing IMAP folder: {folder} (last {days} days)")
    result = ingester.sync_folder(folder=folder, days_back=days)

    print(f"Processed: {result['processed']}")
    print(f"Created: {result['created']}")
    print(f"Updated: {result['updated']}")
    print(f"Skipped: {result.get('skipped', 0)}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"  - {err}")

    db.close()


def cmd_recompute_scores(args):
    """Recompute connection strength scores."""
    from app.scoring.engine import ScoreEngine
    from app.models import Person

    db = get_db()
    engine = ScoreEngine(db)

    if args.person_id:
        print(f"Recomputing score for person: {args.person_id}")
        score = engine.compute_score(args.person_id)
        print(f"Score: {score.score_total}")
        print(f"Breakdown: {score.score_breakdown}")
    else:
        print("Recomputing scores for all tracked people...")
        result = engine.recompute_all_scores()
        print(f"Updated: {result['updated']}")
        print(f"Errors: {result['errors']}")

    db.close()


def cmd_refresh_review_queue(args):
    """Refresh the review queue with candidates."""
    from app.ingestion.linker import PersonLinker

    db = get_db()
    linker = PersonLinker(db)

    print("Refreshing review queue...")
    result = linker.refresh_review_queue()

    print(f"Promote candidates added: {result['promote_candidates']}")
    print(f"Link suggestions added: {result['link_suggestions']}")

    db.close()


def main():
    parser = argparse.ArgumentParser(description="LinkedIn CRM CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init_db
    subparsers.add_parser("init_db", help="Initialize database schema")

    # ingest_linkedin
    p = subparsers.add_parser("ingest_linkedin", help="Ingest LinkedIn CSV")
    p.add_argument("csv_path", nargs="?", help="Path to LinkedIn CSV file")

    # ingest_ost_calendar
    subparsers.add_parser("ingest_ost_calendar", help="Ingest OST calendar JSONL")

    # ingest_ost_emails
    subparsers.add_parser("ingest_ost_emails", help="Ingest OST emails JSONL")

    # ingest_imap
    p = subparsers.add_parser("ingest_imap", help="Sync IMAP mailbox")
    p.add_argument("folder", nargs="?", default="INBOX", help="IMAP folder name")
    p.add_argument("--days", type=int, default=30, help="Days to sync")

    # recompute_scores
    p = subparsers.add_parser("recompute_scores", help="Recompute connection scores")
    p.add_argument("--person_id", help="Specific person ID (or all if not specified)")

    # refresh_review_queue
    subparsers.add_parser("refresh_review_queue", help="Refresh review queue")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init_db": cmd_init_db,
        "ingest_linkedin": cmd_ingest_linkedin,
        "ingest_ost_calendar": cmd_ingest_ost_calendar,
        "ingest_ost_emails": cmd_ingest_ost_emails,
        "ingest_imap": cmd_ingest_imap,
        "recompute_scores": cmd_recompute_scores,
        "refresh_review_queue": cmd_refresh_review_queue,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
