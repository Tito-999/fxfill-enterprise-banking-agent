"""Durable idempotency repository.

Ensures side-effecting operations are executed at most once, even across
process restarts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

import aiosqlite

from fxfill_banking_agent.db import CURRENT_SCHEMA_VERSION, init_database
from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)


class IdempotencyStatus(str, Enum):
    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class IdempotencyRecord:
    idempotency_key: str
    status: IdempotencyStatus
    tool_name: str
    tool_args: dict[str, object] | None
    result: str | None
    error: str | None
    created_at: str
    completed_at: str | None

    def is_terminal(self) -> bool:
        return self.status in (IdempotencyStatus.SUCCEEDED, IdempotencyStatus.FAILED)

    def can_retry(self) -> bool:
        """True if the operation can be safely retried."""
        return self.status in (
            IdempotencyStatus.RESERVED,
            IdempotencyStatus.FAILED,
        )


class IdempotencyStore(Protocol):
    async def reserve(
        self, key: str, tool_name: str, tool_args: dict[str, object] | None
    ) -> IdempotencyRecord: ...
    async def mark_executing(self, key: str) -> bool: ...
    async def mark_succeeded(self, key: str, result: str) -> bool: ...
    async def mark_failed(self, key: str, error: str) -> bool: ...
    async def mark_unknown(self, key: str) -> bool: ...
    async def get(self, key: str) -> IdempotencyRecord | None: ...


class SqliteIdempotencyStore:
    """SQLite-backed idempotency repository."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def _ensure_connected(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await init_database(self._db_path, schema_version=CURRENT_SCHEMA_VERSION)
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def reserve(
        self, key: str, tool_name: str, tool_args: dict[str, object] | None
    ) -> IdempotencyRecord:
        conn = await self._ensure_connected()
        now = datetime.now(timezone.utc).isoformat()

        # UPSERT: reserve only if not already present
        await conn.execute(
            "INSERT OR IGNORE INTO idempotency_records "
            "(idempotency_key, status, tool_name, tool_args, created_at) "
            "VALUES (?, 'RESERVED', ?, ?, ?)",
            (key, tool_name, json.dumps(tool_args or {}), now),
        )
        await conn.commit()

        cursor = await conn.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key=?", (key,)
        )
        row = await cursor.fetchone()
        return _row_to_record(row)  # type: ignore[arg-type]

    async def mark_executing(self, key: str) -> bool:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "UPDATE idempotency_records SET status='EXECUTING' "
            "WHERE idempotency_key=? AND status='RESERVED'",
            (key,),
        )
        await conn.commit()
        return cursor.rowcount == 1

    async def mark_succeeded(self, key: str, result: str) -> bool:
        conn = await self._ensure_connected()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "UPDATE idempotency_records SET status='SUCCEEDED', result=?, completed_at=? "
            "WHERE idempotency_key=? AND status='EXECUTING'",
            (result, now, key),
        )
        await conn.commit()
        return cursor.rowcount == 1

    async def mark_failed(self, key: str, error: str) -> bool:
        conn = await self._ensure_connected()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "UPDATE idempotency_records SET status='FAILED', error=?, completed_at=? "
            "WHERE idempotency_key=?",
            (error, now, key),
        )
        await conn.commit()
        return cursor.rowcount == 1

    async def mark_unknown(self, key: str) -> bool:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "UPDATE idempotency_records SET status='UNKNOWN' "
            "WHERE idempotency_key=? AND status IN ('RESERVED', 'EXECUTING')",
            (key,),
        )
        await conn.commit()
        return cursor.rowcount == 1

    async def get(self, key: str) -> IdempotencyRecord | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key=?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_record(row)


def _row_to_record(row: aiosqlite.Row) -> IdempotencyRecord:
    return IdempotencyRecord(
        idempotency_key=row["idempotency_key"],
        status=IdempotencyStatus(row["status"]),
        tool_name=row["tool_name"],
        tool_args=json.loads(row["tool_args"]) if row["tool_args"] else None,
        result=row["result"],
        error=row["error"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )
