"""Event persistence for the banking agent.

Stores conversation events (messages, tool calls, tool results) in a
SQLite database so that agent runs are queryable and survive restarts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

import aiosqlite

from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class EventKind(str, Enum):
    """Kind of agent event."""

    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    CHECKPOINT = "checkpoint"


@dataclass(frozen=True)
class AgentEvent:
    """A single event in an agent run.

    Attributes:
        run_id: Unique identifier for the agent run.
        seq: Monotonic sequence number within the run.
        kind: Event kind.
        payload: JSON-serializable event data.
        timestamp: UTC timestamp when the event was recorded.
    """

    run_id: str
    seq: int
    kind: EventKind
    payload: dict[str, object]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class EventStore(Protocol):
    """Protocol for persisting and querying agent events."""

    async def insert(self, event: AgentEvent) -> None:
        """Persist a single event."""
        ...

    async def query_run(self, run_id: str) -> list[AgentEvent]:
        """Return all events for a run, ordered by sequence number."""
        ...

    async def query(
        self,
        run_id: str | None = None,
        kind: EventKind | None = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """Query events with optional filters."""
        ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------


class SqliteEventStore:
    """SQLite-backed event store using aiosqlite."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        UNIQUE(run_id, seq)
    );
    CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
    CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
    """

    def __init__(self, db_path: str | Path = "data/agent.db") -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database and create tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(self.SCHEMA)
        await self._conn.commit()
        logger.info("sqlite_event_store_connected", path=str(self._db_path))

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def insert(self, event: AgentEvent) -> None:
        """Persist a single event."""
        if not self._conn:
            raise RuntimeError("SqliteEventStore not connected")
        await self._conn.execute(
            "INSERT INTO events (run_id, seq, kind, payload, timestamp) VALUES (?, ?, ?, ?, ?)",
            (event.run_id, event.seq, event.kind.value, json.dumps(event.payload), event.timestamp),
        )
        await self._conn.commit()

    async def query_run(self, run_id: str) -> list[AgentEvent]:
        """Return all events for a run."""
        if not self._conn:
            raise RuntimeError("SqliteEventStore not connected")
        cursor = await self._conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def query(
        self,
        run_id: str | None = None,
        kind: EventKind | None = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """Query events with optional filters."""
        if not self._conn:
            raise RuntimeError("SqliteEventStore not connected")

        conditions: list[str] = []
        params: list[object] = []
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if kind:
            conditions.append("kind = ?")
            params.append(kind.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self._conn.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: aiosqlite.Row) -> AgentEvent:
        return AgentEvent(
            run_id=row["run_id"],
            seq=row["seq"],
            kind=EventKind(row["kind"]),
            payload=json.loads(row["payload"]),
            timestamp=row["timestamp"],
        )
