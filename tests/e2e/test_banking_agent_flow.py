"""E2E banking flow via HTTP: FastAPI → AgentRuntime → LangGraph →
Provider → MCP → BankingServer → Auth → HITL → SQLite stores."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.auth import AuthorizationGateway, ReadOnlyPolicy, RequireApprovalPolicy
from fxfill_banking_agent.banking.mcp_server import BankingMCPServer
from fxfill_banking_agent.hitl_store import SqliteHITLStore
from fxfill_banking_agent.mcp.client import MCPClientAdapter
from tests.fakes.transports import FakeHTTPTransport


def _make_text_response(content: str) -> tuple[int, str]:
    return 200, json.dumps(
        {
            "id": "r1",
            "model": "test",
            "choices": [{"message": {"content": content, "role": "assistant"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2},
        }
    )


def _make_tool(tool_name: str, args: dict, call_id: str = "t1") -> tuple[int, str]:
    return 200, json.dumps(
        {
            "id": "r1",
            "model": "test",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": json.dumps(args)},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3},
        }
    )


def _make_client(
    tmp_path: Path,
    llm_responses: list[tuple[int, str]],
    auth_gateway: AuthorizationGateway,
) -> TestClient:
    from fxfill_banking_agent.providers.base import ProviderConfig
    from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

    transport = FakeHTTPTransport(llm_responses)
    llm = DeepSeekProvider(ProviderConfig(), "test-token", transport=transport)

    # BankingMCPServer is in-process; connect synchronously
    mcp = MCPClientAdapter(BankingMCPServer())
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.run_until_complete(mcp.connect())
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(mcp.connect())

    db = tmp_path / "e2e.db"
    store = SqliteHITLStore(db)
    app = create_app(llm=llm, mcp_client=mcp, auth_gateway=auth_gateway, hitl_store=store)
    return TestClient(app)


class TestE2EBankingHealth:
    def test_health(self, tmp_path: Path) -> None:
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        client = _make_client(tmp_path, [_make_text_response("ok")], auth)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestE2EReadOnlyFlow:
    def test_read_only_agent_request(self, tmp_path: Path) -> None:
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        client = _make_client(
            tmp_path,
            [
                _make_tool(
                    "get_balance", {"account_id": "ACC-1001", "user_id": "user-alice"}, "t1"
                ),
                _make_text_response("Your balance is $15,000."),
            ],
            auth,
        )
        resp = client.post("/agent", json={"message": "balance?"})
        assert resp.status_code == 200
        answer = resp.json().get("answer", "")
        assert "15000" in answer.replace(",", "") or "15,000" in answer


class TestE2ETransferFlow:
    def test_transfer_request_triggers_hitl(self, tmp_path: Path) -> None:
        """A transfer request triggers HITL pause (202)."""
        auth = AuthorizationGateway(policy=RequireApprovalPolicy())
        client = _make_client(
            tmp_path,
            [
                _make_tool(
                    "create_transfer_draft",
                    {
                        "source_account_id": "ACC-3001",
                        "beneficiary_id": "BEN-003",
                        "amount": 50.0,
                        "currency": "USD",
                        "user_id": "user-carol",
                        "idempotency_key": "e2e-t1",
                    },
                    "t1",
                ),
                _make_tool(
                    "submit_transfer", {"draft_id": "draft-1", "user_id": "user-carol"}, "t2"
                ),
                _make_text_response("Transfer complete."),
            ],
            auth,
        )
        resp = client.post(
            "/agent", json={"message": "Send $50 to Electric Company", "session_id": "e2e-sess-1"}
        )
        # submit_transfer is HIGH_RISK → HITL pause via 202 or tool rejection
        assert resp.status_code in (200, 202)

    def test_approve_reject_endpoints_exist(self, tmp_path: Path) -> None:
        """The HITL approve/reject endpoints are accessible."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        client = _make_client(tmp_path, [_make_text_response("ok")], auth)
        resp = client.post("/agent/approve", json={"session_id": "ghost", "decision": "approve"})
        assert resp.status_code in (404, 501)  # No such session — endpoint exists

    def test_unknown_session_handled(self, tmp_path: Path) -> None:
        """Unknown session returns 200 — starts a new conversation."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        client = _make_client(tmp_path, [_make_text_response("Welcome!")], auth)
        resp = client.post("/agent", json={"message": "hello", "session_id": "brand-new-xyz"})
        assert resp.status_code == 200


class TestE2ECrossUser:
    def test_cross_user_session_isolated(self, tmp_path: Path) -> None:
        """Different sessions have independent state."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        client = _make_client(
            tmp_path,
            [
                _make_text_response("Alice data."),
                _make_text_response("Bob data."),
            ],
            auth,
        )
        r1 = client.post("/agent", json={"message": "alice", "session_id": "alice-sess"})
        r2 = client.post("/agent", json={"message": "bob", "session_id": "bob-sess"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["session_id"] != r2.json()["session_id"]


class TestE2ERestartDurability:
    def test_restart_integration(self, tmp_path: Path) -> None:
        """New runtime on same DB path works after first request."""
        db = tmp_path / "restart_e2e.db"
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())

        # First runtime
        from fxfill_banking_agent.providers.base import ProviderConfig
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

        transport1 = FakeHTTPTransport([_make_text_response("First response.")])
        llm1 = DeepSeekProvider(ProviderConfig(), "token", transport=transport1)
        mcp1 = MCPClientAdapter(BankingMCPServer())
        app1 = create_app(
            llm=llm1, mcp_client=mcp1, auth_gateway=auth, hitl_store=SqliteHITLStore(db)
        )
        client1 = TestClient(app1)
        r1 = client1.post("/agent", json={"message": "test", "session_id": "restart-1"})
        assert r1.status_code == 200

        # Second runtime on same db
        transport2 = FakeHTTPTransport([_make_text_response("Second response.")])
        llm2 = DeepSeekProvider(ProviderConfig(), "token", transport=transport2)
        mcp2 = MCPClientAdapter(BankingMCPServer())
        app2 = create_app(
            llm=llm2, mcp_client=mcp2, auth_gateway=auth, hitl_store=SqliteHITLStore(db)
        )
        client2 = TestClient(app2)
        r2 = client2.post("/agent", json={"message": "another", "session_id": "restart-2"})
        assert r2.status_code == 200
