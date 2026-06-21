"""Production composition root.

Assembles the full application: LLM provider, MCP client, durable
storage, authorization, HITL executor, and FastAPI. Fails fast if
configuration is missing or invalid.

Never imports or instantiates test fakes (MockLLM, StubMCPClient, etc.).
"""

from __future__ import annotations

import os

from fxfill_banking_agent.actor_resolver import ApprovalActorResolver, DevelopmentHeaderResolver
from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.approval_executor import HITLApprovalExecutor
from fxfill_banking_agent.auth import AuthorizationGateway, ReadOnlyPolicy
from fxfill_banking_agent.config import AgentConfig, PersistenceConfig
from fxfill_banking_agent.grant_repo import GrantRepository
from fxfill_banking_agent.hitl_store import SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.logging import configure_logging, get_logger
from fxfill_banking_agent.persistence import SqliteEventStore
from fxfill_banking_agent.providers.base import ProviderConfig

logger = get_logger(__name__)


async def bootstrap_app(
    *,
    agent_config: AgentConfig | None = None,
    provider_config: ProviderConfig | None = None,
    db_path: str | None = None,
    production_mode: bool = False,
):
    """Bootstrap the complete production application.

    Args:
        agent_config: Agent configuration override.
        provider_config: Provider configuration override.
        db_path: Database path (required for HITL-enabled production).
        production_mode: When True, development safeguards are disabled.

    Returns:
        A configured FastAPI application ready to serve.

    Raises:
        RuntimeError: If required configuration is missing.
    """
    cfg = agent_config or AgentConfig()
    pcfg = provider_config or ProviderConfig()

    if db_path:
        cfg = AgentConfig(
            environment=cfg.environment,
            llm=cfg.llm,
            persistence=PersistenceConfig(db_path=db_path),
        )
    else:
        if production_mode:
            raise RuntimeError(
                "Production mode requires db_path — refusing to start without durable storage"
            )

    configure_logging()

    # ── LLM Provider ───────────────────────────────────────────────
    token = os.environ.get(pcfg.token_env_var, "")
    if not token:
        raise RuntimeError(f"Environment variable {pcfg.token_env_var} is not set")

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
    auth_gateway = AuthorizationGateway(policy=ReadOnlyPolicy())

    # ── Durable HITL dependencies (all required when db_path is set) ──
    if db_path:
        hitl_store = SqliteHITLStore(db_path)
        grant_repo = GrantRepository(db_path)
        idem_store = SqliteIdempotencyStore(db_path)
        event_store = SqliteEventStore(db_path)
        await event_store.connect()
    else:
        hitl_store = None
        grant_repo = None
        idem_store = None
        event_store = None

    # ── Actor resolver ─────────────────────────────────────────────
    actor_resolver: ApprovalActorResolver
    if production_mode:
        raise RuntimeError(
            "Production actor resolver not configured — must provide authenticated identity"
        )
    else:
        actor_resolver = DevelopmentHeaderResolver()

    # ── HITL Approval Executor ─────────────────────────────────────
    if db_path and hitl_store and grant_repo and idem_store and event_store:
        approval_executor = HITLApprovalExecutor(
            hitl_store=hitl_store,
            grant_repo=grant_repo,
            idempotency_store=idem_store,
            event_store=event_store,
            mcp_client=mcp,
            actor_resolver=actor_resolver,
        )
    else:
        if production_mode:
            raise RuntimeError("Production mode requires full HITL dependency set")
        approval_executor = None

    # ── FastAPI ────────────────────────────────────────────────────
    app = create_app(
        llm=llm,
        mcp_client=mcp,
        config=cfg,
        auth_gateway=auth_gateway,
        hitl_store=hitl_store,
        grant_repo=grant_repo,
        approval_executor=approval_executor,
    )

    logger.info("bootstrap_complete", production=production_mode, db_path=db_path)
    return app
