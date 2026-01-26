"""Authentication and authorization utilities."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from app.models import AuthSession


security = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session) -> tuple[str, AuthSession]:
    """Create a new auth session and return the raw token."""
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.auth_token_expire_hours)

    session = AuthSession(
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return token, session


def verify_password(password: str) -> bool:
    """Verify the provided password against the configured auth password."""
    return secrets.compare_digest(password, settings.auth_password)


def get_session_by_token(db: Session, token: str) -> Optional[AuthSession]:
    """Look up a session by token, checking expiry."""
    token_hash = hash_token(token)
    session = db.query(AuthSession).filter(
        AuthSession.token_hash == token_hash,
        AuthSession.expires_at > datetime.now(timezone.utc)
    ).first()
    return session


def invalidate_session(db: Session, token: str) -> bool:
    """Invalidate (delete) a session."""
    token_hash = hash_token(token)
    result = db.query(AuthSession).filter(
        AuthSession.token_hash == token_hash
    ).delete()
    db.commit()
    return result > 0


def cleanup_expired_sessions(db: Session) -> int:
    """Remove expired sessions."""
    result = db.query(AuthSession).filter(
        AuthSession.expires_at <= datetime.now(timezone.utc)
    ).delete()
    db.commit()
    return result


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> bool:
    """
    Dependency to verify authentication.
    Returns True if authenticated, raises HTTPException otherwise.
    """
    # Check for token in Authorization header
    token = None
    if credentials:
        token = credentials.credentials

    # Also check for token in cookie (for browser sessions)
    if not token:
        token = request.cookies.get("auth_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = get_session_by_token(db, token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True


# Optional auth dependency (for endpoints that work with or without auth)
async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> bool:
    """Optional authentication - returns False if not authenticated."""
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return False
