"""Test configuration and fixtures."""
import os
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.core.config import clear_settings_cache


@pytest.fixture
async def app():
    """Create application for testing."""
    # Set ALLOWED_ORIGINS for CORS tests (pydantic expects JSON array for list types)
    os.environ["ALLOWED_ORIGINS"] = '["http://localhost:5173","http://localhost:3000"]'
    # Clear settings cache to pick up new environment variable
    clear_settings_cache()
    return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac