"""Wired agent runtime — composes graph, persistence, metrics, and logging."""

from __future__ import annotations

import time
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from fxfill_banking_agent.auth import AuthorizationGateway
from fxfill_banking_agent.checkpoint_store import SqliteCheckpointSaver
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.graph import build_agent_graph
from fxfill_banking_agent.hitl_signal import HITLPending
from fxfill_banking_agent.idempotency_store import IdempotencyStore
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.metrics import InMemoryMetricsCollector, MetricsCollector
from fxfill_banking_agent.persistence import AgentEvent, EventKind, EventStore
from fxfill_banking_agent.state import AgentState

logger = get_logger(__name__)


class AgentRuntime:
    """Composed agent runtime with graph, persistence, metrics, and logging."""

    def __init__(
        self,
        *,
        config: AgentConfig | None = None,
        llm: LLMProvider,
        mcp_client: MCPClient,
        event_store: EventStore | None = None,
        metrics_collector: MetricsCollector | None = None,
        auth_gateway: AuthorizationGateway | None = None,
        checkpoint_saver: Any | None = None,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.llm = llm
        self.mcp_client = mcp_client
        self.event_store = event_store
        self.metrics_collector = metrics_collector or InMemoryMetricsCollector()
        if auth_gateway is None:
            raise RuntimeError(
                "AgentRuntime requires an explicit AuthorizationGateway — refusing to fail open"
            )
        self.auth_gateway = auth_gateway

        # Use durable SQLite checkpoint by default if a db path is configured
        if checkpoint_saver is not None:
            self.checkpoint_saver = checkpoint_saver
        elif self.config.persistence.db_path:
            self.checkpoint_saver = SqliteCheckpointSaver(self.config.persistence.db_path)
        else:
            from langgraph.checkpoint.memory import MemorySaver

            self.checkpoint_saver = MemorySaver()

        self.idempotency_store = idempotency_store

        self._graph = build_agent_graph()

    async def _persist_event(
        self, run_id: str, seq: int, kind: EventKind, payload: dict[str, object]
    ) -> None:
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
                        "idempotency_store": self.idempotency_store,
                        "thread_id": thread_id,
                        "run_id": run_id,
                    },
                },
            )
        except HITLPending:
            await self._persist_event(
                run_id,
                state.get("step_count", 0) + 1,
                EventKind.CHECKPOINT,
                {"state": {"step_count": state.get("step_count", 0), "session_id": run_id}},
            )
            raise
        except RuntimeError as exc:
            logger.error("agent_run_error", run_id=run_id, error=str(exc))
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
