"""Production composition root.

Assembles the full application: LLM provider, MCP client, durable
storage, authorization, HITL, and FastAPI. Fails fast if configuration
is missing or invalid.

Never imports or instantiates test fakes (MockLLM, StubMCPClient, etc.).
"""

from __future__ import annotations

import os

from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.auth import AuthorizationGateway
from fxfill_banking_agent.config import AgentConfig, PersistenceConfig
from fxfill_banking_agent.hitl_store import SqliteHITLStore
from fxfill_banking_agent.logging import configure_logging, get_logger
from fxfill_banking_agent.providers.base import ProviderConfig

logger = get_logger(__name__)


async def bootstrap_app(
    *,
    agent_config: AgentConfig | None = None,
    provider_config: ProviderConfig | None = None,
    db_path: str | None = None,
):
    """Bootstrap the complete production application.

    Args:
        agent_config: Agent configuration override.
        provider_config: Provider configuration override.
        db_path: Override for the database path.

    Returns:
        A configured FastAPI application ready to serve.

    Raises:
        RuntimeError: If required configuration is missing.
    """

    # ── Configuration ──────────────────────────────────────────────
    cfg = agent_config or AgentConfig()
    pcfg = provider_config or ProviderConfig()

    if db_path:
        cfg = AgentConfig(
            environment=cfg.environment,
            llm=cfg.llm,
            persistence=PersistenceConfig(db_path=db_path),
        )

    # ── Logging ────────────────────────────────────────────────────
    configure_logging()

    # ── LLM Provider ───────────────────────────────────────────────
    token = os.environ.get(pcfg.token_env_var, "")
    if not token:
        raise RuntimeError(
            f"Environment variable {pcfg.token_env_var} is not set. "
            f"Cannot create production LLM provider."
        )

    from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

    llm = DeepSeekProvider(config=pcfg, token=token)
    logger.info("provider_created", type="deepseek", model=pcfg.model)

    # ── MCP Client ─────────────────────────────────────────────────
    from fxfill_banking_agent.banking.mcp_server import BankingMCPServer
    from fxfill_banking_agent.mcp.client import MCPClientAdapter

    banking_server = BankingMCPServer()
    mcp = MCPClientAdapter(banking_server)
    await mcp.connect()
    logger.info("mcp_client_created", tool_count=len(mcp.tools))

    # ── Auth Gateway ───────────────────────────────────────────────
    auth_gateway = AuthorizationGateway()

    # ── HITL Store ─────────────────────────────────────────────────
    hitl_store = None
    if db_path:
        hitl_store = SqliteHITLStore(db_path)

    # ── Runtime ────────────────────────────────────────────────────
    # ── FastAPI ────────────────────────────────────────────────────
    app = create_app(
        llm=llm,
        mcp_client=mcp,
        config=cfg,
        auth_gateway=auth_gateway,
        hitl_store=hitl_store,
    )

    logger.info("bootstrap_complete")
    return app
