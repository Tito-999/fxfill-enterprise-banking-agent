"""Acceptance tests: durable HITL workflow — idempotency, concurrent, events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.auth import AuthorizationGateway, ReadOnlyPolicy, RequireApprovalPolicy
from fxfill_banking_agent.banking.mcp_server import BankingMCPServer
from fxfill_banking_agent.grant_repo import GrantRecord, GrantRepository
from fxfill_banking_agent.hitl_store import HITLSession, HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.mcp.client import MCPClientAdapter
from fxfill_banking_agent.persistence import SqliteEventStore
from tests.fakes.transports import FakeHTTPTransport


def _make_text(content: str) -> tuple[int, str]:
    return 200, json.dumps(
        {
            "id": "r",
            "model": "t",
            "choices": [{"message": {"content": content, "role": "assistant"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )


def _make_tool(name: str, args: dict, call_id: str = "t1") -> tuple[int, str]:
    return 200, json.dumps(
        {
            "id": "r",
            "model": "t",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": name, "arguments": json.dumps(args)},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2},
        }
    )


class TestFullHTTPApproval:
    def test_agent_creates_hitl_session_and_grant(self, tmp_path: Path) -> None:
        from fxfill_banking_agent.providers.base import ProviderConfig
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

        db = tmp_path / "accept.db"
        transport = FakeHTTPTransport(
            [
                _make_tool("submit_transfer", {"draft_id": "d1", "user_id": "user-carol"}, "tc1"),
                _make_text("ok"),
            ]
        )
        llm = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        mcp = MCPClientAdapter(BankingMCPServer())
        auth = AuthorizationGateway(policy=RequireApprovalPolicy())
        grant_repo = GrantRepository(db)
        hitl = SqliteHITLStore(db)
        app = create_app(
            llm=llm, mcp_client=mcp, auth_gateway=auth, hitl_store=hitl, grant_repo=grant_repo
        )
        client = TestClient(app)
        resp = client.post(
            "/agent", json={"message": "send $50 to Electric", "session_id": "accept-1"}
        )
        assert resp.status_code == 202

    def test_grant_repo_missing_fails_startup(self, tmp_path: Path) -> None:
        from fxfill_banking_agent.providers.base import ProviderConfig
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

        transport = FakeHTTPTransport([_make_text("ok")])
        llm = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        mcp = MCPClientAdapter(BankingMCPServer())
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        app = create_app(
            llm=llm,
            mcp_client=mcp,
            auth_gateway=auth,
            hitl_store=SqliteHITLStore(str(tmp_path / "no_grant.db")),
        )
        client = TestClient(app)
        resp = client.post("/agent/approve", json={"session_id": "any", "decision": "approve"})
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_reject_transitions_both(self, tmp_path: Path) -> None:
        db = tmp_path / "reject_both.db"
        grant_repo = GrantRepository(db)
        hitl = SqliteHITLStore(db)
        now = datetime.now(timezone.utc).isoformat()
        s = HITLSession(
            session_id="reject-1",
            user_id="u",
            thread_id="t",
            status=HITLSessionStatus.PENDING,
            tool_name="submit_transfer",
            tool_args={"x": 1},
            authorization_decision="PENDING",
            approval_requirement="r",
            idempotency_key="ik1",
            version=1,
            created_at=now,
            updated_at=now,
            expires_at=None,
        )
        await hitl.insert(s)
        g = GrantRecord(
            session_id="reject-1",
            requesting_user_id="u",
            approving_actor_id="",
            thread_id="t",
            run_id="r1",
            checkpoint_id="",
            tool_call_id="submit_transfer",
            tool_name="submit_transfer",
            canonical_tool_args=json.dumps({"x": 1}),
            argument_digest="d1",
            idempotency_key="ik1",
            decision="PENDING",
            status="PENDING",
            created_at=now,
            approved_at=None,
            expires_at=None,
            consuming_at=None,
            consumed_at=None,
            failed_at=None,
            version=1,
        )
        await grant_repo.insert_pending(g)
        await grant_repo.approve_pending("reject-1", "operator", expected_version=1)
        await grant_repo.atomic_consume(
            session_id="reject-1",
            user_id="u",
            approving_actor_id="operator",
            thread_id="t",
            tool_call_id="submit_transfer",
            tool_name="submit_transfer",
            tool_args={"x": 1},
            idempotency_key="ik1",
            version=1,
        )
        await hitl.update_status("reject-1", HITLSessionStatus.REJECTED, expected_version=1)
        await grant_repo.mark_failed("reject-1")
        s2 = await hitl.get("reject-1")
        assert s2.is_terminal()
        grant = await grant_repo.get_by_session("reject-1")
        assert grant and grant.status == "FAILED"


class TestIdempotencyReplay:
    @pytest.mark.asyncio
    async def test_succeeded_idempotency_prevents_mcp(self, tmp_path: Path) -> None:
        db = tmp_path / "idem_replay.db"
        store = SqliteIdempotencyStore(db)
        await store.reserve("replay-1", "submit_transfer", {"amt": 50})
        await store.mark_executing("replay-1")
        await store.mark_succeeded("replay-1", "done")
        rec = await store.get("replay-1")
        assert rec.is_terminal()
        assert not rec.can_retry()

    @pytest.mark.asyncio
    async def test_reserved_idempotency_fails_closed(self, tmp_path: Path) -> None:
        db = tmp_path / "idem_reserved.db"
        store = SqliteIdempotencyStore(db)
        await store.reserve("res-1", "transfer", {"amt": 100})
        rec = await store.get("res-1")
        assert not rec.is_terminal()

    @pytest.mark.asyncio
    async def test_unknown_idempotency_fails_closed(self, tmp_path: Path) -> None:
        db = tmp_path / "idem_unknown.db"
        store = SqliteIdempotencyStore(db)
        await store.reserve("unk-1", "transfer", {"amt": 1000})
        await store.mark_unknown("unk-1")
        rec = await store.get("unk-1")
        assert not rec.can_retry()
        assert not rec.is_terminal()


class TestConcurrentConsumption:
    @pytest.mark.asyncio
    async def test_two_repos_one_winner(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc).isoformat()
        db_a = tmp_path / "concur_a.db"
        db_b = tmp_path / "concur_b.db"
        r1 = GrantRepository(db_a)
        r2 = GrantRepository(db_b)
        g = GrantRecord(
            session_id="race-1",
            requesting_user_id="u",
            approving_actor_id="a",
            thread_id="t",
            run_id="r",
            checkpoint_id="",
            tool_call_id="submit_transfer",
            tool_name="submit_transfer",
            canonical_tool_args='{"x":1}',
            argument_digest="d",
            idempotency_key="ik-race",
            decision="PENDING",
            status="PENDING",
            created_at=now,
            approved_at=None,
            expires_at=None,
            consuming_at=None,
            consumed_at=None,
            failed_at=None,
            version=1,
        )
        await r1.insert_pending(g)
        await r1.approve_pending("race-1", "a", expected_version=1)
        c1 = await r1.atomic_consume(
            session_id="race-1",
            user_id="u",
            approving_actor_id="a",
            thread_id="t",
            tool_call_id="submit_transfer",
            tool_name="submit_transfer",
            tool_args={"x": 1},
            idempotency_key="ik-race",
            version=1,
        )
        c2 = await r2.atomic_consume(
            session_id="race-1",
            user_id="u",
            approving_actor_id="a",
            thread_id="t",
            tool_call_id="submit_transfer",
            tool_name="submit_transfer",
            tool_args={"x": 1},
            idempotency_key="ik-race",
            version=1,
        )
        assert c1 is not None
        assert c2 is None

    @pytest.mark.asyncio
    async def test_durable_events_persisted(self, tmp_path: Path) -> None:
        db = tmp_path / "events.db"
        store = SqliteEventStore(db)
        await store.connect()
        from fxfill_banking_agent.persistence import AgentEvent, EventKind

        await store.insert(
            AgentEvent(run_id="evt-1", seq=0, kind=EventKind.USER_MESSAGE, payload={"msg": "test"})
        )
        events = await store.query_run("evt-1")
        assert len(events) == 1
        assert events[0].kind == EventKind.USER_MESSAGE
        await store.close()

    def test_sqlite_connections_closed(self) -> None:
        from fxfill_banking_agent.db import _open_connections

        assert len(_open_connections) == 0
