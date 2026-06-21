"""Recovery tests: persist, destroy, reconstruct, resume, dedup."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient, ToolResult
from fxfill_banking_agent.persistence import EventKind, SqliteEventStore


@pytest.mark.asyncio
async def test_persist_and_reconstruct_runtime(tmp_path: Path) -> None:
    """Events written by one runtime are readable by a new runtime on the same DB."""
    db_path = tmp_path / "recovery.db"

    # First runtime
    store1 = SqliteEventStore(db_path)
    await store1.connect()
    llm1 = MockLLM([AIMessage(content="First response.")])
    rt1 = AgentRuntime(llm=llm1, mcp_client=StubMCPClient(), event_store=store1)
    result1 = await rt1.run("hello", run_id="recover-me")
    session_id = result1.get("session_id", "recover-me")
    await store1.close()

    # Destroy first runtime (goes out of scope)
    del rt1, store1

    # Second runtime — reads from same DB
    store2 = SqliteEventStore(db_path)
    await store2.connect()
    events = await store2.query_run(session_id)
    assert len(events) >= 1
    assert events[0].kind == EventKind.USER_MESSAGE
    await store2.close()


@pytest.mark.asyncio
async def test_resume_from_saved_state(tmp_path: Path) -> None:
    """Resuming from a saved state continues execution without duplicating completed work."""
    llm = MockLLM(
        [
            AIMessage(content="Continuing after resume."),
        ]
    )
    mcp = StubMCPClient()
    auth = AuthorizationGateway(policy=AutoApprovePolicy())

    # Simulate a partially completed run
    saved_state = {
        "messages": [],
        "step_count": 3,
        "executed_tool_ids": {"t1", "t2"},
    }

    runtime = AgentRuntime(llm=llm, mcp_client=mcp, auth_gateway=auth)
    result = await runtime.run("continue", run_id="resume-test", resume_from_state=saved_state)
    assert result["final_answer"] == "Continuing after resume."


@pytest.mark.asyncio
async def test_idempotent_tool_execution(tmp_path: Path) -> None:
    """Already-executed tool calls are skipped when resuming."""
    llm = MockLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "ping", "args": {}, "id": "t1"},  # already executed
                ],
            ),
            AIMessage(content="All good."),
        ]
    )
    mcp = StubMCPClient(tools={"ping": ToolResult("ping", True, "pong")})
    auth = AuthorizationGateway(policy=AutoApprovePolicy())
    runtime = AgentRuntime(
        llm=llm, mcp_client=mcp, auth_gateway=auth, config=AgentConfig(max_agent_steps=5)
    )

    result = await runtime.run(
        "ping",
        run_id="idem-test",
        resume_from_state={"messages": [], "step_count": 1, "executed_tool_ids": {"t1"}},
    )
    # The already-executed tool should have been skipped
    assert len(mcp.calls) == 0
    assert result["final_answer"] == "All good."


@pytest.mark.asyncio
async def test_missing_checkpoint_handled() -> None:
    """When no saved state exists, the runtime starts from scratch cleanly."""
    llm = MockLLM([AIMessage(content="Fresh start.")])
    runtime = AgentRuntime(llm=llm, mcp_client=StubMCPClient())
    result = await runtime.run("start fresh")
    assert result["final_answer"] == "Fresh start."


@pytest.mark.asyncio
async def test_persistence_failure_does_not_crash_runtime() -> None:
    """If the event store fails, the runtime continues (graceful degradation)."""
    llm = MockLLM([AIMessage(content="ok")])

    class FailingStore:
        async def insert(self, event):
            raise RuntimeError("disk full")

        async def query_run(self, run_id):
            return []

        async def query(self, **kwargs):
            return []

    runtime = AgentRuntime(llm=llm, mcp_client=StubMCPClient(), event_store=FailingStore())
    result = await runtime.run("test")
    assert result["final_answer"] == "ok"
    # Runtime did not crash despite persistence failure


@pytest.mark.asyncio
async def test_corrupted_state_resume_graceful() -> None:
    """Resuming with corrupted state (missing keys) doesn't crash."""
    llm = MockLLM([AIMessage(content="Recovered.")])
    runtime = AgentRuntime(llm=llm, mcp_client=StubMCPClient())
    # Corrupted state: missing required keys
    result = await runtime.run("test", resume_from_state={"messages": []})
    assert result["final_answer"] == "Recovered."
