"""Production composition root.

Assembles the full application: LLM provider, MCP client, durable
storage, authorization, HITL executor, and FastAPI. Fails fast if
configuration is missing or invalid.

Never imports or instantiates test fakes (MockLLM, StubMCPClient, etc.).
"""

from __future__ import annotations

import os

from fxfill_banking_agent.actor_resolver import ApprovalActorResolver, DevelopmentHeaderResolver
from fxfill_banking_agent.api import HITLConfigurationError, create_app
from fxfill_banking_agent.approval_executor import HITLApprovalExecutor
from fxfill_banking_agent.auth import AuthorizationGateway, ReadOnlyPolicy
from fxfill_banking_agent.banking.mcp_server import BankingMCPServer
from fxfill_banking_agent.config import AgentConfig, PersistenceConfig
from fxfill_banking_agent.grant_repo import GrantRepository
from fxfill_banking_agent.hitl_store import SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.lifecycle import ApplicationResources
from fxfill_banking_agent.logging import configure_logging, get_logger
from fxfill_banking_agent.mcp.client import MCPClientAdapter
from fxfill_banking_agent.persistence import SqliteEventStore
from fxfill_banking_agent.providers.base import ProviderConfig
from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

logger = get_logger(__name__)


async def bootstrap_app(
    *,
    agent_config: AgentConfig | None = None,
    provider_config: ProviderConfig | None = None,
    db_path: str | None = None,
    production_mode: bool = False,
    approval_actor_resolver: ApprovalActorResolver | None = None,
):
    """Bootstrap the complete production application.

    All pure validation runs *before* any resource is opened so that
    a partial failure never leaves dangling connections.

    Args:
        agent_config: Agent configuration override.
        provider_config: Provider configuration override.
        db_path: Database path (required for HITL-enabled production).
        production_mode: When True, development safeguards are disabled.

    Returns:
        A configured FastAPI application ready to serve.

    Raises:
        RuntimeError: If required configuration is missing.
        HITLConfigurationError: If HITL is required but dependencies are absent.
    """
    cfg = agent_config or AgentConfig()
    pcfg = provider_config or ProviderConfig()

    # ═══════════════════════════════════════════════════════════════════
    # Phase 1: Pure validation — no resources opened yet
    # ═══════════════════════════════════════════════════════════════════

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

    # Token / environment validation
    token = os.environ.get(pcfg.token_env_var, "")
    if not token:
        raise RuntimeError(f"Environment variable {pcfg.token_env_var} is not set")

    # Actor resolver validation (before resources)
    if approval_actor_resolver is not None:
        actor_resolver = approval_actor_resolver
    elif production_mode:
        raise RuntimeError("Production mode requires approval_actor_resolver")
    else:
        actor_resolver = DevelopmentHeaderResolver()

    if production_mode and isinstance(actor_resolver, DevelopmentHeaderResolver):
        raise RuntimeError("DevelopmentHeaderResolver not allowed in production mode")

    configure_logging()

    # ═══════════════════════════════════════════════════════════════════
    # Phase 2: Resource creation with rollback
    # ═══════════════════════════════════════════════════════════════════

    resources = ApplicationResources()

    try:
        # ── LLM Provider ───────────────────────────────────────────
        llm = DeepSeekProvider(config=pcfg, token=token)
        resources.llm_provider = llm
        logger.info("provider_created", type="deepseek", model=pcfg.model)

        # ── MCP Client ─────────────────────────────────────────────
        banking_server = BankingMCPServer()
        mcp = MCPClientAdapter(banking_server)
        await mcp.connect()
        resources.mcp_client = mcp
        logger.info("mcp_client_created", tool_count=len(mcp.tools))

        # ── Auth Gateway ───────────────────────────────────────────
        auth_gateway = AuthorizationGateway(policy=ReadOnlyPolicy())

        # ── Durable HITL dependencies ──────────────────────────────
        if db_path:
            hitl_store = SqliteHITLStore(db_path)
            resources.hitl_store = hitl_store
            grant_repo = GrantRepository(db_path)
            resources.grant_repo = grant_repo
            idem_store = SqliteIdempotencyStore(db_path)
            resources.idempotency_store = idem_store
            event_store = SqliteEventStore(db_path)
            await event_store.connect()
            resources.event_store = event_store
        else:
            hitl_store = None
            grant_repo = None
            idem_store = None
            event_store = None

        # ── HITL Approval Executor ─────────────────────────────────
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
                raise HITLConfigurationError("Production mode requires full HITL dependency set")
            approval_executor = None

        # ── FastAPI ────────────────────────────────────────────────
        app = create_app(
            llm=llm,
            mcp_client=mcp,
            config=cfg,
            auth_gateway=auth_gateway,
            hitl_store=hitl_store,
            grant_repo=grant_repo,
            approval_executor=approval_executor,
            resources=resources,
        )

        logger.info("bootstrap_complete", production=production_mode, db_path=db_path)
        return app

    except BaseException:
        await resources.close()
        raise
