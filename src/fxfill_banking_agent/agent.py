"""Wired agent runtime — composes graph, persistence, metrics, and logging.

This is the main entry point for running the banking agent in any
environment (development, test, or production).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.graph import build_agent_graph
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.metrics import InMemoryMetricsCollector, MetricsCollector
from fxfill_banking_agent.persistence import AgentEvent, EventKind, EventStore
from fxfill_banking_agent.state import AgentState

logger = get_logger(__name__)


class AgentRuntime:
    """Composed agent runtime with graph, persistence, metrics, and logging.

    Attributes:
        config: Agent configuration.
        llm: LLM provider.
        mcp_client: MCP client for tool execution.
        event_store: Persistent event storage (optional).
        metrics_collector: Per-step metrics collector.
        auth_gateway: Authorization gateway for tool calls.
        checkpoint_saver: LangGraph checkpoint backend.
    """

    def __init__(
        self,
        *,
        config: AgentConfig | None = None,
        llm: LLMProvider,
        mcp_client: MCPClient,
        event_store: EventStore | None = None,
        metrics_collector: MetricsCollector | None = None,
        auth_gateway: AuthorizationGateway | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.llm = llm
        self.mcp_client = mcp_client
        self.event_store = event_store
        self.metrics_collector = metrics_collector or InMemoryMetricsCollector()
        self.auth_gateway = auth_gateway or AuthorizationGateway(policy=AutoApprovePolicy())

        # In-memory checkpoint for now; Phase 3+ can use SqliteSaver
        self.checkpoint_saver = MemorySaver()

        self._graph = build_agent_graph()

    async def _persist_event(
        self, run_id: str, seq: int, kind: EventKind, payload: dict[str, object]
    ) -> None:
        """Persist an event if an event store is configured."""
        if self.event_store is None:
            return
        try:
            await self.event_store.insert(
                AgentEvent(run_id=run_id, seq=seq, kind=kind, payload=payload)
            )
        except Exception:
            logger.warning("event_persist_failed", run_id=run_id, seq=seq, kind=kind.value)

    async def run(
        self,
        user_message: str,
        *,
        run_id: str | None = None,
        thread_id: str | None = None,
        resume_from_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the agent with a user message and return the final state.

        Args:
            user_message: The user's natural-language request.
            run_id: Opaque run identifier (auto-generated if omitted).
            thread_id: LangGraph thread identifier for multi-turn
                conversations (auto-generated if omitted).
            resume_from_state: If provided, resume execution from this
                state (used for HITL resume after approval).

        Returns:
            The final agent state dict.
        """
        run_id = run_id or str(uuid.uuid4())
        thread_id = thread_id or run_id
        logger.info("agent_run_start", run_id=run_id, thread_id=thread_id)

        self.metrics_collector.start_run(run_id)

        if resume_from_state:
            state: AgentState = {
                "messages": resume_from_state.get("messages", []),
                "session_id": run_id,
                "step_count": resume_from_state.get("step_count", 0),
                "final_answer": resume_from_state.get("final_answer"),
                "executed_tool_ids": resume_from_state.get("executed_tool_ids", set()),
                "pending_approvals": resume_from_state.get("pending_approvals", []),
            }
            seq = state.get("step_count", 0)
        else:
            state = {
                "messages": [HumanMessage(content=user_message)],
                "session_id": run_id,
                "step_count": 0,
                "final_answer": None,
                "executed_tool_ids": set(),
                "pending_approvals": [],
            }
            seq = 0
            await self._persist_event(
                run_id, seq, EventKind.USER_MESSAGE, {"content": user_message}
            )

        t0 = time.monotonic()
        try:
            result = await self._graph.ainvoke(
                state,
                config={
                    "configurable": {
                        "llm": self.llm,
                        "mcp_client": self.mcp_client,
                        "agent_config": self.config,
                        "auth_gateway": self.auth_gateway,
                        "thread_id": thread_id,
                        "run_id": run_id,
                    },
                },
            )
        except RuntimeError as exc:
            # HITL pause — persist state and re-raise for caller
            logger.info("agent_run_paused_for_approval", run_id=run_id, error=str(exc))
            await self._persist_event(
                run_id,
                state.get("step_count", 0) + 1,
                EventKind.CHECKPOINT,
                {"state": {"step_count": state.get("step_count", 0), "session_id": run_id}},
            )
            raise

        elapsed_ms = (time.monotonic() - t0) * 1000

        await self._persist_event(
            run_id,
            state.get("step_count", 0) + 1,
            EventKind.AGENT_MESSAGE,
            {"final_answer": result.get("final_answer")},
        )

        run_metrics = self.metrics_collector.finish_run()
        logger.info(
            "agent_run_complete",
            run_id=run_id,
            steps=len(run_metrics.steps),
            duration_ms=round(elapsed_ms, 1),
            total_tokens=run_metrics.total_input_tokens + run_metrics.total_output_tokens,
        )

        return result  # type: ignore[no-any-return]
