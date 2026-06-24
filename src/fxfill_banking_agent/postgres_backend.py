"""PostgreSQL backend adapter (A6).

Provides asyncpg-based connection pooling, migration support, and
health checks for production deployment.

When PostgreSQL is unavailable (local dev), SQLite is used as fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PostgresConfig:
    """PostgreSQL connection configuration.

    Attributes:
        dsn: Connection string (postgresql+asyncpg://user:pass@host:port/db).
        pool_min_size: Minimum connection pool size.
        pool_max_size: Maximum connection pool size.
        command_timeout_seconds: SQL statement timeout.
        ssl_mode: "require", "prefer", or "disable".
    """

    dsn: str = ""
    pool_min_size: int = 2
    pool_max_size: int = 10
    command_timeout_seconds: int = 30
    ssl_mode: str = "prefer"


class PostgresBackend:
    """PostgreSQL backend for durable storage.

    Wraps asyncpg connection pool with migration support and health checks.

    NOTE: This is a scaffold. For full production, integrate Alembic
    migrations and connection pooling via SQLAlchemy async.
    """

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config
        self._pool: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establish connection pool. No-op if asyncpg unavailable or no DSN."""
        if not self._config.dsn or self._connected:
            return
        try:
            import asyncpg  # type: ignore[import-not-found,import-untyped]

            self._pool = await asyncpg.create_pool(
                dsn=self._config.dsn,
                min_size=self._config.pool_min_size,
                max_size=self._config.pool_max_size,
                command_timeout=self._config.command_timeout_seconds,
            )
            self._connected = True
        except ImportError:
            # asyncpg not installed — stay on SQLite
            pass
        except Exception:
            self._connected = False
            raise

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._connected = False

    async def health(self) -> bool:
        """Check database connectivity."""
        if not self._pool or not self._connected:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def execute(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Execute a query and return rows as dicts."""
        if not self._pool:
            raise RuntimeError("PostgreSQL backend not connected")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]
