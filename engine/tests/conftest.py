"""Shared test configuration and fixtures."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from typing import Any, AsyncIterator, Optional
from contextlib import asynccontextmanager


class AsyncContextManagerMock:
    """A mock that properly implements the async context manager protocol."""

    def __init__(self, return_value: Any = None):
        self._return_value = return_value
        self._entered = False

    async def __aenter__(self):
        self._entered = True
        return self._return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._entered = False
        return False


def make_async_connection_mock(fetchval_return: any = None, execute_side_effect=None, fetchrow_return=None, fetch_return=None):
    """Create a mock connection with proper async methods."""
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.execute = AsyncMock(side_effect=execute_side_effect)
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    return conn


@asynccontextmanager
async def mock_acquire_context(conn: Optional[MagicMock] = None) -> AsyncIterator[MagicMock]:
    """Context manager that yields a mock connection."""
    if conn is None:
        conn = MagicMock()
        conn.fetchval = AsyncMock()
        conn.execute = AsyncMock()
        conn.fetchrow = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
    yield conn


def make_pool_mock(acquire_return_value=None):
    """Create a mock pool with proper async context manager support."""
    pool = MagicMock()

    if acquire_return_value is None:
        acquire_return_value = MagicMock()
        acquire_return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        acquire_return_value.__aexit__ = AsyncMock(return_value=False)

    pool.acquire = MagicMock(return_value=acquire_return_value)
    return pool


@pytest.fixture
def mock_db_pool():
    """Create a properly mocked database pool."""
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchval = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    # The acquire() method returns an async context manager
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=MagicMock(
        fetchval=AsyncMock(),
        execute=AsyncMock(),
        fetchrow=AsyncMock(),
        fetch=AsyncMock(return_value=[])
    ))
    async_cm.__aexit__ = AsyncMock(return_value=False)

    pool.pool = MagicMock()
    pool.pool.acquire = MagicMock(return_value=async_cm)

    pool.connect = AsyncMock()
    pool.disconnect = AsyncMock()
    return pool


@pytest.fixture
def mock_conn():
    """Create a mock connection with all necessary async methods."""
    conn = MagicMock()
    conn.fetchval = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    """Create a mock pool that returns the mock connection."""
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    pool.pool = MagicMock()
    pool.pool.acquire = MagicMock(return_value=MagicMock(
        __aenter__=AsyncMock(return_value=mock_conn),
        __aexit__=AsyncMock(return_value=False)
    ))
    return pool