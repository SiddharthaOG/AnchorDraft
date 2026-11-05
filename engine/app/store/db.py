"""Database connection pool for direct PostgreSQL access."""
import asyncpg
from app.core.config import get_settings


class DatabasePool:
    """Asyncpg connection pool for direct PostgreSQL access."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize the connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Execute a query and return a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute a query and return all rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a query and return the status."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def transaction(self) -> asyncpg.transaction.Transaction:
        """Get a transaction from the pool."""
        return self.pool.transaction()


# Global pool instance
_pool: DatabasePool | None = None


async def get_db_pool() -> DatabasePool:
    """Get the global database pool instance."""
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL not configured")
        _pool = DatabasePool(settings.DATABASE_URL)
        await _pool.connect()
    return _pool


async def close_db_pool() -> None:
    """Close the global database pool."""
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None