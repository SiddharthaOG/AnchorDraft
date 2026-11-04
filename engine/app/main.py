"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.middleware import RequestIdMiddleware
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="AnchorDraft Review Engine",
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # CORS middleware - no wildcard, origins from ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-Request-Id", "Authorization", "Content-Type"],
        expose_headers=["X-Request-Id"],
    )

    # X-Request-Id middleware
    app.add_middleware(RequestIdMiddleware)

    # Include routers
    app.include_router(health_router, prefix="/v1")

    return app


app = create_app()