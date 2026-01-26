"""Authentication API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import (
    verify_password, create_session, invalidate_session, get_current_user
)


router = APIRouter()


class LoginRequest(BaseModel):
    """Login request body."""
    password: str


class LoginResponse(BaseModel):
    """Login response with token."""
    token: str
    expires_in_hours: int


class StatusResponse(BaseModel):
    """Auth status response."""
    authenticated: bool


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Login with password and get auth token.
    Token is also set as a cookie for browser sessions.
    """
    if not verify_password(request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )

    token, session = create_session(db)

    # Set cookie for browser sessions
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=60 * 60 * 24 * 7  # 1 week
    )

    from app.core.config import settings
    return LoginResponse(
        token=token,
        expires_in_hours=settings.auth_token_expire_hours
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_user)
):
    """Logout and invalidate current session."""
    # Get token from header or cookie
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("auth_token", "")

    if token:
        invalidate_session(db, token)

    # Clear cookie
    response.delete_cookie("auth_token")

    return {"message": "Logged out"}


@router.get("/status", response_model=StatusResponse)
async def auth_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check if current session is authenticated."""
    from app.core.auth import get_session_by_token

    # Check header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if get_session_by_token(db, token):
            return StatusResponse(authenticated=True)

    # Check cookie
    token = request.cookies.get("auth_token")
    if token and get_session_by_token(db, token):
        return StatusResponse(authenticated=True)

    return StatusResponse(authenticated=False)
