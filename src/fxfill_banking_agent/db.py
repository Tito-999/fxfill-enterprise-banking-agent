"""Shared database initialization and schema migration.

Provides idempotent schema creation with explicit version tracking.
All storage modules (checkpoint, HITL, idempotency, events) share this
initialization path.

**Connection safety:** Every exception after ``aiosqlite.connect()``
closes the connection before re-raising so the worker thread exits and
the calling process can terminate cleanly.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)

CURRENT_SCHEMA_VERSION = 2


async def init_database(
    db_path: str | Path, *, schema_version: int = CURRENT_SCHEMA_VERSION
) -> aiosqlite.Connection:
    """Initialize a database with idempotent schema creation.

    Creates the schema-version table and runs forward migrations up to
    ``schema_version``. Fails if the database has a future schema version.

    The returned connection is open and ready for use.  The caller is
    responsible for closing it.

    Args:
        db_path: Path to the SQLite database file.
        schema_version: Expected schema version.

    Returns:
        An open ``aiosqlite.Connection``.

    Raises:
        RuntimeError: If the database has a schema version higher than
            ``schema_version`` (future/incompatible).
        aiosqlite.Error: On database-level failures (corrupt file, etc.).
        OSError: On filesystem-level failures.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn: aiosqlite.Connection | None = None
    try:
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row

        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")

        # Schema version table
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY)"
        )

        cursor = await conn.execute(
            "SELECT version FROM _schema_version ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        await cursor.close()
        current = row["version"] if row else 0

        if current > schema_version:
            raise RuntimeError(
                f"Database schema version {current} is newer than expected "
                f"{schema_version}. Cannot downgrade."
            )

        if current < 1:
            await _migrate_v1(conn)
        if current < 2:
            await _migrate_v2(conn)

        if current < schema_version:
            await conn.execute(
                "INSERT OR REPLACE INTO _schema_version (version) VALUES (?)",
                (schema_version,),
            )
            await conn.commit()

        logger.info("database_initialized", path=str(db_path), version=schema_version)
        return conn

    except BaseException:
        if conn is not None:
            try:
                await conn.close()
            except BaseException:
                pass  # Best-effort close on the way out
        raise


async def _migrate_v1(conn: aiosqlite.Connection) -> None:
    """Create v1 tables: events, checkpoints, hitl_sessions, idempotency."""
    # Events table (from persistence.py)
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  run_id TEXT NOT NULL,"
        "  seq INTEGER NOT NULL,"
        "  kind TEXT NOT NULL,"
        "  payload TEXT NOT NULL,"
        "  timestamp TEXT NOT NULL,"
        "  UNIQUE(run_id, seq)"
        ")"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)")

    # Checkpoint table (LangGraph-compatible state storage)
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS checkpoints ("
        "  thread_id TEXT NOT NULL,"
        "  checkpoint_ns TEXT NOT NULL DEFAULT '',"
        "  checkpoint_id TEXT NOT NULL,"
        "  parent_checkpoint_id TEXT,"
        "  type TEXT NOT NULL,"
        "  checkpoint BLOB NOT NULL,"
        "  metadata BLOB,"
        "  created_at TEXT NOT NULL,"
        "  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)"
        ")"
    )

    # HITL sessions table
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS hitl_sessions ("
        "  session_id TEXT PRIMARY KEY,"
        "  user_id TEXT NOT NULL DEFAULT 'unknown',"
        "  thread_id TEXT NOT NULL,"
        "  status TEXT NOT NULL DEFAULT 'PENDING',"
        "  tool_name TEXT NOT NULL,"
        "  tool_args TEXT NOT NULL,"
        "  authorization_decision TEXT,"
        "  approval_requirement TEXT,"
        "  idempotency_key TEXT UNIQUE,"
        "  version INTEGER NOT NULL DEFAULT 1,"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL,"
        "  expires_at TEXT"
        ")"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_sessions(status)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_hitl_thread ON hitl_sessions(thread_id)")

    # Idempotency records
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS idempotency_records ("
        "  idempotency_key TEXT PRIMARY KEY,"
        "  status TEXT NOT NULL DEFAULT 'RESERVED',"
        "  tool_name TEXT NOT NULL,"
        "  tool_args TEXT,"
        "  result TEXT,"
        "  error TEXT,"
        "  created_at TEXT NOT NULL,"
        "  completed_at TEXT"
        ")"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_idem_status ON idempotency_records(status)")

    await conn.commit()
    logger.info("migration_v1_complete")


async def _migrate_v2(conn: aiosqlite.Connection) -> None:
    """Create v2 table: approved_operation_grants."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS approved_operation_grants ("
        "  session_id TEXT NOT NULL,"
        "  requesting_user_id TEXT NOT NULL,"
        "  approving_actor_id TEXT NOT NULL,"
        "  thread_id TEXT NOT NULL,"
        "  run_id TEXT,"
        "  checkpoint_id TEXT,"
        "  tool_call_id TEXT NOT NULL,"
        "  tool_name TEXT NOT NULL,"
        "  canonical_tool_args TEXT NOT NULL,"
        "  argument_digest TEXT NOT NULL,"
        "  idempotency_key TEXT NOT NULL,"
        "  decision TEXT NOT NULL DEFAULT 'PENDING',"
        "  status TEXT NOT NULL DEFAULT 'PENDING',"
        "  created_at TEXT NOT NULL,"
        "  approved_at TEXT,"
        "  expires_at TEXT,"
        "  consuming_at TEXT,"
        "  consumed_at TEXT,"
        "  failed_at TEXT,"
        "  version INTEGER NOT NULL DEFAULT 1"
        ")"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_grants_session ON approved_operation_grants(session_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_grants_status ON approved_operation_grants(status)"
    )
    await conn.commit()
    logger.info("migration_v2_complete")
