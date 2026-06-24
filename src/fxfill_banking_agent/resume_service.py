"""HITL resume service — feeds approved tool results back into the agent graph.

After the HITL executor dispatches an approved tool and collects the
result, this service resumes the LangGraph so the model can see the
ToolMessage, verify the outcome, and generate a final grounded answer.

Without resume, the model never sees the tool result — it only gets a
raw MCP output returned directly from the approval API.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from fxfill_banking_agent.approval_executor import ApprovalResult
from fxfill_banking_agent.hitl_store import SqliteHITLStore
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.metrics import MetricsCollector

logger = get_logger(__name__)


class GraphResumeService:
    """Resumes the agent graph after HITL approval so the model can respond.

    After the approval executor runs the tool, this service:
    1. Creates a ToolMessage with the tool result
    2. Invokes the graph with the ToolMessage appended
    3. Lets the model generate a final grounded answer
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        mcp_client: MCPClient,
        hitl_store: SqliteHITLStore,
        metrics_collector: MetricsCollector | None = None,
    ) -> None:
        from fxfill_banking_agent.graph import build_agent_graph

        self._llm = llm
        self._mcp = mcp_client
        self._hitl = hitl_store
        self._metrics = metrics_collector
        self._graph = build_agent_graph()

    async def build_resume_state(
        self,
        approval_result: ApprovalResult,
    ) -> dict[str, Any] | None:
        """Build the state needed to resume the graph after approval.

        Returns None if the result doesn't support resume (e.g. rejected,
        reconciliation required).

        The returned state includes the ToolMessage with the execution
        result so the model can see what happened and respond.
        """
        if approval_result.decision not in ("approved", "rejected"):
            return None

        session = await self._hitl.get(approval_result.session_id)
        if session is None:
            return None

        # Build the tool result message
        if approval_result.decision == "approved":
            tool_content = (
                f"Tool '{session.tool_name}' executed successfully.\n"
                f"Result: {approval_result.answer or 'done'}"
            )
        else:
            tool_content = (
                f"Tool '{session.tool_name}' was rejected by human operator.\n"
                f"Reason: {approval_result.answer or 'Operation rejected'}"
            )

        tool_msg = ToolMessage(
            content=tool_content,
            tool_call_id=session.tool_call_id,
            name=session.tool_name,
        )

        return {
            "messages": [tool_msg],
            "session_id": approval_result.session_id,
            "step_count": 0,
            "final_answer": None,
            "executed_tool_ids": {session.tool_call_id} if session.tool_call_id else set(),
            "pending_approvals": [],
        }

    async def resume_and_respond(
        self,
        resume_state: dict[str, Any],
        *,
        thread_id: str,
        run_id: str,
    ) -> str | None:
        """Resume the graph and let the model generate a final answer.

        Args:
            resume_state: State built by ``build_resume_state``.
            thread_id: Thread identifier for checkpointing.
            run_id: Run identifier for tracing.

        Returns:
            The model's final answer string, or None if generation failed.
        """
        from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
        from fxfill_banking_agent.config import AgentConfig

        try:
            result = await self._graph.ainvoke(
                resume_state,
                config={
                    "configurable": {
                        "llm": self._llm,
                        "mcp_client": self._mcp,
                        "agent_config": AgentConfig(max_agent_steps=5),
                        "auth_gateway": AuthorizationGateway(policy=AutoApprovePolicy()),
                        "idempotency_store": None,
                        "tool_registry": None,
                        "thread_id": thread_id,
                        "run_id": run_id,
                    },
                },
            )

            final_answer = result.get("final_answer")
            if final_answer:
                return str(final_answer)

            # Fallback: use last AI message content
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return str(msg.content)

            return None

        except Exception as exc:
            logger.error("resume_graph_failed", run_id=run_id, error=str(exc))
            return None
