"""Database connection and session management."""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import settings

# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Check connection health
    pool_size=5,
    max_overflow=10,
    echo=settings.debug,
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables (development only)."""
    from app.models import Base
    Base.metadata.create_all(bind=engine)
