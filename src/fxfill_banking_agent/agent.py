"""Wired agent runtime — composes graph, persistence, metrics, and logging.

This is the main entry point for running the banking agent in any
environment (development, test, or production).
"""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.graph import build_agent_graph
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.metrics import InMemoryMetricsCollector, MetricsCollector
from fxfill_banking_agent.persistence import EventStore
from fxfill_banking_agent.state import AgentState

logger = get_logger(__name__)


class AgentRuntime:
    """Composed agent runtime with graph, persistence, metrics, and logging.

    Attributes:
        config: Agent configuration.
        llm: LLM provider.
        mcp_client: MCP client for tool execution.
        event_store: Persistent event storage.
        metrics_collector: Per-step metrics collector.
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
    ) -> None:
        self.config = config or AgentConfig()
        self.llm = llm
        self.mcp_client = mcp_client
        self.event_store = event_store
        self.metrics_collector = metrics_collector or InMemoryMetricsCollector()

        # In-memory checkpoint for now; Phase 3+ can use SqliteSaver
        self.checkpoint_saver = MemorySaver()

        self._graph = build_agent_graph()

    async def run(
        self,
        user_message: str,
        *,
        run_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the agent with a user message and return the final state.

        Args:
            user_message: The user's natural-language request.
            run_id: Opaque run identifier (auto-generated if omitted).
            thread_id: LangGraph thread identifier for multi-turn
                conversations (auto-generated if omitted).

        Returns:
            The final agent state dict.
        """
        import time

        from langchain_core.messages import HumanMessage

        run_id = run_id or str(uuid.uuid4())
        thread_id = thread_id or run_id
        logger.info("agent_run_start", run_id=run_id, thread_id=thread_id)

        self.metrics_collector.start_run(run_id)

        state: AgentState = {
            "messages": [HumanMessage(content=user_message)],
            "session_id": run_id,
            "step_count": 0,
            "final_answer": None,
        }

        t0 = time.monotonic()
        result = await self._graph.ainvoke(
            state,
            config={
                "configurable": {
                    "llm": self.llm,
                    "mcp_client": self.mcp_client,
                    "agent_config": self.config,
                    "thread_id": thread_id,
                    "run_id": run_id,
                },
            },
        )
        elapsed_ms = (time.monotonic() - t0) * 1000

        run_metrics = self.metrics_collector.finish_run()
        logger.info(
            "agent_run_complete",
            run_id=run_id,
            steps=len(run_metrics.steps),
            duration_ms=round(elapsed_ms, 1),
            total_tokens=run_metrics.total_input_tokens + run_metrics.total_output_tokens,
        )

        return result  # type: ignore[no-any-return]
