"""Durable SQLite-backed checkpoint saver for LangGraph.

Replaces the in-memory MemorySaver with persistent storage so agent
state survives process restarts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from fxfill_banking_agent.db import CURRENT_SCHEMA_VERSION, init_database
from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)


class SqliteCheckpointSaver(BaseCheckpointSaver):  # type: ignore[type-arg]
    """SQLite-backed LangGraph checkpoint saver.

    Uses LangGraph's ``JsonPlusSerializer`` to correctly serialize
    LangChain message objects that are not natively JSON-serializable.

    Args:
        db_path: Path to the SQLite database file. Created if it does
            not exist.
    """

    def __init__(self, db_path: str | Path) -> None:
        super().__init__(serde=JsonPlusSerializer())
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

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:  # type: ignore[override]
        conn = await self._ensure_connected()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        if checkpoint_id:
            cursor = await conn.execute(
                "SELECT * FROM checkpoints WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
                (thread_id, checkpoint_ns, checkpoint_id),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM checkpoints WHERE thread_id=? AND checkpoint_ns=? ORDER BY created_at DESC LIMIT 1",
                (thread_id, checkpoint_ns),
            )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_tuple(row)

    async def alist(  # type: ignore[override]
        self,
        config: dict[str, Any] | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        # Simple implementation: return most recent
        if config:
            tup = await self.aget_tuple(config)
            if tup:
                yield tup

    async def aput(  # type: ignore[override]
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, str],
    ) -> dict[str, Any]:
        import base64
        import json as _json
        from datetime import datetime, timezone

        conn = await self._ensure_connected()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = checkpoint.get("parent_checkpoint_id")

        # JsonPlusSerializer.dumps_typed returns (type_str, bytes).
        # We encode bytes as base64 for safe SQLite storage.
        ck_typed = self.serde.dumps_typed(checkpoint)
        md_typed = self.serde.dumps_typed(metadata)

        serialized_checkpoint = _json.dumps(
            [ck_typed[0], base64.b64encode(ck_typed[1]).decode("ascii")]
        )
        serialized_metadata = _json.dumps(
            [md_typed[0], base64.b64encode(md_typed[1]).decode("ascii")]
        )

        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "INSERT OR REPLACE INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                parent_checkpoint_id,
                "checkpoint",
                serialized_checkpoint,
                serialized_metadata,
                now,
            ),
        )
        await conn.commit()
        return config

    async def aput_writes(  # type: ignore[override]
        self,
        config: dict[str, Any],
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store intermediate writes linked to a checkpoint.

        These are channel-level updates produced during graph execution.
        """
        import base64
        import json as _json
        from datetime import datetime, timezone

        conn = await self._ensure_connected()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id", "")
        now = datetime.now(timezone.utc).isoformat()

        for idx, (channel, value) in enumerate(writes):
            typed = self.serde.dumps_typed(value)
            serialized = _json.dumps([typed[0], base64.b64encode(typed[1]).decode("ascii")])
            await conn.execute(
                "INSERT OR REPLACE INTO channel_writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, idx, channel, value, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    task_path,
                    idx,
                    channel,
                    serialized,
                    now,
                ),
            )
        await conn.commit()

    async def adelete_thread(self, thread_id: str) -> None:
        conn = await self._ensure_connected()
        await conn.execute("DELETE FROM channel_writes WHERE thread_id=?", (thread_id,))
        await conn.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
        await conn.commit()


def _row_to_tuple(row: aiosqlite.Row) -> CheckpointTuple:
    import base64
    import json as _json

    serde = JsonPlusSerializer()

    # The checkpoint/metadata are stored as JSON-encoded [type_str, base64_data]
    # from JsonPlusSerializer.dumps_typed().
    def _decode(raw: str | bytes) -> Any:
        if isinstance(raw, str):
            parts = _json.loads(raw)
            # parts is [type_str, base64_encoded_bytes]
            return serde.loads_typed((str(parts[0]), base64.b64decode(parts[1])))
        # Legacy path: raw bytes from BLOB column (pre-v6 databases)
        return serde.loads_typed(("json", raw))

    checkpoint = _decode(row["checkpoint"])
    metadata_raw: Any = _decode(row["metadata"]) if row["metadata"] else {}

    return CheckpointTuple(
        config={
            "configurable": {
                "thread_id": row["thread_id"],
                "checkpoint_ns": row["checkpoint_ns"],
                "checkpoint_id": row["checkpoint_id"],
            }
        },
        checkpoint=checkpoint,
        metadata=metadata_raw,
        parent_config=(
            {
                "configurable": {
                    "thread_id": row["thread_id"],
                    "checkpoint_id": row["parent_checkpoint_id"],
                }
            }
            if row["parent_checkpoint_id"]
            else None
        ),
    )
