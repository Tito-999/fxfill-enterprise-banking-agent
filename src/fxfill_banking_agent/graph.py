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
from langgraph.types import interrupt

from fxfill_banking_agent.auth import (
    ApprovalDecision,
    AuthorizationGateway,
    Operation,
    OperationKind,
)
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.idempotency_store import IdempotencyStore
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient, ToolCall
from fxfill_banking_agent.state import AgentState
from fxfill_banking_agent.tools.registry import ToolRegistry
from fxfill_banking_agent.tools.validation import validate_tool_call


def _require_deps(
    config: RunnableConfig,
) -> tuple[
    LLMProvider,
    MCPClient,
    AgentConfig,
    AuthorizationGateway,
    IdempotencyStore | None,
    ToolRegistry | None,
]:
    """Extract required dependencies from runnable config."""
    cfg = config.get("configurable", {})
    llm: LLMProvider = cfg["llm"]
    mcp: MCPClient = cfg["mcp_client"]
    agent_cfg: AgentConfig = cfg.get("agent_config", AgentConfig())
    auth_raw = cfg.get("auth_gateway")
    if auth_raw is None:
        raise RuntimeError(
            "graph requires an explicit AuthorizationGateway in configurable — refusing to fail open"
        )
    auth: AuthorizationGateway = auth_raw
    idem: IdempotencyStore | None = cfg.get("idempotency_store")
    tool_registry: ToolRegistry | None = cfg.get("tool_registry")
    return llm, mcp, agent_cfg, auth, idem, tool_registry


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
    import time as _time

    llm, _mcp, agent_cfg, _auth, _idem, tool_registry = _require_deps(config)

    step = state.get("step_count", 0)
    if step >= agent_cfg.max_agent_steps:
        raise RuntimeError(f"Agent exceeded max_agent_steps ({agent_cfg.max_agent_steps})")

    messages = state.get("messages", [])

    # Build tools list from registry if available
    tools: list[dict[str, Any]] | None = None
    if tool_registry is not None and tool_registry.count > 0:
        tools = tool_registry.provider_definitions(include_server_fields=False)

    t0 = _time.monotonic()
    response = await llm.invoke(list(messages), tools=tools, tool_choice="auto")
    llm_duration_ms = (_time.monotonic() - t0) * 1000

    # Per-step metrics (P0-07)
    _record_step_metrics(config, step, llm_duration_ms, input_tokens=0, output_tokens=0)

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

    Each tool call is validated, authorized, and then executed.
    Validation uses the ToolRegistry if available; falls back to
    basic name checking if no registry is configured.

    Denied calls produce error ToolMessages. Pending calls raise
    RuntimeError so the caller can initiate the HITL workflow.
    """
    _llm, mcp_client, _agent_cfg, auth_gateway, idem_store, tool_registry = _require_deps(config)

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

        # ── Step 1: Validate tool call against registry ───────────
        if tool_registry is not None:
            validation = validate_tool_call(tool_name, tc.get("args", {}), tool_registry)
            if not validation.valid:
                results.append(
                    ToolMessage(
                        content=f"Tool call rejected: {validation.error}",
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
                continue

        # ── Step 2: Idempotency — skip already-executed ────────────
        if tool_id and tool_id in executed_ids:
            results.append(
                ToolMessage(
                    content=f"[idempotent skip] Tool '{tool_name}' already executed",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )
            continue

        # ── Step 3: Classify operation kind from registry metadata ─
        op_kind = _classify_tool_kind(tool_name)
        if tool_registry is not None:
            td = tool_registry.get(tool_name)
            if td is not None:
                op_kind = _kind_from_metadata(td)

        # ── Step 4: Authorize before execution (ADR 004) ──────────
        op = Operation(
            kind=op_kind,
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
            # Durable graph interrupt — suspends execution until
            # the caller resumes with Command(resume=...).
            # On resume, the returned value contains the approval decision.
            sid = state.get("session_id") or "unknown"
            approval = interrupt(
                {
                    "tool_name": tool_name,
                    "tool_args": tc.get("args", {}),
                    "tool_call_id": tool_id,
                    "session_id": sid,
                    "thread_id": sid,
                    "idempotency_key": f"{sid}:{tool_id}",
                }
            )
            # On resume: approval contains the resume value from Command(resume=...)
            # Expected shape: {"decision": "approved"/"rejected", "canonical_args": {...}, ...}
            if isinstance(approval, dict) and approval.get("decision") == "approved":
                # Use canonical args from the grant, not model-generated args
                if "canonical_args" in approval:
                    tc["args"] = approval["canonical_args"]
                # Continue to execution below
            elif isinstance(approval, dict) and approval.get("decision") == "rejected":
                results.append(
                    ToolMessage(
                        content=f"Operation rejected: {approval.get('reason', 'Human operator declined')}",
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
                if tool_id:
                    executed_ids.add(tool_id)
                continue
            else:
                # Unknown resume value — fail closed
                results.append(
                    ToolMessage(
                        content=f"Error: invalid approval response for '{tool_name}'",
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
                if tool_id:
                    executed_ids.add(tool_id)
                continue

        # ── Step 5: Approved — check durable idempotency ──────────
        idem_key = f"{state.get('session_id', 'unknown')}:{tool_id}" if tool_id else None
        tool_already_done = False

        if idem_key and idem_store is not None:
            existing = await idem_store.get(idem_key)
            if existing is not None:
                if existing.status.value in ("SUCCEEDED",):
                    results.append(
                        ToolMessage(
                            content=f"[idempotent] {existing.result or 'done'}",
                            tool_call_id=tool_id,
                            name=tool_name,
                        )
                    )
                    tool_already_done = True
                elif existing.status.value in ("FAILED", "RESERVED"):
                    await idem_store.mark_executing(idem_key)
                elif existing.status.value in ("EXECUTING", "UNKNOWN"):
                    if op_kind != OperationKind.READ:
                        results.append(
                            ToolMessage(
                                content=f"Error: prior outcome unknown for '{tool_name}'. Manual review required.",
                                tool_call_id=tool_id,
                                name=tool_name,
                            )
                        )
                        tool_already_done = True

        if not tool_already_done:
            if idem_key and idem_store is not None:
                existing = await idem_store.get(idem_key)
                if existing is None:
                    await idem_store.reserve(idem_key, tool_name, tc.get("args", {}))

            call = ToolCall(name=tool_name, arguments=tc.get("args", {}))
            result = await mcp_client.call_tool(call)

            if idem_key and idem_store is not None:
                if result.success:
                    await idem_store.mark_succeeded(idem_key, result.content)
                else:
                    await idem_store.mark_failed(idem_key, result.error or "unknown error")

            results.append(
                ToolMessage(
                    content=result.content if result.success else f"Error: {result.error}",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )

        # Mark as executed for in-memory idempotency
        if tool_id:
            executed_ids.add(tool_id)

    return {
        "messages": results,
        "executed_tool_ids": executed_ids,
    }


def _classify_tool_kind(name: str) -> OperationKind:
    """Classify a tool by name into an operation kind (fallback when no registry metadata)."""
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


def _kind_from_metadata(tool_definition: Any) -> OperationKind:
    """Derive OperationKind from explicit tool metadata (preferred over name matching)."""
    if tool_definition.side_effect:
        risk = tool_definition.risk_level
        if risk == "critical":
            return OperationKind.TRANSFER
        return OperationKind.WRITE
    return OperationKind.READ


def build_agent_graph(*, checkpointer: Any = None) -> Any:
    """Build the LangGraph state graph for the banking agent.

    Args:
        checkpointer: Optional LangGraph-compatible checkpointer.
            When provided, the graph will persist and restore state
            across invocations using ``thread_id``.

    The caller must provide through ``RunnableConfig["configurable"]``:

    * ``"llm"`` — LLMProvider
    * ``"mcp_client"`` — MCPClient
    * ``"agent_config"`` — AgentConfig (optional, defaults used)
    * ``"auth_gateway"`` — AuthorizationGateway (optional, auto-approve used)
    * ``"tool_registry"`` — ToolRegistry (optional)
    * ``"idempotency_store"`` — IdempotencyStore (optional)

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

    return builder.compile(checkpointer=checkpointer)


def _record_step_metrics(
    config: RunnableConfig,
    step_index: int,
    duration_ms: float,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    tool_call_count: int = 0,
    tool_duration_ms: float = 0.0,
) -> None:
    """Record per-step metrics if a MetricsCollector is in the config.

    This is a best-effort recording — failures are silently ignored
    so that metrics never break the agent's execution path.
    """
    try:
        metrics_raw = config.get("configurable", {}).get("metrics_collector")
        if metrics_raw is None:
            return
        from fxfill_banking_agent.metrics import StepMetrics

        metrics_raw.record_step(
            StepMetrics(
                step_index=step_index,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                tool_call_count=tool_call_count,
                tool_duration_ms=tool_duration_ms,
            )
        )
    except Exception:
        pass  # Metrics are best-effort — never fail the agent
