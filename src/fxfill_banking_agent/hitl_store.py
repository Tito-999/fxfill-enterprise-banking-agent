"""Durable HITL (human-in-the-loop) session repository.

Replaces the in-memory ``_paused_sessions`` dict with a persistent
SQLite-backed store that survives process restarts.
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


class HITLSessionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RESUMED = "RESUMED"
    FAILED = "FAILED"


@dataclass
class HITLSession:
    session_id: str
    user_id: str
    thread_id: str
    status: HITLSessionStatus
    tool_name: str
    tool_args: dict[str, object]
    authorization_decision: str | None
    approval_requirement: str | None
    idempotency_key: str | None
    version: int
    created_at: str
    updated_at: str
    expires_at: str | None

    def is_terminal(self) -> bool:
        return self.status in (
            HITLSessionStatus.APPROVED,
            HITLSessionStatus.REJECTED,
            HITLSessionStatus.EXPIRED,
            HITLSessionStatus.FAILED,
        )

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > datetime.fromisoformat(self.expires_at)


class HITLSessionStore(Protocol):
    async def insert(self, session: HITLSession) -> None: ...
    async def get(self, session_id: str) -> HITLSession | None: ...
    async def update_status(
        self, session_id: str, status: HITLSessionStatus, *, expected_version: int
    ) -> bool: ...
    async def list_pending(self, user_id: str | None = None) -> list[HITLSession]: ...


class SqliteHITLStore:
    """SQLite-backed HITL session repository with optimistic concurrency."""

    def __init__(self, db_path: str | Path, *, expiry_minutes: int = 30) -> None:
        self._db_path = Path(db_path)
        self._expiry_minutes = expiry_minutes
        self._conn: aiosqlite.Connection | None = None

    async def _ensure_connected(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await init_database(self._db_path, schema_version=CURRENT_SCHEMA_VERSION)
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def insert(self, session: HITLSession) -> None:
        conn = await self._ensure_connected()
        await conn.execute(
            "INSERT INTO hitl_sessions "
            "(session_id, user_id, thread_id, status, tool_name, tool_args, "
            " authorization_decision, approval_requirement, idempotency_key, "
            " version, created_at, updated_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session.session_id,
                session.user_id,
                session.thread_id,
                session.status.value,
                session.tool_name,
                json.dumps(session.tool_args),
                session.authorization_decision,
                session.approval_requirement,
                session.idempotency_key,
                session.version,
                session.created_at,
                session.updated_at,
                session.expires_at,
            ),
        )
        await conn.commit()
        logger.info(
            "hitl_session_inserted", session_id=session.session_id, status=session.status.value
        )

    async def get(self, session_id: str) -> HITLSession | None:
        conn = await self._ensure_connected()
        cursor = await conn.execute("SELECT * FROM hitl_sessions WHERE session_id=?", (session_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_hitl_session(row)

    async def update_status(
        self, session_id: str, status: HITLSessionStatus, *, expected_version: int
    ) -> bool:
        """Atomically update session status with optimistic locking.

        Returns:
            True if the update succeeded, False if the version mismatch
            indicates a concurrent modification.
        """
        conn = await self._ensure_connected()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "UPDATE hitl_sessions SET status=?, updated_at=?, version=version+1 "
            "WHERE session_id=? AND version=?",
            (status.value, now, session_id, expected_version),
        )
        await conn.commit()
        success = cursor.rowcount == 1
        if success:
            logger.info("hitl_session_updated", session_id=session_id, new_status=status.value)
        return success

    async def list_pending(self, user_id: str | None = None) -> list[HITLSession]:
        conn = await self._ensure_connected()
        if user_id:
            cursor = await conn.execute(
                "SELECT * FROM hitl_sessions WHERE status='PENDING' AND user_id=?",
                (user_id,),
            )
        else:
            cursor = await conn.execute("SELECT * FROM hitl_sessions WHERE status='PENDING'")
        rows = await cursor.fetchall()
        return [_row_to_hitl_session(r) for r in rows]

    async def expire_stale_sessions(self) -> int:
        """Mark expired PENDING sessions as EXPIRED. Returns count updated."""
        conn = await self._ensure_connected()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "UPDATE hitl_sessions SET status='EXPIRED', updated_at=? "
            "WHERE status='PENDING' AND expires_at IS NOT NULL AND expires_at < ?",
            (now, now),
        )
        await conn.commit()
        return cursor.rowcount


def _row_to_hitl_session(row: aiosqlite.Row) -> HITLSession:
    return HITLSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        thread_id=row["thread_id"],
        status=HITLSessionStatus(row["status"]),
        tool_name=row["tool_name"],
        tool_args=json.loads(row["tool_args"]),
        authorization_decision=row["authorization_decision"],
        approval_requirement=row["approval_requirement"],
        idempotency_key=row["idempotency_key"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )
