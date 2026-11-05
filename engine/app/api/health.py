"""Health API endpoints."""
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.store.db import get_db_pool


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    time: str
    database: bool | None = None


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    deep: bool = Query(False, description="Perform deep health check including database connectivity"),
) -> HealthResponse:
    """Health check endpoint for liveness and warm-up.

    With ?deep=1, also checks database connectivity.
    """
    db_healthy = None
    if deep:
        try:
            pool = await get_db_pool()
            async with pool.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            db_healthy = True
        except Exception:
            db_healthy = False

    return HealthResponse(
        status="ok",
        version=request.app.version,
        time=datetime.now(timezone.utc).isoformat(),
        database=db_healthy,
    )