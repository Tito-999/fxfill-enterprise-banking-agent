"""Tests for the LangGraph agent graph."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.graph import _agent_node, _has_tool_calls, _tool_node, build_agent_graph
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient, ToolResult
from fxfill_banking_agent.state import AgentState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(llm: MockLLM, mcp: StubMCPClient, agent_cfg: AgentConfig | None = None) -> RunnableConfig:
    return RunnableConfig(
        configurable={
            "llm": llm,
            "mcp_client": mcp,
            "agent_config": agent_cfg or AgentConfig(max_agent_steps=10),
        }
    )


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------


class TestGraphTopology:
    def test_graph_compiles(self) -> None:
        graph = build_agent_graph()
        assert graph is not None

    def test_nodes_present(self) -> None:
        graph = build_agent_graph()
        nodes = graph.get_graph().nodes
        node_names = {n for n in nodes}
        assert "agent_node" in node_names
        assert "tool_node" in node_names
        assert "__start__" in node_names
        assert "__end__" in node_names


class TestRouting:
    def test_has_tool_calls_true(self) -> None:
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "lookup", "args": {}, "id": "c1"}],
        )
        state: AgentState = {"messages": [msg]}
        assert _has_tool_calls(state) == "tool_node"

    def test_has_tool_calls_false(self) -> None:
        msg = AIMessage(content="All done!")
        state: AgentState = {"messages": [msg]}
        assert _has_tool_calls(state) == "__end__"

    def test_empty_messages_ends(self) -> None:
        state: AgentState = {"messages": []}
        assert _has_tool_calls(state) == "__end__"


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


class TestAgentNode:
    @pytest.mark.asyncio
    async def test_returns_final_answer(self) -> None:
        llm = MockLLM([AIMessage(content="Your balance is $100.")])
        state: AgentState = {"messages": [HumanMessage(content="balance?")]}

        result = await _agent_node(state, _cfg(llm, StubMCPClient()))
        assert result["final_answer"] == "Your balance is $100."
        assert result["step_count"] == 1
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_increments_step_count(self) -> None:
        llm = MockLLM([AIMessage(content="ok")])
        state: AgentState = {
            "messages": [HumanMessage(content="hi")],
            "step_count": 5,
        }

        result = await _agent_node(state, _cfg(llm, StubMCPClient()))
        assert result["step_count"] == 6

    @pytest.mark.asyncio
    async def test_exceeds_step_limit(self) -> None:
        llm = MockLLM([AIMessage(content="x")])
        state: AgentState = {
            "messages": [HumanMessage(content="hi")],
            "step_count": 3,
        }

        with pytest.raises(RuntimeError, match="max_agent_steps"):
            await _agent_node(state, _cfg(llm, StubMCPClient(), AgentConfig(max_agent_steps=3)))


# ---------------------------------------------------------------------------
# Tool node
# ---------------------------------------------------------------------------


class TestToolNode:
    @pytest.mark.asyncio
    async def test_executes_tool_calls(self) -> None:
        client = StubMCPClient(tools={"get_balance": ToolResult("get_balance", True, "$500.00")})
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_balance", "args": {"account": "1234"}, "id": "tc1"}],
        )
        state: AgentState = {"messages": [HumanMessage(content="balance?"), msg]}

        result = await _tool_node(state, _cfg(MockLLM(), client))
        assert len(result["messages"]) == 1
        tool_msg = result["messages"][0]
        assert isinstance(tool_msg, ToolMessage)
        assert tool_msg.content == "$500.00"

    @pytest.mark.asyncio
    async def test_no_tool_calls_noop(self) -> None:
        state: AgentState = {"messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}

        result = await _tool_node(state, _cfg(MockLLM(), StubMCPClient()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_state_noop(self) -> None:
        state: AgentState = {"messages": []}
        result = await _tool_node(state, _cfg(MockLLM(), StubMCPClient()))
        assert result == {}


# ---------------------------------------------------------------------------
# End-to-end graph
# ---------------------------------------------------------------------------


class TestEndToEndGraph:
    @pytest.mark.asyncio
    async def test_simple_no_tools(self) -> None:
        """Agent responds without tool calls → single invocation, final answer."""
        graph = build_agent_graph()
        llm = MockLLM([AIMessage(content="Hello! How can I help?")])
        state: AgentState = {"messages": [HumanMessage(content="hi")]}

        result = await graph.ainvoke(state, config=_cfg(llm, StubMCPClient()))

        assert result["final_answer"] == "Hello! How can I help?"
        assert result["step_count"] == 1
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_single_tool_call(self) -> None:
        """Agent calls one tool, then finishes."""
        graph = build_agent_graph()
        llm = MockLLM(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "get_balance", "args": {"account": "A1"}, "id": "tc1"}],
                ),
                AIMessage(content="Your balance is $100."),
            ]
        )
        client = StubMCPClient(tools={"get_balance": ToolResult("get_balance", True, "$100.00")})
        state: AgentState = {"messages": [HumanMessage(content="balance?")]}

        result = await graph.ainvoke(state, config=_cfg(llm, client))

        assert result["final_answer"] == "Your balance is $100."
        assert llm.call_count == 2
        assert len(client.calls) == 1
        assert client.calls[0].name == "get_balance"

    @pytest.mark.asyncio
    async def test_step_limit_enforced_by_graph(self) -> None:
        """Graph aborts when the agent exceeds max steps."""
        graph = build_agent_graph()

        responses = []
        for i in range(20):
            responses.append(
                AIMessage(
                    content="",
                    tool_calls=[{"name": "ping", "args": {}, "id": f"tc{i}"}],
                )
            )
        llm = MockLLM(responses)
        client = StubMCPClient(tools={"ping": [ToolResult("ping", True, "pong")] * 20})
        cfg = AgentConfig(max_agent_steps=5)
        state: AgentState = {"messages": [HumanMessage(content="start")]}

        with pytest.raises(RuntimeError, match="max_agent_steps"):
            await graph.ainvoke(state, config=_cfg(llm, client, cfg))

    @pytest.mark.asyncio
    async def test_multi_tool_call_in_one_turn(self) -> None:
        """Agent calls multiple tools in a single response."""
        graph = build_agent_graph()
        llm = MockLLM(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "lookup_account", "args": {"id": "A1"}, "id": "tc1"},
                        {"name": "lookup_account", "args": {"id": "A2"}, "id": "tc2"},
                    ],
                ),
                AIMessage(content="Found both accounts."),
            ]
        )
        client = StubMCPClient(
            tools={
                "lookup_account": [
                    ToolResult("lookup_account", True, "Account A1: checking"),
                    ToolResult("lookup_account", True, "Account A2: savings"),
                ]
            }
        )
        state: AgentState = {"messages": [HumanMessage(content="list accounts")]}

        result = await graph.ainvoke(state, config=_cfg(llm, client))

        assert result["final_answer"] == "Found both accounts."
        assert len(client.calls) == 2
        assert client.calls[0].arguments == {"id": "A1"}
        assert client.calls[1].arguments == {"id": "A2"}
