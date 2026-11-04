"""Health API endpoints."""
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    time: str


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint for liveness and warm-up."""
    return HealthResponse(
        status="ok",
        version=request.app.version,
        time=datetime.now(timezone.utc).isoformat(),
    )