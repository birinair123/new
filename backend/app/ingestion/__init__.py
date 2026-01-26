"""Data ingestion modules."""
from .linkedin import LinkedInIngester
from .calendar import CalendarIngester
from .email import EmailIngester
from .imap import IMAPIngester
from .linker import PersonLinker

__all__ = [
    "LinkedInIngester",
    "CalendarIngester",
    "EmailIngester",
    "IMAPIngester",
    "PersonLinker",
]
