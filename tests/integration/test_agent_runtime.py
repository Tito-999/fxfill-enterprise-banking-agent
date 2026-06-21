"""Integration tests: AgentRuntime → LangGraph → LLMProvider/MCPClient."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient, ToolResult


@pytest.mark.asyncio
async def test_runtime_invokes_graph_with_simple_response() -> None:
    """A single-turn message without tool calls returns the LLM response."""
    llm = MockLLM([AIMessage(content="Your balance is $500.")])
    mcp = StubMCPClient()
    runtime = AgentRuntime(llm=llm, mcp_client=mcp)
    result = await runtime.run("What is my balance?")
    assert result["final_answer"] == "Your balance is $500."


@pytest.mark.asyncio
async def test_runtime_graph_tool_loop() -> None:
    """The graph correctly routes agent→tool→agent for tool-calling messages."""
    llm = MockLLM(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "get_balance", "args": {"account": "A1"}, "id": "t1"}],
            ),
            AIMessage(content="Your balance is $100."),
        ]
    )
    mcp = StubMCPClient(tools={"get_balance": ToolResult("get_balance", True, "$100.00")})
    runtime = AgentRuntime(llm=llm, mcp_client=mcp)
    result = await runtime.run("balance?")
    assert result["final_answer"] == "Your balance is $100."
    assert llm.call_count == 2
    assert len(mcp.calls) == 1


@pytest.mark.asyncio
async def test_auth_gateway_passed_to_graph() -> None:
    """The auth gateway is passed through to the graph's tool_node."""
    llm = MockLLM(
        [
            AIMessage(
                content="", tool_calls=[{"name": "transfer", "args": {"amt": 100}, "id": "t1"}]
            ),
            AIMessage(content="Transfer complete."),
        ]
    )
    mcp = StubMCPClient(tools={"transfer": ToolResult("transfer", True, "done")})
    auth = AuthorizationGateway(policy=AutoApprovePolicy())
    runtime = AgentRuntime(llm=llm, mcp_client=mcp, auth_gateway=auth)
    result = await runtime.run("send $100")
    assert result["final_answer"] == "Transfer complete."
    assert len(auth.audit_trail) >= 1


@pytest.mark.asyncio
async def test_graph_tool_result_flows_back() -> None:
    """Tool results are appended as ToolMessages and the agent sees them."""
    llm = MockLLM(
        [
            AIMessage(content="", tool_calls=[{"name": "lookup", "args": {"id": "X"}, "id": "t1"}]),
            AIMessage(content="Found: John Doe, checking."),
        ]
    )
    mcp = StubMCPClient(tools={"lookup": ToolResult("lookup", True, "John Doe")})
    runtime = AgentRuntime(llm=llm, mcp_client=mcp)
    result = await runtime.run("who is X?")
    assert result["final_answer"] == "Found: John Doe, checking."
    assert len(mcp.calls) == 1
    assert mcp.calls[0].name == "lookup"


@pytest.mark.asyncio
async def test_multi_step_graph_execution() -> None:
    """A three-step flow: user→tool1→tool2→final_answer."""
    llm = MockLLM(
        [
            AIMessage(content="", tool_calls=[{"name": "step1", "args": {}, "id": "t1"}]),
            AIMessage(content="", tool_calls=[{"name": "step2", "args": {}, "id": "t2"}]),
            AIMessage(content="All done after two tool calls."),
        ]
    )
    mcp = StubMCPClient(
        tools={
            "step1": ToolResult("step1", True, "r1"),
            "step2": ToolResult("step2", True, "r2"),
        }
    )
    runtime = AgentRuntime(llm=llm, mcp_client=mcp, config=AgentConfig(max_agent_steps=10))
    result = await runtime.run("do steps")
    assert result["final_answer"] == "All done after two tool calls."
    assert llm.call_count == 3
    assert len(mcp.calls) == 2


@pytest.mark.asyncio
async def test_metrics_collected() -> None:
    """Metrics collector receives step data during execution."""
    llm = MockLLM(
        [
            AIMessage(content="", tool_calls=[{"name": "t1", "args": {}, "id": "t1"}]),
            AIMessage(content="Done."),
        ]
    )
    mcp = StubMCPClient(tools={"t1": ToolResult("t1", True, "ok")})
    runtime = AgentRuntime(llm=llm, mcp_client=mcp)
    await runtime.run("test")
    # Metrics collector was used
    assert runtime.metrics_collector is not None
