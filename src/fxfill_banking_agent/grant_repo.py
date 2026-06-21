"""Durable approved-operation grant repository with atomic consumption."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from fxfill_banking_agent.db import CURRENT_SCHEMA_VERSION, init_database
from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GrantRecord:
    session_id: str
    requesting_user_id: str
    approving_actor_id: str
    thread_id: str
    run_id: str | None
    checkpoint_id: str | None
    tool_call_id: str
    tool_name: str
    canonical_tool_args: str
    argument_digest: str
    idempotency_key: str
    decision: str
    status: str
    created_at: str
    approved_at: str | None
    expires_at: str | None
    consuming_at: str | None
    consumed_at: str | None
    failed_at: str | None
    version: int = 1


def _digest(tool_args: dict) -> str:
    return hashlib.sha256(json.dumps(tool_args, sort_keys=True).encode()).hexdigest()


class GrantRepository:
    """Durable repository for approved-operation grants.

    Atomic consumption uses a conditional UPDATE that transitions
    APPROVED → CONSUMING in a single statement. Only one caller succeeds.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await init_database(self._db_path, schema_version=CURRENT_SCHEMA_VERSION)
        return self._conn

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def insert_pending(self, grant: GrantRecord) -> None:
        conn = await self._ensure_db()
        await conn.execute(
            "INSERT INTO approved_operation_grants "
            "(session_id, requesting_user_id, approving_actor_id, thread_id, run_id, "
            " checkpoint_id, tool_call_id, tool_name, canonical_tool_args, argument_digest, "
            " idempotency_key, decision, status, created_at, expires_at, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, 1)",
            (
                grant.session_id,
                grant.requesting_user_id,
                grant.approving_actor_id,
                grant.thread_id,
                grant.run_id,
                grant.checkpoint_id,
                grant.tool_call_id,
                grant.tool_name,
                grant.canonical_tool_args,
                grant.argument_digest,
                grant.idempotency_key,
                grant.decision,
                grant.created_at,
                grant.expires_at,
            ),
        )
        await conn.commit()
        logger.info("grant_inserted", session=grant.session_id, tool=grant.tool_name)

    async def atomic_consume(
        self,
        *,
        session_id: str,
        user_id: str,
        approving_actor_id: str = "",
        thread_id: str,
        run_id: str = "",
        checkpoint_id: str = "",
        tool_call_id: str,
        tool_name: str,
        tool_args: dict,
        idempotency_key: str,
        version: int,
    ) -> GrantRecord | None:
        """Atomically transition APPROVED→CONSUMING.

        Returns the grant if the transition succeeded, None if already consumed
        or conditions don't match.
        """
        conn = await self._ensure_db()
        digest = _digest(tool_args)
        now = datetime.now(timezone.utc).isoformat()

        cursor = await conn.execute(
            "UPDATE approved_operation_grants SET status='CONSUMING', consuming_at=? "
            "WHERE session_id=? AND status='APPROVED' AND version=? "
            "AND requesting_user_id=? AND thread_id=? "
            "AND (approving_actor_id=? OR approving_actor_id='' OR ?='') "
            "AND (run_id=? OR run_id IS NULL OR ?='') "
            "AND (checkpoint_id=? OR checkpoint_id IS NULL OR ?='') "
            "AND tool_call_id=? AND tool_name=? AND argument_digest=? "
            "AND idempotency_key=? AND (expires_at IS NULL OR expires_at > ?)",
            (
                now,
                session_id,
                version,
                user_id,
                thread_id,
                approving_actor_id,
                approving_actor_id,
                run_id,
                run_id,
                checkpoint_id,
                checkpoint_id,
                tool_call_id,
                tool_name,
                digest,
                idempotency_key,
                now,
            ),
        )
        await conn.commit()

        if cursor.rowcount == 0:
            return None

        # Read back the claimed grant
        row_cursor = await conn.execute(
            "SELECT * FROM approved_operation_grants WHERE session_id=? AND status='CONSUMING'",
            (session_id,),
        )
        row = await row_cursor.fetchone()
        if row is None:
            return None
        return _row_to_grant(row)

    async def mark_consumed(self, session_id: str) -> None:
        conn = await self._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE approved_operation_grants SET status='CONSUMED', consumed_at=?"
            " WHERE session_id=? AND status='CONSUMING'",
            (now, session_id),
        )
        await conn.commit()

    async def mark_failed(self, session_id: str) -> None:
        conn = await self._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE approved_operation_grants SET status='FAILED', failed_at=?"
            " WHERE session_id=? AND status='CONSUMING'",
            (now, session_id),
        )
        await conn.commit()

    async def mark_unknown(self, session_id: str) -> None:
        conn = await self._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE approved_operation_grants SET status='UNKNOWN', failed_at=?"
            " WHERE session_id=? AND status='CONSUMING'",
            (now, session_id),
        )
        await conn.commit()

    async def approve_pending(
        self, session_id: str, approving_actor_id: str, expected_version: int
    ) -> bool:
        """Atomically transition PENDING → APPROVED."""
        conn = await self._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "UPDATE approved_operation_grants SET status='APPROVED', "
            "approving_actor_id=?, approved_at=? "
            "WHERE session_id=? AND status='PENDING' AND version=?",
            (approving_actor_id, now, session_id, expected_version),
        )
        await conn.commit()
        return cursor.rowcount == 1

    async def get_by_session(self, session_id: str) -> GrantRecord | None:
        conn = await self._ensure_db()
        cursor = await conn.execute(
            "SELECT * FROM approved_operation_grants WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_grant(row)


def _row_to_grant(row: aiosqlite.Row) -> GrantRecord:
    return GrantRecord(
        session_id=row["session_id"],
        requesting_user_id=row["requesting_user_id"],
        approving_actor_id=row["approving_actor_id"],
        thread_id=row["thread_id"],
        run_id=row["run_id"],
        checkpoint_id=row["checkpoint_id"],
        tool_call_id=row["tool_call_id"],
        tool_name=row["tool_name"],
        canonical_tool_args=row["canonical_tool_args"],
        argument_digest=row["argument_digest"],
        idempotency_key=row["idempotency_key"],
        decision=row["decision"],
        status=row["status"],
        created_at=row["created_at"],
        approved_at=row["approved_at"],
        expires_at=row["expires_at"],
        consuming_at=row["consuming_at"],
        consumed_at=row["consumed_at"],
        failed_at=row["failed_at"],
        version=row["version"],
    )
