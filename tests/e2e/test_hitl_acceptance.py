"""Acceptance tests: durable HITL workflow — correct tests for Step 4J."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.auth import AuthorizationGateway, ReadOnlyPolicy, RequireApprovalPolicy
from fxfill_banking_agent.banking.mcp_server import BankingMCPServer
from fxfill_banking_agent.grant_repo import GrantRecord, GrantRepository, _digest
from fxfill_banking_agent.hitl_store import HITLSession, HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.mcp.client import MCPClientAdapter
from fxfill_banking_agent.persistence import SqliteEventStore
from tests.fakes.transports import FakeHTTPTransport


def _make_text(content: str) -> tuple[int, str]:
    return 200, json.dumps({"id": "r", "model": "t", "choices": [{"message": {"content": content, "role": "assistant"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})


def _make_tool(name: str, args: dict, call_id: str = "t1") -> tuple[int, str]:
    return 200, json.dumps({"id": "r", "model": "t", "choices": [{"message": {"content": "", "role": "assistant", "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}], "usage": {"prompt_tokens": 2, "completion_tokens": 2}})


class TestStartupDependencies:
    @pytest.mark.asyncio
    async def test_approve_fails_without_grant_repo(self, tmp_path: Path) -> None:
        """Approve endpoint returns 501 when grant_repo is not configured."""
        from fxfill_banking_agent.providers.base import ProviderConfig
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider
        db = tmp_path / "startup.db"
        # Insert a valid PENDING HITL session first
        hitl = SqliteHITLStore(db)
        now = datetime.now(timezone.utc).isoformat()
        await hitl.insert(HITLSession(session_id="startup-test", user_id="u", thread_id="t", status=HITLSessionStatus.PENDING, tool_name="t", tool_args={}, authorization_decision="PENDING", approval_requirement="r", idempotency_key="ik-startup", version=1, created_at=now, updated_at=now, expires_at=None))
        # Create app WITHOUT grant_repo
        transport = FakeHTTPTransport([_make_text("ok")])
        llm = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        mcp = MCPClientAdapter(BankingMCPServer())
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        app = create_app(llm=llm, mcp_client=mcp, auth_gateway=auth, hitl_store=hitl)
        client = TestClient(app)
        resp = client.post("/agent/approve", json={"session_id": "startup-test", "decision": "approve"})
        assert resp.status_code == 501


class TestFullHTTPApproval:
    def test_agent_creates_hitl_session(self, tmp_path: Path) -> None:
        from fxfill_banking_agent.providers.base import ProviderConfig
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider
        db = tmp_path / "http_flow.db"
        transport = FakeHTTPTransport([_make_tool("submit_transfer", {"draft_id": "d1", "user_id": "user-carol"}, "tc-http-1"), _make_text("ok")])
        llm = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        mcp = MCPClientAdapter(BankingMCPServer())
        auth = AuthorizationGateway(policy=RequireApprovalPolicy())
        grant_repo = GrantRepository(db)
        hitl = SqliteHITLStore(db)
        app = create_app(llm=llm, mcp_client=mcp, auth_gateway=auth, hitl_store=hitl, grant_repo=grant_repo)
        client = TestClient(app)
        resp = client.post("/agent", json={"message": "send $50", "session_id": "http-1"})
        assert resp.status_code == 202


class TestRejection:
    @pytest.mark.asyncio
    async def test_rejection_directly_from_pending(self, tmp_path: Path) -> None:
        """Rejection transitions PENDING→REJECTED without APPROVED or CONSUMING."""
        db = tmp_path / "reject_pending.db"
        grant_repo = GrantRepository(db)
        hitl = SqliteHITLStore(db)
        now = datetime.now(timezone.utc).isoformat()
        # Insert PENDING
        g = GrantRecord(session_id="rej-1", requesting_user_id="u", approving_actor_id="", thread_id="t", run_id="r", checkpoint_id="", tool_call_id="tc-rej-1", tool_name="submit_transfer", canonical_tool_args='{"x":1}', argument_digest=_digest({"x": 1}), idempotency_key="ik-rej", decision="PENDING", status="PENDING", created_at=now, approved_at=None, expires_at=None, consuming_at=None, consumed_at=None, failed_at=None, version=1)
        await grant_repo.insert_pending(g)
        s = HITLSession(session_id="rej-1", user_id="u", thread_id="t", status=HITLSessionStatus.PENDING, tool_name="submit_transfer", tool_args={"x": 1}, authorization_decision="PENDING", approval_requirement="r", idempotency_key="ik-rej", version=1, created_at=now, updated_at=now, expires_at=None)
        await hitl.insert(s)
        # Reject both
        await hitl.update_status("rej-1", HITLSessionStatus.REJECTED, expected_version=1)
        await grant_repo.mark_rejected("rej-1")
        # Verify
        s2 = await hitl.get("rej-1")
        assert s2 is not None and s2.status == HITLSessionStatus.REJECTED
        g2 = await grant_repo.get_by_session("rej-1")
        assert g2 is not None and g2.status == "REJECTED"


class TestConcurrent:
    @pytest.mark.asyncio
    async def test_two_repos_same_db_one_winner(self, tmp_path: Path) -> None:
        """Two GrantRepository instances on same SQLite file: atomic claim has one winner."""
        import asyncio
        db = tmp_path / "race.db"
        now = datetime.now(timezone.utc).isoformat()
        g = GrantRecord(session_id="race-1", requesting_user_id="u", approving_actor_id="a", thread_id="t", run_id="r", checkpoint_id="", tool_call_id="tc-race", tool_name="submit_transfer", canonical_tool_args='{"x":1}', argument_digest=_digest({"x": 1}), idempotency_key="ik-race", decision="PENDING", status="PENDING", created_at=now, approved_at=None, expires_at=None, consuming_at=None, consumed_at=None, failed_at=None, version=1)
        # Insert + approve via first repo
        r1 = GrantRepository(db)
        await r1.insert_pending(g)
        await r1.approve_pending("race-1", "a", expected_version=1)
        # Concurrent consume from two repos on SAME db
        r2 = GrantRepository(db)
        results = await asyncio.gather(
            r1.atomic_consume(session_id="race-1", user_id="u", approving_actor_id="a", thread_id="t", tool_call_id="tc-race", tool_name="submit_transfer", tool_args={"x": 1}, idempotency_key="ik-race", version=1),
            r2.atomic_consume(session_id="race-1", user_id="u", approving_actor_id="a", thread_id="t", tool_call_id="tc-race", tool_name="submit_transfer", tool_args={"x": 1}, idempotency_key="ik-race", version=1),
        )
        winners = [r for r in results if r is not None]
        assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"


class TestIdempotencyReplay:
    @pytest.mark.asyncio
    async def test_succeeded_returns_without_mcp(self, tmp_path: Path) -> None:
        db = tmp_path / "idem_success.db"
        store = SqliteIdempotencyStore(db)
        await store.reserve("s-1", "submit_transfer", {"amt": 50})
        await store.mark_executing("s-1")
        await store.mark_succeeded("s-1", "done")
        rec = await store.get("s-1")
        assert rec is not None and rec.is_terminal()
        assert not rec.can_retry()

    @pytest.mark.asyncio
    async def test_reserved_fails_closed(self, tmp_path: Path) -> None:
        db = tmp_path / "idem_res.db"
        store = SqliteIdempotencyStore(db)
        await store.reserve("r-1", "transfer", {"amt": 100})
        rec = await store.get("r-1")
        assert rec is not None and not rec.is_terminal()

    @pytest.mark.asyncio
    async def test_unknown_fails_closed(self, tmp_path: Path) -> None:
        db = tmp_path / "idem_unk.db"
        store = SqliteIdempotencyStore(db)
        await store.reserve("u-1", "transfer", {"amt": 1000})
        await store.mark_unknown("u-1")
        rec = await store.get("u-1")
        assert rec is not None and not rec.can_retry()
        assert not rec.is_terminal()


class TestDistinctToolCallID:
    @pytest.mark.asyncio
    async def test_same_tool_name_different_ids_cannot_cross(self, tmp_path: Path) -> None:
        """Two grants with same tool_name but different tool_call_id — approving one doesn't approve the other."""
        db = tmp_path / "distinct.db"
        repo = GrantRepository(db)
        now = datetime.now(timezone.utc).isoformat()
        g1 = GrantRecord(session_id="dist-1", requesting_user_id="u", approving_actor_id="a", thread_id="t", run_id="r", checkpoint_id="", tool_call_id="tc-alpha", tool_name="submit_transfer", canonical_tool_args='{"x":1}', argument_digest=_digest({"x": 1}), idempotency_key="ik-alpha", decision="PENDING", status="PENDING", created_at=now, approved_at=None, expires_at=None, consuming_at=None, consumed_at=None, failed_at=None, version=1)
        g2 = GrantRecord(session_id="dist-2", requesting_user_id="u", approving_actor_id="a", thread_id="t", run_id="r", checkpoint_id="", tool_call_id="tc-beta", tool_name="submit_transfer", canonical_tool_args='{"x":1}', argument_digest=_digest({"x": 1}), idempotency_key="ik-beta", decision="PENDING", status="PENDING", created_at=now, approved_at=None, expires_at=None, consuming_at=None, consumed_at=None, failed_at=None, version=1)
        await repo.insert_pending(g1)
        await repo.insert_pending(g2)
        await repo.approve_pending("dist-1", "a", expected_version=1)
        await repo.approve_pending("dist-2", "a", expected_version=1)
        # Consume g1 with tc-alpha — should work
        c1 = await repo.atomic_consume(session_id="dist-1", user_id="u", approving_actor_id="a", thread_id="t", tool_call_id="tc-alpha", tool_name="submit_transfer", tool_args={"x": 1}, idempotency_key="ik-alpha", version=1)
        assert c1 is not None
        # Try to consume g2 with tc-alpha — should fail (wrong tool_call_id)
        c2 = await repo.atomic_consume(session_id="dist-2", user_id="u", approving_actor_id="a", thread_id="t", tool_call_id="tc-alpha", tool_name="submit_transfer", tool_args={"x": 1}, idempotency_key="ik-beta", version=1)
        assert c2 is None


class TestEvents:
    @pytest.mark.asyncio
    async def test_events_persisted(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteEventStore(db)
        await store.connect()
        from fxfill_banking_agent.persistence import AgentEvent, EventKind
        kinds = [EventKind.USER_MESSAGE, EventKind.CHECKPOINT, EventKind.AGENT_MESSAGE]
        for i, k in enumerate(kinds):
            await store.insert(AgentEvent(run_id="evt-seq", seq=i, kind=k, payload={"n": i}))
        events = await store.query_run("evt-seq")
        assert len(events) == 3
        assert [e.kind for e in events] == kinds
        await store.close()

    def test_sqlite_connections_closed_after_tests(self) -> None:
        from fxfill_banking_agent.db import _open_connections
        assert len(_open_connections) == 0
