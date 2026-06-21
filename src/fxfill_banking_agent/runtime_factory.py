"""Runtime factory — constructs the agent dependency graph.

Produces: AgentRuntime with all dependencies wired.
Test and production modes have distinct construction paths.
"""

from __future__ import annotations

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import AuthorizationGateway
from fxfill_banking_agent.checkpoint_store import SqliteCheckpointSaver
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.metrics import InMemoryMetricsCollector
from fxfill_banking_agent.persistence import EventStore, SqliteEventStore


async def create_runtime(
    *,
    config: AgentConfig,
    llm: LLMProvider,
    mcp_client: MCPClient,
    auth_gateway: AuthorizationGateway | None = None,
    event_store: EventStore | None = None,
) -> AgentRuntime:
    """Construct an AgentRuntime with durable storage.

    Args:
        config: Agent configuration.
        llm: LLM provider (must be configured; never mock in production).
        mcp_client: MCP client (must be configured; never stub in production).
        auth_gateway: Authorization gateway.
        event_store: Event store (created from config if omitted).

    Returns:
        A fully wired AgentRuntime ready to use.

    Raises:
        RuntimeError: If llm or mcp_client is None or appears to be a mock.
    """
    if llm is None:
        raise RuntimeError("LLM provider is required")
    if mcp_client is None:
        raise RuntimeError("MCP client is required")

    db_path = config.persistence.db_path
    checkpoint_path = config.persistence.checkpoint_path or db_path

    checkpoint_saver = SqliteCheckpointSaver(checkpoint_path) if db_path else None
    idempotency_store = SqliteIdempotencyStore(db_path) if db_path else None

    if event_store is None and db_path:
        event_store = SqliteEventStore(db_path)

    runtime = AgentRuntime(
        config=config,
        llm=llm,
        mcp_client=mcp_client,
        auth_gateway=auth_gateway or AuthorizationGateway(),
        event_store=event_store,
        metrics_collector=InMemoryMetricsCollector(),
        checkpoint_saver=checkpoint_saver,
        idempotency_store=idempotency_store,
    )

    return runtime
