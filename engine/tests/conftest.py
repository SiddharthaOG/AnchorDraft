"""Test configuration and fixtures."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest.fixture
async def app():
    """Create application for testing."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac