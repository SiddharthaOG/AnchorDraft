"""Test configuration and fixtures."""
import os
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.core.config import clear_settings_cache


@pytest.fixture
async def app():
    """Create application for testing with JSON array origins."""
    # Set ALLOWED_ORIGINS for CORS tests (pydantic expects JSON array for list types)
    os.environ["ALLOWED_ORIGINS"] = '["http://localhost:5173","http://localhost:3000"]'
    # Clear settings cache to pick up new environment variable
    clear_settings_cache()
    return create_app()


@pytest.fixture
async def app_comma_separated():
    """Create application for testing with comma-separated origins."""
    os.environ["ALLOWED_ORIGINS"] = "http://localhost:5173,http://localhost:3000"
    clear_settings_cache()
    return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_comma_separated(app_comma_separated):
    """Create test client with comma-separated origins."""
    transport = ASGITransport(app=app_comma_separated)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac