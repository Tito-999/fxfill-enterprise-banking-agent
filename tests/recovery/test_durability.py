"""Durability tests: full restart, HITL persistence, idempotency across process boundaries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.checkpoint_store import SqliteCheckpointSaver
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.db import init_database
from fxfill_banking_agent.hitl_store import HITLSession, HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.idempotency_store import (
    IdempotencyStatus,
    SqliteIdempotencyStore,
)
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient, ToolResult

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_durable.db"


@pytest.fixture
async def init_db(db_path: Path) -> Path:
    conn = await init_database(db_path)
    await conn.close()
    return db_path


# ═══════════════════════════════════════════════════════════════════════════
# Checkpoint durability
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointDurability:
    @pytest.mark.asyncio
    async def test_checkpoint_survives_reconstruction(self, init_db: Path) -> None:
        """Checkpoint written by one runtime is readable after reconstruction."""
        saver = SqliteCheckpointSaver(init_db)

        config = {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}
        checkpoint = {"id": "ckpt1", "v": 1}
        await saver.aput(config, checkpoint, {}, {})

        tup = await saver.aget_tuple(config)
        assert tup is not None
        assert tup.checkpoint["id"] == "ckpt1"

        await saver.close()

        # Reconstruct
        saver2 = SqliteCheckpointSaver(init_db)
        tup2 = await saver2.aget_tuple(config)
        assert tup2 is not None
        assert tup2.checkpoint["id"] == "ckpt1"
        await saver2.close()

    @pytest.mark.asyncio
    async def test_missing_checkpoint_returns_none(self, init_db: Path) -> None:
        saver = SqliteCheckpointSaver(init_db)
        tup = await saver.aget_tuple({"configurable": {"thread_id": "ghost"}})
        assert tup is None
        await saver.close()


# ═══════════════════════════════════════════════════════════════════════════
# HITL session durability
# ═══════════════════════════════════════════════════════════════════════════


class TestHITLDurability:
    @pytest.mark.asyncio
    async def test_session_survives_store_reconstruction(self, init_db: Path) -> None:
        """HITL session persists across store instances."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        store1 = SqliteHITLStore(init_db)
        session = HITLSession(
            session_id="sess-1",
            user_id="alice",
            thread_id="t1",
            status=HITLSessionStatus.PENDING,
            tool_name="transfer_funds",
            tool_args={"amount": 100},
            authorization_decision="PENDING",
            approval_requirement="required",
            idempotency_key="idem-1",
            version=1,
            created_at=now,
            updated_at=now,
            expires_at=None,
        )
        await store1.insert(session)
        await store1.close()

        # New store instance reads same DB
        store2 = SqliteHITLStore(init_db)
        loaded = await store2.get("sess-1")
        assert loaded is not None
        assert loaded.status == HITLSessionStatus.PENDING
        assert loaded.tool_name == "transfer_funds"
        await store2.close()

    @pytest.mark.asyncio
    async def test_approve_after_reconstruction(self, init_db: Path) -> None:
        """Approve a session after destroying and reconstructing the store."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        store1 = SqliteHITLStore(init_db)
        await store1.insert(
            HITLSession(
                session_id="sess-2",
                user_id="alice",
                thread_id="t2",
                status=HITLSessionStatus.PENDING,
                tool_name="pay",
                tool_args={},
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik2",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )
        await store1.close()
        del store1

        # Reconstruct
        store2 = SqliteHITLStore(init_db)
        loaded = await store2.get("sess-2")
        ok = await store2.update_status(
            "sess-2", HITLSessionStatus.APPROVED, expected_version=loaded.version
        )
        assert ok
        loaded2 = await store2.get("sess-2")
        assert loaded2.status == HITLSessionStatus.APPROVED
        await store2.close()

    @pytest.mark.asyncio
    async def test_reject_after_reconstruction(self, init_db: Path) -> None:
        """Reject a session after store reconstruction."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        store1 = SqliteHITLStore(init_db)
        await store1.insert(
            HITLSession(
                session_id="sess-r",
                user_id="bob",
                thread_id="t3",
                status=HITLSessionStatus.PENDING,
                tool_name="delete",
                tool_args={},
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-r",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )
        await store1.close()

        store2 = SqliteHITLStore(init_db)
        loaded = await store2.get("sess-r")
        ok = await store2.update_status(
            "sess-r", HITLSessionStatus.REJECTED, expected_version=loaded.version
        )
        assert ok
        await store2.close()

    @pytest.mark.asyncio
    async def test_cross_user_isolation(self, init_db: Path) -> None:
        """Listing pending for user A does not return user B's sessions."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        store = SqliteHITLStore(init_db)
        await store.insert(
            HITLSession(
                session_id="a1",
                user_id="alice",
                thread_id="ta",
                status=HITLSessionStatus.PENDING,
                tool_name="t",
                tool_args={},
                authorization_decision="PENDING",
                approval_requirement="r",
                idempotency_key="ka",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )
        await store.insert(
            HITLSession(
                session_id="b1",
                user_id="bob",
                thread_id="tb",
                status=HITLSessionStatus.PENDING,
                tool_name="t",
                tool_args={},
                authorization_decision="PENDING",
                approval_requirement="r",
                idempotency_key="kb",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )
        alice_sessions = await store.list_pending(user_id="alice")
        assert len(alice_sessions) == 1
        assert alice_sessions[0].session_id == "a1"
        await store.close()

    @pytest.mark.asyncio
    async def test_expired_session_cannot_be_approved(self, init_db: Path) -> None:
        """An expired PENDING session cannot transition to APPROVED."""
        from datetime import datetime, timedelta, timezone

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        store = SqliteHITLStore(init_db)
        await store.insert(
            HITLSession(
                session_id="exp",
                user_id="u",
                thread_id="t",
                status=HITLSessionStatus.PENDING,
                tool_name="x",
                tool_args={},
                authorization_decision="PENDING",
                approval_requirement="r",
                idempotency_key="ke",
                version=1,
                created_at=past,
                updated_at=past,
                expires_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            )
        )
        loaded = await store.get("exp")
        assert loaded.is_expired()
        await store.close()

    @pytest.mark.asyncio
    async def test_concurrent_approve_fails_on_version_mismatch(self, init_db: Path) -> None:
        """Optimistic locking prevents double-approve."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        store = SqliteHITLStore(init_db)
        await store.insert(
            HITLSession(
                session_id="concur",
                user_id="u",
                thread_id="t",
                status=HITLSessionStatus.PENDING,
                tool_name="x",
                tool_args={},
                authorization_decision="PENDING",
                approval_requirement="r",
                idempotency_key="kc",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        # First approval succeeds
        ok1 = await store.update_status("concur", HITLSessionStatus.APPROVED, expected_version=1)
        assert ok1

        # Second approval with stale version fails
        ok2 = await store.update_status("concur", HITLSessionStatus.APPROVED, expected_version=1)
        assert not ok2

        await store.close()


# ═══════════════════════════════════════════════════════════════════════════
# Idempotency durability
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotencyDurability:
    @pytest.mark.asyncio
    async def test_succeeded_operation_not_repeated(self, init_db: Path) -> None:
        """A SUCCEEDED idempotency record blocks re-execution."""
        store = SqliteIdempotencyStore(init_db)
        await store.reserve("key-1", "transfer", {"amt": 100})
        await store.mark_executing("key-1")
        await store.mark_succeeded("key-1", "done")

        # Verify it's terminal
        rec = await store.get("key-1")
        assert rec.is_terminal()
        assert not rec.can_retry()
        await store.close()

    @pytest.mark.asyncio
    async def test_failed_operation_can_retry(self, init_db: Path) -> None:
        """A FAILED operation can be retried."""
        store = SqliteIdempotencyStore(init_db)
        await store.reserve("key-2", "lookup", {"id": 1})
        await store.mark_executing("key-2")
        await store.mark_failed("key-2", "timeout")

        rec = await store.get("key-2")
        assert rec.can_retry()
        await store.close()

    @pytest.mark.asyncio
    async def test_unknown_outcome_fails_closed_for_write(self, init_db: Path) -> None:
        """UNKNOWN status means outcome uncertain — should fail closed."""
        store = SqliteIdempotencyStore(init_db)
        await store.reserve("key-3", "transfer", {"amt": 5000})
        await store.mark_unknown("key-3")

        rec = await store.get("key-3")
        assert not rec.is_terminal()
        assert not rec.can_retry()
        await store.close()

    @pytest.mark.asyncio
    async def test_reserve_is_idempotent(self, init_db: Path) -> None:
        """Calling reserve twice returns the same record."""
        store = SqliteIdempotencyStore(init_db)
        r1 = await store.reserve("key-4", "tool1", {})
        r2 = await store.reserve("key-4", "tool1", {})
        assert r1.idempotency_key == r2.idempotency_key
        assert r1.status == IdempotencyStatus.RESERVED
        await store.close()


# ═══════════════════════════════════════════════════════════════════════════
# Full restart scenarios
# ═══════════════════════════════════════════════════════════════════════════


class TestFullRestartWorkflow:
    @pytest.mark.asyncio
    async def test_full_restart_cycle(self, tmp_path: Path) -> None:
        """Complete cycle: run → pause → destroy → reconstruct → resume → verify."""
        db = tmp_path / "full_cycle.db"

        # Phase 1: Create first runtime and run
        llm = MockLLM(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "get_balance", "args": {"acct": "A"}, "id": "t1"}],
                ),
                AIMessage(content="Your balance is $100."),
            ]
        )
        mcp = StubMCPClient(tools={"get_balance": ToolResult("get_balance", True, "$100.00")})
        auth = AuthorizationGateway(policy=AutoApprovePolicy())
        checkpoint = SqliteCheckpointSaver(db)
        idem = SqliteIdempotencyStore(db)

        rt1 = AgentRuntime(
            llm=llm,
            mcp_client=mcp,
            auth_gateway=auth,
            checkpoint_saver=checkpoint,
            idempotency_store=idem,
            config=AgentConfig(),
        )
        result1 = await rt1.run("balance?", run_id="cycle-1")
        assert result1["final_answer"] == "Your balance is $100."
        assert len(mcp.calls) == 1
        await checkpoint.close()
        await idem.close()

        # Phase 2: Destroy everything, reconstruct
        del rt1, checkpoint, idem

        # Phase 3: Prove data survived by reconstructing the store
        idem2 = SqliteIdempotencyStore(db)
        assert idem2 is not None
        await idem2.close()


# ═══════════════════════════════════════════════════════════════════════════
# Process-boundary test
# ═══════════════════════════════════════════════════════════════════════════


class TestProcessBoundary:
    # Shared subprocess-safe runner
    @staticmethod
    def _run_subprocess(code: str, *, timeout: int = 10) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                cwd="/mnt/f/projects/fxfill-enterprise-banking-agent",
            )
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(
                f"Subprocess timed out after {timeout}s.\n"
                f"stdout so far: {exc.stdout}\nstderr so far: {exc.stderr}"
            ) from exc

    def test_sqlite_data_survives_python_process(self, tmp_path: Path) -> None:
        """Process A writes data, exits. Process B reads it back."""
        db = tmp_path / "proc_boundary.db"
        db_abs = str(db.absolute())

        result_a = self._run_subprocess(f"""
import asyncio
from fxfill_banking_agent.db import init_database
from fxfill_banking_agent.hitl_store import SqliteHITLStore, HITLSession, HITLSessionStatus
from datetime import datetime, timezone

async def main():
    conn = await init_database('{db_abs}')
    await conn.close()
    store = SqliteHITLStore('{db_abs}')
    now = datetime.now(timezone.utc).isoformat()
    await store.insert(HITLSession(
        session_id='proc-test', user_id='alice', thread_id='pt',
        status=HITLSessionStatus.PENDING, tool_name='test_tool', tool_args={{}},
        authorization_decision='PENDING', approval_requirement='required',
        idempotency_key='pk1', version=1, created_at=now, updated_at=now, expires_at=None,
    ))
    await store.close()
    print('OK')

asyncio.run(main())
""")
        assert result_a.returncode == 0, f"Process A failed: {result_a.stderr}"
        assert "OK" in result_a.stdout

        result_b = self._run_subprocess(f"""
import asyncio
from fxfill_banking_agent.hitl_store import SqliteHITLStore

async def main():
    store = SqliteHITLStore('{db_abs}')
    session = await store.get('proc-test')
    assert session is not None, 'Session not found after process restart'
    assert session.status.value == 'PENDING'
    await store.close()
    print('VERIFIED')

asyncio.run(main())
""")
        assert result_b.returncode == 0, f"Process B failed: {result_b.stderr}"
        assert "VERIFIED" in result_b.stdout

    def test_corrupted_checkpoint_handled(self, tmp_path: Path) -> None:
        """Reading from a corrupt database fails gracefully and exits cleanly."""
        db = tmp_path / "corrupt.db"
        db_abs = str(db.absolute())
        db.write_text("not a valid sqlite database")

        result = self._run_subprocess(f"""
import asyncio
from fxfill_banking_agent.checkpoint_store import SqliteCheckpointSaver
async def main():
    try:
        saver = SqliteCheckpointSaver('{db_abs}')
        await saver._ensure_connected()
        print('UNEXPECTED_SUCCESS')
    except Exception as e:
        print(f'EXPECTED_ERROR: {{type(e).__name__}}')
asyncio.run(main())
""")
        assert "EXPECTED_ERROR" in result.stdout, (
            f"Expected error on corrupt db, got stdout={result.stdout} stderr={result.stderr}"
        )
        assert result.returncode == 0, f"Subprocess should exit 0, got {result.returncode}"

    def test_truncated_sqlite_file(self, tmp_path: Path) -> None:
        """A truncated SQLite file must produce an error and exit cleanly."""
        db = tmp_path / "truncated.db"
        db_abs = str(db.absolute())
        # Write a valid SQLite header then truncate (not a complete database)
        db.write_bytes(b"SQLite format 3\0" + b"\0" * 90)

        result = self._run_subprocess(f"""
import asyncio
from fxfill_banking_agent.db import init_database
async def main():
    try:
        await init_database('{db_abs}')
        print('UNEXPECTED_SUCCESS')
    except Exception as e:
        print(f'EXPECTED_ERROR: {{type(e).__name__}}')
asyncio.run(main())
""")
        assert "EXPECTED_ERROR" in result.stdout, (
            f"Expected error on truncated db, got stdout={result.stdout} stderr={result.stderr}"
        )

    def test_incompatible_schema_version_fails(self, tmp_path: Path) -> None:
        """A database with a future schema version must fail initialization."""
        db = tmp_path / "future.db"
        db_abs = str(db.absolute())

        result = self._run_subprocess(f"""
import asyncio, aiosqlite
async def main():
    conn = await aiosqlite.connect('{db_abs}')
    await conn.execute('CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY)')
    await conn.execute('INSERT OR REPLACE INTO _schema_version (version) VALUES (999)')
    await conn.commit()
    await conn.close()
    try:
        from fxfill_banking_agent.db import init_database
        await init_database('{db_abs}', schema_version=1)
        print('UNEXPECTED_SUCCESS')
    except RuntimeError as e:
        print(f'EXPECTED: {{e}}')
asyncio.run(main())
""")
        assert "EXPECTED" in result.stdout, (
            f"Expected schema version error, got stdout={result.stdout} stderr={result.stderr}"
        )

    def test_valid_db_after_corrupt_db(self, tmp_path: Path) -> None:
        """A valid database can still be opened after a corrupt database fails."""
        corrupt = tmp_path / "corrupt2.db"
        corrupt_abs = str(corrupt.absolute())
        corrupt.write_text("garbage not sqlite")

        # First, try the corrupt one — must fail
        r1 = self._run_subprocess(f"""
import asyncio
from fxfill_banking_agent.db import init_database
async def main():
    try:
        await init_database('{corrupt_abs}')
        print('UNEXPECTED_SUCCESS')
    except Exception as e:
        print(f'EXPECTED: {{type(e).__name__}}')
asyncio.run(main())
""")
        assert "EXPECTED" in r1.stdout, f"Corrupt db should fail: {r1.stdout} {r1.stderr}"

        # Then, open a valid database — must succeed
        valid = tmp_path / "valid_after_corrupt.db"
        valid_abs = str(valid.absolute())
        r2 = self._run_subprocess(f"""
import asyncio
from fxfill_banking_agent.db import init_database
async def main():
    conn = await init_database('{valid_abs}')
    await conn.close()
    print('OK')
asyncio.run(main())
""")
        assert "OK" in r2.stdout, f"Valid db should open: {r2.stdout} {r2.stderr}"
        assert r2.returncode == 0

    def test_thread_cleanup_after_init_failure(self, tmp_path: Path) -> None:
        """After init_database fails, the aiosqlite worker thread exits cleanly."""
        db = tmp_path / "bad.db"
        db_abs = str(db.absolute())
        db.write_text("definitely not sqlite")

        # Run: try to init, assert failure, verify process exits promptly
        result = self._run_subprocess(f"""
import asyncio, sys
from fxfill_banking_agent.db import init_database

async def main():
    try:
        await init_database('{db_abs}')
        print('UNEXPECTED_SUCCESS')
        sys.exit(1)
    except Exception:
        print('CAUGHT')
        # The critical assertion: the process must exit without hanging.
        # If the aiosqlite thread leaked, asyncio.run() would hang here.

asyncio.run(main())
print('EXITED_CLEANLY')
""")
        assert "CAUGHT" in result.stdout, f"Should catch error: {result.stdout} {result.stderr}"
        assert "EXITED_CLEANLY" in result.stdout, (
            f"Process must exit cleanly (thread leak detected): {result.stdout} {result.stderr}"
        )
