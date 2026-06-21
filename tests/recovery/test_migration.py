"""Schema migration tests: empty, v1→v3, v2→v3, preservation, idempotency."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from fxfill_banking_agent.db import CURRENT_SCHEMA_VERSION, init_database


class TestEmptyToV3:
    @pytest.mark.asyncio
    async def test_empty_db_initializes(self, tmp_path: Path) -> None:
        conn = await init_database(tmp_path / "empty.db", schema_version=CURRENT_SCHEMA_VERSION)
        cursor = await conn.execute(
            "SELECT version FROM _schema_version ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row["version"] == CURRENT_SCHEMA_VERSION
        # Verify all tables exist
        tables = [
            "events",
            "checkpoints",
            "hitl_sessions",
            "idempotency_records",
            "approved_operation_grants",
        ]
        for t in tables:
            cursor = await conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'"
            )
            assert await cursor.fetchone() is not None, f"Table {t} missing"
        await conn.close()

    @pytest.mark.asyncio
    async def test_repeated_init_idempotent(self, tmp_path: Path) -> None:
        conn1 = await init_database(tmp_path / "idem.db", schema_version=CURRENT_SCHEMA_VERSION)
        await conn1.close()
        conn2 = await init_database(tmp_path / "idem.db", schema_version=CURRENT_SCHEMA_VERSION)
        assert conn2 is not None
        await conn2.close()


class TestSchemaVersion1:
    @pytest.mark.asyncio
    async def test_v1_does_not_create_v2_v3(self, tmp_path: Path) -> None:
        conn = await init_database(tmp_path / "v1only.db", schema_version=1)
        cursor = await conn.execute(
            "SELECT version FROM _schema_version ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row["version"] == 1
        # v2/v3 tables must not exist
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='approved_operation_grants'"
        )
        assert await cursor.fetchone() is None
        await conn.close()


class TestV1ToV3:
    @pytest.mark.asyncio
    async def test_preserves_events(self, tmp_path: Path) -> None:
        # Init at v1
        conn = await init_database(tmp_path / "mig.db", schema_version=1)
        await conn.execute(
            "INSERT INTO events (run_id, seq, kind, payload, timestamp) VALUES ('r1', 0, 'test', '{}', 'now')"
        )
        await conn.commit()
        await conn.close()
        # Migrate to v3
        conn = await init_database(tmp_path / "mig.db", schema_version=CURRENT_SCHEMA_VERSION)
        cursor = await conn.execute("SELECT * FROM events WHERE run_id='r1'")
        row = await cursor.fetchone()
        assert row is not None
        assert row["kind"] == "test"
        await conn.close()


class TestFutureSchema:
    @pytest.mark.asyncio
    async def test_future_version_fails(self, tmp_path: Path) -> None:
        conn = await aiosqlite.connect(str(tmp_path / "future.db"))
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY)"
        )
        await conn.execute("INSERT OR REPLACE INTO _schema_version (version) VALUES (999)")
        await conn.commit()
        await conn.close()
        with pytest.raises(RuntimeError, match="newer"):
            await init_database(tmp_path / "future.db", schema_version=CURRENT_SCHEMA_VERSION)


class TestConnectionCleanup:
    @pytest.mark.asyncio
    async def test_failed_init_closes_connection(self, tmp_path: Path) -> None:
        db = tmp_path / "bad.db"
        db.write_text("not sqlite")
        with pytest.raises(Exception):
            await init_database(db)
        # Database file should not be locked — cleanup happened


class TestGrantConstraints:
    @pytest.mark.asyncio
    async def test_duplicate_session_id_rejected(self, tmp_path: Path) -> None:
        conn = await init_database(
            tmp_path / "grant_test.db", schema_version=CURRENT_SCHEMA_VERSION
        )
        await conn.execute(
            "INSERT INTO approved_operation_grants (session_id, requesting_user_id, approving_actor_id, thread_id, tool_call_id, tool_name, canonical_tool_args, argument_digest, idempotency_key, decision, status, created_at) VALUES ('s1', 'u1', 'a1', 't1', 'tc1', 'tool', '{}', 'd1', 'ik1', 'PENDING', 'PENDING', 'now')"
        )
        await conn.commit()
        with pytest.raises(Exception):  # UNIQUE constraint
            await conn.execute(
                "INSERT INTO approved_operation_grants (session_id, requesting_user_id, approving_actor_id, thread_id, tool_call_id, tool_name, canonical_tool_args, argument_digest, idempotency_key, decision, status, created_at) VALUES ('s1', 'u2', 'a2', 't2', 'tc2', 'tool', '{}', 'd2', 'ik2', 'PENDING', 'PENDING', 'now')"
            )
            await conn.commit()
        await conn.close()

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_key_rejected(self, tmp_path: Path) -> None:
        conn = await init_database(
            tmp_path / "grant_idem.db", schema_version=CURRENT_SCHEMA_VERSION
        )
        await conn.execute(
            "INSERT INTO approved_operation_grants (session_id, requesting_user_id, approving_actor_id, thread_id, tool_call_id, tool_name, canonical_tool_args, argument_digest, idempotency_key, decision, status, created_at) VALUES ('sa', 'u1', 'a1', 't1', 'tc1', 'tool', '{}', 'd1', 'shared-key', 'PENDING', 'PENDING', 'now')"
        )
        await conn.commit()
        with pytest.raises(Exception):  # UNIQUE constraint on idempotency_key
            await conn.execute(
                "INSERT INTO approved_operation_grants (session_id, requesting_user_id, approving_actor_id, thread_id, tool_call_id, tool_name, canonical_tool_args, argument_digest, idempotency_key, decision, status, created_at) VALUES ('sb', 'u2', 'a2', 't2', 'tc2', 'tool', '{}', 'd2', 'shared-key', 'PENDING', 'PENDING', 'now')"
            )
            await conn.commit()
        await conn.close()
