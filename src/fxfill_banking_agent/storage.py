"""Storage abstraction — supports SQLite (dev) and PostgreSQL/Redis (prod).

This module defines storage interfaces so that the application code
doesn't depend on a specific backend. SQLite is the default for local
development; PostgreSQL and Redis are production targets (P1-07).

Key concerns:
- Connection pooling and lifecycle
- Concurrent access (optimistic locking, idempotency)
- Migration management (Alembic-compatible)
- Outbox pattern for reliable event delivery (P2)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class StorageBackend(str, Enum):
    """Supported storage backends."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    REDIS = "redis"


@dataclass(frozen=True)
class StorageConfig:
    """Configuration for a storage backend.

    Attributes:
        backend: Which backend to use.
        url: Connection URL or path.
        pool_size: Connection pool size (PostgreSQL only).
        pool_timeout_seconds: Max wait for a connection.
        echo: Log all SQL statements (development only).
    """

    backend: StorageBackend = StorageBackend.SQLITE
    url: str = "sqlite:///./data/agent.db"
    pool_size: int = 5
    pool_timeout_seconds: int = 30
    echo: bool = False


class HealthCheckable(Protocol):
    """Protocol for storage backends that support health checks."""

    async def health(self) -> bool:
        """Return True if the backend is healthy."""
        ...


class MigrationManager(Protocol):
    """Protocol for schema migration managers."""

    async def upgrade(self, target: str = "head") -> None:
        """Run forward migrations to the target revision."""
        ...

    async def downgrade(self, target: str) -> None:
        """Roll back migrations to the target revision."""
        ...

    async def current(self) -> str:
        """Return the current migration revision."""
        ...


# ── In-memory storage for development ─────────────────────────────────


class InMemoryKVStore:
    """Simple in-memory key-value store for development and testing.

    Mimics Redis-like get/set/delete with optional TTL.
    Not suitable for production — no persistence, no distribution.
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int = 0) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def health(self) -> bool:
        return True
