"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.api import auth, people, interactions, scores, ingestion, review


# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"Starting {settings.app_name}...")

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.jsonl_import_dir.mkdir(parents=True, exist_ok=True)
    settings.linkedin_csv_dir.mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="LinkedIn-first personal CRM with email and calendar integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(people.router, prefix="/api/people", tags=["People"])
app.include_router(interactions.router, prefix="/api/interactions", tags=["Interactions"])
app.include_router(scores.router, prefix="/api/scores", tags=["Scores"])
app.include_router(ingestion.router, prefix="/api/ingestion", tags=["Ingestion"])
app.include_router(review.router, prefix="/api/review", tags=["Review Queue"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "app": settings.app_name}


@app.get("/")
async def root():
    """Root endpoint redirect info."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "docs": "/docs",
        "api": "/api"
    }
