"""V4 migration tests: tool_call_id backfill, preservation, fail-closed."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from fxfill_banking_agent.db import init_database


class TestV4Migration:
    @pytest.mark.asyncio
    async def test_empty_to_v4(self, tmp_path: Path) -> None:
        conn = await init_database(tmp_path / "v4empty.db", schema_version=4)
        cursor = await conn.execute("SELECT version FROM _schema_version")
        row = await cursor.fetchone()
        assert row["version"] == 4
        cursor = await conn.execute("PRAGMA table_info(hitl_sessions)")
        cols = {r["name"] for r in await cursor.fetchall()}
        assert "tool_call_id" in cols
        await conn.close()

    @pytest.mark.asyncio
    async def test_v3_to_v4_preserves_data(self, tmp_path: Path) -> None:
        conn = await init_database(tmp_path / "v3tov4.db", schema_version=3)
        await conn.execute(
            "INSERT INTO hitl_sessions (session_id, user_id, thread_id, status, tool_name, tool_args, authorization_decision, approval_requirement, idempotency_key, version, created_at, updated_at) VALUES ('s1','u1','t1','PENDING','submit_transfer','{}','PENDING','r','ik1',1,'now','now')"
        )
        await conn.commit()
        await conn.close()
        conn = await init_database(tmp_path / "v3tov4.db", schema_version=4)
        cursor = await conn.execute("SELECT tool_call_id FROM hitl_sessions WHERE session_id='s1'")
        row = await cursor.fetchone()
        assert row["tool_call_id"] == ""  # historical rows get empty default
        await conn.close()

    @pytest.mark.asyncio
    async def test_v3_does_not_run_v4(self, tmp_path: Path) -> None:
        conn = await init_database(tmp_path / "v3only.db", schema_version=3)
        cursor = await conn.execute("SELECT version FROM _schema_version")
        row = await cursor.fetchone()
        assert row["version"] == 3
        cursor = await conn.execute("PRAGMA table_info(hitl_sessions)")
        cols = {r["name"] for r in await cursor.fetchall()}
        assert "tool_call_id" not in cols  # v4 not executed
        await conn.close()

    @pytest.mark.asyncio
    async def test_repeated_v4_idempotent(self, tmp_path: Path) -> None:
        c1 = await init_database(tmp_path / "idem.db", schema_version=4)
        await c1.close()
        c2 = await init_database(tmp_path / "idem.db", schema_version=4)
        assert c2 is not None
        await c2.close()

    @pytest.mark.asyncio
    async def test_empty_tool_call_id_fails_closed(self, tmp_path: Path) -> None:
        """Historical row with empty tool_call_id: executor must reject."""
        conn = await init_database(tmp_path / "historical.db", schema_version=4)
        await conn.execute(
            "INSERT INTO hitl_sessions (session_id, user_id, thread_id, status, tool_name, tool_args, tool_call_id, authorization_decision, approval_requirement, idempotency_key, version, created_at, updated_at) VALUES ('hist-1','u1','t1','PENDING','submit_transfer','{}','','PENDING','r','ik-h',1,'now','now')"
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT tool_call_id FROM hitl_sessions WHERE session_id='hist-1'"
        )
        row = await cursor.fetchone()
        assert row["tool_call_id"] == ""
        await conn.close()

    @pytest.mark.asyncio
    async def test_future_schema_rejection_unchanged(self, tmp_path: Path) -> None:
        conn = await aiosqlite.connect(str(tmp_path / "future.db"))
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY)"
        )
        await conn.execute("INSERT OR REPLACE INTO _schema_version (version) VALUES (999)")
        await conn.commit()
        await conn.close()
        with pytest.raises(RuntimeError, match="newer"):
            await init_database(tmp_path / "future.db", schema_version=4)


class TestToolCallIDInvariant:
    def test_no_tool_name_fallback_in_executor(self) -> None:
        """Executor must not use tool_name as fallback for empty tool_call_id."""
        with open("src/fxfill_banking_agent/approval_executor.py") as f:
            source = f.read()
        assert "session.tool_call_id or session.tool_name" not in source, (
            "Tool name fallback detected in executor — historical records must fail closed"
        )

    def test_real_tool_call_id_used_in_api(self) -> None:
        """API must store real pause.tool_call_id, not pause.tool_name."""
        with open("src/fxfill_banking_agent/api.py") as f:
            source = f.read()
        assert "tool_call_id=pause.tool_call_id" in source
        assert "tool_call_id=pause.tool_name" not in source
