"""LangGraph state graph for the banking agent.

The graph implements a standard ReAct-style agent loop:

.. code-block::

    START → agent_node ──(tool calls?)──→ tool_node ──→ agent_node
                │                                        │
                └──(no tool calls)──→ END ←──────────────┘

Nodes:
    ``agent_node``
        Invokes the LLM with the current conversation. If the LLM
        returns tool calls they are stored in state; otherwise the
        response becomes the final answer.
    ``tool_node``
        Executes pending tool calls through the MCP client and appends
        the results to the conversation.

Dependencies (LLM, MCP client, AgentConfig) are passed through
``RunnableConfig["configurable"]`` so the graph definition stays
declarative and testable.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient, ToolCall
from fxfill_banking_agent.state import AgentState


def _require_deps(config: RunnableConfig) -> tuple[LLMProvider, MCPClient, AgentConfig]:
    """Extract required dependencies from runnable config.

    Raises:
        KeyError: If a required dependency is missing.
    """
    cfg = config.get("configurable", {})
    llm: LLMProvider = cfg["llm"]
    mcp: MCPClient = cfg["mcp_client"]
    agent_cfg: AgentConfig = cfg.get("agent_config", AgentConfig())
    return llm, mcp, agent_cfg


def _has_tool_calls(state: AgentState) -> str:
    """Conditional routing edge: continue or finish.

    Returns:
        ``"tool_node"`` if the last AI message has tool calls,
        ``"__end__"`` otherwise.
    """
    messages = state.get("messages", [])
    if not messages:
        return END
    last = messages[-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tool_node"
    return END


async def _agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Invoke the LLM and return the updated state fragment."""
    llm, _mcp, agent_cfg = _require_deps(config)

    step = state.get("step_count", 0)
    if step >= agent_cfg.max_agent_steps:
        raise RuntimeError(f"Agent exceeded max_agent_steps ({agent_cfg.max_agent_steps})")

    messages = state.get("messages", [])
    response = await llm.invoke(list(messages))

    result: dict[str, Any] = {
        "messages": [response],
        "step_count": step + 1,
    }

    # If no tool calls, treat this as the final answer
    if not (hasattr(response, "tool_calls") and response.tool_calls):
        result["final_answer"] = response.content

    return result


async def _tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Execute pending tool calls through the MCP client."""
    _llm, mcp_client, _agent_cfg = _require_deps(config)

    messages = state.get("messages", [])
    if not messages:
        return {}

    last = messages[-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return {}

    results: list[ToolMessage] = []
    for tc in last.tool_calls:
        call = ToolCall(name=tc["name"], arguments=tc.get("args", {}))
        result = await mcp_client.call_tool(call)
        results.append(
            ToolMessage(
                content=result.content,
                tool_call_id=tc["id"],
                name=tc["name"],
            )
        )

    return {"messages": results}


def build_agent_graph() -> Any:
    """Build the LangGraph state graph for the banking agent.

    The caller must provide the LLM and MCP client through
    ``RunnableConfig["configurable"]`` with keys ``"llm"`` and
    ``"mcp_client"``. An optional ``"agent_config"`` key provides
    an ``AgentConfig`` override.

    Returns:
        A compiled ``StateGraph`` ready for invocation.
    """
    builder = StateGraph(AgentState)

    builder.add_node("agent_node", _agent_node)
    builder.add_node("tool_node", _tool_node)

    builder.set_entry_point("agent_node")

    builder.add_conditional_edges(
        "agent_node",
        _has_tool_calls,
        {"tool_node": "tool_node", END: END},
    )
    builder.add_edge("tool_node", "agent_node")

    return builder.compile()
