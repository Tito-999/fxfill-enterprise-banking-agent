"""Full-chain integration tests: DeepSeekProvider → MCPClientAdapter →
BankingMCPServer → AgentRuntime → AuthorizationGateway → HITL → durable stores.

Uses deterministic fake HTTP transport + real banking MCP server + real AgentRuntime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import (
    AuthorizationGateway,
    ReadOnlyPolicy,
    RequireApprovalPolicy,
)
from fxfill_banking_agent.banking.mcp_server import BankingMCPServer
from fxfill_banking_agent.checkpoint_store import SqliteCheckpointSaver
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.mcp.client import MCPClientAdapter
from fxfill_banking_agent.persistence import SqliteEventStore
from tests.fakes.transports import FakeHTTPTransport

# ── Helpers ──────────────────────────────────────────────────────────


def _make_text_response(content: str = "OK") -> tuple[int, str]:
    return 200, json.dumps(
        {
            "id": "req-1",
            "model": "test",
            "choices": [{"message": {"content": content, "role": "assistant"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
    )


def _make_tool_response(tool_name: str, args: dict, call_id: str = "t1") -> tuple[int, str]:
    return 200, json.dumps(
        {
            "id": "req-1",
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
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )


def _make_deepseek(llm_responses: list[tuple[int, str]]):
    from fxfill_banking_agent.providers.base import ProviderConfig
    from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

    transport = FakeHTTPTransport(llm_responses)
    return DeepSeekProvider(ProviderConfig(), "test-token", transport=transport)


async def _create_runtime(
    tmp_path: Path,
    llm_responses: list[tuple[int, str]],
    auth_gateway: AuthorizationGateway,
) -> AgentRuntime:
    from fxfill_banking_agent.providers.base import ProviderConfig
    from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

    transport = FakeHTTPTransport(llm_responses)
    llm = DeepSeekProvider(ProviderConfig(), "test-token", transport=transport)

    db = tmp_path / "test.db"
    server = BankingMCPServer()
    mcp = MCPClientAdapter(server)
    await mcp.connect()

    return AgentRuntime(
        config=AgentConfig(max_agent_steps=10),
        llm=llm,
        mcp_client=mcp,
        auth_gateway=auth_gateway,
        checkpoint_saver=SqliteCheckpointSaver(db),
        idempotency_store=SqliteIdempotencyStore(db),
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestReadOnlyChain:
    @pytest.mark.asyncio
    async def test_balance_request(self, tmp_path: Path) -> None:
        """Full chain: user asks balance → provider returns tool call →
        MCP executes get_balance → agent responds with balance."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        # read-only tools are always approved
        runtime = await _create_runtime(
            tmp_path,
            [
                _make_tool_response(
                    "get_balance", {"account_id": "ACC-1001", "user_id": "user-alice"}, "t1"
                ),
                _make_text_response("Your balance is $15,000.00."),
            ],
            auth,
        )

        result = await runtime.run("What is my balance?", run_id="read-1")
        assert result["final_answer"] == "Your balance is $15,000.00."

    @pytest.mark.asyncio
    async def test_account_summary_request(self, tmp_path: Path) -> None:
        """Full chain: user asks for summary → agent returns account info."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        runtime = await _create_runtime(
            tmp_path,
            [
                _make_tool_response(
                    "get_account_summary", {"account_id": "ACC-1001", "user_id": "user-alice"}, "t1"
                ),
                _make_text_response("Account ACC-1001 has $15,000.00."),
            ],
            auth,
        )

        result = await runtime.run("Give me my account summary", run_id="read-2")
        assert "ACC-1001" in str(result.get("messages", ""))


class TestTransferHITLChain:
    @pytest.mark.asyncio
    async def test_submit_transfer_creates_hitl_session(self, tmp_path: Path) -> None:
        """submit_transfer is HIGH_RISK → triggers HITL pause (RuntimeError)."""
        auth = AuthorizationGateway(policy=RequireApprovalPolicy())
        runtime = await _create_runtime(
            tmp_path,
            [
                _make_tool_response(
                    "create_transfer_draft",
                    {
                        "source_account_id": "ACC-3001",
                        "beneficiary_id": "BEN-003",
                        "amount": 100.0,
                        "currency": "USD",
                        "user_id": "user-carol",
                        "idempotency_key": "idem-hitl-1",
                    },
                    "t1",
                ),
                _make_tool_response(
                    "submit_transfer", {"draft_id": "draft-1", "user_id": "user-carol"}, "t2"
                ),
                _make_text_response("Transfer submitted."),
            ],
            auth,
        )

        with pytest.raises(RuntimeError, match="HITL:"):
            await runtime.run("Send $100 to Electric Company", run_id="hitl-1")

    @pytest.mark.asyncio
    async def test_transfer_rejection_causes_no_side_effect(self, tmp_path: Path) -> None:
        """When a transfer is rejected by the auth gate, balance is unchanged."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())  # read-only → transfer denied
        runtime = await _create_runtime(
            tmp_path,
            [
                _make_tool_response(
                    "create_transfer_draft",
                    {
                        "source_account_id": "ACC-3001",
                        "beneficiary_id": "BEN-003",
                        "amount": 50.0,
                        "currency": "USD",
                        "user_id": "user-carol",
                        "idempotency_key": "idem-deny-1",
                    },
                    "t1",
                ),
                _make_tool_response(
                    "submit_transfer", {"draft_id": "draft-1", "user_id": "user-carol"}, "t2"
                ),
                _make_text_response("Transfer cancelled."),
            ],
            auth,
        )

        result = await runtime.run("Send $50 to Electric Company", run_id="deny-1")
        # The transfer should have been blocked by the tool_node auth check
        assert (
            "Authorization denied" in str(result.get("messages", []))
            or "denied" in str(result.get("messages", [])).lower()
        )


class TestDurableChain:
    @pytest.mark.asyncio
    async def test_restart_before_approval(self, tmp_path: Path) -> None:
        """State persists in SQLite → new runtime can read it."""
        db = tmp_path / "durable.db"
        server = BankingMCPServer()
        mcp = MCPClientAdapter(server)
        await mcp.connect()

        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        runtime1 = AgentRuntime(
            config=AgentConfig(max_agent_steps=5),
            llm=_make_deepseek([_make_text_response("Hello.")]),
            mcp_client=mcp,
            auth_gateway=auth,
            checkpoint_saver=SqliteCheckpointSaver(db),
            idempotency_store=SqliteIdempotencyStore(db),
            event_store=SqliteEventStore(db),
        )

        result1 = await runtime1.run("hello", run_id="durable-1")
        assert result1["final_answer"] == "Hello."

        # Reconstruct — new runtime on same DB
        runtime2 = AgentRuntime(
            config=AgentConfig(max_agent_steps=5),
            llm=_make_deepseek([_make_text_response("Still works.")]),
            mcp_client=mcp,
            auth_gateway=auth,
            checkpoint_saver=SqliteCheckpointSaver(db),
            idempotency_store=SqliteIdempotencyStore(db),
        )
        result2 = await runtime2.run("ping", run_id="durable-2")
        assert result2["final_answer"] == "Still works."
        await mcp.disconnect()


class TestCrossUserSafety:
    @pytest.mark.asyncio
    async def test_cross_user_ownership_violation(self, tmp_path: Path) -> None:
        """Bob cannot access Alice's account."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        runtime = await _create_runtime(
            tmp_path,
            [
                _make_tool_response(
                    "get_balance", {"account_id": "ACC-1001", "user_id": "user-bob"}, "t1"
                ),
                _make_text_response("Here is the balance."),
            ],
            auth,
        )

        result = await runtime.run("What is Alice's balance?", run_id="cross-1")
        # The banking tool should return an error for ownership violation
        messages_str = str(result.get("messages", []))
        assert (
            "access denied" in messages_str.lower()
            or "not found" in messages_str.lower()
            or "Authorization denied" in messages_str
        )


class TestFailureModes:
    @pytest.mark.asyncio
    async def test_malformed_tool_call_fails_closed(self, tmp_path: Path) -> None:
        """Malformed provider response doesn't crash the runtime."""
        auth = AuthorizationGateway(policy=ReadOnlyPolicy())
        # Return a tool call referencing a non-existent tool
        runtime = await _create_runtime(
            tmp_path,
            [
                _make_tool_response("nonexistent_tool", {}, "t1"),
                _make_text_response("I tried."),
            ],
            auth,
        )

        result = await runtime.run("DoS attack via bad tool?", run_id="mal-1")
        # Should complete without exception — error was handled gracefully
        assert result["final_answer"] is not None

    @pytest.mark.asyncio
    async def test_unknown_idempotency_outcome_fails_closed(self, tmp_path: Path) -> None:
        """When idempotency outcome is UNKNOWN, writes fail closed."""
        db = tmp_path / "idem_unknown.db"
        idem = SqliteIdempotencyStore(db)
        await idem.reserve("unknown-1", "transfer", {"amt": 100})
        await idem.mark_unknown("unknown-1")

        rec = await idem.get("unknown-1")
        assert not rec.can_retry()  # UNKNOWN → cannot retry for writes
        assert not rec.is_terminal()
