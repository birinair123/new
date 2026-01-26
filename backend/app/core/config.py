"""Application configuration via environment variables."""
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_url: str = "postgresql://crm:crm@localhost:5432/linkedin_crm"

    # Authentication
    auth_password: str = "changeme"  # Override in production!
    auth_secret_key: str = "super-secret-key-change-in-production"
    auth_token_expire_hours: int = 24 * 7  # 1 week

    # IMAP settings (optional)
    imap_server: Optional[str] = None
    imap_port: int = 993
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: bool = True

    # Paths
    data_dir: Path = Path("./data")
    jsonl_import_dir: Path = Path("./data/imports")
    linkedin_csv_dir: Path = Path("./data/linkedin")

    # Shared folder for Windows VM exports
    ost_export_dir: Path = Path("/shared/crm_export")

    # Application
    app_name: str = "LinkedIn CRM"
    debug: bool = False
    api_rate_limit: int = 100  # Requests per minute

    # Scoring
    score_recency_max: int = 30
    score_frequency_max: int = 20
    score_bidirectional_max: int = 15
    score_meetings_max: int = 20
    score_context_max: int = 15

    # Privacy
    store_email_snippets: bool = True
    snippet_max_length: int = 200

    # Own email addresses (for direction detection)
    own_emails: list[str] = []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
