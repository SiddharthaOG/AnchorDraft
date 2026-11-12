"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.reviews import router as reviews_router
from app.api.imports import router as imports_router
from app.api.kits import router as kits_router
from app.api.guideline_analytics import router as guideline_analytics_router
from app.api.middleware import RequestIdMiddleware
from app.core.config import get_settings
from app.core.errors import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    map_db_exception,
)
from app.store.db import get_db_pool, close_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: initialize database pool
    await get_db_pool()
    yield
    # Shutdown: close database pool
    await close_db_pool()


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
        allow_origins=settings.ALLOWED_ORIGINS_LIST,
        # Allow only this project's Vercel Preview deployment hostnames.
        # Preview deployments use both branch aliases and immutable deployment URLs.
        allow_origin_regex=r"^https://anchordraft(?:-[a-z0-9-]+)?-siddharthaog\.vercel\.app$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-Request-Id", "Authorization", "Content-Type"],
        expose_headers=["X-Request-Id"],
    )

    # X-Request-Id middleware
    from app.api.middleware import RequestIdMiddleware
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Include routers
    app.include_router(health_router, prefix="/v1")
    app.include_router(reviews_router, prefix="/v1")
    app.include_router(imports_router, prefix="/v1")
    app.include_router(kits_router, prefix="/v1")
    app.include_router(guideline_analytics_router, prefix="/v1")

    return app


app = create_app()