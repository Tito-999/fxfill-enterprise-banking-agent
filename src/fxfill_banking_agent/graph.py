"""LangGraph state graph for the banking agent.

The graph implements a standard ReAct-style agent loop with
authorization enforcement before every side-effecting tool call.

.. code-block::

    START → agent_node ──(tool calls?)──→ tool_node ──→ agent_node
                │                                        │
                └──(no tool calls)──→ END ←──────────────┘

Authorization (ADR 004):
    The tool_node checks authorization before every tool call. If
    denied, the tool call is skipped and an error ToolMessage is
    appended. If pending, a RuntimeError is raised to signal that
    human approval is needed (handled by the caller).

Dependencies are passed through ``RunnableConfig["configurable"]``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from fxfill_banking_agent.auth import (
    ApprovalDecision,
    AuthorizationGateway,
    AutoApprovePolicy,
    Operation,
    OperationKind,
)
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient, ToolCall
from fxfill_banking_agent.state import AgentState


def _require_deps(
    config: RunnableConfig,
) -> tuple[LLMProvider, MCPClient, AgentConfig, AuthorizationGateway]:
    """Extract required dependencies from runnable config.

    Raises:
        KeyError: If a required dependency is missing.
    """
    cfg = config.get("configurable", {})
    llm: LLMProvider = cfg["llm"]
    mcp: MCPClient = cfg["mcp_client"]
    agent_cfg: AgentConfig = cfg.get("agent_config", AgentConfig())
    auth: AuthorizationGateway = cfg.get(
        "auth_gateway", AuthorizationGateway(policy=AutoApprovePolicy())
    )
    return llm, mcp, agent_cfg, auth


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
    llm, _mcp, agent_cfg, _auth = _require_deps(config)

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
    """Execute pending tool calls through the MCP client.

    Each tool call is authorized before execution (ADR 004).
    Denied calls produce error ToolMessages. Pending calls raise
    RuntimeError so the caller can initiate the HITL workflow.
    """
    _llm, mcp_client, _agent_cfg, auth_gateway = _require_deps(config)

    messages = state.get("messages", [])
    if not messages:
        return {}

    last = messages[-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return {}

    # Track executed tool calls for idempotency
    executed_ids: set[str] = state.get("executed_tool_ids", set())

    results: list[ToolMessage] = []
    for tc in last.tool_calls:
        tool_id = tc.get("id", "")
        tool_name = tc.get("name", "unknown")

        # Idempotency: skip already-executed tool calls
        if tool_id and tool_id in executed_ids:
            results.append(
                ToolMessage(
                    content=f"[idempotent skip] Tool '{tool_name}' already executed",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )
            continue

        # Authorize before execution (ADR 004)
        op = Operation(
            kind=_classify_tool_kind(tool_name),
            name=tool_name,
            target=f"tool:{tool_name}",
            details={"args": tc.get("args", {})},
        )
        decision = await auth_gateway.authorize(op)

        if decision.decision == ApprovalDecision.DENIED:
            results.append(
                ToolMessage(
                    content=f"Authorization denied: {decision.reason}",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )
            continue

        if decision.decision == ApprovalDecision.PENDING:
            # Signal to caller that HITL is required
            raise RuntimeError(
                f"Tool '{tool_name}' requires human approval. "
                f"Run ID: {state.get('session_id', 'unknown')}"
            )

        # Approved — execute the tool call
        call = ToolCall(name=tool_name, arguments=tc.get("args", {}))
        result = await mcp_client.call_tool(call)
        results.append(
            ToolMessage(
                content=result.content if result.success else f"Error: {result.error}",
                tool_call_id=tool_id,
                name=tool_name,
            )
        )

        # Mark as executed for idempotency
        if tool_id:
            executed_ids.add(tool_id)

    return {
        "messages": results,
        "executed_tool_ids": executed_ids,
    }


def _classify_tool_kind(name: str) -> OperationKind:
    """Classify a tool by name into an operation kind."""
    name_lower = name.lower()
    if any(w in name_lower for w in ("transfer", "wire", "send", "pay")):
        return OperationKind.TRANSFER
    if any(w in name_lower for w in ("delete", "remove", "purge", "close")):
        return OperationKind.DELETE
    if any(
        w in name_lower for w in ("update", "modify", "change", "set", "write", "create", "add")
    ):
        return OperationKind.WRITE
    return OperationKind.READ


def build_agent_graph() -> Any:
    """Build the LangGraph state graph for the banking agent.

    The caller must provide through ``RunnableConfig["configurable"]``:

    * ``"llm"`` — LLMProvider
    * ``"mcp_client"`` — MCPClient
    * ``"agent_config"`` — AgentConfig (optional, defaults used)
    * ``"auth_gateway"`` — AuthorizationGateway (optional, auto-approve used)

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
